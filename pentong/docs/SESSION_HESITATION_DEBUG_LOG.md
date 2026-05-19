# 세션 유지 & Tool-use Hesitation 디버그 로그 (2026-04-17 ~ 2026-04-21)

이 문서는 뚝딱비서 v0.0.13 → v0.0.14 사이에 발생한 "대화 맥락 세션 유지 실패" 와
"Claude 가 도구 호출 전에 권한 확인 자연어로 끝나는 hesitation" 문제를 **며칠에
걸쳐 해결한 작업 흐름**을 시간순으로 기록한 것입니다.

미래에 비슷한 증상이 재발하면 이 문서를 먼저 읽어 **이미 검증해서 폐기한 접근**
을 다시 시도하는 낭비를 막는 게 목적입니다.

---

## 표면 증상 (사용자 관점)

- 두 번째 메시지부터 Claude 가 "이전 대화 맥락을 모르겠다" 고 응답
- 작업 요청 시 "Python 실행 권한이 필요합니다", "파일 쓰기 권한을 승인해 주세요"
  류 자연어 응답 + 도구 호출 없음
- retry 해도 같은 패턴 반복
- 저번주엔 잘 됐는데 갑자기 안 되기 시작

## 두 개의 문제가 얽혀 있었음

| # | 문제 | 진짜 원인 | 최종 해결 |
|---|------|----------|----------|
| A | 세션 맥락 유지 실패 | Claude CLI 2.1.112 → 2.1.114 에서 `--resume` 브랜치 버그 회귀 | Claude Agent SDK 전환 |
| B | 첫 도구 호출 hesitation | `-p` 비대화형 모드에서 Claude 모델의 보수적 행동 | Claude Agent SDK 전환 (A 와 함께 동시 해결) |

---

## 시간순 작업 흐름

### 2026-04-17 — 문제 재현 & v0.0.1 최초 수정
- 증상: Claude CLI 2.1.112 사용 중. `--resume <session_id>` 를 직전 턴 종료 직후
  호출하면 CLI 가 새 session_id 로 브랜치 + permissionMode 가 'default' 로 고정
  → 모든 Bash/Write 거부.
- 수정: `pentong_chat.py` 의 `_call_claude` 에 **3초 버퍼**(`_last_call_end`) +
  `--settings claude_settings.json` 강제 지정.
- 검증: `_test_session.py` 3턴 시나리오 PASS.
- 배포: v0.0.1 ~ v0.0.13 모두 이 방식으로 릴리스.
- 메모리: `project_claude_cli_resume_bug.md` 에 버그 + 회피책 문서화.

### 2026-04-20 오전 — 회귀 재발견
- 사용자가 테스트 PC 에서 "이전 대화 기억 못함" 증상 재보고.
- `claude --version` → **2.1.114** 로 업데이트돼 있음을 확인.
- `_test_session.py` 재실행 → **FAIL**. TURN 2 에서 stream-json 메시지 0개 +
  raw stdout 에 "권한 승인이 필요합니다" plain-text.
- 진단: 3초 버퍼를 5초/8초 로 올려도 동일 실패 → **시간 무관 회귀**.
- `--permission-mode bypassPermissions`, `--settings`, `--dangerously-skip-permissions`
  세 플래그 모두 `--resume` 브랜치 경로에서 무시됨을 실측 확인.

### 2026-04-20 오후 — 방향 전환 시도 1~4 (전부 실패)

**시도 1: 단순 옵션 교체**
- `--dangerously-skip-permissions` 단독 (`--permission-mode` 제거) → TURN 2 에서
  Read-only 작업은 PASS, Write+Bash 복합 작업은 FAIL. **부분 성공**.
- 3초 → 8초 버퍼 → FAIL.

**시도 2: `--input-format stream-json` (stdin JSONL)**
- CLI 의 `--input-format stream-json` 기능으로 stdin 에 message 배열 주입.
- 3턴 검증: TURN 2~3 에서 Claude 가 마지막 user 메시지 무시하고 **첫 user
  메시지에 다시 응답**. `--resume` 대신 이 방식을 쓰면 비결정적.
- **폐기**. Claude CLI 의 stream-json input 은 멀티턴 history 주입용이 아닌
  realtime streaming input 용으로 보임.

**시도 3: user prompt 에 history 직렬화**
- 사용자 메시지 앞에 `=== 이전 대화 이력 ===\n사용자: ...\n어시스턴트: ...\n\n`
  형태 prefix 자동 추가.
