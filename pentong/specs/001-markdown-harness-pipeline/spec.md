# Spec 001 — 마크다운 하네스 파이프라인 (v0.0.25)

**Status**: draft
**Date**: 2026-05-07
**Base**: 뚝딱비서 v0.0.24

## 문제 (Why)

뚝딱비서 v0.0.24 는 단일 시스템 프롬프트(`pentong_system_prompt.txt`)와 `core/*` 헬퍼만으로 동작한다. 이 구조에서 다음 미준수 사례가 반복 관측됨:

| # | 사례 | 사용자 영향 |
|---|---|---|
| 1 | "python/COM 권한 없다 허용해 달라" | UX 즉시 손상, 신뢰도 추락 |
| 2 | "이전 대화 이력 없다" | 멀티턴 대화 단절, 작업 재시작 강요 |
| 3 | 한글 인코딩 깨짐 / 엑셀 요청에 엉뚱한 포맷 반환 | 결과물 불사용, 작업 처음부터 재시도 |
| 4 | 임시 스크립트 v1→v2→v3→v4 별파일 (legacy transcript 24턴/202초/$0.28) | 비용·시간 낭비, 매 시도가 cold start |
| 5 | 같은 에러 4회+ 시도 (3회 룰 위반) | 무한 루프 위험, 사용자 시청 시간 낭비 |

근본 원인: **절차가 시스템 프롬프트 단일 텍스트에 흩어져 있어 강제 불가**. Claude Haiku 4.5 가 작업마다 즉흥 R&D 를 함.

## 목표 (What)

뚝딱비서 v0.0.25 는 **마크다운 기반 하네스 파이프라인**을 도입한다. 모든 stage(루브릭·절차·금지·검증기준·plan·검증리포트·세션 audit) 가 마크다운 파일에 정의되어 hot-reload 가능하다.

핵심 3대 목표:
1. **절차 모듈화** — 작업 종류별 절차를 독립 .md 모듈로 분리, frontmatter 로 강제
2. **산출물 검증** — `core/verify_*.py` 함수가 작업 완료 후 자동 실행, 결과를 마크다운 카드로 사용자에 표시
3. **세션 다중화 + 선택** — 단일 `current_session.md` → 다중 `sessions/<날짜_제목>.md` + 사이드바 UI

## 핵심 결정 사항

### Enforcement 정책
- `plan_required` = **auto-proceed**. 매 작업마다 사용자 확인 X. 위반 감지 시만 멈춤.
- `enforce` 위반 시 = **1-2회 자동 재시도** (사용자에게 안 보이게, UI "처리 중..." 으로 가림). 그래도 실패 시 사용자 보고로 전환.
- `max_attempts` (기본 3회) 위반 시 = **부류 분류 + 분기**. Claude 가 frontmatter 형식으로 종료 메시지 출력.
- 세션 압축 = **하이브리드** (마지막 N턴 + frontmatter summary 갱신)

### Anti-patterns (재시도 금지)
- Multi-agent (planner / generator / evaluator 분리)
- Sonnet advisor + Haiku executor (v0.0.24.1 실험 폐기)
- Sonnet 으로 모델 승격
- Plan-and-Execute 분리

→ Haiku 4.5 단일로 끝까지 패턴화.

## 디렉토리 구조

