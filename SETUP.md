# 뚝딱비서 — 새 PC 개발 환경 셋업

이 문서는 **다른 PC 에서 뚝딱비서 개발을 이어갈 때** 필요한 셋업 절차입니다.
사용자 실행 환경 셋업(`setup_helper.py`) 과는 다릅니다 — 그건 사용자가
exe 를 실행하면 자동으로 진행됩니다.

## 사전 요구 사항

| 도구 | 버전 | 용도 |
|---|---|---|
| Windows | 10 / 11 | 타깃 OS (pywin32 / HWP COM 필요) |
| Python | 3.12.x | 메인 런타임 |
| Node.js | 20+ | kordoc / rhwp HWP bridge |
| Git | 2.40+ | 소스 동기화 |
| Claude Code CLI | 2.1.114+ | AI 호출 백엔드 (SDK 가 내부적으로 사용) |
| 한컴오피스 한글 | 2020+ | HWP COM (사용자 실행 시) — 개발 PC 에선 선택 |

## 1단계 — 소스 클론

```powershell
cd C:\Users\<user>\Desktop
git clone <REPO_URL> _DDukDDak\뚝딱비서
cd _DDukDDak\뚝딱비서
```

> **주의**: 한글 폴더명을 그대로 두면 Google Drive 동기화 등에서 NFD
> (자모 분리) 로 깨질 수 있음. claude CLI 가 NFD cwd 에서 silent fail
> 하는 알려진 이슈가 있어, 깨졌다면 탐색기에서 우클릭 → 이름 바꾸기 →
> 같은 이름 재입력으로 NFC 정규화 필요. 자세한 건 v0.0.25 CHANGELOG.

## 2단계 — Python 의존성

```powershell
cd pentong
python -m pip install -r requirements.txt
```

핵심 패키지:
- `claude-agent-sdk` — 백그라운드 Sonnet 세션 유지
- `anthropic` — SDK 의 transitive 의존
- `openpyxl` / `xlrd` — 엑셀 R/W
- `PyMuPDF` — PDF 추출
- `pywin32` — HWP COM
- `pyinstaller` — exe 빌드

## 3단계 — Node 의존성 (HWP bridge)

```powershell
cd pentong\kordoc_bridge
npm install
cd ..\rhwp_bridge
npm install
```

> `node_modules/` 와 `package-lock.json` 은 .gitignore 됨 — 새 PC 마다
> `npm install` 필요. `package.json` 만 commit 되어 있음.

## 4단계 — Claude Code CLI 설치 + 인증

### 4-a. CLI 설치
```powershell
npm install -g @anthropic-ai/claude-code
claude --version
```

### 4-b. OAuth 인증 (브라우저)
```powershell
claude /login
```

> SDK 는 별도 인증 없이 같은 `~/.claude/` 토큰을 자동 사용합니다.

## 5단계 — 동작 확인

### 5-a. 개발 모드 실행 (exe 빌드 불필요)
```powershell
cd pentong
python pentong_chat.py
```

GUI 가 뜨고 "뚝딱비서 v0.0.25" 타이틀 + 채팅창이 보이면 정상.

### 5-b. 세션 회귀 테스트 (세션 관련 코드 수정 후 필수)
```powershell
cd pentong
python _test_session.py
```

6턴 시나리오. 5~10분 소요. PASS 라인이 마지막에 나와야 함.
실패 케이스는 `pentong/CLAUDE.md` 의 트러블슈팅 섹션 참고.

## 6단계 — exe 빌드 (선택)

```powershell
cd pentong
.\build.bat
```

산출물: `Releases\뚝딱비서_v0.0.25.exe`.

## 7단계 — Claude Code 메모리 동기화 (선택)

이 프로젝트는 Claude Code 의 자동 메모리에 컨텍스트를 쌓아왔습니다.
메모리 디렉토리:

```
%USERPROFILE%\.claude\projects\C--Users-user-Desktop--DDukDDak\memory\
```

새 PC 에 동일한 작업 컨텍스트가 필요하면 위 폴더를 별도로 복사하세요.
**OAuth 토큰**(`~/.claude/.credentials*`) 은 보안상 복사 금지 — 각 PC 에서
`claude /login` 새로 진행.

## 트러블슈팅

### "이전 대화 기억 못함" / 권한 거부 plain-text 응답
- `pentong/CLAUDE.md` 의 "세션 관리 정책 (v0.0.14~)" 섹션 + 트러블슈팅 참고.
- 폐기된 접근들이 박제되어 있으니 재시도 금지.

### claude CLI silent fail (rc=0, stdout 비어있음)
- cwd 한글 폴더가 NFD 일 가능성 — 위 1단계 주의사항 참고.
- 진단 로그: `%USERPROFILE%\.ddukddak\logs\last_silent_fail.log`

### kordoc / rhwp Node 호출 실패
- Node.js 가 PATH 에 잡혀야 합니다 (`where node`).
- `npm install` 을 두 bridge 폴더 각각에서 실행했는지 확인.
- HWP COM 은 한컴오피스가 정식 설치된 PC 에서만 동작.

### HWP COM 미등록
- 한컴오피스 한글 정식 설치 + 1회 실행 필요.
- 미등록 PC 는 `_preflight_hwp_check` 가 즉시 에러 띄우고 중단.

## 다음 작업 (resume 메모리 발췌, 2026-05-07 기준)

1. **양식 지정 권한 거부 fix** — HIGH 우선순위
   - `pentong_chat.py` 의 `_get_template_prompt()` 가 외부 TEMPLATES_DIR
     를 prompt 에 append → invariants "외부 금지" 발동 → hesitation
     swallow → 사용자에 hang 으로 보임.
   - fix: `claude` cmd 에 `--add-dir <TEMPLATES_DIR>` 추가 +
     `_invariants.md` 에 예외 명시.
2. kordoc Stage 1 통합 — `core/hwp_kordoc.py` Python wrapper.
3. 세션 다중화 — `~/.ddukddak/sessions/<날짜_제목>.md`.

자세한 컨텍스트는 Claude Code 메모리 `project_ddukddak_v0_0_25.md` +
`project_ddukddak_resume_2026_05_07.md` 참고.
