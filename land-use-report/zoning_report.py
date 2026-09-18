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


def fetch_land_use(address: str, pdf_path: str) -> str:
    with sync_playwright() as p:
        # PDF 저장 기능은 Playwright에서 headless 모드에서만 지원됨
        browser = p.chromium.launch(headless=True)
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
        page.pdf(path=pdf_path, format="A4", print_background=True)
        browser.close()

    return full_text


def parse_land_use_text(text: str) -> dict:
    def extract(label, stop_labels):
        stop_pattern = "|".join(re.escape(s) for s in stop_labels)
        pattern = re.escape(label) + r"\s*(.*?)\s*(?=" + stop_pattern + r"|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else "(찾을 수 없음)"

    return {
        "소재지": extract("소재지", ["지목"]),
        "지목": extract("지목", ["면적"]),
        "면적": extract("면적", ["개별공시지가"]),
        "개별공시지가": extract("개별공시지가", ["지역지구등"]),
    }


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else input("주소를 입력하세요: ")
    pdf_path = f"{address.replace(' ', '_')}_토지이용계획.pdf"
    print(f"'{address}' 조회 중...\n")

    raw_text = fetch_land_use(address, pdf_path)
    info = parse_land_use_text(raw_text)

    print("===== 토지이용계획 조회 결과 =====")
    for key, value in info.items():
        print(f"{key}: {value}")

    print(f"\nPDF 저장됨: {pdf_path}")

    print("\n===== 원본 텍스트 (파싱이 안 맞으면 이 부분을 참고) =====")
    print(raw_text[:1500])
