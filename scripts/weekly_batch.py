"""주간 배치 수집기 — RRG 시그널 보드용 실데이터 (22개 섹터·테마).

실행: 주 1회 (금요일 장마감 후) 로컬에서
  python scripts/weekly_batch.py
필요: KRX_ID / KRX_PW 환경변수 (KRX 정보데이터시스템 로그인)

산출: data/signal_board.json

구성 (3계층):
- 1군 KRX 공식 섹터지수 17개 — 가격 = 지수, 수급 명부 = 지수 구성종목
- 2군 마케팅 테마 5개 (KRX 지수 부재) — 가격 = KODEX ETF, 수급 명부 = ETF PDF
- 3군 해외 테마 4개 — 가격 = KODEX 해외 ETF, 벤치마크도 해외(KODEX 미국S&P500)

  ※ 3군을 분리한 이유: 국내 반도체 지수가 과열기여도 미국 반도체가 과열기인 것은
    아니다. 기초시장이 다르면 국면도 다르므로 판정을 분리한다. 벤치마크로 원화표시
    KODEX 미국S&P500을 쓰면 분자·분모 모두 원화라 환율 효과가 상쇄된다.
  ※ 3군은 구성종목이 해외 주식이라 KRX 투자자별 순매수가 존재하지 않는다 → 수급 없음.

방법론:
- 단계: RRG — 상대강도(가격/벤치마크)의 26주 평균 대비 수준 × 4주/12주 평균 모멘텀
  (수준−·모멘텀+ = 태동기 / +·+ = 확산기 / +·− = 과열기 / −·− = 쇠퇴기)
- 수급 확인: 구성종목의 최근 13주(분기) 순매수 합의 부호 — 큰손(외국인+기관) × 개인 2×2
  (태동형 큰손+/개인− · 확산형 +/+ · 과열형 −/+ · 쇠퇴형 −/−)
  ※ 13주 창 선택 근거: 2·4주는 부호가 연 10~18회 뒤집혀 판독 불가, 13주는 연 ~4회로 안정 (실측)
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
import pandas as pd

# pykrx는 import 시점에 KRX 로그인을 수행한다. 차단 상태면 여기서 바로 예외가 나
# 우리 안내문을 띄울 기회조차 없다 — 차단 확인 뒤에 불러온다(main에서 _load_pykrx).
stock = None


def _load_pykrx() -> None:
    global stock
    from pykrx import stock as _stock
    stock = _stock

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "signal_board.json"
BENCH = "5300"                  # KRX 300 — 국내 섹터 기본 벤치마크
BENCH_US = ("etf", "379800")    # KODEX 미국S&P500 — 해외 섹터 벤치마크(원화표시)
BENCH_LABEL = {"KRX300": "KRX 300", "US": "KODEX 미국S&P500"}

# ── 22개 명부: price = ("index"|"etf", 코드) / roster = ("krx_index"|"etf_pdf", 코드)
SECTORS = [
    # 1군 — KRX 공식 섹터지수 17
    {"name": "반도체",     "price": ("index", "5044"), "roster": ("krx_index", "5044"), "kodex": "KODEX 반도체"},
    {"name": "은행",       "price": ("index", "5046"), "roster": ("krx_index", "5046"), "kodex": "KODEX 은행"},
    {"name": "자동차",     "price": ("index", "5043"), "roster": ("krx_index", "5043"), "kodex": "KODEX 자동차"},
    {"name": "헬스케어",   "price": ("index", "5045"), "roster": ("krx_index", "5045"), "kodex": "KODEX 바이오·헬스케어"},
    {"name": "에너지화학", "price": ("index", "5048"), "roster": ("krx_index", "5048"), "kodex": "KODEX 에너지화학"},
    {"name": "철강",       "price": ("index", "5049"), "roster": ("krx_index", "5049"), "kodex": "KODEX 철강"},
    {"name": "방송통신",   "price": ("index", "5051"), "roster": ("krx_index", "5051"), "kodex": ""},
    {"name": "건설",       "price": ("index", "5052"), "roster": ("krx_index", "5052"), "kodex": "KODEX 건설"},
    {"name": "증권",       "price": ("index", "5054"), "roster": ("krx_index", "5054"), "kodex": "KODEX 증권"},
    {"name": "기계장비",   "price": ("index", "5055"), "roster": ("krx_index", "5055"), "kodex": "KODEX 기계장비"},
    {"name": "보험",       "price": ("index", "5056"), "roster": ("krx_index", "5056"), "kodex": "KODEX 보험"},
    {"name": "운송",       "price": ("index", "5057"), "roster": ("krx_index", "5057"), "kodex": "KODEX 운송"},
    {"name": "경기소비재", "price": ("index", "5061"), "roster": ("krx_index", "5061"), "kodex": "KODEX 경기소비재"},
    {"name": "필수소비재", "price": ("index", "5062"), "roster": ("krx_index", "5062"), "kodex": "KODEX 필수소비재"},
    {"name": "K콘텐츠",    "price": ("index", "5063"), "roster": ("krx_index", "5063"), "kodex": "KODEX K콘텐츠"},
    {"name": "정보기술",   "price": ("index", "5064"), "roster": ("krx_index", "5064"), "kodex": "KODEX IT"},
    {"name": "유틸리티",   "price": ("index", "5065"), "roster": ("krx_index", "5065"), "kodex": "KODEX 유틸리티"},
    # 2군 — 마케팅 테마 (KRX 섹터지수 부재 → KODEX ETF)
    {"name": "방산",       "price": ("etf", "0080G0"), "roster": ("etf_pdf", "0080G0"), "kodex": "KODEX 방산TOP10"},
    {"name": "2차전지",    "price": ("etf", "305720"), "roster": ("etf_pdf", "305720"), "kodex": "KODEX 2차전지산업"},
    {"name": "조선",       "price": ("etf", "0115D0"), "roster": ("etf_pdf", "0115D0"), "kodex": "KODEX 조선TOP10"},
    {"name": "AI·전력",    "price": ("etf", "487240"), "roster": ("etf_pdf", "487240"), "kodex": "KODEX AI전력핵심설비"},
    {"name": "원자력",     "price": ("etf", "0098F0"), "roster": ("etf_pdf", "0098F0"), "kodex": "KODEX 원자력SMR"},
    # 3군 — 해외 테마 (벤치마크 = KODEX 미국S&P500 · 수급 미집계)
    {"name": "미국반도체",  "price": ("etf", "390390"), "roster": None, "bench": "US", "kodex": "KODEX 미국반도체"},
    {"name": "미국AI전력",  "price": ("etf", "487230"), "roster": None, "bench": "US", "kodex": "KODEX 미국AI전력핵심인프라"},
    {"name": "미국AI테크",  "price": ("etf", "485540"), "roster": None, "bench": "US", "kodex": "KODEX 미국AI테크TOP10"},
    {"name": "미국우주항공", "price": ("etf", "0167Z0"), "roster": None, "bench": "US", "kodex": "KODEX 미국우주항공"},
]

TODAY = date.today()
FR_53W = (TODAY - timedelta(weeks=53)).strftime("%Y%m%d")
FR_13W = (TODAY - timedelta(weeks=13)).strftime("%Y%m%d")
TO = TODAY.strftime("%Y%m%d")

# 수급 집계에 쓰는 기관 세부 분류 (합산 = 기관 전체)
INST_COLS = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]


# KRX는 자동화 대량 조회를 탐지하면 IP를 1일 차단한다. 차단되면 로그인 페이지가
# JSON 대신 'ip-block-page' 안내 HTML을 돌려주고, pykrx는 그것을 파싱하려다 실패해
# 빈 DataFrame을 준다. 우리 코드는 열을 꺼내다 KeyError를 보게 된다 — KeyError는
# 증상이고 원인은 차단이다(실측 2026-08-01).
#
# 차단 상태에서 재시도·재로그인을 반복하면 요청만 늘어 차단이 연장될 수 있다.
# 그래서 차단을 감지하면 즉시 멈춘다. 재시도는 일시적 오류에만 쓴다.
_KRX_BLOCK_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
_krx_blocked = False


def krx_block_notice() -> str | None:
    """KRX 접속 차단이면 안내문을, 아니면 None을 돌려준다."""
    try:
        import requests
        r = requests.get(_KRX_BLOCK_URL, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        if "ip-block-page" not in r.text:
            return None
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S)
        body = [l.strip() for l in re.sub(r"<[^>]+>", "\n", body).splitlines() if l.strip()]
        return " / ".join(body[2:5]) or "KRX 접속 제한"
    except Exception:
        return None


KRX_RETRY = 2


def krx_call(fn, *args, **kwargs):
    """KRX 조회 — 일시적 오류만 한 번 더 시도한다.

    빈 결과도 실패로 본다. 차단 응답은 예외가 아니라 빈 DataFrame으로 오기 때문에
    예외만 잡으면 '조용히 빈 값'이 그대로 통과한다.
    두 번 다 실패하면 차단 여부를 확인하고, 차단이면 배치 전체를 중단한다."""
    global _krx_blocked
    if _krx_blocked:
        raise RuntimeError("KRX 접속 차단 — 조회 중단")
    last = None
    for attempt in range(KRX_RETRY):
        try:
            out = fn(*args, **kwargs)
            if out is not None and len(out):
                return out
            last = ValueError("빈 응답")
        except Exception as e:
            last = e
        if attempt < KRX_RETRY - 1:
            time.sleep(2.0)
    notice = krx_block_notice()
    if notice:
        _krx_blocked = True
        raise RuntimeError(f"KRX 접속 차단 — {notice}")
    raise last if isinstance(last, Exception) else RuntimeError("KRX 조회 실패")


def get_price(kind: str, code: str) -> pd.Series:
    if kind == "index":
        return krx_call(stock.get_index_ohlcv_by_date, FR_53W, TO, code)["종가"]
    return krx_call(stock.get_etf_ohlcv_by_date, FR_53W, TO, code)["종가"]


# ETF PDF의 비주식 행 — 현금·예금·선물 등은 '010010' 같은 6자리 가짜 코드로 들어온다.
# 코드 형식만 보면 통과하므로 구성종목명으로 걸러야 한다. 지금은 미상장 코드라 조회가
# 실패하고 넘어가지만, 실제 상장사 코드와 겹치면 엉뚱한 종목의 순매수가 섞인다.
NON_STOCK_PAT = re.compile(r"현금|예금|예치금|선물|스왑|채권|CD|RP|MMF|원화|외화")


def get_roster(kind: str, code: str) -> list[str]:
    def ok(t) -> bool:
        return isinstance(t, str) and len(t) == 6 and t.isdigit()

    if kind == "krx_index":
        return [t for t in krx_call(stock.get_index_portfolio_deposit_file, code) if ok(t)]
    # ETF PDF는 KRX가 간헐적으로 빈 응답을 준다(실측). krx_call이 빈 응답도 실패로
    # 보고 재로그인 후 재시도한다 — 세션이 끊긴 경우까지 함께 처리된다.
    pdf = krx_call(stock.get_etf_portfolio_deposit_file, code)
    return [t for t, r in pdf.iterrows()
            if ok(t) and not NON_STOCK_PAT.search(str(r.get("구성종목명") or ""))]


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

    # 차단 상태에서 시작하면 수백 건을 헛되이 던지고 차단만 연장된다 — 먼저 확인한다
    notice = krx_block_notice()
    if notice:
        sys.exit(f"KRX 접속이 제한된 상태입니다. 배치를 시작하지 않습니다.\n  {notice}")
    _load_pykrx()

    print(f"[배치 시작] {TODAY.isoformat()} · {len(SECTORS)}개 섹터")

    # 전주 단계 (직전 산출물에서) — 브리핑의 '단계 전환' 감지용
    prev_stages: dict[str, str] = {}
    # 직전 수급 — ETF PDF가 실패했을 때 빈 값으로 덮지 않기 위해 보관한다.
    # 수집 실패를 데이터 손실로 만들면 안 된다(가격 판정은 되는데 수급만 사라진다).
    prev_flows: dict[str, dict] = {}
    # 직전 시세·국면 — 수급과 같은 이유로 보관한다. 지금까지는 시세가 실패하면
    # 그냥 '관망'으로 덮어써서 멀쩡하던 RS·국면이 통째로 사라졌다(실측 2026-07-31).
    prev_px: dict[str, dict] = {}
    prev_asof = ""
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
            prev_asof = prev.get("asof", "")
            prev_stages = {r["섹터"]: r.get("단계", "") for r in prev.get("board", [])}
            prev_flows = {r["섹터"]: r for r in prev.get("board", []) if r.get("구성종목수")}
            prev_px = {r["섹터"]: r for r in prev.get("board", [])
                       if r.get("RS수준") is not None}
        except Exception:
            pass
    def _weekly(s: pd.Series) -> pd.Series:
        s = s.resample("W-FRI").last().dropna()
        # 미완결 주 제거 — 금요일 아닌 요일에 실행해도 '마지막 완결 주'로 고정
        return s[[d <= TODAY for d in s.index.date]]

    bench_w = _weekly(stock.get_index_ohlcv_by_date(FR_53W, TO, BENCH)["종가"])
    # 해외 섹터용 — 원화표시 미국 대표 ETF (분자·분모 모두 원화라 환율이 상쇄된다)
    bench_us_w = _weekly(get_price(*BENCH_US))
    BENCH_W = {"KRX300": bench_w, "US": bench_us_w}
    week_end = bench_w.index[-1].date()
    week_start = week_end - timedelta(days=4)

    flow_cache: dict[str, tuple[float, ...] | None] = {}

    def flows(tk: str):
        """종목의 순매수 합계: (외국인13주, 연기금13주, 기관13주, 개인13주, 외국인1주, 연기금1주, 개인1주).
        1주 = 가격과 동일한 마지막 완결 주(week_start~week_end). 실패 시 None."""
        if tk not in flow_cache:
            try:
                d = stock.get_market_trading_value_by_date(FR_13W, TO, tk, detail=True, on="순매수")
                if len(d) and all(c in d.columns for c in ["개인", "외국인"] + INST_COLS):
                    w1 = d[[week_start <= x <= week_end for x in d.index.date]]
                    flow_cache[tk] = (
                        float(d["외국인"].sum()),
                        float(d["연기금"].sum()),
                        float(d[INST_COLS].sum(axis=1).sum()),
                        float(d["개인"].sum()),
                        float(w1["외국인"].sum()),
                        float(w1["연기금"].sum()),
                        float(w1["개인"].sum()),
                    )
                else:
                    flow_cache[tk] = None
                time.sleep(0.1)
            except Exception:
                flow_cache[tk] = None
        return flow_cache[tk]

    board = []
    px_failed: list[str] = []
    for cfg in SECTORS:
        name = cfg["name"]
        bkey = cfg.get("bench", "KRX300")
        bw = BENCH_W[bkey]
        row = {"섹터": name,
               "군": "해외" if bkey != "KRX300" else ("테마" if cfg["price"][0] == "etf" else "KRX섹터"),
               "벤치마크": BENCH_LABEL[bkey], "KODEX": cfg["kodex"]}
        # ── 가격 → RRG
        try:
            px = get_price(*cfg["price"])
            w = _weekly(px)
            if len(w) >= 2:
                row["주간수익률"] = round(float((w.iloc[-1] / w.iloc[-2] - 1) * 100), 2)
            rs = (w / bw).dropna()
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
                    "초과수익4주": round(float((w.iloc[-1] / w.iloc[-5] - 1) * 100 - (bw.iloc[-1] / bw.iloc[-5] - 1) * 100), 1),
                    "가격백분위52주": round(float(px.rank(pct=True).iloc[-1]) * 100),
                    "궤적": "→".join(path),
                })
        except Exception as e:
            px_failed.append(name)
            keep = prev_px.get(name)
            if keep:
                # 시세를 못 받았다고 국면을 지우면 안 된다 — 직전 판정을 남기고
                # 언제 것인지 밝힌다(수급과 같은 원칙).
                for k in ("단계", "RS수준", "RS모멘텀", "주간수익률",
                          "초과수익4주", "가격백분위52주", "궤적"):
                    if k in keep:
                        row[k] = keep[k]
                row["비고"] = f"시세 실패({type(e).__name__}) — {prev_asof} 판정 유지"
            else:
                row.update({"단계": "관망", "비고": f"시세 실패: {type(e).__name__}"})

        # ── 수급 — 13주(분기) 순매수 합 (주체별 분리 표시용)
        # 해외 섹터(roster=None)는 구성종목이 해외 주식이라 KRX 투자자별 순매수가 없다.
        # 국내 종목처럼 조회하면 헛돌기만 하므로 아예 건너뛴다.
        if not cfg.get("roster"):
            row["수급비고"] = "해외 구성종목 — KRX 투자자별 순매수 미제공"
            if prev_stages.get(name):
                row["전주단계"] = prev_stages[name]
            print(f"  - {name}: {row.get('단계','?')} (해외 · 수급 없음)")
            board.append(row)
            continue
        try:
            stks = get_roster(*cfg["roster"])
            frn = pen = inst = indiv = 0.0
            frn1 = pen1 = indiv1 = 0.0
            used = 0
            for tk in stks:
                f = flows(tk)
                if f is None:
                    continue
                frn += f[0]
                pen += f[1]
                inst += f[2]
                indiv += f[3]
                frn1 += f[4]
                pen1 += f[5]
                indiv1 += f[6]
                used += 1
            if used:
                big = frn + inst  # 외국인+기관 전체 (쇠퇴기 재매집 정렬 기준)
                row.update({
                    "외국인13주억": round(frn / 1e8),
                    "연기금13주억": round(pen / 1e8),
                    "개인13주억": round(indiv / 1e8),
                    "큰손13주억": round(big / 1e8),
                    "외국인1주억": round(frn1 / 1e8),
                    "연기금1주억": round(pen1 / 1e8),
                    "개인1주억": round(indiv1 / 1e8),
                    "구성종목수": used,
                })
        except Exception as e:
            keep = prev_flows.get(name)
            if keep:
                # 이번 주 수급은 못 받았지만 직전 값이라도 남긴다 — 언제 것인지 함께 표시
                for k in ("외국인13주억", "연기금13주억", "개인13주억", "큰손13주억",
                          "외국인1주억", "연기금1주억", "개인1주억", "구성종목수"):
                    if k in keep:
                        row[k] = keep[k]
                row["수급비고"] = f"수급 실패({type(e).__name__}) — {prev_asof} 수집분 유지"
            else:
                row["수급비고"] = f"수급 실패: {type(e).__name__}"

        if prev_stages.get(name):
            row["전주단계"] = prev_stages[name]
        print(f"  - {name}: {row.get('단계','?')} (수급 {row.get('구성종목수','–')}종목)")
        board.append(row)

    # 대량 실패면 아예 쓰지 않는다. 세션이 끊기면 그 뒤 섹터가 줄줄이 실패하는데,
    # 그대로 덮어쓰면 멀쩡하던 지난주 보드를 잃는다(실측: 26개 중 15개가 관망으로 덮임).
    # 절반 넘게 실패했으면 파일을 건드리지 않고 비정상 종료해 커밋을 막는다.
    if len(px_failed) > len(SECTORS) // 2:
        sys.exit(f"시세 실패 {len(px_failed)}/{len(SECTORS)} — KRX 세션이 끊긴 것으로 "
                 f"보입니다. 기존 보드를 보존하고 중단합니다: {', '.join(px_failed[:6])}…")
    if px_failed:
        print(f"[경고] 시세 실패 {len(px_failed)}개 — {', '.join(px_failed)}")

    OUT.parent.mkdir(exist_ok=True)
    bench_wk_ret = round(float((bench_w.iloc[-1] / bench_w.iloc[-2] - 1) * 100), 2)
    OUT.write_text(json.dumps(
        {"asof": TODAY.isoformat(), "benchmark": "KRX 300",
         "benchmark_해외": "KODEX 미국S&P500",
         "주간구간": f"{week_start.isoformat()} ~ {week_end.isoformat()}",
         "벤치주간수익률": bench_wk_ret,
         "벤치주간수익률_해외": round(float((bench_us_w.iloc[-1] / bench_us_w.iloc[-2] - 1) * 100), 2),
         "지표버전": "RRG 26/12/4주 · 수급 13주 부호(2×2)", "board": board},
        ensure_ascii=False, indent=2))
    n = sum(1 for r in board if r.get("단계") != "쇠퇴기")
    print(f"[완료] {OUT} — {len(board)}개 (비쇠퇴 {n}개) · 종목 캐시 {len(flow_cache)}건")


if __name__ == "__main__":
    main()
