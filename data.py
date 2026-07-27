"""데모 데이터 생성 및 실시간 지수 수집 모듈.

실제 운영 시 KRX / 구글뉴스 / 유튜브 API 연동부로 교체하는 것을 전제로,
동일한 스키마의 데모 데이터를 제공한다.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
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

# ══════════════════════════════════════════════
# ETF 실데이터 (scripts/etf_batch.py 산출) — 있으면 데모 유니버스를 대체한다
# 매수강도 = 개인 순매수 ÷ 순자산. ETF의 금융투자는 LP 설정·환매가 지배해
# 마케팅 반응 지표로 부적절하므로 개인 기준을 쓴다 (실측 근거는 etf_batch.py 참조).
# ══════════════════════════════════════════════
_ETF_FLOWS_PATH = Path(__file__).parent / "data" / "etf_flows.json"


def load_etf_flows() -> dict | None:
    """배치 산출물 로드. 없으면 None(→ 데모 유지)."""
    try:
        if _ETF_FLOWS_PATH.exists():
            d = json.loads(_ETF_FLOWS_PATH.read_text())
            return d if d.get("etfs") else None
    except Exception:
        pass
    return None


# ── ETF 분류 (테마·기초시장·브랜드) — 배치와 리포트가 공유하는 단일 기준 ──────
ETF_BRANDS = ["KODEX", "TIGER", "ACE", "SOL", "HANARO", "RISE", "PLUS", "TIMEFOLIO", "TIME"]
ETF_MARKETS = [
    ("미국", r"미국|나스닥|S&P|필라델피아|다우|러셀"),
    ("중국", r"차이나|중국|항셍|홍콩"),
    ("일본", r"일본|닛케이"),
    ("인도", r"인도|니프티"),
    ("글로벌", r"글로벌|선진국|신흥국|월드|해외"),
]
ETF_THEMES = [
    ("반도체", r"반도체|SEMI|메모리|파운드리"),
    ("AI·전력", r"AI|인공지능|전력|광통신|데이터센터"),
    ("2차전지", r"2차전지|배터리|전고체|리튬"),
    ("방산", r"방산|우주항공|K-?방산"),
    ("조선", r"조선|해운"),
    ("원자력", r"원자력|SMR|원전"),
    ("바이오", r"바이오|헬스케어|제약"),
    ("커버드콜", r"커버드콜"),
    ("배당", r"배당|고배당|리츠"),
    ("채권", r"채권|국채|금리|CD|단기자금|통안"),
    ("금·원자재", r"금현물|골드|은|원유|구리|원자재"),
    ("빅테크", r"빅테크|테크|나스닥100|매그니피센트|M7"),
    ("로봇·모빌리티", r"로봇|로보틱스|휴머노이드|자율주행|모빌리티|드론|UAM|전기차|테슬라"),
    ("신재생·수소", r"수소|신재생|클린에너지|태양광|풍력|탄소|기후|천연가스"),
    ("환율·통화", r"달러선물|엔선물|환헤지|머니마켓|SOFR"),
    ("연금·자산배분", r"TDF\d|TRF\d|멀티에셋|자산배분|퇴직연금"),
    ("팩터·스타일", r"가치주|성장주|우량주|모멘텀|퀄리티|밸류Plus|최소변동성|멀티팩터|동일가중"),
    ("국가지수", r"인도|차이나|중국본토|일본|유럽|대만|베트남|Nifty|CSI|TOPIX|니케이|HSCEI|ChiNext"),
    ("국내섹터", r"건설|철강|증권|보험|자동차|운송|기계장비|경기소비재|필수소비재|게임|K콘텐츠|웹툰"),
    ("시장대표", r"200|코스피|코스닥|S&P500|MSCI|KRX300|KTOP30|밸류업|Top10|Top5"),
]


def classify_etf(name: str) -> tuple[str, str]:
    market = next((m for m, pat in ETF_MARKETS if re.search(pat, name, re.I)), "한국")
    theme = next((t for t, pat in ETF_THEMES if re.search(pat, name, re.I)), "기타")
    return theme, market


def etf_brand_of(name: str) -> str | None:
    for b in ETF_BRANDS:
        if name.startswith(b):
            return "TIMEFOLIO" if b == "TIME" else b
    return None


_ETF_NAMES_PATH = Path(__file__).parent / "data" / "etf_names.json"
_LINEUP_EXCLUDE = re.compile(r"인버스|레버리지|2X|3X|곱버스|선물\(H\)|합성")


# 공백 후보로 올릴 최소 경쟁사 수. 3으로 두면 '선발이 1~2곳뿐인 테마'가 통째로
# 빠지는데(실측 13건), 그런 곳이야말로 선점 여지가 크다. 1로 낮춰 후보에 넣고
# 경쟁사가 적을 때의 위험(시장이 검증되지 않았을 수 있다)은 판정 단계에서 가른다.
# ※ 경쟁사가 아예 0곳인 테마는 이 방식으로 탐지할 수 없다 — 테마 목록 자체를
#    기존 ETF 이름에서 뽑으므로, ETF가 하나도 없는 테마는 데이터에 존재하지 않는다.
def lineup_gaps(min_competitors: int = 1) -> list[dict]:
    """전체 ETF 명단(배치 캐시)에서 'KODEX 미보유 + 경쟁사 다수 보유' 테마×시장 공백.
    반환: [{테마, 시장, 경쟁사수, 브랜드}] 경쟁사 많은 순. 캐시 없으면 빈 리스트."""
    try:
        names = json.loads(_ETF_NAMES_PATH.read_text())
    except Exception:
        return []
    from collections import defaultdict
    cov: dict = defaultdict(lambda: defaultdict(int))
    for nm in names.values():
        b = etf_brand_of(nm)
        if not b or _LINEUP_EXCLUDE.search(nm):
            continue
        cov[classify_etf(nm)][b] += 1
    gaps = []
    for (theme, market), brands in cov.items():
        if brands.get("KODEX", 0) == 0 and sum(brands.values()) >= min_competitors:
            gaps.append({"테마": theme, "시장": market,
                         "경쟁사수": sum(brands.values()),
                         "브랜드": dict(brands)})
    gaps.sort(key=lambda g: -g["경쟁사수"])
    return gaps


def etf_product_type(name: str) -> str:
    """ETF명으로 상품 유형 추론 — 공백 영역의 경쟁 구도 분석용."""
    if re.search(r"커버드콜", name):
        return "커버드콜"
    if re.search(r"액티브", name):
        return "액티브"
    if re.search(r"TOP\s?\d+", name):
        return "집중(TOP)"
    return "지수추종"


def gap_competitors(theme: str, market: str, limit: int = 6) -> list[str]:
    """해당 테마×시장의 비(非)KODEX 경쟁 상품 실제 목록."""
    try:
        names = json.loads(_ETF_NAMES_PATH.read_text())
    except Exception:
        return []
    out = []
    for nm in names.values():
        b = etf_brand_of(nm)
        if not b or b == "KODEX" or _LINEUP_EXCLUDE.search(nm):
            continue
        if classify_etf(nm) == (theme, market):
            out.append(nm)
    return out[:limit]


def _intensity_at(netbuy_df, name: str, week: str):
    """특정 ETF의 해당 주 개인 매수강도. 없으면 None."""
    if netbuy_df is None or not len(netbuy_df):
        return None
    r = netbuy_df[(netbuy_df["종목명"] == name) & (netbuy_df["주차"] == week)]
    if len(r) and pd.notna(r.iloc[0].get("매수강도")):
        return float(r.iloc[0]["매수강도"])
    return None


_NEWLISTING_INTENSITY = 40.0   # 이 이상은 신규상장 첫 주 유입 왜곡으로 본다


# ETF명은 숫자·영문으로 끝나는 경우가 많다(TOP10, S&P500, 2X, Plus). 한글이 아니라고
# 받침 없음으로 처리하면 'TOP10를'처럼 틀린 조사가 나가므로 읽는 소리의 받침을 쓴다.
# 숫자는 끝자리 읽기 기준 — 영·일·삼·육·칠·팔은 받침, 이·사·오·구는 없음.
_DIGIT_JONG = {"0": 8, "1": 8, "2": 0, "3": 16, "4": 0,
               "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}
# 영문은 알파벳 이름의 받침 (L 엘 · M 엠 · N 엔 · R 아르 · X 엑스는 없음)
_ALPHA_JONG = {"l": 8, "m": 16, "n": 4, "r": 8}


def _has_jong(word: str) -> int | None:
    """마지막 글자의 받침 코드(0=없음). 판별 불가면 None."""
    if not word:
        return None
    ch = (word.rstrip(")]》」 ") or word)[-1]
    c = ord(ch)
    if 0xAC00 <= c <= 0xD7A3:
        return (c - 0xAC00) % 28
    if ch.isdigit():
        return _DIGIT_JONG[ch]
    if ch.isascii() and ch.isalpha():
        return _ALPHA_JONG.get(ch.lower(), 0)
    return None


def _eun(w: str) -> str:      # 은/는
    j = _has_jong(w)
    return f"{w}은" if j else f"{w}는"


def _euro(w: str) -> str:    # 으로/로 (ㄹ받침은 '로')
    j = _has_jong(w)
    return f"{w}로" if j in (None, 0, 8) else f"{w}으로"


def _ga(w: str) -> str:      # 이/가
    j = _has_jong(w)
    return f"{w}이" if j else f"{w}가"


def _reul(w: str) -> str:    # 을/를
    j = _has_jong(w)
    return f"{w}을" if j else f"{w}를"


# 국면(RRG 22섹터)에 매핑되는 ETF 테마만 국면 판정 대상 — 나머지는 전략상품(레짐 로직)
_THEME_TO_SECTOR = {"반도체": "반도체", "AI·전력": "AI·전력", "2차전지": "2차전지",
                    "방산": "방산", "조선": "조선", "원자력": "원자력"}
_STRATEGY_THEMES = {"커버드콜", "채권", "시장대표", "배당", "금·원자재", "빅테크", "바이오"}


def review_current_marketing(events: list, board: list, netbuy_df, week: str) -> list[dict]:
    """지금 집행 중인 KODEX 마케팅을 국면·자금 근거로 지속/확대/축소 판정.

    반환: [{ETF, 표기명, 판정, rank, 국면, 개인강도, 근거}] — 확대>지속류>축소 순.
    규칙:
      섹터 테마 상품 — 태동·확산→확대 / 과열→지속·신중(자금 이탈 시 축소) /
                      쇠퇴→축소(재매집+자금유입이면 지속·관찰)
      전략 상품(커버드콜·채권·코어) — 국면 대신 시장 레짐. 하락·변동성 장이면 방어 수요→지속
      신규상장 유입은 확대 근거에서 제외.
    """
    stage = {r["섹터"]: r.get("단계", "") for r in board}
    smart = {r["섹터"]: (r.get("외국인13주억") or 0) + (r.get("연기금13주억") or 0) for r in board}
    falling = sum(1 for r in board if r.get("단계") == "쇠퇴기") >= max(1, len(board) // 2)

    out, seen = [], set()
    for e in events:
        # 집행 중인 '마케팅'은 리워드를 건 프로모션만 센다. 블로그 소개 글까지 넣으면
        # 실제로 예산이 나가지 않는 상품도 '집행 중'이 되어 착수 판정이 흐려진다.
        if e.get("유형") != PROMO:
            continue
        name = e.get("표기명", "")
        if name in seen:
            continue
        seen.add(name)
        etf = e.get("ETF", name)
        theme, _ = classify_etf(etf if e.get("분석가능") else name)
        inten = _intensity_at(netbuy_df, etf, week)
        newlisting = inten is not None and inten >= _NEWLISTING_INTENSITY
        sector = _THEME_TO_SECTOR.get(theme)
        phase = stage.get(sector) if sector else None

        if phase is None or theme in _STRATEGY_THEMES:
            verdict, rank, ph = "지속", 1, "전략상품"
            if newlisting:
                why = f"{theme} 신규상장 — 하락장 방어 수요와 맞물린 초기 모멘텀. 확산기 진입까지 집행 유지."
            elif falling:
                why = f"{theme} 계열 방어·코어 상품. 하락·변동성 국면이라 방어 수요가 유지됩니다."
            else:
                why = f"{theme} 계열 코어 상품 — 꾸준한 집행 유지."
        elif phase in ("태동기", "확산기"):
            verdict, rank, ph = "확대", 0, phase
            why = f"{sector} {phase} — 관심이 오르는 테마라 마케팅 확대 적기."
            if inten is not None and 0 < inten < _NEWLISTING_INTENSITY:
                why += f" 개인 순매수 {inten:+.2f}% 동반."
        elif phase == "과열기":
            if inten is not None and inten < 0:
                verdict, rank, ph = "축소", 3, phase
                why = f"{sector} 과열기에 개인 순매수 {inten:+.2f}%로 이탈 — 고점 리스크. 마케팅 축소 검토."
            else:
                verdict, rank, ph = "지속·신중", 2, phase
                why = f"{sector} 과열기 — 고점 리스크로 확대는 자제하고 현 수준 유지."
        else:  # 쇠퇴기
            if smart.get(sector, 0) > 0 and (inten is None or inten >= 0):
                verdict, rank, ph = "지속·관찰", 2, phase
                why = f"{sector} 쇠퇴기이나 외국인·연기금 재매집(+{smart[sector]:,}억) 진행 — 조기 반등 가능성, 축소 보류하고 관찰."
            else:
                verdict, rank, ph = "축소", 3, phase
                why = f"{sector} 쇠퇴기 + 자금 이탈 — 마케팅 축소 검토."

        out.append({"ETF": etf, "표기명": name, "판정": verdict, "rank": rank,
                    "국면": ph, "개인강도": inten, "근거": why})
    out.sort(key=lambda x: x["rank"])
    return out


def build_recommendations(board: list, netbuy_df, week: str,
                          search_deltas: dict | None = None,
                          campaigns: list | None = None) -> list[dict]:
    """국면 × 자금 × 검색 × 재매집 × 캠페인을 교차해 다음 주 마케팅 권고를 생성.

    각 권고: {우선순위, rank, 분류, 제목, 근거}. rank가 낮을수록 상단(적극>선점>유지>관찰>주의).
    규칙:
      - 확산기 섹터 + 보유 KODEX 상품 → 적극 마케팅 (자금 유입 동반 시 근거 강화)
      - 현재 집행 중 캠페인 + 개인 순매수 반응 → 유지 (신규상장 왜곡은 분리 표기)
      - 태동기 섹터 → 선점 콘텐츠
      - 쇠퇴기 + 외국인·연기금 재매집(+) → 출시 준비 관찰
      - 검색 급등하나 과열·쇠퇴 국면 → 신규 대량 출시 주의
    """
    recs = []
    search_deltas = search_deltas or {}

    # 1) 확산기 적극 마케팅
    for r in board:
        if r.get("단계") != "확산기":
            continue
        prod = r.get("KODEX", "")
        wr = r.get("주간수익률")
        inten = _intensity_at(netbuy_df, prod, week)
        why = f"{_eun(r['섹터'])} 확산 국면(상대강도 {r.get('RS수준')}) — 관심이 오르는 구간이라 보유 상품 마케팅 집중이 정석입니다."
        if inten is not None and 0 < inten < _NEWLISTING_INTENSITY:
            why += f" 개인 순매수 강도 {inten:+.2f}%로 자금이 이미 유입 중이라 증폭 효과가 큽니다."
        if wr is not None and wr < -3:
            why += f" 단, 이번 주 {wr:+.1f}% 조정 중이라 방어 메시지 병행이 안전합니다."
        recs.append({"우선순위": "적극", "rank": 0, "분류": "확산기",
                     "제목": f"{r['섹터']} — {prod or 'KODEX 보유 상품'} 광고 집중", "근거": why})

    # 2) 집행 중 캠페인 유지 (자금 반응 확인)
    seen = set()
    for e in (campaigns or []):
        etf = e.get("ETF", "")
        if etf in seen:
            continue
        seen.add(etf)
        inten = _intensity_at(netbuy_df, etf, week)
        if inten is not None and inten >= _NEWLISTING_INTENSITY:
            why = f"신규상장 첫 주 유입(개인 강도 {inten:+.0f}%는 상장 효과 포함). 초기 모멘텀을 확산기 진입까지 이어가는 집행 유지가 필요합니다."
        elif inten is not None and inten > 0:
            why = f"현재 3채널 집행 중이며 개인 순매수 강도 {inten:+.2f}%로 실제 자금 반응이 확인됩니다 — 감이 아닌 데이터 근거로 유지 가치가 있습니다."
        else:
            why = "현재 집행 중인 캠페인. 다음 주 개인 순매수 반응을 보고 지속 여부를 판단합니다."
        recs.append({"우선순위": "유지", "rank": 2, "분류": "캠페인",
                     "제목": f"{e.get('표기명', etf)} 캠페인 유지", "근거": why})

    # 3) 태동기 선점
    for r in board:
        if r.get("단계") != "태동기":
            continue
        prod = r.get("KODEX", "")
        recs.append({"우선순위": "선점", "rank": 1, "분류": "태동기",
                     "제목": f"{r['섹터']} 선점 콘텐츠 검토",
                     "근거": f"{_eun(r['섹터'])} 유일한 태동 국면. {_euro(prod or 'KODEX 보유 상품')} 확산 전환 전 인지도를 미리 확보하는 것이 태동기 액션입니다."})

    # 4) 쇠퇴기 재매집 → 출시 준비 관찰
    decl = []
    for r in board:
        if r.get("단계") == "쇠퇴기":
            smart = (r.get("외국인13주억") or 0) + (r.get("연기금13주억") or 0)
            if smart > 0:
                decl.append((r["섹터"], smart, r.get("KODEX", "")))
    decl.sort(key=lambda x: -x[1])
    if decl:
        names = " · ".join(f"{s}(+{sm:,}억)" for s, sm, _ in decl[:2])
        recs.append({"우선순위": "관찰", "rank": 3, "분류": "재매집",
                     "제목": "쇠퇴기 재매집 섹터 출시 준비 모니터링",
                     "근거": f"{names} 등은 가격은 쇠퇴기지만 외국인·연기금이 순매수 전환 중 — 출시 리드타임(수개월)을 벌기 위한 파이프라인 후보입니다. 순환/구조 성격은 담당자 판단이 필요합니다."})

    # 5) 검색 급등 × 국면 부적기 → 주의
    stage_map = {r["섹터"]: r.get("단계", "") for r in board}
    _theme_sector = {"조선": "조선", "AI반도체": "반도체", "반도체": "반도체",
                     "2차전지": "2차전지", "방산": "방산", "원자력": "원자력", "K-방산": "방산"}
    hot = []
    for kw, v in sorted(search_deltas.items(), key=lambda x: -x[1])[:4]:
        if v < 15:
            continue
        sec = _theme_sector.get(kw)
        stg = stage_map.get(sec, "") if sec else ""
        if stg in ("과열기", "쇠퇴기"):
            hot.append(f"{kw}(검색 +{v:.0f}%·{stg})")
    if hot:
        recs.append({"우선순위": "주의", "rank": 4, "분류": "국면불일치",
                     "제목": "검색 급등 테마 — 신규 대량 출시 주의",
                     "근거": f"{' · '.join(hot)}. 관심은 최고조이나 국면상 고점/쇠퇴 구간이라, 신규 대량 출시보다 기존 상품 방어적 마케팅이 적합합니다."})

    recs.sort(key=lambda x: x["rank"])
    return recs


def real_netbuy_frame(flows: dict) -> pd.DataFrame:
    """배치 산출물 → 순매수 분석용 데이터프레임.
    컬럼: 주차·종목명·테마·기초시장·운용사·순매수액(개인, 억)·순자산(억)"""
    rows = []
    for e in flows.get("etfs", []):
        aum = e.get("순자산억")
        # 테마·기초시장은 JSON에 저장된 값 대신 현재 규칙으로 다시 분류한다.
        # 배치를 다시 돌리지 않아도 분류 개선이 즉시 반영되고, 규칙이 한 곳에만 있다.
        theme, market = classify_etf(e["종목명"])
        for w in e.get("주간", []):
            rows.append({
                "주차": w["주차"], "종목명": e["종목명"], "테마": theme,
                "기초시장": market, "운용사": e["운용사"],
                "순매수액": w.get("개인순매수억", 0), "순자산": aum,
            })
    df = pd.DataFrame(rows)
    if len(df):
        order = {w: i for i, w in enumerate(flows.get("weeks", []))}
        df["_o"] = df["주차"].map(order)
        df = df.sort_values(["종목명", "_o"]).drop(columns="_o").reset_index(drop=True)
    return df


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
    "PLUS": "UCEznrN8oroicBCrwjSyvCDA",           # 한화자산운용 (PLUS ETF)
    "TIMEFOLIO": "UCs7024kj-wa_c9Z5WgXbMFQ",      # TIME 액티브 ETF (타임폴리오)
}

_YT_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def _fetch_channel_videos(brand: str, channel_id: str, n: int = 3) -> list[dict]:
    """유튜브 RSS는 짧은 시간에 여러 번 부르면 500/404를 돌려준다(실측).
    한 번 실패했다고 빈 화면이 되지 않도록 간격을 두고 재시도한다."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    last = None
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            break
        last = r.status_code
        time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"HTTP {last}")
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


