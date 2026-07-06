"""KODEX 마케팅 AI Agent — 섹션형 대시보드.

핵심 섹션: ① 시장 순매수 분석(순매수강도 TOP15 + DiD 인과효과) ② 테마 분석.
보조 섹션: 시장 트렌드 키워드, 운용사 동향, AI 종합 인사이트.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D

# ──────────────────────────────────────────────
# 페이지 설정 & 스타일
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="KODEX 마케팅 AI Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#1E2761"
BLUE = "#3D5AF1"
RED = "#E8505B"
COOL = "#4A7CF0"
GRAY = "#8A93A6"
BG_CARD = "#FFFFFF"

st.markdown(
    f"""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    html, body, [class*="css"] {{
        font-family: 'Pretendard', -apple-system, sans-serif;
    }}
    .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1240px; }}
    #MainMenu, footer {{ visibility: hidden; }}

    /* 헤더 */
    .agent-header {{
        display: flex; align-items: baseline; gap: 14px; margin-bottom: 2px;
    }}
    .agent-title {{ font-size: 1.72rem; font-weight: 800; color: {NAVY}; letter-spacing: -0.5px; }}
    .agent-sub {{ font-size: 0.92rem; color: {GRAY}; }}

    /* 지수 스트립 */
    .idx-strip {{
        display: flex; gap: 10px; flex-wrap: wrap; margin: 14px 0 6px 0;
    }}
    .idx-card {{
        flex: 1; min-width: 150px; background: {NAVY}; border-radius: 12px;
        padding: 13px 16px; color: white;
    }}
    .idx-name {{ font-size: 0.76rem; opacity: 0.72; margin-bottom: 3px; }}
    .idx-val {{ font-size: 1.18rem; font-weight: 700; letter-spacing: -0.3px; }}
    .idx-chg {{ font-size: 0.8rem; font-weight: 600; margin-top: 2px; }}
    .idx-up {{ color: #FF8A93; }}
    .idx-down {{ color: #7FB3FF; }}

    /* 섹션 헤더 */
    .sec-tag {{
        display: inline-block; font-size: 0.7rem; font-weight: 700; color: {BLUE};
        background: rgba(61,90,241,0.09); border-radius: 6px; padding: 3px 9px;
        letter-spacing: 0.6px; margin-bottom: 6px;
    }}
    .sec-title {{ font-size: 1.28rem; font-weight: 800; color: #1A1F36; letter-spacing: -0.4px; }}
    .sec-desc {{ font-size: 0.87rem; color: {GRAY}; margin-top: 2px; }}

    /* 카드 */
    .card {{
        background: {BG_CARD}; border: 1px solid #E9ECF3; border-radius: 14px;
        padding: 18px 20px; height: 100%;
    }}
    .card-title {{ font-size: 0.95rem; font-weight: 700; color: #1A1F36; margin-bottom: 8px; }}
    .card-body {{ font-size: 0.86rem; color: #4B5468; line-height: 1.55; }}

    /* DiD 결과 */
    .did-step {{
        background: #F7F8FC; border: 1px solid #E9ECF3; border-radius: 12px;
        padding: 14px 16px; height: 100%;
    }}
    .did-step-no {{ font-size: 0.7rem; font-weight: 800; color: {BLUE}; letter-spacing: 0.8px; }}
    .did-step-name {{ font-size: 0.92rem; font-weight: 700; color: #1A1F36; margin: 3px 0 5px; }}
    .did-step-val {{ font-size: 1.25rem; font-weight: 800; color: {NAVY}; }}
    .did-step-desc {{ font-size: 0.76rem; color: {GRAY}; margin-top: 4px; line-height: 1.45; }}
    .did-result {{
        background: linear-gradient(135deg, {NAVY} 0%, #2E3E8F 100%);
        border-radius: 14px; padding: 20px 24px; color: white; margin-top: 4px;
    }}
    .did-result-label {{ font-size: 0.78rem; opacity: 0.75; letter-spacing: 0.5px; }}
    .did-result-val {{ font-size: 2.1rem; font-weight: 800; letter-spacing: -0.5px; }}
    .did-result-note {{ font-size: 0.8rem; opacity: 0.8; margin-top: 4px; line-height: 1.5; }}

    /* 키워드 칩 */
    .kw-row {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 9px 4px; border-bottom: 1px solid #F0F2F7; font-size: 0.88rem;
    }}
    .kw-name {{ font-weight: 600; color: #1A1F36; }}
    .kw-badge {{
        font-size: 0.72rem; font-weight: 700; border-radius: 6px; padding: 2px 8px;
    }}
    .kw-rise {{ background: rgba(232,80,91,0.1); color: {RED}; }}
    .kw-fall {{ background: rgba(74,124,240,0.12); color: {COOL}; }}
    .kw-flat {{ background: #F0F2F7; color: {GRAY}; }}

    /* 인사이트 카드 */
    .ins-card {{
        background: {BG_CARD}; border: 1px solid #E9ECF3; border-radius: 14px;
        padding: 18px 20px; height: 100%;
    }}
    .ins-icon {{ font-size: 1.5rem; }}
    .ins-title {{ font-size: 0.98rem; font-weight: 800; color: {NAVY}; margin: 8px 0 6px; }}
    .ins-body {{ font-size: 0.84rem; color: #4B5468; line-height: 1.6; }}

    hr.sec-divider {{ border: none; border-top: 1px solid #E9ECF3; margin: 2.2rem 0 1.6rem; }}
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
        font=dict(family="Pretendard, sans-serif", size=13, color="#1A1F36"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#F0F2F7", zeroline=False),
    )
    return fig


# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_indices():
    return D.fetch_live_indices()


@st.cache_data
def load_netbuy():
    return D.add_intensity(D.demo_netbuy_data())


@st.cache_data
def load_theme_returns():
    return D.demo_theme_returns()


# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### ⚙️ 분석 설정")
    netbuy_df = load_netbuy()
    weeks = list(dict.fromkeys(netbuy_df["주차"]))
    sel_week = st.selectbox("분석 주차", weeks[1:][::-1], index=0)
    top_n = st.slider("순매수강도 TOP N", 5, 20, 15)

    st.markdown("---")
    st.markdown("**DiD 인과분석 설정**")
    etf_names = sorted(netbuy_df["종목명"].unique())
    treat = st.selectbox(
        "처치군 (마케팅한 ETF)", etf_names, index=etf_names.index("KODEX 미국반도체")
    )
    treat_theme = netbuy_df.loc[netbuy_df["종목명"] == treat, "테마"].iloc[0]
    ctrl_candidates = ["(대조군 없음)"] + sorted(
        netbuy_df.loc[
            (netbuy_df["테마"] == treat_theme) & (netbuy_df["종목명"] != treat), "종목명"
        ].unique()
    )
    control = st.selectbox("대조군 (유사 지수 ETF)", ctrl_candidates, index=min(1, len(ctrl_candidates) - 1))

    st.markdown("---")
    up = st.file_uploader("순매수 엑셀 업로드", type=["xlsx"], help="컬럼: 주차·종목명·테마·운용사·순매수액·순자산")
    if up is not None:
        try:
            netbuy_df = D.add_intensity(pd.read_excel(up))
            st.success("업로드 데이터로 분석합니다.")
        except Exception as e:
            st.error(f"파일 형식 오류: {e}")
    else:
        st.caption("미업로드 시 데모 데이터로 동작합니다.")

# ──────────────────────────────────────────────
# 헤더 + 실시간 지수 스트립
# ──────────────────────────────────────────────
st.markdown(
    '<div class="agent-header"><span class="agent-title">📊 KODEX 마케팅 AI Agent</span>'
    '<span class="agent-sub">시장·경쟁사·수급을 하나의 대시보드에서 — 섹션형 통합 모니터링</span></div>',
    unsafe_allow_html=True,
)

idx_html = '<div class="idx-strip">'
for ix in load_indices():
    cls = "idx-up" if ix["up"] else "idx-down"
    arrow = "▲" if ix["up"] else "▼"
    idx_html += (
        f'<div class="idx-card"><div class="idx-name">{ix["name"]}</div>'
        f'<div class="idx-val">{ix["value"]}</div>'
        f'<div class="idx-chg {cls}">{arrow} {ix["change"].lstrip("+-")}</div></div>'
    )
idx_html += "</div>"
st.markdown(idx_html, unsafe_allow_html=True)
st.caption("실시간 지수·환율 (네이버 증권 기준, 5분 캐시) · 시장 마감 시 종가 표시")

st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)

# ══════════════════════════════════════════════
# SECTION 1 — 시장 순매수 분석 (핵심)
# ══════════════════════════════════════════════
section_header(
    "SECTION 1 · 핵심",
    "시장 순매수 분석 — 순매수강도 TOP15 & DiD 인과효과",
    "순매수를 전주 순자산 대비로 정규화해 수급 강도를 측정하고, 처치군·대조군 비교로 마케팅의 순효과를 분리합니다.",
)
st.write("")

wk = netbuy_df[netbuy_df["주차"] == sel_week].dropna(subset=["매수강도"])
top = wk.nlargest(top_n, "매수강도").sort_values("매수강도")

colors = [NAVY if "KODEX" in n else "#C3CBDC" for n in top["종목명"]]
fig_top = go.Figure(
    go.Bar(
        x=top["매수강도"],
        y=top["종목명"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in top["매수강도"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>매수강도 %{x:.2f}%<extra></extra>",
    )
)
fig_top = base_layout(fig_top, height=max(360, top_n * 28))
fig_top.update_layout(
    title=dict(text=f"{sel_week} 순매수강도 TOP {top_n}  <span style='font-size:12px;color:#8A93A6'>(주간 순매수액 ÷ 전주 순자산 × 100)</span>", font=dict(size=15)),
    xaxis_title=None, yaxis_title=None,
)
xmax = float(top["매수강도"].max())
fig_top.update_xaxes(ticksuffix="%", range=[min(0, float(top["매수강도"].min()) * 1.2), xmax * 1.25])

c1, c2 = st.columns([7, 5], gap="large")
with c1:
    st.plotly_chart(fig_top, use_container_width=True)
    st.caption(f"🔵 진한 색 = KODEX 상품 · 분석 대상 {len(wk)}개 ETF")

with c2:
    # DiD 계산
    def intensity(name: str, week: str):
        row = netbuy_df[(netbuy_df["종목명"] == name) & (netbuy_df["주차"] == week)]
        return float(row["매수강도"].iloc[0]) if len(row) and pd.notna(row["매수강도"].iloc[0]) else None

    w_idx = weeks.index(sel_week)
    prev_week = weeks[w_idx - 1] if w_idx > 0 else None

    t_now, t_prev = intensity(treat, sel_week), intensity(treat, prev_week) if prev_week else None
    t_delta = (t_now - t_prev) if (t_now is not None and t_prev is not None) else None

    has_ctrl = control != "(대조군 없음)"
    c_delta = None
    if has_ctrl and prev_week:
        c_now, c_prev = intensity(control, sel_week), intensity(control, prev_week)
        if c_now is not None and c_prev is not None:
            c_delta = c_now - c_prev

    st.markdown('<div class="card-title" style="font-size:1.02rem;">DiD 이중차분 — 마케팅 순효과 4단계 진단</div>', unsafe_allow_html=True)

    s1, s2 = st.columns(2)
    steps = [
        ("STEP 1", "매수강도 정규화", f"{t_now:+.2f}%" if t_now is not None else "—",
         f"{treat[:18]}<br>금주 매수강도"),
        ("STEP 2", "처치군 변화량", f"{t_delta:+.2f}%p" if t_delta is not None else "—",
         "금주 − 전주 매수강도"),
        ("STEP 3", "대조군 변화량", f"{c_delta:+.2f}%p" if c_delta is not None else "대조군 없음",
         f"{control[:18] if has_ctrl else '유사 지수 ETF 미지정'}"),
    ]
    for col, (no, nm, val, desc) in zip([s1, s2, s1], steps):
        col.markdown(
            f'<div class="did-step"><div class="did-step-no">{no}</div>'
            f'<div class="did-step-name">{nm}</div><div class="did-step-val">{val}</div>'
            f'<div class="did-step-desc">{desc}</div></div>',
            unsafe_allow_html=True,
        )
    with s2:
        if t_delta is not None and c_delta is not None:
            did = t_delta - c_delta
            verdict = "마케팅 순효과 양(+)" if did > 0 else "마케팅 순효과 음(−)"
            st.markdown(
                f'<div class="did-result"><div class="did-result-label">STEP 4 · DiD = 처치군 변화 − 대조군 변화</div>'
                f'<div class="did-result-val">{did:+.2f}%p</div>'
                f'<div class="did-result-note">{verdict} — 시장 공통 효과를 제거한 순수 인과효과</div></div>',
                unsafe_allow_html=True,
            )
        elif t_delta is not None:
            st.markdown(
                f'<div class="did-result"><div class="did-result-label">STEP 4 · 단순 변화량 (대조군 없음)</div>'
                f'<div class="did-result-val">Δ{t_delta:+.2f}%p</div>'
                f'<div class="did-result-note">대조군이 없어 시장효과가 제거되지 않은 값입니다. 유사 지수 ETF를 지정하세요.</div></div>',
                unsafe_allow_html=True,
            )

    # 처치군 vs 대조군 추이
    trend_names = [treat] + ([control] if has_ctrl else [])
    tr = netbuy_df[netbuy_df["종목명"].isin(trend_names)].dropna(subset=["매수강도"])
    fig_tr = go.Figure()
    for nm, color in zip(trend_names, [NAVY, "#C3CBDC"]):
        sub = tr[tr["종목명"] == nm]
        fig_tr.add_trace(
            go.Scatter(x=sub["주차"], y=sub["매수강도"], name=nm, mode="lines+markers",
                       line=dict(color=color, width=2.5), marker=dict(size=6))
        )
    fig_tr = base_layout(fig_tr, height=250)
    fig_tr.update_layout(
        title=dict(text="처치군 vs 대조군 매수강도 추이", font=dict(size=14)),
        legend=dict(orientation="h", yanchor="top", y=-0.25, x=0, font=dict(size=11)),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig_tr.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_tr, use_container_width=True)

st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)

# ══════════════════════════════════════════════
# SECTION 2 — 테마 분석 (핵심)
# ══════════════════════════════════════════════
section_header(
    "SECTION 2 · 핵심",
    "테마 분석 — 라이징 테마 & 자금 흐름",
    "테마별 수익률·순매수를 교차 분석해 시장이 어디로 움직이는지 파악하고, 차주 주목 테마를 도출합니다.",
)
st.write("")

theme_ret = load_theme_returns()
this_ret = theme_ret[theme_ret["주차"] == sel_week].set_index("테마")["수익률"]
prev_ret = theme_ret[theme_ret["주차"] == prev_week].set_index("테마")["수익률"] if prev_week else this_ret

theme_flow = (
    wk.groupby("테마")
    .agg(순매수합=("순매수액", "sum"), 평균강도=("매수강도", "mean"), 종목수=("종목명", "count"))
    .round(2)
)
theme_tbl = theme_flow.join(this_ret.rename("수익률")).reset_index()
theme_tbl["모멘텀"] = (theme_tbl["테마"].map(this_ret) - theme_tbl["테마"].map(prev_ret)).round(2)

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
        title=dict(text="수익률 × 매수강도 맵  <span style='font-size:12px;color:#8A93A6'>버블 크기 = 순매수 규모 · 붉은색 = 모멘텀 상승</span>", font=dict(size=15)),
        xaxis_title="주간 수익률(%)", yaxis_title="평균 매수강도(%)",
    )
    fig_sc.update_xaxes(showgrid=True, gridcolor="#F0F2F7", zeroline=True, zerolinecolor="#D9DEE9")
    fig_sc.update_yaxes(zeroline=True, zerolinecolor="#D9DEE9")
    st.plotly_chart(fig_sc, use_container_width=True)

# 라이징 / 하락 테마 & Gemini's Pick — 수익률과 모멘텀을 함께 반영한 종합 점수로 판별
theme_tbl["점수"] = theme_tbl["수익률"] + theme_tbl["모멘텀"]
rising = theme_tbl.sort_values("점수", ascending=False).head(3)
falling = theme_tbl.sort_values("점수").head(2)

p1, p2, p3 = st.columns([4, 4, 4], gap="medium")
with p1:
    rows = "".join(
        f'<div class="kw-row"><span class="kw-name">🔥 {r.테마}</span>'
        f'<span class="kw-badge kw-rise">수익률 {r.수익률:+.1f}% · 모멘텀 {r.모멘텀:+.1f}%p</span></div>'
        for r in rising.itertuples()
    )
    st.markdown(f'<div class="card"><div class="card-title">라이징 테마</div>{rows}</div>', unsafe_allow_html=True)
with p2:
    rows = "".join(
        f'<div class="kw-row"><span class="kw-name">🧊 {r.테마}</span>'
        f'<span class="kw-badge kw-fall">수익률 {r.수익률:+.1f}% · 모멘텀 {r.모멘텀:+.1f}%p</span></div>'
        for r in falling.itertuples()
    )
    st.markdown(f'<div class="card"><div class="card-title">하락·정체 테마</div>{rows}</div>', unsafe_allow_html=True)
with p3:
    pick_theme = rising.iloc[0]
    pick_etf = wk[(wk["테마"] == pick_theme["테마"]) & (wk["운용사"] == "KODEX")]
    pick_name = pick_etf.nlargest(1, "매수강도")["종목명"].iloc[0] if len(pick_etf) else f"{pick_theme['테마']} 대표 ETF"
    st.markdown(
        f'<div class="card" style="background:linear-gradient(135deg,{NAVY},#2E3E8F);border:none;color:white;">'
        f'<div class="card-title" style="color:white;">✨ Gemini\'s Pick — 차주 주목 ETF</div>'
        f'<div style="font-size:1.15rem;font-weight:800;margin:4px 0 8px;">{pick_name}</div>'
        f'<div style="font-size:0.83rem;opacity:0.85;line-height:1.6;">'
        f'선정 배경: <b>{pick_theme["테마"]}</b> 테마가 수익률 {pick_theme["수익률"]:+.1f}%, '
        f'모멘텀 {pick_theme["모멘텀"]:+.1f}%p로 강세 전환. 순매수 유입이 동반돼 '
        f'차주 푸시 상품으로 적합.</div></div>',
        unsafe_allow_html=True,
    )

with st.expander("테마별 상세 데이터 보기"):
    st.dataframe(
        theme_tbl.drop(columns=["점수"]).sort_values("수익률", ascending=False).rename(
            columns={"순매수합": "순매수 합계(억)", "평균강도": "평균 매수강도(%)", "수익률": "주간 수익률(%)", "모멘텀": "모멘텀(%p)"}
        ),
        use_container_width=True, hide_index=True,
    )

st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)

# ══════════════════════════════════════════════
# SECTION 3 — 시장 트렌드 & 운용사 동향 (보조)
# ══════════════════════════════════════════════
section_header(
    "SECTION 3",
    "시장 트렌드 & 운용사 동향",
    "구글 뉴스 키워드 언급량과 8대 ETF 브랜드(KODEX·TIGER·ACE·SOL·HANARO·RISE·PLUS·TIMEFOLIO) 핵심 이슈 요약.",
)
st.write("")

n1, n2 = st.columns([5, 7], gap="large")
with n1:
    rows = ""
    for kw in D.NEWS_KEYWORDS:
        cls = {"라이징": "kw-rise", "하락": "kw-fall", "정체": "kw-fall"}.get(kw["방향"], "kw-flat")
        rows += (
            f'<div class="kw-row"><span class="kw-name">{kw["키워드"]}</span>'
            f'<span style="color:{GRAY};font-size:0.8rem;">언급 {kw["언급량"]}건</span>'
            f'<span class="kw-badge {cls}">{kw["증감"]:+d}% {kw["방향"]}</span></div>'
        )
    st.markdown(
        f'<div class="card"><div class="card-title">📰 ETF 이슈 키워드 (구글 뉴스 · 주간)</div>{rows}</div>',
        unsafe_allow_html=True,
    )
with n2:
    ic1, ic2 = st.columns(2)
    half = len(D.ISSUERS) // 2
    for col, issuers in [(ic1, D.ISSUERS[:half]), (ic2, D.ISSUERS[half:])]:
        with col:
            for issuer in issuers:
                items = "".join(
                    f'<div style="font-size:0.82rem;color:#4B5468;line-height:1.55;padding:5px 0;border-bottom:1px solid #F0F2F7;">· {n}</div>'
                    for n in D.ISSUER_NEWS[issuer]
                )
                accent = NAVY if issuer == "KODEX" else "#5B6478"
                st.markdown(
                    f'<div class="card" style="margin-bottom:12px;"><div class="card-title" style="color:{accent};">{issuer}</div>{items}</div>',
                    unsafe_allow_html=True,
                )

st.markdown('<hr class="sec-divider">', unsafe_allow_html=True)

# ══════════════════════════════════════════════
# SECTION 4 — AI 종합 인사이트
# ══════════════════════════════════════════════
section_header(
    "SECTION 4",
    "AI 종합 마케팅 인사이트",
    "전 섹션을 종합해 금주 마케팅 전략을 카드형으로 제안합니다 — 무엇을·왜·어떻게가 즉시 파악되도록.",
)
st.write("")

cols = st.columns(3, gap="medium")
for col, ins in zip(cols, D.AI_INSIGHTS):
    col.markdown(
        f'<div class="ins-card"><span class="ins-icon">{ins["icon"]}</span>'
        f'<div class="ins-title">{ins["title"]}</div>'
        f'<div class="ins-body">{ins["body"]}</div></div>',
        unsafe_allow_html=True,
    )

st.write("")
st.caption(
    "ⓘ 데모 모드: 순매수·테마 데이터는 샘플이며, 실운영 시 KRX·구글뉴스·유튜브 API 연동부로 교체됩니다. "
    "지수·환율은 네이버 증권 실시간 조회(실패 시 데모 값)입니다."
)
