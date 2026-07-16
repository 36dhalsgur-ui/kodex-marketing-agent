"""주간 배치 수집기 — RRG 시그널 보드용 실데이터.

실행: 주 1회 (금요일 장마감 후) 로컬에서
  python scripts/weekly_batch.py
필요: KRX_ID / KRX_PW 환경변수 (KRX 정보데이터시스템 로그인)

산출: data/signal_board.json
  테마별 [RRG 단계, RS수준, RS모멘텀, 4주 초과수익, 52주 가격백분위,
         개인 주간점수(0/1/2), 연기금·외국인 월간점수 합산(0~4), 근거 수치]

방법론:
- 단계: RRG — 상대강도(ETF종가/KRX300)의 26주 평균 대비 수준 × 4주/12주 평균 모멘텀
- 수급 점수: 구성종목(KRX 섹터지수 또는 ETF PDF) 순매수 합의 부호 + 지속성
  (한화리서치 산식 재현 검증: 반도체 개인 5주·방산 개인 6주 완전 일치, 2026-07)
"""

import json
import os
import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
from pykrx import stock
from pykrx.website.krx.etx.core import ETF_투자자별거래실적_개별종목_일별추이 as ETF_INV

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "signal_board.json"

# ── 테마 명부: (가격용 ETF 티커, 수급 명부 출처)
# roster: ("krx_index", 지수티커) — KRX 섹터지수 구성종목
#         ("etf_pdf", ETF티커)   — 해당 ETF의 PDF 구성종목
THEMES = {
    "반도체":   {"etf": "091160", "roster": ("krx_index", "5044")},
    "은행":     {"etf": "091170", "roster": ("krx_index", "5046")},
    "자동차":   {"etf": "091180", "roster": ("krx_index", "5043")},
    "바이오":   {"etf": "244580", "roster": ("krx_index", "5045")},
    "2차전지":  {"etf": "305720", "roster": ("etf_pdf", "305720")},
    "방산":     {"etf": "0080G0", "roster": ("etf_pdf", "0080G0")},
}

BENCH = "5300"  # KRX 300


def dstr(d: date) -> str:
    return d.strftime("%Y%m%d")


TODAY = date.today()
FR_52W = dstr(TODAY - timedelta(weeks=53))
FR_14M = dstr(TODAY - timedelta(days=430))
FR_13W = dstr(TODAY - timedelta(weeks=14))
TO = dstr(TODAY)


def get_roster_stocks(kind: str, code: str) -> list[str]:
    if kind == "krx_index":
        items = stock.get_index_portfolio_deposit_file(code)
    else:
        items = stock.get_etf_portfolio_deposit_file(code).index
    return [t for t in items if isinstance(t, str) and len(t) == 6 and t.isdigit()]


def persistence_scores(series: pd.Series, freq: str) -> list[int]:
    """순매수 합의 부호 + 지속성 점수 (이번 기간 순매수=1, 직전 기간도 순매수=2, 순매도=0)."""
    agg = series.resample(freq).sum()
    out, prev = [], None
    for v in agg.values:
        pos = v > 0
        out.append(2 if (pos and prev) else (1 if pos else 0))
        prev = pos
    return out


def rrg_metrics(etf_close_w: pd.Series, bench_w: pd.Series):
    rs = (etf_close_w / bench_w).dropna()
    if len(rs) < 27:
        return None
    ratio = float((rs.iloc[-1] / rs.rolling(26).mean().iloc[-1] - 1) * 100)
    mom = float((rs.rolling(4).mean().iloc[-1] / rs.rolling(12).mean().iloc[-1] - 1) * 100)
    return ratio, mom


def quad(ratio: float, mom: float) -> str:
    if ratio >= 0 and mom >= 0:
        return "확산기"
    if ratio < 0 and mom >= 0:
        return "태동기"
    if ratio >= 0 and mom < 0:
        return "과열기"
    return "쇠퇴기"


def main():
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        sys.exit("KRX_ID/KRX_PW 환경변수가 필요합니다.")

    print(f"[배치 시작] {TODAY.isoformat()}")
    bench = stock.get_index_ohlcv_by_date(FR_52W, TO, BENCH)["종가"]
    bench_w = bench.resample("W-FRI").last().dropna()

    flow_cache: dict[str, pd.DataFrame] = {}

    def stock_flows(tk: str) -> pd.DataFrame | None:
        if tk in flow_cache:
            return flow_cache[tk]
        try:
            d = stock.get_market_trading_value_by_date(FR_14M, TO, tk, detail=True, on="순매수")
            if "개인" not in d.columns or len(d) == 0:
                flow_cache[tk] = None
            else:
                flow_cache[tk] = d[["개인", "연기금", "외국인"]]
            time.sleep(0.15)
        except Exception:
            flow_cache[tk] = None
        return flow_cache[tk]

    board = []
    for theme, cfg in THEMES.items():
        print(f"  - {theme} 수집 중…")
        row = {"테마": theme, "ETF": cfg["etf"]}
        try:
            px = stock.get_etf_ohlcv_by_date(FR_52W, TO, cfg["etf"])
            close = px["종가"]
            close_w = close.resample("W-FRI").last().dropna()
            m = rrg_metrics(close_w, bench_w)
            if m is None:
                row["단계"] = "관망"
                row["비고"] = f"이력 {len(close_w)}주 — 26주 미달"
            else:
                ratio, mom = m
                row.update({
                    "단계": quad(ratio, mom),
                    "RS수준": round(ratio, 1),
                    "RS모멘텀": round(mom, 1),
                    "초과수익4주": round(
                        (close_w.iloc[-1] / close_w.iloc[-5] - 1) * 100
                        - (bench_w.iloc[-1] / bench_w.iloc[-5] - 1) * 100, 1),
                    "가격백분위52주": round(float(close.rank(pct=True).iloc[-1]) * 100),
                })
            # 회전율(참고): 최근 4주 거래대금 합 / 최근 시총 근사(종가×상장주식수 미취득 → 생략 가능)
        except Exception as e:
            row["단계"] = "관망"
            row["비고"] = f"시세 수집 실패: {e}"

        # 수급 점수 — 구성종목 합산
        try:
            stks = get_roster_stocks(*cfg["roster"])
            indiv = pension = foreign = None
            used = 0
            for tk in stks:
                d = stock_flows(tk)
                if d is None:
                    continue
                indiv = d["개인"] if indiv is None else indiv.add(d["개인"], fill_value=0)
                pension = d["연기금"] if pension is None else pension.add(d["연기금"], fill_value=0)
                foreign = d["외국인"] if foreign is None else foreign.add(d["외국인"], fill_value=0)
                used += 1
            if used:
                w_indiv = persistence_scores(indiv.last("100D"), "W-FRI")
                m_pen = persistence_scores(pension, "ME")
                m_for = persistence_scores(foreign, "ME")
                row.update({
                    "개인주간점수": w_indiv[-1],
                    "개인점수궤적": w_indiv[-6:],
                    "큰손월간점수": m_pen[-1] + m_for[-1],
                    "연기금월점수": m_pen[-1], "외국인월점수": m_for[-1],
                    "개인4주억": round(float(indiv.last("28D").sum()) / 1e8),
                    "구성종목수": used,
                })
        except Exception as e:
            row["수급비고"] = f"수급 수집 실패: {e}"

        board.append(row)

    OUT.parent.mkdir(exist_ok=True)
    payload = {"asof": TODAY.isoformat(), "benchmark": "KRX 300", "board": board}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[완료] {OUT} — {len(board)}개 테마")


if __name__ == "__main__":
    main()