# 직전에 성공한 결과 — 일시적 스로틀로 화면이 통째로 비는 것을 막는다
_YT_LAST_GOOD: dict[str, list[dict]] = {}
YOUTUBE_STATUS: dict[str, str] = {}


def fetch_youtube(n_per_channel: int = 3) -> dict[str, list[dict]]:
    """8개 브랜드 유튜브 채널의 최신 영상 수집.

    동시 8개 요청은 유튜브 스로틀을 유발해 전 채널이 한꺼번에 비는 일이 있었다
    (실측: 15건 → 0건). 동시성을 낮추고, 실패한 채널은 직전 성공분으로 대체한다.
    실패 사유는 YOUTUBE_STATUS에 남겨 화면에서 '수집 실패'와 '영상 없음'을 구분한다."""
    out: dict[str, list[dict]] = {}
    YOUTUBE_STATUS.clear()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_channel_videos, b, cid, n_per_channel): b
            for b, cid in YOUTUBE_CHANNELS.items()
        }
        for fut, brand in futures.items():
            try:
                vids = fut.result()
                out[brand] = vids
                if vids:
                    _YT_LAST_GOOD[brand] = vids
            except Exception as e:
                out[brand] = _YT_LAST_GOOD.get(brand, [])
                YOUTUBE_STATUS[brand] = f"{type(e).__name__}: {e}"
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
# 판매채널 (증권·은행) 유튜브·블로그 — 키 불필요
# 채널 ID·블로그 ID는 공식 사이트 푸터 + 영상/게시물 제목으로 정체 검증 (2026-07 실측)
# 블로그가 None인 곳은 네이버 블로그 미운영 (토스증권·신한은행·한국투자증권)
# ══════════════════════════════════════════════
PARTNER_CHANNELS = [
    {"그룹": "증권", "회사": "키움증권",     "yt": "UCsNWZNw6LB9JYjDB1SMdJsw", "blog": "kiwoomhero"},
    {"그룹": "증권", "회사": "토스증권",     "yt": "UCW_P8DTCnlDcUHRfGFwRRLA", "blog": None},
    {"그룹": "증권", "회사": "미래에셋증권", "yt": "UCz9kpnQNdgrUTeSIjiyw6Iw", "blog": "how2invest"},
    {"그룹": "증권", "회사": "삼성증권",     "yt": "UCq7h8qFlHN5FL_T6waKZllw", "blog": "samsung_fn"},
    {"그룹": "증권", "회사": "한국투자증권", "yt": "UCh_9ffn36zS3HIQCwb3pgSQ", "blog": None},
    {"그룹": "은행", "회사": "KB국민은행",   "yt": "UCHq8auIJ8ewo7iD2pqX22UA", "blog": "youngkbblog"},
    {"그룹": "은행", "회사": "신한은행",     "yt": "UC4E394G9WuS9y6SlBZslMsQ", "blog": None},
    {"그룹": "은행", "회사": "하나은행",     "yt": "UCejh7cdlFSkCh_rqQT6WB8Q", "blog": "kebhana_official"},
    {"그룹": "은행", "회사": "NH농협은행",   "yt": "UCsR09lr9oy0DMv6gtqh-XCw", "blog": "nhbanksns"},
]

