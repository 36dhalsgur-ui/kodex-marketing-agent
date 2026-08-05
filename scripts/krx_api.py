"""KRX Open API 클라이언트 (openapi.krx.co.kr).

KRX가 공식 경로로 안내하는 API다. 기존 pykrx 방식은 화면용 엔드포인트를 긁는
것이라 이용약관 제10조 제2호(자동화 수단을 통한 무단 수집) 위반으로 IP가 1일
차단됐다(실측 2026-08-01). 이 모듈은 그 대체다.

사용 전 준비 (사람이 직접 해야 한다 — 계정 생성·키 발급은 대행할 수 없다):
  1. data.krx.co.kr 회원가입 후 로그인
  2. openapi.krx.co.kr → 마이페이지에서 인증키(AUTH_KEY) 발급 신청
  3. 쓰려는 서비스별로 이용 신청 → 관리자 승인 대기
  4. 발급받은 키를 환경변수 KRX_API_KEY 에 넣는다 (~/.zshrc)

pykrx 대비 이점 — 요청 수가 근본적으로 줄어든다:
  pykrx  종목 400개 × 13주 순매수 = 수백~수천 요청
  OpenAPI 날짜 1건 = 전 종목 1회 → 65거래일이면 65요청
날짜 단위 응답이라 종목이 늘어도 요청 수가 늘지 않는다.

한도: 하루 10,000회 (공개 안내 기준).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

BASE = "https://data-dbg.krx.co.kr/svc/apis"

# 확인된 엔드포인트 — 카테고리/서비스. 서비스 목록 전체는 인증키 발급 후
# scripts/krx_api_probe.py 로 실제 호출해 확정한다(차단 중에는 문서 열람도 막힌다).
ENDPOINTS = {
    "유가증권_일별매매": "sto/stk_bydd_trd",
    "코스닥_일별매매": "sto/ksq_bydd_trd",
    "유가증권_종목기본": "sto/stk_isu_base_info",
    "코스닥_종목기본": "sto/ksq_isu_base_info",
    "ETF_일별매매": "etp/etf_bydd_trd",
    "ETN_일별매매": "etp/etn_bydd_trd",
    "KOSPI지수_일별": "idx/kospi_dd_trd",
    "KOSDAQ지수_일별": "idx/kosdaq_dd_trd",
    "KRX지수_일별": "idx/krx_dd_trd",
}

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "krx_api"
RATE_SLEEP = 0.3          # 호출 간 최소 간격 — 한도(1만/일)와 무관하게 예의
TIMEOUT = 30


class KrxApiError(RuntimeError):
    pass


def _key() -> str:
    k = os.environ.get("KRX_API_KEY", "").strip()
    if not k:
        raise KrxApiError(
            "KRX_API_KEY가 없습니다. openapi.krx.co.kr에서 인증키를 발급받아 "
            "환경변수로 설정하세요 (계정 생성·키 발급은 직접 해야 합니다)."
        )
    return k


def fetch(service: str, bas_dd: str, use_cache: bool = True) -> list[dict]:
    """하루치 데이터를 통째로 받는다.

    service — ENDPOINTS의 값 또는 'sto/stk_bydd_trd' 형태의 경로
    bas_dd  — 기준일자 YYYYMMDD

    과거 날짜의 값은 바뀌지 않으므로 디스크에 캐시한다. 같은 날짜를 다시
    부르지 않는 것이 한도를 아끼고 차단을 피하는 가장 확실한 방법이다.
    """
    path = ENDPOINTS.get(service, service)
    cf = CACHE / path.replace("/", "_") / f"{bas_dd}.json"
    if use_cache and cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass

    time.sleep(RATE_SLEEP)
    r = requests.get(f"{BASE}/{path}", params={"basDd": bas_dd},
                     headers={"AUTH_KEY": _key()}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise KrxApiError(f"{path} {bas_dd} — HTTP {r.status_code}: {r.text[:200]}")
    try:
        body = r.json()
    except Exception:
        # 차단·점검 시 JSON이 아닌 HTML이 온다 — 원문 앞부분을 남겨 원인을 보이게 한다
        raise KrxApiError(f"{path} {bas_dd} — JSON 아님: {r.text[:200]}")

    # 응답 래핑 키는 서비스마다 다르다(OutBlock_1 등) — 리스트인 첫 값을 쓴다
    rows = next((v for v in body.values() if isinstance(v, list)), None)
    if rows is None:
        raise KrxApiError(f"{path} {bas_dd} — 목록 없음: {str(body)[:200]}")

    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(rows, ensure_ascii=False))
    return rows


# ── 주간 스냅샷 ────────────────────────────────────────────────────
# RRG는 주간 종가만 쓴다. 일별을 전부 받을 이유가 없다.
#   일별 53주 × 5일 × 2종 = 530회   →   주 1회씩 53 × 2종 = 106회
# 과거 주는 캐시되므로 매주 새로 받는 건 2회뿐이다.
#
# 두 소스를 각자 날짜로 되짚으면 어긋난다(실측): 휴장일에 지수 API는 0건을
# 주는데 ETF API는 행을 주되 종가가 빈 문자열이다. 그래서 ETF 쪽만 휴장일을
# 유효한 날로 잘못 잡아 4주가 어긋났고 RS가 틀어졌다.
# → 거래일은 지수 API로 한 번 정하고, ETF는 그 날짜에만 맞춰 받는다.
# → 시계열 인덱스는 실제 거래일이 아니라 '그 주의 금요일'로 고정해 항상 정렬된다.

_CAL_SERVICE = "idx/krx_dd_trd"


def trading_dates(weeks: int = 53, end: "date | None" = None,
                  max_back: int = 6) -> dict[str, str]:
    """주별 마지막 거래일. {주금요일 YYYYMMDD: 실제 거래일 YYYYMMDD}

    end 이후의 미완결 주는 담지 않는다 — 금요일이 아닌 날 실행해도
    '마지막 완결 주'로 고정되도록 기존 배치와 같은 규칙을 지킨다.
    """
    from datetime import date as _date, timedelta
    end = end or _date.today()
    last_fri = end - timedelta(days=(end.weekday() - 4) % 7)
    out: dict[str, str] = {}
    for i in range(weeks):
        fri = last_fri - timedelta(weeks=i)
        for back in range(max_back):
            dd = (fri - timedelta(days=back)).strftime("%Y%m%d")
            try:
                if fetch(_CAL_SERVICE, dd):      # 휴장일은 0건
                    out[fri.strftime("%Y%m%d")] = dd
                    break
            except KrxApiError:
                continue
    return dict(sorted(out.items()))


def snapshots(service: str, dates: dict[str, str]) -> dict[str, list[dict]]:
    """정해진 거래일들의 데이터를 주금요일 키로 담는다."""
    out: dict[str, list[dict]] = {}
    for week, dd in dates.items():
        try:
            rows = fetch(service, dd)
        except KrxApiError:
            continue
        if rows:
            out[week] = rows
    return out


def series_from(snaps: dict[str, list[dict]], key: str, value: str,
                match: str) -> "pd.Series":
    """주간 스냅샷에서 한 종목·지수의 시계열을 뽑는다. 인덱스는 주금요일.

    key   — 행을 식별하는 필드 (ISU_CD / IDX_NM)
    value — 값 필드 (TDD_CLSPRC / CLSPRC_IDX)
    match — key가 이 값과 같은 행을 고른다
    빈 문자열·0은 값이 없는 것으로 보고 건너뛴다(휴장일 잔여 행 방어).
    """
    import pandas as pd
    idx, vals = [], []
    for week, rows in sorted(snaps.items()):
        row = next((r for r in rows if r.get(key) == match), None)
        if row is None:
            continue
        try:
            v = float(str(row[value]).replace(",", "").strip())
        except (KeyError, ValueError):
            continue
        if v <= 0:
            continue
        idx.append(pd.Timestamp(week))
        vals.append(v)
    return pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
