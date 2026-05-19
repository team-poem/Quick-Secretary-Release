# 뚝딱비서 — Claude Code 작업 가이드

이 문서는 Claude Code CLI (혹은 Claude Agent SDK) 가 이 프로젝트의 소스를
수정할 때 참고하는 온보딩 문서입니다. 실사용자와의 대화 중 런타임 행동 지침은
`pentong_system_prompt.txt` 에 있습니다.

- [프로젝트 개요](#프로젝트-개요)
- [핵심 디렉토리/파일](#핵심-디렉토리파일)
- [실행/빌드](#실행빌드)
- [테스트](#테스트)
- [세션 관리 정책 (v0.0.14~)](#세션-관리-정책-v0014)
- [가드레일](#가드레일)
- [릴리스 플로우](#릴리스-플로우)
- [트러블슈팅](#트러블슈팅)

**필수 사전 독서**: 세션 관련 변경 작업 전에 반드시
[docs/SESSION_HESITATION_DEBUG_LOG.md](docs/SESSION_HESITATION_DEBUG_LOG.md) 를
읽어 **이미 검증해서 폐기한 접근**을 다시 시도하지 말 것. v0.0.13 → v0.0.14
전환 과정에서 며칠 걸린 모든 실험·실패·최종 해법 기록이 있습니다.

## 프로젝트 개요

뚝딱비서는 Windows 데스크톱 GUI 래퍼로, 사용자가 엑셀(.xls/.xlsx) 과 한글(.hwp)
파일을 자연어 지시로 편집할 수 있게 해주는 AI 어시스턴트입니다. 내부적으로
Claude Code CLI 의 `-p` (print/비대화형) 모드를 서브프로세스로 띄워서 응답을
받아옵니다.

- 진입점: `pentong_chat.py` (tkinter GUI + 세션 관리 + CLI 호출)
- 모델: Claude Sonnet 4.6 (`--model sonnet`)
- 배포: PyInstaller 단일 exe, GitHub Releases 에 업로드
- 타깃 사용자: 한국 교직원/사무직 (비개발자)

## 핵심 디렉토리/파일

```
뚝딱비서/
├── pentong/                       # 소스 루트
│   ├── pentong_chat.py            # 메인 GUI + 세션 로직 (진입점)
│   ├── pentong_system_prompt.txt  # 런타임에 Claude 에 주입되는 행동 지침
│   ├── build.bat                  # PyInstaller 빌드 스크립트
│   ├── pentong_chat.spec          # PyInstaller 설정
│   ├── core/                      # Claude 가 호출하는 검증된 엑셀/HWP 함수
│   │   ├── excel_reader.py, excel_writer.py, excel_template.py, ...
│   │   ├── hwp_reader.py, hwp_replace.py, hwp_section.py, ...
│   │   └── setup_helper.py        # Python/Git/Node/CLI 자동 설치
│   ├── _test_session.py           # 세션 유지 검증 (6턴 시나리오)
│   ├── CLAUDE.md                  # 이 파일
│   └── .github/copilot-instructions.md  # 코드리뷰·PR 정책
├── Releases/                      # 빌드된 exe + CHANGELOG
│   ├── CHANGELOG.md
│   └── 뚝딱비서_v0.0.N.exe
└── 세션_요약_YYYY-MM-DD.txt        # 개발 세션 노트 (보조 문서)
```

### 먼저 읽을 파일 (5개)

1. `pentong_chat.py` — GUI·세션 관리·Claude CLI 호출. 핵심은 `_call_claude`,
   `_execute_cli_once`, `_ensure_system_prompt_file`.
2. `pentong_system_prompt.txt` — Claude 의 런타임 행동 지침. ABSOLUTE RULE /
   세션 캐시 / 권한 / core 함수 / 루프 방지.
3. `core/excel_reader.py` (예) — Claude 가 import 해서 쓰는 검증된 헬퍼 패턴.
4. `_test_session.py` — 세션 코드 변경 후 반드시 돌려서 PASS 확인하는 회귀
   테스트. 6턴 시나리오.
5. `Releases/CHANGELOG.md` — 버전별 변경·버그 히스토리·폐기된 접근 기록.

## 실행/빌드

**개발 실행** (exe 빌드 불필요):
```
cd pentong
python pentong_chat.py
```

**exe 빌드**:
```
cd pentong
build.bat
```
→ `../Releases/뚝딱비서_v0.0.N.exe` 생성.

**의존성**: Python 3.12, pywin32, openpyxl, xlrd. 사용자 환경에선 앱이 자체
`setup_helper.py` 로 자동 설치.

## 테스트

**세션 회귀 테스트** (세션 관련 코드 수정 후 필수):
```
cd pentong
python _test_session.py
```
6턴 돌면서 (1) 파일 목록 → (2) xls 분석/양식 출력 → (3) "2번 스크립트"
컨텍스트 의존 → (4) 정밀 회수 → (5) 후속 작업 → (6) 최초 의도 회상.

통과 기준: 각 턴 stream-json 메시지 > 0, TURN 4 에서 `2024~25학년도
전체지원자.xls` 직답, TURN 6 에서 최초 요청 한 줄 요약.

소요 시간: 약 5~10 분 (Claude Sonnet 호출 비용 발생).

## 세션 관리 정책 (v0.0.14~)

**이 정책을 지키지 않으면 "대화 맥락 기억 못 함" 회귀가 재발합니다.**

### 절대 금지 (상세 근거는 docs/SESSION_HESITATION_DEBUG_LOG.md)

- **`-p` 비대화형 CLI 서브프로세스 반복** 구조로 회귀 금지. 이게 tool-use
  hesitation 의 근본 원인. 반드시 SDK 대화형 세션 사용.
- `--resume <session_id>` 사용 금지. CLI 2.1.114 에서 시간 무관 회귀.
- `--input-format stream-json` + stdin JSONL 로 멀티턴 주입 금지. 마지막 user
  메시지 비결정적 무시.
- user / system prompt 에 대화 이력 직렬화 주입 금지. SDK 가 자체 유지하므로
  불필요 + 중복 주입은 Claude 혼동 유발.
- retry prompt 에 "[시스템 알림]" 같은 메타 지시 워딩 금지. Claude 가
  prompt-injection 으로 의심해 더 강한 거부 유발.

### 현재 방식 (유일한 정답)

1. **Claude Agent SDK** (`claude-agent-sdk`) 기반. `-p` 비대화형 subprocess 를
   반복 호출하지 않고, `ClaudeSDKClient` 를 **백그라운드 asyncio loop 에서
   대화형 세션으로 장수 유지**.
2. SDK 가 내부적으로 Claude CLI 를 띄우고 같은 `~/.claude/` OAuth 토큰 사용 →
   로그인 플로우 / 인증은 **변화 없음**.
3. 세션 맥락은 SDK 가 자동 유지. 앱의 `self.history` 는 턴 수 카운트 +
   `~/.ddukddak/current_session.md` 기록용으로만 사용.
4. 작업 폴더 변경 시 SDK client disconnect → 다음 호출에서 새 cwd 로 재연결.
5. Claude 가 맥락이 부족하다고 느끼면 `current_session.md` 를 Read 로 읽어
   복원 가능 (시스템 프롬프트에 명시).
6. 중단 버튼 → `client.interrupt()`. 앱 종료 → `client.disconnect()` + loop stop.

### `ClaudeAgentOptions` (고정)

```python
ClaudeAgentOptions(
    model="haiku",
    system_prompt={
        "type": "preset", "preset": "claude_code",
        "append": <pentong_system_prompt.txt 내용>,
    },
    allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
    permission_mode="bypassPermissions",
    cwd=<work_dir>,
    add_dirs=[CONFIG_DIR],           # session_cache 접근용
    include_partial_messages=True,   # "쓰는 중" 피드백
    env={"DDUKDDAK_SESSION_CACHE": SESSION_CACHE_FILE, ...},
    cli_path=<claude CLI 경로>,
)
```

### 재시도 로직

첫 응답이 stream-json 0개 + plain-text > 30자 면 (Claude 가 도구 호출 전에
자연어로 끝낸 케이스) 같은 prompt 로 1회 자동 재시도. retry prompt 에 워딩
추가 금지 — prompt-injection 의심 유발.

## 가드레일

- **세션 관련 코드 수정 전 반드시 `_test_session.py` 통과 확인**. 가짜 PASS
  (응답 본문을 실제로 확인 안 하고 키워드 매치만) 를 피하려고 검증 로직에
  권한 거부 텍스트 / stream-json 0개 / 응답 길이 휴리스틱까지 포함됨.
- **`pentong_system_prompt.txt` 첫 줄의 `[ABSOLUTE RULE]` 섹션을 건드리지
  말 것.** 건드릴 필요가 생기면 같은 턴에 `_test_session.py` 재검증.
- **메모리 (`~/.claude/projects/.../memory/`) 의 `project_v0_0_14_*.md` 와
  `project_claude_cli_resume_bug.md` 를 읽고 작업 시작**. 과거 실패한 접근을
  다시 시도하지 않도록.
- 폐기된 접근을 문서에서 지우지 말 것. CHANGELOG 와 메모리에 "검토 후 폐기"
  로 명시해서 미래 회귀 방지.

## 릴리스 플로우

1. `pentong_chat.py` 의 `__version__` 문자열 bump.
2. `Releases/CHANGELOG.md` 에 새 버전 항목 추가 (잔여 한계·폐기한 대안까지
   정직하게).
3. `_test_session.py` 6턴 PASS 확인.
4. `build.bat` 실행 → `Releases/뚝딱비서_v0.0.N.exe`.
5. GitHub `FirstNotFists/Quick-Secretary-Release` 에 태그 + exe 업로드.
6. 기존 exe 는 그대로 두고 신규 exe 추가 (자동 업데이트가 최신 exe 찾음).

## 트러블슈팅

**증상: "이전 대화 기억 못함" / "권한이 필요합니다" plain-text 응답**
- 세션 정책 어긋났는지 확인 (위 `세션 관리 정책` 참고).
- `~/.ddukddak/system_prompt.txt` 열어서 이력 섹션이 실제로 들어가 있는지
  확인. 없으면 `_ensure_system_prompt_file` 버그.
- Claude CLI 버전 확인 (`claude --version`). 2.1.114 기준으로 개발됨.

**증상: 빌드 후 exe 실행 시 core 모듈 import 실패**
- `pentong_chat.spec` 의 `datas` 에 `core/` 포함됐는지 확인.
- `_ensure_core_modules` 가 `%USERPROFILE%/.ddukddak/core` 로 복사하는지
  로그 확인.

**증상: HWP COM 에서 무한 루프**
- `_preflight_hwp_check` 가 COM 등록 상태 체크. 미등록이면 즉시 에러 메시지
  띄우고 중단. 시스템 프롬프트의 "루프 방지 철칙" 이 Claude 를 3회 이내
  포기시킴.

**증상: 자동 업데이트 후 exe 가 재시작 안 됨**
- Windows Job Object 탈출 필요. `core/updater.py` 의 Popen 에
  `CREATE_BREAKAWAY_FROM_JOB` 있는지 확인 (v0.0.7~).

## 커밋 관례

- Conventional Commits 권장: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`,
  `test:`.
- 세션 관련 변경은 제목에 `[session]` 태그 추가 권장 (grep 용이).
- 폐기한 실험이 있으면 커밋 메시지 본문에 "폐기 이유" 한 줄 포함.