ETF_CONTENT_PAT = r"ETF|etf|상장지수|이티에프|커버드콜|월배당|연금.?투자|IRP|ISA"


def fetch_partners(n_per_source: int = 8) -> list[dict]:
    """증권·은행 채널의 유튜브 영상 + 블로그 글을 통합 피드로 수집 (날짜 내림차순).
    항목: {그룹, 회사, 소스, title, link, date, views}"""
    jobs = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for ch in PARTNER_CHANNELS:
            jobs.append((ch, "유튜브", ex.submit(_fetch_channel_videos, ch["회사"], ch["yt"], n_per_source)))
            if ch["blog"]:
                jobs.append((ch, "블로그", ex.submit(
                    _fetch_blog, ch["회사"], f"https://blog.rss.naver.com/{ch['blog']}.xml", n_per_source)))
        feed = []
        for ch, source, fut in jobs:
            try:
                for it in fut.result():
                    feed.append({
                        "그룹": ch["그룹"], "회사": ch["회사"], "소스": source,
                        "title": it["title"],
                        "link": it.get("url") or it.get("link", ""),
                        "date": it.get("published") or it.get("date", ""),
                        "views": it.get("views", 0),
                    })
            except Exception:
                pass
    feed.sort(key=lambda x: x["date"], reverse=True)
    return feed


# ══════════════════════════════════════════════
# 금융 규제 동향 (금융위 보도자료 · 입법예고 + 구글 뉴스) — 키 불필요
# ※ '법령 DB'가 아니라 '발표된 규제 동향'의 부분집합이다.
#    개정 이력·시행일의 완전한 목록은 국가법령정보센터 API(OC 키 발급 필요)가 있어야 한다.
# ══════════════════════════════════════════════
FSC_BASE = "https://www.fsc.go.kr"

# 우리 사업(ETF·자본시장)에 직접 닿는 주제만 남기기 위한 필터
REG_RELEVANT = re.compile(
    r"ETF|ETN|상장지수|자본시장|금융투자|집합투자|공모펀드|사모펀드|레버리지|파생|"
    r"인덱스펀드|퇴직연금|IRP|ISA|자산운용|투자자\s?보호|증권신고서|투자광고")
# '펀드'·'지수' 단독은 정책펀드(국민성장펀드 등)·물가지수까지 걸려 오탐이 많다(실측).
# 아래에 걸리면 관련 없음으로 되돌린다.
REG_EXCLUDE = re.compile(r"국민성장펀드|정책펀드|모태펀드|성장펀드|공적자금|기금")
# 규제 문서의 성격 분류
REG_KIND = [
    ("법률", r"법률|법\s?개정|제정법"),
    ("시행령", r"시행령"),
    ("규정·고시", r"감독규정|규정|고시|시행규칙"),
    ("정책방안", r"방안|대책|로드맵|계획"),
]


def _reg_kind(title: str) -> str:
    for k, pat in REG_KIND:
        if re.search(pat, title):
            return k
    return "기타"


