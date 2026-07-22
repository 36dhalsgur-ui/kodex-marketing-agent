"""ETF 실데이터 배치 — 라인업 · 주간 개인 순매수 · 순자산.

실행: 주 1회 (weekly_batch.py / channel_batch.py 와 함께)
  python scripts/etf_batch.py
필요: KRX_ID / KRX_PW 환경변수

산출: data/etf_flows.json
  {asof, weeks: [...], etfs: [{종목명, 티커, 운용사, 테마, 기초시장, 순자산억,
                              주간: [{주차, 개인순매수억, 기관순매수억, 외국인순매수억}]}]}

설계 근거:
- ETF 투자자별 순매수는 주식용 화면이 ETF 코드를 거부해 조회 불가.
  ETF 전용 get_etf_trading_volume_and_value 를 사용한다 (실측 확인).
- 매수강도 분모인 순자산(AUM)은 KRX 시가총액 API에 ETF가 없어
  네이버 etfKeyIndicator.totalNav 를 쓴다 (키 불필요).
- 마케팅 효과 지표는 '개인 순매수'를 주로 쓴다.
  ETF의 금융투자 항목은 LP(유동성공급자)의 설정·환매가 지배해
  (KODEX 200 실측 -1.4조) 투자 판단이 아닌 기계적 물량이기 때문이다.
  대중 마케팅이 겨냥하는 대상도 개인 투자자다.
"""

import json
import os
import re
import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import requests
from pykrx import stock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import data as D  # 분류 기준을 앱과 공유 (drift 방지)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_flows.json"
NAME_CACHE = ROOT / "data" / "etf_names.json"
UA = {"User-Agent": "Mozilla/5.0"}

N_WEEKS = 10          # DiD 베이스라인 8주 + 여유
MAX_PEERS_PER_THEME = 4   # 테마별 경쟁사 ETF 수집 상한 (배치 시간 관리)

# 분류·브랜드 판별은 data.py의 단일 기준을 재사용한다 (앱과 drift 방지).
# 기초시장을 분리하는 이유: '반도체' 하나로 묶으면 미국반도체 처치군에
# 한국반도체가 대조군으로 붙어 DiD의 평행추세 가정이 깨진다.
classify = D.classify_etf
brand_of = D.etf_brand_of


def week_ranges(n: int) -> list[tuple[str, date, date]]:
    """최근 n개 완결 주(월~금) — (주차라벨, 시작일, 종료일)."""
    today = date.today()
    last_fri = today - timedelta(days=(today.weekday() - 4) % 7 or (0 if today.weekday() == 4 else 0))
    if today.weekday() < 4:                      # 이번 주 미완결 → 지난주 금요일로
        last_fri = today - timedelta(days=today.weekday() + 3)
    out = []
    for i in range(n - 1, -1, -1):
        fri = last_fri - timedelta(weeks=i)
        mon = fri - timedelta(days=4)
        out.append((f"{fri.month}월 {(fri.day - 1) // 7 + 1}주", mon, fri))
    return out


def load_names() -> dict[str, str]:
    """티커→종목명. 1,100종 조회가 느려 캐시한다(주 1회 갱신)."""
    if NAME_CACHE.exists():
        try:
            cached = json.loads(NAME_CACHE.read_text())
            if cached:
                print(f"  이름 캐시 사용 ({len(cached)}종) — 갱신하려면 {NAME_CACHE.name} 삭제")
                return cached
        except Exception:
            pass
    names = {}
    for t in stock.get_etf_ticker_list(date.today().strftime("%Y%m%d")):
        try:
            nm = stock.get_etf_ticker_name(t)
            # 일부 티커는 str이 아닌 Series를 반환한다(실측) — 첫 값으로 정규화
            if not isinstance(nm, str):
                nm = str(nm.iloc[0]) if hasattr(nm, "iloc") and len(nm) else str(nm)
            names[t] = nm.strip()
        except Exception:
            continue
    NAME_CACHE.parent.mkdir(exist_ok=True)
    NAME_CACHE.write_text(json.dumps(names, ensure_ascii=False))
    print(f"  이름 {len(names)}종 수집·캐시")
    return names


