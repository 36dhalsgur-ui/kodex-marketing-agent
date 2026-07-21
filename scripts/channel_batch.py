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
    h = dict(UA, Origin="https://www.aceetf.co.kr", Referer="https://www.aceetf.co.kr/")
    d = requests.get("https://papi.aceetf.co.kr/api/main/keyvisual", headers=h, timeout=15).json()
    items = []
    for b in d.get("data", []):
        title = clean(f"{b.get('bannerTitle', '')} — {b.get('subtitle', '')}".strip(" —"))
        if title:
            items.append({"제목": title, "링크": b.get("pcUrl") or "https://www.aceetf.co.kr"})
    return items[:MAX_BANNERS]


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
            items.append({"제목": txt, "링크": absol(base, a["href"] if a else "")})
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


def main():
    prev: dict[str, list] = {}
    if OUT.exists():
        try:
            for b in json.loads(OUT.read_text()).get("brands", []):
                prev[b["브랜드"]] = b.get("배너", [])
        except Exception:
            pass

    brands = []
    for name, fn in EXTRACTORS:
        row = {"브랜드": name}
        try:
            banners = fn()
            if not banners:
                raise ValueError("배너 0건")
            prev_titles = {b["제목"] for b in prev.get(name, [])}
            for b in banners:
                b["NEW"] = bool(prev_titles) and b["제목"] not in prev_titles
            row["배너"] = banners
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
