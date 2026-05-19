---
skill: _index
type: routing
priority: 999
always_load: true
description: 사용자 메시지 → skill 라우팅 테이블. 매칭 안 되면 unclear_intent 부류로 verdict.
---

# Skill 라우팅

작업 시작 전 사용자 메시지를 보고 매칭되는 skill 을 결정한다. 매칭된 skill 의 .md 를 Read 한 후 절차 시작.

## 매칭 규칙

1. trigger 키워드가 메시지에 있으면 매칭
2. 여러 skill 매칭 시 priority 큰 값 우선
3. 매칭 안 되면 verdict `category: unclear_intent` 로 명확화 질문

## 등록된 skill (Phase 별 점진 추가)

### Phase 1 — 토대 (이미 등록)

| skill | 파일 | 트리거 |
|---|---|---|
| _invariants | _invariants.md | 모든 작업에 자동 적용 |
| _session | _session.md | 모호 참조 ("아까", "방금") 시 자동 |
| _output_contract | _output_contract.md | 결과 출력 시 자동 |
| _loop_guard | _loop_guard.md | 에러 반복 감지 시 자동 |

### Phase 2 — 시드 skill (등록됨)

| skill | 파일 | 트리거 예시 | core 매핑 |
|---|---|---|---|
| xlsx_pdf_match | xlsx_pdf_match.md | "PDF에서 ___ 엑셀에 입력" / "엑셀 마지막 컬럼에 PDF ___" | core.excel_reader, core.excel_writer, pdfplumber |

### Phase 6 — 나머지 skill (예정)

| skill | 파일 | 트리거 예시 | core 매핑 |
|---|---|---|---|
| xlsx_clean | xlsx_clean.md | "빈 행 제거", "공란 정리" | core.excel_clean |
| xlsx_split | xlsx_split.md | "시트별로 나누기", "분할" | core.excel_split |
| xlsx_merge | xlsx_merge.md | "합치기", "취합" | core.excel_merge |
| xlsx_template | xlsx_template.md | "양식 채우기", "템플릿" | core.excel_template |
| hwp_section | hwp_section.md | "섹션 추출", "단원 분리" | core.hwp_section |
| hwp_template | hwp_template.md | "양식 작성", "신청서 채우기" | core.hwp_template |
| hwp_replace | hwp_replace.md | "찾아 바꾸기", "치환" | core.hwp_replace |
| hwp_merge | hwp_merge.md | "한글 파일 합치기", "취합본 만들기" | core.hwp_merge |
| pdf_extract | pdf_extract.md | "PDF 텍스트", "PDF에서 표 추출" | core.pdf_text |

## 매칭 안 될 때 — verdict

```yaml
---
verdict: stop
category: unclear_intent
recoverable_by_user: true
attempted:
  - step: route
    result: failed
    detail: "메시지에서 작업 종류를 특정할 수 없음"
last_error: "no_matching_skill"
user_action: |
  어떤 작업을 원하시는지 한 번 더 알려주세요. 예:
  - "이 엑셀의 빈 행 제거해줘"
  - "이 한글 양식에 학과명 채워줘"
  - "여러 PDF 에서 표 뽑아 엑셀에 합쳐줘"
---
```

## 등록 절차 (개발자용)

새 skill 추가 시:
1. `prompts/skills/<name>.md` 작성 (frontmatter + 절차)
2. 이 `_index.md` 에 행 추가
3. (선택) `core/verify_<name>.py` 추가
4. (선택) `rubrics/verify_<name>.md` 추가
5. 빌드 — 임베드는 빌드 시점에 동결됨
