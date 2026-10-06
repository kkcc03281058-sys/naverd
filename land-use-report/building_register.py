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


def fetch_building_register(address: str, dong: str = None, ho: str = None) -> str:
    with sync_playwright() as p:
        # launch_persistent_context를 쓰면 로그인 상태(쿠키)가 eais_login_profile
        # 폴더에 저장되어서, 세움터 세션이 살아있는 동안(보통 1시간)은
        # 다시 실행해도 매번 로그인할 필요가 없다. (이 폴더는 지우지 말 것)
        context = p.chromium.launch_persistent_context(
            "eais_login_profile", headless=False
        )
        page = context.new_page()
        page.goto("https://cloud.eais.go.kr")

        input("\n이미 로그인되어 있으면 그냥 Enter, 아니면 로그인을 완료하신 후 Enter를 눌러주세요...")

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

        # 화면에 보이는 "건축물 소재지를 입력하세요." 글자는 실제 입력창이 아니라
        # 별도의 안내문구(span.multiselect__placeholder)이고, 진짜 입력창은 그
        # 뒤에 숨어있다가 클릭해야 활성화된다. 그래서 안내문구를 클릭해 활성화한
        # 뒤 키보드로 바로 타이핑한다.
        page.get_by_text("건축물 소재지를 입력하세요.", exact=True).click()
        page.wait_for_timeout(500)
        page.keyboard.type(address)
        page.wait_for_timeout(1500)

        # 자동완성 목록은 기본으로 맨 위(지번주소) 항목에 "선택" 버튼이 바로 보인다
        page.get_by_role("button", name="선택", exact=True).first.click()
        page.wait_for_timeout(1500)

        # 동이 여러 개인 건물이면 "동명" 선택 목록이 한 번 더 뜬다
        if page.locator(":text('동명')").count() > 0:
            if dong:
                page.get_by_text(dong, exact=False).first.click()
                page.wait_for_timeout(300)
            page.get_by_role("button", name="선택", exact=True).first.click()
            page.wait_for_timeout(1500)

        # 호가 여러 개인 건물(공동주택/다세대 등)이면 "호명" 선택 목록이 한 번 더 뜬다
        if page.locator(":text('호명')").count() > 0:
            if ho:
                page.get_by_text(ho, exact=False).first.click()
                page.wait_for_timeout(300)
            page.get_by_role("button", name="선택", exact=True).first.click()
            page.wait_for_timeout(1500)

        # 주소/동/호 태그를 다 고른 뒤에는 돋보기(검색) 버튼을 직접 눌러야
        # 실제 조회결과가 나온다 (버튼의 접근성 이름은 "검색")
        page.get_by_role("button", name="검색", exact=True).first.click()
        page.wait_for_timeout(1500)

        # 결과 목록은 일반 표가 아니라 AG-Grid라서, 체크박스 칸(col-id="0")을
        # 직접 클릭해야 선택된다
        page.locator('div.ag-cell[col-id="0"]').first.click()
        page.wait_for_timeout(500)

        page.get_by_text("신청할 민원 담기", exact=False).click()
        page.wait_for_timeout(1000)

        page.get_by_text("건축물대장 발급 신청", exact=False).click()
        page.wait_for_timeout(1500)

        # "건축물대장을 열람합니다." 선택 (기본값인 발급 대신 열람으로 변경)
        page.get_by_text("건축물대장을 열람합니다.", exact=True).click()
        page.wait_for_timeout(500)

        page.get_by_text("신청하기", exact=True).click()
        page.wait_for_timeout(2000)

        # 신청내역 목록에서 "표제부" 행의 "열람" 버튼 클릭 -> 새 탭(팝업)으로 보고서 표시
        # (이 사이트는 결과 목록이 일반 표가 아닐 수 있어 role="row"로 찾는다)
        with page.expect_popup() as popup_info:
            page.get_by_role("row", name=re.compile("표제부")).first.get_by_text("열람", exact=True).click()
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

        context.close()

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
    ho = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"'{address}' 조회 중...\n", flush=True)
    raw_text = fetch_building_register(address, dong, ho)
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
