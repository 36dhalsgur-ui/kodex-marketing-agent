"""주간 채널 배치 — 운용사 8개사 공식 홈페이지의 메인 배너/캠페인 수집.

실행: 주 1회 (weekly_batch.py와 함께)
  python scripts/channel_batch.py
필요: requests, beautifulsoup4 (로컬 전용 — 앱 requirements에는 불필요)

산출: data/channel_board.json
  {asof, brands: [{브랜드, 배너: [{제목, 링크, NEW}]}]}

NEW 판정: 직전 산출물에 없던 배너 제목이면 True (전주 대비 새로 걸린 캠페인).

사이트별 수집 방식 (2026-07 구조 실측 기준):
- KODEX     kodex.com                          정적 HTML  .kv-kodex 스와이퍼
- TIGER     investments.miraeasset.com(구 페이지)  정적 HTML  .focus-item 스와이퍼
- ACE       papi.aceetf.co.kr/api/main/keyvisual  JSON API (사이트는 Next.js SPA)
- SOL       soletf.com                         정적 HTML  .main-visual
- RISE      riseetf.co.kr                      정적 HTML  .wrap_visual_slide .slide_item
- PLUS      plusetf.co.kr                      정적 HTML  공지 h1/h2 + [신규상장] 링크
- HANARO    hanaroetf.com                      정적 HTML  .visual ul.slide
- TIMEFOLIO timeetf.co.kr (TIME 리브랜딩)        정적 HTML  .swiper-container.info1
구조 변경으로 특정 사이트 파싱이 깨져도 나머지는 정상 수집되며,
해당 브랜드는 직전 산출물의 배너를 유지한다 (비고에 표시).
"""

import datetime as dt
import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "channel_board.json"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko"}
MAX_BANNERS = 5


def clean(txt: str, limit: int = 90) -> str:
    return " ".join(txt.split())[:limit].strip()


def absol(base: str, href: str) -> str:
    if not href or href.startswith("javascript"):
        return base
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


# ── 이벤트 보드 추출기 ────────────────────────────────────────────
# 메인 배너는 '상품 상세'로 가는 홍보물이지만, 이벤트 보드는 기간이 명시된
# 실제 캠페인이다 — 대상 상품·시작일·종료일이 다 있어 DiD의 개입 정의에 그대로 쓴다.

def _period(txt: str) -> tuple[str, str]:
    """'2026.07.14 ~ 2026.08.31' → ('2026-07-14', '2026-08-31')"""
    d = re.findall(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", txt)
    f = [f"{y}-{m}-{dd}" for y, m, dd in d[:2]]
    return (f[0] if f else "", f[1] if len(f) > 1 else "")


def kodex_events():
    """samsungfund.com 이벤트 보드 — kodex.com은 전부 여기로 리다이렉트된다."""
    base = "https://www.samsungfund.com/etf/lounge/"
    soup = get_soup(base + "event.do")
    out = []
    for a in soup.select('a[href*="event-view.do"]'):
        t = a.select_one(".event-tltle")
        if not t:
            continue
        badge = a.select_one(".event-badge")
        per = a.select_one(".event-period")
        st, en = _period(per.get_text(" ", strip=True) if per else "")
        out.append({"제목": clean(t.get_text(" ", strip=True), 90),
                    "링크": absol(base, a["href"]),
                    "상태": clean(badge.get_text(strip=True)) if badge else "",
                    "시작": st, "종료": en})
    return _dedup_events(out)


def tiger_events():
    """TIGER 이벤트 목록은 JS로 그려진다 — 목록을 만드는 ajax를 직접 호출한다.
    (www.tigeretf.com은 1KB짜리 리다이렉트 껍데기라 링크 탐색이 통하지 않는다)"""
    base = "https://investments.miraeasset.com/tigeretf/ko/customer/event/"
    r = requests.post(base + "list.ajax",
                      headers=dict(UA, **{"X-Requested-With": "XMLHttpRequest",
                                          "Referer": base + "list.do"}),
                      timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for li in soup.select("li"):
        t = li.select_one(".title")
        if not t:
            continue
        key = re.search(r"'detailsKey',\s*'(\d+)'", str(li))
        vals = [v.get_text(strip=True) for v in li.select(".c-pair .value")]
        st, en = _period(vals[0] if vals else "")
        badge = li.select_one(".status")
        out.append({"제목": clean(t.get_text(" ", strip=True), 90),
                    "링크": base + f"view.do?detailsKey={key.group(1)}" if key else base + "list.do",
                    "상태": clean(badge.get_text(strip=True)) if badge else "",
                    "시작": st, "종료": en})
    return _dedup_events(out)


def _dedup_events(rows: list[dict]) -> list[dict]:
    """링크 기준 중복 제거 — KODEX 보드는 반응형 레이아웃 때문에 같은 카드를
    데스크톱·모바일용으로 두 번 렌더링한다."""
    seen, out = set(), []
    for e in rows:
        if e["링크"] in seen:
            continue
        seen.add(e["링크"])
        out.append(e)
    return out


EVENT_BOARDS = {"KODEX": kodex_events, "TIGER": tiger_events}


# ── 사이트별 추출기: [{제목, 링크}] 반환 ──────────────────────────


def kodex():
    base = "https://www.kodex.com"
    soup = get_soup(base)
    items, seen = [], set()
    for slide in soup.select("section.kv-kodex .swiper-slide"):
        # 슬라이드 안의 캠페인 제목 = 상품명/카피가 담긴 앞부분 텍스트
        txt = clean(slide.get_text(" ", strip=True), 80)
        a = slide.find("a", href=True)
        if len(txt) > 10 and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a else "")})
    return items[:MAX_BANNERS]


