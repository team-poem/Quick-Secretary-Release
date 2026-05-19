---
skill: _output_contract
type: protocol
priority: 985
always_load: true
description: 출력 포맷 계약. 미준수 사례 3 (인코딩 깨짐, 엉뚱한 포맷) 차단.
---

# 출력 포맷 계약

## 결과 파일 명명 규칙

| 입력 | 결과 파일명 |
|---|---|
| `data.xlsx` (단순 처리) | `data_결과.xlsx` |
| `data.xlsx` (수정) | `data_수정본.xlsx` |
| `보고서.hwpx` | `보고서_수정본.hwpx` |
| 분할 산출물 | `data_split/Sheet1.xlsx`, `data_split/Sheet2.xlsx` ... |
| 취합 산출물 | `merged.xlsx` (사용자 지정 가능) |
| 변환 (HWP→MD) | `보고서.md` (확장자만 변경) |

**금지**:
- 원본 덮어쓰기 (사용자 명시 요청 시만 예외)
- 영문 임의 명명 (`output.xlsx`, `result.xlsx` 등 — 어떤 작업의 결과인지 모름)
- 작업 폴더 외부 저장
- `.tmp` / `.bak` 접미사 (임시 파일은 `%TEMP%/_ddukddak_*`)

## HWP 결과 자동 HWPX 변환 안내

`core.hwp_*` 모듈이 편집/병합/섹션 교체 결과를 **HWPX 로 자동 저장**한다 (rhwp 가 HWP 바이너리 저장 미완). 사용자가 `.hwp` 확장자를 지정해도 결과는 `.hwpx` 로 출력될 수 있음.

**보고 메시지**:
```
✅ 처리 완료
- 입력: 보고서.hwp
- 결과: 보고서_수정본.hwpx (한컴/뷰어 정상 열림)
- 변환된 단락 수: 12
```

확장자 차이를 사용자가 의아해할 수 있으니 한 줄로 안내.

## 인코딩 — 한글 안 깨지게

### 임시 스크립트 첫 두 줄 (필수)

```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
```

### 한글 경로

- NFC 정규화 권장 (Windows 기본)
- 외부에서 받은 파일이 NFD (mac/iCloud 동기화 등) 일 수 있음 → `os.listdir()` 결과의 정확한 이름 사용
- `Path(r'한글경로')` 형태가 안전

### 결과 파일 인코딩

| 포맷 | 도구 | 인코딩 |
|---|---|---|
| .xlsx | openpyxl | (자동) |
| .xls | xlrd 읽기, openpyxl 쓰기 (xls 쓰기 불가) | (자동) |
| .hwp / .hwpx | rhwp / kordoc | (자동) |
| .md | open(..., encoding='utf-8') | UTF-8 |
| .csv | **금지 (인코딩 문제)** — 부득이 시 BOM + utf-8-sig | UTF-8-sig |
| .txt | encoding='utf-8' | UTF-8 |

CSV 폴백 금지. 사용자가 명시 요청 시만 BOM 포함 utf-8-sig.

## 사용자에 표 데이터 보여주기 — 마크다운 표 강제

엑셀 / HWP 표 / PDF 표 데이터를 사용자에게 보여줄 때:

### 형식

```
| 컬럼1 | 컬럼2 | 컬럼3 |
| --- | --- | --- |
| 값1 | 값2 | 값3 |
| 값4 | 값5 | 값6 |
```

UI 가 자동으로 HTML `<table>` 로 렌더한다. JSON / Python dict / raw 출력 금지.

### 큰 데이터 처리

- **20행 이내**: 전체 표시
- **20행 초과**: 첫 10-20행 + "전체 N행 중 일부" 명시
- 사용자가 "더 보여줘" 요청 시 다음 chunk

예시:
```
| 학번 | 이름 | 학과 |
| --- | --- | --- |
| 2024001 | 홍길동 | AI공학과 |
| 2024002 | 김영희 | 컴퓨터공학과 |
... (전체 142행 중 첫 10행)

전체 보시려면 "다 보여줘" 하시면 됩니다.
```

### 셀에 줄바꿈 / 파이프 문자

마크다운 표는 셀 내 `|` 와 줄바꿈을 못 다룸. 다음 처리:
- `|` → `\|` 이스케이프
- `\n` → `<br>` 또는 공백
- 너무 긴 셀 (>50자) → 첫 30자 + "..."

### 너무 많은 컬럼 (>8개)