def fetch_aum(ticker: str) -> float | None:
    """순자산총액(억원) — 네이버 etfKeyIndicator.totalNav ('23조 4,583억')."""
    try:
        d = requests.get(f"https://m.stock.naver.com/api/stock/{ticker}/integration",
                         headers=UA, timeout=8).json()
        raw = (d.get("etfKeyIndicator") or {}).get("totalNav")
        if not raw:
            return None
        s = raw.replace(",", "").replace(" ", "")
        jo = re.search(r"([\d.]+)조", s)
        eok = re.search(r"([\d.]+)억", s)
        return (float(jo.group(1)) * 10000 if jo else 0) + (float(eok.group(1)) if eok else 0)
    except Exception:
        return None


def fetch_week_flow(ticker: str, mon: date, fri: date) -> dict | None:
    """해당 주 투자자별 순매수(억원). 개인 중심, 기관·외국인은 참고."""
    try:
        d = stock.get_etf_trading_volume_and_value(
            mon.strftime("%Y%m%d"), fri.strftime("%Y%m%d"), ticker)
        net = d[("거래대금", "순매수")]
        return {
            "개인순매수억": round(float(net.get("개인", 0)) / 1e8),
            "기관순매수억": round(float(net.get("기관합계", 0)) / 1e8),
            "외국인순매수억": round(float(net.get("외국인", 0)) / 1e8),
        }
    except Exception:
        return None


def main():
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        sys.exit("KRX_ID/KRX_PW 환경변수가 필요합니다.")

    print(f"[ETF 배치] {date.today().isoformat()}")
    names = load_names()

    # 브랜드 필터 → 테마·기초시장 분류
    rows = []
    for tk, nm in names.items():
        b = brand_of(nm)
        if not b:
            continue
        theme, market = classify(nm)
        rows.append({"종목명": nm, "티커": tk, "운용사": b, "테마": theme, "기초시장": market})
    print(f"  8개 브랜드 ETF {len(rows)}종")

    # KODEX 전 종목 + 같은 (테마·시장)의 경쟁사 일부만 수집 (배치 시간 관리)
    kodex = [r for r in rows if r["운용사"] == "KODEX"]
    keys = {(r["테마"], r["기초시장"]) for r in kodex}
    peers = []
    for k in keys:
        cand = [r for r in rows if r["운용사"] != "KODEX" and (r["테마"], r["기초시장"]) == k]
        peers.extend(cand[:MAX_PEERS_PER_THEME])
    target = kodex + peers
    print(f"  수집 대상 {len(target)}종 (KODEX {len(kodex)} + 경쟁 {len(peers)})")

    weeks = week_ranges(N_WEEKS)
    print(f"  주차: {weeks[0][0]} ~ {weeks[-1][0]} ({len(weeks)}주)")

    result = []
    for i, r in enumerate(target, 1):
        wk_rows = []
        for label, mon, fri in weeks:
            f = fetch_week_flow(r["티커"], mon, fri)
            if f:
                wk_rows.append({"주차": label, **f})
            time.sleep(0.05)
        if not wk_rows:
            continue
        r["순자산억"] = fetch_aum(r["티커"])
        r["주간"] = wk_rows
        result.append(r)
        if i % 20 == 0:
            print(f"    {i}/{len(target)} 진행")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "asof": date.today().isoformat(),
        "weeks": [w[0] for w in weeks],
        "지표": "개인 순매수 중심 — ETF 금융투자는 LP 설정·환매가 지배해 제외",
        "etfs": result,
    }, ensure_ascii=False, indent=2))
    n_aum = sum(1 for r in result if r.get("순자산억"))
    print(f"[완료] {OUT} — {len(result)}종 (순자산 확보 {n_aum}종)")


if __name__ == "__main__":
    main()