def tiger():
    base = "https://investments.miraeasset.com"
    soup = get_soup(base + "/tigeretf/ko/main/index.do")
    items, seen = [], set()
    for slide in soup.select("div.swiper-slide.focus-item"):
        txt = clean(re.sub(r"\d{4}\.\d{2}\.\d{2}|ETF 영상", "", slide.get_text(" ", strip=True)), 80)
        a = slide.find("a", href=True)
        if len(txt) > 10 and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a else "")})
    return items[:MAX_BANNERS]


def ace():
    """ACE는 API가 실제 노출 우선순위(rank·bannerOrder)와 게재기간을 제공한다.
    다른 사이트는 DOM 순서뿐이라 이런 근거가 없다 — 있는 곳은 반드시 쓴다."""
    h = dict(UA, Origin="https://www.aceetf.co.kr", Referer="https://www.aceetf.co.kr/")
    d = requests.get("https://papi.aceetf.co.kr/api/main/keyvisual", headers=h, timeout=15).json()
    now = dt.datetime.now()
    rows = []
    for b in d.get("data", []):
        if b.get("viewYn") == "N":
            continue
        # 게재기간이 지난/시작 전 배너 제외
        try:
            st_ = b.get("noticeStartDate")
            en_ = b.get("noticeEndDate")
            if st_ and dt.datetime.strptime(st_, "%Y-%m-%d %H:%M:%S") > now:
                continue
            if en_ and dt.datetime.strptime(en_, "%Y-%m-%d %H:%M:%S") < now:
                continue
        except Exception:
            pass
        title = clean(f"{b.get('bannerTitle', '')} — {b.get('subtitle', '')}".strip(" —"))
        if title:
            rows.append((b.get("rank", 99), b.get("bannerOrder", 99), title,
                         b.get("pcUrl") or "https://www.aceetf.co.kr"))
    rows.sort(key=lambda r: (r[0], r[1]))          # 운용사가 매긴 우선순위대로
    return [{"제목": t, "링크": u, "순위근거": f"rank {r}-{o}"} for r, o, t, u in rows[:MAX_BANNERS]]


