---
skill: xlsx_pdf_match
type: task
priority: 50
always_load: false        # trigger 매칭 시에만 Read
trigger:
  - "PDF 에서 ___ 엑셀에 입력"
  - "PDF 정보를 xlsx 에 매칭"
  - "PDF 의 ___ 를 엑셀에 채워"
  - "xlsx 마지막 컬럼에 PDF ___"
  - "엑셀과 PDF 매칭"
enforce: true
plan_required: false      # auto-proceed (Q1 b)
single_script: true       # v_n+1 별파일 금지
max_attempts: 3

preconditions:
  - 입력 .xlsx 파일 1개 + .pdf 파일 N개
  - 모두 작업 폴더 내부
  - .xlsx 에 매칭 키 컬럼 존재 (예: 교과목명, 학번, 부서명)
  - .pdf 에 매칭 키 + 입력 데이터 (표 형태)

steps:
  - id: parse_target
    op: core.excel_reader.get_workbook_info
    record: [sheet_count, row_count, header_row, columns]
  - id: parse_sources
    op: pdfplumber_all_pages_all_tables   # ← v3 교훈: 모든 페이지·모든 테이블
    foreach: input_pdfs
  - id: normalize
    rule: NFC + remove_whitespace          # ← v4 교훈: 학교마다 띄어쓰기 정책 다름
  - id: match
    metric: matched_rows / total_target_rows
  - id: verify
    op: core.verify_xlsx.run
  - id: report
    format: markdown_table

postconditions:
  - 결과 파일명: "<원본>_결과.xlsx"
  - 시트 수 == 원본 시트 수
  - 행 수 == 원본 행 수 (입력 작업이므로 행 추가 없어야)
  - 매칭률 >= 0.3 (낮으면 verdict + 사용자 보고)
  - 입력된 컬럼이 빈 셀 → 새 값으로 변경되어야

forbidden:
  - 원본 덮어쓰기 (반드시 새 파일 _결과.xlsx)
  - %TEMP% 외부에 임시 .py 작성
  - JSON 으로 결과 출력
  - 임시 스크립트 _v\d+ 별파일 (legacy v1~v4 사례 차단)
  - python 인라인 코드 5줄 초과 시 임시 파일로

unsupported:
  - 스캔 PDF (텍스트 추출 0 — OCR 필요)
  - 암호화 PDF
  - 100페이지+ PDF (성능, 부분 처리 안내)
  - PDF 의 표가 이미지로만 된 경우
---

# 절차

## 1. 엑셀 구조 파악

```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from core.excel_reader import get_workbook_info, read_sheet
import json

xlsx_path = Path(r'<엑셀 파일>')
info = get_workbook_info(xlsx_path)
print(json.dumps(info, ensure_ascii=False, default=str))
```

**기록할 정보**:
- sheet_count, sheet_names
- 각 시트의 row_count
- 헤더 행 위치 (첫 줄 아닐 수 있음 — 첫 5행 보고 사람이 알 만한 컬럼명 행)
- 매칭 키 컬럼 (예: "교과목명") 의 인덱스
- 입력 대상 컬럼 (예: "원격수업 유무", "(개설)공유대학명") 의 인덱스

## 2. PDF 추출 — 모든 페이지·모든 테이블 (v3 교훈)

```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import pdfplumber

pdf_paths = [Path(r'<pdf1>'), Path(r'<pdf2>'), ...]
all_rows = {}  # {pdf_name: [{col1: val, col2: val, ...}, ...]}

for pdf_path in pdf_paths:
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()    # ← 모든 테이블 추출
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                header = tbl[0]
                for r in tbl[1:]:
                    rows.append(dict(zip(header, r)))
    all_rows[pdf_path.stem] = rows
    print(f'{pdf_path.name}: {len(rows)}행')
```

**v3 교훈**: pdfplumber 의 `extract_tables()` 는 **페이지마다** 호출해야 모든 테이블 회수. `pdf.extract_tables()` 같은 게 없음. 페이지 루프 필수.

**페이지 분할 표 처리**: 같은 표가 여러 페이지로 분할되면 헤더가 한 번만 나옴. 두 번째 페이지부터는 데이터만. 휴리스틱:
- 두 번째 페이지의 첫 행이 직전 페이지 헤더와 같으면 헤더로 간주, 아니면 데이터로 간주.

## 3. 교과목명 정규화 — NFC + 공백제거 (v4 교훈)

```python
import unicodedata

def normalize_key(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFC', str(s))
    s = ''.join(s.split())  # 모든 공백 제거 (탭/줄바꿈 포함)
    return s.strip()
```

**v4 교훈**: 학교마다 교과목명 띄어쓰기 정책 다름. 부산공유대학은 띄어쓰기 인정, 우리 학교는 띄어쓰기 제거. 매칭 시 둘 다 normalize 후 비교 필수.

NFC 정규화는 mac/iCloud 동기화 파일에서 받은 NFD 한글 (`ㄱㅏ`) 을 (`가`) 로 바꿔줌.

## 4. 매칭

```python
target_keys = {normalize_key(row[key_col]): row_idx for row_idx, row in enumerate(target_rows)}
matched = []
for pdf_name, rows in all_rows.items():
    semester = infer_semester(pdf_name)   # 1학기 / 2학기 / 하계 / 동계
    for row in rows:
        key = normalize_key(row.get('교과목명', ''))
        if key in target_keys:
            target_idx = target_keys[key]
            matched.append({
                'target_idx': target_idx,
                'pdf_data': row,
                'semester': semester,
            })

matched_count = len(matched)
total_count = len(target_rows)
match_rate = matched_count / total_count if total_count else 0
print(f'매칭률: {matched_count}/{total_count} = {match_rate:.1%}')
```