def _fsc_page(path: str, link_pat: str, source: str, page: int) -> list[dict]:
    """금융위 게시판 한 페이지 파싱 — 제목/링크/날짜(첨부파일명 YYMMDD 또는 예고기간)."""
    from bs4 import BeautifulSoup
    r = requests.get(f"{FSC_BASE}{path}", params={"curPage": page},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if not re.search(link_pat, a["href"]):
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        title = re.sub(r"\s*\.?\s*금일 등록된 게시글$", "", title)
        if len(title) < 8 or title in seen:
            continue
        seen.add(title)
        date, period = "", ""
        card = a.find_parent(["li", "tr", "div"])
        scope = card.parent if card else None
        if scope:
            txt = scope.get_text(" ", strip=True)
            # 입법예고·규정변경예고: '예고기간 : 2026-05-22 ~ 2026-07-01'
            mp = re.search(r"예고기간\s*[:：]\s*(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", txt)
            if mp:
                date, period = mp.group(1), f"{mp.group(1)} ~ {mp.group(2)}"
            else:
                # 보도자료: 첨부파일명이 'YYMMDD(보도자료)…' 형태
                m = re.search(r"\b(\d{2})(\d{2})(\d{2})\s*[\(\[]", txt)
                if m:
                    date = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
        href = a["href"].lstrip(".")
        rel = bool(REG_RELEVANT.search(title)) and not REG_EXCLUDE.search(title)
        out.append({
            "제목": title, "링크": href if href.startswith("http") else FSC_BASE + href,
            "date": date, "예고기간": period, "출처": source, "유형": _reg_kind(title),
            "관련": rel,
        })
    return out


# 게시판별 스캔 깊이 — 한 페이지 10건.
# 보도자료는 전 금융 분야가 매일 쌓여 ETF 건이 앞쪽에 몰리지만(3페이지면 충분),
# 입법예고는 건수가 적고 자본시장 관련이 뒤쪽까지 흩어져 있다 (실측: 1p 1건 → 6p 11건).
FSC_BOARDS = [
    ("/no010101", r"/no010101/\d+", "금융위 보도자료", 3),
    ("/po040301", r"po040301/view\?noticeId=\d+", "입법예고·규정변경", 6),
]


def fetch_regulations(limit: int = 12) -> tuple[list[dict], dict]:
    """금융위 보도자료 + 입법예고/규정변경예고 수집.

    반환: (목록, 출처별 상태). 상태 = {출처: {"수집": n, "관련": n, "오류": str|None}}
    수집 실패와 '수집은 됐지만 관련 건이 없음'을 화면에서 구분할 수 있어야 하므로
    예외를 삼키지 않고 사유를 함께 돌려준다.
    """
    items: list[dict] = []
    status: dict[str, dict] = {}
    for path, pat, src, pages in FSC_BOARDS:
        got, err, seen = [], None, set()
        for pg in range(1, pages + 1):
            try:
                rows = _fsc_page(path, pat, src, pg)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                break
            fresh = [r for r in rows if r["제목"] not in seen]
            if not fresh:          # 페이지네이션이 끝났거나 같은 목록이 반복됨
                break
            seen.update(r["제목"] for r in fresh)
            got += fresh
        status[src] = {"수집": len(got), "관련": sum(1 for r in got if r["관련"]),
                       "오류": err if not got else None}
        items += got
    items.sort(key=lambda x: (x["date"] or "", x["관련"]), reverse=True)
    return items, status


# ── 국가법령정보센터 OpenAPI — 근거 법령의 현행 상태·시행일 ─────────────
# OC는 이메일 앞부분(무료 발급). 미설정 시 공개 테스트 계정으로 동작한다.
LAW_API = "https://www.law.go.kr/DRF/lawSearch.do"
# ETF 마케팅에 직접 닿는 근거 법령·규정
LAW_TARGETS = [
    ("자본시장과 금융투자업에 관한 법률", "법률"),
    ("자본시장과 금융투자업에 관한 법률 시행령", "시행령"),
    ("금융투자업규정", "행정규칙"),
    ("금융소비자 보호에 관한 법률", "법률"),
]


def _law_query(name: str, kind: str, oc: str) -> dict | None:
    """법령명으로 현행 법령 1건 조회 — 공포일자·시행일자·제개정구분."""
    target = "admrul" if kind == "행정규칙" else "law"
    try:
        r = requests.get(LAW_API, params={
            "OC": oc, "target": target, "type": "XML", "query": name, "display": "5",
        }, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        root = ET.fromstring(r.content)
        if root.findtext("resultCode") not in (None, "00"):
            return None
        node = root.find("law") if target == "law" else root.find("admrul")
        if node is None:
            return None

        def g(*tags):
            for t in tags:
                v = node.findtext(t)
                if v and v.strip():
                    return v.strip()
            return ""

        def fmt(d):
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 and d.isdigit() else d

        return {
            "법령명": g("법령명한글", "행정규칙명"),
            "약칭": g("법령약칭명"),
            "구분": g("법령구분명", "행정규칙종류") or kind,
            "제개정": g("제개정구분명"),
            "공포일": fmt(g("공포일자", "발령일자")),
            "시행일": fmt(g("시행일자")),
            "소관": g("소관부처명"),
            "현행": g("현행연혁코드") or "현행",
            "링크": "https://www.law.go.kr" + g("법령상세링크", "행정규칙상세링크"),
        }
    except Exception:
        return None


def fetch_laws() -> tuple[list[dict], bool]:
    """ETF 마케팅 근거 법령의 현행 상태. 반환: (목록, 실데이터 여부).

    보도자료는 '발표'를 보여주지만 실제 규제는 **시행일**부터 적용된다.
    시행 전후로 상품 메시지가 달라져야 하므로 시행일을 함께 본다."""
    oc = os.environ.get("LAW_OC") or "test"
    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_law_query, n, k, oc): (n, k) for n, k in LAW_TARGETS}
        for fut in futs:
            r = fut.result()
            if r and r.get("법령명"):
                out.append(r)
    # 시행일 임박·최신 개정 순
    out.sort(key=lambda x: x.get("시행일") or "", reverse=True)
    return out, bool(out)


def fetch_regulation_news(query: str = "ETF 규제 자본시장법 개정", limit: int = 10) -> list[dict]:
    """규제 관련 뉴스 (구글 뉴스 RSS) — 보도자료가 놓친 건을 보완."""
    try:
        r = requests.get(
            f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        root = ET.fromstring(r.content)
        out = []
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            if not t:
                continue
            out.append({"제목": t, "링크": (it.findtext("link") or "").strip(),
                        "date": _rss_date(it.findtext("pubDate") or ""),
                        "유형": _reg_kind(t)})
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


# ══════════════════════════════════════════════
# 네이버 데이터랩 검색 트렌드
# NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 설정 시 실데이터, 미설정 시 데모
# ══════════════════════════════════════════════
DATALAB_GROUPS = ["KODEX", "TIGER", "ACE", "SOL", "HANARO", "RISE", "PLUS", "TIMEFOLIO"]

# 브랜드별 검색 키워드 — SOL·PLUS·ACE·RISE·TIGER는 단독어 오염이 심해(예: SOL=신한앱·솔라나)
# 'ETF' 한정어를 사용, 고유 브랜드(KODEX·HANARO·TIMEFOLIO)만 단독 키워드 허용 (2026-07 실측)
DATALAB_KEYWORDS = {
    "KODEX": ["KODEX", "코덱스 ETF"],
    "TIGER": ["TIGER ETF", "타이거 ETF"],
    "ACE": ["ACE ETF", "에이스 ETF"],
    "SOL": ["SOL ETF", "쏠 ETF"],
    "HANARO": ["HANARO", "하나로 ETF"],
    "RISE": ["RISE ETF", "라이즈 ETF"],
    "PLUS": ["PLUS ETF", "플러스 ETF"],
    "TIMEFOLIO": ["TIMEFOLIO", "타임폴리오"],
}
_DATALAB_ANCHOR = "KODEX"  # 데이터랩 요청당 그룹 5개 제한 → 2회 분할, 공통 앵커로 배율 보정


def _demo_datalab(n_weeks: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    today = dt.date.today()
    rows = []
    base = {"KODEX": 82, "TIGER": 58, "ACE": 30, "SOL": 22, "HANARO": 18,
            "RISE": 26, "PLUS": 12, "TIMEFOLIO": 14}
    for g in DATALAB_GROUPS:
        level = base.get(g, 20)
        for i in range(n_weeks - 1, -1, -1):
            d = today - dt.timedelta(weeks=i)
            level = max(4, level + rng.normal(0.3, 3))
            rows.append({"date": d.isoformat(), "group": g, "ratio": round(level, 1)})
    return pd.DataFrame(rows)


def _datalab_batch(cid, csec, start, end, groups) -> dict[str, dict]:
    """한 번의 데이터랩 요청 → {브랜드: {날짜: ratio}}."""
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "week",
        "keywordGroups": [{"groupName": g, "keywords": DATALAB_KEYWORDS[g]} for g in groups],
    }
    r = requests.post(
        "https://openapi.naver.com/v1/datalab/search", json=body,
        headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec,
                 "Content-Type": "application/json"}, timeout=10,
    )
    r.raise_for_status()
    return {res["title"]: {pt["period"]: pt["ratio"] for pt in res["data"]}
            for res in r.json()["results"]}


def fetch_datalab(client_id: str | None = None, client_secret: str | None = None) -> tuple[pd.DataFrame, bool]:
    """네이버 데이터랩 주간 검색량 (8개 브랜드). 반환: (데이터, 실데이터 여부).

    데이터랩은 요청당 키워드 그룹 5개 제한 + 요청마다 최대값=100으로 따로 정규화되므로,
    두 요청에 공통 앵커(KODEX)를 넣고 앵커 수준이 일치하도록 2번째 배치를 배율 보정한다."""
    cid = client_id or os.environ.get("NAVER_CLIENT_ID")
    csec = client_secret or os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and csec):
        return _demo_datalab(), False
    try:
        today = dt.date.today()
        end = today - dt.timedelta(days=today.weekday() + 1)  # 지난 일요일 — 미완결 주 왜곡 방지
        start = end - dt.timedelta(weeks=12)
        others = [b for b in DATALAB_GROUPS if b != _DATALAB_ANCHOR]
        batch1 = [_DATALAB_ANCHOR] + others[:4]   # 앵커 + 4 (5개)
        batch2 = [_DATALAB_ANCHOR] + others[4:]   # 앵커 + 나머지
        d1 = _datalab_batch(cid, csec, start, end, batch1)
        d2 = _datalab_batch(cid, csec, start, end, batch2)

        # 앵커 배율: batch1 기준으로 batch2를 맞춤
        a1, a2 = d1[_DATALAB_ANCHOR], d2[_DATALAB_ANCHOR]
        common = [p for p in a1 if p in a2 and a2[p] > 0]
        k = (sum(a1[p] for p in common) / sum(a2[p] for p in common)) if common else 1.0

        rows = []
        for g in batch1:
            for p, v in d1[g].items():
                rows.append({"date": p, "group": g, "ratio": round(v, 2)})
        for g in batch2:
            if g == _DATALAB_ANCHOR:
                continue  # 앵커는 batch1에서 이미 추가
            for p, v in d2[g].items():
                rows.append({"date": p, "group": g, "ratio": round(v * k, 2)})
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


