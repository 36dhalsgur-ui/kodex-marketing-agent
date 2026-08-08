"""주간 마케팅 리포트 — 인쇄(PDF)용 HTML 생성.

앱 대시보드는 요약본, 이 모듈은 전체본을 만든다.
브라우저에서 열어 인쇄(Ctrl/Cmd+P) → 'PDF로 저장'하면 리포트 PDF가 된다.
(WeasyPrint 등 시스템 라이브러리 의존 없이 동작하도록 인쇄 CSS만 사용)
"""

from __future__ import annotations

import datetime as dt
import html


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _ga(word: str) -> str:
    """이/가 조사 — 받침 있으면 '이', 없으면 '가'."""
    if not word:
        return word
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return f"{word}이" if (c - 0xAC00) % 28 else f"{word}가"
    return f"{word}가"


def _reul(word: str) -> str:
    """을/를 조사만 반환 — 태그 뒤에 붙일 때 사용."""
    if not word:
        return "를"
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return "을" if (c - 0xAC00) % 28 else "를"
    return "를"


def _eun(word: str) -> str:
    """은/는 조사만 반환. 테마명이 매주 바뀌어 고정하면 어긋난다."""
    if not word:
        return "는"
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return "은" if (c - 0xAC00) % 28 else "는"
    return "는"


def build_lead(ctx: dict, polite: bool = False) -> str:
    """리드 문단 — 국면·캠페인·검색을 엮은 한 단락 종합 (규칙 기반).

    polite=True면 경어체 — 앱 탭은 홈 스냅샷과 어투를 맞춘다.
    PDF·HTML 리포트는 문서라서 평서체를 그대로 쓴다."""
    def _e(plain: str, formal: str) -> str:
        return formal if polite else plain

    n_dec = ctx["stage_counts"].get("쇠퇴기", 0)
    n_tot = ctx["n_sectors"]
    # 앞단 — 시장 상황
    # '광범위한 조정'은 바로 아래 KPI의 KRX300 주간수익률과 같은 말이라 뺀다.
    market = [
        f'{n_tot}개 섹터 중 <span class="hl">{n_dec}개가 쇠퇴 국면</span>'
        f'{_e("이다", "입니다")}.'
    ]
    worst = ctx["top_dn"][0] if ctx["top_dn"] else None
    if worst:
        market.append(f'{_ga(_esc(worst[0]))} <b>{worst[1]:+.1f}%</b>로 '
                      f'낙폭이 가장 {_e("컸다", "컸습니다")}.')

    # 뒷단 — 우리 마케팅 해석
    tail = []
    camps = ctx.get("campaigns", [])
    if camps:
        c0 = camps[0]
        nm = c0.get("표기명", "")
        # 신규상장 캠페인이면 그 사실을 문장에 드러낸다
        pre = "신규상장된 " if "신규" in (c0.get("제목") or "") else ""
        # '이런 하락장에서'는 앞 문장의 되풀이. 집행 건수는 KPI에 있으므로 대표 상품만.
        # 상품명이 이미 'KODEX ~'라 주어와 겹친다 — 표기명에서 브랜드를 떼고 쓴다.
        _short = _esc(nm).replace("KODEX ", "")
        tail.append(
            f'KODEX는 {pre}<b>{_short}</b> 등 방어형을 집행 중 '
            f'— <span class="hl">국면에 부합</span>{_e("한다", "합니다")}.')
    ups = sorted([(k, v) for k, v in ctx.get("search", {}).items() if v > 15],
                 key=lambda x: -x[1])[:2]
    if ups:
        names = "·".join(k for k, _ in ups)
        # 조사를 이름 끝소리에 맞춘다 — 예전 '미국주식로'처럼 어긋났다.
        tail.append(
            f'검색이 몰린 {_esc(names)}{_eun(names)} 이미 과열이라, 재매집 중인 섹터를 '
            f'다음 사이클 후보로 관찰할 {_e("시점이다", "시점입니다")}.')

    # 시장 상황(앞) / 우리 해석(뒤) 사이에서만 한 번 줄을 바꾼다
    out = " ".join(market)
    if tail:
        out += "<br>" + " ".join(tail)
    return out


