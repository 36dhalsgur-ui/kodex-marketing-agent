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
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import data as D  # 분류 기준을 앱과 공유 (drift 방지)
from kis_api import (INVESTOR_FIELDS, KisApiError, etf_components,
                     investor_daily, to_eok)
from krx_api import KrxApiError, fetch, snapshots, trading_dates

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_flows.json"
ETF_SVC = "etp/etf_bydd_trd"

# DiD 베이스라인 8주 + 이벤트 이전 구간. 12주로는 6월 초 시작한 장기 이벤트의
# '이벤트 전'이 1주밖에 안 남아 측정 자체가 불가능했다(실측 2026-08-08:
# 미국S&P500·나스닥100). 24주면 그 두 건이 측정되고, 나머지 건의 평행추세도
# '검증 불가'에서 '양호'로 바뀐다 — 사전 DiD가 5주 이상 확보되기 때문.
# 비용은 거의 없다: 주간 스냅샷은 날짜당 1회 호출로 전 종목이 오고 디스크
# 캐시라, 매주 새로 받는 건 1건뿐이다.
N_WEEKS = 24

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
    """YYYYMMDD → '7월 4주' (앱의 주차 라벨 규칙과 동일).

    라벨은 '그 주의 금요일'로 매긴다. 날짜 자체로 매기면 같은 주가 갈린다 —
    2026-07-27(월)은 '7월 4주', 같은 주 금요일 07-31은 '7월 5주'가 되어
    일별 수급을 주 단위로 합칠 때 한 주가 두 라벨로 쪼개진다(실측).
    """
    d = date.fromisoformat(f"{dd[:4]}-{dd[4:6]}-{dd[6:]}")
    fri = d + timedelta(days=4 - d.weekday()) if d.weekday() <= 4 else d
    return f"{fri.month}월 {(fri.day - 1) // 7 + 1}주"


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
    first_wk: dict[str, str] = {}
    for wk in weeks_sorted:
        for r in snaps[wk]:
            tk = r.get("ISU_CD")
            if not tk:
                continue
            by_tk.setdefault(tk, {})[wk] = r
            latest_name[tk] = r.get("ISU_NM", "")
            first_wk.setdefault(tk, week_label(wk))

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
        last = series.get(weeks_sorted[-1]) or series[max(series)]
        aum = _num(last.get("INVSTASST_NETASST_TOTAMT"))
        result.append({
            "종목명": nm, "티커": tk, "운용사": brand,
            "테마": theme, "기초시장": market,
            # 공시 기초지수명 — 대조군 선정에서 '무엇을 담는 상품인지'의 공식 근거.
            # 상품명 키워드만 보면 커버드콜 풀에 코스피200·팔란티어·금이 섞인다.
            "기초지수": last.get("IDX_IND_NM", "") or "",
            # 데이터에 처음 등장한 주 = 사실상 상장 주. 첫 주는 Δ좌수를 낼 직전 주가
            # 없어 순유입 행이 한 주 늦게 시작하는데, 이걸 '수집 시작'으로 오해하면
            # '수집은 7월 4주부터인데 개입은 7월 3주'라는 앞뒤 안 맞는 설명이 된다.
            # 관측 구간 첫 주부터 있던 종목은 상장 시점을 알 수 없으므로 None.
            "첫주차": first_wk.get(tk) if first_wk.get(tk) != week_label(weeks_sorted[0]) else None,
            "순자산억": round(aum / 1e8) if aum else None,
            # 상장 직후엔 직전 주가 없어 Δ가 안 나온다. 그래도 목록에는 남긴다 —
            # 빼면 라인업·공백 분석과 캠페인 이름 매칭에서 사라진다(실측 2026-08-08:
            # 8/4 상장 KODEX 미국CPU반도체TOP10이 캠페인 매칭에서 누락).
            "주간": wk_rows[-N_WEEKS:],
            "신규상장": not wk_rows,
        })

    # ── 투자자별 순매수 (한국투자증권 KIS API)
    # KRX Open API에는 투자자별 데이터가 없다. 좌수 기반 순유입이 '새 돈이
    # 들어왔나'를 보는 것이라면, 이쪽은 '누가 샀나'를 본다. 마케팅은 개인을
    # 겨냥하므로 둘은 같은 질문의 다른 면이고 함께 봐야 판단이 선다.
    # 한 번 호출에 30영업일(약 6주)이 오므로 12주를 채우려면 두 번 부른다.
    if os.environ.get("KIS_APP_KEY") and os.environ.get("KIS_APP_SECRET"):
        # 투자자별 순매수는 최근 12주만 채운다. DiD는 KRX 좌수 기반 순유입만 쓰고
        # 이 열은 화면 표시용이다. KIS는 종목마다 호출해야 해서(961종 × 앵커)
        # 24주로 늘리면 배치 시간만 배로 든다.
        anchors = [weeks_sorted[-1]]
        for back in (7, 13):                      # 30영업일씩 앞으로
            if len(weeks_sorted) > back:
                anchors.append(weeks_sorted[-back - 1])
        wk_of = {}                                 # 영업일 → 주차 라벨
        got = fail = 0
        for i, r in enumerate(result, 1):
            daily = {}
            for a in anchors:
                try:
                    for d in investor_daily(r["티커"], a):
                        daily[d.get("stck_bsop_date", "")] = d
                except Exception:
                    # 종목 하나의 네트워크 오류로 전체가 죽지 않게 한다(실측 2026-08-07)
                    continue
            if not daily:
                fail += 1
                continue
            # 일별 → 주차 합계
            agg: dict[str, dict[str, float]] = {}
            for dd, d in daily.items():
                if len(dd) != 8:
                    continue
                lb = wk_of.setdefault(dd, week_label(dd))
                acc = agg.setdefault(lb, {k: 0.0 for k in INVESTOR_FIELDS})
                for name, fld in INVESTOR_FIELDS.items():
                    acc[name] += to_eok(d.get(fld))
            for w in r["주간"]:
                a = agg.get(w["주차"])
                if a:
                    w.update({f"{k}순매수억": round(v) for k, v in a.items()})
            got += 1
            if i % 100 == 0:
                print(f"    수급 {i}/{len(result)}")
        print(f"  투자자별 순매수 {got}종 수집 (실패 {fail}종)")
    else:
        print("  투자자별 순매수 건너뜀 — KIS_APP_KEY/SECRET 미설정")

    # ── 일별 종가 → data/etf_prices.json — 수익률 상관(해외 대조군 유사성)용.
    # 날짜 1건 응답에 전 종목이 있어 거래일 수만큼만 부른다. fetch가 날짜별로
    # 디스크 캐시하므로 매주 새 거래일 ~5건만 실제 요청이 나간다.
    days, d = [], date.today()
    while len(days) < 65 and (date.today() - d).days < 100:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    days.reverse()
    closes, valid_dates = {}, []
    for dd in days:
        try:
            rows = fetch(ETF_SVC, dd)
        except KrxApiError:
            continue
        got = 0
        for r in rows:
            px = _num(r.get("TDD_CLSPRC"))
            if px:
                closes.setdefault(r.get("ISU_CD", ""), {})[dd] = px
                got += 1
        if got > 100:                      # 휴장일은 행이 없거나 값이 비어 온다
            valid_dates.append(dd)
    (ROOT / "data" / "etf_prices.json").write_text(json.dumps({
        "asof": date.today().isoformat(), "dates": valid_dates,
        "closes": {tk: [v.get(dd) for dd in valid_dates]
                   for tk, v in closes.items() if tk},
    }, ensure_ascii=False))
    print(f"  일별 종가 {len(valid_dates)}거래일 · {len(closes)}종")

    # ── 구성종목 → data/etf_holdings.json — 대조군 유사성(비중 겹침)의 근거.
    # KRX Open API에는 없고(404 확인) KIS ETF구성종목시세로 받는다.
    # 해외 자산 ETF는 빈 목록이 온다 — 그 종목은 수익률 상관으로 대신한다.
    if os.environ.get("KIS_APP_KEY") and os.environ.get("KIS_APP_SECRET"):
        hold, h_fail = {}, 0
        for i, r in enumerate(result, 1):
            try:
                hold[r["티커"]] = [[c, n, w] for c, n, w in etf_components(r["티커"])]
            except Exception:
                h_fail += 1
            if i % 200 == 0:
                print(f"    구성종목 {i}/{len(result)}")
        (ROOT / "data" / "etf_holdings.json").write_text(json.dumps({
            "asof": date.today().isoformat(), "holdings": hold,
        }, ensure_ascii=False))
        n_has = sum(1 for v in hold.values() if v)
        print(f"  구성종목 {n_has}종 확보 (해외 등 미제공 {len(hold) - n_has} · 실패 {h_fail})")

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
        "지표": "순유입 = Δ상장좌수 × NAV (설정·환매 기준, DiD 처치 지표). "
              "개인·외국인·기관 순매수는 장내 매매 기준으로 함께 싣는다 — "
              "순유입은 '새 돈이 들어왔나', 순매수는 '누가 샀나'를 본다.",
        "출처": "한국거래소 통계정보 (KRX Open API · ETF 일별매매정보) · "
              "투자자별 순매수는 한국투자증권 KIS Open API",
        "etfs": result,
        "공백경쟁사순자산": gap_aum,
    }, ensure_ascii=False, indent=2))
    n_aum = sum(1 for r in result if r.get("순자산억"))
    print(f"[완료] {OUT} — {len(result)}종 (KODEX {kodex_n} · 순자산 확보 {n_aum}종) · {len(weeks)}주")


if __name__ == "__main__":
    main()
