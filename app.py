"""KODEX 마케팅 AI Agent — 홈 + 채널 탭 구조.

워크플로: 모니터링(시장 트렌드·채널) → 마케팅 효과 측정(DiD) → 주간 리포트.
DiD는 KODEX 처치군 고정 · 동일테마 경쟁 ETF 평균 대조군 · 8주 베이스라인 ·
Z-score→Sigmoid 0~100점 설계를 따른다.
"""

import datetime as dt
import importlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D

# 배포 환경 핫리로드 시 data 모듈이 구버전으로 캐시되면 필수 함수가 없어
# 앱 전체가 죽는다 — 필수 속성 누락 시 강제 재로드로 자가 복구한다.
_REQUIRED_ATTRS = (
    "kodex_etfs", "control_group", "did_series", "did_score",
    "build_insights", "fetch_youtube", "fetch_datalab", "fetch_weekly_market", "fetch_news_mentions",
    "NEWS_KW_PATTERNS", "fetch_blogs", "BRAND_BLOGS", "fetch_partners", "PARTNER_CHANNELS", "ETF_CONTENT_PAT",
    "theme_signal_board", "demo_theme_flows", "signal_label",
    "DATALAB_GROUPS", "ISSUERS", "BASELINE_WEEKS", "ZSCORE_WINDOW", "LAPLACE_ALPHA",
)
if any(not hasattr(D, a) for a in _REQUIRED_ATTRS):
    D = importlib.reload(D)


def news_link(query: str) -> str:
    """구글 뉴스 검색 링크 (data 모듈 버전과 무관한 자체 폴백)."""
    return f"https://news.google.com/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR%3Ako"


# ──────────────────────────────────────────────
# 페이지 설정 & 스타일
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="KODEX 마케팅 AI Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

INK = "#101828"
MUTED = "#667085"
FAINT = "#98A2B3"
LINE = "#E4E7EC"
NAVY = "#16244D"
RED = "#F04452"
COOL = "#3182F6"
GRAY = MUTED
BG_CARD = "#FFFFFF"

