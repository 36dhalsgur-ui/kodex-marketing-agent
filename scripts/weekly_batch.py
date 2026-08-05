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
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "signal_board.json"
BENCH = "KRX 300"               # KRX 300 — 국내 섹터 기본 벤치마크(지수명)
BENCH_US = "379800"             # KODEX 미국S&P500 — 해외 섹터 벤치마크(원화표시)
BENCH_LABEL = {"KRX300": "KRX 300", "US": "KODEX 미국S&P500"}

# ── 22개 명부: price = ("index"|"etf", 코드) / roster = ("krx_index"|"etf_pdf", 코드)
SECTORS = [
    # 1군 — KRX 공식 섹터지수 17
    {"name": "반도체",     "price": ("index", "KRX 반도체"), "roster": ("krx_index", "5044"), "kodex": "KODEX 반도체"},
    {"name": "은행",       "price": ("index", "KRX 은행"), "roster": ("krx_index", "5046"), "kodex": "KODEX 은행"},
    {"name": "자동차",     "price": ("index", "KRX 자동차"), "roster": ("krx_index", "5043"), "kodex": "KODEX 자동차"},
    {"name": "헬스케어",   "price": ("index", "KRX 헬스케어"), "roster": ("krx_index", "5045"), "kodex": "KODEX 바이오·헬스케어"},
    {"name": "에너지화학", "price": ("index", "KRX 에너지화학"), "roster": ("krx_index", "5048"), "kodex": "KODEX 에너지화학"},
    {"name": "철강",       "price": ("index", "KRX 철강"), "roster": ("krx_index", "5049"), "kodex": "KODEX 철강"},
    {"name": "방송통신",   "price": ("index", "KRX 방송통신"), "roster": ("krx_index", "5051"), "kodex": ""},
    {"name": "건설",       "price": ("index", "KRX 건설"), "roster": ("krx_index", "5052"), "kodex": "KODEX 건설"},
    {"name": "증권",       "price": ("index", "KRX 증권"), "roster": ("krx_index", "5054"), "kodex": "KODEX 증권"},
    {"name": "기계장비",   "price": ("index", "KRX 기계장비"), "roster": ("krx_index", "5055"), "kodex": "KODEX 기계장비"},
    {"name": "보험",       "price": ("index", "KRX 보험"), "roster": ("krx_index", "5056"), "kodex": "KODEX 보험"},
    {"name": "운송",       "price": ("index", "KRX 운송"), "roster": ("krx_index", "5057"), "kodex": "KODEX 운송"},
    {"name": "경기소비재", "price": ("index", "KRX 경기소비재"), "roster": ("krx_index", "5061"), "kodex": "KODEX 경기소비재"},
    {"name": "필수소비재", "price": ("index", "KRX 필수소비재"), "roster": ("krx_index", "5062"), "kodex": "KODEX 필수소비재"},
    {"name": "K콘텐츠",    "price": ("index", "KRX K콘텐츠"), "roster": ("krx_index", "5063"), "kodex": "KODEX K콘텐츠"},
    {"name": "정보기술",   "price": ("index", "KRX 정보기술"), "roster": ("krx_index", "5064"), "kodex": "KODEX IT"},
    {"name": "유틸리티",   "price": ("index", "KRX 유틸리티"), "roster": ("krx_index", "5065"), "kodex": "KODEX 유틸리티"},
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

# 데이터 출처: KRX Open API (openapi.krx.co.kr). 예전에는 pykrx로 화면용
# 엔드포인트를 긁었는데, 이용약관 제10조 제2호(자동화 수단을 통한 무단 수집)
# 위반으로 IP가 1일 차단됐다(실측 2026-08-01). 공식 경로로 옮겼다.
#
# 요청 수: 주 1회씩 53주 × 2종 = 106회(첫 실행), 이후 캐시로 주 2회.
# 한도 10,000회/일 대비 1% 수준이라 재차단 위험이 없다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from krx_api import KrxApiError, series_from, snapshots, trading_dates  # noqa: E402

IDX_SVC = "idx/krx_dd_trd"      # 지수 — 섹터지수 17 + KRX 300이 한 응답에 온다
ETF_SVC = "etp/etf_bydd_trd"    # ETF — 전 종목 시세·NAV·순자산·상장좌수



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
    if not os.environ.get("KRX_API_KEY"):
        sys.exit("KRX_API_KEY 환경변수가 필요합니다 (openapi.krx.co.kr 인증키).")

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
    # ── 시세 수집 — 거래일을 지수 API로 정하고 두 소스를 같은 날짜에 맞춘다.
    # 휴장일에 지수는 0건, ETF는 종가가 빈 행을 주므로 각자 되짚으면 어긋난다.
    try:
        dates = trading_dates(weeks=53, end=TODAY)
        isnap = snapshots(IDX_SVC, dates)
        esnap = snapshots(ETF_SVC, dates)
    except KrxApiError as e:
        sys.exit(f"KRX Open API 조회 실패 — {e}")
    if len(isnap) < 27:
        sys.exit(f"지수 이력 {len(isnap)}주 — 26주 미달로 판정 불가")

    bench_w = series_from(isnap, "IDX_NM", "CLSPRC_IDX", BENCH)
    # 해외 섹터용 — 원화표시 미국 대표 ETF (분자·분모 모두 원화라 환율이 상쇄된다)
    bench_us_w = series_from(esnap, "ISU_CD", "TDD_CLSPRC", BENCH_US)
    BENCH_W = {"KRX300": bench_w, "US": bench_us_w}
    week_end = bench_w.index[-1].date()
    week_start = week_end - timedelta(days=4)
    print(f"  시세 {len(dates)}주 · 마지막 완결 주 {week_start}~{week_end}")

    def price_of(cfg) -> "pd.Series":
        kind, code = cfg["price"]
        if kind == "index":
            return series_from(isnap, "IDX_NM", "CLSPRC_IDX", code)
        return series_from(esnap, "ISU_CD", "TDD_CLSPRC", code)

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
            px = w = price_of(cfg)
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

        # ── 수급 — KRX Open API에는 투자자별 순매수(외국인·기관·개인)가 없다.
        # 서비스 목록에 없고 후보 경로도 404로 확인됐다(실측 2026-08-05).
        # 지우면 ①의 수급 열과 태동기 '조용한 매집' 판정이 통째로 사라지므로,
        # 마지막으로 받은 값을 언제 것인지 밝혀 남긴다. 갱신되지 않는 값이라는
        # 사실이 화면에 드러나야 오해가 없다.
        if not cfg.get("roster"):
            row["수급비고"] = "해외 구성종목 — KRX 투자자별 순매수 미제공"
        else:
            keep = prev_flows.get(name)
            if keep:
                for k in ("외국인13주억", "연기금13주억", "개인13주억", "큰손13주억",
                          "외국인1주억", "연기금1주억", "개인1주억", "구성종목수"):
                    if k in keep:
                        row[k] = keep[k]
                row["수급비고"] = (f"{keep.get('수급기준일') or prev_asof} 수집분 — "
                                 "Open API 전환 후 투자자별 순매수는 갱신되지 않습니다")
                row["수급기준일"] = keep.get("수급기준일") or prev_asof
            else:
                row["수급비고"] = "투자자별 순매수 미수집 — Open API 미제공"

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
    print(f"[완료] {OUT} — {len(board)}개 (비쇠퇴 {n}개)")


if __name__ == "__main__":
    main()