# ── 마케팅 이벤트 탐지 — DiD의 '처치'를 채널 수집물에서 정의한다 ──────────
# 배너·유튜브·블로그 제목이 특정 ETF를 지목하면 그 주차를 개입 시점으로 본다.
# ETF명 매칭은 '정확일치'만 허용 — 부분일치를 허용하면
# 'KODEX 200커버드콜액티브'가 별개 상품인 'KODEX 200'에 붙어 분석이 오염된다(실측 확인).
# 브랜드 접두 상품명 — 배너가 '무엇을' 주목하는지 뽑는 데 쓴다.
# TIME은 TIMEFOLIO의 리브랜딩 표기라 함께 받는다.
# 브랜드 + (붙어 있는 수식어) + 공백 + 한 토큰.
# 두 토큰을 받으면 'HANARO 미국AI광통신TOP10 미국'처럼 뒤 설명문까지 삼킨다.
# 대신 'RISE미국 우주&로봇TOP2'처럼 브랜드에 글자가 붙는 표기를 흡수한다.
_BRAND_PROD = re.compile(
    r"(?:KODEX|TIGER|ACE|SOL|HANARO|RISE|PLUS|TIMEFOLIO|TIME)"
    r"[가-힣A-Za-z0-9&\+\.]*\s?[가-힣A-Za-z0-9&\+\.]+")


def banner_focus(title: str) -> str:
    """배너가 주목하는 대상 — 상품명이 있으면 상품명, 없으면 테마 키워드.

    'TIGER ETF'처럼 브랜드 일반 언급은 상품이 아니므로 테마로 넘긴다."""
    m = _BRAND_PROD.search(title or "")
    if m:
        raw = re.sub(r"\s*ETF\s*$", "", m.group(0).strip())
        # 브랜드명만 남거나 'TIGER ETF' 꼴이면 상품 지목이 아니다
        tail = re.sub(r"^(?:KODEX|TIGER|ACE|SOL|HANARO|RISE|PLUS|TIMEFOLIO|TIME)", "", raw).strip()
        if len(tail) >= 2 and not tail.upper().startswith("ETF"):
            return raw
    for kw, pat in NEWS_KW_PATTERNS:
        if re.search(pat, title or ""):
            return kw
    # 상품도 테마도 없으면 브랜드가 스스로 붙인 카테고리 라벨을 쓴다 ('[ETF 포트폴리오] …')
    m = re.match(r"\s*\[([^\]]{2,16})\]", title or "")
    return m.group(1).strip() if m else ""


_ETF_MENTION = re.compile(r"KODEX\s+[가-힣A-Za-z0-9&\+\.]+(?:\s*[가-힣A-Za-z0-9&\+\.]+)?")


def _norm_etf(name: str) -> str:
    return re.sub(r"[\s·\-]|ETF", "", name).upper()


def week_label_of(date_str: str) -> str:
    """ISO 날짜 → 주차 라벨('7월 3주'). week_labels()와 동일 규칙."""
    try:
        d = dt.date.fromisoformat(date_str[:10])
    except Exception:
        return ""
    return f"{d.month}월 {(d.day - 1) // 7 + 1}주"


# 프로모션 — 투자자에게 리워드를 걸고 행동(매수·응모·인증)을 요구하는 판촉.
# 블로그 글 한 편과는 성격이 다르다: 비용이 들고, 기간이 정해지고, 순매수를 직접 겨냥한다.
_PROMO_PAT = re.compile(
    r"이벤트|응모|추첨|경품|증정|사은|캐시백|리워드|인증|퀴즈|룰렛|"
    r"적립식\s?매수|매수\s?챌린지|선착순")
# 콘텐츠 푸시 — 리워드 없이 상품을 알리는 집행(신규상장 안내 배너, 상품 소개 글·영상).
# 마케팅이 아닌 건 아니지만 프로모션과 같은 칸에 세면 판촉 규모를 부풀린다.
_LAUNCH_PAT = re.compile(r"신규\s?상장|출시|런칭|특별\s?분배|오픈|사전\s?예약")
# 정기물 — 특정 상품 푸시가 아니라 매주·매분기 반복되는 리포트류. DiD의 '개입'으로 볼 수 없다.
# ※ '팩트체크' 같은 순회 시리즈는 회차마다 다른 상품을 다루므로(실측 확인) 정기물이 아니라 캠페인이다.
_ROUTINE_PAT = re.compile(r"WEEKLY|주간|월간|분기|성과\s?리뷰|운용\s?계획|시황|랭킹|리포트", re.I)

# DiD의 '개입'으로 볼 수 있는 유형 — 프로모션이 우선, 콘텐츠는 보조
PROMO, CONTENT = "프로모션", "콘텐츠"
CAMPAIGN_TYPES = (PROMO, CONTENT)


def classify_marketing_events(events: list[dict]) -> list[dict]:
    """이벤트를 프로모션 / 콘텐츠 / 정기 / 단순언급으로 분류하고 '유형'·'근거'를 채운다.

    프로모션과 콘텐츠를 나누는 이유: 매수·인증 이벤트는 리워드를 걸고 투자자에게
    행동을 요구하는 판촉이고, 블로그 소개 글은 인지도 콘텐츠다. 같은 칸에 세면
    '캠페인 5종'처럼 판촉 규모가 부풀려진다. 둘 다 개입이지만 급이 다르다.

    프로모션 = 운용사 이벤트 보드 등재(기간 고지) 또는 제목에 판촉 신호어
    콘텐츠   = ① 신규상장·출시 안내 등 상품 푸시 신호어
               ② 같은 ETF가 7일 이내에 2개 이상 채널에 등장(집중 집행)
    정기     = 주간·분기 리포트 등 평소 반복 포맷 → 개입이 아니므로 DiD 제외
    단순언급 = 1개 채널 단발 등장 (교육 콘텐츠에 예시로 언급된 경우 등)"""
    def _d(s):
        try:
            return dt.date.fromisoformat(s[:10])
        except Exception:
            return None

    by_etf: dict[str, list[dict]] = {}
    for e in events:
        by_etf.setdefault(e["표기명"], []).append(e)

    multi = set()
    for evs in by_etf.values():
        for i, a in enumerate(evs):
            da = _d(a["date"])
            if da is None:
                continue
            chans = {b["채널"] for b in evs
                     if _d(b["date"]) and abs((da - _d(b["date"])).days) <= 7}
            if len(chans) >= 2:
                multi.add(id(a))

    for e in events:
        title = e.get("제목", "")
        # 이벤트 보드 출처는 추정이 아니라 운용사가 직접 고지한 집행이다 — 최상위 근거
        if e.get("채널") == "이벤트":
            e["유형"] = PROMO
            e["근거"] = (f'이벤트 {e.get("시작","")}~{e.get("종료","")}'
                        if e.get("시작") else "이벤트 보드")
        elif _PROMO_PAT.search(title):
            e["유형"], e["근거"] = PROMO, "판촉 신호어"
        elif _LAUNCH_PAT.search(title):
            e["유형"], e["근거"] = CONTENT, "상품 푸시 신호어"
        elif id(e) in multi:
            e["유형"], e["근거"] = CONTENT, "복수 채널 동시 집행"
        elif _ROUTINE_PAT.search(title):
            e["유형"], e["근거"] = "정기", "정기 리포트 포맷"
        else:
            e["유형"], e["근거"] = "단순언급", "단발 언급"
    return events


