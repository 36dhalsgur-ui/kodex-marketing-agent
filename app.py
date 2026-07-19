"""KODEX 마케팅 AI Agent — 홈 + 채널 탭 구조.

워크플로: 모니터링(시장 트렌드·채널) → 마케팅 효과 측정(DiD) → 주간 리포트.
DiD는 KODEX 처치군 고정 · 동일테마 경쟁 ETF 평균 대조군 · 8주 베이스라인 ·
Z-score→Sigmoid 0~100점 설계를 따른다.
"""

import datetime as dt
import importlib
import json
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
    "build_insights", "fetch_youtube", "fetch_datalab", "fetch_weekly_market", "theme_trend_table",
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
    return D.fetch_youtube(n_per_channel=3)


@st.cache_data
def load_theme_flows():
    return D.demo_theme_flows()


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

    # ── 테마 검색량 — 네이버 데이터랩 주간 검색량의 전주 대비 증감
    search_deltas, search_live = load_theme_search()

    def naver_news_link(query: str) -> str:
        return "https://search.naver.com/search.naver?where=news&query=" + quote(query)

    def search_row(name: str) -> str:
        v = search_deltas.get(name)
        if v is None:
            return ""
        s_cls = "kw-rise" if v >= 0 else "kw-fall"
        return (
            f'<a class="kw-link" href="{naver_news_link(name + " ETF")}" target="_blank">'
            f'<div class="kw-row"><span class="kw-name">{name} ↗</span>'
            f'<span class="kw-badge {s_cls}">검색 {v:+.1f}%</span></div></a>'
        )

    names = [g for g, _ in D.THEME_SEARCH_GROUPS]
    names.sort(key=lambda n: -(search_deltas.get(n) or 0))
    mid = (len(names) + 1) // 2
    col_a = "".join(search_row(n) for n in names[:mid])
    col_b = "".join(search_row(n) for n in names[mid:])
    live_tag = "데이터랩 실데이터" if search_live else "데모 — NAVER API 키 설정 시 실데이터"
    st.markdown(
        f'<div class="card"><div class="card-title">테마 검색량 '
        f'<span style="font-size:0.7rem;color:{FAINT};font-weight:600;">네이버 데이터랩 주간 검색량 · 전주 대비 증감 · {live_tag}</span></div>'
        f'<div class="kw-cols"><div class="kw-col">{col_a}</div><div class="kw-col">{col_b}</div></div>'
        f'<div style="font-size:0.7rem;color:{GRAY};margin-top:10px;">'
        f'키워드를 클릭하면 네이버 뉴스 검색으로 이동합니다</div></div>',
        unsafe_allow_html=True,
    )
    st.write("")

    t1, t2 = st.columns([6, 6], gap="large")
    with t1:
        srt = theme_tbl.sort_values("수익률")
        bar_colors = [RED if v >= 0 else COOL for v in srt["수익률"]]
        fig_th = go.Figure(
            go.Bar(x=srt["수익률"], y=srt["테마"], orientation="h", marker_color=bar_colors,
                   text=[f"{v:+.1f}%" for v in srt["수익률"]], textposition="outside",
                   cliponaxis=False,
                   hovertemplate="%{y}<br>주간 수익률 %{x:.2f}%<extra></extra>")
        )
        fig_th = base_layout(fig_th, height=430)
        fig_th.update_layout(title=dict(text=f"{sel_week} 테마별 주간 수익률", font=dict(size=15)))
        fig_th.update_xaxes(
            ticksuffix="%",
            range=[float(srt["수익률"].min()) * 1.35 - 0.3, float(srt["수익률"].max()) * 1.3 + 0.3],
        )
        st.plotly_chart(fig_th, use_container_width=True)
        kospi_w = next((m["weekly"] for m in load_weekly_market() if m["name"] == "코스피"), None)
        if kospi_w is not None:
            st.caption(f"해석 기준선 — 같은 기간 코스피 {kospi_w:+.1f}% (홈 탭 시장 요약 참조)")
    with t2:
        fig_sc = go.Figure(
            go.Scatter(
                x=theme_tbl["수익률"], y=theme_tbl["평균강도"],
                mode="markers+text", text=theme_tbl["테마"], textposition="top center",
                textfont=dict(size=11, color="#4B5468"),
                marker=dict(
                    size=(theme_tbl["순매수합"].abs() / theme_tbl["순매수합"].abs().max() * 34 + 10),
                    color=[RED if m > 0 else COOL for m in theme_tbl["모멘텀"]],
                    opacity=0.75, line=dict(width=1, color="white"),
                ),
                hovertemplate="<b>%{text}</b><br>수익률 %{x:.2f}% · 평균 매수강도 %{y:.2f}%<extra></extra>",
            )
        )
        fig_sc = base_layout(fig_sc, height=430)
        fig_sc.update_layout(
            title=dict(text="수익률 × 매수강도 맵  <span style='font-size:12px;color:#98A2B3'>버블 크기 = 순매수 규모 · 붉은색 = 전주보다 가속</span>", font=dict(size=15)),
            xaxis_title="주간 수익률(%)", yaxis_title="평균 매수강도(%)",
        )
        fig_sc.update_xaxes(showgrid=True, gridcolor="#F0F2F7", zeroline=True, zerolinecolor="#D9DEE9")
        fig_sc.update_yaxes(zeroline=True, zerolinecolor="#D9DEE9")
        st.plotly_chart(fig_sc, use_container_width=True)

    rising = theme_tbl.sort_values("점수", ascending=False).head(3)
    falling = theme_tbl.sort_values("점수").head(2)
    p1, p2 = st.columns(2, gap="medium")
    with p1:
        rows = "".join(
            f'<div class="kw-row"><span class="kw-name"><span style="color:{RED};">▲</span> {r.테마}</span>'
            f'<span style="color:#475467;font-size:0.82rem;font-variant-numeric:tabular-nums;">전주 {r.전주수익률:+.1f}% → 금주 {r.수익률:+.1f}%</span>'
            f'<span class="kw-badge kw-rise">{flow_state(r.전주수익률, r.수익률)}</span></div>'
            for r in rising.itertuples()
        )
        st.markdown(f'<div class="card"><div class="card-title">라이징 테마</div>{rows}</div>', unsafe_allow_html=True)
    with p2:
        rows = "".join(
            f'<div class="kw-row"><span class="kw-name"><span style="color:{COOL};">▼</span> {r.테마}</span>'
            f'<span style="color:#475467;font-size:0.82rem;font-variant-numeric:tabular-nums;">전주 {r.전주수익률:+.1f}% → 금주 {r.수익률:+.1f}%</span>'
            f'<span class="kw-badge kw-fall">{flow_state(r.전주수익률, r.수익률)}</span></div>'
            for r in falling.itertuples()
        )
        st.markdown(f'<div class="card"><div class="card-title">하락·정체 테마</div>{rows}</div>', unsafe_allow_html=True)

    st.write("")
    live_badge = "실데이터" if datalab_live else "데모 — NAVER_CLIENT_ID/SECRET 설정 시 실데이터"
    st.markdown(
        f'<div class="sec-tag">NAVER DATALAB</div>'
        f'<div style="font-size:1.02rem;font-weight:800;">브랜드 검색량 트렌드 <span style="font-size:0.7rem;color:{FAINT};font-weight:600;">({live_badge})</span></div>',
        unsafe_allow_html=True,
    )
    fig_dl = go.Figure()
    palette = {"KODEX": NAVY, "TIGER": "#E88D2A", "ACE": "#C0392B", "RISE": "#C89312", "ETF": "#A5B1C9"}
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
# ② 채널 모니터링 — 유튜브(실썸네일) + 뉴스
# ──────────────────────────────────────────────
with tab_channel:
    st.write("")
    section_header("STEP 2 · MONITOR", "채널 모니터링", "8개 ETF 브랜드의 유튜브 최신 콘텐츠와 뉴스 이슈를 수집합니다. 여기서 감지된 마케팅이 ③ 효과 측정의 입력이 됩니다.")
    st.write("")

    st.markdown('<div class="sec-tag">YOUTUBE · LIVE</div><div style="font-size:1.02rem;font-weight:800;margin-bottom:10px;">브랜드 유튜브 최신 영상</div>', unsafe_allow_html=True)

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
    "ⓘ 데모 모드: 순매수·테마·뉴스 데이터는 샘플이며 유튜브·지수·환율은 실시간 수집입니다. "
    "실운영 시 KRX·뉴스 크롤링·LLM 연동부로 교체됩니다."
)
