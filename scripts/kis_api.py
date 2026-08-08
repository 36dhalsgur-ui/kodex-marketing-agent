"""한국투자증권 KIS Open API 클라이언트 — 종목별 투자자 매매동향.

KRX Open API에는 투자자별 순매수(외국인·기관·개인)가 없다. 서비스 목록에
없고 후보 경로도 404로 확인했다(2026-08-05). 섹터 수급과 태동기 '조용한 매집'
판정은 그 데이터가 있어야 성립하므로 증권사 API로 보완한다.

사용 전 준비 (사람이 직접 — 계정 생성·키 발급은 대행할 수 없다):
  1. 한국투자증권 계좌 개설 (MTS 화면번호 0281)
  2. ID 등록 (4503) → 오픈API 서비스 신청 (3944)
  3. 발급받은 APP Key/Secret을 환경변수로
       export KIS_APP_KEY="..."
       export KIS_APP_SECRET="..."

주의 — 접근토큰은 1분에 한 번만 발급된다(EGW00133). 유효시간이 24시간이므로
디스크에 캐시해 재사용한다. 캐시가 없으면 배치가 시작조차 못 하는 일이 생긴다.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

BASE = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "kis_token.json"
INVESTOR_URL = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
INVESTOR_TR = "FHPTJ04160001"

RATE_SLEEP = 0.3      # 실측: 0.12초로 돌리면 EGW00201(초당 거래건수 초과)이 뜬다
RATE_RETRY = 4        # 초당 한도는 잠깐 쉬면 풀린다 — 실패로 버리지 않는다
TIMEOUT = 20


class KisApiError(RuntimeError):
    pass


def _creds() -> tuple[str, str]:
    k, s = os.environ.get("KIS_APP_KEY", ""), os.environ.get("KIS_APP_SECRET", "")
    if not (k and s):
        raise KisApiError(
            "KIS_APP_KEY / KIS_APP_SECRET이 없습니다. 한국투자증권 오픈API를 "
            "신청해 발급받으세요 (계정·키 발급은 직접 해야 합니다)."
        )
    return k, s


def token(force: bool = False) -> str:
    """접근토큰. 24시간 유효하므로 캐시해 쓴다 — 재발급은 1분당 1회로 막혀 있다."""
    if not force and TOKEN_CACHE.exists():
        try:
            d = json.loads(TOKEN_CACHE.read_text())
            if d.get("exp", 0) > time.time() + 600:      # 10분 여유
                return d["tok"]
        except Exception:
            pass
    key, sec = _creds()
    try:
        r = requests.post(f"{BASE}/oauth2/tokenP", timeout=TIMEOUT,
                          json={"grant_type": "client_credentials",
                                "appkey": key, "appsecret": sec})
        d = r.json() if r.content else {}
    except requests.RequestException as e:
        raise KisApiError(f"토큰 발급 실패 — {type(e).__name__}")
    if "access_token" not in d:
        raise KisApiError(f"토큰 발급 실패 — {d.get('error_description') or d or r.status_code}")
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({
        "tok": d["access_token"],
        "exp": time.time() + int(d.get("expires_in", 86400)),
    }))
    return d["access_token"]


def investor_daily(code: str, bas_dd: str) -> list[dict]:
    """종목별 투자자 매매동향(일별). code는 6자리, bas_dd는 YYYYMMDD.

    한 번 호출에 그 날짜 기준 최근 30영업일치가 output2로 온다.
    """
    key, sec = _creds()
    last = ""
    for attempt in range(RATE_RETRY):
        time.sleep(RATE_SLEEP * (attempt + 1))
        try:
            r = requests.get(f"{BASE}{INVESTOR_URL}", timeout=TIMEOUT,
                             headers={"authorization": f"Bearer {token()}",
                                      "appkey": key, "appsecret": sec,
                                      "tr_id": INVESTOR_TR, "custtype": "P"},
                             params={"FID_COND_MRKT_DIV_CODE": "J",
                                     "FID_INPUT_ISCD": code,
                                     "FID_INPUT_DATE_1": bas_dd,
                                     "FID_ORG_ADJ_PRC": "", "FID_ETC_CLS_CODE": ""})
        except requests.RequestException as e:
            # 타임아웃·연결 끊김은 KisApiError가 아니라 그대로 튀어나가 배치 전체를
            # 죽였다(실측 2026-08-07: 종목 하나의 ReadTimeout으로 26개 섹터가 통째로
            # 날아감). 네트워크 오류도 재시도 대상으로 잡고, 끝내 안 되면 우리 예외로
            # 바꿔 호출부가 종목 단위로 건너뛸 수 있게 한다.
            last = f"{type(e).__name__}"
            continue
        try:
            d = r.json()
        except Exception:
            raise KisApiError(f"{code} {bas_dd} — JSON 아님: {r.text[:150]}")
        if d.get("rt_cd") == "0":
            return d.get("output2") or []
        last = f"{d.get('msg1', '')} ({d.get('msg_cd', '')})".strip()
        if d.get("msg_cd") != "EGW00201":     # 초당 한도 외에는 재시도해도 소용없다
            break
    raise KisApiError(f"{code} {bas_dd} — {last}")


# 투자자별 순매수 금액 필드(*_ntby_tr_pbmn)는 **백만원** 단위다(실측 검산:
# 개인 순매수 -2,656,901주 × 108,820원 = -2,891억, 필드값 -269,679 × 100만 = -2,697억).
# 원 단위로 잘못 읽으면 모든 값이 0에 수렴하므로 여기서 한 번만 변환한다.
INVESTOR_FIELDS = {
    "개인": "prsn_ntby_tr_pbmn",
    "외국인": "frgn_ntby_tr_pbmn",
    "기관": "orgn_ntby_tr_pbmn",
    "연기금": "fund_ntby_tr_pbmn",
}


def to_eok(v) -> float:
    """*_ntby_tr_pbmn(백만원) → 억원."""
    try:
        return float(str(v).replace(",", "").strip()) * 1e6 / 1e8
    except (TypeError, ValueError):
        return 0.0
