"""ETF 실데이터 배치 — 라인업 · 주간 순유입 · 순자산.

실행: 주 1회 (weekly_batch.py / channel_batch.py 와 함께)
  python scripts/etf_batch.py
필요: KRX_API_KEY (openapi.krx.co.kr 인증키)

산출: data/etf_flows.json
  {asof, weeks: [...], etfs: [{종목명, 티커, 운용사, 테마, 기초시장, 순자산억,
                              주간: [{주차, 순유입억, 좌수증감, NAV}]}]}

데이터 출처: KRX Open API 'ETF 일별매매정보' 하나로 전부 해결된다.
날짜 1건 응답에 전 종목(1,160종)의 종가·NAV·순자산총액·상장좌수가 들어 있어,
예전처럼 종목마다 조회할 필요가 없다. 주 1회씩 13주 = 13회면 끝이다.
(예전 방식은 종목 400개 × 10주 = 수천 요청이었고, 그래서 IP가 차단됐다.)

지표 변경 — 개인 순매수 → 상장좌수 기반 순유입:
  순유입액 = Δ상장좌수 × NAV
  ETF는 자금이 들어오면 좌수가 늘고 빠지면 줄어든다(설정·환매).
  기존에 쓰던 개인 순매수는 장내 손바뀜이라, 개인이 사면 누군가는 판 것이어서
  ETF 규모가 늘었다는 뜻이 아니다. 좌수 증감은 신규 유입만 잡는다.
  '마케팅이 새 자금을 끌어왔는가'라는 질문에는 이쪽이 정확하다.
  (투자자별 순매수는 KRX Open API가 제공하지 않는다 — 서비스 목록에 없고
   후보 경로도 404로 확인. 주체 구분이 필요하면 증권사 API를 붙여야 한다.)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import data as D  # 분류 기준을 앱과 공유 (drift 방지)
from krx_api import KrxApiError, snapshots, trading_dates

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_flows.json"
ETF_SVC = "etp/etf_bydd_trd"

N_WEEKS = 12          # DiD 베이스라인 8주 + 여유

# 분류·브랜드 판별은 data.py의 단일 기준을 재사용한다 (앱과 drift 방지).
# 기초시장을 분리하는 이유: '반도체' 하나로 묶으면 미국반도체 처치군에
# 한국반도체가 대조군으로 붙어 DiD의 평행추세 가정이 깨진다.
classify = D.classify_etf
brand_of = D.etf_brand_of


def _num(v) -> float | None:
    """빈 문자열·0·콤마를 걸러 양수만 돌려준다(휴장일 잔여 행 방어)."""
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def week_label(dd: str) -> str:
    """YYYYMMDD → '7월 4주' (앱의 주차 라벨 규칙과 동일)."""
    d = date.fromisoformat(f"{dd[:4]}-{dd[4:6]}-{dd[6:]}")
    return f"{d.month}월 {(d.day - 1) // 7 + 1}주"


def main():
    if not os.environ.get("KRX_API_KEY"):
        sys.exit("KRX_API_KEY 환경변수가 필요합니다 (openapi.krx.co.kr 인증키).")

    print(f"[ETF 배치] {date.today().isoformat()}")
    try:
        # Δ좌수를 내려면 첫 주에도 직전 주가 있어야 한다 → 1주 더 받는다
        dates = trading_dates(weeks=N_WEEKS + 1)
        snaps = snapshots(ETF_SVC, dates)
    except KrxApiError as e:
        sys.exit(f"KRX Open API 조회 실패 — {e}")
    if len(snaps) < 3:
        sys.exit(f"주간 스냅샷 {len(snaps)}주 — 분석 불가")

    weeks_sorted = sorted(snaps)
    print(f"  스냅샷 {len(weeks_sorted)}주 · {weeks_sorted[0]} ~ {weeks_sorted[-1]}")

    # 종목별 시계열로 뒤집는다 — {티커: {주: 행}}
    by_tk: dict[str, dict[str, dict]] = {}
    latest_name: dict[str, str] = {}
    for wk in weeks_sorted:
        for r in snaps[wk]:
            tk = r.get("ISU_CD")
            if not tk:
                continue
            by_tk.setdefault(tk, {})[wk] = r
            latest_name[tk] = r.get("ISU_NM", "")

    result = []
    for tk, series in by_tk.items():
        nm = latest_name.get(tk, "")
        brand = brand_of(nm)
        if not brand:                     # 8개 브랜드 외는 제외
            continue
        theme, market = classify(nm)
        wk_rows, prev_sh = [], None
        for wk in weeks_sorted:
            r = series.get(wk)
            if r is None:
                continue
            sh, nav = _num(r.get("LIST_SHRS")), _num(r.get("NAV"))
            if sh is None or nav is None:
                continue
            if prev_sh is not None:
                # 좌수 증감 × NAV = 그 주에 실제로 들어오고 나간 돈
                wk_rows.append({
                    "주차": week_label(wk),
                    "순유입억": round((sh - prev_sh) * nav / 1e8),
                    "좌수증감": int(sh - prev_sh),
                    "NAV": round(nav, 2),
                })
            prev_sh = sh
        if not wk_rows:
            continue
        last = series.get(weeks_sorted[-1]) or series[max(series)]
        aum = _num(last.get("INVSTASST_NETASST_TOTAMT"))
        result.append({
            "종목명": nm, "티커": tk, "운용사": brand,
            "테마": theme, "기초시장": market,
            "순자산억": round(aum / 1e8) if aum else None,
            "주간": wk_rows[-N_WEEKS:],
        })

    # 라인업 공백 테마의 경쟁사 순자산 — 신규 출시 판단에 쓴다.
    # 공백은 정의상 KODEX가 없는 테마라 위 목록(8개 브랜드)에 없을 수 있다.
    # 이제 전 종목이 한 응답에 있으므로 이름으로 바로 찾는다.
    last_rows = {r.get("ISU_NM", ""): r for r in snaps[weeks_sorted[-1]]}
    gap_aum: dict[str, float] = {}
    got = {r["종목명"] for r in result}
    try:
        for g in D.lineup_gaps():
            for cn in D.gap_competitors(g["테마"], g["시장"], limit=8):
                if cn in gap_aum or cn in got:
                    continue
                row = last_rows.get(cn)
                v = _num(row.get("INVSTASST_NETASST_TOTAMT")) if row else None
                if v:
                    gap_aum[cn] = round(v / 1e8)
        print(f"  라인업 공백 경쟁사 순자산 {len(gap_aum)}종")
    except Exception as e:
        print(f"  공백 경쟁사 순자산 수집 실패: {type(e).__name__}")

    weeks = [week_label(w) for w in weeks_sorted[1:]][-N_WEEKS:]
    kodex_n = sum(1 for r in result if r["운용사"] == "KODEX")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "asof": date.today().isoformat(),
        "weeks": weeks,
        "지표": "순유입 = Δ상장좌수 × NAV (설정·환매 기준). "
              "장내 손바뀜인 개인 순매수와 달리 신규 유입만 잡는다.",
        "출처": "한국거래소 통계정보 (KRX Open API · ETF 일별매매정보)",
        "etfs": result,
        "공백경쟁사순자산": gap_aum,
    }, ensure_ascii=False, indent=2))
    n_aum = sum(1 for r in result if r.get("순자산억"))
    print(f"[완료] {OUT} — {len(result)}종 (KODEX {kodex_n} · 순자산 확보 {n_aum}종) · {len(weeks)}주")


if __name__ == "__main__":
    main()
