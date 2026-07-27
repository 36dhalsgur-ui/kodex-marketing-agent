"""KODEX 마케팅 AI Agent — 홈 + 채널 탭 구조.

워크플로: 모니터링(시장 트렌드·채널) → 마케팅 효과 측정(DiD) → 주간 리포트.
DiD는 KODEX 처치군 고정 · 동일테마 경쟁 ETF 평균 대조군 · 8주 베이스라인 ·
Z-score→Sigmoid 0~100점 설계를 따른다.
"""

import datetime as dt
import hashlib
import importlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D
import report_template as RT

# 배포 환경 핫리로드 시 data 모듈이 구버전으로 캐시되면 필수 함수가 없어
# 앱 전체가 죽는다 — 필수 속성 누락 시 강제 재로드로 자가 복구한다.
_REQUIRED_ATTRS = (
    "kodex_etfs", "control_group", "did_series", "did_score", "detect_marketing_events", "classify_marketing_events",
    "load_etf_flows", "real_netbuy_frame", "lineup_gaps", "classify_etf", "etf_brand_of",
    "review_current_marketing", "gap_competitors", "etf_product_type", "build_recommendations",
    "fetch_regulations", "fetch_regulation_news", "REG_RELEVANT", "REG_EXCLUDE",
    "fetch_laws", "LAW_TARGETS",
    "build_insights", "fetch_youtube", "fetch_datalab", "fetch_weekly_market", "fetch_news_mentions",
    "NEWS_KW_PATTERNS", "fetch_blogs", "BRAND_BLOGS", "fetch_partners", "PARTNER_CHANNELS", "ETF_CONTENT_PAT",
    "theme_signal_board", "demo_theme_flows", "signal_label",
    "DATALAB_GROUPS", "DATALAB_KEYWORDS", "ISSUERS", "BASELINE_WEEKS", "ZSCORE_WINDOW", "LAPLACE_ALPHA",
)
if any(not hasattr(D, a) for a in _REQUIRED_ATTRS):
    D = importlib.reload(D)

# 위 목록은 사람이 관리해서 새 함수를 추가할 때 빠뜨리기 쉽다(실제로 반복 발생).
# 이름 존재 여부만 보면 '시그니처만 바뀐 기존 함수'를 놓친다(실측: detect_marketing_events에
# 인자를 추가했는데 이름이 이미 있어 재로드가 안 걸렸다). 소스 해시를 직접 대조한다.
try:
    _src = (Path(__file__).parent / "data.py").read_text()
    _sig = hashlib.md5(_src.encode()).hexdigest()
    if getattr(D, "_SRC_SIG", None) != _sig:
        D = importlib.reload(D)
        D._SRC_SIG = _sig
except Exception:
    pass


def news_link(query: str) -> str:
    """구글 뉴스 검색 링크 (data 모듈 버전과 무관한 자체 폴백)."""
    return f"https://news.google.com/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR%3Ako"


# ──────────────────────────────────────────────
# 페이지 설정 & 스타일
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="KODEX ETF 마케팅 AI Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 컬러 시스템 — 삼성자산운용 브랜드 계열
# 브랜드 블루를 정체성으로, 구조는 네이비로. 중립색은 푸른기를 살짝 섞어
# 범용 회색조가 아니라 이 팔레트에서 고른 색으로 읽히게 한다.
BRAND = "#1428A0"       # 삼성 블루 — 브랜드 앵커(상단 바·강조·활성 탭)
BRAND_SOFT = "#EAEEF9"  # 브랜드 연배경
NAVY = "#1F3A6E"        # 구조색 — 제목·표 헤더·규칙선
INK = "#141B2D"
MUTED = "#5B6478"
FAINT = "#93A0B4"
LINE = "#E3E8EF"
RED = "#D0342C"         # 상승(한국 관례) — 데이터 전용
COOL = "#2A62B8"        # 하락 — 데이터 전용
GRAY = MUTED
# 표면 위계 — 페이지 / 패널 / 카드를 구분해야 '떠 있는' 느낌이 생긴다
BG_PAGE = "#F6F8FB"     # 페이지 바탕 (흰 배경에 흰 카드 → 평면적이던 문제)
BG_PANEL = "#FBFCFE"    # 사이드바
BG_CARD = "#FFFFFF"

st.markdown(
    f"""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    /* 폰트 — Streamlit 기본(Source Sans)이 우선해 앱 전체가 기본 폰트로 렌더되던 문제.
       .stApp에 지정하고 아이콘을 제외한 전 요소가 상속하도록 강제한다. */
    .stApp {{
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont,
                     'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
        color: {INK}; background: {BG_PAGE};
        font-variant-numeric: tabular-nums; font-feature-settings: 'tnum' 1;
        /* 한글은 기본값이면 단어 중간에서 끊긴다("감지"/"된"). 어절 단위로만 줄바꿈하되,
           한 어절이 줄보다 길면 넘치지 않게 예외적으로 쪼갠다. */
        word-break: keep-all; overflow-wrap: break-word;
    }}
    .stApp *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]) {{
        font-family: inherit;
    }}

    .block-container {{ padding-top: 1.1rem; padding-bottom: 4rem; max-width: 1320px; }}
    #MainMenu, footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{ background: transparent; height: 0; }}

    /* 사이드바 — 기본 위젯 나열이 아니라 설정 패널로 */
    [data-testid="stSidebar"] {{ background: {BG_PANEL}; border-right: 1px solid {LINE}; }}
    [data-testid="stSidebar"] label p {{
        font-size: 0.75rem !important; font-weight: 700 !important; color: {MUTED} !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
        border-radius: 8px; border-color: {LINE}; background: #fff;
    }}
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{
        border-radius: 8px; border: 1px dashed {LINE}; background: #fff;
    }}
    [data-testid="stSidebar"] hr {{ margin: 1.1rem 0; border-color: {LINE}; }}
    /* 슬라이더를 브랜드색으로 (기본 빨강 제거) */
    [data-testid="stSidebar"] [role="slider"] {{ background: {BRAND} !important; }}
    [data-testid="stSidebar"] [data-baseweb="slider"] [data-testid="stThumbValue"] {{
        color: {BRAND} !important;
    }}

    /* 브랜드 앵커 — 리포트(PDF) 상단 바와 동일한 장치 */
    .block-container::before {{
        content: ""; position: fixed; top: 0; left: 0; right: 0; height: 4px;
        background: {BRAND}; z-index: 999;
    }}

    button[data-baseweb="tab"] {{ font-weight: 700; }}
    button[data-baseweb="tab"] p {{ font-size: 0.92rem !important; }}
    button[data-baseweb="tab"][aria-selected="true"] p {{ color: {BRAND} !important; }}
    [data-baseweb="tab-highlight"] {{ background-color: {BRAND} !important; }}

    /* 홈 — 주간 종합 리드 */
    .home-lead {{
        background: linear-gradient(135deg, {NAVY} 0%, {BRAND} 140%);
        border-radius: 12px; padding: 20px 24px; color: #fff;
    }}
    .home-lead .hl-k {{
        font-size: 0.64rem; font-weight: 700; letter-spacing: .16em; opacity: .72;
    }}
    .home-lead .hl-t {{ font-size: 1.02rem; font-weight: 600; line-height: 1.7; margin-top: 7px; }}
    .home-lead b {{ font-weight: 800; }}

    /* 홈 — 지수 스트립 (카드 나열 → 구분선 한 줄) */
    .mkt-strip {{
        display: flex; background: {BG_CARD}; border: 1px solid {LINE};
        border-radius: 10px; overflow: hidden;
    }}
    .mkt-cell {{ flex: 1; padding: 11px 14px; border-left: 1px solid {LINE}; }}
    .mkt-cell:first-child {{ border-left: none; }}
    .mkt-n {{ font-size: 0.64rem; font-weight: 700; letter-spacing: .07em; color: {FAINT};
        text-transform: uppercase; }}
    .mkt-v {{ font-size: 1.02rem; font-weight: 800; margin-top: 3px; color: {INK};
        font-variant-numeric: tabular-nums; letter-spacing: -.01em;
        display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }}
    /* 전일 등락률 — 지수값 옆 수식어라 한 급 작게 */
    .mkt-d {{ font-size: 0.82rem; font-weight: 700; }}
    .mkt-s {{ font-size: 0.68rem; color: {FAINT}; margin-top: 2px;
        font-variant-numeric: tabular-nums; }}

    /* 홈 — KPI (하나만 주인공) */
    .kpi2 {{ background: {BG_CARD}; border: 1px solid {LINE}; border-radius: 10px;
        padding: 14px 16px; height: 100%; }}
    .kpi2.lead {{ border-color: {BRAND}; box-shadow: 0 0 0 3px {BRAND_SOFT}; }}
    .kpi2 .k {{ font-size: 0.64rem; font-weight: 700; letter-spacing: .08em; color: {FAINT};
        text-transform: uppercase; }}
    .kpi2 .v {{ font-size: 1.12rem; font-weight: 800; color: {INK}; margin-top: 5px;
        line-height: 1.3; letter-spacing: -.01em; }}
    .kpi2 .s {{ font-size: 0.74rem; color: {MUTED}; margin-top: 4px; line-height: 1.5; }}

    /* 홈 — 워크플로 스텝 */
    .flow {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .flow-step {{ flex: 1; min-width: 150px; background: {BG_CARD}; border: 1px solid {LINE};
        border-radius: 10px; padding: 12px 14px; position: relative; }}
    .flow-step .no {{ font-size: 0.66rem; font-weight: 800; color: {BRAND}; letter-spacing: .06em; }}
    .flow-step .nm {{ font-size: 0.86rem; font-weight: 800; color: {INK}; margin: 2px 0 3px; }}
    .flow-step .ds {{ font-size: 0.71rem; color: {MUTED}; line-height: 1.5; }}

    /* 헤더 — 아이덴티티 + 데이터 신선도 상태를 한 줄에 (모니터링 도구의 기본 정보) */
    .apphead {{
        display: flex; align-items: flex-end; justify-content: space-between; gap: 24px;
        padding: 2px 0 14px; border-bottom: 1px solid {LINE}; margin-bottom: 2px;
    }}
    .agent-overline {{
        font-size: 0.62rem; font-weight: 800; letter-spacing: 0.18em;
        color: {BRAND}; margin-bottom: 7px;
    }}
    .agent-title {{
        font-size: 1.72rem; font-weight: 800; color: {INK};
        letter-spacing: -0.035em; line-height: 1.15;
    }}
    .agent-sub {{ font-size: 0.82rem; color: {MUTED}; margin-top: 6px; letter-spacing: -0.01em; }}
    .head-meta {{ display: flex; gap: 18px; white-space: nowrap; }}
    .hm-item {{ text-align: right; }}
    .hm-k {{ font-size: 0.6rem; font-weight: 700; letter-spacing: .09em; color: {FAINT};
        text-transform: uppercase; }}
    .hm-v {{ font-size: 0.82rem; font-weight: 700; color: {INK}; margin-top: 3px; }}
    .hm-dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%;
        background: #2E9E62; margin-right: 5px; vertical-align: middle; }}

    .idx-strip {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0; }}
    .idx-card {{
        flex: 1; min-width: 128px; background: {BG_CARD};
        border: 1px solid {LINE}; border-radius: 10px; padding: 12px 14px;
    }}
    .idx-name {{
        font-size: 0.66rem; font-weight: 600; letter-spacing: 0.07em;
        color: {FAINT}; margin-bottom: 6px; text-transform: uppercase;
    }}
    .idx-val {{
        font-size: 1.1rem; font-weight: 700; color: {INK};
        letter-spacing: -0.01em; font-variant-numeric: tabular-nums;
    }}
    .idx-chg {{
        font-size: 0.75rem; font-weight: 600; margin-top: 3px;
        font-variant-numeric: tabular-nums;
    }}
    .idx-up {{ color: {RED}; }}
    .idx-down {{ color: {COOL}; }}
    .idx-group {{
        font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em;
        color: {FAINT}; margin: 14px 0 6px;
    }}

    /* 시그널 보드 — 단일 표(헤더 1회) · 행 높이를 낮춰 정보밀도를 올린다 */
    table.sig-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    table.sig-table th {{
        font-size: 0.62rem; font-weight: 800; letter-spacing: 0.1em; color: {MUTED};
        text-transform: uppercase; text-align: left; padding: 0 10px 7px;
        border: none; border-bottom: 1.5px solid {NAVY}; white-space: nowrap;
    }}
    table.sig-table th.num, table.sig-table td.num {{ text-align: right; }}
    table.sig-table td {{
        font-size: 0.85rem; padding: 9px 10px; text-align: left; border: none;
        font-variant-numeric: tabular-nums; color: {INK}; vertical-align: top;
    }}
    table.sig-table tbody tr:hover td {{ background: #FAFBFD; }}
    .sig-pos {{ color: {RED}; font-weight: 700; }}
    .sig-neg {{ color: {COOL}; font-weight: 700; }}
    table.sig-table td.flow-cell {{
        font-size: 0.74rem; color: {MUTED}; line-height: 1.7;
        font-weight: 500; text-align: right;
    }}

    /* 섹션 헤더 — 좌측 브랜드 룰로 위계를 만든다 */
    .sec-tag {{
        font-size: 0.62rem; font-weight: 800; letter-spacing: 0.16em;
        color: {BRAND}; margin-bottom: 7px;
    }}
    .sec-title {{
        font-size: 1.42rem; font-weight: 800; color: {INK}; letter-spacing: -0.032em;
        line-height: 1.25; padding-left: 12px; border-left: 3px solid {BRAND};
    }}
    /* max-width에 ch를 쓰면 안 된다 — ch는 숫자 '0' 폭 기준이라 한글은 약 2배를 차지해
       78ch가 실제로는 39글자 남짓에서 끊긴다. 폭은 상위 컨테이너에 맡긴다. */
    .sec-desc {{ font-size: 0.83rem; color: {MUTED}; margin-top: 6px; padding-left: 15px;
        line-height: 1.6; }}

    /* 카드 — 테두리 대신 옅은 그림자로 페이지 바탕 위에 띄운다 */
    .card {{
        background: {BG_CARD}; border: 1px solid #EDF1F6; border-radius: 12px;
        padding: 18px 20px; height: 100%;
        box-shadow: 0 1px 2px rgba(20,27,45,.04), 0 4px 12px rgba(20,27,45,.03);
    }}
    .card-title {{
        font-size: 0.9rem; font-weight: 800; color: {INK}; margin-bottom: 11px;
        letter-spacing: -0.015em;
    }}

    /* KPI */
    .kpi-card {{
        background: {BG_CARD}; border: 1px solid {LINE}; border-radius: 12px;
        padding: 16px 18px; height: 100%;
    }}
    .kpi-label {{
        font-size: 0.64rem; font-weight: 700; letter-spacing: 0.12em;
        color: {FAINT}; text-transform: uppercase;
    }}
    .kpi-value {{
        font-size: 1.25rem; font-weight: 800; color: {INK}; margin-top: 7px;
        letter-spacing: -0.01em; line-height: 1.3;
    }}
    .kpi-sub {{ font-size: 0.76rem; color: {MUTED}; margin-top: 4px; font-variant-numeric: tabular-nums; }}

    /* DiD */
    .did-step {{
        background: #FAFBFC; border: 1px solid {LINE}; border-radius: 10px;
        padding: 14px 16px; height: 100%;
    }}
    .did-step-no {{ font-size: 0.64rem; font-weight: 700; letter-spacing: 0.12em; color: {FAINT}; }}
    .did-step-name {{ font-size: 0.88rem; font-weight: 700; color: {INK}; margin: 4px 0 6px; }}
    .did-step-val {{
        font-size: 1.3rem; font-weight: 800; color: {NAVY};
        font-variant-numeric: tabular-nums; letter-spacing: -0.01em;
    }}
    .did-step-desc {{ font-size: 0.74rem; color: {MUTED}; margin-top: 5px; line-height: 1.5; }}
    .did-result {{
        background: {NAVY}; border-radius: 10px; padding: 18px 20px;
        color: white;
    }}
    .did-result-label {{ font-size: 0.66rem; font-weight: 600; letter-spacing: 0.1em; opacity: 0.65; }}
    .did-result-val {{
        font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; margin-top: 2px;
        font-variant-numeric: tabular-nums;
    }}
    .did-result-note {{ font-size: 0.78rem; opacity: 0.78; margin-top: 5px; line-height: 1.55; }}
    .score-track {{
        background: rgba(255,255,255,0.18); border-radius: 99px; height: 8px;
        margin-top: 12px; overflow: hidden;
    }}
    .score-fill {{ background: #7FE0A7; height: 100%; border-radius: 99px; }}

    /* 키워드 */
    .kw-row {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 2px; border-bottom: 1px solid #F2F4F7; font-size: 0.86rem;
    }}
    .kw-row:last-child {{ border-bottom: none; }}
    .kw-name {{ font-weight: 600; color: {INK}; }}
    .kw-badge {{
        font-size: 0.7rem; font-weight: 700; border-radius: 5px; padding: 3px 8px;
        font-variant-numeric: tabular-nums; white-space: nowrap;
    }}
    .kw-rise {{ background: #FEF1F2; color: #D63C48; }}
    .kw-ok {{ background: #ECFDF5; color: #0E9F6E; }}
    .kw-fall {{ background: #EFF5FF; color: #2A6FDB; }}
    .kw-flat {{ background: #F2F4F7; color: {MUTED}; }}
    .kw-warn {{ background: #FFF6E6; color: #B3730A; }}
    .kw-none {{ background: transparent; border: 1px dashed #CBD5E1; color: {FAINT}; }}
    .kw-shift {{ background: #F5F0FF; color: #7C3AED; }}
    a.kw-link, a.kw-link * {{ text-decoration: none !important; color: inherit; }}
    a.kw-link {{ display: block; }}
    a.kw-link:hover .kw-name {{ color: {NAVY}; text-decoration: underline !important; }}
    .kw-cols {{ display: flex; gap: 32px; }}
    .kw-col {{ flex: 1; min-width: 0; }}

    /* 유튜브 실썸네일 카드 */
    .yt-card {{
        background: {BG_CARD}; border: 1px solid {LINE}; border-radius: 12px;
        overflow: hidden; margin-bottom: 4px;
    }}
    .yt-real-thumb {{ display: block; position: relative; }}
    .yt-real-thumb img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
    .yt-brand-chip {{
        position: absolute; top: 8px; left: 8px; font-size: 0.62rem; font-weight: 800;
        letter-spacing: 0.06em; color: white; background: rgba(10,16,40,0.72);
        border-radius: 5px; padding: 3px 8px;
    }}
    .yt-card, .yt-card * {{ text-decoration: none !important; }}
    .yt-body {{ padding: 11px 13px 12px; }}
    .yt-title {{
        display: block; font-size: 0.8rem; font-weight: 700; color: {INK};
        line-height: 1.45; margin-bottom: 6px; min-height: 2.9em;
    }}
    .yt-title:hover {{ color: {NAVY}; text-decoration: underline !important; }}
    .yt-meta {{ font-size: 0.72rem; color: {MUTED}; font-variant-numeric: tabular-nums; }}
    .yt-thumb {{
        display: flex; flex-direction: column; justify-content: space-between;
        aspect-ratio: 16 / 9; padding: 12px 14px;
    }}
    .yt-chip {{
        align-self: flex-start; font-size: 0.6rem; font-weight: 700;
        letter-spacing: 0.12em; color: rgba(255,255,255,0.85);
        border: 1px solid rgba(255,255,255,0.4); border-radius: 4px; padding: 2px 7px;
    }}
    .yt-brand {{ font-size: 1.3rem; font-weight: 800; color: white; }}
    .yt-tag {{ font-size: 0.7rem; font-weight: 600; color: rgba(255,255,255,0.8); margin-top: 2px; }}
    .yt-sub {{
        display: block; font-size: 0.72rem; font-weight: 500; color: {MUTED};
        line-height: 1.4; padding-top: 8px; border-top: 1px solid #F2F4F7;
    }}
    .yt-sub:hover {{ color: {NAVY}; text-decoration: underline !important; }}

    /* 액션 카드 */
    .act-card {{
        background: {BG_CARD}; border: 1px solid {LINE}; border-radius: 12px;
        padding: 16px 18px; margin-bottom: 10px;
    }}
    .act-prio {{
        display: inline-block; font-size: 0.62rem; font-weight: 800;
        letter-spacing: 0.1em; border-radius: 5px; padding: 3px 8px; margin-bottom: 8px;
    }}
    .prio-HIGH {{ background: #FEF1F2; color: #D63C48; }}
    .prio-MID {{ background: #FFF6E6; color: #B3730A; }}
    .prio-LOW {{ background: #F2F4F7; color: {MUTED}; }}
    .act-title {{ font-size: 0.95rem; font-weight: 800; color: {INK}; margin-bottom: 6px; }}
    .act-row {{ font-size: 0.8rem; color: #475467; line-height: 1.6; }}
    .act-row b {{ color: {NAVY}; }}

    hr.sec-divider {{ border: none; border-top: 1px solid {LINE}; margin: 1.8rem 0 1.4rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def section_header(tag: str, title: str, desc: str):
    st.markdown(
        f'<div class="sec-tag">{tag}</div>'
        f'<div class="sec-title">{title}</div>'
        f'<div class="sec-desc">{desc}</div>',
        unsafe_allow_html=True,
    )


# 가로 막대 1개가 차지하는 높이 + 제목·축·여백에 필요한 고정분.
# 항목 수 × ROW_PX 만 잡으면 제목이 잘린다(실측) — CHROME_PX를 반드시 더한다.
# st.container(height=…)로 스크롤 박스를 씌우는 방법도 시도했으나, Plotly가
# 스크롤 컨테이너 안에서 폭을 0으로 측정해 resize 전까지 빈 화면이 된다(실측).
BAR_ROW_PX = 26
CHART_CHROME_PX = 110


def sub_header(no: str, title: str, desc: str = ""):
    """탭 내부 소제목 — 번호 + 제목 + 한 줄 설명으로 문서 위계를 만든다."""
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:9px;margin:2px 0 9px;">'
        f'<span style="font-size:0.66rem;font-weight:800;color:{BRAND};'
        f'background:{BRAND_SOFT};border-radius:5px;padding:3px 8px;letter-spacing:.06em;">{no}</span>'
        f'<span style="font-size:0.98rem;font-weight:800;color:{INK};">{title}</span>'
        f'<span style="font-size:0.74rem;color:{FAINT};">{desc}</span></div>',
        unsafe_allow_html=True,
    )


def base_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    """차트도 타이포와 같은 수준으로 다듬는다 — 옅은 그리드, 축 라벨 축소, 제목 정렬."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=44, b=8),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Pretendard, -apple-system, sans-serif", size=12, color=MUTED),
        # y/yanchor를 명시하지 않으면 Plotly가 제목을 SVG 위쪽 밖으로 밀어 글자 윗부분이
        # 잘린다(실측: 차트 상단보다 9px 위에 그려짐). 상단에서 일정 비율로 못박는다.
        title=dict(x=0, xanchor="left", y=0.99, yanchor="top",
                   font=dict(size=14.5, color=INK, weight=800), pad=dict(b=10)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=11.5), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, zeroline=False, showline=True, linecolor=LINE,
                   tickfont=dict(size=11, color=FAINT)),
        yaxis=dict(gridcolor="#F0F3F8", zeroline=False, griddash="dot",
                   tickfont=dict(size=11, color=FAINT)),
        hoverlabel=dict(bgcolor="white", bordercolor=LINE,
                        font=dict(family="Pretendard, sans-serif", size=12, color=INK)),
    )
    # title dict를 text 없이 넘기면 Plotly가 'undefined'를 그린다 —
    # 제목을 소제목으로 빼둔 차트(브랜드 검색량 트렌드)가 여기 해당했다.
    # 제목이 없으면 상단 여백도 함께 줄인다.
    if not fig.layout.title.text:
        fig.update_layout(title_text="", margin=dict(l=8, r=8, t=12, b=8))
    return fig


# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_weekly_market():
    return D.fetch_weekly_market()


@st.cache_data
def load_netbuy():
    """ETF 순매수 — 배치 실데이터(개인 순매수÷순자산)가 있으면 그것을, 없으면 데모."""
    flows = D.load_etf_flows()
    if flows:
        df = D.real_netbuy_frame(flows)
        if len(df):
            return D.add_intensity(df), True
    return D.add_intensity(D.demo_netbuy_data()), False


@st.cache_data
def load_theme_returns():
    return D.demo_theme_returns()


@st.cache_data(ttl=1800)
def _load_youtube_cached():
    return D.fetch_youtube(n_per_channel=8)


def load_youtube():
    """전 채널이 빈 결과는 캐시에 남기지 않는다.

    유튜브 RSS가 일시적으로 막히면 빈 dict가 30분 동안 캐시돼 화면이 계속
    비어 있었다(실측). 수집 실패는 30분 붙잡을 값이 아니므로 즉시 폐기하고
    한 번 더 시도한다."""
    y = _load_youtube_cached()
    if not any(y.values()):
        _load_youtube_cached.clear()
        y = _load_youtube_cached()
    return y


@st.cache_data(ttl=1800)
def load_issuer_news():
    return D.fetch_issuer_news(n_per_issuer=3)


@st.cache_data(ttl=1800)
def load_blogs():
    return D.fetch_blogs(n_per_blog=6)


@st.cache_data(ttl=1800)
def load_partners():
    return D.fetch_partners(n_per_source=10)


@st.cache_data(ttl=3600)
def load_regulations(rule_sig: str = ""):
    # rule_sig는 캐시 키 전용 — 필터 규칙이 바뀌면 낡은 결과를 자동 폐기한다
    return D.fetch_regulations()


@st.cache_data(ttl=3600)
def load_regulation_news():
    return D.fetch_regulation_news()


@st.cache_data(ttl=86400)
def load_laws():
    return D.fetch_laws()


def _mtime(name: str) -> float:
    """배치 산출 JSON의 수정 시각 — 캐시 키로 써서 파일이 바뀌면 자동 무효화."""
    p = Path(__file__).parent / "data" / name
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data
def _load_json(name: str, mtime: float):
    p = Path(__file__).parent / "data" / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def load_sector_universe():
    """섹터 구성종목 (scripts/sector_universe.py 산출).
    배치를 다시 돌리면 mtime이 바뀌어 캐시가 자동으로 폐기된다."""
    return _load_json("sector_universe.json", _mtime("sector_universe.json"))


@st.cache_data
def load_theme_flows():
    return D.demo_theme_flows()


@st.cache_data(ttl=1800)
def load_news_mentions():
    return D.fetch_news_mentions()


@st.cache_data(ttl=3600)
def load_theme_search():
    """테마 키워드별 주간 검색량 증감 (네이버 데이터랩, 키 미설정 시 데모)."""
    cid = csec = None
    try:
        cid = st.secrets.get("NAVER_CLIENT_ID")
        csec = st.secrets.get("NAVER_CLIENT_SECRET")
    except Exception:
        pass
    return D.fetch_theme_search(cid, csec)


@st.cache_data(ttl=3600)
def load_datalab(brands_sig: tuple = ()):
    # brands_sig는 캐시 키 전용 — 브랜드 목록이 바뀌면 낡은 캐시를 자동 무효화한다
    cid = csec = None
    try:
        cid = st.secrets.get("NAVER_CLIENT_ID")
        csec = st.secrets.get("NAVER_CLIENT_SECRET")
    except Exception:
        pass
    return D.fetch_datalab(cid, csec)


# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div class="sec-tag">ANALYSIS SETTINGS</div>'
        '<div style="font-size:1.05rem;font-weight:800;margin-bottom:4px;">분석 설정</div>',
        unsafe_allow_html=True,
    )
    netbuy_df, netbuy_live = load_netbuy()
    weeks = list(dict.fromkeys(netbuy_df["주차"]))
    sel_week = st.selectbox("분석 주차", weeks[1:][::-1], index=0)
    top_n = st.slider("순매수강도 TOP N", 5, 20, 15)

    st.markdown("---")
    up = st.file_uploader("순매수 엑셀 업로드", type=["xlsx"], help="컬럼: 주차·종목명·테마·운용사·순매수액·순자산")
    if up is not None:
        try:
            netbuy_df = D.add_intensity(pd.read_excel(up))
            weeks = list(dict.fromkeys(netbuy_df["주차"]))
            netbuy_live = True
            st.success("업로드 데이터로 분석합니다.")
        except Exception as e:
            st.error(f"파일 형식 오류: {e}")
    elif netbuy_live:
        st.caption(f"KRX 실데이터 · 개인 순매수 기준 · {netbuy_df['종목명'].nunique()}개 ETF")
    else:
        st.caption("미업로드 시 데모 데이터로 동작합니다.")

# ──────────────────────────────────────────────
# 공용 계산
# ──────────────────────────────────────────────
w_idx = weeks.index(sel_week)
prev_week = weeks[w_idx - 1] if w_idx > 0 else None
wk = netbuy_df[netbuy_df["주차"] == sel_week].dropna(subset=["매수강도"])

theme_ret = load_theme_returns()
this_ret = theme_ret[theme_ret["주차"] == sel_week].set_index("테마")["수익률"]
prev_ret = theme_ret[theme_ret["주차"] == prev_week].set_index("테마")["수익률"] if prev_week else this_ret
theme_flow = (
    wk.groupby("테마")
    .agg(순매수합=("순매수액", "sum"), 평균강도=("매수강도", "mean"), 종목수=("종목명", "count"))
    .round(2)
)
theme_tbl = theme_flow.join(this_ret.rename("수익률")).reset_index()
theme_tbl["전주수익률"] = theme_tbl["테마"].map(prev_ret).round(2)
theme_tbl["모멘텀"] = (theme_tbl["테마"].map(this_ret) - theme_tbl["테마"].map(prev_ret)).round(2)
theme_tbl["점수"] = theme_tbl["수익률"] + theme_tbl["모멘텀"]


def flow_state(prev: float, this: float) -> str:
    """전주→금주 수익률 흐름을 사람이 읽는 상태 라벨로."""
    if prev < 0 <= this:
        return "상승 전환"
    if this < 0 <= prev:
        return "하락 전환"
    if this >= 0:
        return "가속" if this > prev else "상승 둔화"
    return "낙폭 축소" if this > prev else "낙폭 확대"


def universe_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    """실데이터 유니버스(종목명·테마·기초시장·운용사). 데모면 None."""
    cols = {"종목명", "테마", "기초시장", "운용사"}
    if cols.issubset(df.columns):
        return df[list(cols)].drop_duplicates(subset=["종목명"])
    return None


def kodex_list(df: pd.DataFrame) -> list[str]:
    uni = universe_frame(df)
    if uni is not None:
        return sorted(uni[uni["운용사"] == "KODEX"]["종목명"].unique())
    return D.kodex_etfs()


# ── ②·③·④가 공유하는 분석 파이프라인 ───────────────────────────────
# 탭마다 따로 계산하면 같은 캠페인이 탭마다 다른 숫자로 나온다.
# (실측: ③은 상품 5종인데 ④는 같은 상품을 채널 수만큼 세어 5'건' — 그중
#  2개 상품의 중복이었고, 이벤트 보드를 안 읽어 3개 상품은 아예 빠졌다.)
# 개선을 한 탭에만 반영하는 사고를 막으려면 진입점이 하나여야 한다.

