# -*- coding: utf-8 -*-
"""
세움터(cloud.eais.go.kr)에서 건축물대장(표제부)을 조회하는 스크립트.

이 사이트는 로그인이 필요해서 완전 자동화가 안 되고,
"로그인은 사람이 직접, 그 다음 검색/추출은 자동"으로 동작합니다.

사용법 (명령 프롬프트에서):
    py building_register.py "경기도 광주시 능평동 488-15"
"""

import re
import sys
import traceback
from playwright.sync_api import sync_playwright


def fetch_building_register(address: str, dong: str = None) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://cloud.eais.go.kr")

        input("\n브라우저 창에서 로그인을 완료하신 후, 여기로 돌아와서 Enter를 눌러주세요...")

        # 주소를 직접 입력(goto)하면 로그인 직후의 내부 리다이렉트와 충돌이 나서,
        # 실제 사람이 하듯 "민원서비스" 메뉴를 통해 들어간다
        menu_link = page.get_by_role("link", name="민원서비스")
        menu_link.hover()
        page.wait_for_timeout(800)
        menu_link.click()
        page.wait_for_timeout(1000)
        page.get_by_role("link", name="건축물대장발급", exact=True).click()
        page.wait_for_url(re.compile("BCIAAA02L01"), timeout=15000)
        page.wait_for_timeout(1500)

        search_box = page.locator('input[placeholder="건축물 소재지를 입력하세요."]:visible').first
        search_box.click()
        search_box.fill(address)
        page.wait_for_timeout(1500)

        # 자동완성 목록에서 "지번주소"로 표시된 항목의 "선택" 버튼 클릭
        page.locator("li:has-text('지번주소')").first.get_by_text("선택", exact=True).click()
        page.wait_for_timeout(1500)

        # 동이 여러 개인 건물이면 "동명" 선택 목록이 한 번 더 뜬다
        dong_list = page.locator("li:has-text('동명')")
        if dong_list.count() > 0:
            if dong:
                page.locator(f"li:has-text('{dong}')").first.get_by_text("선택", exact=True).click()
            else:
                dong_list.first.get_by_text("선택", exact=True).click()
            page.wait_for_timeout(1500)

        # 결과 행의 체크박스가 비어있으면 체크 (보통은 자동으로 체크되어 있음)
        checkbox = page.locator("table tbody tr").first.locator("input[type=checkbox]")
        if checkbox.count() > 0 and not checkbox.is_checked():
            checkbox.check()
        page.wait_for_timeout(500)

        page.get_by_text("신청할 민원 담기", exact=False).click()
        page.wait_for_timeout(1000)

        page.get_by_text("건축물대장 발급 신청", exact=False).click()
        page.wait_for_timeout(1500)

        # 발급/열람 선택은 기본값(발급) 그대로 두고 바로 신청
        page.get_by_text("신청하기", exact=True).click()
        page.wait_for_timeout(2000)

        # 신청내역 목록에서 "표제부" 행의 "열람" 버튼 클릭 -> 새 탭(팝업)으로 보고서 표시
        with page.expect_popup() as popup_info:
            page.locator("tr:has-text('표제부')").first.get_by_text("열람", exact=True).click()
        popup = popup_info.value
        popup.wait_for_load_state()
        popup.wait_for_timeout(1000)

        page1_text = popup.locator("body").inner_text()

        # 2페이지(사용승인일 등이 있는 페이지)로 이동해서 마저 가져오기
        next_btn = popup.locator("#next, button[title*='다음'], [aria-label*='다음']")
        page2_text = ""
        if next_btn.count() > 0:
            next_btn.first.click()
            popup.wait_for_timeout(1000)
            page2_text = popup.locator("body").inner_text()

        browser.close()

    return page1_text + "\n" + page2_text


def parse_building_register(text: str) -> dict:
    def extract(label, stop_labels):
        stop_pattern = "|".join(re.escape(s) for s in stop_labels)
        pattern = re.escape(label) + r"\s*(.*?)\s*(?=" + stop_pattern + r"|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else "(찾을 수 없음)"

    return {
        "대지위치": extract("대지위치", ["지번"]),
        "도로명주소": extract("도로명주소", ["대지면적", "지번 관련"]),
        "대지면적": extract("대지면적", ["연면적"]),
        "연면적": extract("연면적", ["지역", "용적률산정용"]),
        "건축면적": extract("건축면적", ["용적률산정용"]),
        "주구조": extract("주구조", ["주용도"]),
        "주용도": extract("주용도", ["층수"]),
        "층수": extract("층수", ["건폐율"]),
        "건폐율": extract("건폐율", ["용적률"]),
        "용적률": extract("용적률", ["높이"]),
        "허가일": extract("허가일", ["착공일"]),
        "착공일": extract("착공일", ["사용승인일"]),
        "사용승인일": extract("사용승인일", ["$"]),
    }


def main():
    address = sys.argv[1] if len(sys.argv) > 1 else input("주소를 입력하세요 (예: 경기도 광주시 능평동 488-15): ")
    dong = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"'{address}' 조회 중...\n", flush=True)
    raw_text = fetch_building_register(address, dong)
    info = parse_building_register(raw_text)

    print("===== 건축물대장(표제부) 조회 결과 =====")
    for key, value in info.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n===== 에러가 발생했습니다 (아래 내용을 캡처해서 보내주세요) =====")
        traceback.print_exc()
    input("\n(아무 키나 눌러서 창을 닫으세요)")