st.markdown(
    f"""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    html, body, [class*="css"] {{
        font-family: 'Pretendard', -apple-system, sans-serif;
        color: {INK};
    }}
    .block-container {{ padding-top: 1.5rem; padding-bottom: 3.5rem; max-width: 1280px; }}
    #MainMenu, footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{ background: #FAFBFC; border-right: 1px solid {LINE}; }}

    button[data-baseweb="tab"] {{ font-weight: 700; }}
    button[data-baseweb="tab"] p {{ font-size: 0.92rem !important; }}

    .agent-overline {{
        font-size: 0.66rem; font-weight: 700; letter-spacing: 0.16em;
        color: {FAINT}; margin-bottom: 6px;
    }}
    .agent-title {{
        font-size: 1.5rem; font-weight: 800; color: {INK};
        letter-spacing: -0.02em; line-height: 1.2;
    }}
    .agent-sub {{ font-size: 0.85rem; color: {MUTED}; margin-top: 5px; }}

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

    /* 시그널 보드 */
    table.sig-table {{ width: 100%; border-collapse: collapse; }}
    table.sig-table th {{
        font-size: 0.64rem; font-weight: 700; letter-spacing: 0.08em; color: #475467;
        text-transform: uppercase; text-align: right; padding: 6px 10px;
        border-bottom: 1px solid {LINE};
    }}
    table.sig-table th:first-child {{ text-align: left; }}
    table.sig-table td {{
        font-size: 0.87rem; padding: 10px; border-bottom: 1px solid #F2F4F7;
        text-align: right; font-variant-numeric: tabular-nums; color: #1F2937;
    }}
    table.sig-table td:first-child {{ text-align: left; font-weight: 700; color: {INK}; }}
    table.sig-table tr:last-child td {{ border-bottom: none; }}
    .sig-pos {{ color: #D63C48; font-weight: 600; }}
    .sig-neg {{ color: #2A6FDB; font-weight: 600; }}
    table.sig-table td.flow-cell {{
        font-size: 0.74rem; color: {MUTED}; line-height: 1.7;
        font-weight: 500; text-align: right;
    }}

    .sec-tag {{
        font-size: 0.66rem; font-weight: 700; letter-spacing: 0.16em;
        color: {NAVY}; margin-bottom: 8px;
    }}
    .sec-title {{ font-size: 1.3rem; font-weight: 800; color: {INK}; letter-spacing: -0.02em; }}
    .sec-desc {{ font-size: 0.85rem; color: {MUTED}; margin-top: 4px; }}

    .card {{
        background: {BG_CARD}; border: 1px solid {LINE}; border-radius: 12px;
        padding: 18px 20px; height: 100%;
    }}
    .card-title {{ font-size: 0.92rem; font-weight: 700; color: {INK}; margin-bottom: 10px; }}

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


def base_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Pretendard, sans-serif", size=12.5, color="#344054"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#EEF1F5", zeroline=False),
    )
    return fig


# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_weekly_market():
    return D.fetch_weekly_market()


@st.cache_data
def load_netbuy():
    return D.add_intensity(D.demo_netbuy_data())


@st.cache_data
def load_theme_returns():
    return D.demo_theme_returns()


@st.cache_data(ttl=1800)
def load_youtube():
    return D.fetch_youtube(n_per_channel=8)


@st.cache_data(ttl=1800)
def load_blogs():
    return D.fetch_blogs(n_per_blog=6)


@st.cache_data(ttl=1800)
def load_partners():
    return D.fetch_partners(n_per_source=10)


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
def load_datalab():
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
    netbuy_df = load_netbuy()
    weeks = list(dict.fromkeys(netbuy_df["주차"]))
    sel_week = st.selectbox("분석 주차", weeks[1:][::-1], index=0)
    top_n = st.slider("순매수강도 TOP N", 5, 20, 15)

    st.markdown("---")
    up = st.file_uploader("순매수 엑셀 업로드", type=["xlsx"], help="컬럼: 주차·종목명·테마·운용사·순매수액·순자산")
    if up is not None:
        try:
            netbuy_df = D.add_intensity(pd.read_excel(up))
            weeks = list(dict.fromkeys(netbuy_df["주차"]))
            st.success("업로드 데이터로 분석합니다.")
        except Exception as e:
            st.error(f"파일 형식 오류: {e}")
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


@st.cache_data
def build_did_board(df: pd.DataFrame, week: str) -> pd.DataFrame:
    """전 KODEX ETF의 금주 DiD 점수 보드."""
    rows = []
    for name in D.kodex_etfs():
        controls = D.control_group(name)
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
datalab_df, datalab_live = load_datalab()

# ──────────────────────────────────────────────
# 헤더 + 지수 스트립 (2줄)
# ──────────────────────────────────────────────
st.markdown(
    '<div class="agent-overline">MARKETING INTELLIGENCE · WEEKLY MONITOR</div>'
    '<div class="agent-title">KODEX 마케팅 AI Agent</div>'
    '<div class="agent-sub">모니터링 → 마케팅 효과 측정(DiD) → 주간 리포트 — 채널 탭 기반 통합 분석</div>',
    unsafe_allow_html=True,
)


st.write("")

# ══════════════════════════════════════════════
# 탭 구조 — 모니터링이 먼저, 효과 측정(DiD)은 그 뒤
# ══════════════════════════════════════════════
tab_home, tab_trend, tab_channel, tab_did, tab_report = st.tabs(
    ["홈", "① 시장 트렌드", "② 채널 모니터링", "③ 마케팅 효과 측정", "④ 주간 리포트"]
)

# ──────────────────────────────────────────────
# 홈 — 금주 요약 KPI
# ──────────────────────────────────────────────
with tab_home:
    st.write("")
    section_header("HOME", f"{sel_week} 요약", "각 탭의 핵심 지표를 한눈에 — 상세 분석은 ①~④ 탭에서.")

    # 금주 시장 요약 — 주간(5거래일) 등락률
    weekly_chips = ""
    for m in load_weekly_market():
        up = m["weekly"] >= 0
        cls = "idx-up" if up else "idx-down"
        arrow = "▲" if up else "▼"
        weekly_chips += (
            f'<div class="idx-card"><div class="idx-name">{m["name"]}</div>'
            f'<div class="idx-val {cls}">{m["weekly"]:+.1f}%</div>'
            f'<div class="idx-chg" style="color:{FAINT};">{arrow} 현재 {m["level"]}</div></div>'
        )
    st.markdown(
        f'<div class="idx-group">금주 시장 요약 · 최근 5거래일 등락률</div>'
        f'<div class="idx-strip">{weekly_chips}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    top_theme = theme_tbl.sort_values("점수", ascending=False).iloc[0]
    top_flow = wk.nlargest(1, "매수강도").iloc[0]
    scored = did_board.dropna(subset=["score"]).sort_values("score", ascending=False) if len(did_board) else did_board
    yt_total = sum(len(v) for v in youtube.values())

    k1, k2, k3, k4 = st.columns(4, gap="medium")
    k1.markdown(
        f'<div class="kpi-card"><div class="kpi-label">라이징 테마 · ①</div>'
        f'<div class="kpi-value">{top_theme["테마"]}</div>'
        f'<div class="kpi-sub">전주 {top_theme["전주수익률"]:+.1f}% → 금주 {top_theme["수익률"]:+.1f}% · {flow_state(top_theme["전주수익률"], top_theme["수익률"])}</div></div>',
        unsafe_allow_html=True,
    )
    k2.markdown(
        f'<div class="kpi-card"><div class="kpi-label">순매수강도 1위 · ③</div>'
        f'<div class="kpi-value" style="font-size:1.02rem;">{top_flow["종목명"]}</div>'
        f'<div class="kpi-sub">매수강도 {top_flow["매수강도"]:+.2f}%</div></div>',
        unsafe_allow_html=True,
    )
    if len(scored):
        best = scored.iloc[0]
        k3.markdown(
            f'<div class="kpi-card"><div class="kpi-label">KODEX DiD 최고점 · ③</div>'
            f'<div class="kpi-value" style="font-size:1.02rem;">{best["종목명"]}</div>'
            f'<div class="kpi-sub">마케팅 효과 {best["score"]:.0f}점 / 100</div></div>',
            unsafe_allow_html=True,
        )
    else:
        k3.markdown(
            '<div class="kpi-card"><div class="kpi-label">KODEX DiD · ③</div>'
            '<div class="kpi-value" style="font-size:1.02rem;">산출 대상 없음</div>'
            '<div class="kpi-sub">데이터 업로드 후 재계산</div></div>',
            unsafe_allow_html=True,
        )
    k4.markdown(
        f'<div class="kpi-card"><div class="kpi-label">유튜브 신규 영상 · ②</div>'
        f'<div class="kpi-value">{yt_total}건</div>'
        f'<div class="kpi-sub">8개 브랜드 채널 최근 수집분</div></div>',
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown(
        f'<div class="card"><div class="card-title">워크플로</div>'
        f'<div style="font-size:0.85rem;color:#475467;line-height:1.8;">'
        f'<b style="color:{NAVY};">① 시장 트렌드</b> — 뉴스 키워드·테마 수익률·검색량으로 시장 방향 진단 &nbsp;→&nbsp; '
        f'<b style="color:{NAVY};">② 채널 모니터링</b> — 8개 브랜드 유튜브·뉴스로 경쟁사 마케팅 감지 &nbsp;→&nbsp; '
        f'<b style="color:{NAVY};">③ 마케팅 효과 측정</b> — 감지된 마케팅의 순매수 효과를 DiD로 검증 &nbsp;→&nbsp; '
        f'<b style="color:{NAVY};">④ 주간 리포트</b> — 종합 인사이트·차주 액션 도출</div></div>',
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────
# ① 시장 트렌드
# ──────────────────────────────────────────────
with tab_trend:
    st.write("")
    section_header("STEP 1 · MONITOR", "시장 트렌드", "섹터 단계 진단·테마 수익률·검색량으로 시장이 어디로 움직이는지 파악합니다.")
    st.write("")

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
        '<path d="M 40 108 C 100 104, 155 90, 210 70" fill="none" stroke="#B3730A" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 210 70 C 280 44, 350 24, 420 20" fill="none" stroke="#D63C48" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 420 20 C 470 18, 520 34, 560 54" fill="none" stroke="#2A6FDB" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M 560 54 C 610 76, 680 98, 740 108" fill="none" stroke="#98A2B3" stroke-width="5" stroke-linecap="round"/>'
        # 단계명
        '<text x="120" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#B3730A">① 태동기</text>'
        '<text x="315" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#D63C48">② 확산기</text>'
        '<text x="490" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#2A6FDB">③ 과열기</text>'
        '<text x="650" y="142" text-anchor="middle" font-size="13.5" font-weight="800" fill="#98A2B3">④ 쇠퇴기</text>'
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
        '<text x="120" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">콘텐츠 기획 착수 · 소재 선점</text>'
        '<text x="120" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">관련 ETF 라인업 점검</text>'
        '<text x="315" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">광고 · 콘텐츠 집중 집행</text>'
        '<text x="315" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">푸시 상품 전면 배치</text>'
        '<text x="490" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">마케팅 수확 지속 (수요 정점)</text>'
        '<text x="490" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">적립식 · 분산 소구 병행</text>'
        '<text x="650" y="196" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">노출 최소화</text>'
        '<text x="650" y="211" text-anchor="middle" font-size="11" font-weight="800" fill="#101828">수급 재유입 모니터링</text>'
        "</svg>"
    )
    st.markdown(
        f'<div class="card"><div class="card-title">ETF 테마 단계 진단</div>'
        f'<div style="font-size:0.84rem;color:#475467;line-height:1.7;">'
        f'테마에는 수명주기가 있고, <b style="color:{NAVY};">단계마다 마케터가 해야 할 행동이 다릅니다.</b> '
        f'아래 시그널 보드가 각 테마의 현재 단계를 매주 진단합니다.</div>'
        f"{cycle_svg}</div>",
        unsafe_allow_html=True,
    )
    st.write("")

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

        def stage_rows(rows, decline_order=False):
            # 기본: RS모멘텀 내림차순 / 쇠퇴기: 외국인·연기금 매수 금액 내림차순 (재매집 후보 상단)
            if decline_order:
                rows = sorted(rows, key=lambda x: -smart_buy(x))
            else:
                rows = sorted(rows, key=lambda x: -(x.get("RS모멘텀") or -99))
            out = ""
            for r in rows:
                has_rrg = r.get("RS수준") is not None
                note = r.get("비고") or r.get("수급비고") or ""
                note_html = f'<br><span style="font-size:0.66rem;color:{FAINT};">{note}</span>' if note else ""
                out += (
                    f'<tr><td>{r["섹터"]}<br><span style="font-size:0.68rem;color:{FAINT};font-weight:500;">{r.get("KODEX", "")}</span>{note_html}</td>'
                    + (
                        f'<td><span style="font-size:1rem;font-weight:800;">{signed(r["RS수준"])}</span><br>{lvl_word(r["RS수준"])}</td>'
                        f'<td><span style="font-size:1rem;font-weight:800;">{signed(r["RS모멘텀"])}</span><br>{mom_word(r["RS모멘텀"])}</td>'
                        if has_rrg else '<td>—</td><td>—</td>'
                    )
                    + f'<td class="flow-cell">{flow_cell(r)}</td></tr>'
                )
            return out

        TABLE_HEAD = (
            f'<table class="sig-table"><thead>'
            # 위계를 보여주는 그룹 헤더 — 단계는 가격이 정하고, 수급은 확인용
            f'<tr><th style="border-bottom:none;"></th>'
            f'<th colspan="2" style="text-align:center;background:#F8F5FF;color:{NAVY};">단계 판정 근거 — 가격 (상대강도)</th>'
            f'<th style="border-bottom:none;"></th></tr>'
            f'<tr><th>섹터<br><span style="font-weight:500;">관련 KODEX 상품</span></th>'
            f'<th>RS수준<br><span style="font-weight:500;">시장 대비 강도 (반년 평균=0)</span></th>'
            f'<th>RS모멘텀<br><span style="font-weight:500;">강도의 방향 (+ 강해짐)</span></th>'
            f'<th style="color:{FAINT};">수급 참고<br><span style="font-weight:500;">13주(분기) 순매수</span></th></tr></thead><tbody>'
        )

        STAGES = [
            ("태동기", "kw-warn", "콘텐츠 기획 착수 · 소재 선점"),
            ("확산기", "kw-rise", "광고·콘텐츠 집중 집행"),
            ("과열기", "kw-fall", "마케팅 수확 지속 + 적립식·분산 소구 병행"),
        ]
        groups_html = ""
        for stage, badge, action in STAGES:
            rows = by_stage.get(stage, [])
            groups_html += (
                f'<div style="margin:16px 0 6px;">'
                f'<span class="kw-badge {badge}">{stage}</span> '
                f'<span style="font-size:0.78rem;color:#475467;font-weight:600;">({len(rows)}) → {action}</span></div>'
            )
            if rows:
                groups_html += TABLE_HEAD + stage_rows(rows) + "</tbody></table>"
            else:
                groups_html += f'<div style="font-size:0.76rem;color:{FAINT};padding:4px 2px;">해당 섹터 없음</div>'

        st.markdown(
            f'<div class="card"><div class="card-title">섹터 시그널 보드 '
            f'<span style="font-size:0.7rem;color:{FAINT};font-weight:600;">'
            f'{sb.get("asof", "")} 기준 · 벤치마크 {sb.get("benchmark", "KRX 300")} · 주 1회 갱신</span></div>'
            f'<div style="font-size:0.9rem;font-weight:700;color:{INK};margin-bottom:4px;">{summary}</div>'
            f'<div style="font-size:0.78rem;color:#475467;margin-bottom:6px;line-height:1.6;">'
            f'단계는 <b style="color:{NAVY};">가격(시장 대비 상대강도)만으로</b> 판정합니다. '
            f'수급(최근 13주 순매수)은 <b>판정과 별개로 자금이 실제로 어디로 움직였는지 보여주는 보조 지표</b>입니다. '
            f'쇠퇴기에선 <b>외국인·연기금 매수 강도가 높은 섹터가 상단에 배치됩니다.</b></div>'
            f"{groups_html}</div>",
            unsafe_allow_html=True,
        )

        decline = by_stage.get("쇠퇴기", []) + by_stage.get("관망", [])
        n_watch = sum(1 for r in decline if smart_buy(r) > 0)
        with st.expander(f"⚪ 쇠퇴기·관망 ({len(decline)}) — 외국인·연기금이 매수 중인 재매집 후보 {n_watch}개를 상단 배치"):
            st.markdown(
                TABLE_HEAD + stage_rows(decline, decline_order=True) + "</tbody></table>",
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
            fig_th = base_layout(fig_th, height=560)
            fig_th.update_layout(title=dict(
                text=f"섹터별 주간 수익률  <span style='font-size:12px;color:#98A2B3'>KRX 실데이터 · {wk_range}</span>",
                font=dict(size=15)))
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
            fig_sc = base_layout(fig_sc, height=560)
            fig_sc.update_layout(
                title=dict(text="주간 수익률 × 수급 맵  <span style='font-size:12px;color:#98A2B3'>붉은색 = 외국인·연기금 순매수, 파란색 = 순매도</span>", font=dict(size=15)),
                xaxis_title="주간 수익률(%)", yaxis_title="외국인+연기금 주간 순매수(억원)",
            )
            fig_sc.update_xaxes(showgrid=True, gridcolor="#F0F2F7", zeroline=True, zerolinecolor="#D9DEE9")
            fig_sc.update_yaxes(zeroline=True, zerolinecolor="#D9DEE9")
            st.plotly_chart(fig_sc, use_container_width=True)
        elif wk_rows:
            st.info("주간 수급 데이터가 없습니다 — 배치 재실행 후 표시됩니다.")


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
                    "이 수치가 올라가는 시점이 판매채널로의 ETF 확산·제휴 징후입니다. 토글을 끄면 전체 콘텐츠를 볼 수 있습니다.")
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
        st.markdown(
            '<div class="sec-tag">HOMEPAGE</div>'
            '<div style="font-size:1.02rem;font-weight:800;margin-bottom:2px;">공식 홈페이지 — 메인 배너</div>'
            f'<div style="font-size:0.72rem;color:#98A2B3;margin-bottom:10px;">각 사 홈페이지 첫 배너 = 지금 가장 미는 캠페인 · 클릭 시 배너 페이지 · '
            f'<span style="color:#C2333F;font-weight:700;">NEW</span> = 전주에 없던 배너</div>',
            unsafe_allow_html=True,
        )
        if ch_brands:
            hp_rows = ""
            for brand in D.ISSUERS:
                info = ch_brands.get(brand, {})
                banners = info.get("배너", [])
                if banners:
                    b = banners[0]
                    hp_rows += feed_row(brand, b["제목"][:52], brand_themes(brand), b["링크"],
                                        NEW_BADGE if b.get("NEW") else "")
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
            st.caption(f'공식 홈페이지 배너 주간 배치 수집 ({ch_data.get("asof", "")}) · 우측 = 배너·영상·글 제목에서 매칭된 콘텐츠 테마')
        else:
            st.info("배너 데이터가 없습니다 — 로컬에서 `python scripts/channel_batch.py` 실행 후 커밋하면 표시됩니다.")

        # ── ② 공식 유튜브 — 최신 영상 (썸네일 그리드)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        st.markdown('<div class="sec-tag">YOUTUBE · LIVE</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:10px;">공식 유튜브 — 최신 영상</div>', unsafe_allow_html=True)

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
            st.caption("유튜브 채널 RSS 실시간 수집 (30분 캐시) · API 키 없이 동작, YOUTUBE_API_KEY 설정 시 좋아요·댓글 확장 가능")
        else:
            st.info("유튜브 수집에 실패했습니다. 네트워크 상태를 확인해주세요.")

        # ── ③ 공식 블로그 — 최신 글 (브랜드별 묶음)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        st.markdown('<div class="sec-tag">BLOG · LIVE</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:10px;">공식 블로그 — 최신 글</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="sec-tag">NEWS</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:10px;">운용사 뉴스 이슈</div>', unsafe_allow_html=True)

        BRAND_STYLE = {
            "KODEX": "linear-gradient(135deg,#16244D 0%,#3B5BA5 100%)",
            "TIGER": "linear-gradient(135deg,#B45309 0%,#E88D2A 100%)",
            "ACE": "linear-gradient(135deg,#7F1D1D 0%,#C0392B 100%)",
            "SOL": "linear-gradient(135deg,#1E40AF 0%,#3B82F6 100%)",
            "HANARO": "linear-gradient(135deg,#166534 0%,#34B364 100%)",
            "RISE": "linear-gradient(135deg,#854D0E 0%,#C89312 100%)",
            "PLUS": "linear-gradient(135deg,#9A3412 0%,#D9480F 100%)",
            "TIMEFOLIO": "linear-gradient(135deg,#1F2937 0%,#4B5563 100%)",
        }

        def issuer_card(issuer: str) -> str:
            entries = [
                n if isinstance(n, dict) else {"title": n, "url": news_link(f"{issuer} ETF")}
                for n in D.ISSUER_NEWS[issuer]
            ]
            primary = entries[0]
            tag = primary["title"].split("—")[0].split(",")[0].strip()
            tag = tag if len(tag) <= 26 else tag[:25] + "…"
            grad = BRAND_STYLE.get(issuer, BRAND_STYLE["TIMEFOLIO"])
            html = (
                f'<div class="yt-card">'
                f'<a class="yt-thumb" href="{primary["url"]}" target="_blank" style="background:{grad};">'
                f'<span class="yt-chip">NEWS BRIEF</span>'
                f'<span><span class="yt-brand">{issuer}</span>'
                f'<div class="yt-tag">{tag}</div></span></a>'
                f'<div class="yt-body">'
                f'<a class="yt-title" href="{primary["url"]}" target="_blank">{primary["title"]}</a>'
            )
            if len(entries) > 1:
                html += f'<a class="yt-sub" href="{entries[1]["url"]}" target="_blank">{entries[1]["title"]} ↗</a>'
            html += "</div></div>"
            return html

        issuer_list = getattr(D, "ISSUERS", list(D.ISSUER_NEWS.keys()))
        for row_start in range(0, len(issuer_list), 4):
            row_cols = st.columns(4, gap="medium")
            for col, issuer in zip(row_cols, issuer_list[row_start : row_start + 4]):
                col.markdown(issuer_card(issuer), unsafe_allow_html=True)
            st.write("")

        # ── ⑤ 브랜드 검색량 (캠페인 → 관심 반응 확인)
        st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
        live_badge = "실데이터" if datalab_live else "데모 — NAVER_CLIENT_ID/SECRET 설정 시 실데이터"
        st.markdown(
            f'<div class="sec-tag">NAVER DATALAB</div>'
            f'<div style="font-size:1.02rem;font-weight:800;">브랜드 검색량 트렌드 <span style="font-size:0.7rem;color:{FAINT};font-weight:600;">({live_badge}) — 위 캠페인·콘텐츠가 실제 관심으로 이어졌는지 확인</span></div>',
            unsafe_allow_html=True,
        )
        fig_dl = go.Figure()
        palette = {"KODEX": NAVY, "TIGER": "#E88D2A", "ACE": "#C0392B", "RISE": "#C89312"}
        for g in D.DATALAB_GROUPS:
            sub = datalab_df[datalab_df["group"] == g]
            fig_dl.add_trace(go.Scatter(
                x=sub["date"], y=sub["ratio"], name=g, mode="lines",
                line=dict(color=palette.get(g, "#888"), width=2.5 if g == "KODEX" else 1.6),
            ))
        fig_dl = base_layout(fig_dl, height=300)
        fig_dl.update_layout(yaxis_title="검색량 지수")
        st.plotly_chart(fig_dl, use_container_width=True)

# ──────────────────────────────────────────────
# ③ 마케팅 효과 측정 — DiD (KODEX 중심 재설계)
# ──────────────────────────────────────────────
with tab_did:
    st.write("")
    section_header(
        "STEP 3 · MEASURE",
        "마케팅 효과 측정 — DiD 인과분석",
        "②에서 감지한 KODEX 마케팅이 실제 순매수에 미친 효과를 검증합니다. "
        "처치군은 KODEX ETF 고정, 대조군은 동일 테마 경쟁 ETF 평균 — 8주 베이스라인 · Z-score → 0~100점.",
    )
    st.write("")

    c_sel1, c_sel2 = st.columns([5, 7], gap="large")
    with c_sel1:
        treat = st.selectbox("처치군 — 마케팅한 KODEX ETF", D.kodex_etfs(),
                             index=D.kodex_etfs().index("KODEX 미국반도체"))
    auto_controls = D.control_group(treat)
    with c_sel2:
        controls = st.multiselect(
            "대조군 — 동일 테마 경쟁 ETF (자동 매핑, 수정 가능)",
            options=sorted(n for n, _, i in D.ETF_UNIVERSE if i != "KODEX"),
            default=auto_controls,
        )

    series = D.did_series(netbuy_df, treat, controls)
    sc = D.did_score(series, sel_week)

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
        fig_top = base_layout(fig_top, height=max(360, top_n * 27))
        fig_top.update_layout(title=dict(text=f"{sel_week} 순매수강도 TOP {top_n}", font=dict(size=15)))
        xmax = float(top["매수강도"].max())
        fig_top.update_xaxes(ticksuffix="%", range=[min(0, float(top["매수강도"].min()) * 1.2), xmax * 1.25])
        st.plotly_chart(fig_top, use_container_width=True)
        st.caption(f"진한 남색 = KODEX 상품 · 분석 대상 {len(wk)}개 ETF")

    with d2:
        st.markdown('<div class="card-title" style="font-size:1.02rem;">DiD 진단 — 8주 베이스라인 대비</div>', unsafe_allow_html=True)
        s1c, s2c = st.columns(2)
        dt_v = sc.get("delta_treat")
        dc_v = sc.get("delta_ctrl")
        s1c.markdown(
            f'<div class="did-step"><div class="did-step-no">STEP 1 · 처치군</div>'
            f'<div class="did-step-name">Δ처치 (베이스라인 대비)</div>'
            f'<div class="did-step-val">{dt_v:+.2f}%p</div>'
            f'<div class="did-step-desc">{treat[:20]}<br>금주 강도 − 직전 8주 평균</div></div>'
            if dt_v is not None else '<div class="did-step">산출 불가</div>',
            unsafe_allow_html=True,
        )
        s2c.markdown(
            f'<div class="did-step"><div class="did-step-no">STEP 2 · 대조군</div>'
            f'<div class="did-step-name">Δ대조군 평균</div>'
            f'<div class="did-step-val">{dc_v:+.2f}%p</div>'
            f'<div class="did-step-desc">{len(controls)}개 경쟁 ETF 평균<br>= 시장이 원래 움직인 만큼</div></div>'
            if dc_v is not None else
            '<div class="did-step"><div class="did-step-no">STEP 2 · 대조군</div>'
            '<div class="did-step-name">대조군 없음</div>'
            '<div class="did-step-desc">경쟁 ETF를 지정하면 시장효과가 제거됩니다</div></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        if sc.get("did") is not None:
            score = sc.get("score")
            if score is not None:
                verdict = "효과 우수" if score >= 70 else ("효과 양호" if score >= 55 else ("중립" if score >= 45 else "효과 미약"))
                st.markdown(
                    f'<div class="did-result"><div class="did-result-label">DiD {sc["did"]:+.2f}%p · Z {sc["z"]:+.2f} → 마케팅 효과 점수</div>'
                    f'<div class="did-result-val">{score:.0f}점 <span style="font-size:0.9rem;opacity:0.7;">/ 100 · {verdict}</span></div>'
                    f'<div class="score-track"><div class="score-fill" style="width:{score}%;"></div></div>'
                    f'<div class="did-result-note">시장 공통 효과 제거 후 순수 마케팅 효과 — 과거 {D.ZSCORE_WINDOW}주 분포 대비 상대 위치</div></div>',
                    unsafe_allow_html=True,
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
            marker_color=[NAVY if w == sel_week else "#C7CFDF" for w in series["주차"]],
        ))
        fig_did = base_layout(fig_did, height=220)
        fig_did.update_layout(title=dict(text="주차별 DiD 추이", font=dict(size=14)),
                              margin=dict(l=10, r=10, t=40, b=10))
        fig_did.update_yaxes(ticksuffix="%p")
        st.plotly_chart(fig_did, use_container_width=True)

    st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sec-tag">SCOREBOARD</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:8px;">전체 KODEX ETF — 금주 DiD 점수 보드</div>', unsafe_allow_html=True)
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
        "주간 리포트 — 종합 인사이트 & 차주 액션",
        "①~③의 수집·측정 결과를 근거로 자동 도출합니다. 특정 전략 프레임 없이 데이터 신호만 반영 — 규칙 기반이며 LLM 연동 시 이 지점만 교체됩니다.",
    )
    st.write("")

    ins = D.build_insights(theme_tbl, D.NEWS_KEYWORDS, did_board, youtube)

    st.markdown(
        f'<div class="card" style="background:{NAVY};border:none;color:white;">'
        f'<div class="did-result-label" style="margin-bottom:10px;">EXECUTIVE SUMMARY · {sel_week}</div>'
        + "".join(
            f'<div style="font-size:0.92rem;font-weight:600;line-height:1.7;">{i+1}. {s}</div>'
            for i, s in enumerate(ins["summary"])
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    r1, r2 = st.columns(2, gap="medium")
    with r1:
        rows = "".join(
            f'<div class="kw-row"><span class="kw-name">'
            f'<span style="color:{RED if s["type"] == "라이징" else COOL};">{"▲" if s["type"] == "라이징" else "▼"}</span> '
            f'{s["text"]}</span></div>'
            for s in ins["signals"]
        )
        st.markdown(f'<div class="card"><div class="card-title">시장 시그널</div>{rows}</div>', unsafe_allow_html=True)
    with r2:
        rows = "".join(
            f'<div class="kw-row"><span class="kw-name" style="font-weight:500;">{c}</span></div>'
            for c in ins["channel_eval"]
        )
        st.markdown(f'<div class="card"><div class="card-title">채널 평가</div>{rows}</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="sec-tag">NEXT WEEK</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:10px;">차주 액션 제안</div>', unsafe_allow_html=True)
    a_cols = st.columns(2, gap="medium")
    for i, act in enumerate(ins["actions"]):
        a_cols[i % 2].markdown(
            f'<div class="act-card"><span class="act-prio prio-{act["priority"]}">{act["priority"]}</span>'
            f'<div class="act-title">{act["title"]}</div>'
            f'<div class="act-row"><b>왜</b> — {act["why"]}</div>'
            f'<div class="act-row"><b>어떻게</b> — {act["how"]}</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    # 마크다운 리포트 다운로드
    md_lines = [f"# KODEX 마케팅 주간 리포트 — {sel_week}", "", "## 핵심 요약"]
    md_lines += [f"{i+1}. {s}" for i, s in enumerate(ins["summary"])]
    md_lines += ["", "## 시장 시그널"] + [f"- [{s['type']}] {s['text']}" for s in ins["signals"]]
    md_lines += ["", "## 채널 평가"] + [f"- {c}" for c in ins["channel_eval"]]
    md_lines += ["", "## 차주 액션"]
    for act in ins["actions"]:
        md_lines += [f"### [{act['priority']}] {act['title']}", f"- 왜: {act['why']}", f"- 어떻게: {act['how']}"]
    if len(did_board):
        cols_md = list(did_board.columns)
        table = ["| " + " | ".join(cols_md) + " |", "| " + " | ".join(["---"] * len(cols_md)) + " |"]
        table += ["| " + " | ".join(str(v) for v in row) + " |" for row in did_board.itertuples(index=False)]
        md_lines += ["", "## KODEX DiD 점수 보드"] + table
    st.download_button(
        "리포트 다운로드 (Markdown)",
        "\n".join(md_lines),
        file_name=f"kodex_weekly_report_{dt.date.today().isoformat()}.md",
        mime="text/markdown",
    )
    st.caption("ⓘ 인사이트는 수집 데이터 기반 규칙 엔진으로 생성됩니다. LLM API 연동 시 data.py의 build_insights()만 교체하면 됩니다.")

st.write("")
st.caption(
    "ⓘ 시그널 보드·주간 수익률·수급(KRX)·검색량(네이버 데이터랩)·뉴스(구글)·유튜브·지수·환율은 실데이터입니다. "
    "마케팅 효과 측정 탭의 순매수 데이터는 샘플이며, 엑셀 업로드 또는 실운영 연동 시 교체됩니다."
)
