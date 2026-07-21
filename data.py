"""데모 데이터 생성 및 실시간 지수 수집 모듈.

실제 운영 시 KRX / 구글뉴스 / 유튜브 API 연동부로 교체하는 것을 전제로,
동일한 스키마의 데모 데이터를 제공한다.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

RNG = np.random.default_rng(42)

# ──────────────────────────────────────────────
# ETF 유니버스 (종목명, 테마, 운용사)
# ──────────────────────────────────────────────
ETF_UNIVERSE = [
    ("KODEX 미국반도체", "반도체", "KODEX"),
    ("TIGER 미국반도체나스닥", "반도체", "TIGER"),
    ("KODEX AI전력핵심설비", "AI·전력", "KODEX"),
    ("TIGER AI코리아그로스액티브", "AI·전력", "TIGER"),
    ("KODEX 2차전지산업", "2차전지", "KODEX"),
    ("TIGER 2차전지테마", "2차전지", "TIGER"),
    ("KODEX K-방산", "방산", "KODEX"),
    ("PLUS K방산", "방산", "PLUS"),
    ("KODEX 미국나스닥100", "미국빅테크", "KODEX"),
    ("TIGER 미국나스닥100", "미국빅테크", "TIGER"),
    ("ACE 미국빅테크TOP7", "미국빅테크", "ACE"),
    ("KODEX 200", "국내대표지수", "KODEX"),
    ("RISE 200", "국내대표지수", "RISE"),
    ("KODEX 골드선물(H)", "금·원자재", "KODEX"),
    ("ACE KRX금현물", "금·원자재", "ACE"),
    ("KODEX 미국30년국채액티브", "채권·금리", "KODEX"),
    ("TIGER 미국30년국채", "채권·금리", "TIGER"),
    ("KODEX 바이오", "바이오", "KODEX"),
    ("TIGER 바이오TOP10", "바이오", "TIGER"),
    ("KODEX 고배당", "배당", "KODEX"),
    ("RISE 고배당", "배당", "RISE"),
    ("KODEX 은행", "금융", "KODEX"),
    ("TIGER 은행고배당플러스", "금융", "TIGER"),
    ("KODEX 원자력", "원자력", "KODEX"),
    ("HANARO 원자력iSelect", "원자력", "HANARO"),
    ("KODEX CD금리액티브", "단기자금", "KODEX"),
    ("TIGER CD금리투자KIS", "단기자금", "TIGER"),
    ("KODEX 미국S&P500", "미국빅테크", "KODEX"),
    ("ACE 미국S&P500", "미국빅테크", "ACE"),
    ("RISE 미국AI밸류체인", "AI·전력", "RISE"),
    ("SOL 미국배당다우존스", "배당", "SOL"),
    ("SOL 조선TOP3플러스", "조선", "SOL"),
    ("SOL 미국AI소프트웨어", "AI·전력", "SOL"),
    ("KODEX K-친환경조선해운액티브", "조선", "KODEX"),
    ("HANARO Fn K-반도체", "반도체", "HANARO"),
    ("HANARO 200", "국내대표지수", "HANARO"),
    ("PLUS 고배당주", "배당", "PLUS"),
    ("PLUS 태양광&ESS", "AI·전력", "PLUS"),
    ("RISE 방위산업", "방산", "RISE"),
    ("TIMEFOLIO 글로벌AI인공지능액티브", "AI·전력", "TIMEFOLIO"),
    ("TIMEFOLIO K바이오액티브", "바이오", "TIMEFOLIO"),
    ("TIMEFOLIO 미국나스닥100액티브", "미국빅테크", "TIMEFOLIO"),
]

# 모니터링 대상 8개 ETF 브랜드
ISSUERS = ["KODEX", "TIGER", "ACE", "SOL", "HANARO", "RISE", "PLUS", "TIMEFOLIO"]

THEMES = sorted({t for _, t, _ in ETF_UNIVERSE})


def week_labels(n: int = 8) -> list[str]:
    """최근 n주의 주차 라벨 (예: '6월 4주')."""
    today = dt.date.today()
    labels = []
    for i in range(n - 1, -1, -1):
        d = today - dt.timedelta(weeks=i)
        week_no = (d.day - 1) // 7 + 1
        labels.append(f"{d.month}월 {week_no}주")
    return labels


def demo_netbuy_data(n_weeks: int = 8) -> pd.DataFrame:
    """주차별 순매수액·순자산 데모 데이터 (단위: 억원)."""
    weeks = week_labels(n_weeks)
    rows = []
    for name, theme, issuer in ETF_UNIVERSE:
        base_aum = float(RNG.uniform(2_000, 60_000))
        # 테마별로 수급 사이클을 달리해 자연스러운 패턴 생성
        cycle = RNG.uniform(0, np.pi)
        for w_idx, week in enumerate(weeks):
            trend = np.sin(cycle + w_idx * 0.9) * 0.8 + RNG.normal(0, 0.6)
            netbuy = base_aum * trend * 0.01  # 순자산의 ±1~2% 수준
            rows.append(
                {
                    "주차": week,
                    "종목명": name,
                    "테마": theme,
                    "운용사": issuer,
                    "순매수액": round(netbuy, 1),
                    "순자산": round(base_aum, 1),
                }
            )
            base_aum = max(base_aum + netbuy + base_aum * RNG.normal(0.001, 0.004), 500)
    return pd.DataFrame(rows)


def add_intensity(df: pd.DataFrame) -> pd.DataFrame:
    """매수강도 = (주간 순매수액 / 전주 순자산) × 100."""
    df = df.copy()
    df["전주순자산"] = df.groupby("종목명")["순자산"].shift(1)
    df["매수강도"] = (df["순매수액"] / df["전주순자산"] * 100).round(2)
    return df


def demo_theme_returns(n_weeks: int = 8) -> pd.DataFrame:
    """테마별 주간 수익률(%) 데모 데이터."""
    weeks = week_labels(n_weeks)
    rows = []
    for theme in THEMES:
        cycle = RNG.uniform(0, np.pi)
        momentum = RNG.normal(0, 1.2)
        for w_idx, week in enumerate(weeks):
            ret = momentum + np.sin(cycle + w_idx * 0.7) * 2.2 + RNG.normal(0, 1.0)
            rows.append({"주차": week, "테마": theme, "수익률": round(ret, 2)})
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 뉴스 키워드 / 운용사 동향 / AI 인사이트 (데모)
# ──────────────────────────────────────────────
def news_url(query: str) -> str:
    """구글 뉴스 검색 링크 (수집원과 동일 소스). 실운영 시 기사 원문 URL로 대체."""
    return f"https://news.google.com/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR%3Ako"


# 테마 키워드 축 — 검색량(데이터랩)과 뉴스 언급량을 같은 키로 결합한다
NEWS_KEYWORDS = [
    {"키워드": "AI반도체", "언급량": 128, "증감": 41, "방향": "라이징"},
    {"키워드": "금리 인하", "언급량": 96, "증감": 18, "방향": "라이징"},
    {"키워드": "K-방산", "언급량": 87, "증감": 25, "방향": "라이징"},
    {"키워드": "월배당", "언급량": 74, "증감": 6, "방향": "유지"},
    {"키워드": "조선", "언급량": 44, "증감": 19, "방향": "라이징"},
    {"키워드": "2차전지", "언급량": 52, "증감": -21, "방향": "하락"},
    {"키워드": "금 투자", "언급량": 48, "증감": 15, "방향": "라이징"},
    {"키워드": "커버드콜", "언급량": 41, "증감": -4, "방향": "유지"},
]
for _kw in NEWS_KEYWORDS:
    _kw["url"] = news_url(_kw["키워드"] + " ETF")

# 운용사별 뉴스 (제목, 검색 질의) — url은 아래에서 일괄 생성
_ISSUER_NEWS_RAW = {
    "KODEX": [
        ("AI전력핵심설비 ETF 순자산 5,000억 돌파 — 데이터센터 전력주 수요 지속", "KODEX AI전력핵심설비"),
        ("'강남역 8번출구' 시즌2 공개, 초보 투자자 대상 콘텐츠 마케팅 강화", "KODEX 강남역 8번출구"),
    ],
    "TIGER": [
        ("미국배당다우존스 월배당 시리즈 라인업 확대 발표", "TIGER 미국배당다우존스"),
        ("타깃데이트펀드(TDF) 액티브 ETF 신규 상장 예고", "TIGER TDF 액티브 ETF"),
    ],
    "ACE": [
        ("KRX금현물 ETF 순자산 3조 돌파, 금 투자 열풍 수혜", "ACE KRX금현물"),
        ("'ACE RUN' 러닝 커뮤니티 이벤트로 2030 접점 확대", "ACE RUN 한국투자신탁운용"),
    ],
    "SOL": [
        ("조선TOP3플러스 순자산 1조 돌파 — K-조선 슈퍼사이클 수혜 지속", "SOL 조선TOP3플러스"),
        ("미국배당다우존스 월배당 시리즈로 연금 투자자 공략 강화", "SOL 미국배당다우존스"),
    ],
    "HANARO": [
        ("원자력iSelect, SMR 모멘텀에 기관 자금 유입 지속", "HANARO 원자력 ETF"),
        ("퇴직연금 채널 연계 마케팅으로 라인업 확장 추진", "HANARO ETF 퇴직연금"),
    ],
    "RISE": [
        ("리브랜딩 1주년 — 미국AI밸류체인 중심 해외 테마 강화", "RISE 미국AI밸류체인"),
        ("고배당 라인업 보수 인하로 연금계좌 수요 공략", "RISE 고배당 ETF"),
    ],
    "PLUS": [
        ("K방산 ETF, 방산 수출 모멘텀에 순자산 최고치 경신", "PLUS K방산"),
        ("리브랜딩 이후 시그니처 테마 선점 전략 지속", "PLUS ETF 한화자산운용"),
    ],
    "TIMEFOLIO": [
        ("액티브 ETF 수익률 상위권 석권 — 운용 역량 부각", "TIMEFOLIO 액티브 ETF"),
        ("K바이오액티브에 기관 자금 유입 확대", "TIMEFOLIO K바이오액티브"),
    ],
}

ISSUER_NEWS = {
    issuer: [{"title": t, "url": news_url(q)} for t, q in items]
    for issuer, items in _ISSUER_NEWS_RAW.items()
}

AI_INSIGHTS = [
    {
        "icon": "📈",
        "title": "AI·전력 테마 푸시 강화",
        "body": "AI 전력 인프라 키워드 언급량이 주간 +41% 급증했고 테마 수익률·순매수가 동반 상승. "
        "KODEX AI전력핵심설비를 차주 대표 푸시 상품으로 제안.",
    },
    {
        "icon": "🎯",
        "title": "방산 테마 선점 콘텐츠",
        "body": "K-방산 수출 뉴스 모멘텀 대비 KODEX K-방산의 순매수강도가 경쟁 ETF보다 낮음. "
        "테마 선명성 확보를 위한 집중 콘텐츠 제작 필요.",
    },
    {
        "icon": "⚖️",
        "title": "2차전지 마케팅 축소 검토",
        "body": "2차전지 키워드 언급량 -21%, 테마 수익률 하락 전환. DiD 분석에서도 최근 캠페인 "
        "순효과가 미미해 예산 재배분을 권고.",
    },
]

# 지수·환율 수집 대상 (라벨, 종류, 코드) — 국내 2 + 해외 4 + 환율 1
INDEX_SOURCES = [
    ("코스피", "domestic", "KOSPI"),
    ("코스닥", "domestic", "KOSDAQ"),
    ("S&P 500", "world", ".INX"),
    ("나스닥", "world", ".IXIC"),
    ("닛케이 225", "world", ".N225"),
    ("가권", "world", ".TWII"),
    ("USD/KRW", "fx", "FX_USDKRW"),
]

# 실시간 조회 실패 시 사용할 지수 폴백 값
INDEX_FALLBACK = [
    {"name": "코스피", "value": "3,183.23", "change": "+0.42%", "up": True},
    {"name": "코스닥", "value": "812.44", "change": "-0.31%", "up": False},
    {"name": "S&P 500", "value": "7,526.62", "change": "+0.58%", "up": True},
    {"name": "나스닥", "value": "24,881.15", "change": "+0.72%", "up": True},
    {"name": "닛케이 225", "value": "42,310.50", "change": "-0.18%", "up": False},
    {"name": "가권", "value": "28,455.30", "change": "+0.35%", "up": True},
    {"name": "USD/KRW", "value": "1,368.50", "change": "+0.12%", "up": True},
]


def _fetch_one_index(label: str, kind: str, code: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    if kind == "domestic":
        d = requests.get(
            f"https://m.stock.naver.com/api/index/{code}/basic", headers=headers, timeout=3
        ).json()
        price, rate = d["closePrice"], float(d["fluctuationsRatio"])
    elif kind == "world":
        d = requests.get(
            f"https://api.stock.naver.com/index/{code}/basic", headers=headers, timeout=3
        ).json()
        price, rate = d["closePrice"], float(d["fluctuationsRatio"])
    else:  # fx
        d = requests.get(
            "https://m.stock.naver.com/front-api/marketIndex/prices"
            f"?category=exchange&reutersCode={code}&page=1",
            headers=headers,
            timeout=3,
        ).json()
        item = d["result"][0]
        price, rate = item["closePrice"], float(item["fluctuationsRatio"])
    return {"name": label, "value": price, "change": f"{rate:+.2f}%", "up": rate >= 0}


def fetch_live_indices() -> list[dict]:
    """네이버 증권에서 국내·해외 지수와 달러 환율을 병렬 조회. 실패 항목은 폴백 값."""
    fallback = {f["name"]: f for f in INDEX_FALLBACK}
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(INDEX_SOURCES)) as ex:
        futures = {ex.submit(_fetch_one_index, *src): src[0] for src in INDEX_SOURCES}
        for fut, label in futures.items():
            try:
                results[label] = fut.result()
            except Exception:
                results[label] = fallback[label]
    return [results[label] for label, _, _ in INDEX_SOURCES]


# ══════════════════════════════════════════════
# 유튜브 채널 모니터링 — RSS 기반 (API 키 불필요)
# API 키(YOUTUBE_API_KEY)가 있으면 좋아요·댓글 수까지 확장 가능
# ══════════════════════════════════════════════
YOUTUBE_CHANNELS = {
    "KODEX": "UCQSlMWKs6L5lf5pz5FTbgKQ",       # 삼성자산운용
    "TIGER": "UCNcMZz0cIba-4xBLZcoWrBA",
    "ACE": "UCnuyNitL5SIfBJvTJcdDNLQ",
    "SOL": "UCZ_aq57IPiAdmNYlxGZ8Pfg",
    "HANARO": "UCnK3ANYTFZnF8pkEh3_cOgg",
    "RISE": "UCZ_xAP42i9KMUKZbomB6JSQ",
    "PLUS": "UChurqZc7g4AB4XPxWnjzDNA",
    "TIMEFOLIO": "UC9HqkQ6PeK9bNbf_urnn2yA",
}

_YT_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def _fetch_channel_videos(brand: str, channel_id: str, n: int = 3) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
    root = ET.fromstring(r.content)
    videos = []
    for entry in root.findall("a:entry", _YT_NS)[:n]:
        vid = entry.find("yt:videoId", _YT_NS).text
        title = entry.find("a:title", _YT_NS).text
        published = entry.find("a:published", _YT_NS).text[:10]
        stats = entry.find("media:group/media:community/media:statistics", _YT_NS)
        views = int(stats.get("views")) if stats is not None else 0
        videos.append(
            {
                "brand": brand,
                "videoId": vid,
                "title": title,
                "published": published,
                "views": views,
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return videos


def fetch_youtube(n_per_channel: int = 3) -> dict[str, list[dict]]:
    """8개 브랜드 유튜브 채널의 최신 영상을 병렬 수집. 실패 채널은 빈 리스트."""
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(_fetch_channel_videos, b, cid, n_per_channel): b
            for b, cid in YOUTUBE_CHANNELS.items()
        }
        for fut, brand in futures.items():
            try:
                out[brand] = fut.result()
            except Exception:
                out[brand] = []
    return out


# ══════════════════════════════════════════════
# 공식 블로그 (네이버 블로그 RSS + KODEX 워드프레스 RSS) — 키 불필요
# ID 출처: 각 사 공식 홈페이지 푸터 (2026-07 실측)
# ══════════════════════════════════════════════
BRAND_BLOGS = {
    "KODEX": "https://samsungfundblog.com/feed",          # 자체 블로그 (워드프레스)
    "TIGER": "https://blog.rss.naver.com/m_invest.xml",
    "ACE": "https://blog.rss.naver.com/aceetf.xml",
    "SOL": "https://blog.rss.naver.com/soletf.xml",
    "RISE": "https://blog.rss.naver.com/riseetf.xml",
    "PLUS": "https://blog.rss.naver.com/hanwhaasset.xml",
    "HANARO": "https://blog.rss.naver.com/hanaro_etf.xml",
    "TIMEFOLIO": "https://blog.rss.naver.com/timefolioetf.xml",
}

_RSS_MONTH = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _rss_date(pub: str) -> str:
    """'Tue, 14 Jul 2026 06:50:03 +0000' → '2026-07-14'. 실패 시 빈 문자열."""
    try:
        parts = pub.strip().split()
        d, mon, y = int(parts[1]), _RSS_MONTH[parts[2]], int(parts[3])
        return f"{y:04d}-{mon:02d}-{d:02d}"
    except Exception:
        return ""


def _fetch_blog(brand: str, url: str, n: int = 6) -> list[dict]:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    root = ET.fromstring(r.content)
    posts = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date_s = _rss_date(item.findtext("pubDate") or "")
        if title:
            posts.append({"brand": brand, "title": title, "link": link, "date": date_s})
        if len(posts) >= n:
            break
    return posts


def fetch_blogs(n_per_blog: int = 6) -> dict[str, list[dict]]:
    """8개 브랜드 공식 블로그 최신 글을 병렬 수집. 실패 브랜드는 빈 리스트."""
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_blog, b, u, n_per_blog): b for b, u in BRAND_BLOGS.items()}
        for fut, brand in futures.items():
            try:
                out[brand] = fut.result()
            except Exception:
                out[brand] = []
    return out


# ══════════════════════════════════════════════
# 네이버 데이터랩 검색 트렌드
# NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 설정 시 실데이터, 미설정 시 데모
# ══════════════════════════════════════════════
DATALAB_GROUPS = ["KODEX", "TIGER", "ACE", "RISE"]  # 일반 키워드 "ETF"는 상대지수 최대값을 독점해 브랜드 비교를 뭉개므로 제외


def _demo_datalab(n_weeks: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    today = dt.date.today()
    rows = []
    base = {"KODEX": 62, "TIGER": 55, "ACE": 30, "RISE": 24}
    for g in DATALAB_GROUPS:
        level = base[g]
        for i in range(n_weeks - 1, -1, -1):
            d = today - dt.timedelta(weeks=i)
            level = max(5, level + rng.normal(0.5, 4))
            rows.append({"date": d.isoformat(), "group": g, "ratio": round(level, 1)})
    return pd.DataFrame(rows)


def fetch_datalab(client_id: str | None = None, client_secret: str | None = None) -> tuple[pd.DataFrame, bool]:
    """네이버 데이터랩 주간 검색량. 반환: (데이터, 실데이터 여부)."""
    cid = client_id or os.environ.get("NAVER_CLIENT_ID")
    csec = client_secret or os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and csec):
        return _demo_datalab(), False
    try:
        today = dt.date.today()
        end = today - dt.timedelta(days=today.weekday() + 1)  # 지난 일요일 — 미완결 주가 0 근처로 꺾여 보이는 왜곡 방지
        start = end - dt.timedelta(weeks=12)
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "timeUnit": "week",
            "keywordGroups": [{"groupName": g, "keywords": [g, f"{g} ETF"]} for g in DATALAB_GROUPS],
        }
        r = requests.post(
            "https://openapi.naver.com/v1/datalab/search",
            json=body,
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
            timeout=6,
        )
        r.raise_for_status()
        rows = []
        for res in r.json()["results"]:
            for pt in res["data"]:
                rows.append({"date": pt["period"], "group": res["title"], "ratio": pt["ratio"]})
        return pd.DataFrame(rows), True
    except Exception:
        return _demo_datalab(), False


# ══════════════════════════════════════════════
# DiD 재설계 — KODEX 처치군 고정 · 경쟁 ETF 평균 대조군
# 베이스라인 8주 평균 + 라플라스 스무딩 + Z-score → Sigmoid 0~100점
# ══════════════════════════════════════════════
LAPLACE_ALPHA = 10.0   # 억원 — 소형 ETF 변화율 폭발 방지
BASELINE_WEEKS = 8
ZSCORE_WINDOW = 15     # 권장 15주 (데이터 부족 시 가용 주차 사용)


def kodex_etfs() -> list[str]:
    return sorted(n for n, _, issuer in ETF_UNIVERSE if issuer == "KODEX")


def control_group(treat_name: str) -> list[str]:
    """처치군과 동일 테마의 비(非)KODEX 경쟁 ETF 자동 매핑."""
    theme = next((t for n, t, _ in ETF_UNIVERSE if n == treat_name), None)
    return sorted(
        n for n, t, issuer in ETF_UNIVERSE if t == theme and issuer != "KODEX"
    )


def _smoothed_intensity(df: pd.DataFrame) -> pd.DataFrame:
    """매수강도(스무딩) = 순매수액 / (전주 순자산 + α) × 100."""
    d = df.copy()
    d["전주순자산"] = d.groupby("종목명")["순자산"].shift(1)
    d["강도"] = d["순매수액"] / (d["전주순자산"] + LAPLACE_ALPHA) * 100
    return d


def did_series(df: pd.DataFrame, treat: str, controls: list[str]) -> pd.DataFrame:
    """주차별 DiD 시계열: Δ처치(8주 베이스라인 대비) − Δ대조군 평균."""
    d = _smoothed_intensity(df)
    weeks = list(dict.fromkeys(d["주차"]))

    def intensity_of(name: str) -> pd.Series:
        s = d[d["종목명"] == name].set_index("주차")["강도"]
        return s.reindex(weeks)

    treat_s = intensity_of(treat)
    ctrl_df = pd.DataFrame({c: intensity_of(c) for c in controls}) if controls else pd.DataFrame(index=weeks)

    rows = []
    for i, wk in enumerate(weeks):
        if i < 1:
            continue
        lo = max(0, i - BASELINE_WEEKS)
        base_t = treat_s.iloc[lo:i].mean()
        delta_t = treat_s.iloc[i] - base_t
        if len(controls):
            deltas_c = [
                ctrl_df[c].iloc[i] - ctrl_df[c].iloc[lo:i].mean() for c in controls
            ]
            valid = [v for v in deltas_c if pd.notna(v)]
            delta_c = float(np.mean(valid)) if valid else np.nan
        else:
            delta_c = np.nan
        did = delta_t - delta_c if not math.isnan(delta_c) else np.nan
        rows.append(
            {"주차": wk, "처치강도": treat_s.iloc[i], "Δ처치": delta_t, "Δ대조군": delta_c, "DiD": did}
        )
    return pd.DataFrame(rows)


def did_score(series: pd.DataFrame, week: str) -> dict:
    """해당 주차 DiD를 Z-score 표준화 후 Sigmoid로 0~100점 변환."""
    row = series[series["주차"] == week]
    if row.empty:
        return {"available": False}
    r = row.iloc[0]
    hist = series[series["주차"] != week]["DiD"].dropna().tail(ZSCORE_WINDOW)
    result = {
        "available": True,
        "delta_treat": float(r["Δ처치"]) if pd.notna(r["Δ처치"]) else None,
        "delta_ctrl": float(r["Δ대조군"]) if pd.notna(r["Δ대조군"]) else None,
        "did": float(r["DiD"]) if pd.notna(r["DiD"]) else None,
        "score": None,
        "z": None,
        "fallback": None,
    }
    if result["did"] is None:
        result["fallback"] = "대조군 없음 — Δ처치(시장효과 미제거)만 제공"
        return result
    if len(hist) >= 4 and hist.std() > 1e-9:
        z = (result["did"] - hist.mean()) / hist.std()
        result["z"] = round(float(z), 2)
        result["score"] = round(100 / (1 + math.exp(-z)), 1)
    else:
        result["fallback"] = f"이력 {len(hist)}주 — Z-score 산출에 부족(최소 4주), DiD 원값만 제공"
    return result


# ══════════════════════════════════════════════
# 데이터 기반 인사이트 엔진 (규칙 기반 — LLM 연동 시 교체 지점)
# 특정 전략 프레임 없이 수집 데이터의 신호만으로 도출
# ══════════════════════════════════════════════
def build_insights(theme_tbl: pd.DataFrame, keywords: list[dict],
                   did_board: pd.DataFrame, youtube: dict) -> dict:
    """수집 데이터를 종합해 요약·시그널·채널평가·액션을 생성."""
    tt = theme_tbl.copy()
    tt["점수"] = tt["수익률"] + tt["모멘텀"]
    rising = tt.sort_values("점수", ascending=False)
    falling = tt.sort_values("점수")
    top_theme, low_theme = rising.iloc[0], falling.iloc[0]

    kw_rise = [k for k in keywords if k["증감"] > 10]
    kw_fall = [k for k in keywords if k["증감"] < -10]

    # 유튜브 채널 활동 요약
    yt_stats = []
    for b, vids in youtube.items():
        if vids:
            yt_stats.append({"brand": b, "n": len(vids), "views": sum(v["views"] for v in vids),
                             "top": max(vids, key=lambda v: v["views"])})
    yt_stats.sort(key=lambda x: -x["views"])

    best = did_board.dropna(subset=["score"]).sort_values("score", ascending=False) if len(did_board) else did_board
    top_did = best.iloc[0] if len(best) else None
    low_did = best.iloc[-1] if len(best) > 1 else None

    summary = [
        f"{top_theme['테마']} 테마가 금주 {top_theme['수익률']:+.1f}% (전주 대비 {top_theme['모멘텀']:+.1f}%p 가속)로 시장을 주도",
        (f"KODEX 마케팅 효과 최고점은 {top_did['종목명']} — DiD {top_did['score']:.0f}점"
         if top_did is not None else "금주 DiD 점수 산출 대상 없음 (데이터 확인 필요)"),
        (f"뉴스 키워드 중 '{kw_rise[0]['키워드']}' 언급 {kw_rise[0]['증감']:+d}% 급증"
         if kw_rise else "급등 키워드 없음 — 시장 관심 정체 구간"),
    ]

    signals = [
        {"type": "라이징", "text": f"{r.테마}: 금주 {r.수익률:+.1f}% (전주 대비 {r.모멘텀:+.1f}%p) · 순매수 {r.순매수합:+,.0f}억"}
        for r in rising.head(3).itertuples()
    ] + [
        {"type": "하락", "text": f"{low_theme['테마']}: 금주 {low_theme['수익률']:+.1f}% (전주 대비 {low_theme['모멘텀']:+.1f}%p) — 노출 축소 검토"}
    ]

    channel_eval = [
        f"유튜브 최다 조회 채널: {yt_stats[0]['brand']} (최근 영상 {yt_stats[0]['n']}개 합산 {yt_stats[0]['views']:,}회)" if yt_stats else "유튜브 수집 실패 — 네트워크 확인",
        (f"조회수 1위 영상: [{yt_stats[0]['top']['brand']}] {yt_stats[0]['top']['title'][:40]} ({yt_stats[0]['top']['views']:,}회)"
         if yt_stats else ""),
        f"뉴스 키워드 라이징 {len(kw_rise)}건 / 하락 {len(kw_fall)}건",
    ]

    actions = []
    # 1) 라이징 테마 × KODEX 보유 → 푸시
    kodex_in_top = [n for n, t, iss in ETF_UNIVERSE if iss == "KODEX" and t == top_theme["테마"]]
    if kodex_in_top:
        actions.append({
            "priority": "HIGH", "title": f"{top_theme['테마']} 테마 푸시 — {kodex_in_top[0]}",
            "why": f"테마 수익률 금주 {top_theme['수익률']:+.1f}%, 전주 대비 {top_theme['모멘텀']:+.1f}%p 가속, 순매수 유입 확인",
            "how": "차주 콘텐츠·배너 1순위 배정, 유튜브 신규 영상 소재로 활용",
        })
    # 2) DiD 고득점 → 캠페인 강화
    if top_did is not None and top_did["score"] and top_did["score"] >= 60:
        actions.append({
            "priority": "HIGH", "title": f"{top_did['종목명']} 캠페인 연장·확대",
            "why": f"DiD {top_did['score']:.0f}점 — 시장효과 제거 후에도 순매수 순증 확인",
            "how": "동일 소재로 집행 기간 연장, 유사 테마 ETF로 소재 확장 테스트",
        })
    # 3) DiD 저득점 → 재배분
    if low_did is not None and low_did["score"] is not None and low_did["score"] < 40:
        actions.append({
            "priority": "MID", "title": f"{low_did['종목명']} 마케팅 예산 재배분",
            "why": f"DiD {low_did['score']:.0f}점 — 마케팅 대비 순매수 반응 미약",
            "how": "소재·타깃 교체 후 2주 재측정, 무반응 지속 시 라이징 테마로 예산 이동",
        })
    # 4) 라이징 키워드 콘텐츠
    if kw_rise:
        actions.append({
            "priority": "MID", "title": f"'{kw_rise[0]['키워드']}' 키워드 콘텐츠 선점",
            "why": f"언급량 {kw_rise[0]['증감']:+d}% 급증 — 검색 유입 선점 기회",
            "how": "숏폼 1건 + 블로그 해설 1건 발행, 데이터랩 검색량 반응 추적",
        })
    # 5) 경쟁사 활동 대응
    if yt_stats and yt_stats[0]["brand"] != "KODEX":
        actions.append({
            "priority": "LOW", "title": f"{yt_stats[0]['brand']} 콘텐츠 벤치마킹",
            "why": f"경쟁 채널이 조회수 우위 ({yt_stats[0]['views']:,}회) — 소재·포맷 분석 필요",
            "how": "상위 영상 포맷 분석 후 KODEX 채널 A/B 테스트",
        })

    return {"summary": summary, "signals": signals, "channel_eval": [c for c in channel_eval if c], "actions": actions[:5]}


# ══════════════════════════════════════════════
# 금주 시장 요약 — 주간 등락률 (실시간 호가 스트립 대체)
# 주간 의사결정 도구에 맞춰 최근 5거래일 등락률을 제공한다.
# ══════════════════════════════════════════════
WEEKLY_SOURCES = [
    ("코스피", "domestic", "KOSPI"),
    ("코스닥", "domestic", "KOSDAQ"),
    ("S&P 500", "world", ".INX"),
    ("나스닥", "world", ".IXIC"),
    ("USD/KRW", "fx", "FX_USDKRW"),
]

WEEKLY_FALLBACK = [
    {"name": "코스피", "level": "7,475.94", "weekly": 1.8},
    {"name": "코스닥", "level": "831.23", "weekly": -0.6},
    {"name": "S&P 500", "level": "7,537.43", "weekly": 0.9},
    {"name": "나스닥", "level": "26,121.16", "weekly": 1.4},
    {"name": "USD/KRW", "level": "1,522.40", "weekly": 0.3},
]


def _parse_price(s: str) -> float:
    return float(str(s).replace(",", ""))


def _fetch_weekly_one(label: str, kind: str, code: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    if kind == "domestic":
        rows = requests.get(
            f"https://m.stock.naver.com/api/index/{code}/price?pageSize=7&page=1",
            headers=headers, timeout=4,
        ).json()
        closes = [_parse_price(r["closePrice"]) for r in rows]
    elif kind == "world":
        rows = requests.get(
            f"https://api.stock.naver.com/index/{code}/price?pageSize=7&page=1",
            headers=headers, timeout=4,
        ).json()
        closes = [_parse_price(r["closePrice"]) for r in rows]
    else:  # fx
        rows = requests.get(
            "https://m.stock.naver.com/front-api/marketIndex/prices"
            f"?category=exchange&reutersCode={code}&page=1&pageSize=7",
            headers=headers, timeout=4,
        ).json()["result"]
        closes = [_parse_price(r["closePrice"]) for r in rows]
    if len(closes) < 6:
        raise ValueError("이력 부족")
    weekly = (closes[0] / closes[5] - 1) * 100  # 최근 5거래일 등락률
    return {"name": label, "level": f"{closes[0]:,.2f}", "weekly": round(weekly, 2)}


def fetch_weekly_market() -> list[dict]:
    """주요 지수·환율의 주간(5거래일) 등락률. 실패 항목은 폴백."""
    fallback = {f["name"]: f for f in WEEKLY_FALLBACK}
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(WEEKLY_SOURCES)) as ex:
        futures = {ex.submit(_fetch_weekly_one, *src): src[0] for src in WEEKLY_SOURCES}
        for fut, label in futures.items():
            try:
                results[label] = fut.result()
            except Exception:
                results[label] = fallback[label]
    return [results[label] for label, _, _ in WEEKLY_SOURCES]


# ══════════════════════════════════════════════
# 테마 검색량 트렌드 — 네이버 데이터랩 (수요 측 지표)
# 뉴스 언급량(공급 측)과 결합해 관심의 성격을 판독한다.
# ══════════════════════════════════════════════
THEME_SEARCH_GROUPS = [
    ("AI반도체", ["AI반도체", "반도체 ETF"]),
    ("금리 인하", ["금리인하", "채권 ETF"]),
    ("K-방산", ["방산주", "방산 ETF"]),
    ("월배당", ["월배당 ETF", "배당 ETF"]),
    ("조선", ["조선주", "조선 ETF"]),
    ("2차전지", ["2차전지", "2차전지 ETF"]),
    ("금 투자", ["금투자", "금 ETF"]),
    ("커버드콜", ["커버드콜", "커버드콜 ETF"]),
    ("원자력", ["원전주", "원자력 ETF"]),
    ("미국주식", ["미국주식", "나스닥"]),
    ("ETF 상장폐지", ["ETF 상장폐지", "ETF 상폐"]),
]

# 데모용 주간 검색량 증감률(%) — 실데이터 연동 시 데이터랩 계산값으로 대체
_DEMO_SEARCH_DELTA = {
    "AI반도체": 34.2, "금리 인하": 12.7, "K-방산": 27.9, "월배당": 4.1,
    "조선": 41.5, "2차전지": -18.3, "금 투자": 22.4, "커버드콜": -9.8,
    "원자력": 8.0, "미국주식": 5.5, "ETF 상장폐지": 15.0,
}


def fetch_theme_search(client_id: str | None = None, client_secret: str | None = None) -> tuple[dict, bool]:
    """테마 키워드별 주간 검색량 증감률(%). 반환: ({키워드: 증감}, 실데이터 여부)."""
    cid = client_id or os.environ.get("NAVER_CLIENT_ID")
    csec = client_secret or os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and csec):
        return dict(_DEMO_SEARCH_DELTA), False
    try:
        today = dt.date.today()
        # 부분 주 오염 방지: 진행 중인 주를 제외하고 지난 일요일까지만 조회
        end = today - dt.timedelta(days=today.weekday() + 1)
        start = end - dt.timedelta(weeks=8)
        deltas: dict[str, float] = {}
        # 데이터랩은 요청당 5개 그룹 제한 → 나눠서 호출
        for chunk_start in range(0, len(THEME_SEARCH_GROUPS), 5):
            chunk = THEME_SEARCH_GROUPS[chunk_start : chunk_start + 5]
            body = {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "timeUnit": "week",
                "keywordGroups": [{"groupName": g, "keywords": kws} for g, kws in chunk],
            }
            r = requests.post(
                "https://openapi.naver.com/v1/datalab/search",
                json=body,
                headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
                timeout=6,
            )
            r.raise_for_status()
            for res in r.json()["results"]:
                pts = res["data"]
                if len(pts) >= 2 and pts[-2]["ratio"] > 0:
                    deltas[res["title"]] = round(
                        (pts[-1]["ratio"] / pts[-2]["ratio"] - 1) * 100, 1
                    )
        return deltas, True
    except Exception:
        return dict(_DEMO_SEARCH_DELTA), False


def _read_signal(search_delta: float, news_delta: int) -> str:
    """검색량(수요) × 뉴스(공급) 조합 판독."""
    s_up, n_up = search_delta >= 10, news_delta >= 10
    s_dn, n_dn = search_delta <= -10, news_delta <= -10
    if s_up and n_up:
        return "대중 확산"
    if s_up and not n_up:
        return "커뮤니티발 선행"
    if n_up and not s_up:
        return "업계 이슈"
    if s_dn and n_dn:
        return "관심 냉각"
    return "유지"


def theme_trend_table(client_id: str | None = None, client_secret: str | None = None) -> tuple[pd.DataFrame, bool]:
    """테마별 검색량 증감 + 뉴스 언급 + 판독 결합 테이블."""
    search, live = fetch_theme_search(client_id, client_secret)
    rows = []
    for kw in NEWS_KEYWORDS:
        name = kw["키워드"]
        s_delta = search.get(name)
        if s_delta is None:
            continue
        rows.append(
            {
                "키워드": name,
                "검색증감": s_delta,
                "뉴스언급": kw["언급량"],
                "뉴스증감": kw["증감"],
                "판독": _read_signal(s_delta, kw["증감"]),
                "url": kw["url"],
            }
        )
    df = pd.DataFrame(rows).sort_values("검색증감", ascending=False)
    return df, live


# ══════════════════════════════════════════════
# 테마 시그널 보드 — 수급·주가·검색 3축 러프 진단 → 액션 라벨
# 부호 기반 단순 판정 (정교화는 실데이터 축적 후 백테스트로)
# ══════════════════════════════════════════════
def demo_theme_flows(n_weeks: int = 8) -> pd.DataFrame:
    """테마별 주간 투자자 수급 데모 (억원). 스마트머니 = 외국인+기관(금융투자 제외).
    실운영 시 테마 대표종목 바스켓의 KRX 투자자별 순매수로 대체."""
    weeks = week_labels(n_weeks)
    rng = np.random.default_rng(11)
    rows = []
    for theme in THEMES:
        phase = rng.uniform(0, 2 * np.pi)
        scale = rng.uniform(80, 400)
        for i, wk in enumerate(weeks):
            smart = np.sin(phase + i * 0.8) * scale + rng.normal(0, scale * 0.35)
            # 개인은 스마트머니에 후행(위상 지연)하는 경향을 데모에 반영
            retail = np.sin(phase + i * 0.8 - 1.6) * scale * 0.9 + rng.normal(0, scale * 0.35)
            rows.append(
                {"주차": wk, "테마": theme, "스마트머니": round(smart, 1), "개인": round(retail, 1)}
            )
    return pd.DataFrame(rows)


# 테마 ↔ 검색 키워드 매핑 (매핑 없는 테마는 데모 증감 사용)
THEME_SEARCH_MAP = {
    "반도체": "AI반도체",
    "방산": "K-방산",
    "배당": "월배당",
    "조선": "조선",
    "2차전지": "2차전지",
    "금·원자재": "금 투자",
    "채권·금리": "금리 인하",
}


PRICE_FLAT = 1.0  # 4주 수익률 ±1% 이내는 보합으로 취급 (확산기 오판 방지)


def signal_label(smart4: float, retail4: float, price4: float) -> str:
    """러프 판정: 네 단계 조건을 병행 검사한 뒤 판단한다 (순차 우선순위 없음).

    조건 정의 —
      태동기 = 외인·기관+ & 개인 미유입 / 확산기 = 가격 +1% 초과 상승 & 개인+ /
      과열기 = 외인·기관− & 개인+ (교대 구조) / 쇠퇴기 = 모두 이탈 & 가격 비상승
    판정 —
      정확히 1개 참 → 해당 단계 / 확산기·과열기 동시 참 → '확산→과열' 전환 구간
      (논리상 동시 성립 가능한 조합은 이 둘뿐) / 모두 거짓 → 관망(판정 유보)."""
    matches = []
    if smart4 > 0 and retail4 <= 0:
        matches.append("태동기")
    if price4 > PRICE_FLAT and retail4 > 0:
        matches.append("확산기")
    if smart4 < 0 and retail4 > 0:
        matches.append("과열기")
    if smart4 < 0 and retail4 <= 0 and price4 <= 0:
        matches.append("쇠퇴기")

    if len(matches) == 1:
        return matches[0]
    if set(matches) == {"확산기", "과열기"}:
        return "확산→과열"
    return "관망"


LABEL_ORDER = {"확산기": 0, "태동기": 1, "확산→과열": 2, "과열기": 3, "쇠퇴기": 4, "관망": 5}


def theme_signal_board(
    flows: pd.DataFrame,
    theme_returns: pd.DataFrame,
    sel_week: str,
    search_deltas: dict[str, float],
) -> pd.DataFrame:
    """테마별 [스마트머니·개인 4주 수급, 4주 수익률, 검색 증감] + 액션 라벨."""
    weeks = list(dict.fromkeys(flows["주차"]))
    if sel_week not in weeks:
        return pd.DataFrame()
    end = weeks.index(sel_week) + 1
    window = weeks[max(0, end - 4) : end]
    rng = np.random.default_rng(23)

    rows = []
    for theme in sorted(flows["테마"].unique()):
        f4 = flows[(flows["테마"] == theme) & (flows["주차"].isin(window))]
        r4 = theme_returns[
            (theme_returns["테마"] == theme) & (theme_returns["주차"].isin(window))
        ]["수익률"].sum()
        smart4 = f4["스마트머니"].sum()
        retail4 = f4["개인"].sum()
        kw = THEME_SEARCH_MAP.get(theme)
        search_d = search_deltas.get(kw) if kw else None
        if search_d is None:
            search_d = round(float(rng.normal(0, 12)), 1)  # 미매핑 테마 데모값
        rows.append(
            {
                "테마": theme,
                "스마트머니4주": round(smart4, 0),
                "개인4주": round(retail4, 0),
                "가격4주": round(float(r4), 1),
                "검색증감": search_d,
                "라벨": signal_label(smart4, retail4, r4),
            }
        )
    df = pd.DataFrame(rows)
    df["_ord"] = df["라벨"].map(LABEL_ORDER)
    return df.sort_values(["_ord", "가격4주"], ascending=[True, False]).drop(columns="_ord")


# ══════════════════════════════════════════════
# 실시간 뉴스 키워드 언급량 — 구글 뉴스 RSS (키 불필요, 실데이터)
# ══════════════════════════════════════════════
# 사전 매칭 방식: 조잡한 형태소 토큰화 대신 금융·테마 사전으로 헤드라인 매칭
NEWS_KW_PATTERNS = [
    ("반도체", r"반도체"), ("AI", r"AI|인공지능"), ("2차전지", r"2차전지|이차전지"),
    ("방산", r"방산|방위산업"), ("조선", r"조선"), ("은행", r"은행"), ("보험", r"보험"),
    ("바이오", r"바이오|제약"), ("배당", r"배당"), ("금리", r"금리"), ("채권", r"채권"),
    ("금 현물", r"금값|금 시세|금현물|골드"), ("원자력", r"원자력|원전|SMR"),
    ("전력", r"전력|전선"), ("미국주식", r"미국|나스닥|S&P|월가"), ("커버드콜", r"커버드콜"),
    ("리츠", r"리츠"), ("밸류업", r"밸류업"), ("연금", r"연금|퇴직연금|IRP"),
    ("코스피", r"코스피"), ("코스닥", r"코스닥"), ("엔비디아", r"엔비디아"),
    ("비트코인", r"비트코인|가상자산"), ("상장폐지", r"상장폐지|상폐"), ("신규상장", r"신규 상장|상장[^폐]"),
]


def fetch_news_mentions(query: str = "ETF", max_kw: int = 12):
    """구글 뉴스 RSS 헤드라인에서 키워드 언급량 집계.
    반환: (키워드 목록 [{키워드, 언급량, url}], 최근 기사 [{title, link}], 실데이터 여부)"""
    import re as _re
    try:
        r = requests.get(
            f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
        )
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        articles = []
        for it in items:
            t, l = it.find("title"), it.find("link")
            if t is not None and t.text:
                articles.append({"title": t.text, "link": l.text if l is not None else "#"})
        if not articles:
            return [], [], False
        counts = []
        for name, pat in NEWS_KW_PATTERNS:
            n = sum(1 for a in articles if _re.search(pat, a["title"]))
            if n > 0:
                counts.append({
                    "키워드": name, "언급량": n,
                    "url": f"https://news.google.com/rss/search?q={quote(name + ' ETF')}" .replace("/rss", "")
                           + "&hl=ko&gl=KR&ceid=KR%3Ako",
                })
        counts.sort(key=lambda x: -x["언급량"])
        return counts[:max_kw], articles[:30], True
    except Exception:
        return [], [], False