_CSS = """
:root{
  --paper:#fff; --ink:#171B22; --muted:#5C6572; --faint:#949DAA;
  --line:#E7EAEF; --line-strong:#CDD3DC;
  --navy:#1F3A6E; --brand:#1B4DE4; --brand-soft:#EAF0FD;
  --up:#C4362E; --down:#2C63B5;
  --keep:#2E7D5B; --watch:#B0801F; --cut:#2C63B5;
}
*{box-sizing:border-box;}
body{margin:0; background:#EEF0F3;}
.rpt{font-family:"Apple SD Gothic Neo","Pretendard","Malgun Gothic",system-ui,-apple-system,sans-serif;
  background:var(--paper); color:var(--ink); max-width:880px; margin:24px auto; padding:0 34px 44px;
  line-height:1.6; font-variant-numeric:tabular-nums; box-shadow:0 2px 16px rgba(20,30,55,.12);}
.rpt *{font-variant-numeric:tabular-nums;}
.brandbar{height:5px; background:var(--brand); margin:0 -34px 30px;}
.mast{display:flex; justify-content:space-between; align-items:flex-end; gap:24px;
  padding-bottom:14px; border-bottom:2.5px solid var(--navy);}
.eyebrow{font-size:10.5px; letter-spacing:.22em; font-weight:700; color:var(--brand); text-transform:uppercase;}
.mast h1{font-size:26px; font-weight:800; margin:5px 0 0; letter-spacing:-.01em;}
.mast-meta{text-align:right; font-size:11px; color:var(--muted); line-height:1.7; white-space:nowrap;}
.mast-meta b{color:var(--ink);}
.strip{margin:20px 0 6px;}
.strip-label{display:flex; justify-content:space-between; font-size:11px; color:var(--faint); margin-bottom:6px;}
.bar{display:flex; height:26px; border-radius:4px; overflow:hidden; border:1px solid var(--line);}
.bar span{display:flex; align-items:center; justify-content:center; font-size:10.5px; font-weight:700; color:#fff;}
.lead{margin:22px 0 4px; font-size:16px; line-height:1.72;}
.lead .hl{background:linear-gradient(transparent 62%, var(--brand-soft) 62%); font-weight:700;}
.lead b{font-weight:700;}
.sec{margin-top:32px;}
.sec-h{display:flex; align-items:baseline; gap:11px; padding-bottom:8px;
  border-bottom:1px solid var(--line-strong); margin-bottom:13px;}
.sec-no{font-size:12px; font-weight:800; color:var(--brand);}
.sec-t{font-size:16px; font-weight:800;}
.sec-tag{margin-left:auto; font-size:10.5px; color:var(--faint); text-transform:uppercase; font-weight:600;}
.sec p{font-size:13.5px; margin:0 0 11px; line-height:1.72;}
.sec p b{font-weight:700;} .u{color:var(--up); font-weight:700;} .d{color:var(--down); font-weight:700;}
table{width:100%; border-collapse:collapse; font-size:12.5px; margin:4px 0 2px;}
th{text-align:left; font-size:10.5px; color:var(--faint); font-weight:600; padding:5px 8px;
  border-bottom:1px solid var(--line-strong); text-transform:uppercase;}
td{padding:6px 8px; border-bottom:1px solid var(--line);}
td.num{text-align:right;} .up{color:var(--up); font-weight:700;} .down{color:var(--down); font-weight:700;}
.co-tag{display:inline-block; font-size:10px; font-weight:700; color:var(--navy);
  background:var(--brand-soft); border-radius:3px; padding:1px 6px; margin-right:6px;}
.did{display:flex; gap:8px; margin:8px 0 10px; flex-wrap:wrap;}
.did-step{flex:1; min-width:150px; border:1px solid var(--line); border-radius:7px; padding:11px 13px;}
.did-step .k{font-size:10px; color:var(--faint); font-weight:700; text-transform:uppercase;}
.did-step .t{font-size:12px; font-weight:700; margin:2px 0 4px;}
.did-step .v{font-size:20px; font-weight:800;}
.blk-label{display:flex; align-items:center; gap:8px; font-size:12.5px; font-weight:700; margin:4px 0 9px;}
.blk-label i{font-style:normal; display:inline-flex; align-items:center; justify-content:center;
  width:19px; height:19px; border-radius:4px; font-size:10.5px; font-weight:800; color:#fff;}
.blk-a{background:var(--navy);} .blk-b{background:var(--brand);} .blk-c{background:var(--keep);}
.vd{display:inline-block; font-size:10.5px; font-weight:800; border-radius:20px; padding:3px 9px;
  color:#fff; white-space:nowrap; word-break:keep-all; line-height:1.35; text-align:center;}
.vd-keep{background:var(--keep);} .vd-watch{background:var(--watch);} .vd-cut{background:var(--cut);}
.rz{font-size:11.5px; color:var(--muted); line-height:1.5;}
.revtbl{table-layout:fixed;} .revtbl td{word-break:keep-all; overflow-wrap:break-word;}
.ph{font-size:11.5px; color:var(--muted); white-space:nowrap;}
.review-read{margin-top:10px; padding:11px 14px; background:var(--brand-soft); border-radius:7px;
  font-size:12.5px; line-height:1.65;}
.emerge{display:flex; gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:8px; overflow:hidden;}
.em-main{flex:1.6; background:#fff; padding:14px 16px;} .em-side{flex:1; background:#fff; padding:14px 16px;}
.em-sec{font-size:15px; font-weight:800;}
.em-badge{font-size:10px; font-weight:700; color:#fff; background:#4C6FC6; border-radius:20px;
  padding:2px 9px; margin-left:7px;}
.em-body,.es-v{font-size:12.5px; color:var(--muted); line-height:1.65; margin-top:6px;}
.es-k{font-size:10px; text-transform:uppercase; font-weight:700; color:var(--faint);}
.es-v b{color:var(--ink);}
.proposal{margin-top:6px; border:1px solid var(--line-strong); border-radius:9px; overflow:hidden;}
.prop-head{display:flex; justify-content:space-between; gap:16px; padding:15px 18px;
  background:var(--brand-soft); border-bottom:1px solid var(--line);}
.prop-kicker{font-size:10px; letter-spacing:.14em; text-transform:uppercase; font-weight:700; color:var(--brand);}
.prop-name{font-size:18px; font-weight:800; margin-top:4px;} .prop-name em{font-size:12px; font-weight:500;
  font-style:normal; color:var(--faint);}
.prop-timing{text-align:right; font-size:10.5px; color:var(--muted); line-height:1.6; max-width:250px;}
.prop-timing b{color:var(--up);}
.prop-grid{display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--line);}
.prop-cell{background:#fff; padding:12px 16px;}
.pc-k{font-size:10px; text-transform:uppercase; color:var(--faint); font-weight:700;}
.pc-v{font-size:14px; font-weight:700; margin:4px 0 3px;}
.pc-d{font-size:11px; color:var(--muted); line-height:1.5;}
.prop-angle{padding:14px 18px; font-size:12.5px; line-height:1.7; border-top:1px solid var(--line);}
.prop-verify{display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:12px 18px;
  background:var(--brand-soft); border-top:1px solid var(--line);}
.pv-label{font-size:10.5px; font-weight:800; color:var(--brand); text-transform:uppercase;}
.prop-verify span:not(.pv-label){font-size:11.5px; color:var(--muted); background:#fff;
  border:1px solid var(--line); border-radius:20px; padding:3px 11px;}
.foot{margin-top:38px; padding-top:16px; border-top:1px solid var(--line-strong);
  font-size:11px; color:var(--faint); line-height:1.75;}
.foot .src{display:flex; flex-wrap:wrap; gap:6px 14px; margin-bottom:10px;}
.foot .src span{color:var(--muted);} .foot .src b{color:var(--ink);}
.foot .byline b{color:var(--brand);}
table.mini{width:100%;border-collapse:collapse;margin-top:12px;font-size:9.5pt}
table.mini th{text-align:left;font-weight:700;color:#5B6478;border-bottom:1.5px solid #1F3A6E;
  padding:5px 7px;font-size:8.5pt;letter-spacing:.04em}
table.mini td{padding:5px 7px;border-bottom:1px solid #EEF1F6;color:#141B2D}
table.mini .num{text-align:right}
p.note{font-size:8.5pt;color:#8A93A6;margin:6px 0 0;line-height:1.5}

@media print{
  body{background:#fff;}
  .rpt{box-shadow:none; margin:0; max-width:none; padding:0 12mm 12mm;}
  .brandbar{margin:0 -12mm 8mm;}
  .sec{break-inside:avoid;} .proposal,.emerge,.did{break-inside:avoid;}
  @page{size:A4; margin:12mm;}
}
"""