```
pentong/
├── pentong_chat.py                       # 호스트 — verdict 카드 / hook / retry 숨김
├── pentong_system_prompt.txt             # 슬림화 (4-5KB) — invariants + index 만 append
├── prompts/
│   └── skills/
│       ├── _invariants.md                # 절대 금지/필수 (Hard rules)
│       ├── _index.md                     # trigger → skill 라우팅
│       ├── _session.md                   # 세션 캐시 강제 참조
│       ├── _output_contract.md           # 출력 포맷 계약
│       ├── _loop_guard.md                # 3회 룰, 같은 스크립트 수정만
│       ├── xlsx_clean.md                 # core/excel_clean.py 매핑
│       ├── xlsx_split.md                 # core/excel_split.py
│       ├── xlsx_merge.md                 # core/excel_merge.py
│       ├── xlsx_template.md              # core/excel_template.py
│       ├── xlsx_pdf_match.md             # legacy v1~v4 사례 박제 시드
│       ├── hwp_section.md                # core/hwp_section.py
│       ├── hwp_template.md               # core/hwp_template.py
│       ├── hwp_replace.md                # core/hwp_replace.py
│       ├── hwp_merge.md                  # core/hwp_merge.py
│       └── pdf_extract.md                # core/pdf_text.py
├── rubrics/
│   ├── verify_xlsx.md
│   ├── verify_hwpx.md
│   └── verify_md.md
└── core/
    ├── verify_xlsx.py                    # 신규 — 행수·시트수 invariant
    ├── verify_hwpx.py                    # 신규 — 단락수·표수 invariant
    ├── verify_md.py                      # 신규 — 마크다운 라운드트립 손실
    └── (기존 *.py 유지)
```

## Skill 모듈 frontmatter 스펙

```yaml
---
skill: xlsx_clean
trigger:
  - "빈 행 제거"
  - "공란 정리"
  - "blank row"
priority: 10                              # 충돌 시 큰 값 우선
enforce: true
plan_required: false                      # auto-proceed
single_script: true                       # v_n+1 별파일 금지
max_attempts: 3
preconditions:
  - 파일 확장자 .xlsx 또는 .xlsm
  - 작업 폴더 내부 경로
steps:
  - id: parse
    op: core.excel_reader.get_workbook_info
    record: [sheet_count, row_count]
  - id: clean
    op: core.excel_clean.remove_blank_rows
  - id: verify
    op: core.verify_xlsx.run
    rubric: rubrics/verify_xlsx.md
postconditions:
  - 결과 파일명 패턴: "<원본>_결과.xlsx"
  - 시트 수 == 원본 시트 수
  - 행 수 < 원본 행 수
forbidden:
  - 원본 덮어쓰기
  - JSON 결과 출력 (마크다운 표 강제)
unsupported:
  - 피벗 / 매크로 / 조건부서식 (있으면 "부분 처리" 통보)
---

# 절차 (markdown body)
...

# 알려진 함정
...
```

## verdict 카드 스펙 (max_attempts 위반 시)

Claude 가 다음 frontmatter 로 종료 메시지 출력:

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
    detail: "정규화 후에도 매칭률 33% — PDF 형식이 학기마다 달라 헤더 자동 인식 실패"
last_error: "match step 매칭률 < 50% 임계 미만"
user_action: |
  PDF 의 1학기와 2학기 파일이 컬럼 순서가 다릅니다.
  헤더 행이 명확한 PDF 로 다시 첨부하시거나,
  매칭 가능한 12행만 결과 받으시려면 [부분 진행] 을 눌러 주세요.
---
```

호스트가 카드로 렌더:

```
┌─────────────────────────────────────┐
│ ⏸ 작업 멈춤 (3회 시도)              │
│                                     │
│ 🔧 사용자 행동 필요                 │
│                                     │
│ ✅ 1. 엑셀 읽기 — 100행, 5시트       │
│ ✅ 2. PDF 추출 — 130개 교과목        │
│ ❌ 3. 매칭 — 매칭률 33% 임계 미달   │
│                                     │
│ PDF 의 1학기와 2학기 파일이         │
│ 컬럼 순서가 다릅니다. 헤더 행이     │
│ 명확한 PDF 로 다시 첨부해 주세요.   │
│                                     │
│ [부분 진행 (12행만)] [다른 파일로]  │
└─────────────────────────────────────┘
```

부류 아이콘:
- 🔧 `external_blocker` — 사용자 행동 필요 (대부분 이 부류)
- 🚫 `system_limit` — v0.0.25 미지원 명시
- ❓ `unclear_intent` — 명확화 질문

## 세션 다중화

```
%APPDATA%/뚝딱비서/sessions/
├── index.md                              # 사이드바 캐시 (제목·날짜·turn 수·verify)
├── 2026-05-07_1052_BITS매칭.md
├── 2026-05-07_1430_정산부서별취합.md
└── 2026-05-06_1100_HWP양식정리.md
```

세션 파일 frontmatter:
```yaml
---
session_id: 2026-05-07_1052
title: BITS 매칭 작업
created: 2026-05-07T10:52:00+09:00
last_active: 2026-05-07T11:15:00+09:00
turn_count: 24
cost_usd: 0.28
work_dir: C:\Users\DSU\Desktop\올빼미
attached_files: [...]
skill_used: xlsx_pdf_match
verify_result: pass
status: completed
summary: |
  (Haiku 가 매 턴 끝에 갱신 — 압축용)