- 결과: Claude 가 "이미 끝난 과거 기록" 으로 보고 "대기 중입니다", "도와드릴까요?"
  같은 마무리 톤으로 응답. 새 user 요청을 무시.
- **폐기**. 프레임 리프레이밍("이어지는 대화")도 효과 없음.

**시도 4: system prompt 에 history 직렬화**
- base `pentong_system_prompt.txt` 뒤에 `[지금까지 진행된 대화 이력]\n...` 을
  임시 파일로 만들어 `--append-system-prompt-file` 로 주입.
- 6턴 검증: 컨텍스트 유지, 회상, 직답 모두 **정상 작동**. v0.0.14 의 최초 구현.
- 그러나 **TURN 2 의 첫 도구 호출** 에서 Claude 가 "Python 실행 권한 필요합니다"
  plain-text 로 끝내는 hesitation 현상 재발 → 세션 유지는 되는데 **다른
  종류의 실패**. 이게 문제 B 의 첫 등장.

**시도 5: 자동 재시도 로직 (시도 4 위에 덧댐)**
- stream-json 0개 + plain-text > 30자 감지 시 같은 prompt 로 1회 재시도.
- retry prompt 에 "[시스템 알림] 권한 확인 없이 즉시 작업하세요" 같은 메타 지시
  추가 → Claude 가 **"프롬프트 인젝션 가능성이 있어 임의 실행 보류"** 응답.
- 더 강한 거부 유발. retry prompt 를 중립 워딩(원본 prompt 그대로)으로 바꿔도
  Claude 가 같은 hesitation 반복.
- **부분 폐기** — retry 자체는 유지하되 prompt 강화는 포기.

### 2026-04-21 오전 — 이전 구현체 포렌식 분석
- 사용자 보고: "저번주엔 잘 됐는데 갑자기 안 된다"
- GitHub Releases 의 v0.0.1 / v0.0.5 / v0.0.7 exe 를 `pyinstxtractor-ng` 로
  추출해 bytecode 비교 (`dis` + marshal deep-hash):
  - v0.0.1 ~ v0.0.13 의 `_call_claude` 세션 코드가 **byte-identical**
  - `pentong_system_prompt.txt` 도 동일
  - 즉 **사용자의 "잘 됐던" 기억은 옛 코드가 좋아서가 아니라 당시 CLI 버전(2.1.112)
    의 `--resume` 이 안정적이었기 때문**
- Google Drive 백업의 zip 에서 옛 소스 확보. `pentong_system_prompt.txt` 에
  **"run_python 도구로 Python 스크립트를 실행합니다"** 라는 문구 발견.
  → 과거 계획은 MCP `run_python` 커스텀 도구였으나 코드에는 구현된 적 없음
  (system_prompt 와 구현의 영구 불일치).
- 9개 exe 중 `뚝딱비서(4).exe` 만 유일하게 `--continue` 플래그 흔적 발견.

### 2026-04-21 오후 — `--continue` 실험
- 어제 밤 발견한 단서: `--continue` 는 `--resume <sid>` 와 다르게 **cwd 기반으로
  최근 세션을 자동 이어감**. session_id 관리 불필요.
- `_test_continue.py` 3턴 검증: **PASS** (TURN 2 에서 45 messages 도구 호출 +
  파일 생성).
- v0.0.14 본체에 반영: 첫 턴은 `--continue` 없이, 2턴차부터 `--continue` 추가.
- history 는 system prompt 주입 제거 (--continue 가 CLI 레벨에서 맥락 유지).
- **하지만 실 GUI 테스트에서 TURN 2 의 복잡 작업 (Write+Bash) 에서 또 hesitation**.
  `_test_continue.py` 의 PASS 는 **stochastic 운**이었음이 드러남. 같은 조건에서
  반복 실행 시 2~3/10 번 실패 재현.

### 2026-04-21 오후 — Haiku 전환 + warmup 자동화
- **Haiku 전환**: Sonnet 보다 tool-use hesitation 이 약한 편이라 기대.
  `--model haiku` 로 1줄 변경. → 여전히 복잡 작업에서 "권한 필요" 자연어 응답.
  **폐기 (덜 효과적)**.
