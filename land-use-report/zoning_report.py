# -*- coding: utf-8 -*-
"""
토지이음(eum.go.kr)에서 주소로 토지이용계획/공시지가를 자동 조회하는 스크립트.

사용법 (명령 프롬프트에서):
    py zoning_report.py "능평동488-15"

로그인이 필요 없는 사이트라 완전 자동으로 동작합니다.
"""

import re
import sys
from playwright.sync_api import sync_playwright


def fetch_land_use(address: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.eum.go.kr")

        search_box = page.get_by_role("textbox", name="주소검색", exact=True)
        search_box.click()
        search_box.fill(address)
        page.wait_for_timeout(1500)  # 자동완성 목록이 뜰 때까지 대기
        search_box.press("ArrowDown")
        search_box.press("Enter")

        page.wait_for_url(re.compile("luLandDet"), timeout=15000)
        page.wait_for_timeout(1000)

        full_text = page.locator("body").inner_text()
        browser.close()

    return full_text


def parse_land_use_text(raw_text: str) -> dict:
    # 화면 제목 줄("토지이용계획 - 소재지, 지목, 면적 및 개별공시지가")에도
    # 같은 단어들이 나와서 혼동되므로, 그 줄을 건너뛰고 실제 값이 나오는
    # 지점부터 파싱한다.
    anchor = "및 개별공시지가"
    idx = raw_text.find(anchor)
    basic_text = raw_text[idx + len(anchor):] if idx != -1 else raw_text

    def extract(source, label, stop_labels):
        stop_pattern = "|".join(re.escape(s) for s in stop_labels)
        pattern = re.escape(label) + r"\s*(.*?)\s*(?=" + stop_pattern + r"|$)"
        m = re.search(pattern, source, re.DOTALL)
        return m.group(1).strip() if m else "(찾을 수 없음)"

    result = {
        "소재지": extract(basic_text, "소재지", ["지목"]),
        "지목": extract(basic_text, "지목", ["면적"]),
        "면적": extract(basic_text, "면적", ["개별공시지가"]),
        "개별공시지가": extract(basic_text, "개별공시지가", ["토지이용계획"]),
    }

    # "지역지구등 지정여부"라는 라벨이 제목 줄과 실제 데이터에 두 번 나오므로
    # 두 번째로 나오는 지점부터를 실제 값으로 본다.
    label = "지역지구등 지정여부"
    first_idx = raw_text.find(label)
    second_idx = raw_text.find(label, first_idx + 1) if first_idx != -1 else -1

    if second_idx != -1:
        zoning_section = raw_text[second_idx + len(label):]
        end_idx = zoning_section.find("토지이용계획 - 확인도면")
        if end_idx != -1:
            zoning_section = zoning_section[:end_idx]
        result["지역지구등"] = zoning_section.strip()
    else:
        result["지역지구등"] = "(찾을 수 없음)"

    return result


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else input("주소를 입력하세요: ")
    print(f"'{address}' 조회 중...\n")

    raw_text = fetch_land_use(address)
    info = parse_land_use_text(raw_text)

    print("===== 토지이용계획 조회 결과 =====")
    for key, value in info.items():
        print(f"{key}: {value}")