---
```

UI: 좌측 사이드바 (ChatGPT 패턴). 클릭 → 활성화 + Claude context 주입. "이어서 작업" / "새 세션" 버튼.

## 강제 메커니즘 — 3중 방어

1. **시스템 프롬프트** — Claude 측. 작업 흐름 강제.
2. **호스트 hook** — `pentong_chat.py` PreToolUse/PostToolUse. 도구 호출이 활성 skill 의 `steps[].op` 와 일치하는지 검증. 응답 텍스트 패턴 매칭 ("권한", "허용") 자동 차단.
3. **JSON Schema strict** — bridge/verify 응답 검증. additionalProperties: false. 5회 자동 수정 루프.

## 캘리브레이션 루프 (3겹)

```
sessions/*.md  ─── audit 입력
       ↓
 tools/skill_audit.py (주기 실행)
   - skill 의 steps[] vs 실제 도구 호출 시퀀스 비교
   - 미준수 사례 자동 분류
   - report.md 생성
       ↓
 사용자/개발자가 report.md 보고 skill.md / _invariants.md 수정
       ↓
 빌드 후 hot-reload (개별 transcript 재처리 X, 기준만 개선)
```

무신사 The Machine 의 "개별 점수 안 고치고 루브릭만 캘리브레이션" 패턴 동일.

## 단계별 구현 계획

| Phase | 작업 | 검증 |
|---|---|---|
| **P1** | `_invariants.md` + `_index.md` + `_session.md` 골격 | system prompt slim, 미준수 사례 1·2·3 차단 확인 |
| **P2** | `xlsx_pdf_match.md` 시드 모듈 (legacy 사례 박제) | legacy transcript 시나리오 < 8턴 안에 끝나는지 |
| **P3** | `core/verify_xlsx.py` + verdict 카드 호스트 렌더 | xlsx_clean 후 행수 검증 카드 표시 |
| **P4** | 호스트 hook (PreToolUse / PostToolUse / 응답 패턴 매칭) | "권한 허용" 응답 자동 차단 |
| **P5** | 세션 다중화 (`sessions/` 폴더, 사이드바 UI) | 5개 세션 만들고 전환 동작 |
| **P6** | 나머지 skill 모듈 (xlsx_*, hwp_*, pdf_*) | 회귀 테스트 (`_test_session.py` 확장) |
| **P7** | `tools/skill_audit.py` 캘리브레이션 도구 | 1주 사용 후 report.md 자동 생성 |

## Out of scope (v0.0.25 미포함)

- HWP 본문 in-place 텍스트 편집 (rhwp 미지원)
- OCR (스캔 PDF)
- Multi-agent / advisor pattern
- Sonnet 모델 승격
- 텔레메트리 (PIPA 리스크)

## 참고 자료

- 무신사 The Machine — 7-게이트 + JSON Schema strict + 마크다운 루브릭 hot-reload + 3겹 피드백
- Anthropic harness-design — context reset > compaction, 파일·계약 기반 핸드오프
- Martin Fowler harness-engineering — feedforward(가이드) + feedback(센서)