- **warmup 자동화**: 작업 폴더 변경 시 앱이 "파일 목록 보여줘" 를 자동 전송해
  TURN 1 을 간단한 Glob 호출로 통과시킴. 사용자 실제 첫 메시지는 TURN 2 가 됨.
  → 첫 턴은 확실히 통과. 그러나 TURN 2 에서 복잡 작업 (Write 필요) 들어오면
  다시 hesitation. 근본 해결 아님.

### 2026-04-21 저녁 — 결정적 통찰 & SDK 전환 결정

**사용자 지적**: 원래 뚝딱비서 설계 의도는 "Claude CLI 가 백그라운드에서
**대화형 세션**으로 돌아가고, 뚝딱비서 GUI 는 그 세션의 화면을 relay" 하는
구조였음. 그런데 실제 구현은 매 턴마다 `-p` 비대화형 서브프로세스를 새로 띄우는
구조 → **취지와 구현이 어긋나 있었음**.

**가설**: Claude 모델은 `-p` 모드에서 "사용자가 실시간으로 확인할 수 없는 환경" 으로
인지하고 더 보수적으로 행동. 복잡한 첫 도구 호출 (여러 권한 동시 필요) 앞에서
자발적 확인 요청. 시스템 프롬프트와 CLI 플래그로 override 불가능.

**검증**: 내(Claude Code CLI 대화형 세션) 가 같은 작업(xls 읽기 + xlsx 생성) 을
직접 수행 → 권한 요청 한 번도 없이 Bash → xlrd → openpyxl → Write 자유롭게
연속 사용, 깨끗하게 완료. **대화형 vs `-p` 비대화형 차이가 결정적**.

**해결 경로**: `claude-agent-sdk` (Python) 전환.
- SDK 는 내부적으로 Claude CLI 를 **대화형 세션으로 띄우고 장수 유지**
- 같은 `~/.claude/` OAuth 토큰 사용 (API key 불필요, 로그인 플로우 그대로)
- `ClaudeSDKClient.connect()` → `query()` → `receive_response()` 의 async API
- `-p` 모드 영영 탈출

### 2026-04-21 밤 — SDK 전환 실행
- `pip install claude-agent-sdk` (0.1.64)
- `_call_claude` 를 async `_sdk_send` + `_sdk_connect` 로 재작성.
- 백그라운드 asyncio loop 를 별도 스레드에서 가동, tkinter 메인스레드와
  `asyncio.run_coroutine_threadsafe` + `queue.Queue` 로 통신.
- 작업 폴더 변경 시 SDK client disconnect → 다음 호출에서 새 cwd 로 재연결.
- 중단 버튼 → `client.interrupt()`.
- 앱 종료 → `client.disconnect()` + loop stop.
- 설정 UI / 로그인 / 구글 로그아웃 / `SetupWizard` 는 **일절 건드리지 않음**
  (SDK 가 같은 OAuth 토큰 사용).
- `_test_sdk_smoke.py` 2턴 검증: **PASS** (TURN 1 5.6s Glob, TURN 2 32.9s 에
  Bash 6회 연속 호출로 분석 완료, 권한 요청 0회).

### 2026-04-21 밤 — 문서화 및 가드레일
- 이 문서(`docs/SESSION_HESITATION_DEBUG_LOG.md`) 작성
- `pentong/CLAUDE.md` 의 세션 관리 정책 섹션 업데이트
- `Releases/CHANGELOG.md` v0.0.14 항목에 폐기한 접근 기록 (재시도 방지)
- 메모리 `project_v0_0_14_session_redesign.md` 업데이트

---

## 폐기된 접근 (재시도 금지) — 최종 정리

| 접근 | 실패 원인 |
|------|----------|
| `--resume <session_id>` + 3~8초 버퍼 | CLI 2.1.114 에서 시간 무관 회귀. 첫 재개 호출이 무조건 'default' 권한 모드로 브랜치 |
| `--input-format stream-json` + stdin JSONL 멀티턴 | 마지막 user 메시지를 비결정적으로 무시 |
| user prompt 에 history 직렬화 | Claude 가 "끝난 과거 기록" 으로 보고 마무리 톤으로 응답 |
| system prompt 에 history 직렬화 (`--append-system-prompt-file`) | 컨텍스트 유지는 되지만 `-p` 모드의 첫 도구 호출 hesitation 그대로 |
| retry prompt 워딩 강화 (`[시스템 알림]` 등) | Claude 가 prompt-injection 으로 의심해 더 강한 거부 |
| `--continue` + warmup 자동화 | 확률적으로 PASS (60~70%). 복잡 작업에서 stochastic 실패 |
| Haiku 모델 전환 | hesitation 완화는 되지만 complex Write 조합에선 여전 발생 |
| ABSOLUTE RULE 영문 강화 (`NEVER ask for approval`) | `-p` 모드에서는 모델 내부 보수성을 override 못 함 |
| Claude CLI 2.1.112 다운그레이드 | hesitation 은 CLI 버전과 무관 (모델 측 문제). 효과 미미 + 유지보수 부담 |

