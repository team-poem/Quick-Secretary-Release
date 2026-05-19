---
skill: _loop_guard
type: protocol
priority: 980
always_load: true
description: 루프 방지 + 자동 재시도 정책. 미준수 사례 4 (v_n+1 별파일) / 5 (3회 룰 위반) 차단.
---

# 루프 방지 + 재시도 정책

## 핵심 철학

**"끝까지 파본다" 보다 "막히면 빨리 보고"**.

사용자는 10분 뺑뺑이보다 30초 안에 명확한 다음 step 안내를 원한다. 모델 비용·사용자 시청 시간·신뢰도 모두 손해.

## 자동 재시도 (Q2 a — 사용자에 안 보이게)

**스코프**: 단일 step 내 일시 실패. 재시도 1-2회 자동, 사용자 UI 에는 "처리 중..." 만 표시.

### 자동 재시도가 가능한 경우

| 케이스 | 재시도 동작 |
|---|---|
| `ENOENT: no such file` (한글 NFC/NFD 차이) | `os.listdir()` 결과 정규화 후 재시도 |
| `ModuleNotFoundError` (kordoc / pdfplumber 미설치) | `pip install -q ___` 후 재시도 |
| `KeyError: <컬럼명>` (대소문자/공백 차이) | 정규화 후 재시도 |
| `UnicodeDecodeError` | encoding='utf-8' 명시 후 재시도 |
| Subprocess timeout | 같은 명령 1회 재시도 |

### 자동 재시도가 불가능한 경우 (즉시 verdict)

- HWP v3 (구버전) — `UNSUPPORTED_FORMAT`
- 스캔 PDF (텍스트 0)
- 암호화 파일
- 사용자 의도 모호 + 데이터 모호
- 작업 폴더 외부 경로 요청

### 재시도 절차

```
1. 첫 시도 실패
   ↓
2. 에러 분류 (위 표)
   ↓
3. recoverable: true → 같은 step 재시도 (최대 2회)
   recoverable: false → verdict 즉시 출력
   ↓
4. 재시도도 실패 → verdict (사용자에 보고)
```

호스트(`pentong_chat.py`)는 재시도 중에는 partial message 도 사용자에 노출하지 않는다 (`include_partial_messages=False` 일시 toggle 또는 메시지 swallow). UI 는 "처리 중..." 단일 표시.

## 단일 스크립트 수정 강제 (Rule 6)

**금지 패턴**:
```
%TEMP%/_ddukddak_pipeline.py     (v1)
%TEMP%/_ddukddak_pipeline_v2.py   (v2)
%TEMP%/_ddukddak_pipeline_v3.py   (v3)
%TEMP%/_ddukddak_pipeline_final.py (v4)
```

→ legacy 24턴/202초 transcript 의 절반이 이 패턴. 매 시도가 cold start.

**정답 패턴**:
```
%TEMP%/_ddukddak_pipeline.py
  ↓ (Edit으로 수정)
같은 파일 재실행
  ↓ (Edit으로 수정)
같은 파일 재실행
```

### 호스트 자동 검증

`pentong_chat.py` 가 PostToolUse hook 에서 검증:
- `%TEMP%` 의 `_ddukddak_*` 파일 목록 비교
- 파일명 패턴 `_v\d+`, `_final\d*`, `_new`, `_fixed`, `_real` 발견 시 차단
- Claude 에 회신: "단일 스크립트 수정 정책 위반. 같은 파일 (`_ddukddak_pipeline.py`) 을 Edit 으로 수정해 주세요."
- 자동 재시도 1회

## 같은 에러 카운팅

호스트가 다음을 turn 단위로 카운트:

```python
error_counter = {}  # error_signature → count

def signature(error_text):
    # 영문/한글 메시지의 첫 단어 + 에러 타입 추출
    # "ENOENT: no such file '/foo/...'" → "ENOENT"
    # "KeyError: '학과명'" → "KeyError"
    return ...

# 매 도구 결과 후
sig = signature(stderr or output)
error_counter[sig] = error_counter.get(sig, 0) + 1
if error_counter[sig] >= 3:
    force_verdict()
```

## 행동 기반 트리거 (호스트 측 감지)

다음 패턴이 감지되면 즉시 verdict 강제:

| 신호 | 임계 |
|---|---|
| Python 스크립트 작성·수정·재실행 | 4회 이상 |
| 같은 파일 편집 (Edit) | 5회 이상 |
| 한 turn 내 Bash 도구 호출 | 15회 이상 |
| 같은 에러 시그니처 | 3회 이상 |
| 라이브러리 변경 (openpyxl→xlrd→pandas...) | 2회 이상 |
| `%TEMP%/_ddukddak_*_v\d+.py` 파일 생성 | 1회 (즉시 차단) |
| 응답에 "권한"·"허용" 키워드 | 1회 (즉시 차단 + 재시도) |

