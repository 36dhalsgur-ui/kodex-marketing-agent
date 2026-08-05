"""KRX Open API 탐침 — 인증키로 무엇을 받을 수 있는지 실제로 확인한다.

인증키를 발급받은 뒤 한 번 돌린다:
  python scripts/krx_api_probe.py

왜 필요한가: openapi.krx.co.kr의 서비스 목록은 로그인해야 보이고, 승인된
서비스만 실제로 호출된다. 문서를 읽는 것보다 호출해 보는 쪽이 확실하다.
특히 확인해야 할 것은 '투자자별 순매수(외국인·기관·개인)'가 종목 단위로
제공되는지다 — 시그널 보드의 수급 지표 전체가 여기 달려 있다.

출력: 서비스별 성공 여부와 응답 필드 목록. 필드명을 봐야 기존 코드의
어느 열에 대응하는지 매핑할 수 있다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from krx_api import ENDPOINTS, KrxApiError, fetch  # noqa: E402

# 목록에 없지만 있을 법한 후보 — 있으면 좋고 없으면 대안을 찾아야 하는 것들.
# 투자자별 순매수가 여기 걸리는지가 이 탐침의 핵심이다.
CANDIDATES = {
    "투자자별_거래실적(주식)": "sto/stk_invsr_trd",
    "투자자별_거래실적(코스닥)": "sto/ksq_invsr_trd",
    "투자자별_순매수(종목)": "sto/stk_isu_invsr_trd",
    "ETF_구성종목(PDF)": "etp/etf_pdf",
    "ETF_기본정보": "etp/etf_isu_base_info",
    "지수_구성종목": "idx/idx_comp",
}


def last_business_day() -> str:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:          # 토·일 제외 (공휴일은 응답 0건으로 구분된다)
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def probe(label: str, path: str, bas_dd: str) -> None:
    try:
        rows = fetch(path, bas_dd, use_cache=False)
    except KrxApiError as e:
        print(f"  ✗ {label:26s} {path:26s} {str(e)[:90]}")
        return
    if not rows:
        print(f"  △ {label:26s} {path:26s} 응답 0건 (휴장일이거나 미승인)")
        return
    fields = ", ".join(list(rows[0].keys())[:12])
    print(f"  ✓ {label:26s} {path:26s} {len(rows):,}건")
    print(f"      필드: {fields}")


def main() -> None:
    bas_dd = last_business_day()
    print(f"[탐침] 기준일 {bas_dd}\n")
    print("── 공개 문서로 확인된 서비스")
    for label, path in ENDPOINTS.items():
        probe(label, path, bas_dd)
    print("\n── 후보 (있는지 확인이 필요한 것)")
    for label, path in CANDIDATES.items():
        probe(label, path, bas_dd)
    print("\n투자자별 순매수가 하나도 안 잡히면 수급 지표는 다른 경로가 필요합니다.")


if __name__ == "__main__":
    main()
