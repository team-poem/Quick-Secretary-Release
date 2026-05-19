---
skill: _session
type: protocol
priority: 990
always_load: true
description: 세션 캐시 강제 참조 절차. 미준수 사례 2 ("이전 대화 이력 없다") 근본 차단.
---

# 세션 컨텍스트 절차

## 활성 세션 결정

호스트가 환경변수 `DDUKDDAK_ACTIVE_SESSION` 으로 활성 세션 파일 경로를 전달한다. 없으면 단일 모드(legacy v0.0.24 호환):

```
DDUKDDAK_ACTIVE_SESSION = ~/.ddukddak/sessions/2026-05-07_1052_BITS매칭.md
DDUKDDAK_SESSION_CACHE  = ~/.ddukddak/current_session.md  (legacy fallback)
```

v0.0.25 부터는 `sessions/` 폴더 다중화. 사용자가 사이드바에서 선택한 세션이 활성.

## 세션 파일 frontmatter

```yaml
---
session_id: 2026-05-07_1052
title: BITS 매칭 작업
created: 2026-05-07T10:52:00+09:00
last_active: 2026-05-07T11:15:00+09:00
turn_count: 24
cost_usd: 0.28
work_dir: C:\Users\DSU\Desktop\올빼미
attached_files:
  - 2025학년도 BITS 개설과목 리스트.xlsx
  - 부산공유대학_*.pdf
skill_used: xlsx_pdf_match
verify_result: pass | fail | partial
status: active | completed | stopped
summary: |
  (Haiku 가 매 턴 끝에 갱신. 압축용. 80자 이내 한 줄.)
---

## Turn 1 — 10:52
**User**: ...
**Assistant**: ...
[도구: parse_xlsx]

## Turn 2 — 11:14
...
```

## 강제 참조 트리거

사용자 메시지에 다음 표현이 등장하면 답변 전 반드시 활성 세션 파일을 Read 한다:

**모호 참조**:
- "아까 그거" / "방금 그거" / "이전 거" / "그거"
- "2번 파일" / "3번째" / "그 파일" / "이 파일"
- "그 결과" / "방금 만든 거" / "전에 만든"
- "이어서" / "다시" / "또" / "계속"

**작업 연속 의도**:
- "여기에 추가로" / "이번에는"
- "그럼 이제" / "그리고"
- "방금 작업한 거"

**금지 응답** (이런 답 출력 시 호스트가 차단 + 재시도):
- "이전 대화 이력이 없습니다"
- "어떤 ___ 인지 모르겠습니다"
- "맥락이 없어서 답변 불가"
- "처음부터 다시 알려주세요"

## Read 절차

```
1. 활성 세션 경로 확인:
   path = os.environ.get("DDUKDDAK_ACTIVE_SESSION") \
       or os.environ.get("DDUKDDAK_SESSION_CACHE")

2. Read tool 로 파일 읽기

3. frontmatter 의 attached_files / work_dir / skill_used 확인

4. body 의 마지막 N (=10) 턴 + frontmatter summary 결합해 컨텍스트 복원

5. 사용자 모호 참조와 매칭되는 turn 찾기:
   - "방금 만든 파일" → 가장 최근 turn 의 결과 파일명
   - "2번 파일" → attached_files[1]
   - "이어서" → 가장 최근 turn 의 작업 종류

6. 매칭 실패 시 verdict unclear_intent (사용자에 한 번만 명확화 질문)
```

## summary 필드 갱신 (Q4 하이브리드)

매 turn 작업 종료 직전, 다음 형식으로 frontmatter 의 `summary` 를 갱신한다:

```
summary: "<원본>.xlsx 마지막 두 컬럼에 PDF 4개의 수업유형/강의실 매칭 입력 (37행, 매칭률 100%, 결과 파일 ___결과.xlsx)"
```

규칙:
- 80자 이내 한 줄 (UI 사이드바 표시용)
- 작업 종류 + 입력 파일 + 결과 + 핵심 수치
- 한국어 명사형 (동사 종결 X)

호스트가 turn 끝에 자동으로 다음 메타 메시지를 system 채널로 보낸다:
```
[INTERNAL] 세션 summary 를 갱신해 주세요. 활성 세션 파일의 frontmatter `summary` 필드를 위 작업 결과로 한 줄 업데이트.
```

이 메시지는 사용자에게 보이지 않는다.

## 세션 파일 없음 처리

- `path` 가 None 이거나 파일 미존재 → **새 대화로 간주**
- 사용자에 묻지 말고 즉시 작업 시작
- 첫 turn 끝에 호스트가 새 세션 파일을 자동 생성

## 파일 미존재 시 금지 응답

- "세션 파일을 찾을 수 없습니다"
- "맥락이 비어 있어서 ..."
- "이전 작업 정보가 없습니다"

→ 그냥 새 작업으로 처리. 사용자는 어차피 이 메시지를 본 적 없을 가능성 큼.

## 다중 세션 전환 (v0.0.25+)

사용자가 사이드바에서 다른 세션을 클릭하면 호스트가:
1. 현재 SDK client `disconnect()`
2. `DDUKDDAK_ACTIVE_SESSION` 환경변수 갱신
3. 새 SDK client 생성 (cwd = 새 세션의 work_dir)
4. 다음 user 메시지 입력 시 첫 답 전에 활성 세션 파일 자동 Read

Claude 측에서는 매 turn 시작 시 환경변수가 가리키는 파일이 활성 세션이라고 간주하면 된다.

## 압축 정책 (Q4 c 하이브리드)

세션 turn_count > 10 이면:
- 마지막 10 turn body 만 컨텍스트 주입
- 그 이전 turn 은 frontmatter `summary` 한 줄로 대체
- 호스트가 system prompt append 시 자동 처리 (Claude 측은 신경 X)

단, 사용자가 "처음에 뭐였더라" 식으로 명시 회상 요청 시:
- 활성 세션 파일을 Read 해서 1번 turn 부터 회수
- Read 결과를 컨텍스트로 새 답변

## 디버깅 (개발자용)

세션이 안 이어진다는 의심:
1. `echo $DDUKDDAK_ACTIVE_SESSION` (또는 SET in CMD)
2. 그 파일을 Read
3. frontmatter `last_active` 가 최근인지
4. body 마지막 turn 이 직전 사용자 메시지를 담고 있는지
5. 호스트의 turn append 로직이 정상인지 (`pentong_chat.py` 의 `_append_turn_to_session`)