호스트가 위 임계 도달 시 user prompt 에 시스템 메시지 주입:
```
[INTERNAL] 루프 방지 — 위 작업이 ___ 회 반복되었습니다.
즉시 멈추고 verdict frontmatter 를 출력해 주세요.
부류: external_blocker | system_limit | unclear_intent
```

## verdict 출력 절차

3회 룰 또는 행동 트리거 도달 시:

```yaml
---
verdict: stop
category: external_blocker | system_limit | unclear_intent
recoverable_by_user: true | false
attempted:
  - step: <id>
    result: ok | failed
    detail: "<한국어 한 줄>"
  - ...
last_error: "<영문 에러 시그니처 OR '루프 임계 도달'>"
user_action: |
  <사용자가 다음에 할 행동, 한국어 1-3 문장>
  <필요하면 [버튼] 표기로 호스트에 액션 힌트>
---
```

### attempted 누적 방식

각 step 의 result/detail 은 그 step 시작·종료 시점의 사실로 채운다.

**좋은 예**:
```yaml
attempted:
  - step: parse_xlsx
    result: ok
    detail: "원본 142행, 5시트 — 헤더는 6번째 행"
  - step: parse_pdf
    result: ok
    detail: "PDF 4개에서 130개 교과목 추출 — 일부 페이지 표 분할"
  - step: normalize
    result: ok
    detail: "NFC + 공백제거 적용 — 130개 모두 정규화 성공"
  - step: match
    result: failed
    detail: "매칭률 33% (37/142) — 1학기 PDF 만 매칭 잘 됨, 2학기는 헤더 다름"
```

**나쁜 예 (금지)**:
```yaml
attempted:
  - step: try1
    result: failed
    detail: "안 됨"
  - step: try2
    result: failed
    detail: "또 안 됨"
```

### user_action 작성 가이드

- **구체적**: "재시도해 주세요" 단독 금지. 무엇을 어떻게 할지 명시.
- **한국어**: 영어 표현 / 영문 명령 그대로 노출 금지.
- **선택지 제시**: 가능하면 2-3 개 옵션 (예: "재첨부 vs 부분 진행 vs 다른 파일")
- **버튼 표기**: 호스트가 액션 버튼으로 렌더 가능하게 `[버튼명]` 형태:
  - `[재시도]`
  - `[부분 진행 (12행만)]`
  - `[다른 파일로]`
  - `[새 세션]`
  - `[수동 가이드 보기]`

## v0.0.25 미지원 응답 (system_limit 부류)

다음 작업은 1회 시도 전에 즉시 verdict (max_attempts 까지 가지 말 것):

| 요청 | 답 |
|---|---|
| HWP 본문 in-place 텍스트 편집 (특정 단락 수정) | "현재 버전 미지원. 마크다운으로 읽고 새 .hwpx 작성 방식 권장. 진행할까요?" |
| 스캔 PDF 텍스트 추출 | "이 PDF 는 스캔 이미지 같습니다. OCR 필요. 현재 미지원." |
| Excel 피벗 / 매크로 / 조건부서식 | "현재 버전 미지원 기능. 가능한 부분만 처리합니다." |
| 작업 폴더 외부 접근 | "작업 폴더 외부 경로는 접근할 수 없습니다. 좌측 [폴더 변경] 버튼으로 작업 폴더를 바꿔주세요." |

이 경우 verdict frontmatter:
```yaml
---
verdict: stop
category: system_limit
recoverable_by_user: true
attempted:
  - step: precheck
    result: failed
    detail: "이 작업은 v0.0.25 미지원 기능입니다."
last_error: "unsupported_feature"
user_action: "<위 표의 답>"
---
```

## 사용자에게 보내는 응답 톤

verdict 카드는 호스트가 시각화하지만, 카드와 함께 한 줄의 사용자 친화 메시지를 추가하면 더 좋다:

**좋은 예**:
> "지금까지 시도한 결과 매칭률이 33% 라 신뢰도가 낮네요. PDF 형식 차이가 원인 같습니다. 아래 카드의 안내를 확인해 주세요."

**나쁜 예** (금지):
> "에러 발생. 작업 중단."
> "Failed after 3 attempts."

## 디버깅 (개발자용)

루프가 자주 발생한다는 의심:
1. `~/.ddukddak/sessions/<현재>.md` 의 마지막 turn 들에서 `[도구]` 호출 횟수 카운트
2. 같은 파일 Edit 횟수 grep
3. 호스트 측 `error_counter` 로그 확인 (`pentong_chat.py` 가 stderr 또는 logs 에 기록)
4. skill 모듈의 `forbidden:` / `unsupported:` 가 정확히 매칭되는지 검토
5. `_index.md` 의 trigger 가 사용자 메시지를 잘못 매칭하는 케이스 확인