def sol():
    base = "https://www.soletf.com"
    soup = get_soup(base)
    items, seen = [], set()
    for slide in soup.select(".main-visual [class*=slide], .main-visual a"):
        raw = slide.get_text(" ", strip=True)
        if raw.count("ISA") >= 2:  # 개별 슬라이드가 아니라 컨테이너(전체 묶음) 텍스트
            continue
        txt = clean(re.sub(r"^(?:ISA|개인연금|퇴직연금|\d+%|\s)+", "", raw), 80)
        a = slide if slide.name == "a" and slide.get("href") else slide.find("a", href=True)
        if len(txt) > 10 and txt not in seen:
            seen.add(txt)
            link = absol(base, a["href"] if a else "")
            # SOL은 로케일 프리픽스(/ko)가 있어야 상품 페이지가 열린다.
            # 일부 앵커에 /ko가 빠져 있어 그대로 쓰면 404 (실측 확인)
            link = re.sub(r"^(https://www\.soletf\.com)/fund/", r"\1/ko/fund/", link)
            items.append({"제목": txt, "링크": link})
    return items[:MAX_BANNERS]


def rise():
    base = "https://www.riseetf.co.kr"
    soup = get_soup(base)
    items, seen = [], set()
    for slide in soup.select(".wrap_visual_slide .slide_item"):
        txt = clean(re.sub(r"종목코드\s*:\s*\S+|More", "", slide.get_text(" ", strip=True)), 80)
        a = slide.find("a", href=True) or (slide if slide.name == "a" else None)
        if len(txt) > 10 and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a else "")})
    return items[:MAX_BANNERS]


def plus():
    base = "https://www.plusetf.co.kr"
    soup = get_soup(base)
    items, seen = [], set()
    # 신규상장 캠페인 (insight/tv) 우선, 그다음 메인 공지
    for a in soup.select('a[href*="insight/tv"]'):
        txt = clean(a.get_text(" ", strip=True), 80)
        if "신규" in txt and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"])})
    for tag in soup.select("h1, h2"):
        txt = clean(tag.get_text(" ", strip=True), 80)
        if len(txt) > 10 and "메인 페이지" not in txt and txt not in seen:
            seen.add(txt)
            a = tag.find_parent("a") or tag.find("a", href=True)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a and a.get("href") else "")})
    return items[:MAX_BANNERS]


def hanaro():
    base = "https://www.hanaroetf.com"
    soup = get_soup(base)
    items, seen = [], set()
    for li in soup.select("section.visual ul.slide li, ul.slide li"):
        txt = clean(li.get_text(" ", strip=True), 80)
        a = li.find("a", href=True)
        if len(txt) > 10 and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a else "")})
    return items[:MAX_BANNERS]


def timefolio():
    base = "https://timeetf.co.kr"
    soup = get_soup(base + "/")
    items, seen = [], set()
    for slide in soup.select(".swiper-container.info1 .swiper-slide"):
        txt = clean(re.sub(r"\d{4}\.\d{2}\.\d{2}", "", slide.get_text(" ", strip=True)), 80)
        a = slide.find("a", href=True) or (slide.find_parent("a"))
        if len(txt) > 8 and txt not in seen:
            seen.add(txt)
            items.append({"제목": txt, "링크": absol(base, a["href"] if a and a.get("href") else "")})
    return items[:MAX_BANNERS]


EXTRACTORS = [
    ("KODEX", kodex), ("TIGER", tiger), ("ACE", ace), ("SOL", sol),
    ("RISE", rise), ("PLUS", plus), ("HANARO", hanaro), ("TIMEFOLIO", timefolio),
]

# 공식 홈페이지 메인 — 배너 링크가 자사 도메인 밖(유튜브·블로그 등)이면 홈으로 정규화
# ('홈페이지' 열 클릭은 항상 홈페이지 계열로 가야 한다는 소스 분리 원칙)
HOMES = {
    "KODEX": ("https://www.kodex.com", ["kodex.com", "samsungfund.com"]),
    "TIGER": ("https://www.tigeretf.com", ["tigeretf.com", "miraeasset.com"]),
    "ACE": ("https://www.aceetf.co.kr", ["aceetf.co.kr"]),
    "SOL": ("https://www.soletf.com", ["soletf.com", "soletf.co.kr"]),
    "RISE": ("https://www.riseetf.co.kr", ["riseetf.co.kr"]),
    "PLUS": ("https://www.plusetf.co.kr", ["plusetf.co.kr"]),
    "HANARO": ("https://www.hanaroetf.com", ["hanaroetf.com"]),
    "TIMEFOLIO": ("https://timeetf.co.kr", ["timeetf.co.kr", "timefolio.co.kr"]),
}


