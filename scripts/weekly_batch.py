"""주간 배치 수집기 — RRG 시그널 보드용 실데이터 (22개 섹터·테마).

실행: 주 1회 (금요일 장마감 후) 로컬에서
  python scripts/weekly_batch.py
필요: KRX_ID / KRX_PW 환경변수 (KRX 정보데이터시스템 로그인)

산출: data/signal_board.json

구성 (2계층):
- 1군 KRX 공식 섹터지수 17개 — 가격 = 지수, 수급 명부 = 지수 구성종목
- 2군 마케팅 테마 5개 (KRX 지수 부재) — 가격 = KODEX ETF, 수급 명부 = ETF PDF

방법론:
- 단계: RRG — 상대강도(가격/KRX300)의 26주 평균 대비 수준 × 4주/12주 평균 모멘텀
  (수준−·모멘텀+ = 태동기 / +·+ = 확산기 / +·− = 과열기 / −·− = 쇠퇴기)
- 수급 확인: 구성종목의 최근 13주(분기) 순매수 합의 부호 — 큰손(외국인+기관) × 개인 2×2
  (태동형 큰손+/개인− · 확산형 +/+ · 과열형 −/+ · 쇠퇴형 −/−)
  ※ 13주 창 선택 근거: 2·4주는 부호가 연 10~18회 뒤집혀 판독 불가, 13주는 연 ~4회로 안정 (실측)
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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "signal_board.json"
BENCH = "5300"  # KRX 300

# ── 22개 명부: price = ("index"|"etf", 코드) / roster = ("krx_index"|"etf_pdf", 코드)
SECTORS = [
    # 1군 — KRX 공식 섹터지수 17
    {"name": "반도체",     "price": ("index", "5044"), "roster": ("krx_index", "5044"), "kodex": "KODEX 반도체·미국반도체"},
    {"name": "은행",       "price": ("index", "5046"), "roster": ("krx_index", "5046"), "kodex": "KODEX 은행"},
    {"name": "자동차",     "price": ("index", "5043"), "roster": ("krx_index", "5043"), "kodex": "KODEX 자동차"},
    {"name": "헬스케어",   "price": ("index", "5045"), "roster": ("krx_index", "5045"), "kodex": "KODEX 바이오·헬스케어"},
    {"name": "에너지화학", "price": ("index", "5048"), "roster": ("krx_index", "5048"), "kodex": "KODEX 에너지화학"},
    {"name": "철강",       "price": ("index", "5049"), "roster": ("krx_index", "5049"), "kodex": "KODEX 철강"},
    {"name": "방송통신",   "price": ("index", "5051"), "roster": ("krx_index", "5051"), "kodex": "KODEX 미디어&엔터"},
    {"name": "건설",       "price": ("index", "5052"), "roster": ("krx_index", "5052"), "kodex": "KODEX 건설"},
    {"name": "증권",       "price": ("index", "5054"), "roster": ("krx_index", "5054"), "kodex": "KODEX 증권"},
    {"name": "기계장비",   "price": ("index", "5055"), "roster": ("krx_index", "5055"), "kodex": "KODEX 기계장비"},
    {"name": "보험",       "price": ("index", "5056"), "roster": ("krx_index", "5056"), "kodex": "KODEX 보험"},
    {"name": "운송",       "price": ("index", "5057"), "roster": ("krx_index", "5057"), "kodex": "KODEX 운송"},
    {"name": "경기소비재", "price": ("index", "5061"), "roster": ("krx_index", "5061"), "kodex": "KODEX 경기소비재"},
    {"name": "필수소비재", "price": ("index", "5062"), "roster": ("krx_index", "5062"), "kodex": "KODEX 필수소비재"},
    {"name": "K콘텐츠",    "price": ("index", "5063"), "roster": ("krx_index", "5063"), "kodex": "KODEX Fn웹툰&드라마"},
    {"name": "정보기술",   "price": ("index", "5064"), "roster": ("krx_index", "5064"), "kodex": "KODEX IT"},
    {"name": "유틸리티",   "price": ("index", "5065"), "roster": ("krx_index", "5065"), "kodex": "KODEX 유틸리티"},
    # 2군 — 마케팅 테마 (KRX 섹터지수 부재 → KODEX ETF)
    {"name": "방산",       "price": ("etf", "0080G0"), "roster": ("etf_pdf", "0080G0"), "kodex": "KODEX 방산TOP10"},
    {"name": "2차전지",    "price": ("etf", "305720"), "roster": ("etf_pdf", "305720"), "kodex": "KODEX 2차전지산업"},
    {"name": "조선",       "price": ("etf", "0115D0"), "roster": ("etf_pdf", "0115D0"), "kodex": "KODEX 조선TOP10"},
    {"name": "AI·전력",    "price": ("etf", "487240"), "roster": ("etf_pdf", "487240"), "kodex": "KODEX AI전력핵심설비"},
    {"name": "원자력",     "price": ("etf", "0098F0"), "roster": ("etf_pdf", "0098F0"), "kodex": "KODEX 원자력SMR"},
]

TODAY = date.today()
FR_53W = (TODAY - timedelta(weeks=53)).strftime("%Y%m%d")
FR_13W = (TODAY - timedelta(weeks=13)).strftime("%Y%m%d")
TO = TODAY.strftime("%Y%m%d")

# 수급 집계에 쓰는 기관 세부 분류 (합산 = 기관 전체)
INST_COLS = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]


def get_price(kind: str, code: str) -> pd.Series:
    if kind == "index":
        return stock.get_index_ohlcv_by_date(FR_53W, TO, code)["종가"]
    return stock.get_etf_ohlcv_by_date(FR_53W, TO, code)["종가"]


def get_roster(kind: str, code: str) -> list[str]:
    items = (
        stock.get_index_portfolio_deposit_file(code)
        if kind == "krx_index"
        else stock.get_etf_portfolio_deposit_file(code).index
    )
    return [t for t in items if isinstance(t, str) and len(t) == 6 and t.isdigit()]


def flow_signature(big: float, indiv: float) -> str:
    """13주 순매수 부호 2×2 → 수급 시그니처.
    태동형: 큰손+ 개인− / 확산형: +/+ / 과열형: −/+ / 쇠퇴형: −/−"""
    if big > 0:
        return "확산형" if indiv > 0 else "태동형"
    return "과열형" if indiv > 0 else "쇠퇴형"


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

    print(f"[배치 시작] {TODAY.isoformat()} · {len(SECTORS)}개 섹터")
    bench_w = (
        stock.get_index_ohlcv_by_date(FR_53W, TO, BENCH)["종가"]
        .resample("W-FRI").last().dropna()
    )

    flow_cache: dict[str, tuple[float, float] | None] = {}

    def flows(tk: str):
        """종목의 13주 순매수 합계: (외국인, 연기금, 기관전체, 개인). 실패 시 None."""
        if tk not in flow_cache:
            try:
                d = stock.get_market_trading_value_by_date(FR_13W, TO, tk, detail=True, on="순매수")
                if len(d) and all(c in d.columns for c in ["개인", "외국인"] + INST_COLS):
                    flow_cache[tk] = (
                        float(d["외국인"].sum()),
                        float(d["연기금"].sum()),
                        float(d[INST_COLS].sum(axis=1).sum()),
                        float(d["개인"].sum()),
                    )
                else:
                    flow_cache[tk] = None
                time.sleep(0.1)
            except Exception:
                flow_cache[tk] = None
        return flow_cache[tk]

    board = []
    for cfg in SECTORS:
        name = cfg["name"]
        row = {"섹터": name, "군": "테마" if cfg["price"][0] == "etf" else "KRX섹터", "KODEX": cfg["kodex"]}
        # ── 가격 → RRG
        try:
            px = get_price(*cfg["price"])
            w = px.resample("W-FRI").last().dropna()
            rs = (w / bench_w).dropna()
            if len(rs) < 27:
                row.update({"단계": "관망", "비고": f"이력 {len(rs)}주 — 26주 미달"})
            else:
                ratio = float((rs.iloc[-1] / rs.rolling(26).mean().iloc[-1] - 1) * 100)
                mom = float((rs.rolling(4).mean().iloc[-1] / rs.rolling(12).mean().iloc[-1] - 1) * 100)
                path = []
                for lag in (8, 4, 0):
                    sub = rs.iloc[: len(rs) - lag] if lag else rs
                    r = (sub.iloc[-1] / sub.rolling(26).mean().iloc[-1] - 1) * 100
                    m = (sub.rolling(4).mean().iloc[-1] / sub.rolling(12).mean().iloc[-1] - 1) * 100
                    path.append(quad(r, m))
                row.update({
                    "단계": quad(ratio, mom),
                    "RS수준": round(ratio, 1), "RS모멘텀": round(mom, 1),
                    "초과수익4주": round(float((w.iloc[-1] / w.iloc[-5] - 1) * 100 - (bench_w.iloc[-1] / bench_w.iloc[-5] - 1) * 100), 1),
                    "가격백분위52주": round(float(px.rank(pct=True).iloc[-1]) * 100),
                    "궤적": "→".join(path),
                })
        except Exception as e:
            row.update({"단계": "관망", "비고": f"시세 실패: {type(e).__name__}"})

        # ── 수급 — 13주(분기) 순매수 합 (주체별 분리 표시용)
        try:
            stks = get_roster(*cfg["roster"])
            frn = pen = inst = indiv = 0.0
            used = 0
            for tk in stks:
                f = flows(tk)
                if f is None:
                    continue
                frn += f[0]
                pen += f[1]
                inst += f[2]
                indiv += f[3]
                used += 1
            if used:
                big = frn + inst  # 외국인+기관 전체 (쇠퇴기 재매집 정렬 기준)
                row.update({
                    "외국인13주억": round(frn / 1e8),
                    "연기금13주억": round(pen / 1e8),
                    "개인13주억": round(indiv / 1e8),
                    "큰손13주억": round(big / 1e8),
                    "구성종목수": used,
                })
        except Exception as e:
            row["수급비고"] = f"수급 실패: {type(e).__name__}"

        print(f"  - {name}: {row.get('단계','?')} (수급 {row.get('구성종목수','–')}종목)")
        board.append(row)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(
        {"asof": TODAY.isoformat(), "benchmark": "KRX 300",
         "지표버전": "RRG 26/12/4주 · 수급 13주 부호(2×2)", "board": board},
        ensure_ascii=False, indent=2))
    n = sum(1 for r in board if r.get("단계") != "쇠퇴기")
    print(f"[완료] {OUT} — {len(board)}개 (비쇠퇴 {n}개) · 종목 캐시 {len(flow_cache)}건")


if __name__ == "__main__":
    main()
