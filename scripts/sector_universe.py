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
from weekly_batch import NON_STOCK_PAT, SECTORS  # 섹터 정의·필터 공유 (drift 방지)

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
        if NON_STOCK_PAT.search(nm):   # 원화현금 등 비주식 행 — 구성종목이 아니다
            continue
        try:
            w = float(r.get("비중") or 0)
        except Exception:
            w = 0.0
        rows.append({"티커": str(tk), "종목명": nm.strip(), "비중": round(w, 2)})
    rows.sort(key=lambda x: -x["비중"])
    return rows[:MAX_ITEMS]


def overseas_members(code: str) -> list[dict]:
    """해외 ETF PDF — 종목명만. KRX가 해외 보유분에는 비중을 주지 않고(전부 0.0),
    티커도 내부코드(4626A1 등)라 사용자에게 의미가 없다."""
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
    for _, r in df.iterrows():
        nm = r.get("구성종목명")
        if isinstance(nm, str) and nm.strip() and not NON_STOCK_PAT.search(nm):
            rows.append({"종목명": nm.strip()})
    return rows[:MAX_ITEMS]


def main():
    import os
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        sys.exit("KRX_ID/KRX_PW 환경변수가 필요합니다.")

    print(f"[섹터 유니버스] {date.today().isoformat()} · {len(SECTORS)}개")

    # 직전 산출물 — KRX가 간헐적으로 빈 응답을 준다(재시도 3회로도 못 넘길 때가 있다).
    # 실패한 섹터를 빈 값으로 덮으면 수집 실패가 그대로 데이터 손실이 된다
    # (실측: 536종목 → 421종목). 이전 값을 유지하고 언제 것인지 표시한다.
    prev: dict[str, dict] = {}
    prev_asof = ""
    if OUT.exists():
        try:
            _p = json.loads(OUT.read_text())
            prev_asof = _p.get("asof", "")
            prev = {s["섹터"]: s for s in _p.get("sectors", []) if s.get("종목수")}
        except Exception:
            pass

    out = []
    for cfg in SECTORS:
        name = cfg["name"]
        # 해외 섹터는 roster가 없다 — 가격 소스인 ETF의 PDF를 그대로 명부로 쓴다
        overseas = not cfg.get("roster")
        kind, code = ("etf_pdf", cfg["price"][1]) if overseas else cfg["roster"]
        row = {"섹터": name,
               "군": "해외" if overseas else ("테마" if kind == "etf_pdf" else "KRX섹터"),
               "기준": (f'{cfg["kodex"]} 구성종목(PDF) · 비중 미제공' if overseas
                      else f'{cfg["kodex"]} 구성종목(PDF)' if kind == "etf_pdf"
                      else f"KRX {name} 지수 구성종목")}
        try:
            row["종목"] = (overseas_members(code) if overseas else
                          etf_members(code) if kind == "etf_pdf" else index_members(code))
            row["종목수"] = len(row["종목"])
            print(f"  - {name}: {row['종목수']}종목")
        except Exception as e:
            keep = prev.get(name)
            if keep:
                row["종목"] = keep["종목"]
                row["종목수"] = keep["종목수"]
                row["비고"] = f"수집 실패({type(e).__name__}) — {prev_asof} 수집분 유지"
                print(f"  - {name}: 실패 {type(e).__name__} → 직전 {row['종목수']}종목 유지")
            else:
                row["종목"], row["종목수"] = [], 0
                row["비고"] = f"수집 실패: {type(e).__name__}"
                print(f"  - {name}: 실패 {type(e).__name__} (직전 데이터도 없음)")
        out.append(row)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"asof": date.today().isoformat(), "sectors": out},
                              ensure_ascii=False, indent=2))
    print(f"[완료] {OUT} — {sum(r['종목수'] for r in out)}개 종목")


if __name__ == "__main__":
    main()