---

## 최종 방식 (v0.0.14 ~)

1. **Claude Agent SDK (`claude-agent-sdk`) 사용**
2. `ClaudeSDKClient` 를 백그라운드 asyncio loop 에서 장수 유지 (대화형 세션)
3. `ClaudeAgentOptions` 로:
   - `model="haiku"` (Sonnet 으로 변경 가능 — 이제 모델별 차이 줄어듦)
   - `system_prompt={"type": "preset", "preset": "claude_code", "append": <base>}`
   - `allowed_tools=["Bash","Read","Write","Edit","Glob","Grep"]`
   - `permission_mode="bypassPermissions"`
   - `cwd=<work_dir>`, `add_dirs=[CONFIG_DIR]`, `include_partial_messages=True`
4. `self.history` 는 **턴 수 카운트 + session_cache 기록용**. 맥락 유지는 SDK
   가 자동 (별도 주입 불필요).
5. 작업 폴더 변경 시 client 재연결.
6. `~/.ddukddak/current_session.md` self-managed memory 캐시는 유지 (Claude 가
   필요시 Read 로 접근).

---

## 교훈 (미래 작업 시 참고)

1. **CLI 버전 업데이트는 조용한 치명타**: 2.1.112 → 2.1.114 가 `--resume` 동작을
   바꿨고, 우리는 CLI 를 자동 업데이트에 맡긴 상태였다. 앞으론 CLI 버전을 pin
   하거나, 매 릴리스 전 `_test_sdk_smoke.py` 류 검증 필수.
2. **"잘 됐던 기억" 을 의심하라**: 옛 exe 의 bytecode 가 전부 동일했다는 건
   "코드가 좋았다" 가 아니라 "환경이 좋았다" 는 뜻. 단일 코드 경로가 환경에
   따라 stochastic 하게 돌거나 안 돌 수 있다.
3. **테스트 PASS = 확정적 성공이 아님**: `_test_continue.py` 가 PASS 였던
   이유는 TURN 1 이 간단한 Glob 만 필요한 요청이었기 때문. 실사용 패턴(복잡
   Write)으로 검증해야 진짜 PASS.
4. **사용자 설계 의도와 구현이 어긋나 있으면 언젠가 터진다**: "CLI 대화형 세션의
   GUI 래퍼" 설계 의도가 `-p` 반복 구조로 구현돼 있었고, 이게 표면화되기까지
   CLI/모델 업데이트 몇 번이 필요했을 뿐. 원래 의도로 돌아가는 게 정답.
5. **Claude 모델의 tool-use hesitation 은 prompt 로 이길 수 없다**: `-p`
   비대화형에서는 시스템 프롬프트의 "NEVER ask for approval" 같은 지시가 모델의
   내부 보수성 프라이어를 완전히 override 하지 못함. 환경을 바꿔야 함 (대화형
   전환).
6. **폐기한 접근도 문서에 남겨라**: 미래의 나 / 다른 개발자가 같은 실험을
   반복하지 않게. 이 문서가 그 역할.

---

## 다음 가드레일 (TODO)

- [ ] `_test_sdk_smoke.py` 를 빌드 파이프라인(`build.bat`) 에 자동 실행 훅으로
      포함 — FAIL 이면 exe 안 만들어지게
- [ ] SDK 버전 pin (`requirements.txt` 에 `claude-agent-sdk==0.1.64`) 및 업데이트
      정책 명시
- [ ] Haiku / Sonnet 모델별 도메인 정확도 비교 — "프로그램 종류수" 같은 용어
      해석 차이 검증
- [ ] 작업 폴더 변경 시 SDK 재연결이 안 될 때 fallback 로직
- [ ] session_cache 가 너무 길어지면 요약 + truncate (현재 무제한 누적)
