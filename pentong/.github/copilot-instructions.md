# 뚝딱비서 — 코드 리뷰·PR 작업 지침

이 문서는 Claude / Copilot / 기타 AI 코드 리뷰어가 이 프로젝트의 PR 을
검토할 때 따라야 하는 정책입니다. 개발 온보딩은 `../CLAUDE.md` 참고.

## 환경 제약

- Windows 11 전용 프로젝트 (Python tkinter + pywin32 + HWP COM).
- Claude Code CLI 2.1.114 기준으로 개발됨. CLI 버전 올라가면 세션 정책
  회귀 가능성 매번 점검 (`_test_session.py`).
- 사용자 환경은 Python/Git/Node 미설치 가정. `core/setup_helper.py` 가 자동
  설치 책임.

## PR 제목 규칙 (Conventional Commits)

허용 prefix:
- `feat:` — 새 기능
- `fix:` — 버그 수정
- `refactor:` — 기능 변화 없는 구조 개선
- `docs:` — 문서만 변경
- `test:` — 테스트만 추가/수정
- `chore:` — 빌드·릴리스·의존성 변경

세션 관련 변경엔 본문에 `[session]` 태그. 폐기한 실험은 "폐기 이유" 포함.

## 리뷰 우선순위

1. **Correctness** — 세션 유지, HWP preflight, 권한 플로우, 자동 업데이트
2. **회귀 안전망** — `_test_session.py` PASS 여부. 변경이 세션 로직이면 필수
3. **사용자 환경 오염** — 작업 폴더에 쓰레기 파일 안 남기는지
4. **에러 메시지 한국어 자연스러움** — 타깃 사용자가 비개발자
5. **보안** — 사용자 홈 외부 경로 쓰기 금지, 임시파일은 `%TEMP%` 에만

## 검토 포인트

### 세션 코드 변경

- `self.history` append 조건 (`final_result_text and not self._user_aborted`)
  이 여전히 지켜지는가.
- `--resume` / `--input-format stream-json` / user prompt 이력 직렬화 중
  어느 하나라도 재등장하면 즉시 차단. 모두 검증 후 폐기된 접근 (CHANGELOG
  v0.0.14 참고).
- `_ensure_system_prompt_file` 이 매 호출마다 임시 파일을 **매번 새로** 쓰는지
  (history 갱신 반영).
- `~/.ddukddak/current_session.md` append 는 turn 성공 시에만 발생하는지.
  실패/중단 턴이 캐시 오염시키면 Claude 의 self-managed memory fallback 이
  깨짐.

### HWP COM 작업

- `_preflight_hwp_check` 가 여전히 내용 편집 요청에만 걸리고 파일시스템
  작업(목록/삭제) 은 skip 하는지 (v0.0.13 수정 맥락).
- 시스템 프롬프트의 "루프 방지 철칙" 이 Claude 에게 3회 이내 포기하도록
  명령하는지.

### 자동 업데이트

- `core/updater.py` Popen 에 `CREATE_BREAKAWAY_FROM_JOB` 유지 (v0.0.7~).
- `pentong_chat.py _apply_update` 에서 `os._exit(0)` 유지 (v0.0.9~,
  `sys.exit` 는 tkinter after 콜백에서 삼켜짐).
- 업데이트 후 `.bak` 자동 삭제 로직 (v0.0.11~).

## 코멘트하지 말 것 (Do NOT comment on)

- `_call_claude` 의 stream-json 파싱 루프 스타일 (if/elif 체인) — 의도적
  평탄 구조, 리팩터 제안 사절.
- 시스템 프롬프트의 한국어 문장 톤 — 실사용자 대상으로 다듬은 결과물,
  "영어로 바꿔라" / "더 간결하게" 제안 금지.
- `pentong_system_prompt.txt` 의 `[ABSOLUTE RULE]` 영문 섹션 — Claude 의
  instruction following 특성 고려해 literal 명령 패턴. 의역/축약 금지.
- CHANGELOG 의 "폐기된 대안" 섹션 — 미래 회귀 방지 목적으로 일부러 남김,
  "쓰지 않는데 왜 남기냐" 제안 금지.
- exe 빌드 파일 크기 — PyInstaller + tkinter + pywin32 번들 결과.

## 자주 하는 실수 (bug-causing patterns)

### 세션 이력 오염

```python
# BAD — 실패 턴도 이력에 들어가서 다음 턴 Claude 가 혼동
self.history.append({"role": "user", "content": user_msg})
if got_result:
    self.history.append({"role": "assistant", "content": result})

# GOOD — 성공 쌍만 append
if final_result_text and not self._user_aborted:
    self.history.append({"role": "user", "content": full_prompt})
    self.history.append({"role": "assistant", "content": final_result_text})
```

### 시스템 프롬프트 파일 경로

```python
# BAD — PyInstaller exe 내부 경로(_MEIPASS) 를 Claude CLI 서브프로세스에 전달
# → 서브프로세스가 접근 못해서 Read 실패
cmd = [..., "--append-system-prompt-file", SYSTEM_PROMPT_FILE]

# GOOD — 사용자 홈에 안정 경로로 복사한 뒤 전달
prompt_file = self._ensure_system_prompt_file()
cmd = [..., "--append-system-prompt-file", prompt_file]
```

### `--resume` 유혹

```python
# BAD — CLI 브랜치 버그로 첫 재개 호출이 'default' 권한 모드로 리셋
if self.session_id:
    cmd.extend(["--resume", self.session_id])

# GOOD — --resume 자체를 안 씀. history 는 system prompt 주입 + 캐시 파일.
#  (v0.0.14 에서 session_id 필드 자체 제거됨)
```

## 에러 핸들링 규칙

- 내부 에러 (`core/` 모듈) 는 traceback 을 영문 그대로 사용자에게 노출 금지.
  한국어 한두 문장으로 원인 + 해결 힌트 번역해서 제시.
- 예외 삼키기 (`except Exception: pass`) 는 외부 시스템 경계(`taskkill`,
  임시파일 삭제, 레지스트리 조회) 에만 허용. 내부 로직에선 금지.
- 로그는 `%TEMP%\_ddukddak_*.log` 로만. 작업 폴더에 남기지 말 것.

## 플랫폼-특화 코드

- Windows 전용 API (pywin32, winreg, `subprocess.CREATE_NO_WINDOW`) 는
  `if sys.platform == "win32":` 로 가드.
- 한글 경로는 PowerShell `-LiteralPath` 사용 (cmd `move` 는 한글 깨짐, v0.0.3
  수정 이력 참고).
- 한국어 stdout 은 `sys.stdout.reconfigure(encoding="utf-8")`.