_EVENT_PAT = re.compile(r"이벤트|EVENT", re.I)


def find_event_link(home: str) -> dict | None:
    """사이트에 별도 이벤트/프로모션 페이지가 있으면 그 링크를 찾는다.

    메인 배너는 대부분 상품 상세로 연결되므로(상품 홍보가 목적),
    '이벤트'는 별도 메뉴로 운영되는 곳(RISE·TIMEFOLIO 등)만 존재한다."""
    try:
        soup = get_soup(home)
    except Exception:
        return None
    best = None
    for a in soup.find_all("a", href=True):
        txt = " ".join(a.get_text(" ", strip=True).split())
        href = a["href"]
        if not _EVENT_PAT.search(txt + href):
            continue
        # 공지 겸용 메뉴('공지/이벤트')보다 순수 이벤트 메뉴를 우선
        score = (2 if _EVENT_PAT.search(txt) and "공지" not in txt else 1)
        if best is None or score > best[0]:
            best = (score, txt or "이벤트", absol(home, href))
    return {"라벨": best[1], "링크": best[2]} if best else None


def main():
    prev: dict[str, list] = {}
    if OUT.exists():
        try:
            for b in json.loads(OUT.read_text()).get("brands", []):
                prev[b["브랜드"]] = b.get("배너", [])
        except Exception:
            pass

    def slot_share(banners: list[dict]) -> list[dict]:
        """같은 상품이 배너 슬롯을 몇 개 차지하는지 — '미는 강도'의 실측 근거.
        배너 순서(DOM)는 우선순위 근거가 못 되지만, 슬롯 점유 수는 근거가 된다."""
        def key(t: str) -> str:
            m = re.search(r"[A-Z]{3,}\s*[가-힣A-Za-z0-9&\+\.]+", t)
            return (m.group(0) if m else t)[:18]
        cnt: dict = {}
        for b in banners:
            cnt[key(b["제목"])] = cnt.get(key(b["제목"]), 0) + 1
        for b in banners:
            b["슬롯수"] = cnt[key(b["제목"])]
        return banners

    brands = []
    for name, fn in EXTRACTORS:
        home, own_domains = HOMES[name]
        row = {"브랜드": name, "홈": home}
        # 이벤트 보드를 파싱할 수 있는 곳은 개별 이벤트를 기간까지 수집한다.
        # 나머지는 종전대로 '이벤트 메뉴 링크' 한 줄만 찾는다.
        if name in EVENT_BOARDS:
            try:
                evs = EVENT_BOARDS[name]()
                row["이벤트목록"] = evs
                live = [e for e in evs if e.get("상태") == "진행중"]
                print(f"  - {name} 이벤트: 전체 {len(evs)}건 · 진행중 {len(live)}건")
            except Exception as e:
                row["이벤트비고"] = f"이벤트 수집 실패: {type(e).__name__}"
                print(f"  - {name} 이벤트: 실패 {type(e).__name__}")
        ev = find_event_link(home)
        if ev:
            row["이벤트"] = ev
        try:
            banners = fn()
            if not banners:
                raise ValueError("배너 0건")
            prev_titles = {b["제목"] for b in prev.get(name, [])}
            for b in banners:
                b["NEW"] = bool(prev_titles) and b["제목"] not in prev_titles
                if not any(d in b["링크"] for d in own_domains):
                    b["링크"] = home
            row["배너"] = slot_share(banners)
            # 배너 순서의 성격을 명시 — ACE만 운용사가 매긴 실제 우선순위
            row["순서근거"] = "운용사 지정 우선순위" if any("순위근거" in b for b in banners) else "사이트 노출 순서"
            print(f"  - {name}: {len(banners)}건 (신규 {sum(1 for b in banners if b['NEW'])})")
        except Exception as e:
            row["배너"] = prev.get(name, [])
            row["비고"] = f"수집 실패({type(e).__name__}) — 직전 데이터 유지"
            print(f"  - {name}: 실패 {type(e).__name__} → 직전 {len(row['배너'])}건 유지")
        brands.append(row)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"asof": date.today().isoformat(), "brands": brands},
                              ensure_ascii=False, indent=2))
    print(f"[완료] {OUT}")


if __name__ == "__main__":
    main()
