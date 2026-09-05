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


# ── 공지 게시판형 이벤트 ────────────────────────────────────────
# ACE·SOL·PLUS·HANARO는 이벤트 전용 페이지가 없고 공지사항에 섞어 올린다.
# 제목으로 골라내고, 제목 끝의 '(~10/31)' 같은 표기에서 종료일을 읽는다.
# 시작일은 공지 등록일로 대신한다 — 정확한 개시일이 어디에도 없다.
# (경쟁사 이벤트는 화면 표시용이다. DiD의 개입 시점은 KODEX 이벤트 보드만 쓴다.)
EVENT_TITLE = re.compile(r"이벤트|EVENT|경품|매수\s?인증|응모")
# 당첨자 발표·결과 안내는 집행이 아니라 끝난 뒤의 사후 공지다
EVENT_EXCLUDE = re.compile(r"당첨자|당첨\s?발표|결과\s?안내|유의\s?사항")


def _tail_deadline(title: str, posted: str) -> str:
    """'(~10/31)' → '2026-10-31'. 연도는 등록일 기준으로 붙이되 해를 넘기면 +1년."""
    m = re.search(r"~\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\)", title)
    if not m or not posted:
        return ""
    mm, dd = int(m.group(1)), int(m.group(2))
    try:
        y = int(posted[:4])
        if (mm, dd) < (int(posted[5:7]), int(posted[8:10])):
            y += 1                      # 12월 공지의 '(~1/15)'는 다음 해다
        return f"{y}-{mm:02d}-{dd:02d}"
    except ValueError:
        return ""


def _notice_event(title: str, link: str, posted: str) -> dict | None:
    """공지 한 건을 이벤트 형식으로. 이벤트가 아니면 None."""
    if not EVENT_TITLE.search(title) or EVENT_EXCLUDE.search(title):
        return None
    end = _tail_deadline(title, posted)
    state = ""
    if end:
        state = "진행중" if end >= date.today().isoformat() else "종료"
    elif re.search(r"종료|마감", title):
        state = "종료"          # 제목에 이미 박혀 있으면 기간이 없어도 안다
    return {"제목": clean(title, 90), "링크": link,
            "상태": state, "시작": posted, "종료": end}


def ace_events():
    """ACE는 Next.js SPA — 목록을 만드는 API를 직접 부른다."""
    h = dict(UA, Accept="application/json", Origin="https://www.aceetf.co.kr",
             Referer="https://www.aceetf.co.kr/")
    d = requests.get("https://papi.aceetf.co.kr/api/notices",
                     params={"page": 1, "size": 30}, headers=h, timeout=15).json()
    out = []
    for it in d.get("data") or []:
        e = _notice_event(it.get("title", ""),
                          f"https://www.aceetf.co.kr/cs/notice/{it.get('id','')}",
                          (it.get("regDate") or "")[:10])
        if e:
            out.append(e)
    return _dedup_events(out)


def sol_events():
    """SOL도 목록이 JS로 그려진다 — 공지 API를 직접 부른다."""
    out = []
    # 한 페이지가 10건뿐이라 분배금 공지에 밀려 이벤트가 뒤로 간다 — 앞 3페이지를 본다
    for pg in (1, 2, 3):
        # 페이지 파라미터는 nowPage가 아니라 page다(nowPage는 응답 필드일 뿐 무시된다)
        d = requests.get("https://www.soletf.com/api/cs/notice",
                         params={"page": pg},
                         headers=dict(UA, Accept="application/json"), timeout=15).json()
        for it in d.get("items") or []:
            e = _notice_event(it.get("TITLE", ""),
                              f"https://www.soletf.com/ko/cs/notice/{it.get('NO','')}",
                              (it.get("REG_DATE") or "")[:10])
            if e:
                out.append(e)
    return _dedup_events(out)


def plus_events():
    """PLUS는 공지 목록이 정적 HTML로 온다."""
    base = "https://www.plusetf.co.kr"
    soup = get_soup(base + "/customer/notice/list")
    out = []
    for a in soup.select("a[href*='notice/detail']"):
        txt = " ".join(a.get_text(" ", strip=True).split())
        m = re.search(r"(20\d\d[.\-]\d\d[.\-]\d\d)\s*$", txt)
        posted = m.group(1).replace(".", "-") if m else ""
        title = re.sub(r"^\d+\s*", "", txt[:m.start()] if m else txt).strip()
        e = _notice_event(title, absol(base, a["href"]), posted)
        if e:
            out.append(e)
    return _dedup_events(out)


