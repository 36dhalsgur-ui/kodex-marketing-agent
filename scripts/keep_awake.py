"""Streamlit 앱을 재우지 않기 위한 접속 스크립트 (GitHub Actions 전용).

Streamlit Community Cloud는 트래픽이 12시간 없으면 앱을 재운다. 그런데 이때의
'트래픽'은 HTML 요청이 아니라 실제 세션(WebSocket)이다. curl로 아무리 두드려도
컨테이너 입장에서는 아무도 안 온 것과 같다 — 실측 2026-09-05:

  워크플로 3회 모두 HTTP 200(9,426바이트) · 마지막 접속 4.6시간 뒤에도 잠들어 있었다

게다가 잠든 앱도 깨어 있는 앱과 똑같은 껍데기를 돌려준다. 'Zzzz / Yes, get this
app back up!'은 그 안에서 자바스크립트로 그려지므로, 본문 검사도 브라우저 없이는
통하지 않는다. 그래서 실제 브라우저로 연다.

잠들어 있으면 깨우기 버튼까지 눌러 복구한다 — 다음 방문자가 그 화면을 보지
않는 것이 목적이므로, 감지에서 멈추면 의미가 없다.
"""

from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "").strip()
SLEEP_MARK = "get this app back up"
# 앱이 실제로 떴는지 알려주는 문구 — 탭 이름은 앱을 고쳐도 잘 안 바뀐다
READY_MARKS = ("시장 트렌드", "채널 모니터링", "주간 리포트")
BOOT_WAIT = 420          # 컨테이너 기동 + 실시간 수집. 넉넉히 준다.
POLL = 5


def body_text(page) -> str:
    """최상위와 모든 iframe의 본문을 합쳐서 본다.

    *.streamlit.app은 앱을 iframe에 담아 띄운다 — 최상위 body만 보면 텍스트가
    비어 있어 '기동 실패'로 오판한다(실측: 깨운 뒤 본문 0자).
    잠금 화면은 최상위에 그려지므로 둘 다 필요하다.
    """
    parts = []
    for f in [page] + list(page.frames):
        try:
            parts.append(f.locator("body").inner_text(timeout=3_000))
        except Exception:
            pass
    return "\n".join(parts)


def wait_ready(page, limit: int, bail_on_sleep: bool = True) -> tuple[bool, str]:
    """앱 본문이 뜰 때까지 기다린다. (준비됨, 마지막 본문)

    깨운 뒤에는 bail_on_sleep=False로 부른다 — 최상위에 잠금 화면 문구가 남아
    있어도 앱은 iframe에서 뜨는 중이라, 여기서 나가면 매번 실패로 끝난다.
    """
    end = time.time() + limit
    txt = ""
    while time.time() < end:
        txt = body_text(page)
        if any(m in txt for m in READY_MARKS):
            return True, txt
        if bail_on_sleep and SLEEP_MARK in txt:
            return False, txt          # 잠든 상태는 기다려도 안 바뀐다
        time.sleep(POLL)
    return False, txt


def main() -> int:
    if not URL:
        print("::error::APP_URL 환경변수가 없습니다")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)

        ready, txt = wait_ready(page, 60)
        slept = SLEEP_MARK in txt

        if slept:
            # 감지에서 멈추지 않는다 — 여기서 깨워둬야 다음 방문자가 안 본다
            print("::warning::앱이 잠들어 있었다 — 깨운다. 실행 간격을 더 좁혀야 한다")
            page.get_by_text("Yes, get this app back up!").click(timeout=30_000)
            ready, txt = wait_ready(page, BOOT_WAIT, bail_on_sleep=False)

        browser.close()

    if ready:
        print("깨어 있음" if not slept else "잠들어 있어 깨움 — 정상 기동 확인")
        return 0
    print("::error::앱 본문을 확인하지 못했다 (기동 실패 또는 화면 구조 변경)")
    print("본문 앞부분:", " ".join(txt.split())[:300])
    return 1


if __name__ == "__main__":
    sys.exit(main())