def detect_marketing_events(banners: list[dict], videos: list[dict], posts: list[dict],
                            universe: list[str] | None = None,
                            events_board: list[dict] | None = None) -> list[dict]:
    """채널 수집물에서 ETF를 지목한 마케팅 이벤트를 추출.

    반환: [{ETF, 표기명, 주차, date, 채널, 제목, 링크, 분석가능}] — 날짜 내림차순.
    분석가능=False는 순매수 유니버스에 없는 ETF(=DiD 계산 불가, 데이터 연동 필요).

    events_board(운용사 이벤트 보드)는 다른 소스와 성격이 다르다 — 배너·영상·글은
    '언제 올라왔나'만 알 수 있어 개입 시점을 수집일로 근사하지만, 이벤트는 집행
    시작일·종료일이 명시돼 있다. 그래서 개입 주차를 시작일로 잡고 구간을 함께 싣는다."""
    uni = {_norm_etf(n): n for n in (universe if universe is not None else kodex_etfs())}
    src = []
    for b in banners or []:
        src.append(("홈페이지", b.get("제목", ""), b.get("링크", ""), b.get("date", ""), None))
    for v in videos or []:
        src.append(("유튜브", v.get("title", ""), v.get("url", ""), v.get("published", ""), None))
    for p in posts or []:
        src.append(("블로그", p.get("title", ""), p.get("link", ""), p.get("date", ""), None))
    for e in events_board or []:
        # 개입 시점 = 이벤트 시작일 (수집일이 아니다)
        src.append(("이벤트", e.get("제목", ""), e.get("링크", ""), e.get("시작", ""), e))

    events = []
    for channel, title, link, date, meta in src:
        m = _ETF_MENTION.search(title or "")
        if not m:
            continue
        raw = re.sub(r"\s*ETF\s*$", "", m.group(0).strip())
        tail = raw[len("KODEX"):].strip()
        if len(tail) < 2 or tail.startswith("ETF"):
            continue  # 'KODEX ETF가 제안하는' 같은 브랜드 일반 언급은 제외
        matched = uni.get(_norm_etf(raw))
        row = {
            "ETF": matched or raw, "표기명": raw, "채널": channel,
            "제목": title, "링크": link, "date": (date or "")[:10],
            "주차": week_label_of(date or ""), "분석가능": matched is not None,
        }
        if meta:
            row.update({"시작": meta.get("시작", ""), "종료": meta.get("종료", ""),
                        "상태": meta.get("상태", "")})
        events.append(row)
    classify_marketing_events(events)
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# 실행 대상으로 올릴 판정 — 나머지는 화면에서 뺀다.
# 판정 결과를 전부 늘어놓으면 선별한 의미가 없고 읽는 사람이 다시 골라야 한다.
EMERGING_ACTIONABLE = ("착수", "선점 검토")
GAP_ACTIONABLE = ("출시 검토", "선점 기회", "시점 대기", "차별화 필요")


def split_actionable(rows: list[dict], actionable: tuple[str, ...]) -> tuple[list[dict], str]:
    """(실행 대상, 제외 요약). 제외된 것은 개수와 사유만 한 줄로 남긴다."""
    keep = [r for r in rows if r.get("판정") in actionable]
    dropped = [r for r in rows if r.get("판정") not in actionable]
    if not dropped:
        return keep, ""
    from collections import Counter as _C2
    cnt = _C2(r.get("판정", "기타") for r in dropped)
    return keep, " · ".join(f"{k} {v}" for k, v in cnt.most_common())


# 태동기 착수 판정 기준 — 캠페인 예산은 한 번에 억 단위로 나간다. 틀린 착수의
# 비용이 놓친 기회의 비용보다 크므로, 애매하면 올리지 않는 쪽으로 기울인다.
EMERGING_MOM_STRONG = 8.0    # RS모멘텀 — 이 이상이면 '뚜렷하게 돌아서는 중'
EMERGING_NEAR_CROSS = -3.0   # RS수준 — 0에 이만큼 근접하면 확산 전환 임박

# 마케팅 집행 최소 규모(순자산, 억). 국면이 좋아도 상품이 작으면 회수가 안 된다.
# 운용보수는 순자산에 비례한다. 국내 섹터 ETF 총보수는 대략 0.15~0.45%라
# 순자산 1,000억이면 연 1.5~4.5억이고, 캠페인으로 50%를 키워도 증분은 연 1~2억이다.
# 캠페인 한 건 비용이 그 수준이므로 1,000억이 회수 가능성의 현실적인 하한이다.
# (예전 하한 300억은 증분이 연 5천만원도 안 돼 사실상 회수가 불가능했다.)
AUM_MARKETABLE = 1000.0
AUM_COMFORTABLE = 3000.0     # 이 이상이면 규모 제약 없음


def emerging_launch_review(board: list[dict], is_marketed, aum_of=None) -> list[dict]:
    """태동 섹터 중 '지금 착수할 만한 곳'을 판정한다.

    태동기 전체를 나열하는 건 점검이 아니다 — 무엇을 해야 하는지 골라줘야 한다.
    착수 근거는 성격이 다른 두 가지다:

      전환 임박 : 모멘텀이 강하고 RS수준이 0에 근접 — 곧 확산기로 넘어간다.
                 콘텐츠 제작에 리드타임이 걸리므로 넘어간 뒤 시작하면 늦다.
      조용한 매집: 외국인·연기금이 사고 개인이 파는 구간 — 가격이 아직 움직이지
                 않았을 때 수급이 먼저 도는 신호다(가격 지표엔 없는 정보).

    둘 다 아니면 '관찰'로 남긴다. 상품이 없으면 애초에 밀 수가 없으므로
    신규 출시 검토로 넘긴다.
    """
    out = []
    for r in board:
        if r.get("단계") != "태동기":
            continue
        sec, kodex = r["섹터"], (r.get("KODEX") or "").strip()
        mom, lvl = r.get("RS모멘텀"), r.get("RS수준")
        big = (r.get("외국인13주억") or 0) + (r.get("연기금13주억") or 0)
        indiv = r.get("개인13주억") or 0
        aum = (aum_of(kodex) if (aum_of and kodex) else None)
        row = {"섹터": sec, "kodex": kodex, "모멘텀": mom, "수준": lvl,
               "큰손13주억": big, "개인13주억": indiv, "순자산억": aum}

        if not kodex:
            row.update(판정="상품 없음", 우선순위=3,
                       근거="해당 섹터 KODEX 상품 미보유 — 신규 출시 검토 대상")
        elif is_marketed(kodex):
            row.update(판정="집행 중", 우선순위=2, 근거="이미 마케팅 집행 중 — 착수 대상 아님")
        elif mom is None or lvl is None:
            row.update(판정="관찰", 우선순위=2, 근거="지표 산출 불가")
        elif aum_of is not None and aum is None:
            # 상품명은 있는데 순자산이 안 잡힌다 = 상장폐지·개명 가능성.
            # 확인 안 된 것을 착수로 올리면 없는 상품을 밀라고 하는 셈이다.
            row.update(판정="확인 필요", 우선순위=2,
                       근거=f"'{kodex}' 순자산 조회 불가 — 상장폐지·개명 여부 확인 후 재판정")
        elif aum is not None and aum < AUM_MARKETABLE:
            # 국면 판정보다 앞선다 — 아무리 좋은 국면이어도 회수가 안 되면 집행 대상이 아니다
            row.update(판정="규모 미달", 우선순위=2,
                       근거=f"순자산 {aum:,.0f}억으로 집행 하한({AUM_MARKETABLE:,.0f}억) 미만 "
                            f"— 국면은 유효하나 마케팅비 대비 회수가 어렵다")
        else:
            near = lvl >= EMERGING_NEAR_CROSS
            strong = mom >= EMERGING_MOM_STRONG
            quiet = big > 0 and indiv < 0          # 큰손 매수 · 개인 매도
            _sz = ("" if aum is None else
                   f" 순자산 {aum:,.0f}억으로 규모도 충분하다." if aum >= AUM_COMFORTABLE else
                   f" 다만 순자산 {aum:,.0f}억으로 크지 않아 집행 규모는 조절이 필요하다.")
            if strong and near and big >= 0:
                # 큰손 자금이 빠지는 중이면 가격만 오른 반등일 수 있다 — 착수로 올리지 않는다
                row.update(판정="착수", 우선순위=0,
                           근거=f"확산 전환 임박 — 모멘텀 {mom:+.1f}, 시장 대비 {lvl:+.1f}로 "
                                f"평균선 회복 직전이고 외국인·연기금도 {big:+,}억으로 이탈이 없다. "
                                f"리드타임 감안 지금 착수.{_sz}")
            elif strong and near:
                row.update(판정="선점 검토", 우선순위=1,
                           근거=f"모멘텀 {mom:+.1f}로 평균선 회복 직전이나 외국인·연기금이 "
                                f"{big:+,}억 이탈 중 — 큰손 자금이 돌아설 때까지 소재만 준비")
            elif quiet and strong:
                row.update(판정="착수", 우선순위=0,
                           근거=f"조용한 매집 — 외국인·연기금 {big:+,}억 순매수, 개인 {indiv:+,}억 "
                                f"순매도. 가격({mom:+.1f})보다 수급이 먼저 돌았다.{_sz}")
            elif quiet:
                row.update(판정="선점 검토", 우선순위=1,
                           근거=f"외국인·연기금 {big:+,}억 매집 중이나 모멘텀 {mom:+.1f}로 아직 약함 "
                                f"— 소재 선점만 준비")
            elif strong:
                row.update(판정="선점 검토", 우선순위=1,
                           근거=f"모멘텀 {mom:+.1f}로 강하나 큰손 자금은 {big:+,}억 유출 "
                                f"— 가격만 오른 반등일 수 있어 확인 필요")
            else:
                row.update(판정="관찰", 우선순위=2,
                           근거=f"모멘텀 {mom:+.1f}·시장 대비 {lvl:+.1f} — 돌아서는 초입이라 아직 이름")
        out.append(row)
    out.sort(key=lambda x: (x["우선순위"], -(x["모멘텀"] if x["모멘텀"] is not None else -99)))
    return out


# 신규 출시 판정 기준 — 공백이라고 다 채울 일이 아니다. 출시 후 모을 수 있어야 한다.
GAP_MARKET_VIABLE = 3000.0   # 테마 시장 규모(경쟁사 순자산 합, 억). 이 미만이면 수요 자체가 작다
GAP_MARKET_LARGE = 10000.0   # 1조 이상이면 후발이어도 파이가 크다
GAP_DOMINANCE = 0.60         # 1위가 시장의 이 비율을 넘으면 이미 굳어진 판


