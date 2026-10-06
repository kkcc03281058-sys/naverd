# -*- coding: utf-8 -*-
"""
세움터(cloud.eais.go.kr)에서 건축물대장을 조회하는 스크립트.

이 사이트는 로그인이 필요해서 완전 자동화가 안 되고,
"로그인은 사람이 직접, 그 다음 검색/추출은 자동"으로 동작합니다.

사용법 (명령 프롬프트에서):
    py building_register.py "경기도 광주시 능평동 488-15"
"""

import sys
from playwright.sync_api import sync_playwright


def fetch_building_register(address: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://cloud.eais.go.kr")

        input("\n브라우저 창에서 로그인을 완료하신 후, 여기로 돌아와서 Enter를 눌러주세요...")

        # TODO: 로그인 후 실제 화면 구조를 보고 아래 검색 로직을 채워야 함
        print("(아직 검색 로직이 없습니다 - 로그인 후 화면을 보고 다음 단계를 진행합니다)")
        input("확인했으면 Enter를 눌러 창을 닫습니다...")

        browser.close()

    return ""


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else input("주소를 입력하세요: ")
    fetch_building_register(address)
