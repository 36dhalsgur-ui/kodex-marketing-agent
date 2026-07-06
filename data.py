"""데모 데이터 생성 및 실시간 지수 수집 모듈.

실제 운영 시 KRX / 구글뉴스 / 유튜브 API 연동부로 교체하는 것을 전제로,
동일한 스키마의 데모 데이터를 제공한다.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

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
NEWS_KEYWORDS = [
    {"키워드": "AI 전력 인프라", "언급량": 128, "증감": 41, "방향": "라이징"},
    {"키워드": "금리 인하 기대", "언급량": 96, "증감": 18, "방향": "라이징"},
    {"키워드": "K-방산 수출", "언급량": 87, "증감": 25, "방향": "라이징"},
    {"키워드": "월배당 ETF", "언급량": 74, "증감": 6, "방향": "유지"},
    {"키워드": "반도체 업황", "언급량": 69, "증감": -12, "방향": "정체"},
    {"키워드": "2차전지 반등", "언급량": 52, "증감": -21, "방향": "하락"},
    {"키워드": "금 현물 투자", "언급량": 48, "증감": 15, "방향": "라이징"},
    {"키워드": "커버드콜 전략", "언급량": 41, "증감": -4, "방향": "유지"},
]

ISSUER_NEWS = {
    "KODEX": [
        "AI전력핵심설비 ETF 순자산 5,000억 돌파 — 데이터센터 전력주 수요 지속",
        "'강남역 8번출구' 시즌2 공개, 초보 투자자 대상 콘텐츠 마케팅 강화",
    ],
    "TIGER": [
        "미국배당다우존스 월배당 시리즈 라인업 확대 발표",
        "타깃데이트펀드(TDF) 액티브 ETF 신규 상장 예고",
    ],
    "RISE": [
        "리브랜딩 1주년 — 미국AI밸류체인 중심 해외 테마 강화",
        "고배당 라인업 보수 인하로 연금계좌 수요 공략",
    ],
    "ACE": [
        "KRX금현물 ETF 순자산 3조 돌파, 금 투자 열풍 수혜",
        "'ACE RUN' 러닝 커뮤니티 이벤트로 2030 접점 확대",
    ],
    "SOL": [
        "조선TOP3플러스 순자산 1조 돌파 — K-조선 슈퍼사이클 수혜 지속",
        "미국배당다우존스 월배당 시리즈로 연금 투자자 공략 강화",
    ],
    "HANARO": [
        "원자력iSelect, SMR 모멘텀에 기관 자금 유입 지속",
        "퇴직연금 채널 연계 마케팅으로 라인업 확장 추진",
    ],
    "PLUS": [
        "K방산 ETF, 방산 수출 모멘텀에 순자산 최고치 경신",
        "리브랜딩 이후 시그니처 테마 선점 전략 지속",
    ],
    "TIMEFOLIO": [
        "액티브 ETF 수익률 상위권 석권 — 운용 역량 부각",
        "K바이오액티브에 기관 자금 유입 확대",
    ],
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