def gap_launch_review(gaps: list[dict], stage_of, aum_of, limit: int = 8) -> list[dict]:
    """라인업 공백 중 '실제로 출시할 만한 곳'을 판정한다.

    공백 = 기회가 아니다. 경쟁사가 안 만든 게 아니라 만들었는데 안 모인 테마도
    공백으로 잡힌다. 출시 판단에는 세 가지를 본다:

      시장 규모  경쟁사들이 그 테마에서 실제로 모은 순자산 합계. 작으면 수요가 없다.
      경쟁 구도  1위 점유율. 이미 굳어진 판이면 후발로 뺏기 어렵다.
      국면      과열·쇠퇴면 지금 내도 늦다(리드타임 감안 준비만).
    """
    out = []
    for g in gaps[:limit]:
        theme, market = g["테마"], g["시장"]
        peers = gap_competitors(theme, market, limit=8)
        sizes = [(p, aum_of(p)) for p in peers]
        sizes = [(p, v) for p, v in sizes if v is not None]
        total = sum(v for _, v in sizes)
        top = max(sizes, key=lambda x: x[1]) if sizes else None
        share = (top[1] / total) if (top and total > 0) else None
        stage = stage_of(theme) or ""
        row = {"테마": theme, "시장": market, "경쟁사수": g["경쟁사수"],
               "브랜드": ", ".join(f"{b} {n}" for b, n in
                                 sorted(g["브랜드"].items(), key=lambda x: -x[1])),
               "국면": stage, "시장규모억": total if sizes else None,
               "1위": top[0] if top else "", "1위순자산": top[1] if top else None,
               "점유율": share, "확인종수": len(sizes)}

        n_rivals = g["경쟁사수"]
        if not sizes:
            row.update(판정="확인 필요", 우선순위=3,
                       근거="경쟁사 순자산을 확인하지 못했다 — 시장 규모 미상")
        elif n_rivals <= 2:
            # 선발이 1~2곳 — 경쟁사 수가 적어 시장 규모만으로는 판단할 수 없다.
            # 아직 아무도 못 키운 것인지, 이제 열리는 시장인지가 갈린다.
            if total >= GAP_MARKET_VIABLE:
                row.update(판정="선점 기회", 우선순위=0,
                           근거=f"선발 {n_rivals}곳뿐인데 이미 {total:,.0f}억을 모았다 "
                                f"— 경쟁이 굳기 전에 들어갈 여지가 있다")
            else:
                row.update(판정="시장 미검증", 우선순위=3,
                           근거=f"선발 {n_rivals}곳이 {total:,.0f}억에 그친다 "
                                f"— 수요가 없는 것인지 아직 안 열린 것인지 확인 필요")
        elif total < GAP_MARKET_VIABLE:
            row.update(판정="보류", 우선순위=3,
                       근거=f"경쟁 {len(sizes)}종이 모은 돈이 다 합쳐 {total:,.0f}억 "
                            f"— 만들어도 모일 시장이 아니다")
        elif share is not None and share >= GAP_DOMINANCE:
            row.update(판정="차별화 필요", 우선순위=2,
                       근거=f"시장 {total:,.0f}억 중 {top[0]}가 {share:.0%} 독식 "
                            f"— 같은 구성으로는 후발 진입이 어렵다")
        elif stage in ("과열기", "쇠퇴기"):
            row.update(판정="시점 대기", 우선순위=1,
                       근거=f"시장 {total:,.0f}억으로 규모는 되나 국면이 {stage} "
                            f"— 리드타임 감안 준비만, 출시는 진정 후")
        else:
            _sz = "1조 이상 대형 시장" if total >= GAP_MARKET_LARGE else f"시장 {total:,.0f}억"
            row.update(판정="출시 검토", 우선순위=0,
                       근거=f"{_sz}에 KODEX만 부재 · 1위 {top[0]} {share:.0%}로 "
                            f"독점 구도도 아니다")
        out.append(row)
    out.sort(key=lambda x: (x["우선순위"], -(x["시장규모억"] or 0)))
    return out


def dedupe_campaigns(events: list[dict]) -> list[dict]:
    """같은 ETF의 캠페인을 하나로 묶는다 — DiD는 상품당 한 번만 돌리면 된다.

    같은 상품을 홈페이지·유튜브·블로그·이벤트에 동시 집행하면 채널 수만큼
    이벤트가 잡히는데, 순매수 시계열은 하나뿐이라 몇 번을 돌려도 처치군은 같다.
    달라지는 건 개입 주차뿐이고, 그건 '가장 먼저 시작한 시점'이 맞다.

    대표 선정: 집행 기간이 명시된 이벤트 > 그 외 최초 감지일.
    묶인 채널 목록은 '멀티채널 집행'의 근거로 남긴다."""
    by_etf: dict[str, list[dict]] = {}
    for e in events:
        by_etf.setdefault(e["ETF"], []).append(e)

    out = []
    for etf, evs in by_etf.items():
        dated = [e for e in evs if e.get("date")]
        board = [e for e in dated if e.get("채널") == "이벤트"]
        # 이벤트 보드가 있으면 그 시작일이 개입 시점 — 추정이 아니라 고지된 값이다
        rep = min(board or dated or evs, key=lambda e: e.get("date") or "9999")
        rep = dict(rep)
        chans = sorted({e["채널"] for e in evs})
        rep["채널목록"] = chans
        rep["채널수"] = len(chans)
        rep["감지건수"] = len(evs)
        if len(chans) > 1:
            rep["근거"] = f'{rep.get("근거", "")} · {len(chans)}개 채널 동시'.strip(" ·")
        # 상품 단위 유형 — 한 채널이라도 프로모션이면 그 상품은 판촉 대상이다
        promo = [e for e in evs if e.get("유형") == PROMO]
        rep["유형"] = PROMO if promo else CONTENT
        rep["프로모션채널"] = sorted({e["채널"] for e in promo})
        # 정렬 기준은 '언제 시작했나'가 아니라 '얼마나 밀고 있나'.
        # 날짜로 정렬하면 블로그 글 한 건이 기간 고지된 신규상장 이벤트를 앞선다.
        # (배너는 게시일이 없어 수집일이 붙으므로 날짜 정렬에 특히 취약하다.)
        rep["집행강도"] = (30 if promo else 0) + len(chans) * 10 + min(len(evs), 4)
        out.append(rep)
    out.sort(key=lambda e: (e["집행강도"], e.get("date") or ""), reverse=True)
    return out


def kodex_etfs() -> list[str]:
    return sorted(n for n, _, issuer in ETF_UNIVERSE if issuer == "KODEX")


INVERSE_LEV_PAT = re.compile(r"인버스|레버리지|2X|3X|곱버스")


def control_group(treat_name: str, universe: pd.DataFrame | None = None) -> list[str]:
    """처치군과 '테마 + 기초시장'이 모두 같은 비(非)KODEX 경쟁 ETF 자동 매핑.

    기초시장까지 일치시키는 이유: 테마만 맞추면 'KODEX 미국반도체'의 대조군에
    'HANARO Fn K-반도체'(한국)가 붙는다. 두 시장은 환율·현지 실적에 다르게 반응해
    DiD의 평행추세 가정이 깨지고, 마케팅과 무관한 차이가 효과로 오독된다."""
    if universe is not None and len(universe):
        row = universe[universe["종목명"] == treat_name]
        if len(row):
            theme = row.iloc[0]["테마"]
            market = row.iloc[0].get("기초시장", "")
            # '기타'는 동질 집단이 아니라 '분류 실패한 것들 모음'이다.
            # 자동 매핑하면 로보틱스 ETF에 회사채·ESG·수소경제가 대조군으로 붙는다(실측).
            # 틀린 대조군으로 그럴듯한 DiD를 내놓느니 비워두고 직접 지정하게 한다.
            if theme == "기타":
                return []
            peers = universe[(universe["테마"] == theme)
                             & (universe["기초시장"] == market)
                             & (universe["운용사"] != "KODEX")]
            names = sorted(peers["종목명"].unique())
            # 인버스·레버리지는 기초자산이 같아도 방향·배수가 달라 평행추세가 성립하지 않는다
            # (예: '2차전지TOP10인버스'는 테마가 오를 때 내린다)
            if not INVERSE_LEV_PAT.search(treat_name):
                names = [n for n in names if not INVERSE_LEV_PAT.search(n)]
            return names
        return []
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


# 평행추세 판정 기준 — 개입 이전 구간에서 처치군과 얼마나 같이 움직였나
PARALLEL_MIN_WEEKS = 4    # 이보다 짧으면 검증 자체가 불가
PARALLEL_GOOD = 0.30      # Δ상관 이 이상이면 양호


