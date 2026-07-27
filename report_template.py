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


def build_lead(ctx: dict) -> str:
    """리드 문단 — 국면·캠페인·검색을 엮은 한 단락 종합 (규칙 기반)."""
    n_dec = ctx["stage_counts"].get("쇠퇴기", 0)
    n_tot = ctx["n_sectors"]
    bench = ctx.get("bench_ret")
    # 앞단 — 시장 상황
    market = [
        f'이번 주 국내 증시는 {n_tot}개 섹터 중 <span class="hl">{n_dec}개가 쇠퇴 국면</span>에 '
        f'진입하며 광범위한 조정을 겪었다.'
    ]
    if bench is not None:
        worst = ctx["top_dn"][0] if ctx["top_dn"] else None
        w = (f'{_ga(_esc(worst[0]))} <b>{worst[1]:+.1f}%</b>로 낙폭이 가장 컸고, ' if worst else "")
        market.append(f'{w}시장 대표 지수(KRX300)도 <b>{bench:+.1f}%</b> 동반 하락했다.')

    # 뒷단 — 우리 마케팅 해석
    tail = []
    camps = ctx.get("campaigns", [])
    if camps:
        c0 = camps[0]
        nm = c0.get("표기명", "")
        # 신규상장 캠페인이면 그 사실을 문장에 드러낸다
        pre = "신규상장된 " if "신규" in (c0.get("제목") or "") else ""
        tail.append(
            f'이런 하락장에서 삼성자산운용은 {pre}<b>{_esc(nm)}</b>{_reul(nm)} 중심으로 '
            f'마케팅 집행하며 방어형 수요를 겨냥했다.')
        tail.append(f'— <span class="hl">국면에 부합하는 선택</span>이다.')
    ups = sorted([(k, v) for k, v in ctx.get("search", {}).items() if v > 15],
                 key=lambda x: -x[1])[:2]
    if ups:
        names = "·".join(k for k, _ in ups)
        tail.append(
            f'반면 검색 수요는 {_esc(names)}로 쏠렸으나 해당 테마는 이미 과열·쇠퇴 국면이어서, '
            f'지금은 신규 진입보다 재매집이 진행 중인 섹터를 다음 사이클 후보로 관찰할 시점이다.')

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
            f'신규상장 캠페인은 상장 이전 순매수가 없어 측정 대상에서 제외했다.</p>'
            f'<div class="did">'
            f'<div class="did-step"><div class="k">Step 1 · 처치</div><div class="t">Δ처치</div>'
            f'<div class="v down">{did["dt"]:+.2f}%p</div></div>'
            f'<div class="did-step"><div class="k">Step 2 · 대조군</div><div class="t">Δ대조군 평균</div>'
            f'<div class="v down">{did["dc"]:+.2f}%p</div></div>'
            f'<div class="did-step" style="border-color:var(--brand)"><div class="k">Step 3 · 순효과</div>'
            f'<div class="t">DiD</div><div class="v down">{did["did"]:+.2f}%p</div></div></div>'
            f'<p class="rz">이 ETF의 평소 DiD 분포({did["base_mean"]:+.2f} ± {did["base_std"]:.2f}%p)로 '
            f'표준화하면 <b>{did["score"]:.0f}점 / 100 · {_esc(did["verdict"])}</b>. '
            f'50점이 "평소와 같음"이며, 그보다 낮으면 평소만 못했다는 뜻이다.</p>')
    else:
        did_html = '<p>이번 주 측정 가능한 캠페인이 없다 — 감지된 캠페인이 모두 신규상장이라 베이스라인이 없다.</p>'

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
                '<p class="note">착수 = 확산 전환이 임박했거나(모멘텀 강 + 평균선 근접) '
                '큰손이 조용히 매집 중인 섹터. 나열이 아니라 판정 결과다.</p>')

    # 05-C 신규 출시 후보
    gp = ctx.get("gap")
    gap_html = ""
    if gp:
        chips = "".join(f"<span>{_esc(c)}</span>" for c in
                        ["추종 지수 존재 확인", "구성종목 선정", "분산요건 · 단일종목 상한", "환헤지 · 보수 구조"])
        gap_html = (
            f'<div class="blk-label" style="margin-top:20px;"><i class="blk-c">C</i> 신규 출시 후보 — 라인업 공백 상세</div>'
            f'<div class="proposal"><div class="prop-head"><div>'
            f'<div class="prop-kicker">신규 상품 후보 · 상세 제안</div>'
            f'<div class="prop-name">{_esc(gp["가칭"])} <em>(가칭)</em></div></div>'
            f'<div class="prop-timing">출시 타이밍 <b>{_esc(gp["타이밍"])}</b><br>{_esc(gp["타이밍설명"])}</div></div>'
            f'<div class="prop-grid">'
            f'<div class="prop-cell"><div class="pc-k">라인업 공백</div>'
            f'<div class="pc-v">KODEX 미보유 · 경쟁 {gp["경쟁사수"]}종</div>'
            f'<div class="pc-d">테마×기초시장({_esc(gp["테마"])}·{_esc(gp["시장"])}) 기준</div></div>'
            f'<div class="prop-cell"><div class="pc-k">경쟁 구도</div>'
            f'<div class="pc-v">{_esc(gp["유형요약"])}</div>'
            f'<div class="pc-d">{_esc(" · ".join(gp["경쟁상품"][:3]))}</div></div>'
            f'<div class="prop-cell"><div class="pc-k">시장 신호</div>'
            f'<div class="pc-v">{_esc(gp["테마"])} 국면 {_esc(gp["국면"] or "미상")}</div>'
            f'<div class="pc-d">{_esc(gp["신호설명"])}</div></div></div>'
            f'<div class="prop-angle"><b>차별화 각도 —</b> {_esc(gp["차별화"])}</div>'
            f'<div class="prop-verify"><span class="pv-label">담당자 검증 필요</span>{chips}</div></div>')
        # 1순위 상세 뒤에 공백 전체를 붙인다 — 나머지 후보도 같은 자리에서 검토되게
        _gs = ctx.get("gaps_all") or []
        if len(_gs) > 1:
            _r = "".join(
                f'<tr><td>{_esc(g["테마"])} × {_esc(g["시장"])}</td>'
                f'<td>{_esc(g["브랜드"])}</td><td class="num">{g["경쟁사수"]}종</td>'
                f'<td>{_esc(g["국면"] or "—")}</td><td>{_esc(g["타이밍"])}</td></tr>'
                for g in _gs)
            gap_html += (
                '<table class="mini"><thead><tr><th>테마 × 기초시장</th><th>경쟁 브랜드</th>'
                '<th class="num">경쟁</th><th>국면</th><th>타이밍</th></tr></thead>'
                f'<tbody>{_r}</tbody></table>'
                '<p class="note">KODEX 미보유 · 경쟁사 3곳 이상 보유. 국면이 과열·쇠퇴면 '
                '대기(리드타임 감안 준비만), 그 외 검토. 신규 상장이 있을 때만 바뀐다.</p>')

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
