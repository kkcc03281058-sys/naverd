# 주소 기반 토지이용계획/공시지가 자동 조회

토지이음(eum.go.kr)에서 로그인 없이 주소만으로 토지이용계획, 지목, 면적, 개별공시지가를
자동으로 조회하는 스크립트입니다.

## 사전 준비 (한 번만)

1. [python.org](https://www.python.org/downloads/)에서 파이썬 설치 (설치 시 "Add python.exe to PATH" 체크 필수)
2. 명령 프롬프트에서:
   ```
   py -m pip install playwright
   py -m playwright install chromium
   ```

## 사용법

이 폴더의 `zoning_report.py` 파일을 PC에 저장한 뒤, 명령 프롬프트에서:

```
py zoning_report.py "능평동488-15"
```

주소를 안 넣고 실행하면 실행 중에 입력하라고 물어봅니다.

## 참고

- 이 사이트는 로그인이 필요 없어서 완전 자동으로 동작합니다.
- 사이트 구조가 바뀌면 파싱이 틀어질 수 있는데, 그럴 땐 출력 맨 아래 "원본 텍스트" 부분을 보고
  어떤 라벨(예: "소재지", "지목")이 사라졌거나 바뀌었는지 확인해서 코드를 다시 맞추면 됩니다.
