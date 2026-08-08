#!/usr/bin/env bash
# 주간 데이터 갱신 — 4개 배치 실행 → data/*.json 변경분만 커밋·푸시
#
# GitHub Actions와 macOS launchd가 이 스크립트 하나를 공유한다.
# 두 곳에 로직을 복사하면 반드시 한쪽만 고쳐지고 갈라진다.
#
# 필요: KRX_API_KEY (openapi.krx.co.kr 인증키) — weekly_batch·etf_batch
#       channel_batch는 키 없이 동작한다.
#
# 사용:
#   scripts/run_weekly.sh          # 실행 + 커밋 + 푸시
#   NO_PUSH=1 scripts/run_weekly.sh  # 커밋까지만 (푸시 안 함)

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# launchd는 PATH가 최소('/usr/bin:/bin:...')라 Homebrew·Framework 파이썬이 빠진다.
# PATH에 기대지 말고 배치에 필요한 패키지가 실제로 있는 인터프리터를 고른다.
resolve_python() {
    local cands=("${PYTHON_BIN:-}" python3
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3
        /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3)
    for c in "${cands[@]}"; do
        [ -n "$c" ] || continue
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pandas, requests' >/dev/null 2>&1; then
            echo "$c"; return 0
        fi
    done
    return 1
}
PY="$(resolve_python)" || {
    echo "✗ pandas·requests가 설치된 python3을 찾지 못했습니다." >&2
    exit 1
}
log() { printf '[%s] %s\n' "$(date '+%m-%d %H:%M:%S')" "$*"; }

if [ -z "${KRX_API_KEY:-}" ]; then
    log "✗ KRX_API_KEY 환경변수가 없습니다 — KRX 배치를 돌릴 수 없습니다."
    exit 1
fi

log "주간 배치 시작 (python: $PY)"
failed=()
for s in weekly_batch etf_batch channel_batch sector_universe; do
    log "▶ $s"
    # 로그인 시각·만료 시각 줄에는 계정 흔적이 남아 로그에서 지운다.
    # 파이프를 쓰면 종료코드가 grep 것이 되므로 PIPESTATUS로 파이썬 결과를 본다.
    "$PY" "scripts/$s.py" 2>&1 | grep -v "로그인 시간\|만료 시간\|로그인 ID"
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        log "  ✗ $s 실패"
        failed+=("$s")
    else
        log "  ✓ $s"
    fi
done

# 산출물이 실제로 최신 주를 담았는지 확인 — 배치가 조용히 옛 주를 남기는 것을 잡는다.
# signal_board만 보면 부족하다. 화면의 '분석 주차'는 etf_flows가 결정하므로
# weekly_batch만 성공하고 etf_batch가 실패하면 날짜가 어긋난 채 갱신된 것처럼 보인다
# (실측 2026-08-07: KIS 타임아웃으로 etf_batch가 죽어 보드가 7월 5주에 멈춤).
if ! "$PY" - <<'PYEOF'
import json, sys
from datetime import date, timedelta
from pathlib import Path

today = date.today()
last_fri = today - timedelta(days=(today.weekday() - 4) % 7)
if today.weekday() < 4:
    last_fri = today - timedelta(days=today.weekday() + 3)

stale = []
sb = Path("data/signal_board.json")
if sb.exists():
    board = json.loads(sb.read_text())
    got = (board.get("주간구간") or "").split("~")[-1].strip()
    print(f"  {'✓' if got == last_fri.isoformat() else '!'} signal_board 종료일 "
          f"{got or '없음'} (기대 {last_fri})")
    if got != last_fri.isoformat():
        stale.append("signal_board")
    miss = [r["섹터"] for r in board.get("board", [])
            if r.get("군") != "해외" and not r.get("구성종목수")]
    if miss:
        print(f"  ! 수급 미수집 {len(miss)}개: {', '.join(miss)}")
else:
    stale.append("signal_board(없음)")

ef = Path("data/etf_flows.json")
if ef.exists():
    weeks = json.loads(ef.read_text()).get("weeks") or []
    got_w = weeks[-1] if weeks else ""
    want_w = f"{last_fri.month}월 {(last_fri.day - 1) // 7 + 1}주"
    print(f"  {'✓' if got_w == want_w else '!'} etf_flows 마지막 주차 "
          f"{got_w or '없음'} (기대 {want_w})")
    if got_w != want_w:
        stale.append("etf_flows")
else:
    stale.append("etf_flows(없음)")

if stale:
    print(f"  ✗ 최신 주가 아닙니다: {', '.join(stale)}")
    sys.exit(1)
PYEOF
then
    failed+=("날짜검증")
fi

if ! git diff --quiet -- data/ || [ -n "$(git status --porcelain -- data/)" ]; then
    git add data/
    git -c user.name="kodex-batch" \
        -c user.email="batch@users.noreply.github.com" \
        commit -q -m "데이터: 주간 배치 자동 갱신 ($(date '+%Y-%m-%d'))${failed:+ — 실패: ${failed[*]}}"
    log "✓ 커밋 완료"
    if [ -z "${NO_PUSH:-}" ]; then
        if git push -q; then
            log "✓ 푸시 완료 — Streamlit이 자동 재배포합니다"
        else
            log "✗ 푸시 실패 (인증 확인 필요)"
            exit 1
        fi
    fi
else
    log "· 변경된 데이터 없음 — 커밋 생략"
fi

if [ ${#failed[@]} -gt 0 ]; then
    log "✗ 실패한 배치: ${failed[*]}"
    exit 1
fi
log "주간 배치 완료"