## 5. Verify (매칭률 < 0.3 시 verdict)

```python
if match_rate < 0.3:
    print(f'''---
verdict: stop
category: external_blocker
recoverable_by_user: true
attempted:
  - step: parse_target
    result: ok
    detail: "엑셀 {target_count}행"
  - step: parse_sources
    result: ok
    detail: "PDF {len(pdf_paths)}개에서 {sum(len(r) for r in all_rows.values())}행"
  - step: match
    result: failed
    detail: "정규화 후에도 매칭률 {match_rate:.1%}"
last_error: "match_rate < 0.3"
user_action: |
  매칭률이 낮습니다. 가능한 원인:
  - PDF 의 교과목명 컬럼명이 "강좌명"·"과목명" 등으로 다름 → 헤더 자동 매핑 보강 필요
  - PDF 가 학기별로 형식이 달라 헤더 인식 실패
  - 띄어쓰기 외 문자 차이 (괄호·하이픈 등)
  매칭된 {matched_count}행만 결과 받으시려면 알려주세요.
---''')
    sys.exit(0)
```

## 6. 입력 + 결과 파일 저장

```python
from core.excel_writer import write_cell
from openpyxl import load_workbook

wb = load_workbook(xlsx_path)
ws = wb.active

for m in matched:
    row_no = m['target_idx'] + header_row + 1  # openpyxl 은 1-indexed
    ws.cell(row=row_no, column=col_원격수업유무).value = m['pdf_data'].get('수업유형', '')
    ws.cell(row=row_no, column=col_공유대학명).value = m['pdf_data'].get('강의실', '')

result_path = xlsx_path.with_stem(xlsx_path.stem + '_결과')
wb.save(result_path)
print(f'결과 저장: {result_path}')
```

## 7. 검증 리포트 (verify_report frontmatter)

```python
print(f'''---
report: verify
skill: xlsx_pdf_match
verdict: pass
checks:
  - name: 행수_보존
    expected: {total_count}
    actual: {len(target_rows)}
    pass: true
  - name: 시트수_보존
    expected: {original_sheet_count}
    actual: {len(wb.sheetnames)}
    pass: true
  - name: 매칭률
    expected: ">= 0.3"
    actual: {match_rate:.2f}
    pass: true
output_file: {result_path.name}
---''')
```

## 8. 사용자 보고 메시지

```
✅ <원본>.xlsx 마지막 두 컬럼에 PDF 매칭 정보 입력

- 매칭된 교과목: 37개 (1학기 20, 2학기 16, 하계 1)
- 입력 컬럼: 원격수업 유무, (개설)공유대학명
- 결과 파일: <원본>_결과.xlsx

다음 권장: 결과 파일 열어 확인 후 이상 있으면 알려주세요.
```

## 9. 임시 파일 정리

```bash
del "%TEMP%\_ddukddak_xlsx_pdf_match*.py"
```

---

# 알려진 함정

| 증상 | 원인 | 대응 |
|---|---|---|
| `extract_tables()` 가 빈 리스트 반환 | 페이지에 표가 없음 또는 인식 못함 | `extract_text()` 로 fallback, 텍스트 패턴 매칭으로 행 추출 |
| 매칭률 0% | 키 컬럼명이 PDF/Excel 다름 ("교과목명" vs "강좌명") | 동의어 매핑 dict 추가 |
| `pdfplumber` 미설치 | 사용자 환경 의존성 누락 | `pip install -q pdfplumber` 자동 실행 |
| 페이지 분할 표 헤더 누락 | 표가 페이지 사이로 끊김 | 직전 페이지 헤더 기억해서 적용 |
| 셀 값에 줄바꿈 포함 | PDF 표가 multi-line cell | `str.replace('\\n', ' ').strip()` |
| 매칭은 됐으나 결과 셀이 빈 채로 | 컬럼 인덱스 1-off | header_row 후 데이터 행 1-indexed 명확히 |
| 결과 .xlsx 가 한컴 엑셀 안 열림 | `openpyxl` 의 호환 모드 | `keep_vba=False` 명시, 매크로 .xlsm 은 별도 처리 |

---

# legacy v1→v2→v3→v4 패턴 박제 (재발 방지)

이 skill 은 legacy 뚝딱비서 (~ v0.0.24 이전) 의 BITS 매칭 작업 transcript (24턴/202초/$0.28) 분석에서 도출. 그 transcript 에서 v1→v4 까지 임시 스크립트 별파일 4개 생성:

- v1: 헤더 자동 인식 실패 (실제 헤더가 1행 아님)
- v2: 정규화 추가했으나 매칭률 0% (PDF 테이블 추출 자체가 부분만 됨)
- v3: 페이지/테이블 전체 추출로 변경 (이번 절차의 step 2 박제)
- v4: 헤더 컬럼 인덱스 수정 (이번 절차의 step 1 의 header_row 자동 감지 박제)

**이 skill 의 효과 측정 기준**:
- legacy 24턴 → 8턴 이내 완료
- 별파일 0개 (단일 스크립트)
- 매칭률 100% (BITS 시나리오 기준)
- 첫 시도 성공률 ≥ 80%
