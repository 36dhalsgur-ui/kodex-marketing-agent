"""섹터 유니버스 배치 — 22개 섹터가 '어떤 종목으로 구성되는지' 수집.

실행: 주 1회 (구성종목은 자주 바뀌지 않아 가볍게 돌린다)
  python scripts/sector_universe.py
필요: KRX_ID / KRX_PW

산출: data/sector_universe.json
  {asof, sectors: [{섹터, 군, 기준, 종목수, 종목: [{티커, 종목명, 비중?}]}]}

- 1군(KRX 섹터지수 17): 지수 구성종목 — 비중 정보는 제공되지 않아 종목명만
- 2군(테마 5): KODEX ETF PDF — 구성종목명과 **비중**까지 제공되므로 비중 내림차순

시그널 보드의 국면 판정이 '어떤 종목 묶음'을 근거로 한 것인지 확인할 수 있게 한다.
"""

import json
import sys
import time
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_batch import SECTORS  # 섹터 정의를 공유 (drift 방지)

from pykrx import stock

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sector_universe.json"
MAX_ITEMS = 40


def index_members(code: str) -> list[dict]:
    """KRX 섹터지수 구성종목 — 티커 + 종목명 (비중 미제공)."""
    out = []
    for t in stock.get_index_portfolio_deposit_file(code):
        if not (isinstance(t, str) and len(t) == 6 and t.isdigit()):
            continue
        try:
            nm = stock.get_market_ticker_name(t)
            nm = nm if isinstance(nm, str) else str(nm)
        except Exception:
            nm = "-"
        out.append({"티커": t, "종목명": nm})
        time.sleep(0.02)
    return out[:MAX_ITEMS]


def etf_members(code: str) -> list[dict]:
    """KODEX ETF PDF — 구성종목명 + 비중(%) 내림차순.
    KRX 응답이 간헐적으로 비어 오므로(실측) 재시도한다."""
    df = None
    for attempt in range(3):
        try:
            df = stock.get_etf_portfolio_deposit_file(code)
            if df is not None and len(df):
                break
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    if df is None or not len(df):
        raise ValueError("PDF 응답 없음(3회 재시도)")
    rows = []
    for tk, r in df.iterrows():
        nm = r.get("구성종목명")
        if not isinstance(nm, str) or not nm.strip():
            continue
        try:
            w = float(r.get("비중") or 0)
        except Exception:
            w = 0.0
        rows.append({"티커": str(tk), "종목명": nm.strip(), "비중": round(w, 2)})
    rows.sort(key=lambda x: -x["비중"])
    return rows[:MAX_ITEMS]


def main():
    import os
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        sys.exit("KRX_ID/KRX_PW 환경변수가 필요합니다.")

    print(f"[섹터 유니버스] {date.today().isoformat()} · {len(SECTORS)}개")
    out = []
    for cfg in SECTORS:
        name = cfg["name"]
        kind, code = cfg["roster"]
        row = {"섹터": name, "군": "테마" if kind == "etf_pdf" else "KRX섹터",
               "기준": (f'{cfg["kodex"]} 구성종목(PDF)' if kind == "etf_pdf"
                      else f"KRX {name} 지수 구성종목")}
        try:
            row["종목"] = etf_members(code) if kind == "etf_pdf" else index_members(code)
            row["종목수"] = len(row["종목"])
            print(f"  - {name}: {row['종목수']}종목")
        except Exception as e:
            row["종목"], row["종목수"] = [], 0
            row["비고"] = f"수집 실패: {type(e).__name__}"
            print(f"  - {name}: 실패 {type(e).__name__}")
        out.append(row)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"asof": date.today().isoformat(), "sectors": out},
                              ensure_ascii=False, indent=2))
    print(f"[완료] {OUT} — {sum(r['종목수'] for r in out)}개 종목")


if __name__ == "__main__":
    main()
