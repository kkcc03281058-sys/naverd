# -*- coding: utf-8 -*-
"""
부동산공시가격알리미(realtyprice.kr)에서 공동주택(아파트/연립/다세대) 공시가격을
자동 조회하는 스크립트. 로그인이 필요 없는 사이트라 완전 자동으로 동작합니다.

사용법 (명령 프롬프트에서):
    py apartment_price.py "경기도" "광주시" "능평동" "488" "15" "F" "102"
    (시도, 시군구, 읍면동, 본번, 부번, 동, 호 순서. 동/호는 생략하면 첫 번째 항목 자동 선택)
"""

import re
import sys
from playwright.sync_api import sync_playwright


def fetch_apartment_price(sido: str, sigungu: str, eupmyeondong: str, bun: str, ji: str,
                           dong: str = None, ho: str = None) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.realtyprice.kr/notice/town/searchPastYear.htm")
        page.wait_for_timeout(2000)

        # 이 사이트의 버튼들은 진짜 버튼이 아니라 alt 속성이 붙은 이미지(gif)로
        # 만들어져 있어서 get_by_alt_text로 찾는다 (공백 유무가 있을 수 있어 정규식 사용).
        page.get_by_alt_text(re.compile("지번\\s*검색")).click()
        page.wait_for_timeout(500)

        selects = page.locator("select:visible")
        selects.nth(0).select_option(label=sido)
        page.wait_for_timeout(500)
        selects.nth(1).select_option(label=sigungu)
        page.wait_for_timeout(500)
        selects.nth(2).select_option(label=eupmyeondong)
        page.wait_for_timeout(500)

        # "지번 입력" 텍스트가 여러 군데 있어서 혼동됐음. 실제로는
        # name="rdoCondi" value="1"인 라디오 버튼이 진짜 대상.
        page.locator('input[name="rdoCondi"][value="1"]').check()
        page.wait_for_timeout(500)

        text_inputs = page.locator("input[type=text]:visible")
        text_inputs.nth(0).fill(bun)
        text_inputs.nth(1).fill(ji)

        # 이 버튼은 alt 속성이 아예 없고 onclick="searchAptName(1);"으로만
        # 구분되므로 그걸로 지정
        page.locator('input[onclick="searchAptName(1);"]').click()
        page.wait_for_timeout(1500)

        # 단지명 -> 해당 지번에는 보통 단지가 하나뿐이라 첫 번째 항목 선택
        page.locator("select:visible").nth(3).select_option(index=0)
        page.wait_for_timeout(500)

        # 동 -> 지정한 동이 있으면 그걸로, 없으면 첫 번째 항목
        dong_select = page.locator("select:visible").nth(4)
        if dong:
            dong_select.select_option(label=dong)
        else:
            dong_select.select_option(index=0)
        page.wait_for_timeout(500)

        # 호 -> 지정한 호가 있으면 그걸로, 없으면 첫 번째 항목
        ho_select = page.locator("select:visible").nth(5)
        if ho:
            ho_select.select_option(label=ho)
        else:
            ho_select.select_option(index=0)

        page.wait_for_timeout(500)
        page.screenshot(path="debug2.png", full_page=True)

        # 같은 onclick을 가진 버튼이 2개 있어 alt="열람하기"로 정확히 구분
        page.locator('input[alt="열람하기"]').click()
        page.wait_for_timeout(1500)

        # 결과 표에서 가장 최근(맨 위) 행의 "산정기초자료" 클릭 -> 새 창(팝업)
        with page.expect_popup() as popup_info:
            page.get_by_text("산정기초자료").first.click()
        popup = popup_info.value
        popup.wait_for_load_state()

        popup_text = popup.locator("body").inner_text()
        browser.close()

    return popup_text


def parse_apartment_popup(text: str) -> dict:
    def extract(label, stop_labels):
        stop_pattern = "|".join(re.escape(s) for s in stop_labels)
        pattern = re.escape(label) + r"\s*(.*?)\s*(?=" + stop_pattern + r"|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else "(찾을 수 없음)"

    return {
        "소재지": extract("소재지", ["단지명"]),
        "단지명": extract("단지명", ["동/호"]),
        "동/호": extract("동/호", ["전년가격"]),
        "전년가격": extract("전년가격(원)", ["금년가격"]),
        "금년가격": extract("금년가격(원)", ["위치도"]),
        "용도": extract("용도", ["용도지역"]),
        "용도지역": extract("용도지역", ["건물구조"]),
        "건물구조": extract("건물구조", ["사용승인연도"]),
        "사용승인연도": extract("사용승인연도", ["동수"]),
        "세대수": extract("세대수", ["건폐율"]),
    }


if __name__ == "__main__":
    dong = None
    ho = None
    if len(sys.argv) >= 6:
        sido, sigungu, eupmyeondong, bun, ji = sys.argv[1:6]
        if len(sys.argv) >= 7:
            dong = sys.argv[6]
        if len(sys.argv) >= 8:
            ho = sys.argv[7]
    else:
        sido = input("시/도 (예: 경기도): ")
        sigungu = input("시/군/구 (예: 광주시): ")
        eupmyeondong = input("읍/면/동 (예: 능평동): ")
        bun = input("본번 (예: 488): ")
        ji = input("부번 (예: 15): ")
        dong = input("동 (모르면 그냥 Enter): ") or None
        ho = input("호 (모르면 그냥 Enter): ") or None

    print("조회 중...\n")
    raw_text = fetch_apartment_price(sido, sigungu, eupmyeondong, bun, ji, dong, ho)
    info = parse_apartment_popup(raw_text)

    print("===== 공동주택 공시가격 조회 결과 =====")
    for key, value in info.items():
        print(f"{key}: {value}")