def render_report(ctx: dict) -> str:
    """전체 리포트 HTML (독립 문서 — 다운로드 후 브라우저에서 인쇄→PDF)."""
    sc = ctx["stage_counts"]
    n = max(1, ctx["n_sectors"])
    segs = [("태동기", "#4C6FC6"), ("확산기", "#2E7D5B"), ("과열기", "#C4362E"), ("쇠퇴기", "#7A8595")]
    bar = "".join(
        f'<span style="width:{sc.get(s,0)/n*100:.1f}%;background:{c}">'
        f'{s[:2] + " " + str(sc.get(s,0)) if sc.get(s,0)/n > .10 else ""}</span>'
        for s, c in segs if sc.get(s, 0)
    )

    # 01 시장
    rows_mkt = ""
    for i in range(max(len(ctx["top_up"]), len(ctx["top_dn"]))):
        u = ctx["top_up"][i] if i < len(ctx["top_up"]) else None
        d = ctx["top_dn"][i] if i < len(ctx["top_dn"]) else None
        rows_mkt += (
            "<tr>"
            + (f'<td>{_esc(u[0])}</td><td class="num up">{u[1]:+.1f}%</td>' if u else "<td></td><td></td>")
            + (f'<td>{_esc(d[0])}</td><td class="num down">{d[1]:+.1f}%</td>' if d else "<td></td><td></td>")
            + "</tr>")

    # 02 경쟁
    rows_camp = "".join(
        f'<tr><td>{_esc(c["표기명"])}</td><td>{_esc(c["채널"])}</td><td class="num">{_esc(c["주차"])}</td></tr>'
        for c in ctx["campaigns"][:4]) or '<tr><td colspan="3">감지된 캠페인 없음</td></tr>'

    # 03 자금
    rows_flow = "".join(
        f'<tr><td>{_esc(nm)}</td><td class="num up">{v:+.2f}%</td></tr>'
        for nm, v in ctx["flow_top"][:4]) or '<tr><td colspan="2">데이터 없음</td></tr>'

    # 04 DiD
    did = ctx.get("did")
    if did:
        did_html = (
            f'<p>캠페인이 순매수를 실제로 움직였는지는 <b>DiD(이중차분)</b>로 시장 공통 효과를 제거하고 본다. '
            f'이번 주 측정 가능한 사례는 <b>{_esc(did["name"])}</b>({_esc(did["channel"])}, {_esc(did["week"])})이다. '
            f'이벤트 이전 이력이 없거나(상장과 이벤트가 같은 주), 구성종목이 충분히 '
            f'비슷한 경쟁 ETF가 없으면 측정하지 않는다.</p>'
            f'<div class="did">'
            f'<div class="did-step"><div class="k">Step 1 · 처치</div><div class="t">Δ처치</div>'
            f'<div class="v down">{did["dt"]:+.2f}%p</div></div>'
            f'<div class="did-step"><div class="k">Step 2 · 대조군</div><div class="t">Δ대조군 평균</div>'
            f'<div class="v down">{did["dc"]:+.2f}%p</div></div>'
            f'<div class="did-step" style="border-color:var(--brand)"><div class="k">Step 3 · 순효과</div>'
            f'<div class="t">DiD</div><div class="v down">{did["did"]:+.2f}%p</div></div></div>'
            f'<p class="rz">이 ETF의 평소 DiD 변동폭(±{did["base_std"]:.2f}%p)과 견주면 '
            f'<b>{did["score"]:.0f}점 / 100 · {_esc(did["verdict"])}</b>. '
            f'DiD가 양수면 같은 기간 경쟁 ETF보다 자금을 더 받았다는 뜻이고, '
            f'점수 38~62는 평소 범위라 효과로 보기 어렵다.</p>')
        # 대표 1건만 실으면 '어떤 건 통하고 어떤 건 아닌지'가 빠진다 — 전 건을 표로 잇는다
        _rest = [r for r in (ctx.get("did_all") or []) if r is not did]
        if _rest:
            _tr = "".join(
                f'<tr><td>{_esc(r["name"])}</td><td>{_esc(r["week"])}</td>'
                + (f'<td class="num">{r["did"]:+.2f}%p</td>'
                   f'<td class="num">{r["score"]:.0f}점</td>'
                   f'<td>{_esc(r["verdict"])}</td>'
                   if r["did"] is not None else
                   f'<td class="num">—</td><td class="num">—</td>'
                   f'<td>{_esc(r["reason"])}</td>')
                + '</tr>' for r in _rest)
            did_html += (
                '<table class="mini"><thead><tr><th>ETF</th><th>집행</th>'
                '<th class="num">DiD</th><th class="num">점수</th><th>판정</th>'
                '</tr></thead><tbody>' + _tr + '</tbody></table>')
    else:
        did_html = ('<p>이번 주 측정 가능한 캠페인이 없다 — 이벤트 이전 이력이 부족하거나, '
                    '구성종목이 충분히 비슷한 경쟁 ETF가 없어 비교가 성립하지 않는다.</p>')

    # 05-A 현재 마케팅 점검
    vd_cls = {"지속": "vd-keep", "확대": "vd-keep", "지속·관찰": "vd-watch",
              "지속·신중": "vd-watch", "축소": "vd-cut"}

    def _rev_row(r: dict) -> str:
        v = r.get("개인강도")
        if v is None:
            flow, cls = "—", "ph"
        elif v >= 40:                       # 신규상장 첫 주 유입 왜곡
            flow, cls = "신규상장", "ph"
        else:
            flow, cls = f"{v:+.2f}%", ("up" if v > 0 else "down")
        name = r.get("표기명", "").replace("KODEX ", "")
        cls_vd = vd_cls.get(r.get("판정"), "vd-keep")
        # '지속·관찰'이 음절 중간에서 잘리지 않도록 가운뎃점 뒤에만 줄바꿈 기회를 준다
        verdict = _esc(r.get("판정")).replace("·", "·<wbr>")
        return (f'<tr><td>{_esc(name)}</td><td class="ph">{_esc(r.get("국면"))}</td>'
                f'<td class="num {cls}">{_esc(flow)}</td>'
                f'<td><span class="vd {cls_vd}">{verdict}</span></td>'
                f'<td class="rz">{_esc(r.get("근거"))}</td></tr>')

    rows_rev = "".join(_rev_row(r) for r in ctx["review"])

    # 05-B 태동기
    em = ctx.get("emerging")
    em_html = ""
    if em:
        em_html = (
            f'<div class="blk-label"><i class="blk-b">B</i> 태동기 착수 — 아직 안 밀고 있는 상승 초입 섹터</div>'
            f'<div class="emerge"><div class="em-main">'
            f'<div class="em-sec">{_esc(em["섹터"])}<span class="em-badge">{_esc(em.get("배지", "태동기"))}</span></div>'
            f'<div class="em-body">태동 국면 진입. <b>{_esc(em["kodex"])}</b> 보유 상품이 있으나 현재 마케팅 미집행 — '
            f'확산 전환 전 인지도를 선점하는 착수 대상입니다.</div></div>'
            f'<div class="em-side"><div class="es-k">경쟁사 참조</div>'
            f'<div class="es-v">{_esc(em["peer_note"])}</div></div></div>')
        # 1순위만 싣고 끝내면 나머지 태동 섹터가 검토되지 않는다 — 전체를 표로 덧붙인다
        _ems = ctx.get("emerging_all") or []
        if len(_ems) > 1:
            _r = "".join(
                f'<tr><td>{"<b>" if e["판정"] == "착수" else ""}{_esc(e["판정"])}'
                f'{"</b>" if e["판정"] == "착수" else ""}</td>'
                f'<td>{_esc(e["섹터"])}</td><td>{_esc(e["kodex"])}</td>'
                f'<td>{_esc(e["근거"])}</td></tr>'
                for e in _ems)
            em_html += (
                '<table class="mini"><thead><tr><th>판정</th><th>섹터</th>'
                '<th>KODEX 상품</th><th>근거</th></tr></thead>'
                f'<tbody>{_r}</tbody></table>'
                '<p class="note">착수는 ① 순자산이 집행 하한을 넘고 ② 확산 전환이 임박했으며 '
                '③ 외국인·연기금 자금이 빠지지 않는 섹터만 올린다. 하나라도 어긋나면 선점 검토로 '
                '내려 소재만 준비한다. 규모 미달·관찰 섹터는 제외했다.</p>')

    # 05-C 신규 출시 후보 — 검토 대상 전부를 상세 제안으로 (1건만 상세하면 나머지는 판단이 안 선다)
    _details = ctx.get("gap_details") or ([ctx["gap"]] if ctx.get("gap") else [])
    gap_html = ""
    if _details:
        chips = "".join(f"<span>{_esc(c)}</span>" for c in
                        ["추종 지수 존재 확인", "구성종목 선정", "분산요건 · 단일종목 상한", "환헤지 · 보수 구조"])
        gap_html = (f'<div class="blk-label" style="margin-top:20px;"><i class="blk-c">C</i> '
                    f'신규 출시 후보 — 검토 대상 {len(_details)}건 상세</div>')
        for gp in _details:
            _mk = f'{gp["시장규모억"]:,.0f}억' if gp.get("시장규모억") else "—"
            _lead = (f'{gp["1위"]} {gp["점유율"]:.0%}'
                     if gp.get("1위") and gp.get("점유율") else _esc(gp["유형요약"]))
            gap_html += (
                f'<div class="proposal"><div class="prop-head"><div>'
                f'<div class="prop-kicker">신규 상품 후보 · 상세 제안</div>'
                f'<div class="prop-name">{_esc(gp["가칭"])} <em>(가칭)</em></div></div>'
                f'<div class="prop-timing">출시 판정 <b>{_esc(gp["타이밍"])}</b><br>'
                f'{_esc(gp["타이밍설명"])}</div></div>'
                f'<div class="prop-grid">'
                f'<div class="prop-cell"><div class="pc-k">시장 규모</div>'
                f'<div class="pc-v">{_mk}</div>'
                f'<div class="pc-d">경쟁 {gp["경쟁사수"]}종이 그 테마에서 모은 순자산 합계</div></div>'
                f'<div class="prop-cell"><div class="pc-k">경쟁 구도</div>'
                f'<div class="pc-v">{_esc(_lead)}</div>'
                f'<div class="pc-d">{_esc(gp["유형요약"])} · '
                f'{_esc(" / ".join(gp.get("경쟁상품", [])[:3]))}</div></div>'
                f'<div class="prop-cell"><div class="pc-k">시장 신호</div>'
                f'<div class="pc-v">{_esc(gp["테마"])} 국면 {_esc(gp["국면"] or "미상")}</div>'
                f'<div class="pc-d">{_esc(gp["신호설명"])}</div></div></div>'
                f'<div class="prop-angle"><b>차별화 각도 —</b> {_esc(gp["차별화"])}</div>'
                f'<div class="prop-verify"><span class="pv-label">담당자 검증 필요</span>{chips}</div></div>')
        gap_html += ('<p class="note">시장 규모 = 그 테마에서 경쟁사가 실제로 모은 순자산 합계. '
                     '시장 규모가 작으면 시장성이 부족하다고 판단해 제외한다. 선발이 1~2곳뿐인 '
                     '테마는 규모만으로 판단할 수 없어 따로 가른다 — 이미 돈이 모였으면 선점 기회, '
                     '그렇지 않으면 시장 미검증. 경쟁사가 한 곳도 없는 테마는 탐지되지 않는다.</p>')

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>KODEX 주간 마케팅 리포트 — {_esc(ctx['week'])}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style></head><body>
<div class="rpt">
  <div class="brandbar"></div>
  <div class="mast">
    <div><div class="eyebrow">KODEX ETF · Marketing Intelligence</div><h1>주간 마케팅 리포트</h1></div>
    <div class="mast-meta">{_esc(ctx['week'])} · <b>발행 {_esc(ctx['issued'])}</b><br>
      데이터 기준 {_esc(ctx['asof'])}<br>
      KODEX 라인업 <b>{ctx['n_kodex']}종</b> · 경쟁 8개 브랜드</div>
  </div>

  <div class="strip">
    <div class="strip-label"><span>{ctx['n_sectors']}개 섹터 국면 분포 (KRX 상대강도·RRG)</span>
      <span>{_esc(ctx['regime'])}</span></div>
    <div class="bar">{bar}</div>
  </div>

  <p class="lead">{build_lead(ctx)}</p>

  <div class="sec"><div class="sec-h"><span class="sec-no">01</span><span class="sec-t">시장 국면</span>
    <span class="sec-tag">Signal Board · KRX</span></div>
    <p>상대강도 기준 시장의 무게중심은 {_esc(ctx['regime'])}다. 태동 국면은
      <b>{_esc(ctx['emerging_names'] or '없음')}</b>, 확산 국면은 <b>{_esc(ctx['expanding_names'] or '없음')}</b>이다.</p>
    <table><thead><tr><th>상위</th><th class="num">주간</th><th>하위</th><th class="num">주간</th></tr></thead>
      <tbody>{rows_mkt}</tbody></table>
  </div>

  <div class="sec"><div class="sec-h"><span class="sec-no">02</span><span class="sec-t">경쟁 환경</span>
    <span class="sec-tag">Channels · Live</span></div>
    <p>이번 주 KODEX가 집행한 캠페인과 경쟁 브랜드의 콘텐츠 발행량이다.
      발행량 1위는 <b>{_esc(ctx['top_brand'][0])}</b>({ctx['top_brand'][1]}건)였다.</p>
    <table><thead><tr><th>KODEX 감지 캠페인</th><th>채널</th><th class="num">주차</th></tr></thead>
      <tbody>{rows_camp}</tbody></table>
  </div>

  <div class="sec"><div class="sec-h"><span class="sec-no">03</span><span class="sec-t">자금 흐름</span>
    <span class="sec-tag">개인 순매수 · KRX</span></div>
    <p>마케팅 반응은 <b>개인 순매수</b>로 읽는다(기관·LP의 설정·환매는 제외).
      매수강도 = 개인 주간 순매수 ÷ 순자산 × 100.</p>
    <table><thead><tr><th>순매수 강도 상위</th><th class="num">강도</th></tr></thead>
      <tbody>{rows_flow}</tbody></table>
  </div>

  <div class="sec"><div class="sec-h"><span class="sec-no">04</span><span class="sec-t">마케팅 효과 — DiD</span>
    <span class="sec-tag">이중차분 · 인과추정</span></div>{did_html}
  </div>

  <div class="sec"><div class="sec-h"><span class="sec-no">05</span><span class="sec-t">다음 주 액션</span>
    <span class="sec-tag">현재 마케팅 · 국면 근거</span></div>
    <div class="blk-label"><i class="blk-a">A</i> 현재 마케팅 점검 — 국면·자금 근거로 지속·확대·축소</div>
    <table class="revtbl"><colgroup><col style="width:22%"><col style="width:13%">
      <col style="width:10%"><col style="width:17%"><col></colgroup>
      <thead><tr><th>집행 중 ETF</th><th>테마 국면</th><th class="num">개인 자금</th>
      <th>판정</th><th>근거</th></tr></thead><tbody>{rows_rev}</tbody></table>
    <div class="review-read">{_esc(ctx['review_read'])}</div>
    <div style="margin-top:20px;">{em_html}</div>
    {gap_html}
  </div>

  <div class="foot">
    <div class="src"><span><b>데이터</b> 시세·수급 KRX</span><span>검색량 네이버 데이터랩</span>
      <span>뉴스 구글 뉴스 RSS</span><span>채널 공식 홈페이지·유튜브·네이버 블로그 RSS</span></div>
    <div class="byline">생성 · <b>KODEX 마케팅 AI Agent</b> — 규칙 엔진 자동 브리핑</div>
    <div style="margin-top:8px;">내부 마케팅 분석용 자료입니다. 국면별 액션은 데이터 신호 기반 제안이며,
      테마의 순환/구조 성격과 추종 지수·규제 요건 등 출시 가능성은 담당자 검증이 필요합니다.
      투자 권유 자료가 아닙니다.</div>
  </div>
</div></body></html>"""