def control_diagnostics(df: pd.DataFrame, treat: str, candidates: list[str],
                        event_week: str) -> pd.DataFrame:
    """후보별 평행추세 적합도 — DiD가 성립하는지 실제로 확인한다.

    DiD의 가정은 '마케팅이 없었다면 처치군도 대조군과 같은 방향으로 움직였을 것'이다.
    테마·기초시장이 같다는 건 그럴듯한 이유일 뿐 검증이 아니다. 개입 이전 구간에서
    주간 변화량(Δ)이 실제로 동행했는지를 본다.

    반환 컬럼: 종목명·공통주·상관·평행오차·순자산·판정
      상관   = 개입 전 Δ강도의 상관계수 (음수면 반대로 움직임 = 부적합)
      평행오차 = |Δ처치 − Δ대조|의 평균. 작을수록 나란히 움직였다는 뜻
    """
    d = _smoothed_intensity(df)
    weeks = list(dict.fromkeys(d["주차"]))
    if event_week not in weeks:
        return pd.DataFrame()
    pre = weeks[: weeks.index(event_week)]
    aum = df.drop_duplicates("종목명").set_index("종목명")["순자산"]

    def series(n):
        return d[d["종목명"] == n].set_index("주차")["강도"].reindex(weeks)

    t = series(treat).loc[pre].astype(float)
    rows = []
    for c in candidates:
        b = series(c).loc[pre].astype(float)
        m = t.notna() & b.notna()
        n_pre = int(m.sum())
        corr = np.nan
        err = np.nan
        if n_pre >= 2:
            dt_, dc_ = t[m].diff(), b[m].diff()
            err = float(np.nanmean(np.abs(dt_ - dc_)))
            # 처치군이 개입 전 내내 0이면(신규상장) 분산이 없어 상관을 낼 수 없다
            if t[m].std() > 0 and b[m].std() > 0:
                corr = float(np.corrcoef(t[m], b[m])[0, 1])
        # 검증 불가는 원인이 두 가지다 — 관측이 짧은 것과, 값이 아예 안 움직인 것.
        # 둘을 뭉치면 "7주인데 최소 4주 필요"처럼 앞뒤가 안 맞는 안내가 나간다.
        reason = ""
        if n_pre < PARALLEL_MIN_WEEKS:
            verdict, reason = "검증 불가", f"개입 이전 관측 {n_pre}주 (최소 {PARALLEL_MIN_WEEKS}주 필요)"
        elif np.isnan(corr):
            if n_pre >= 2 and float(t[m].std() or 0) == 0:
                verdict, reason = "검증 불가", "처치군이 개입 이전 내내 순매수 0 (신규 상장) — 변화가 없어 상관 계산 불가"
            elif n_pre >= 2 and float(b[m].std() or 0) == 0:
                verdict, reason = "검증 불가", "대조군 후보가 개입 이전 내내 순매수 0"
            else:
                verdict, reason = "검증 불가", "상관 계산 불가"
        elif corr < 0:
            verdict = "부적합"
        elif corr < PARALLEL_GOOD:
            verdict = "약함"
        else:
            verdict = "양호"
        rows.append({"종목명": c, "공통주": n_pre, "상관": corr,
                     "평행오차": err, "순자산": float(aum.get(c, 0) or 0),
                     "판정": verdict, "사유": reason})
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["판정", "상관"], ascending=[True, False],
                              key=lambda s: s.map({"양호": 0, "약함": 1, "검증 불가": 2,
                                                   "부적합": 3}) if s.name == "판정" else s)
    return out.reset_index(drop=True)


def select_controls(diag: pd.DataFrame, max_n: int = 5) -> list[str]:
    """평행추세가 확인된 후보만 대조군으로 채택.

    '부적합'(반대로 움직인 종목)은 제외한다 — 넣으면 DiD가 부호까지 뒤집힌다.
    검증이 불가능한 구간(신규상장 등)에서는 걸러낼 근거가 없으므로 후보를 그대로
    두되, 화면에 '검증 불가'로 표시해 검증된 것처럼 보이지 않게 한다."""
    if diag is None or not len(diag):
        return []
    ok = diag[diag["판정"].isin(["양호", "약함"])]
    if not len(ok):                       # 검증 가능한 게 없으면 미검증 후보 유지
        ok = diag[diag["판정"] == "검증 불가"]
    return ok["종목명"].head(max_n).tolist()


def did_series(df: pd.DataFrame, treat: str, controls: list[str],
               weights: dict[str, float] | None = None) -> pd.DataFrame:
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
            pairs = [(c, ctrl_df[c].iloc[i] - ctrl_df[c].iloc[lo:i].mean()) for c in controls]
            valid = [(c, v) for c, v in pairs if pd.notna(v)]
            if valid:
                # 단순 평균은 96억 ETF와 1,782억 ETF를 같은 비중으로 다뤄
                # 소형 종목의 노이즈가 그대로 들어온다 → 순자산 가중이 기본
                ws = [max(float((weights or {}).get(c, 1.0)), 0.0) for c, _ in valid]
                tot = sum(ws)
                delta_c = (float(np.average([v for _, v in valid], weights=ws))
                           if tot > 0 else float(np.mean([v for _, v in valid])))
            else:
                delta_c = np.nan
        else:
            delta_c = np.nan
        did = delta_t - delta_c if not math.isnan(delta_c) else np.nan
        rows.append(
            {"주차": wk, "처치강도": treat_s.iloc[i], "Δ처치": delta_t, "Δ대조군": delta_c, "DiD": did}
        )
    return pd.DataFrame(rows)


MIN_BASELINE_ACTIVE = 4   # 개입 이전에 실제 거래가 있었던 최소 주 수


def did_score(series: pd.DataFrame, week: str) -> dict:
    """해당 주차 DiD를 Z-score 표준화 후 Sigmoid로 0~100점 변환."""
    row = series[series["주차"] == week]
    if row.empty:
        return {"available": False}

    # 신규 상장 가드 — 개입 이전 기간에 거래 자체가 없었다면 DiD는 성립하지 않는다.
    # (상장 전 순매수는 0이므로 베이스라인이 0이 되고, 상장 첫 주 유입이
    #  통째로 '효과'로 계산돼 수백 %p 같은 허수가 나온다 — 실측 확인)
    prior = series[series.index < row.index[0]]["처치강도"]
    active = int((prior.fillna(0) != 0).sum())
    if active < MIN_BASELINE_ACTIVE:
        return {
            "available": True, "did": None, "score": None, "z": None,
            "delta_treat": None, "delta_ctrl": None,
            "fallback": f"개입 이전 거래 이력 {active}주 — 신규 상장 등으로 베이스라인이 없어 "
                        f"DiD 측정 불가 (최소 {MIN_BASELINE_ACTIVE}주 필요)",
        }
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
        # 해석용 기준값 — '평소'가 실제로 몇 %p인지 보여주기 위해 함께 반환
        result["base_mean"] = round(float(hist.mean()), 2)
        result["base_std"] = round(float(hist.std()), 2)
        result["n_hist"] = int(len(hist))
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
    {"name": "코스피", "level": "7,475.94", "daily": 0.4, "weekly": 1.8},
    {"name": "코스닥", "level": "831.23", "daily": -0.2, "weekly": -0.6},
    {"name": "S&P 500", "level": "7,537.43", "daily": 0.2, "weekly": 0.9},
    {"name": "나스닥", "level": "26,121.16", "daily": 0.3, "weekly": 1.4},
    {"name": "USD/KRW", "level": "1,522.40", "daily": 0.1, "weekly": 0.3},
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
    # 같은 응답(7일치 종가)에서 일간·주간을 함께 계산 — 추가 호출이 없다
    daily = (closes[0] / closes[1] - 1) * 100   # 전일 대비
    weekly = (closes[0] / closes[5] - 1) * 100  # 최근 5거래일
    return {"name": label, "level": f"{closes[0]:,.2f}",
            "daily": round(daily, 2), "weekly": round(weekly, 2)}


def fetch_weekly_market() -> list[dict]:
    """주요 지수·환율의 전일 대비·주간 등락률. 실패 항목은 폴백."""
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


# 브랜드별 검색어 — 브랜드명만으로는 동음이의어가 섞인다.
# (SOL=솔 음악·솔루션, PLUS=플러스 일반어, TIME=시간, RISE=상승)
_ISSUER_NEWS_QUERY = {
    "KODEX": "KODEX ETF",
    "TIGER": "TIGER ETF 미래에셋",
    "ACE": "ACE ETF 한국투자신탁운용",
    "SOL": "SOL ETF 신한자산운용",
    "HANARO": "HANARO ETF NH아문디",
    "RISE": "RISE ETF KB자산운용",
    "PLUS": "PLUS ETF 한화자산운용",
    "TIMEFOLIO": "타임폴리오 ETF",
}


def _fetch_issuer_news_one(issuer: str, n: int = 3) -> list[dict]:
    """브랜드 하나의 최신 기사 — 구글 뉴스 RSS. 키 불필요."""
    q = _ISSUER_NEWS_QUERY.get(issuer, f"{issuer} ETF")
    r = requests.get(
        f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko",
        headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
    )
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.findall(".//item")[:n]:
        t, l, d = it.find("title"), it.find("link"), it.find("pubDate")
        if t is None or not t.text:
            continue
        # 구글 뉴스 제목은 '기사제목 - 매체명' 형식이라 매체를 분리한다
        title, _, source = (t.text or "").rpartition(" - ")
        out.append({
            "title": (title or t.text).strip(),
            "source": source.strip(),
            "url": l.text if l is not None else "#",
            "date": (d.text or "")[5:16] if d is not None else "",
        })
    return out


ISSUER_NEWS_STATUS: dict[str, str] = {}


def fetch_issuer_news(n_per_issuer: int = 3) -> dict[str, list[dict]]:
    """운용사 8개 브랜드의 최신 뉴스를 병렬 수집.

    예전에는 제목이 data.py에 하드코딩돼 있어(예시 문구) 시간이 지나도 바뀌지
    않았다 — 다른 섹션이 전부 실데이터인데 여기만 데모로 남아 있었다.
    유튜브와 같은 이유로 동시성을 낮춘다(구글 뉴스도 과다 요청 시 429를 준다)."""
    out: dict[str, list[dict]] = {}
    ISSUER_NEWS_STATUS.clear()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_fetch_issuer_news_one, b, n_per_issuer): b for b in ISSUERS}
        for fut, brand in futures.items():
            try:
                out[brand] = fut.result()
            except Exception as e:
                out[brand] = []
                ISSUER_NEWS_STATUS[brand] = f"{type(e).__name__}: {e}"
    return out


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