def hanaro_events():
    """HANARO 공지 목록은 ajax로 조각 HTML을 받아 그린다 — 그 조각을 직접 받는다."""
    r = requests.get("https://www.hanaroetf.com/customer/notice-list-ajax",
                     params={"currentPage": 1, "pageListSize": 30, "searchWord": ""},
                     headers=dict(UA, **{"X-Requested-With": "XMLHttpRequest",
                                         "Referer": "https://www.hanaroetf.com/customer/notice"}),
                     timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.select("a[href*='/customer/notice/']"):
        txt = " ".join(a.get_text(" ", strip=True).split())
        m = re.search(r"(20\d\d-\d\d-\d\d)\s*$", txt)
        posted = m.group(1) if m else ""
        title = re.sub(r"^공지\s*", "", txt[:m.start()] if m else txt).strip()
        e = _notice_event(title, absol("https://www.hanaroetf.com", a["href"].split("?")[0]),
                          posted)
        if e:
            out.append(e)
    return _dedup_events(out)


def rise_events():
    """RISE는 이벤트 전용 페이지가 있고 상태·기간이 그대로 적혀 있다."""
    soup = get_soup("https://www.riseetf.co.kr/cust/event")
    out = []
    for li in soup.select("li"):
        txt = " ".join(li.get_text(" ", strip=True).split())
        if "이벤트 기간" not in txt:
            continue
        st, en = _period(txt)
        a = li.find("a", href=True)
        state = "진행중" if txt.startswith("진행중") else ("종료" if txt.startswith("종료") else "")
        title = re.sub(r"^(진행중|종료)\s*", "", txt).split("이벤트 기간")[0].strip()
        out.append({"제목": clean(title, 90),
                    "링크": a["href"] if a else "https://www.riseetf.co.kr/cust/event",
                    "상태": state, "시작": st, "종료": en})
    return _dedup_events(out)


def timefolio_events():
    """TIME ETF 이벤트 페이지 — '이벤트기간 2026.07.06~2026.07.31' 형태."""
    soup = get_soup("https://timeetf.co.kr/board/board.php?bbsid=event")
    txt = " ".join(soup.get_text(" ", strip=True).split())
    out = []
    for m in re.finditer(r"(\[EVENT\][^\[]{5,80}?)\s*이벤트기간\s*"
                         r"(20\d\d\.\d\d\.\d\d)\s*~\s*(20\d\d\.\d\d\.\d\d)", txt):
        en = m.group(3).replace(".", "-")
        out.append({"제목": clean(m.group(1), 90),
                    "링크": "https://timeetf.co.kr/board/board.php?bbsid=event",
                    "상태": "진행중" if en >= date.today().isoformat() else "종료",
                    "시작": m.group(2).replace(".", "-"), "종료": en})
    return _dedup_events(out)


EVENT_BOARDS = {"KODEX": kodex_events, "TIGER": tiger_events,
                "ACE": ace_events, "SOL": sol_events, "PLUS": plus_events,
                "HANARO": hanaro_events, "RISE": rise_events,
                "TIMEFOLIO": timefolio_events}


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
    """TIGER 메인 영역 — .only-main 안의 .c-section 블록들 (data-component=MainHero 등).

    스와이퍼가 아니라 섹션이 세로로 쌓이는 구조라 'swiper-slide'를 찾으면 안 된다.
    기존 파서는 페이지 1,700px 아래 '투자 포커스'(ETF 영상) 캐러셀을 잡고 있었다.
    각 카드는 .category(라벨) + .title(헤드라인)로 나뉘어 있어 그대로 쓴다."""
    base = "https://investments.miraeasset.com"
    soup = get_soup(base + "/tigeretf/ko/main/index.do")
    main = soup.select_one(".only-main")
    items, seen = [], set()
    for card in (main.select(".c-section.active .c-card") if main else []):
        title_el = card.select_one(".title")
        if not title_el:
            continue
        title = clean(title_el.get_text(" ", strip=True), 70)
        cat_el = card.select_one(".category .val")
        cat = clean(cat_el.get_text(" ", strip=True), 16) if cat_el else ""
        a = card.find("a", href=True)
        if len(title) < 4 or title in seen:
            continue
        seen.add(title)
        items.append({"제목": (f"[{cat}] {title}" if cat else title),
                      "링크": absol(base, a["href"] if a else ""),
                      "노출": "메인 배너"})
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


def link_kind(url: str, home: str, own_domains: list[str]) -> str:
    """배너가 실제로 어디로 가는지 분류.

    예전에는 자사 도메인 밖 링크를 홈으로 덮어썼는데, 그러면 브랜드마다 목적지가
    제각각인 것(TIGER는 전부 유튜브, TIMEFOLIO는 전부 블로그)이 '어떤 건 홈,
    어떤 건 상품'이라는 이유 모를 불일치로 보인다. 링크는 그대로 두고 유형을
    표기해, 누르기 전에 어디로 갈지 알 수 있게 한다."""
    if not url or url.rstrip("/") == home.rstrip("/"):
        return "홈"
    if re.search(r"youtube\.com|youtu\.be", url):
        return "영상"
    if "blog.naver.com" in url:
        return "블로그"
    if re.search(r"news\.naver\.com|/news/", url):
        return "뉴스"
    if any(d in url for d in own_domains):
        # 자사 도메인 안에서도 목적지 성격이 다르다 — PLUS는 자사 TV(영상 콘텐츠),
        # RISE는 공지·PDF 자료로 연결된다. '홈페이지'로 뭉뚱그리면 또 제각각으로 보인다.
        if re.search(r"/(insight/)?tv/|/movie|/video", url, re.I):
            return "영상"
        if re.search(r"notice|공지", url, re.I):
            return "공지"
        if re.search(r"\.pdf|/pdf/", url, re.I):
            return "자료"
        if re.search(r"/(product|fund|prod|etf)", url, re.I):
            return "상품"
        return "홈페이지"
    return "외부"


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
                b["링크유형"] = link_kind(b["링크"], home, own_domains)
                # 노출 위치 — 파서가 지정하지 않았으면 메인 배너 캐러셀이다
                b.setdefault("노출", "메인 배너")
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