def kodex_campaigns(ch_data: dict, youtube: dict, blogs: dict,
                    netbuy_df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """②에서 감지된 KODEX 마케팅 → (전체 이벤트, 캠페인 상품별 1건).

    배너·유튜브·블로그에 더해 이벤트 보드까지 넣는다 — 이벤트는 집행 기간이
    고지돼 있어 개입 시점을 추정이 아니라 사실로 정할 수 있다."""
    banners = [dict(b, date=ch_data.get("asof", ""))
               for br in ch_data.get("brands", []) if br.get("브랜드") == "KODEX"
               for b in br.get("배너", [])]
    board = next((b.get("이벤트목록", []) for b in ch_data.get("brands", [])
                  if b.get("브랜드") == "KODEX"), [])
    events = D.detect_marketing_events(
        banners, youtube.get("KODEX", []), blogs.get("KODEX", []),
        universe=kodex_list(netbuy_df), events_board=board)
    campaigns = D.dedupe_campaigns([e for e in events if e["유형"] == "캠페인"])
    return events, campaigns


def did_verified(netbuy_df: pd.DataFrame, uni, treat: str, week: str):
    """평행추세를 검증한 대조군으로 DiD 산출 → (진단표, 채택 대조군, 점수).

    라벨(테마·기초시장)만 맞은 후보를 그대로 쓰면 개입 전에 반대로 움직인
    종목이 섞여 DiD 부호까지 왜곡된다. 대조군 평균은 순자산 가중."""
    diag = D.control_diagnostics(netbuy_df, treat, D.control_group(treat, uni), week)
    controls = D.select_controls(diag)
    weights = (uni.drop_duplicates("종목명").set_index("종목명")["순자산"].to_dict()
               if uni is not None and "순자산" in uni.columns else None)
    score = D.did_score(D.did_series(netbuy_df, treat, controls, weights=weights), week)
    return diag, controls, score


@st.cache_data
def build_did_board(df: pd.DataFrame, week: str) -> pd.DataFrame:
    """전 KODEX ETF의 금주 DiD 점수 보드."""
    uni = universe_frame(df)
    rows = []
    for name in kodex_list(df):
        controls = D.control_group(name, uni)
        s = D.did_series(df, name, controls)
        sc = D.did_score(s, week)
        if not sc.get("available"):
            continue
        rows.append(
            {
                "종목명": name,
                "대조군 수": len(controls),
                "Δ처치(%p)": round(sc["delta_treat"], 2) if sc["delta_treat"] is not None else None,
                "Δ대조군(%p)": round(sc["delta_ctrl"], 2) if sc["delta_ctrl"] is not None else None,
                "DiD(%p)": round(sc["did"], 2) if sc["did"] is not None else None,
                "z": sc["z"],
                "score": sc["score"],
                "비고": sc["fallback"] or "",
            }
        )
    return pd.DataFrame(rows)


did_board = build_did_board(netbuy_df, sel_week)
youtube = load_youtube()
datalab_df, datalab_live = load_datalab(tuple(D.DATALAB_GROUPS))

# ──────────────────────────────────────────────
# 헤더 + 지수 스트립 (2줄)
# ──────────────────────────────────────────────
def _asof(fname: str) -> str:
    """배치 산출물의 수집일 — 모니터링 도구는 데이터 신선도가 곧 신뢰도다."""
    try:
        return json.loads((Path(__file__).parent / "data" / fname).read_text()).get("asof", "—")
    except Exception:
        return "—"


_meta = [
    ("시장·수급", _asof("signal_board.json")),
    ("ETF 자금", _asof("etf_flows.json")),
    ("채널", _asof("channel_board.json")),
]
st.markdown(
    '<div class="apphead"><div>'
    '<div class="agent-overline">MARKETING INTELLIGENCE · WEEKLY MONITOR</div>'
    '<div class="agent-title">KODEX ETF 마케팅 AI Agent</div>'
    '<div class="agent-sub">시장 트렌드 → 채널 모니터링 → 마케팅 효과 측정(DiD) → 주간 리포트 → 규제 동향</div>'
    '</div><div class="head-meta">'
    + "".join(f'<div class="hm-item"><div class="hm-k">{k}</div>'
              f'<div class="hm-v">{v}</div></div>' for k, v in _meta)
    + f'<div class="hm-item"><div class="hm-k">데이터</div>'
      f'<div class="hm-v"><span class="hm-dot"></span>실시간 연동</div></div>'
    + '</div></div>',
    unsafe_allow_html=True,
)


st.write("")

# ══════════════════════════════════════════════
# 탭 구조 — 모니터링이 먼저, 효과 측정(DiD)은 그 뒤
# ══════════════════════════════════════════════
tab_home, tab_trend, tab_channel, tab_did, tab_report, tab_reg = st.tabs(
    ["홈", "① 시장 트렌드", "② 채널 모니터링", "③ 마케팅 효과 측정", "④ 주간 리포트", "⑤ 규제 동향"]
)

# ──────────────────────────────────────────────
# 홈 — 금주 요약 KPI
# ──────────────────────────────────────────────
with tab_home:
    st.write("")
    section_header("HOME", f"{sel_week} 요약", "이번 주 시장과 우리 마케팅의 상태를 한 화면에 — 상세는 ①~⑤ 탭에서.")
    st.write("")

    # ── 실데이터 (시그널 보드 · 순매수 · 캠페인)
    try:
        _hb = json.loads((Path(__file__).parent / "data" / "signal_board.json").read_text())
    except Exception:
        _hb = {}
    _hrows = _hb.get("board", [])
    from collections import Counter as _HC
    _hstage = dict(_HC(r.get("단계", "관망") for r in _hrows))
    _hdec = _hstage.get("쇠퇴기", 0)
    _hn = len(_hrows) or 1
    _hbench = _hb.get("벤치주간수익률")
    _hret = sorted([r for r in _hrows if r.get("주간수익률") is not None],
                   key=lambda r: r["주간수익률"])
    _hup = _hret[-1] if _hret else None
    _hdn = _hret[0] if _hret else None
    _hemerge = [r["섹터"] for r in _hrows if r.get("단계") == "태동기"]

    # ── 주간 종합 리드 (실데이터 기반 한 문단)
    _lead_parts = [
        f'{_hn}개 섹터 중 <b>{_hdec}개가 쇠퇴 국면</b>입니다.'
    ]
    if _hbench is not None:
        # '주간 -9.6%'는 섹터명처럼 읽혀서 '한 주 동안'으로 풀어 쓴다
        _lead_parts.append(
            f'시장 대표 지수(KRX300)는 한 주 동안 <b>{_hbench:+.1f}%</b> 움직였습니다.')
    if _hdn is not None:
        _lead_parts.append(
            f'{D._ga(_hdn["섹터"])} <b>{_hdn["주간수익률"]:+.1f}%</b>로 낙폭이 가장 컸습니다.')
    if _hemerge:
        _lead_parts.append(f'태동 국면은 <b>{", ".join(_hemerge)}</b> — 선점 콘텐츠 검토 대상입니다.')
    st.markdown(
        f'<div class="home-lead"><div class="hl-k">WEEKLY SNAPSHOT · {sel_week}</div>'
        f'<div class="hl-t">{" ".join(_lead_parts)}</div></div>',
        unsafe_allow_html=True)
    st.write("")

    # ── 시장 지수 — 전일 대비를 앞에, 주간 누적을 보조로 (같은 응답에서 둘 다 계산됨)
    _cells = ""
    for m in load_weekly_market():
        _d, _w = m.get("daily", 0.0), m["weekly"]
        _cells += (
            f'<div class="mkt-cell"><div class="mkt-n">{m["name"]}</div>'
            # 지수값이 주인공, 전일 등락률은 그 옆에 붙는 수식어
            f'<div class="mkt-v">{m["level"]}'
            f'<span class="mkt-d" style="color:{RED if _d >= 0 else COOL};">{_d:+.2f}%</span></div>'
            f'<div class="mkt-s">주간 '
            f'<span style="color:{RED if _w >= 0 else COOL};font-weight:700;">{_w:+.1f}%</span>'
            f'</div></div>')
    st.markdown(
        f'<div style="font-size:0.7rem;color:{FAINT};font-weight:600;letter-spacing:.06em;'
        f'margin-bottom:6px;">시장 현황 · 30분마다 갱신</div>'
        f'<div class="mkt-strip">{_cells}</div>', unsafe_allow_html=True)
    st.write("")

    # ── KPI — 이번 주 주목할 것 하나를 주인공으로
    _top_flow = wk.nlargest(1, "매수강도").iloc[0] if len(wk) else None
    _scored = (did_board.dropna(subset=["score"]).sort_values("score", ascending=False)
               if len(did_board) else did_board)
    _yt_week = sum(1 for vs in youtube.values() for v in vs
                   if v.get("published", "") >= (dt.date.today() - dt.timedelta(days=7)).isoformat())

    k1, k2, k3, k4 = st.columns(4, gap="medium")
    # 주인공 — 과열/쇠퇴 국면 요약 (판정의 핵심)
    _hot = [r["섹터"] for r in _hrows if r.get("단계") == "과열기"]
    k1.markdown(
        f'<div class="kpi2 lead"><div class="k">시장 국면 · 01</div>'
        f'<div class="v">쇠퇴 {_hdec} / {_hn}</div>'
        f'<div class="s">태동 {_hstage.get("태동기",0)} · 확산 {_hstage.get("확산기",0)} · '
        f'과열 {_hstage.get("과열기",0)}{" (" + ", ".join(_hot) + ")" if _hot else ""}</div></div>',
        unsafe_allow_html=True)
    if _hup is not None:
        k2.markdown(
            f'<div class="kpi2"><div class="k">주간 최고 섹터 · 01</div>'
            f'<div class="v">{_hup["섹터"]}</div>'
            f'<div class="s" style="color:{RED};font-weight:700;">{_hup["주간수익률"]:+.1f}%</div></div>',
            unsafe_allow_html=True)
    if _top_flow is not None:
        _fi = _top_flow["매수강도"]
        _fnote = "신규상장 유입" if _fi >= 40 else f"매수강도 {_fi:+.2f}%"
        k3.markdown(
            f'<div class="kpi2"><div class="k">개인 순매수 1위 · 03</div>'
            f'<div class="v" style="font-size:0.98rem;">{_top_flow["종목명"]}</div>'
            f'<div class="s">{_fnote}</div></div>', unsafe_allow_html=True)
    k4.markdown(
        f'<div class="kpi2"><div class="k">브랜드 신규 영상 · 02</div>'
        f'<div class="v">{_yt_week}건</div>'
        f'<div class="s">8개 브랜드 · 최근 7일</div></div>', unsafe_allow_html=True)
    st.write("")

    # ── 워크플로 (문장 나열 → 스텝)
    # 번호는 원문자(①) 대신 숫자 — 원문자가 아이콘 폰트로 대체돼 깨지는 환경이 있다
    _steps = [
        ("01", "시장 트렌드", "섹터 국면·수익률·검색량으로 시장 방향 진단"),
        ("02", "채널 모니터링", "8개 브랜드 배너·유튜브·블로그로 경쟁 마케팅 감지"),
        ("03", "효과 측정", "감지된 캠페인의 순매수 효과를 DiD로 검증"),
        ("04", "주간 리포트", "종합 브리핑·다음 주 액션 도출"),
        ("05", "규제 동향", "금융위 발표·법령 시행일 점검"),
    ]
    st.markdown(
        f'<div style="font-size:0.7rem;color:{FAINT};font-weight:600;letter-spacing:.06em;'
        f'margin-bottom:6px;">워크플로</div>'
        f'<div class="flow">'
        + "".join(f'<div class="flow-step"><div class="no">{n}</div>'
                  f'<div class="nm">{t}</div><div class="ds">{d}</div></div>'
                  for n, t, d in _steps)
        + '</div>', unsafe_allow_html=True)

# ──────────────────────────────────────────────
# ① 시장 트렌드
# ──────────────────────────────────────────────
with tab_trend:
    st.write("")
    section_header("STEP 1 · MONITOR", "시장 트렌드", "섹터 단계 진단·테마 수익률·검색량으로 시장이 어디로 움직이는지 파악합니다.")
    st.write("")

    sub_header("01", "진단 프레임", "테마 수명주기 4단계와 단계별 마케터 행동")

    # ── 테마 단계 진단 배너 — 단계 정의(수급·주가·검색량) + 단계별 마케터 행동
    cycle_svg = (
        '<svg viewBox="0 0 760 224" style="width:100%;max-width:920px;display:block;margin:6px auto 0;">'
        # 축 (세로 = 테마 관심도·주가)
        '<line x1="30" y1="12" x2="30" y2="118" stroke="#98A2B3" stroke-width="1.2"/>'
        '<path d="M 30 10 l -4 8 l 8 0 z" fill="#98A2B3"/>'
        '<line x1="30" y1="118" x2="744" y2="118" stroke="#98A2B3" stroke-width="1.2"/>'
        '<path d="M 746 118 l -8 -4 l 0 8 z" fill="#98A2B3"/>'
        '<text x="16" y="66" font-size="10" fill="#667085" transform="rotate(-90 16 66)" text-anchor="middle">테마 관심도</text>'
        '<text x="742" y="132" font-size="10" fill="#667085" text-anchor="end">시간</text>'
        # 단계 구분선
        '<line x1="210" y1="14" x2="210" y2="118" stroke="#E4E7EC" stroke-dasharray="4 4"/>'
        '<line x1="420" y1="14" x2="420" y2="118" stroke="#E4E7EC" stroke-dasharray="4 4"/>'
        '<line x1="560" y1="14" x2="560" y2="118" stroke="#E4E7EC" stroke-dasharray="4 4"/>'
        # 관심도·주가 곡선 — 4색 구간 (시그널 보드 진단 색과 동일)
        '<path d="M 40 108 C 100 104, 155 90, 210 70" fill="none" stroke="#6E4CA6" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 210 70 C 280 44, 350 24, 420 20" fill="none" stroke="#2E7D5B" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 420 20 C 470 18, 520 34, 560 54" fill="none" stroke="#D0342C" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 560 54 C 610 76, 680 98, 740 108" fill="none" stroke="#5B6478" stroke-width="5" stroke-linecap="round"/>'
        # 단계명
        '<text x="120" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#6E4CA6">01 태동기</text>'
        '<text x="315" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#2E7D5B">02 확산기</text>'
        '<text x="490" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#D0342C">03 과열기</text>'
        '<text x="650" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#5B6478">04 쇠퇴기</text>'
        # 단계 정의 — 수급 / 주가·검색량
        '<text x="120" y="160" text-anchor="middle" font-size="10" fill="#667085">외국인·기관 유입 · 개인 잠잠</text>'
        '<text x="120" y="174" text-anchor="middle" font-size="10" fill="#667085">주가 바닥권 · 검색량 낮음</text>'
        '<text x="315" y="160" text-anchor="middle" font-size="10" fill="#667085">개인 매수 본격 유입</text>'
        '<text x="315" y="174" text-anchor="middle" font-size="10" fill="#667085">주가 상승 · 검색량 급증</text>'
        '<text x="490" y="160" text-anchor="middle" font-size="10" fill="#667085">외국인·기관 매도 전환</text>'
        '<text x="490" y="174" text-anchor="middle" font-size="10" fill="#667085">주가 고점권 · 검색량 정점</text>'
        '<text x="650" y="160" text-anchor="middle" font-size="10" fill="#667085">매수 주체 소멸</text>'
        '<text x="650" y="174" text-anchor="middle" font-size="10" fill="#667085">주가 하락 · 검색량 감소</text>'
        # 마케터 행동 (볼드)
        '<text x="120" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">콘텐츠 기획 착수 · 소재 선점</text>'
        '<text x="120" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">관련 ETF 라인업 점검</text>'
        '<text x="315" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">광고 · 콘텐츠 집중 집행</text>'
        '<text x="315" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">푸시 상품 전면 배치</text>'
        '<text x="490" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">마케팅 수확 지속 (수요 정점)</text>'
        '<text x="490" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">적립식 · 분산 소구 병행</text>'
        '<text x="650" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">노출 최소화</text>'
        '<text x="650" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#141B2D">수급 재유입 모니터링</text>'
        "</svg>"
    )
    st.markdown(
        f'<div class="card">'
        f'<div style="font-size:0.84rem;color:{MUTED};line-height:1.7;">'
        f'테마에는 수명주기가 있고, <b style="color:{NAVY};">단계마다 마케터가 해야 할 행동이 다릅니다.</b> '
        f'아래 시그널 보드가 각 테마의 현재 단계를 매주 진단합니다.</div>'
        f"{cycle_svg}</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("02", "섹터 시그널 보드", "22개 섹터의 현재 단계 판정 — 주 1회 갱신")

    # 단계별 색·행동 — 시그널 보드와 섹터 유니버스가 같은 팔레트를 쓰도록 탭 상단에 둔다
    STAGE_META = {
        "태동기": ("#6E4CA6", "#F3EFFA", "콘텐츠 기획 착수 · 소재 선점"),
        "확산기": ("#2E7D5B", "#EAF7EF", "광고·콘텐츠 집중 집행"),
        "과열기": (RED, "#FDECEB", "수확 지속 + 적립식·분산 소구 병행"),
        "쇠퇴기": (MUTED, "#F2F4F7", "집행 축소 · 재매집 신호만 관찰"),
        "관망": (FAINT, "#F7F9FC", "판정 유보 (이력 부족)"),
    }

    # ── 섹터 시그널 보드 — 주간 배치 실데이터 (data/signal_board.json)
    board_file = Path(__file__).parent / "data" / "signal_board.json"
    if not board_file.exists():
        st.info("시그널 보드 데이터가 없습니다 — 로컬에서 `python scripts/weekly_batch.py` 실행 후 커밋하면 표시됩니다.")
    else:
        sb = json.loads(board_file.read_text())
        rows_all = sb.get("board", [])
        by_stage: dict = {}
        for r in rows_all:
            by_stage.setdefault(r.get("단계", "관망"), []).append(r)
        summary = " · ".join(
            f"{s} {len(by_stage.get(s, []))}" for s in ("태동기", "확산기", "과열기", "쇠퇴기")
        )
        if by_stage.get("관망"):
            summary += f" · 관망 {len(by_stage['관망'])}"

        def lvl_word(v):
            return f'<span style="font-size:0.72rem;color:#475467;font-weight:600;">{"강세" if v >= 0 else "약세"}</span>'

        def mom_word(v):
            return f'<span style="font-size:0.72rem;color:#475467;font-weight:600;">{"강해지는 중" if v >= 0 else "약해지는 중"}</span>'

        def signed(v, suffix=""):
            cls = "sig-pos" if v > 0 else ("sig-neg" if v < 0 else "")
            return f'<span class="{cls}">{v:+.1f}{suffix}</span>'

        def krw_line(label, v):
            """주체별 13주 순매수 한 줄 — 매수 빨강 / 매도 파랑."""
            if v is None:
                return ""
            amt = f"{v / 1e4:+,.1f}조" if abs(v) >= 1e4 else f"{v:+,}억"
            color, word = ("#D63C48", "매수") if v > 0 else ("#2A6FDB", "매도")
            return (
                f'<span style="color:{FAINT};">{label}</span> '
                f'<span style="color:{color};font-weight:600;">{amt} {word}</span>'
            )

        def eok(v):
            """억 단위 축약 — 1조 이상은 조로."""
            return f"{v / 1e4:+,.1f}조" if abs(v) >= 1e4 else f"{v:+,.0f}억"

        def flow_cell(r):
            if r.get("외국인13주억") is None and r.get("큰손13주억") is None:
                return "—"
            lines = [
                krw_line("외국인", r.get("외국인13주억")),
                krw_line("연기금", r.get("연기금13주억")),
                krw_line("개인", r.get("개인13주억")),
            ]
            return "<br>".join(l for l in lines if l) or "—"

        def smart_buy(r):
            """외국인+연기금 13주 순매수 합 — 재매집 정렬 기준."""
            return (r.get("외국인13주억") or 0) + (r.get("연기금13주억") or 0)

        def flow_inline(r):
            """수급 3주체를 한 줄로 — 세로 3줄이라 행이 과하게 높아지던 문제."""
            if r.get("외국인13주억") is None and r.get("큰손13주억") is None:
                return f'<span style="color:{FAINT};">—</span>'
            parts = []
            for nm, v in (("외", r.get("외국인13주억")), ("연", r.get("연기금13주억")),
                          ("개", r.get("개인13주억"))):
                if v is None:
                    continue
                c = RED if v > 0 else (COOL if v < 0 else FAINT)
                parts.append(f'<span style="color:{FAINT};">{nm}</span> '
                             f'<span style="color:{c};font-weight:700;">{eok(v)}</span>')
            return '<span style="white-space:nowrap;">' + '<span style="color:#D7DCE5;"> · </span>'.join(parts) + '</span>'

        def stage_rows(rows, stage, decline_order=False):
            """단계 배지를 첫 행에만 두고 나머지는 비워, 그룹이 시각적으로 묶이게 한다."""
            if decline_order:
                rows = sorted(rows, key=lambda x: -smart_buy(x))
            else:
                rows = sorted(rows, key=lambda x: -(x.get("RS모멘텀") or -99))
            col, bg, action = STAGE_META.get(stage, (MUTED, "#F2F4F7", ""))
            out = ""
            for i, r in enumerate(rows):
                has = r.get("RS수준") is not None
                # 해외 행의 수급비고는 '해외' 배지 + 수급 열의 '—'와 중복이라 생략
                note = r.get("비고") or ("" if r.get("군") == "해외" else r.get("수급비고", "")) or ""
                first = i == 0
                badge = (f'<span style="display:inline-block;font-size:0.68rem;font-weight:800;'
                         f'color:{col};background:{bg};border-radius:5px;padding:3px 9px;">{stage}</span>'
                         f'<div style="font-size:0.64rem;color:{FAINT};margin-top:4px;line-height:1.4;">{action}</div>'
                         if first else "")
                out += (
                    f'<tr style="border-top:{"1px solid " + LINE if first and i == 0 else "1px solid #F2F5F9"};">'
                    f'<td style="width:96px;vertical-align:top;padding-top:11px;">{badge}</td>'
                    f'<td><b style="font-size:0.88rem;">{r["섹터"]}</b>'
                    + (f'<span style="font-size:0.6rem;font-weight:800;color:{NAVY};'
                       f'background:{BRAND_SOFT};border-radius:4px;padding:2px 6px;'
                       f'margin-left:6px;vertical-align:middle;">해외</span>'
                       if r.get("군") == "해외" else "")
                    + f'<div style="font-size:0.68rem;color:{FAINT};">{r.get("KODEX", "")}'
                    + (f' · {note}' if note else "") + '</div></td>'
                    + (
                        f'<td class="num"><b style="font-size:0.98rem;">{signed(r["RS수준"])}</b>'
                        f'<div style="font-size:0.66rem;color:{FAINT};">{"강세" if r["RS수준"] >= 0 else "약세"}</div></td>'
                        f'<td class="num"><b style="font-size:0.98rem;">{signed(r["RS모멘텀"])}</b>'
                        f'<div style="font-size:0.66rem;color:{FAINT};">{"강해지는 중" if r["RS모멘텀"] >= 0 else "약해지는 중"}</div></td>'
                        if has else f'<td class="num" style="color:{FAINT};">—</td><td class="num" style="color:{FAINT};">—</td>'
                    )
                    + f'<td style="text-align:right;font-size:0.76rem;">{flow_inline(r)}</td></tr>'
                )
            return out

        # 헤더 1회 — 이전엔 단계마다 표를 따로 만들어 헤더가 3번 반복됐다
        TABLE_HEAD = (
            f'<table class="sig-table"><colgroup><col style="width:96px"><col>'
            f'<col style="width:104px"><col style="width:112px"><col style="width:31%"></colgroup>'
            f'<thead><tr>'
            f'<th>단계</th><th>섹터 · KODEX 상품</th>'
            f'<th class="num">RS수준</th><th class="num">RS모멘텀</th>'
            f'<th style="text-align:right;">수급 참고 · 13주 순매수</th>'
            f'</tr></thead><tbody>'
        )
        groups_html = TABLE_HEAD
        for stage in ("태동기", "확산기", "과열기"):
            rows = by_stage.get(stage, [])
            if rows:
                groups_html += stage_rows(rows, stage)
        groups_html += "</tbody></table>"

        # 단계별 개수를 칩으로 — "태동기 3 · 확산기 2" 텍스트보다 한눈에 들어온다
        _chips = ""
        for _s in ("태동기", "확산기", "과열기", "쇠퇴기", "관망"):
            _n = len(by_stage.get(_s, []))
            if not _n and _s == "관망":
                continue
            _c, _bg, _ = STAGE_META.get(_s, (MUTED, "#F2F4F7", ""))
            _chips += (f'<span style="display:inline-flex;align-items:center;gap:6px;'
                       f'font-size:0.72rem;font-weight:700;color:{_c};background:{_bg};'
                       f'border-radius:6px;padding:4px 10px;margin-right:6px;">{_s}'
                       f'<b style="font-size:0.82rem;">{_n}</b></span>')

        st.markdown(
            f'<div class="card">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'flex-wrap:wrap;gap:8px;margin-bottom:12px;">'
            f'<div>{_chips}</div>'
            f'<div style="font-size:0.68rem;color:{FAINT};font-weight:600;">'
            f'{sb.get("asof", "")} 기준 · 벤치마크 국내 {sb.get("benchmark", "KRX 300")}'
            f' · 해외 {sb.get("benchmark_해외", "—")}</div></div>'
            f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;'
            f'border-left:3px solid {BRAND};background:{BRAND_SOFT};'
            f'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:14px;">'
            f'단계는 <b style="color:{NAVY};">가격(시장 대비 상대강도)만으로</b> 판정합니다. '
            f'수급(13주 순매수)은 판정과 별개로 <b>자금이 실제로 어디로 움직였는지</b> 보여주는 보조 지표입니다.</div>'
            f"{groups_html}</div>",
            unsafe_allow_html=True,
        )

        decline = by_stage.get("쇠퇴기", []) + by_stage.get("관망", [])
        n_watch = sum(1 for r in decline if smart_buy(r) > 0)
        with st.expander(f"쇠퇴기·관망 ({len(decline)}) — 외국인·연기금이 매수 중인 재매집 후보 {n_watch}개를 상단 배치"):
            st.markdown(
                TABLE_HEAD + stage_rows(decline, "쇠퇴기", decline_order=True) + "</tbody></table>",
                unsafe_allow_html=True,
            )

        with st.expander("지표 설명 · 수치 근거"):
            st.markdown(
                f"""
##### 단계 판정 — RRG (Relative Rotation, 섹터 로테이션 표준 방법론)

- **상대강도(RS)** = 섹터 가격 ÷ KRX 300 — 시장을 이기면 오르는 값
- **RS수준** = 상대강도가 자기 26주(반년) 평균보다 몇 % 위/아래인가 → **강세/약세의 현재 위치**
- **RS모멘텀** = 상대강도의 4주 평균이 12주 평균 대비 몇 %인가 → **강해지는 중/약해지는 중의 방향**

| RS수준 | RS모멘텀 | 단계 | 뜻 |
|--------|---------|------|-----|
| − 약세 | + 강해짐 | 🟡 태동기 | 소외됐다가 돌아서는 중 |
| + 강세 | + 강해짐 | 🔴 확산기 | 주도하며 더 강해짐 |
| + 강세 | − 약해짐 | 🔵 과열기 | 아직 강자지만 꺾이기 시작 |
| − 약세 | − 약해짐 | ⚪ 쇠퇴기 | 소외가 깊어짐 |

관망 = 이력 26주 미만이거나 수집 실패로 판정 유보.

##### 수급 열 — 참고 정보이며, 판정·채점에 쓰지 않습니다

구성종목의 **최근 13주(약 1분기) 순매수 합**을 외국인·연기금·개인으로 나눠 원액 그대로 보여줍니다.

- **판정에 쓰지 않는 이유 (실측)**: 매매는 제로섬이라 기관·외국인과 개인의 순매수는 거의 정확히 반대 부호입니다 — 즉 수급이 주는 실질 정보는 "기관·외국인이 사느냐 파느냐" 하나뿐이라, 4단계 판정을 지지·반박하는 용도로는 정보량이 부족합니다. 가격 판정과의 "일치 배지"를 붙여봤으나 일치율이 3/22에 그쳤고, 시장 상대화로 보정해도 2/22로 오히려 악화되어 폐기했습니다.
- **수급의 고유 가치**: 가격이 아직 움직이지 않은 "조용한 매집"은 가격 지표에 존재하지 않는 정보입니다. 그래서 쇠퇴기 표에서만 **외국인·연기금 매수 강도가 높은 섹터(재매집 후보)를 상단에 배치**하는 데 사용합니다 (정렬 = 외국인+연기금 13주 순매수 합 내림차순).
- **13주(분기) 창을 쓰는 근거 (실측)**: 2주·4주 창은 부호가 연 10~18회 뒤집혀 판독 불가, 13주는 연 ~4회로 안정적이며, 반도체의 구조적 매도 전환도 단기 창보다 먼저·한 번에 포착했습니다.

##### 데이터 출처·수집

| 항목 | 출처 | 비고 |
|------|------|------|
| 가격 (1군 17개 섹터) | KRX 공식 섹터지수 | 코스피+코스닥 통합 |
| 가격 (2군 5개 테마) | KODEX 테마 ETF 종가 | 방산·2차전지·조선·AI전력·원자력 |
| 수급 구성종목 명부 | 1군 = KRX 섹터지수 구성종목 / 2군 = ETF PDF | 공식 공시 명부 — 자의적 선별 없음 |
| 투자자별 순매수 | KRX 정보데이터시스템 (투자자별 거래실적) | 주 1회 로컬 배치 수집 |
| 벤치마크 | KRX 300 | 코스닥 쏠림 왜곡 방지 |

##### 알아둘 점

- RRG 파라미터(26/12/4주)는 관행적 초기값이며, 과거 사이클 백테스트로 조정 예정입니다.
- 경계값 부근(RS모멘텀 ±0.5 이내 등)에서는 라벨이 주 단위로 바뀔 수 있습니다 — 라벨보다 원값을 먼저 확인하세요.
- 과열기의 대응(수확 지속 vs 소구 전환의 비중)은 데이터가 아니라 경영 판단의 영역입니다. 보드는 국면 정보와 근거까지만 제공합니다.
"""
            )
    st.write("")

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("03", "관심과 화제", "대중 검색량(수요) · 언론 언급량(화제성) — 콘텐츠 소재의 근거")

    # ── 실시간 뉴스 키워드 언급량 + 시장 트렌드 브리핑 (구글 뉴스 RSS · 실데이터)
    kw_counts, articles, news_live = load_news_mentions()
    search_deltas, search_live = load_theme_search()

    nc1, nc2 = st.columns([6, 6], gap="large")
    with nc1:
        # 테마 검색량 — 대중 관심(수요)의 측정. 네이버 데이터랩 주간 검색량.
        def naver_news_link(query: str) -> str:
            return "https://search.naver.com/search.naver?where=news&query=" + quote(query)

        names = [g for g, _ in D.THEME_SEARCH_GROUPS if g in search_deltas]
        names.sort(key=lambda n: -search_deltas[n])
        rows_html = ""
        for n in names:
            v = search_deltas[n]
            s_cls = "kw-rise" if v >= 0 else "kw-fall"
            rows_html += (
                f'<a class="kw-link" href="{naver_news_link(n)}" target="_blank">'
                f'<div class="kw-row"><span class="kw-name">{n} ↗</span>'
                f'<span class="kw-badge {s_cls}">검색 {v:+.1f}%</span></div></a>'
            )
        live_tag = "데이터랩 실데이터" if search_live else "데모 — NAVER API 키 설정 시 실데이터"
        st.markdown(
            f'<div class="card"><div class="card-title">테마 검색량 (주간) '
            f'<span style="font-size:0.7rem;color:{FAINT};font-weight:600;">네이버 데이터랩 · 전주 대비 증감 · {live_tag}</span></div>'
            f"{rows_html}"
            f'<div style="font-size:0.7rem;color:{GRAY};margin-top:8px;">'
            f'대중이 실제로 검색한 양의 변화 — 관심(수요)의 측정치입니다. 클릭 시 관련 기사로 이동</div></div>',
            unsafe_allow_html=True,
        )
    with nc2:
        # 금주 언론 이슈 — 헤드라인에서 많이 다뤄진 주제 순 (화제성 기준)
        pat_map = dict(getattr(D, "NEWS_KW_PATTERNS", []))
        issue_blocks = ""
        shown = set()  # 여러 키워드에 걸치는 기사는 첫 블록에만 노출
        for k in kw_counts[:4]:
            pat = pat_map.get(k["키워드"])
            matched = [a for a in articles if pat and re.search(pat, a["title"])]
            hits = [a for a in matched if a["title"] not in shown][:2]
            if not hits:  # 전부 앞 블록에 노출된 경우 대표 기사 1건은 유지
                hits = matched[:1]
            shown.update(a["title"] for a in hits)
            links = "".join(
                f'<a href="{a["link"]}" target="_blank" style="display:block;font-size:0.79rem;'
                f'color:#374151;text-decoration:none;padding:2px 0;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;">– {a["title"]}</a>'
                for a in hits
            )
            issue_blocks += (
                f'<div style="padding:9px 0;border-bottom:1px solid #F0F2F7;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">'
                f'<span style="font-size:0.86rem;font-weight:800;color:{INK};">{k["키워드"]}</span>'
                f'<span class="kw-badge" style="background:#F2F4F7;color:#475467;">기사 {k["언급량"]}건</span></div>'
                f"{links}</div>"
            )
        if not issue_blocks:
            issue_blocks = f'<div style="font-size:0.8rem;color:{GRAY};">뉴스 데이터를 불러오지 못했습니다.</div>'
        news_tag = "구글 뉴스 실시간" if news_live else "수집 실패"
        st.markdown(
            f'<div class="card"><div class="card-title">금주 언론 이슈 '
            f'<span style="font-size:0.7rem;color:{FAINT};font-weight:600;">ETF 헤드라인 {len(articles)}건 · 언급 많은 순 · {news_tag}</span></div>'
            f"{issue_blocks}"
            f'<div style="font-size:0.7rem;color:{GRAY};margin-top:8px;">'
            f'이번 주 언론이 가장 많이 다룬 주제 순 — 화제성의 측정치입니다. 콘텐츠 소재로 활용</div></div>',
            unsafe_allow_html=True,
        )
        if articles:
            with st.expander(f"콘텐츠 소재함 — 전체 기사 보기 ({len(articles)}건)"):
                st.markdown("\n".join(f"- [{a['title']}]({a['link']})" for a in articles))
    st.write("")

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("04", "금주 성과와 수급", "섹터별 실제 주간 수익률과 외국인·연기금 자금 흐름")

    # 섹터별 실제 주간 수익률 · 주간 수급 — 주간 배치 실데이터 (data/signal_board.json)
    try:
        _sb_wk = json.loads(board_file.read_text()) if board_file.exists() else {}
    except Exception:
        _sb_wk = {}
    wk_rows = [r for r in _sb_wk.get("board", []) if r.get("주간수익률") is not None]
    wk_range = _sb_wk.get("주간구간", "")
    wk_bench = _sb_wk.get("벤치주간수익률")

    t1, t2 = st.columns([6, 6], gap="large")
    with t1:
        if wk_rows:
            srt = sorted(wk_rows, key=lambda r: r["주간수익률"])
            vals = [r["주간수익률"] for r in srt]
            fig_th = go.Figure(
                go.Bar(x=vals, y=[r["섹터"] for r in srt], orientation="h",
                       marker_color=[RED if v >= 0 else COOL for v in vals],
                       text=[f"{v:+.1f}%" for v in vals], textposition="outside",
                       cliponaxis=False,
                       hovertemplate="%{y}<br>주간 수익률 %{x:.2f}%<extra></extra>")
            )
            # 높이를 섹터 수에 비례시킨다 — 560px 고정이라 섹터가 22→26개로 늘자
            # 막대가 눌리면서 제목·상단 막대가 잘렸다 (③ 탭 차트와 같은 방식)
            _h_th = max(420, len(srt) * BAR_ROW_PX + CHART_CHROME_PX)
            fig_th = base_layout(fig_th, height=_h_th)
            fig_th.update_layout(
                title=dict(
                    text=f"섹터별 주간 수익률  <span style='font-size:12px;color:#98A2B3'>KRX 실데이터 · {wk_range}</span>",
                    font=dict(size=15)),
                margin=dict(l=8, r=8, t=56, b=8))
            fig_th.update_xaxes(ticksuffix="%", range=[min(vals) * 1.35 - 0.3, max(vals) * 1.3 + 0.3])
            st.plotly_chart(fig_th, use_container_width=True)
            if wk_bench is not None:
                st.caption(f"해석 기준선 — 같은 주간 KRX 300 {wk_bench:+.1f}% (시그널 보드와 동일 벤치마크)")
        else:
            st.info("주간 수익률 데이터가 없습니다 — `python scripts/weekly_batch.py` 재실행 후 커밋하면 표시됩니다.")
    with t2:
        f_rows = [r for r in wk_rows if r.get("외국인1주억") is not None]
        if f_rows:
            xs = [r["주간수익률"] for r in f_rows]
            ys = [(r.get("외국인1주억") or 0) + (r.get("연기금1주억") or 0) for r in f_rows]
            fig_sc = go.Figure(
                go.Scatter(
                    x=xs, y=ys, mode="markers+text", text=[r["섹터"] for r in f_rows],
                    textposition="top center", textfont=dict(size=11, color="#4B5468"),
                    marker=dict(size=13, color=[RED if v > 0 else COOL for v in ys],
                                opacity=0.8, line=dict(width=1, color="white")),
                    hovertemplate="<b>%{text}</b><br>주간 수익률 %{x:.2f}%<br>외국인+연기금 주간 순매수 %{y:,.0f}억<extra></extra>",
                )
            )
            # 좌측 막대차트와 높이를 맞춰 두 열이 나란히 끝나게 한다
            _h_sc = max(420, len(wk_rows) * BAR_ROW_PX + CHART_CHROME_PX)
            fig_sc = base_layout(fig_sc, height=_h_sc)
            fig_sc.update_layout(
                title=dict(text="주간 수익률 × 수급 맵  <span style='font-size:12px;color:#98A2B3'>붉은색 = 외국인·연기금 순매수, 파란색 = 순매도</span>", font=dict(size=15)),
                xaxis_title="주간 수익률(%)", yaxis_title="외국인+연기금 주간 순매수(억원)",
                margin=dict(l=8, r=8, t=56, b=8),
            )
            fig_sc.update_xaxes(showgrid=True, gridcolor="#F0F2F7", zeroline=True, zerolinecolor="#D9DEE9")
            fig_sc.update_yaxes(zeroline=True, zerolinecolor="#D9DEE9")
            st.plotly_chart(fig_sc, use_container_width=True)
        elif wk_rows:
            st.info("주간 수급 데이터가 없습니다 — 배치 재실행 후 표시됩니다.")

    # ══════════ 섹터 유니버스 — 국면 판정의 근거가 된 종목 묶음 ══════════
    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("05", "섹터 유니버스", "위 판정이 어떤 종목 묶음을 근거로 했는지 확인")
    st.markdown(
        f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;margin-bottom:12px;">'
        f'KRX 섹터지수는 <b>지수 구성종목</b>, 테마는 <b>KODEX ETF 구성내역(PDF·비중 포함)</b> 기준입니다 — '
        f'자의적 종목 선별 없이 공식 공시 명부를 그대로 사용합니다.</div>',
        unsafe_allow_html=True)
    _uni_data = load_sector_universe()
    _uni_secs = _uni_data.get("sectors", [])
    if _uni_secs:
        _by_name = {s["섹터"]: s for s in _uni_secs}
        _order = [r["섹터"] for r in rows_all if r["섹터"] in _by_name] or list(_by_name)
        u1, u2 = st.columns([4, 8], gap="large")
        with u1:
            pick_sec = st.selectbox("섹터 선택", _order, key="uni_pick")
            s = _by_name[pick_sec]
            stg = next((r.get("단계", "") for r in rows_all if r["섹터"] == pick_sec), "")
            _sc, _sbg, _ = STAGE_META.get(stg, (NAVY, BRAND_SOFT, ""))
            st.markdown(
                f'<div class="card" style="padding:12px 15px;border-left:3px solid {_sc};">'
                f'<div style="font-size:0.68rem;color:{FAINT};font-weight:700;letter-spacing:.06em;">현재 국면</div>'
                f'<div style="font-size:1.1rem;font-weight:800;color:{_sc};margin-top:2px;">{stg or "—"}</div>'
                f'<div style="font-size:0.74rem;color:{MUTED};margin-top:9px;line-height:1.6;">'
                f'{s.get("기준","")}<br><b style="color:{INK};">{s.get("종목수",0)}종목</b> · {s.get("군","")}</div></div>',
                unsafe_allow_html=True)
        with u2:
            items = s.get("종목", [])
            if items:
                has_w = any("비중" in it for it in items)
                if has_w:
                    rows_u = "".join(
                        f'<div class="kw-row"><span class="kw-name">{it["종목명"]}</span>'
                        f'<span style="flex:1;margin:0 10px;height:6px;background:#EEF1F6;border-radius:3px;'
                        f'overflow:hidden;display:inline-block;"><span style="display:block;height:100%;'
                        f'width:{min(100, it.get("비중", 0) * 3):.0f}%;background:{NAVY};"></span></span>'
                        f'<span class="kw-badge" style="background:#F2F4F7;color:#475467;">'
                        f'{it.get("비중", 0):.1f}%</span></div>'
                        for it in items[:20])
                    cap = "KODEX ETF 구성내역(PDF) · 비중 내림차순 · 막대는 비중 상대 길이"
                else:
                    # 해외 ETF는 KRX가 비중도 티커도 제공하지 않아 종목명만 남는다
                    cells = "".join(
                        f'<span style="display:inline-block;font-size:0.78rem;color:{INK};'
                        f'background:#F5F6FA;border:1px solid #EAEDF3;border-radius:6px;'
                        f'padding:4px 10px;margin:0 6px 6px 0;">{it["종목명"]}'
                        + (f'<span style="color:{FAINT};font-size:0.68rem;margin-left:5px;">'
                           f'{it["티커"]}</span>' if it.get("티커") else "")
                        + '</span>'
                        for it in items[:40])
                    rows_u = f'<div style="padding:4px 0;">{cells}</div>'
                    cap = ("해외 ETF 구성종목 · KRX가 해외 보유분의 비중을 제공하지 않아 종목명만 표시"
                           if s.get("군") == "해외" else
                           "KRX 섹터지수 구성종목 · 지수는 비중을 공개하지 않아 종목명만 표시")
                st.markdown(f'<div class="card" style="padding:10px 16px;">{rows_u}</div>',
                            unsafe_allow_html=True)
                st.caption(cap)
            else:
                st.info(s.get("비고", "구성종목을 수집하지 못했습니다."))
        st.caption(f"수집 {_uni_data.get('asof','')} · 주간 배치 `python scripts/sector_universe.py`")
    else:
        st.info("섹터 유니버스 데이터가 없습니다 — 로컬에서 `python scripts/sector_universe.py` 실행 후 커밋하면 표시됩니다.")


# ──────────────────────────────────────────────
# ② 채널 모니터링 — 캠페인 보드(배너 배치) + 유튜브·블로그·뉴스
# ──────────────────────────────────────────────
with tab_channel:
    st.write("")
    section_header("STEP 2 · MONITOR", "채널 모니터링", "경쟁 운용사가 지금 무엇을 밀고 있는지 — 공식 홈페이지 배너·유튜브·블로그·뉴스를 수집합니다. 여기서 감지된 마케팅이 ③ 효과 측정의 입력이 됩니다.")
    st.write("")

    blogs = load_blogs()
    _week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()

    # ── 경쟁사 캠페인 보드 — 주간 배치(data/channel_board.json) + RSS 실시간
    ch_file = Path(__file__).parent / "data" / "channel_board.json"
    try:
        ch_data = json.loads(ch_file.read_text()) if ch_file.exists() else {}
    except Exception:
        ch_data = {}
    ch_brands = {b["브랜드"]: b for b in ch_data.get("brands", [])}

    def brand_themes(brand: str) -> str:
        """배너·영상·블로그 제목에서 테마 키워드 매칭 (뉴스 소재함과 동일한 사전)."""
        texts = [x["제목"] for x in ch_brands.get(brand, {}).get("배너", [])]
        texts += [v["title"] for v in youtube.get(brand, [])[:5]]
        texts += [p["title"] for p in blogs.get(brand, [])[:5]]
        found = []
        for kw, pat in getattr(D, "NEWS_KW_PATTERNS", []):
            if any(re.search(pat, t) for t in texts):
                found.append(kw)
            if len(found) >= 3:
                break
        return " · ".join(found) if found else "—"

    NEW_BADGE = ('<span style="font-size:0.6rem;font-weight:800;color:#fff;background:#D63C48;'
                 'border-radius:4px;padding:1px 5px;margin-left:6px;vertical-align:middle;">NEW</span>')

    def feed_row(chip: str, title: str, right: str, link: str, badge: str = "") -> str:
        """소스 피드 한 줄 — 좌측 출처 칩 + 제목 + 우측 정보 (2번째 이미지 스타일)."""
        return (
            f'<a class="kw-link" href="{link}" target="_blank"><div class="kw-row" style="align-items:center;">'
            f'<span style="font-size:0.7rem;font-weight:700;color:#475467;background:#F2F4F7;'
            f'border-radius:5px;padding:2px 8px;margin-right:10px;white-space:nowrap;'
            f'display:inline-block;min-width:80px;text-align:center;">{chip}</span>'
            f'<span class="kw-name" style="flex:1;font-size:0.84rem;font-weight:600;">{title}</span>{badge}'
            f'<span style="font-size:0.72rem;color:{GRAY};white-space:nowrap;margin-left:10px;">{right}</span>'
            f'</div></a>'
        )

    grp_amc, grp_sec, grp_bank = st.tabs(["운용사", "증권 (판매채널)", "은행 (판매채널)"])

    partners = load_partners()

    def partner_group(group: str, note: str):
        """증권/은행 서브탭 본문 — 회사별 채널 요약 + 통합 피드 (유튜브·블로그 시간순)."""
        rows = [c for c in D.PARTNER_CHANNELS if c["그룹"] == group]
        feed = [f for f in partners if f["그룹"] == group]
        # 회사별 요약 카드
        cols = st.columns(len(rows), gap="small")
        for col, ch in zip(cols, rows):
            n_wk = sum(1 for f in feed if f["회사"] == ch["회사"] and f["date"] >= _week_ago)
            blog_txt = "블로그 ○" if ch["blog"] else "블로그 미운영"
            col.markdown(
                f'<div class="card" style="padding:10px 12px;text-align:center;">'
                f'<div style="font-weight:800;font-size:0.85rem;">{ch["회사"]}</div>'
                f'<div style="font-size:0.72rem;color:{GRAY};margin-top:2px;">유튜브 ○ · {blog_txt}</div>'
                f'<div style="font-size:0.78rem;color:#475467;margin-top:4px;">이번 주 게시물 <b>{n_wk}</b>건</div></div>',
                unsafe_allow_html=True,
            )
        st.write("")
        etf_feed = [f for f in feed if re.search(D.ETF_CONTENT_PAT, f["title"])]
        only_etf = st.toggle("ETF 관련 콘텐츠만 보기", value=True, key=f"etf_only_{group}",
                             help="제목에 ETF·커버드콜·월배당·연금투자·IRP·ISA가 포함된 게시물만 표시")
        shown = etf_feed if only_etf else feed
        # ETF 노출 비중 = 판매채널이 ETF를 얼마나 미는지의 지표
        share = f"{len(etf_feed)}/{len(feed)}" if feed else "0/0"
        st.caption(f"수집 {len(feed)}건 중 ETF 관련 <b>{len(etf_feed)}건</b> ({share}) — {group} 채널의 ETF 노출 비중입니다."
                   if feed else "수집된 게시물이 없습니다.", unsafe_allow_html=True)
        if shown:
            items = "".join(
                f'<a class="kw-link" href="{f["link"]}" target="_blank"><div class="kw-row">'
                f'<span style="font-size:0.7rem;font-weight:700;color:#475467;background:#F2F4F7;'
                f'border-radius:5px;padding:2px 7px;margin-right:8px;white-space:nowrap;">{f["회사"]} · {f["소스"]}</span>'
                f'<span class="kw-name" style="flex:1;font-size:0.83rem;font-weight:600;">{f["title"][:56]}</span>'
                f'<span style="font-size:0.72rem;color:{GRAY};white-space:nowrap;">{f["date"]}</span>'
                f'</div></a>'
                for f in shown[:25]
            )
            st.markdown(f'<div class="card" style="padding:8px 16px;">{items}</div>', unsafe_allow_html=True)
        elif only_etf and feed:
            st.info(f"최근 수집분에 ETF 관련 게시물이 없습니다 — {group} 채널은 지금 ETF를 거의 노출하지 않는다는 신호입니다. "
                    "이 수치가 올라가는 시점이 판매채널로의 ETF 확산·제휴 징후입니다.\n\n"
                    "토글을 끄면 전체 콘텐츠를 볼 수 있습니다.")
        else:
            st.info("수집된 게시물이 없습니다.")
        st.caption(note)

    with grp_sec:
        st.write("")
        partner_group("증권", "유튜브 채널 RSS + 네이버 블로그 RSS 실시간 수집 (30분 캐시) · 토스증권·한국투자증권은 네이버 블로그 미운영으로 유튜브만 수집")
    with grp_bank:
        st.write("")
        partner_group("은행", "유튜브 채널 RSS + 네이버 블로그 RSS 실시간 수집 (30분 캐시) · 신한은행은 네이버 블로그 미운영으로 유튜브만 수집 · 은행 ETF 콘텐츠는 주로 퇴직연금(IRP) 맥락에서 등장")

    with grp_amc:
        st.write("")
        # ── ① 공식 홈페이지 — 메인 배너 (브랜드별 1행, 우측=콘텐츠 테마)
        sub_header("01", "공식 홈페이지 — 메인 배너", "브랜드별 메인 영역 노출 · 주 1회 배치 수집")
        st.markdown(
            f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;'
            f'border-left:3px solid {BRAND};background:{BRAND_SOFT};'
            f'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:12px;">'
            f'각 운용사 홈 <b>메인 영역의 첫 번째 노출</b>입니다. 우측은 그것이 '
            f'<b>무엇을 주목하는지</b> — 상품명이 있으면 상품명, 없으면 테마나 카테고리입니다. '
            f'링크는 모두 <b>해당 운용사 공식 홈페이지</b>로 연결됩니다. '
            f'<span style="color:{RED};font-weight:700;">NEW</span> = 전주에 없던 배너.</div>',
            unsafe_allow_html=True,
        )
        if ch_brands:
            hp_rows = ""
            for brand in D.ISSUERS:
                info = ch_brands.get(brand, {})
                banners = info.get("배너", [])
                if banners:
                    b = banners[0]
                    _focus = D.banner_focus(b["제목"])
                    _right = (f'<span style="font-size:0.78rem;font-weight:700;color:{NAVY};'
                              f'white-space:nowrap;">{_focus}</span>' if _focus else
                              f'<span style="font-size:0.74rem;color:{FAINT};">—</span>')
                    hp_rows += feed_row(brand, b["제목"][:52], _right,
                                        info.get("홈", "#"), NEW_BADGE if b.get("NEW") else "")
                else:
                    hp_rows += feed_row(
                        brand, f'<span style="color:{GRAY};">{info.get("비고", "수집된 배너 없음")}</span>',
                        "", info.get("홈", "#"))
            st.markdown(f'<div class="card" style="padding:8px 16px;">{hp_rows}</div>', unsafe_allow_html=True)

            with st.expander("브랜드별 전체 배너 보기"):
                bcols = st.columns(2, gap="large")
                for i, brand in enumerate(D.ISSUERS):
                    banners = ch_brands.get(brand, {}).get("배너", [])
                    items = "".join(
                        f'<a href="{b["링크"]}" target="_blank" style="display:block;font-size:0.8rem;color:#374151;'
                        f'text-decoration:none;padding:3px 0;border-bottom:1px solid #F5F6FA;">'
                        + ('<span style="color:#D63C48;font-weight:800;">NEW </span>' if b.get("NEW") else "")
                        + f'{b["제목"][:52]}</a>'
                        for b in banners
                    ) or f'<div style="font-size:0.75rem;color:{GRAY};">수집된 배너 없음</div>'
                    bcols[i % 2].markdown(
                        f'<div style="margin-bottom:14px;"><div style="font-weight:800;font-size:0.88rem;margin-bottom:2px;">{brand}</div>{items}</div>',
                        unsafe_allow_html=True,
                    )
            _ord = {b: ch_brands.get(b, {}).get("순서근거", "-") for b in D.ISSUERS}
            _n_rank = sum(1 for v in _ord.values() if v == "운용사 지정 우선순위")
            st.caption(
                f'공식 홈페이지 배너 주간 배치 수집 ({ch_data.get("asof", "")}) · '
                f'운용사가 매긴 실제 순위를 제공하는 곳은 {_n_rank}/{len(D.ISSUERS)}개사뿐이라 '
                f'"첫 배너 = 최우선"이라고 단정할 수 없습니다 — 슬롯 점유 수·동시 집행 채널 수는 '
                f'수집해두고 ③ 효과 측정의 캠페인 판정에만 사용합니다.')
        else:
            st.info("배너 데이터가 없습니다 — 로컬에서 `python scripts/channel_batch.py` 실행 후 커밋하면 표시됩니다.")

        # ── ② 진행 중 이벤트 — 기간이 명시된 실제 캠페인
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        _ev_brands = [(b, ch_brands[b]["이벤트목록"]) for b in D.ISSUERS
                      if ch_brands.get(b, {}).get("이벤트목록")]
        _n_live = sum(1 for _, evs in _ev_brands for e in evs if e.get("상태") == "진행중")
        sub_header("02", "진행 중 이벤트",
                   f"기간이 명시된 실제 캠페인 · 진행 중 {_n_live}건")
        st.markdown(
            f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;'
            f'border-left:3px solid {BRAND};background:{BRAND_SOFT};'
            f'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:12px;">'
            f'01이 <b>지금 무엇을 걸어놨는지</b>를 본다면, 여기서는 그 캠페인이 '
            f'<b>언제 시작해 언제 끝나는지</b>를 봅니다. 집행 기간이 명시돼 있어 '
            f'③ 효과 측정에서 개입 시점을 정의하는 데 가장 적합한 신호입니다. '
            f'이벤트 보드를 파싱할 수 있는 곳은 KODEX·TIGER 2개사입니다.</div>', unsafe_allow_html=True)
        if _ev_brands:
            _today_iso = dt.date.today().isoformat()
            for _b, _evs in _ev_brands:
                _live = [e for e in _evs if e.get("상태") == "진행중"]
                _rows = ""
                for e in sorted(_live, key=lambda x: x.get("종료") or "9999")[:8]:
                    _end = e.get("종료") or ""
                    _left = ""
                    if _end >= _today_iso:
                        _d = (dt.date.fromisoformat(_end) - dt.date.today()).days
                        _left = (f'<span style="color:{RED};font-weight:700;">D-{_d}</span>'
                                 if _d <= 14 else f'<span style="color:{MUTED};">D-{_d}</span>')
                    _rows += (
                        f'<a class="kw-link" href="{e["링크"]}" target="_blank">'
                        f'<div class="kw-row" style="align-items:center;">'
                        f'<span class="kw-name" style="flex:1;font-size:0.83rem;font-weight:600;">'
                        f'{e["제목"]}</span>'
                        f'<span style="font-size:0.72rem;color:{FAINT};white-space:nowrap;'
                        f'margin:0 10px;">{e.get("시작","")} ~ {_end}</span>'
                        f'<span style="font-size:0.72rem;white-space:nowrap;min-width:44px;'
                        f'text-align:right;">{_left}</span></div></a>')
                st.markdown(
                    f'<div class="card" style="padding:8px 16px;margin-bottom:12px;">'
                    f'<div style="font-size:0.8rem;font-weight:800;color:{INK};padding:4px 0;">'
                    f'{_b} <span style="font-size:0.7rem;color:{FAINT};font-weight:600;">'
                    f'진행 중 {len(_live)}건 / 수집 {len(_evs)}건</span></div>'
                    f'{_rows}</div>', unsafe_allow_html=True)
            st.caption("운용사 이벤트 보드 주간 배치 수집 · D-n은 종료까지 남은 일수 (14일 이내 강조)")
        else:
            st.info("이벤트 데이터가 없습니다 — `python scripts/channel_batch.py` 실행 후 커밋하면 표시됩니다.")

        # 개별 이벤트까지는 못 긁지만 이벤트 메뉴는 운영하는 브랜드 — 수동 확인용 링크
        _ev_menu = [(b, ch_brands[b]["이벤트"]) for b in D.ISSUERS
                    if ch_brands.get(b, {}).get("이벤트")
                    and not ch_brands.get(b, {}).get("이벤트목록")]
        if _ev_menu:
            _chips = "".join(
                f'<a href="{e["링크"]}" target="_blank" style="text-decoration:none;'
                f'font-size:0.75rem;color:{MUTED};background:#F2F4F7;border:1px solid {LINE};'
                f'border-radius:20px;padding:4px 11px;margin:0 6px 6px 0;display:inline-block;">'
                f'<b style="color:{INK};">{b}</b> · {e["라벨"][:10]} ↗</a>'
                for b, e in _ev_menu)
            st.markdown(
                f'<div style="margin-top:14px;"><div style="font-size:0.72rem;color:{FAINT};'
                f'margin-bottom:6px;">이벤트 메뉴는 있으나 목록 자동 수집이 안 되는 브랜드 '
                f'({len(_ev_menu)}개) — 링크로 직접 확인</div>{_chips}</div>',
                unsafe_allow_html=True)

        # ── ③ 공식 유튜브 — 최신 영상 (썸네일 그리드)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        sub_header("03", "공식 유튜브 — 최신 영상", "8개 브랜드 채널 RSS 실시간 · 브랜드별 최신 1건")

        def yt_video_card(v: dict) -> str:
            views = f"{v['views']:,}회" if v["views"] else "조회수 비공개"
            return (
                f'<div class="yt-card"><a class="yt-real-thumb" href="{v["url"]}" target="_blank">'
                f'<img src="{v["thumbnail"]}" alt="thumbnail" loading="lazy">'
                f'<span class="yt-brand-chip">{v["brand"]}</span></a>'
                f'<div class="yt-body"><a class="yt-title" href="{v["url"]}" target="_blank">{v["title"]}</a>'
                f'<div class="yt-meta">{views} · {v["published"]}</div></div></div>'
            )

        latest = [vids[0] for vids in youtube.values() if vids]
        if latest:
            for row_start in range(0, len(latest), 4):
                cols = st.columns(4, gap="medium")
                for col, v in zip(cols, latest[row_start : row_start + 4]):
                    col.markdown(yt_video_card(v), unsafe_allow_html=True)
                st.write("")
            all_videos = [v for vids in youtube.values() for v in vids]
            top_view = sorted(all_videos, key=lambda v: -v["views"])[:8]
            with st.expander("조회수 TOP 8 전체 보기"):
                for row_start in range(0, len(top_view), 4):
                    cols = st.columns(4, gap="medium")
                    for col, v in zip(cols, top_view[row_start : row_start + 4]):
                        col.markdown(yt_video_card(v), unsafe_allow_html=True)
            _yt_fail = getattr(D, "YOUTUBE_STATUS", {})
            if _yt_fail:
                st.caption(
                    "⚠ 수집 실패 " + ", ".join(f"{b}({e.split(':')[0]})" for b, e in _yt_fail.items())
                    + " — 유튜브 RSS 일시 제한입니다. 직전 성공분을 표시 중이며 잠시 후 자동 복구됩니다.")
            st.caption(f"유튜브 채널 RSS 실시간 수집 (30분 캐시) · {len(latest)}/{len(D.ISSUERS)}개 브랜드 · "
                       "API 키 없이 동작, YOUTUBE_API_KEY 설정 시 좋아요·댓글 확장 가능")
        else:
            st.info("유튜브 수집에 실패했습니다 — RSS 일시 제한일 수 있습니다. "
                    "잠시 후 새로고침하면 복구됩니다.")

        # ── ③ 공식 블로그 — 최신 글 (브랜드별 묶음)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        sub_header("04", "공식 블로그 — 최신 글", "브랜드별 최신 4건 · 네이버 블로그 RSS 실시간")
        if any(blogs.values()):
            bcols = st.columns(2, gap="large")
            for i, brand in enumerate(D.ISSUERS):
                posts = blogs.get(brand, [])[:4]
                items = "".join(
                    f'<a class="kw-link" href="{p["link"]}" target="_blank"><div class="kw-row" style="align-items:center;">'
                    f'<span class="kw-name" style="flex:1;font-size:0.82rem;font-weight:600;">{p["title"][:44]}</span>'
                    f'<span style="font-size:0.72rem;color:{GRAY};white-space:nowrap;margin-left:10px;">{p["date"]}</span>'
                    f'</div></a>'
                    for p in posts
                ) or f'<div style="font-size:0.75rem;color:{GRAY};padding:4px 0;">수집 실패 또는 게시물 없음</div>'
                bcols[i % 2].markdown(
                    f'<div class="card" style="padding:10px 16px;margin-bottom:14px;">'
                    f'<div class="card-title" style="margin-bottom:2px;">{brand}</div>{items}</div>',
                    unsafe_allow_html=True,
                )
            st.caption("네이버 블로그 RSS 실시간 수집 (30분 캐시) · 브랜드별 최신순 · KODEX는 자체 블로그(samsungfundblog.com)")
        else:
            st.info("블로그 수집에 실패했습니다. 네트워크 상태를 확인해주세요.")

        # ── ④ 운용사 뉴스 이슈 (외부 언론)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        _inews = load_issuer_news()
        _in_fail = getattr(D, "ISSUER_NEWS_STATUS", {})
        _n_art = sum(len(v) for v in _inews.values())
        sub_header("05", "운용사 뉴스 이슈",
                   f"외부 언론이 다룬 브랜드 이슈 · 구글 뉴스 실시간 {_n_art}건")

        BRAND_ACCENT = {
            "KODEX": BRAND, "TIGER": "#E88D2A", "ACE": "#C0392B", "SOL": "#2E86C1",
            "HANARO": "#27AE60", "RISE": "#C89312", "PLUS": "#D9480F",
            "TIMEFOLIO": "#5B6478",
        }

        def issuer_news_card(issuer: str) -> str:
            arts = _inews.get(issuer, [])
            acc = BRAND_ACCENT.get(issuer, MUTED)
            if not arts:
                body = (f'<div style="font-size:0.76rem;color:{FAINT};padding:10px 0;">'
                        f'{"수집 실패" if issuer in _in_fail else "최근 기사 없음"}</div>')
            else:
                body = "".join(
                    f'<a href="{a["url"]}" target="_blank" style="display:block;'
                    f'text-decoration:none;padding:7px 0;'
                    f'border-top:{"1px solid " + LINE if i else "none"};">'
                    f'<div style="font-size:0.8rem;font-weight:600;color:{INK};'
                    f'line-height:1.45;">{a["title"][:60]}</div>'
                    f'<div style="font-size:0.68rem;color:{FAINT};margin-top:3px;">'
                    f'{a["source"]}{" · " + a["date"] if a["date"] else ""}</div></a>'
                    for i, a in enumerate(arts[:3]))
            return (
                f'<div class="card" style="padding:12px 16px;height:100%;'
                f'border-top:3px solid {acc};">'
                f'<div style="font-size:0.78rem;font-weight:800;color:{acc};'
                f'letter-spacing:.04em;margin-bottom:6px;">{issuer}</div>'
                f'{body}</div>')

        for row_start in range(0, len(D.ISSUERS), 4):
            row_cols = st.columns(4, gap="medium")
            for col, issuer in zip(row_cols, D.ISSUERS[row_start : row_start + 4]):
                col.markdown(issuer_news_card(issuer), unsafe_allow_html=True)
            st.write("")
        if _in_fail:
            st.caption("⚠ 수집 실패 " + ", ".join(_in_fail)
                       + " — 구글 뉴스 일시 제한입니다. 잠시 후 자동 복구됩니다.")
        st.caption("구글 뉴스 RSS 실시간 수집 (30분 캐시) · 브랜드별 최신 3건 · "
                   "동음이의어(SOL·PLUS 등)를 피하려고 운용사명을 함께 검색합니다.")

        # ── ⑤ 브랜드 검색량 (캠페인 → 관심 반응 확인)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        live_badge = "실데이터" if datalab_live else "데모 — NAVER_CLIENT_ID/SECRET 설정 시 실데이터"
        sub_header("06", "브랜드 검색량 트렌드",
                   f"위 캠페인·콘텐츠가 실제 관심으로 이어졌는지 확인 · {live_badge}")
        fig_dl = go.Figure()
        palette = {
            "KODEX": NAVY, "TIGER": "#E88D2A", "ACE": "#C0392B", "SOL": "#2E86C1",
            "HANARO": "#27AE60", "RISE": "#C89312", "PLUS": "#D9480F", "TIMEFOLIO": "#7D8597",
        }
        for g in D.DATALAB_GROUPS:
            sub = datalab_df[datalab_df["group"] == g]
            fig_dl.add_trace(go.Scatter(
                x=sub["date"], y=sub["ratio"], name=g, mode="lines",
                line=dict(color=palette.get(g, "#888"), width=2.6 if g == "KODEX" else 1.6),
            ))
        fig_dl = base_layout(fig_dl, height=320)
        fig_dl.update_layout(yaxis_title="검색량 지수", legend=dict(orientation="h"))
        st.plotly_chart(fig_dl, use_container_width=True)
        st.caption("네이버 데이터랩 주간 검색량 · 8개 브랜드 · KODEX 앵커로 2개 요청 배율 보정 · 브랜드명 오염이 심한 SOL·PLUS 등은 'ETF' 한정 키워드 사용")

# ──────────────────────────────────────────────
# ③ 마케팅 효과 측정 — DiD (KODEX 중심 재설계)
# ──────────────────────────────────────────────
with tab_did:
    st.write("")
    section_header(
        "STEP 3 · MEASURE",
        "마케팅 효과 측정 — DiD 인과분석",
        "②에서 실제로 감지된 마케팅만 분석 대상입니다. 개입 시점(집행 주차)을 기준으로 "
        "처치군 KODEX ETF와 동일 테마 경쟁 ETF 평균을 비교해 시장효과를 제거합니다.",
    )
    st.write("")

    # ── 마케팅 이벤트 탐지 — 채널 수집물(배너·유튜브·블로그)이 지목한 ETF = 처치
    events, _campaigns_dedup = kodex_campaigns(ch_data, youtube, blogs, netbuy_df)
    # 같은 ETF를 여러 채널에 집행하면 채널 수만큼 잡히지만, 순매수 시계열은 하나뿐이라
    # DiD는 상품당 한 번이면 된다. 감지 내역은 아래 목록에 그대로 남긴다.
    campaigns_raw = [e for e in events if e["유형"] == "캠페인"]
    campaigns = _campaigns_dedup
    others = [e for e in events if e["유형"] != "캠페인"]
    usable = [e for e in campaigns if e["분석가능"]]

    CH_ICON = {"홈페이지": "#6B4FBB", "유튜브": "#C2333F", "블로그": "#1E7A55",
               "이벤트": BRAND}

    def ev_row(e: dict, dim: bool = False) -> str:
        dot = CH_ICON.get(e["채널"], "#98A2B3")
        if dim:
            right = f'<span style="font-size:0.68rem;color:{GRAY};">{e["유형"]} · DiD 제외</span>'
        else:
            right = ('<span style="font-size:0.68rem;font-weight:700;color:#1E7A55;">분석 가능</span>'
                     if e["분석가능"] else
                     f'<span style="font-size:0.68rem;color:{GRAY};">순매수 미연동</span>')
        name_color = GRAY if dim else INK
        return (
            f'<a class="kw-link" href="{e["링크"]}" target="_blank"><div class="kw-row" style="align-items:center;">'
            f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{dot};margin-right:9px;"></span>'
            f'<span style="font-size:0.7rem;font-weight:700;color:#475467;background:#F2F4F7;'
            f'border-radius:5px;padding:2px 7px;margin-right:9px;white-space:nowrap;">'
            + (f'{e["채널"]} +{e["채널수"]-1}' if e.get("채널수", 1) > 1 else e["채널"])
            + '</span>'
            f'<span class="kw-name" style="flex:1;font-size:0.83rem;font-weight:700;color:{name_color};">{e["표기명"]}</span>'
            f'<span style="font-size:0.7rem;color:#98A2B3;margin-right:10px;white-space:nowrap;">{e["근거"]}</span>'
            f'<span style="font-size:0.75rem;color:#475467;margin-right:10px;white-space:nowrap;">{e["주차"]}</span>'
            f'{right}</div></a>'
        )

    sub_header("01", "감지된 캠페인", "특정 ETF를 미는 일회성 집행만 = DiD의 처치")
    st.markdown(
        f'<div style="font-size:0.76rem;color:{MUTED};margin-bottom:10px;">'
        f'감지 {len(campaigns_raw)}건 → <b style="color:{INK};">상품 {len(campaigns)}종</b>'
        f' (분석 가능 {len(usable)}종) · 정기물·단발 언급 {len(others)}건은 개입으로 보지 않아 제외<br>'
        f'같은 상품을 여러 채널에 집행해도 순매수 시계열은 하나뿐이라 '
        f'<b>DiD는 상품당 한 번</b>만 돌립니다 — 개입 시점은 <b>가장 먼저 시작한 채널</b> 기준입니다.</div>',
        unsafe_allow_html=True,
    )
    if campaigns:
        st.markdown(
            f'<div class="card" style="padding:8px 16px;">{"".join(ev_row(e) for e in campaigns[:8])}</div>',
            unsafe_allow_html=True)
    else:
        st.info("감지된 캠페인이 없습니다 — 수집물에 특정 ETF를 미는 일회성 집행이 없습니다.")
    if others:
        with st.expander(f"DiD에서 제외된 콘텐츠 {len(others)}건 — 정기물 · 단발 언급"):
            st.markdown(
                f'<div style="padding:0 4px;">{"".join(ev_row(e, dim=True) for e in others[:12])}</div>',
                unsafe_allow_html=True)
            st.caption("정기 리포트는 평소 반복되는 베이스라인이라 개입이 아니고, 단발 언급은 "
                       "교육 콘텐츠에 예시로 등장한 경우가 많아 해당 ETF를 위한 마케팅으로 보기 어렵습니다.")
    st.write("")

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("02", "분석 대상 지정", "처치군 ETF와 개입 주차 · 비교할 대조군")

    # ── 분석할 캠페인 선택 (처치 ETF + 개입 주차가 함께 결정된다)
    manual_mode = False
    if usable:
        labels = [f'{e["표기명"]} · 개입 {e["주차"]}'
                  + (f' · {e["채널수"]}개 채널' if e.get("채널수", 1) > 1 else f' · {e["채널"]}')
                  for e in usable]
        pick = st.selectbox("분석할 마케팅 이벤트", labels,
                            help="선택한 이벤트의 ETF가 처치군, 집행 주차가 개입 시점이 됩니다")
        ev = usable[labels.index(pick)]
        treat, event_week = ev["ETF"], ev["주차"]
    else:
        st.warning(
            "분석 가능한 캠페인이 없습니다 — 캠페인 대상 ETF가 순매수 유니버스에 없습니다. "
            "실제 KODEX 라인업·순매수 실데이터를 연동하면 해소됩니다. 아래는 수동 지정 모드입니다."
        )
        manual_mode = True
        treat = st.selectbox("처치군 — 마케팅한 KODEX ETF (수동)", kodex_list(netbuy_df))
        event_week = sel_week

    weeks_avail = list(dict.fromkeys(netbuy_df["주차"]))
    if event_week not in weeks_avail:   # 순매수 데이터에 없는 주차면 최신 주차로 대체
        event_week = weeks_avail[-1]

    _uni = universe_frame(netbuy_df)
    # 테마·기초시장이 같다는 건 '그럴듯한 이유'일 뿐 검증이 아니다.
    # 개입 이전 구간에서 실제로 나란히 움직였는지 확인하고 그 결과로 채택한다.
    _diag, auto_controls, _ = did_verified(netbuy_df, _uni, treat, event_week)
    ctrl_options = (sorted(_uni[_uni["운용사"] != "KODEX"]["종목명"].unique()) if _uni is not None
                    else sorted(n for n, _, i in D.ETF_UNIVERSE if i != "KODEX"))
    controls = st.multiselect(
        "대조군 — 평행추세가 확인된 경쟁 ETF (자동 선정, 수정 가능)",
        options=ctrl_options,
        default=auto_controls,
    )
    st.caption(f"처치군 **{treat}** · 개입 주차 **{event_week}**"
               + ("  (수동 지정 — 실제 마케팅 여부는 검증되지 않음)" if manual_mode
                  else "  (감지된 마케팅 집행 시점 기준)"))

    # ── 평행추세 진단 — DiD의 가정이 성립하는지 보여준다
    if len(_diag):
        _V = {"양호": ("#1E7A55", "#EAF7EF"), "약함": ("#B0801F", "#FDF6E7"),
              "부적합": (RED, "#FDECEB"), "검증 불가": (MUTED, "#F2F4F7")}
        _n_bad = int((_diag["판정"] == "부적합").sum())
        _n_untested = int((_diag["판정"] == "검증 불가").sum())
        _rows = ""
        for _, r in _diag.iterrows():
            _c, _bg = _V.get(r["판정"], (MUTED, "#F2F4F7"))
            _used = r["종목명"] in controls
            _corr = "—" if pd.isna(r["상관"]) else f'{r["상관"]:+.2f}'
            _rows += (
                f'<tr style="opacity:{"1" if _used else "0.45"};">'
                f'<td style="padding:6px 10px;font-size:0.82rem;">{r["종목명"]}</td>'
                f'<td class="num" style="padding:6px 10px;font-size:0.82rem;">{_corr}</td>'
                f'<td class="num" style="padding:6px 10px;font-size:0.82rem;">{r["평행오차"]:.2f}</td>'
                f'<td class="num" style="padding:6px 10px;font-size:0.82rem;">{r["순자산"]:,.0f}억</td>'
                f'<td style="padding:6px 10px;text-align:right;">'
                f'<span style="font-size:0.68rem;font-weight:700;color:{_c};background:{_bg};'
                f'border-radius:4px;padding:2px 8px;">{r["판정"]}</span></td></tr>')
        with st.expander(
                f"평행추세 진단 — 후보 {len(_diag)}개 중 {len(controls)}개 채택"
                + (f" · 부적합 {_n_bad}개 제외" if _n_bad else "")
                + (f" · 검증 불가 {_n_untested}개" if _n_untested else ""),
                expanded=bool(_n_bad or _n_untested)):
            st.markdown(
                f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;margin-bottom:10px;">'
                f'DiD는 <b>"마케팅이 없었다면 처치군도 대조군과 같은 방향으로 움직였을 것"</b>을 가정합니다. '
                f'개입 이전 구간에서 주간 강도 변화(Δ)가 실제로 동행했는지 확인한 결과입니다 — '
                f'<b>상관이 음수(부적합)</b>면 반대로 움직였다는 뜻이라 넣으면 DiD 부호까지 왜곡됩니다. '
                f'대조군 평균은 <b>순자산 가중</b>입니다 (소형 ETF의 노이즈 억제).</div>'
                f'<table class="sig-table"><thead><tr>'
                f'<th>후보</th><th class="num">Δ상관</th><th class="num">평행오차</th>'
                f'<th class="num">순자산</th><th style="text-align:right;">판정</th>'
                f'</tr></thead><tbody>{_rows}</tbody></table>',
                unsafe_allow_html=True)
            if _n_untested == len(_diag):
                _why = next((r for r in _diag.get("사유", pd.Series(dtype=str)) if r), "")
                st.info(f"평행추세를 검증할 수 없습니다 — {_why}\n\n"
                        "아래 DiD 값은 **가정이 확인되지 않은 상태**의 참고치입니다.")

    _w = (_uni.drop_duplicates("종목명").set_index("종목명")["순자산"].to_dict()
          if _uni is not None and "순자산" in _uni.columns else None)
    series = D.did_series(netbuy_df, treat, controls, weights=_w)
    sc = D.did_score(series, event_week)

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("03", "진단 결과", "좌: 금주 순매수강도 맥락 · 우: 처치−대조 이중차분")

    d1, d2 = st.columns([7, 5], gap="large")
    with d1:
        # 순매수강도 TOP N (참고 맥락)
        top = wk.nlargest(top_n, "매수강도").sort_values("매수강도")
        colors = [NAVY if "KODEX" in n else "#D5DBE7" for n in top["종목명"]]
        fig_top = go.Figure(
            go.Bar(x=top["매수강도"], y=top["종목명"], orientation="h", marker_color=colors,
                   text=[f"{v:+.2f}%" for v in top["매수강도"]], textposition="outside",
                   cliponaxis=False,
                   hovertemplate="%{y}<br>매수강도 %{x:.2f}%<extra></extra>")
        )
        _h_top = max(360, top_n * BAR_ROW_PX + CHART_CHROME_PX)
        fig_top = base_layout(fig_top, height=_h_top)
        fig_top.update_layout(title=dict(text=f"{sel_week} 순매수강도 TOP {top_n}", font=dict(size=15)))
        xmax = float(top["매수강도"].max())
        fig_top.update_xaxes(ticksuffix="%", range=[min(0, float(top["매수강도"].min()) * 1.2), xmax * 1.25])
        st.plotly_chart(fig_top, use_container_width=True)
        st.caption(f"진한 남색 = KODEX 상품 · 분석 대상 {len(wk)}개 ETF")

    with d2:
        st.markdown(
            f'<div style="font-size:0.9rem;font-weight:800;color:{INK};margin-bottom:8px;">'
            f'DiD 진단 <span style="font-size:0.72rem;color:{FAINT};font-weight:600;">'
            f'8주 베이스라인 대비</span></div>', unsafe_allow_html=True)
        # 신규 상장 등으로 베이스라인이 없으면 단계 카드 대신 사유를 명확히 알린다
        no_baseline = sc.get("did") is None and sc.get("delta_treat") is None and sc.get("fallback")
        if no_baseline:
            st.markdown(
                f'<div class="did-result" style="background:#5B6478;">'
                f'<div class="did-result-label">측정 불가</div>'
                f'<div class="did-result-val" style="font-size:1.35rem;">DiD 산출 안 함</div>'
                f'<div class="did-result-note">{sc["fallback"]}<br><br>'
                f'DiD는 <b>개입 전과 후를 비교</b>하는 방법이라, 상장 직후처럼 "이전"이 존재하지 않으면 '
                f'성립하지 않습니다. 이 경우 첫 주 유입은 마케팅 효과가 아니라 상품 출시 그 자체입니다.'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            st.caption("신규 상장 캠페인은 동일 시기 상장한 경쟁 ETF와 초기 유입을 비교하는 별도 지표가 적합합니다.")
        s1c, s2c = st.columns(2)
        dt_v = sc.get("delta_treat")
        dc_v = sc.get("delta_ctrl")
        s1c.markdown(
            f'<div class="did-step"><div class="did-step-no">STEP 1 · 처치군</div>'
            f'<div class="did-step-name">Δ처치 (베이스라인 대비)</div>'
            f'<div class="did-step-val">{dt_v:+.2f}%p</div>'
            f'<div class="did-step-desc">{treat[:20]}<br>금주 강도 − 직전 8주 평균</div></div>'
            if dt_v is not None else
            ('<div class="did-step"><div class="did-step-no">STEP 1 · 처치군</div>'
             '<div class="did-step-name">산출 불가</div>'
             f'<div class="did-step-desc">{treat[:20]}<br>비교할 직전 8주 베이스라인이 없습니다</div></div>'),
            unsafe_allow_html=True,
        )
        s2c.markdown(
            f'<div class="did-step"><div class="did-step-no">STEP 2 · 대조군</div>'
            f'<div class="did-step-name">Δ대조군 평균</div>'
            f'<div class="did-step-val">{dc_v:+.2f}%p</div>'
            f'<div class="did-step-desc">{len(controls)}개 경쟁 ETF 평균<br>= 시장이 원래 움직인 만큼</div></div>'
            if dc_v is not None else
            ('<div class="did-step"><div class="did-step-no">STEP 2 · 대조군</div>'
             f'<div class="did-step-name">{"산출 불가" if no_baseline else "대조군 없음"}</div>'
             f'<div class="did-step-desc">{f"대조군 {len(controls)}개는 지정됨 — 처치군 베이스라인이 없어 계산 불가" if no_baseline else "경쟁 ETF를 지정하면 시장효과가 제거됩니다"}</div></div>'),
            unsafe_allow_html=True,
        )
        st.write("")
        if sc.get("did") is not None:
            score = sc.get("score")
            if score is not None:
                # 판정 구간은 Z(표준편차 배수)에 직접 대응시킨다 — 50점 = 평소와 같음이 기준선
                z = sc["z"]
                if z >= 1.65:
                    verdict, vcolor, vsay = "이례적으로 강함", "#2E9E62", "평소 상위 5% 수준 — 마케팅 효과가 뚜렷합니다."
                elif z >= 1.0:
                    verdict, vcolor, vsay = "평소보다 강함", "#7FE0A7", "평소보다 1σ 이상 높습니다 — 효과가 있었다고 볼 만합니다."
                elif z >= 0.5:
                    verdict, vcolor, vsay = "다소 강함", "#B8E6C8", "평소보다 조금 높지만 단정하기엔 약합니다."
                elif z > -0.5:
                    verdict, vcolor, vsay = "평소와 차이 없음", "#C7CFDF", "평소 변동 범위 안입니다 — 효과가 있었는지 판별되지 않습니다."
                else:
                    verdict, vcolor, vsay = "평소보다 부진", "#9DB2D9", "평소보다 오히려 낮습니다 — 이번 캠페인 주간의 순유입은 평소만 못했습니다."
                base_txt = (f'이 ETF 평소 DiD {sc["base_mean"]:+.2f}%p ± {sc["base_std"]:.2f}%p ({sc["n_hist"]}주)'
                            if sc.get("base_mean") is not None else "")
                st.markdown(
                    f'<div class="did-result">'
                    f'<div class="did-result-label">DiD {sc["did"]:+.2f}%p · {base_txt}</div>'
                    f'<div class="did-result-val">{score:.0f}점 '
                    f'<span style="font-size:0.9rem;opacity:0.75;">/ 100 · {verdict}</span></div>'
                    f'<div class="score-track" style="position:relative;">'
                    f'<div class="score-fill" style="width:{score}%;background:{vcolor};"></div>'
                    f'<div style="position:absolute;left:50%;top:-3px;width:2px;height:calc(100% + 6px);'
                    f'background:rgba(255,255,255,0.85);"></div></div>'
                    f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;opacity:0.6;margin-top:3px;">'
                    f'<span>0 · 평소보다 낮음</span><span>50 · 평소와 같음</span><span>100 · 평소보다 높음</span></div>'
                    f'<div class="did-result-note">{vsay}</div></div>',
                    unsafe_allow_html=True,
                )
                with st.expander("점수 해석 기준"):
                    st.markdown(
                        f"""
**점수는 "이 ETF의 평소 DiD와 비교해 이번 주가 얼마나 달랐나"입니다.**
절대적인 효과 크기가 아니라 **평소 대비 상대 위치**입니다.

- **50점 = 평소와 똑같음** (기준선). 0점이 아니라 50점이 "효과 없음"입니다.
- 점수는 Z(표준편차 배수)를 0~100으로 변환한 값입니다.

| 점수 | Z | 판정 | 의미 |
|---|---|---|---|
| 84점 이상 | +1.65σ 이상 | 이례적으로 강함 | 평소 분포의 상위 5% |
| 73~84점 | +1.0σ 이상 | 평소보다 강함 | 효과가 있었다고 볼 만함 |
| 62~73점 | +0.5σ 이상 | 다소 강함 | 방향은 긍정, 단정은 이름 |
| 38~62점 | ±0.5σ 이내 | 평소와 차이 없음 | 판별 불가 |
| 38점 미만 | −0.5σ 이하 | 평소보다 부진 | 평소만 못함 |

**주의** — 기준이 되는 "평소"는 해당 ETF 자신의 과거 {D.ZSCORE_WINDOW}주 DiD 분포입니다.
따라서 평소에도 마케팅을 자주 한 ETF는 기준선이 높아 점수가 짜게 나옵니다.
마케팅을 한 적 없는 ETF들과 비교하는 절대 기준선은 별도 작업(귀무분포)이 필요합니다.
                        """
                    )
            else:
                st.markdown(
                    f'<div class="did-result"><div class="did-result-label">DiD (점수화 불가)</div>'
                    f'<div class="did-result-val">{sc["did"]:+.2f}%p</div>'
                    f'<div class="did-result-note">{sc["fallback"]}</div></div>',
                    unsafe_allow_html=True,
                )
        elif dt_v is not None:
            st.markdown(
                f'<div class="did-result"><div class="did-result-label">단순 변화량 (대조군 없음)</div>'
                f'<div class="did-result-val">Δ{dt_v:+.2f}%p</div>'
                f'<div class="did-result-note">시장효과가 제거되지 않은 값입니다. 대조군을 지정하세요.</div></div>',
                unsafe_allow_html=True,
            )

        # DiD 시계열
        fig_did = go.Figure()
        fig_did.add_trace(go.Bar(
            x=series["주차"], y=series["DiD"], name="DiD",
            marker_color=[NAVY if w == event_week else "#C7CFDF" for w in series["주차"]],
        ))
        fig_did = base_layout(fig_did, height=220)
        fig_did.update_layout(title=dict(text=f"주차별 DiD 추이 (진한 막대 = 개입 주차 {event_week})", font=dict(size=14)),
                              margin=dict(l=10, r=10, t=40, b=10))
        fig_did.update_yaxes(ticksuffix="%p")
        st.plotly_chart(fig_did, use_container_width=True)

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("04", "전체 KODEX ETF 점수 보드", "캠페인 유무와 무관하게 전 종목의 금주 DiD를 나열")
    if len(did_board):
        st.dataframe(
            did_board.sort_values("score", ascending=False, na_position="last").rename(columns={"score": "효과점수(0~100)"}),
            use_container_width=True, hide_index=True,
        )
        st.caption(f"베이스라인 {D.BASELINE_WEEKS}주 평균 · 라플라스 α={D.LAPLACE_ALPHA:.0f}억 · Z-score 창 {D.ZSCORE_WINDOW}주(가용분) · 대조군 = 동일 테마 비KODEX 평균")
    else:
        st.info("점수 산출 가능한 KODEX ETF가 없습니다.")

# ──────────────────────────────────────────────
# ④ 주간 리포트 — 데이터 기반 인사이트
# ──────────────────────────────────────────────
with tab_report:
    st.write("")
    section_header(
        "STEP 4 · REPORT",
        "주간 마케팅 리포트",
        "①~③의 실데이터를 종합한 주간 브리핑입니다. 화면은 핵심 요약이며, 하단에서 전체 리포트를 PDF로 받을 수 있습니다.",
    )
    st.write("")

    # ── 리포트 컨텍스트 (실데이터 · 탭 간 의존 없이 자체 완결)
    try:
        _sb_all = json.loads((Path(__file__).parent / "data" / "signal_board.json").read_text())
    except Exception:
        _sb_all = {}
    rep_board = _sb_all.get("board", [])
    rep_kw, rep_articles, rep_news_live = load_news_mentions()
    rep_search, rep_search_live = load_theme_search()
    rep_blogs = load_blogs()
    try:
        _ch = json.loads((Path(__file__).parent / "data" / "channel_board.json").read_text())
    except Exception:
        _ch = {}
    # ③과 같은 파이프라인 — 탭마다 따로 계산해 숫자가 어긋나던 것을 없앤다
    rep_events, rep_campaigns = kodex_campaigns(_ch, youtube, rep_blogs, netbuy_df)
    _week_ago_r = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    _uni_r = universe_frame(netbuy_df)

    from collections import Counter as _C
    stage_ct = dict(_C(r.get("단계", "관망") for r in rep_board))
    ret_rows = sorted([r for r in rep_board if r.get("주간수익률") is not None],
                      key=lambda r: r["주간수익률"])
    top_up = [(r["섹터"], r["주간수익률"]) for r in ret_rows[-3:][::-1]]
    top_dn = [(r["섹터"], r["주간수익률"]) for r in ret_rows[:3]]
    n_sectors = len(rep_board) or 1
    n_dec = stage_ct.get("쇠퇴기", 0)
    regime = "쇠퇴 우위 시장" if n_dec >= n_sectors / 2 else "혼조 시장"

    # 현재 마케팅 점검
    review = D.review_current_marketing(rep_events, rep_board, netbuy_df, event_week)
    n_cut = sum(1 for r in review if r["판정"] == "축소")
    n_keep = sum(1 for r in review if r["판정"].startswith("지속"))
    review_read = (
        f"하락장에서 방어·코어 상품 마케팅은 지속({n_keep}건), "
        f"과열·쇠퇴 성장테마는 축소 검토({n_cut}건). 확대할 만한 상승 국면 캠페인은 이번 주 없음."
        if n_dec >= n_sectors / 2 else
        f"지속 {n_keep}건 · 축소 {n_cut}건 — 국면별로 집행 강도를 조정할 시점입니다.")

    # 브랜드 발행량
    brand_act = sorted(
        ((b, sum(1 for v in youtube.get(b, []) if v.get("published", "") >= _week_ago_r)
          + sum(1 for p in rep_blogs.get(b, []) if p.get("date", "") >= _week_ago_r))
         for b in D.ISSUERS), key=lambda x: -x[1])

    # 자금 상위
    flow_top = []
    if netbuy_live:
        _w = netbuy_df[netbuy_df["주차"] == event_week].dropna(subset=["매수강도"])
        _w = _w[_w["매수강도"] < 40]                      # 신규상장 왜곡 제외
        flow_top = [(r["종목명"], r["매수강도"]) for _, r in _w.nlargest(4, "매수강도").iterrows()]

    # DiD 예시 (최근 측정 가능 건)
    did_ctx = None
    for e in rep_campaigns:
        if not e["분석가능"]:
            continue
        _wk = e["주차"] if e["주차"] in weeks else weeks[-1]
        _, _c, _sx = did_verified(netbuy_df, _uni_r, e["ETF"], _wk)
        if _sx.get("did") is not None and _sx.get("score") is not None:
            _z = _sx["z"]
            did_ctx = {
                "name": e["표기명"], "channel": e["채널"], "week": _wk,
                "dt": _sx["delta_treat"], "dc": _sx["delta_ctrl"], "did": _sx["did"],
                "score": _sx["score"], "base_mean": _sx["base_mean"], "base_std": _sx["base_std"],
                "verdict": ("이례적으로 강함" if _z >= 1.65 else "평소보다 강함" if _z >= 1.0 else
                            "다소 강함" if _z >= 0.5 else "평소와 차이 없음" if _z > -0.5 else "평소보다 부진"),
            }
            break

    # 태동기 착수 후보 (현재 미집행 섹터)
    _marketed = {r["표기명"] for r in review}
    emerging = None
    for r in rep_board:
        if r.get("단계") == "태동기":
            emerging = {"섹터": r["섹터"], "kodex": r.get("KODEX", "KODEX 보유 상품"),
                        "peer_note": "경쟁 8개 브랜드 모두 해당 섹터 캠페인 미집행 — 선점 여지가 큽니다."}
            break
    emerging_names = ", ".join(r["섹터"] for r in rep_board if r.get("단계") == "태동기")
    expanding_names = ", ".join(r["섹터"] for r in rep_board if r.get("단계") == "확산기")

    # 신규 출시 후보 (라인업 공백 1순위)
    gaps = D.lineup_gaps() if hasattr(D, "lineup_gaps") else []
    gap_ctx = None
    if gaps:
        g = gaps[0]
        _peers = D.gap_competitors(g["테마"], g["시장"]) if hasattr(D, "gap_competitors") else []
        _types = _C(D.etf_product_type(p) for p in _peers) if _peers else {}
        _dom = max(_types, key=_types.get) if _types else "지수추종"
        _all_same = len(_types) == 1
        _stage = next((r.get("단계", "") for r in rep_board if r["섹터"] == g["테마"]), "")
        _srch = rep_search.get(g["테마"]) or rep_search.get("AI반도체" if g["테마"] == "반도체" else "", None)
        gap_ctx = {
            "테마": g["테마"], "시장": g["시장"], "경쟁사수": g["경쟁사수"], "경쟁상품": _peers,
            "가칭": f'KODEX {g["시장"]}{g["테마"]}'.replace("한국", ""),
            "유형요약": (f'{g["경쟁사수"]}종 모두 {_dom}' if _all_same else f'{_dom} 중심 {g["경쟁사수"]}종'),
            "국면": _stage,
            "신호설명": (f'검색 {_srch:+.1f}%' if _srch is not None else "검색 신호 없음")
                        + (f' · 국면상 {_stage}' if _stage else ""),
            "타이밍": "대기" if _stage in ("과열기", "쇠퇴기") else "검토",
            "타이밍설명": ("국면이 고점/쇠퇴 구간 — 진정 후 겨냥, 리드타임 감안 준비만 착수"
                        if _stage in ("과열기", "쇠퇴기") else "국면 확인 후 출시 시점 판단"),
            "차별화": (f'경쟁 {g["경쟁사수"]}종이 전부 {_dom}이므로 액티브·세부 테마 심화로 차별화 여지가 있습니다. '
                     if _all_same else f'경쟁이 {_dom} 중심이므로 다른 운용 방식으로 빈틈을 노릴 수 있습니다. ')
                    + "추종 지수 존재 여부와 구성종목은 담당자 검증이 필요합니다.",
        }

    ctx = {
        "week": event_week, "asof": _sb_all.get("asof", ""), "issued": dt.date.today().isoformat(),
        "n_sectors": n_sectors, "n_kodex": len(kodex_list(netbuy_df)),
        "stage_counts": stage_ct, "regime": regime,
        "bench_ret": _sb_all.get("벤치주간수익률"),
        "top_up": top_up, "top_dn": top_dn,
        "campaigns": rep_campaigns, "top_brand": brand_act[0] if brand_act else ("—", 0),
        "flow_top": flow_top, "did": did_ctx, "review": review, "review_read": review_read,
        "emerging": emerging, "emerging_names": emerging_names, "expanding_names": expanding_names,
        "gap": gap_ctx, "search": rep_search,
    }

    # ══════════ 헤드라인 ══════════
    _lead = RT.build_lead(ctx)
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#16244D,#1F3A6E);border-radius:12px;'
        f'padding:20px 24px;color:#fff;">'
        f'<div style="font-size:0.66rem;letter-spacing:.16em;font-weight:700;opacity:.75;">'
        f'WEEKLY SYNTHESIS · {event_week}</div>'
        f'<div style="font-size:0.95rem;line-height:1.75;margin-top:8px;">{_lead}</div></div>',
        unsafe_allow_html=True)
    st.write("")

    # ══════════ 국면 스트립 + KPI ══════════
    k1, k2 = st.columns([7, 5], gap="large")
    with k1:
        segs = [("태동기", "#4C6FC6"), ("확산기", "#2E7D5B"), ("과열기", "#C4362E"), ("쇠퇴기", "#7A8595")]
        bar = "".join(
            f'<span style="width:{stage_ct.get(s,0)/n_sectors*100:.1f}%;background:{c};display:flex;'
            f'align-items:center;justify-content:center;font-size:0.62rem;font-weight:700;color:#fff;">'
            f'{s[:2]+" "+str(stage_ct.get(s,0)) if stage_ct.get(s,0)/n_sectors > .10 else ""}</span>'
            for s, c in segs if stage_ct.get(s, 0))
        st.markdown(
            f'<div style="font-size:0.72rem;color:{GRAY};margin-bottom:5px;">'
            f'{n_sectors}개 섹터 국면 분포 · <b style="color:{INK};">{regime}</b></div>'
            f'<div style="display:flex;height:26px;border-radius:5px;overflow:hidden;'
            f'border:1px solid #E4E7EC;">{bar}</div>', unsafe_allow_html=True)
    with k2:
        _b = ctx["bench_ret"]
        kpis = [("KRX300 주간", f"{_b:+.1f}%" if _b is not None else "—", COOL if (_b or 0) < 0 else RED),
                ("집행 캠페인", f"{len(rep_campaigns)}건", INK),
                ("축소 검토", f"{n_cut}건", COOL)]
        cells = "".join(
            f'<div style="flex:1;text-align:center;"><div style="font-size:0.66rem;color:{GRAY};">{k}</div>'
            f'<div style="font-size:1.05rem;font-weight:800;color:{c};margin-top:2px;">{v}</div></div>'
            for k, v, c in kpis)
        st.markdown(f'<div style="display:flex;gap:8px;padding-top:14px;">{cells}</div>',
                    unsafe_allow_html=True)
    st.write("")

    # ══════════ A. 현재 마케팅 점검 (핵심) ══════════
    sub_header("A", "현재 마케팅 점검", "집행 중인 상품을 국면·자금 근거로 지속·확대·축소 판정")
    if review:
        _vc = {"지속": ("#2E7D5B", "#EAF7EF"), "확대": ("#2E7D5B", "#EAF7EF"),
               "지속·관찰": ("#B0801F", "#FDF6E7"), "지속·신중": ("#B0801F", "#FDF6E7"),
               "축소": ("#2C63B5", "#EAF0FD")}
        rows = ""
        for r in review:
            col, bg = _vc.get(r["판정"], ("#5C6572", "#F2F4F7"))
            v = r.get("개인강도")
            flow = ("신규상장" if v is not None and v >= 40 else
                    f"{v:+.2f}%" if v is not None else "—")
            fcol = GRAY if (v is None or v >= 40) else (RED if v > 0 else COOL)
            rows += (
                f'<div style="display:flex;align-items:center;gap:10px;padding:9px 0;'
                f'border-bottom:1px solid #F0F2F7;">'
                f'<span style="font-size:0.68rem;font-weight:800;color:{col};background:{bg};'
                f'border-radius:20px;padding:3px 10px;white-space:nowrap;min-width:70px;'
                f'text-align:center;">{r["판정"]}</span>'
                f'<span style="flex:1;font-size:0.84rem;font-weight:700;">'
                f'{r["표기명"].replace("KODEX ","")}</span>'
                f'<span style="font-size:0.72rem;color:{GRAY};white-space:nowrap;">{r["국면"]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:{fcol};white-space:nowrap;'
                f'min-width:66px;text-align:right;">{flow}</span></div>')
        st.markdown(f'<div class="card" style="padding:6px 18px 12px;">{rows}'
                    f'<div style="margin-top:10px;padding:10px 13px;background:#EAF0FD;border-radius:7px;'
                    f'font-size:0.8rem;line-height:1.6;">{review_read}</div></div>',
                    unsafe_allow_html=True)
        with st.expander("판정 근거 자세히"):
            for r in review:
                st.markdown(f"**[{r['판정']}] {r['표기명']}** — {r['근거']}")
    else:
        st.info("현재 집행 중인 KODEX 마케팅이 감지되지 않았습니다.")
    st.write("")

    # ══════════ B · C ══════════
    b1, b2 = st.columns(2, gap="large")
    with b1:
        sub_header("B", "태동기 착수")
        if emerging:
            st.markdown(
                f'<div class="card"><div style="font-size:1rem;font-weight:800;">{emerging["섹터"]} '
                f'<span style="font-size:0.65rem;font-weight:700;color:#fff;background:#4C6FC6;'
                f'border-radius:20px;padding:2px 9px;vertical-align:middle;">유일 태동기</span></div>'
                f'<div style="font-size:0.8rem;color:{GRAY};line-height:1.65;margin-top:6px;">'
                f'<b style="color:{INK};">{emerging["kodex"]}</b> 보유하나 현재 미집행 — 확산 전환 전 '
                f'인지도를 선점하는 착수 대상입니다.<br>{emerging["peer_note"]}</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="card"><div style="font-size:0.82rem;color:{GRAY};">'
                        f'이번 주 태동 국면 섹터가 없습니다.</div></div>', unsafe_allow_html=True)
    with b2:
        sub_header("C", "신규 출시 후보")
        if gap_ctx:
            st.markdown(
                f'<div class="card"><div style="font-size:1rem;font-weight:800;">'
                f'{gap_ctx["테마"]} × {gap_ctx["시장"]} '
                f'<span style="font-size:0.65rem;font-weight:700;color:#fff;background:#B0801F;'
                f'border-radius:20px;padding:2px 9px;vertical-align:middle;">'
                f'출시 {gap_ctx["타이밍"]}</span></div>'
                f'<div style="font-size:0.8rem;color:{GRAY};line-height:1.65;margin-top:6px;">'
                f'KODEX 미보유 · 경쟁 <b style="color:{INK};">{gap_ctx["경쟁사수"]}종</b> '
                f'({gap_ctx["유형요약"]})<br>{gap_ctx["타이밍설명"]}</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="card"><div style="font-size:0.82rem;color:{GRAY};">'
                        f'라인업 공백 계산 불가 — 배치 실행 후 표시됩니다.</div></div>', unsafe_allow_html=True)
    st.write("")

    # ══════════ DiD 요약 ══════════
    if did_ctx:
        sub_header("D", "마케팅 효과 검증", "③에서 측정한 이번 주 대표 사례")
        st.markdown(
            f'<div class="card" style="padding:14px 18px;">'
            f'<div style="font-size:0.82rem;color:{GRAY};margin-bottom:8px;">'
            f'측정 사례 <b style="color:{INK};">{did_ctx["name"]}</b> · {did_ctx["channel"]} · {did_ctx["week"]}</div>'
            f'<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">'
            f'<span style="font-size:0.8rem;">Δ처치 <b>{did_ctx["dt"]:+.2f}%p</b></span>'
            f'<span style="color:{FAINT};">−</span>'
            f'<span style="font-size:0.8rem;">Δ대조군 <b>{did_ctx["dc"]:+.2f}%p</b></span>'
            f'<span style="color:{FAINT};">=</span>'
            f'<span style="font-size:0.9rem;color:{NAVY};">DiD <b>{did_ctx["did"]:+.2f}%p</b></span>'
            f'<span style="margin-left:auto;font-size:0.86rem;font-weight:800;color:{NAVY};">'
            f'{did_ctx["score"]:.0f}점 · {did_ctx["verdict"]}</span></div>'
            f'<div style="font-size:0.72rem;color:{GRAY};margin-top:8px;">'
            f'50점이 "평소와 같음" 기준선 · 이 ETF 평소 DiD {did_ctx["base_mean"]:+.2f}±{did_ctx["base_std"]:.2f}%p'
            f'</div></div>', unsafe_allow_html=True)
        st.write("")

    # ══════════ PDF 내보내기 ══════════
    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("PDF", "전체 리포트 내려받기", "화면 요약보다 자세한 5개 섹션 전체 리포트")
    st.markdown(
        f'<div style="font-size:0.76rem;color:{MUTED};margin-bottom:10px;">'
        f'내려받은 파일을 열어 <b>인쇄(⌘/Ctrl+P) → PDF로 저장</b>하면 A4 리포트가 만들어집니다.</div>',
        unsafe_allow_html=True)
    try:
        _html = RT.render_report(ctx)
        st.download_button(
            "📄 주간 리포트 내려받기 (HTML → 인쇄 시 PDF)",
            _html.encode("utf-8"),
            file_name=f"KODEX_주간마케팅리포트_{dt.date.today().isoformat()}.html",
            mime="text/html",
            type="primary",
        )
        with st.expander("리포트 미리보기"):
            st.components.v1.html(_html, height=760, scrolling=True)
    except Exception as _e:
        st.error(f"리포트 생성 실패: {type(_e).__name__} — {_e}")

    st.caption("ⓘ 시장·자금·캠페인은 실데이터(KRX·네이버·구글·RSS)입니다. 국면별 액션은 규칙 기반 제안이며, "
               "순환/성장 판단과 출시 가능성 검증은 담당자 몫입니다.")

# ──────────────────────────────────────────────
# ⑤ 규제 동향 — 금융위 보도자료·입법예고 + 규제 뉴스
# ──────────────────────────────────────────────
with tab_reg:
    st.write("")
    section_header(
        "STEP 5 · REGULATION",
        "금융 규제 동향",
        "금융위원회 보도자료·입법예고와 규제 뉴스를 수집해 ETF·자본시장 관련 건만 추립니다. "
        "집행 중인 마케팅과 겹치는 규제는 상단에 경고로 띄웁니다.",
    )
    st.write("")

    _rule_sig = (getattr(D, "REG_RELEVANT", None).pattern if hasattr(D, "REG_RELEVANT") else "") \
        + "|" + (getattr(D, "REG_EXCLUDE", None).pattern if hasattr(D, "REG_EXCLUDE") else "")
    # 반환 형태가 (목록, 출처별 상태)로 바뀌어 캐시 키에 버전을 섞는다
    regs, reg_status = load_regulations(_rule_sig + "|v2-paged")
    reg_news = load_regulation_news()
    rel = [r for r in regs if r["관련"]]

    # ── 집행 중 마케팅 × 규제 교차 경고
    _rev_names = [r["표기명"] for r in review] if "review" in dir() else []
    alerts = []
    for r in rel:
        for nm in _rev_names:
            core = re.sub(r"^KODEX\s*", "", nm)
            toks = [t for t in re.findall(r"[가-힣A-Za-z0-9]{3,}", core)][:2]
            if toks and any(t in r["제목"] for t in toks):
                alerts.append((r, nm))
                break
    if alerts:
        for r, nm in alerts[:3]:
            st.warning(
                f"**집행 중 마케팅과 겹치는 규제** — {r['유형']} · {r['date'] or '날짜미상'}\n\n"
                f"[{r['제목']}]({r['링크']})\n\n"
                f"현재 **{nm}** 마케팅을 집행 중입니다. 규제 방향을 확인한 뒤 메시지·집행 강도를 재검토하세요.")
        st.write("")

    c1, c2 = st.columns([7, 5], gap="large")
    with c1:
        sub_header("01", "금융위 보도자료 · 입법예고")
        # 수집 실패와 '수집은 됐으나 관련 건 없음'을 구분해서 보여준다
        _failed = [k for k, v in reg_status.items() if v.get("오류")]
        _parts = " · ".join(
            f'{k.replace("·규정변경", "")} {v["수집"]}건'
            + (f' <span style="color:{RED};">수집 실패</span>' if v.get("오류") else "")
            for k, v in reg_status.items())
        st.markdown(
            f'<div style="font-size:0.76rem;color:{MUTED};margin-bottom:10px;">'
            f'{_parts} 수집 → ETF·자본시장 관련 '
            f'<b style="color:{INK};">{len(rel)}건</b> (정책펀드·기금 등은 제외)</div>',
            unsafe_allow_html=True)
        for _k in _failed:
            st.error(f"**{_k} 수집 실패** — {reg_status[_k]['오류']}\n\n"
                     "금융위 사이트 응답이 없거나 페이지 구조가 바뀐 경우입니다. "
                     "아래 목록에는 이 게시판 건이 빠져 있습니다.")
        if rel:
            KIND_C = {"법률": "#B5321F", "시행령": "#1B4DE4", "규정·고시": "#6B4FBB",
                      "정책방안": "#B0801F", "기타": "#5C6572"}
            _today_s = dt.date.today().isoformat()
            rows = ""
            for r in rel[:10]:
                c = KIND_C.get(r["유형"], "#5C6572")
                # 입법예고는 의견제출 마감일이 핵심 — 진행 중이면 강조
                per = r.get("예고기간", "")
                if per:
                    end = per.split("~")[-1].strip()
                    open_now = end >= _today_s
                    right = (f'<span style="font-size:0.68rem;font-weight:700;'
                             f'color:{"#B5321F" if open_now else GRAY};white-space:nowrap;">'
                             f'{"의견접수 중" if open_now else "예고 종료"} · ~{end}</span>')
                else:
                    right = (f'<span style="font-size:0.7rem;color:{GRAY};white-space:nowrap;">'
                             f'{r["date"] or "—"}</span>')
                rows += (
                    f'<a class="kw-link" href="{r["링크"]}" target="_blank">'
                    f'<div class="kw-row" style="align-items:center;">'
                    f'<span style="font-size:0.66rem;font-weight:800;color:#fff;background:{c};'
                    f'border-radius:4px;padding:2px 7px;margin-right:9px;white-space:nowrap;'
                    f'min-width:58px;text-align:center;">{r["유형"]}</span>'
                    f'<span class="kw-name" style="flex:1;font-size:0.83rem;">{r["제목"][:56]}</span>'
                    f'<span style="margin-left:8px;">{right}</span></div></a>')
            st.markdown(f'<div class="card" style="padding:8px 16px;">{rows}</div>',
                        unsafe_allow_html=True)
            # 관련 건이 10건을 넘으면 나머지도 볼 수 있어야 한다 (예전엔 무관 건만 노출됐다)
            if len(rel) > 10:
                with st.expander(f"관련 건 나머지 {len(rel) - 10}건 보기"):
                    for r in rel[10:]:
                        st.markdown(f"- [{r['제목']}]({r['링크']})  ·  {r['유형']} · "
                                    f"{r.get('예고기간') or r['date'] or '날짜미상'}")
            with st.expander(f"관련도 낮은 나머지 {len(regs) - len(rel)}건 보기"):
                for r in [x for x in regs if not x["관련"]][:20]:
                    st.markdown(f"- [{r['제목']}]({r['링크']})  ·  {r['출처']}")
        elif _failed:
            st.info("수집에 실패해 표시할 항목이 없습니다 — 위 오류를 확인하세요.")
        else:
            st.info(f"게시판 {sum(v['수집'] for v in reg_status.values())}건을 수집했지만 "
                    "그중 ETF·자본시장 관련 건이 없습니다 — 수집 실패가 아니라 "
                    "해당 기간에 관련 발표가 없었다는 뜻입니다.")
        st.caption("금융위원회 보도자료 3페이지·입법예고/규정변경예고 6페이지 실시간 수집 (1시간 캐시) · "
                   "입법예고는 건수가 적고 자본시장 관련이 뒤쪽까지 흩어져 있어 더 깊이 봅니다 · "
                   "날짜는 첨부파일명 기준이라 일부는 미상으로 표시됩니다.")
    with c2:
        sub_header("02", "규제 관련 보도")
        if reg_news:
            rows = "".join(
                f'<a class="kw-link" href="{n["링크"]}" target="_blank"><div class="kw-row">'
                f'<span class="kw-name" style="flex:1;font-size:0.8rem;">{n["제목"][:52]}</span>'
                f'<span style="font-size:0.7rem;color:{GRAY};white-space:nowrap;">{n["date"]}</span>'
                f'</div></a>' for n in reg_news[:8])
            st.markdown(f'<div class="card" style="padding:8px 16px;">{rows}</div>',
                        unsafe_allow_html=True)
        else:
            st.info("규제 뉴스를 불러오지 못했습니다.")
        st.caption("구글 뉴스 RSS · 보도자료가 놓친 건을 보완합니다.")

    # ── 근거 법령 현황 (국가법령정보센터 OpenAPI)
    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    sub_header("03", "근거 법령 현황", "국가법령정보센터 · 발표가 아니라 시행일 기준")
    st.markdown(
        f'<div style="font-size:0.76rem;color:{MUTED};line-height:1.65;'
        f'border-left:3px solid {BRAND};background:{BRAND_SOFT};'
        f'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:12px;">'
        f'보도자료는 <b>발표</b>를 보여주지만, 규제는 <b>시행일</b>부터 적용됩니다 — '
        f'시행 전후로 상품 메시지가 달라져야 하므로 시행일을 함께 봅니다.</div>',
        unsafe_allow_html=True)
    laws, laws_live = load_laws()
    if laws:
        _today = dt.date.today().isoformat()
        rows = ""
        for l in laws:
            시행 = l.get("시행일") or "—"
            future = 시행 > _today
            badge = ('<span style="font-size:0.64rem;font-weight:800;color:#fff;background:#B5321F;'
                     'border-radius:4px;padding:2px 7px;margin-left:7px;">시행 예정</span>' if future else "")
            rows += (
                f'<a class="kw-link" href="{l["링크"]}" target="_blank">'
                f'<div class="kw-row" style="align-items:center;">'
                f'<span style="font-size:0.66rem;font-weight:700;color:#475467;background:#F2F4F7;'
                f'border-radius:4px;padding:2px 7px;margin-right:9px;white-space:nowrap;'
                f'min-width:60px;text-align:center;">{l["구분"]}</span>'
                f'<span class="kw-name" style="flex:1;font-size:0.84rem;">'
                f'{l.get("약칭") or l["법령명"]}{badge}</span>'
                f'<span style="font-size:0.72rem;color:{GRAY};white-space:nowrap;margin-left:8px;">'
                f'{l["제개정"]} · 공포 {l["공포일"]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:{NAVY};white-space:nowrap;'
                f'margin-left:12px;">시행 {시행}</span></div></a>')
        st.markdown(f'<div class="card" style="padding:8px 16px;">{rows}</div>', unsafe_allow_html=True)
        _future = [l for l in laws if (l.get("시행일") or "") > _today]
        if _future:
            st.info("**시행 예정 법령이 있습니다** — "
                    + " · ".join(f'{l.get("약칭") or l["법령명"]}({l["시행일"]} 시행)' for l in _future)
                    + "\n\n시행일 전후로 상품 설명·광고 문구 검토가 필요할 수 있습니다.")
        st.caption("국가법령정보센터 OpenAPI · 현행 법령 기준 (1일 캐시) · "
                   "LAW_OC 환경변수에 본인 OC를 넣으면 공개 테스트 계정 대신 사용됩니다.")
    else:
        st.info("법령 정보를 불러오지 못했습니다 — 국가법령정보센터 응답을 확인해주세요.")

    st.write("")
    st.caption(
        "ⓘ 이 탭은 **발표된 규제 동향(금융위)**과 **근거 법령의 현행 상태(국가법령정보센터)**를 함께 봅니다. "
        "다만 개별 조문이 우리 상품에 갖는 의미와 컴플라이언스 판단은 담당 부서 확인이 필요합니다.")

st.write("")
st.caption(
    "ⓘ 시그널 보드·주간 수익률·섹터 수급·ETF 개인 순매수·순자산(KRX), 검색량(네이버 데이터랩), "
    "뉴스(구글)·규제(금융위), 채널 콘텐츠(공식 홈페이지·유튜브·블로그 RSS)는 모두 실데이터입니다. "
    "주간 배치: weekly_batch.py · etf_batch.py · channel_batch.py · sector_universe.py"
)