마크다운 표가 가로 스크롤 발생 → 사용자 가독성 ↓. 다음 중 선택:
- 핵심 5-6 컬럼만 표시 + "전체 컬럼 보시려면 'N번째 컬럼' 식으로 요청"
- 행/열 swap 후 표시 (적은 행에 다중 컬럼 통합)

## 결과 보고 메시지 형식

작업 완료 시:

```
✅ <한 줄 요약>

- <변경 항목 1>
- <변경 항목 2>
- <변경 항목 3>

다음 권장: <한 문장>
```

### 좋은 예

```
✅ BITS 엑셀에 PDF 4개 매칭 정보 입력

- 매칭된 교과목: 37개 (1학기 20, 2학기 16, 하계 1)
- 입력 컬럼: 원격수업 유무 (Col 25), 공유대학명 (Col 26)
- 결과 파일: BITS_결과.xlsx (작업 폴더)

다음 권장: 결과 파일 열어 확인 후 이상 있으면 알려주세요.
```

### 나쁜 예 (금지)

```
❌ 작업이 완료되었습니다.

(아무 정보 없음 — 사용자가 뭘 했는지 모름)
```

```
❌ Successfully processed the file.
- Total rows: 142
- Updated columns: 25, 26
- Output: BITS_결과.xlsx

(영어 사용 + 결과 의미 없음)
```

## 카드 출력 — verdict frontmatter

작업 stop / 검증 완료 시 frontmatter 출력. 호스트가 카드로 렌더.

### verdict (max_attempts 위반)

```yaml
---
verdict: stop
category: external_blocker | system_limit | unclear_intent
recoverable_by_user: true | false
attempted:
  - step: parse_xlsx
    result: ok
    detail: "원본 100행, 5시트"
  - step: parse_pdf
    result: ok
    detail: "PDF 4개에서 130개 교과목 추출"
  - step: match
    result: failed
    detail: "정규화 후에도 매칭률 33% — PDF 헤더 자동 인식 실패"
last_error: "match step 매칭률 < 50% 임계 미만"
user_action: |
  PDF 의 1학기와 2학기 파일이 컬럼 순서가 다릅니다.
  헤더가 명확한 PDF 로 재첨부하시거나,
  매칭 가능한 12행만 결과 받으시려면 [부분 진행] 을 눌러 주세요.
---
```

### verify_report (산출물 검증 결과)

```yaml
---
report: verify
skill: xlsx_pdf_match
checks:
  - name: 행수_보존
    expected: 142
    actual: 142
    pass: true
  - name: 시트수_보존
    expected: 3
    actual: 3
    pass: true
  - name: 매칭률
    expected: ">= 0.5"
    actual: 1.0
    pass: true
verdict: pass
output_file: BITS_결과.xlsx
---
```

호스트가 ✅/❌ 표시 + 마크다운 표 카드로 렌더.

## 오류 응답 — 한국어 한두 문장

영문 traceback 그대로 노출 금지.

| 나쁜 (금지) | 좋은 |
|---|---|
| `Traceback (most recent call last): File "...", line 42` | "이 파일은 한글 v3 (구버전) 라 처리 불가합니다. 한글 프로그램에서 'HWPX 다른 이름 저장' 후 재시도해 주세요." |
| `KeyError: '학과명'` | "엑셀에 '학과명' 컬럼이 없습니다. 헤더를 확인해 주시거나 다른 컬럼명을 알려주세요." |
| `UnicodeDecodeError: 'cp949' ...` | "파일 인코딩 문제로 읽지 못했습니다. 다른 이름으로 저장하면서 인코딩을 UTF-8 로 바꿔주세요." |

## 중복 출력 금지

부분 chunk 가 점진 누적되며 같은 의미 문장을 두 번 쓰지 말 것. 최종 의미 있는 텍스트 한 번만.

**나쁜 예 (legacy transcript 에서 자주 발견)**:
```
(11초) 작업을 시작하겠습니다. 먼저 Excel 파일 구조를 파악하고 PDF들...
(13초) Excel 파일 구조를 먼저 파악하겠습니다.
(14초) Excel 파일 구조를 먼저 파악하겠습니다.
```

**좋은 예**: 한 번만 출력하고 도구 호출로 진행.

## 진행 메시지 (도구 호출 직전)

복잡 다단계 작업 시 사용자가 멍하게 기다리지 않게:

```
1단계: 엑셀 구조 파악 중...
[parse_xlsx 호출]

2단계: PDF 4개에서 교과목 정보 추출 중...
[parse_pdf 호출]

3단계: 교과목명 정규화 후 매칭 중...
[match 호출]
```

각 단계 시작 시 한 줄. 같은 단계에서 반복 출력 금지.
