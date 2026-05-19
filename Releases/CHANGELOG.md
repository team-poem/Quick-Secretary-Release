# 뚝딱비서 변경 이력

## v0.0.25 — 2026-05-07 (마크다운 하네스 파이프라인 도입 + NFD 폴더 silent fail 진단)

### 마크다운 하네스 파이프라인 (Phase 1 토대)

`pentong_system_prompt.txt` 단일 7KB 시스템 프롬프트에서 → **합성 25KB** 로 확장.
`prompts/skills/_*.md` 토대 모듈 5개를 frontmatter strip 후 자동 append:

- **`_invariants.md`** (4KB) — 13개 hard rule. 권한 묻기 / 세션 미참조 / COM 금지 / 작업 폴더 경계 / %TEMP% 강제 / 단일 스크립트 수정 / 3회 룰 / 결과 파일명 / 마크다운 표 강제 / 인코딩 / 한국어 에러 / 결과 보고 형식 / 호스트 강제 메커니즘
- **`_index.md`** — skill 라우팅 테이블 (Phase 2/6 의 trigger 기반 skill 등록 위치)
- **`_session.md`** — 세션 캐시 강제 참조 절차 (미준수 사례 "이전 대화 이력 없다" 차단)
- **`_output_contract.md`** — 출력 포맷 계약 (마크다운 표, 인코딩, verdict frontmatter)
- **`_loop_guard.md`** — 루프 방지 + 자동 재시도 (Q2 a 정책: 재시도 1-2회 사용자에 안 보이게)

호스트(`pentong_chat.py`):
- `_load_system_prompt` 가 base + 5 skill 자동 합성
- `_ensure_system_prompt_file` 가 합성 결과를 `~/.ddukddak/system_prompt.txt` 에 저장
- PyInstaller spec 의 datas 에 `prompts/` 추가

### verdict / verify_report 카드 렌더

Claude 응답에 YAML frontmatter (`verdict: stop` 또는 `report: verify`) 가 붙으면 호스트가 카드로 분기 렌더. PyYAML 의존성 회피 위해 미니 YAML 파서 (`_parse_minimal_yaml`) 자체 구현 — verdict / verify_report 형식만 처리.

부류 아이콘:
- 🔧 `external_blocker` — 사용자 행동 필요
- 🚫 `system_limit` — 미지원 명시
- ❓ `unclear_intent` — 명확화 질문

### 권한·맥락 미준수 패턴 차단 강화

`_HESITATION_MARKERS` 확장 (미준수 사례 1번 외에 2번 "이전 대화 이력 없다" 류도 추가):
- 권한 묻기 12종
- 세션 미참조 6종

호스트가 응답을 chat 에 박기 직전에 패턴 매칭 후 hesitation 의심 시 **사용자 UI 에 노출 없이 즉시 retry**. 기존 v0.0.24 의 retry 후 안내 메시지 제거 (Q2 a 결정).

### NFD 폴더 silent fail 진단 + 안내

Google Drive 의 zip 다운로드가 한글 폴더명을 macOS 스타일 NFD (자모 분리) 로 저장하는 알려진 문제 — claude CLI (claude.cmd → node) 가 NFD cwd 받으면 silent fail (rc=0, stdout/stderr 0). 실측 확인:
- `cmd /c cd` + NFD cwd: 정상 동작
- `claude.cmd` + NFD cwd: silent fail
- `\\?\` prefix: cmd 가 거부
- `GetShortPathNameW`: NFD path 인식 못 함

호스트가 우회 불가하므로 **사전 감지 후 사용자에게 우회 안내** (탐색기 우클릭 → 이름 바꾸기 → 같은 이름 재입력 → NFC 자동 정규화). `_call_claude` 시작부에 NFD component 검증 추가.

### Silent fail 진단 로깅

`~/.ddukddak/logs/last_silent_fail.log` 신규 — silent failure 발생 시:
- timestamp, returncode
- work_dir / cwd_for_popen 비교
- claude_cmd / prompt_file 존재 여부
- full_prompt 길이, env PATH 일부
- cmd, stderr (2KB), stdout 라인 (30줄)

다음 silent fail 발생 시 즉시 원인 진단 가능.

### 시드 skill 모듈 1개 (Phase 2)

- **`xlsx_pdf_match.md`** — legacy v1→v4 임시 스크립트 별파일 사례 박제. PDF 추출 시 `extract_tables` 페이지마다 호출 강제, 교과목명 NFC+공백제거 정규화, 매칭률 < 0.3 시 verdict.

### 알려진 v0.0.25 한계

- kordoc bridge (HWP/HWPX 신규 작성·병합·양식채우기·신구대조표) 인프라는 PoC 통과했으나 호스트 통합 미완. 다음 patch 또는 v0.0.26 에서 진행.
- HWP/HWPX 다중 병합 (`core.hwp_merge.merge_hwp_files`) 결과가 한컴에서 안 열리는 rhwp 한계는 v0.0.25 에서 미해결. kordoc 통합 후 해결 예정.

---

## v0.0.24.1 — 2026-04-22 (Advisor Pattern 테스트 — Plan-and-Execute)

v0.0.24 동일 + **항시 Sonnet advisor** 로 실행 계획 수립 후 Haiku executor 실행.
사용자 테스트 전용 임시 빌드. 소스에는 영구 반영 안 함.

### 동작
```
사용자 메시지
    ↓
[Advisor: Sonnet, 도구 없음]  — "실행 계획" 텍스트만 생성
    ↓
[Executor: Haiku, 도구 허용]  — 계획 prefix + 원본 메시지 받아 실제 수행
    ↓
결과
```

### 기대 효과
- 복잡 다단계 요청에서 Haiku hesitation 사전 차단 (이미 구체 계획 받음)
- 업계 표준 Plan-and-Execute 패턴 (92% 완료율 / 3.6x 속도 벤치마크)

### 트레이드오프
- 매 메시지마다 Sonnet 호출 추가 → 비용 ↑, 대기시간 +3~5초
- 단순 요청 (파일 목록 등) 도 Advisor 거침 — 과투자

### UI
- `💡 Advisor(Sonnet) 가 실행 계획 수립 중...` (Sonnet 단계)
- `📋 [실행 계획] 1. ... 2. ... 3. ...` (info)
- 이후 기존 Haiku 실행 표시

### 테스트 포인트
- 복잡 엑셀 요청에서 hesitation 발생 빈도 감소 확인
- Advisor 계획 품질 확인 (Sonnet 이 정확한 단계 쪼개는지)
- 비용 / 대기시간 체감

---

## v0.0.24 — 2026-04-22 (BUG-007 — 에러 진단 개선 + cwd 유효성 체크)

### 배경
사용자 증상: `❌ 오류: [WinError 267] 디렉터리 이름이 올바르지 않습니다` —
어느 라인 / 어떤 경로가 문제인지 메시지에 안 나와서 원인 파악 불가능.
가장 의심: `subprocess.Popen(cwd=self.work_dir)` 가 유효하지 않은 디렉터리
로 호출될 때 발생. 폴더 삭제/이름 변경/네트워크 드라이브 끊김 등.

### 수정
- **`_call_claude` 시작부에 `work_dir` 유효성 pre-check**. `os.path.isdir()`
  통과 안 하면 즉시 명확한 에러 메시지 + 해결 안내 (작업 폴더 재선택). Popen
  이 불친절한 WinError 던지기 전에 차단.
- **`except Exception` 에서 traceback 마지막 6줄 포함 송신**. 다음에 비슷한
  증상 나와도 어느 Python 라인에서 난 건지 즉시 확인 가능.
- **`_change_dir` 에서 선택 경로 재검증**. filedialog 가 내준 경로라도 그 사이
  삭제될 수 있음.

### 효과
- WinError 267 같은 알쏭달쏭한 에러가 재발해도 메시지가 "어느 디렉터리가 왜
  문제인지" 즉시 보여줌.
- 작업 폴더 잘못 설정된 상태에서 Claude 호출 자체를 차단 → 불필요한 실행 비용
  / Claude 가 엉뚱하게 해석 시도하는 시간 낭비 방지.

---

## v0.0.23.1 — 2026-04-22 (sonnet 모델 비교 빌드)

v0.0.23 과 동일. `_call_claude` cmd 의 `--model haiku` 를 `--model sonnet`
으로만 교체. 동일 시나리오에서 haiku vs sonnet 성능/정확도/hesitation 빈도
비교용. 사용자가 한 대에 v0.0.23 (haiku), 다른 대에 v0.0.23.1 (sonnet) 깔고
같은 작업 시켜 체감 비교.

### 모델 차이 (참고)
- **haiku 4.5**: 빠름(응답 1~3s), 저비용, 도구 호출 hesitation 약간 덜함
- **sonnet 4.6/4.7**: 느림(응답 3~10s), 비용 3~5배, 복잡 추론 정확도 높음,
  도구 호출 hesitation 이 haiku 보다 강하게 발동할 수도 있음 (보수성 ↑)

비교 후 `pentong_chat.py` 의 `"--model"` 플래그 값을 고정하면 됨.

---

## v0.0.23 — 2026-04-22 (BUG-006 해결 — hesitation 자동 리셋 재시도)

v0.0.21 base 에서 이어진 릴리스. v0.0.22 (python 캐싱) 는 배포 제외, 그 변경
미적용.

### 배경
Claude 가 첫 턴 복잡 작업 요청 앞에서 "권한 승인해 주세요" 자연어로 끝내는
hesitation 현상이 v0.0.21 까지 남아있었음. 사용자 실증: **"대화 초기화" 버튼
누르고 같은 메시지 재입력하면 바로 성공** — hesitation 이 확률적이고 첫 턴
에만 발생하며, 맥락을 완전히 지운 후 재시도는 새 주사위.

### 수정 — hesitation 감지 → 자동 리셋 + 동일 prompt 재전송
사용자가 수동으로 하던 "대화 초기화 + 재입력" 을 앱이 자동으로 수행.

발동 조건 (모두 AND):
1. **첫 턴** (`self.history` 가 비어있었음)
2. **도구 호출 0개** (tool_use 블록 하나도 없었음)
3. **응답에 hesitation 키워드** (`권한 승인`, `권한이 필요`, `허용해 주`, `승인해 주`, `approval`, `permission` 등)
4. 이미 재시도 경로가 아님 (무한루프 방지)

동작:
- UI 에 "Claude 가 권한 확인 응답으로 끝났습니다. 세션 초기화 후 같은 요청 자동 재시도합니다..." info 표시
- `self.history = []` + `_reset_session_cache()` + `_seed_session_cache_if_empty()`
- `_call_claude(prompt, _hesitation_retry=True)` 재귀 호출 1회
- 재시도 결과가 실제 응답으로 표시됨 (사용자 무개입)

### 과거 retry 실패와의 차이
- **이전 retry** (v0.0.14~): 같은 세션에서 워딩 강화 붙여 재시도 → Claude 가
  prompt-injection 의심해 더 강한 거부.
- **이번 전략**: 세션 완전 리셋 + **원본 prompt 그대로** 재전송. 워딩 추가
  없음. Claude 에게는 완전히 첫 턴이라 이전 hesitation 응답이 맥락에 없음.
  → prompt-injection 의심 트리거 없음.

### 한계
- 재시도도 hesitation 이면 그대로 사용자에게 노출 (1회만 재시도)
- 재시도 시 사용자 대기 시간 2배 (첫 실패 + 재시도)
- 첫 턴에서만 발동 — 이어지는 턴 hesitation 은 다른 경로 필요 (희귀 케이스)

---

## v0.0.21 — 2026-04-22 (BUG 백로그 일괄 해결)

4건의 누적 BUG 을 한 번에 처리.

### BUG-003 (최우선) — HWP 표 추출 기능 추가
사용자가 "표 X 의 데이터로 표 Y 재구성" 요청 시 `core.hwp_reader` 가 문단
텍스트만 주고 **표 구조는 없어서** Claude 가 "core 로 불가능" 판단 → COM
fallback 으로 `win32com.client.Dispatch` 시도 → 실패 → "엑셀로 내보내세요"
같은 우회 제안.

수정:
- `rhwp_bridge.js` 에 operation 3개 추가: `list_tables`, `extract_table`,
  `read_tables`. rhwp 의 `getTableDimensions`, `getCellInfo`, `getTextInCell`
  API 활용.
- `core/hwp_reader.py` 에 Python 래퍼 3개 추가: `list_tables(path)`,
  `extract_table(path, index=N)`, `read_tables(path)`.
- system_prompt 에 표 추출 API 소개 + "win32com / COM 절대 시도 금지" 재강조.
- 검증: 실제 HWP 파일로 540개 표 탐지, 2D 셀 데이터 정확 추출 확인.

### BUG-001 — Microsoft Store Python Install Manager 창 자꾸 뜸
Windows App Execution Alias 의 `python.exe` shim 이 Store Installer 로
리다이렉트. 시스템 python 설치돼 있어도 PATH 우선순위로 shim 이 먼저 잡힘.

수정:
- `_call_claude` 의 env["PATH"] 구성 시:
  - `Microsoft\WindowsApps` 디렉토리 **제거** — python alias shim 차단.
  - `_find_python()` 이 찾은 실제 python 디렉토리를 PATH **최상위에 prepend**.
- Claude CLI 서브프로세스 / 그 하위의 python / node 까지 env 상속되어 연쇄
  적용.

### BUG-002 — 새 PC 대화 맥락 이중 공백
`~/.claude/projects/` (CLI 세션) + `~/.ddukddak/current_session.md` (앱 캐시)
둘 다 비어있어서 새 PC 에선 맥락 복원 fallback 없음.

수정:
- `_seed_session_cache_if_empty()` 신설 — 앱 시작 시 세션 캐시가 없으면
  **기본 시드** 생성. 뚝딱비서 정체 / 권한 정책 / core 모듈 사용법 등 앱
  환경 정보 사전 기록.
- Claude 가 맥락 복원 Read 시 빈 파일이 아니라 기본 컨텍스트가 즉시 주어짐.
- `_append_to_session_cache` 도 시드 호출 먼저 → 첫 턴 저장 시 시드 + 턴 모두
  기록.

### BUG-004 — `_ensure_rhwp_bridge` 실패 조용함
번들 해제가 실패해도 조용히 넘어가서 HWP 작업 중에야 "Node.js bridge 없음"
같은 애매한 에러 발생.

수정:
- `_prepare_bundled_assets` 에서 core / rhwp_bridge / session_cache 각
  단계별 실패 감지. exe (frozen) 환경에서 디렉토리/파일 누락 확인.
- 실패 건이 있으면 앱 UI 에 `error` 큐로 "초기화 경고" 명시. 사용자가 즉시
  설정 창 재설치 진행 가능.

### 유지
v0.0.20 의 `-p` subprocess + `--continue` 방식, rhwp 기반 HWP 엔진, 번들
자동 해제 (v0.0.19), COM 시스템 프롬프트 금지 (v0.0.20) 모두 유지.

---

## v0.0.20 — 2026-04-22 (COM 경로 원천 차단 + `hwp_merge` rhwp 전환)

### 배경
v0.0.19 에서 사용자가 엑셀 작업 중 관찰: Claude 가 `win32com.client.Dispatch(
"Excel.Application")` 같은 COM 경로를 계속 시도. 엑셀은 **원래부터 `openpyxl`/
`xlrd` 기반이라 COM 필요 없음**인데 Claude 가 시스템 프롬프트의 옛 가이드
+ `core.hwp_merge` 가 여전히 `win32com` 기반이라는 사실로 인해 COM 을 탐색.

### 수정 1 — 시스템 프롬프트에서 COM 지침 전면 제거
기존에 남아있던:
- `[HWP 자동화 — 한컴오피스 2022 특이사항]` 섹션 (`XHwpWindows.Item(0).Visible`,
  `XHwpDocuments.Add(isTab=True)` 같은 COM 코드 예시)
- `[fallback]` 의 "직접 openpyxl/xlrd/**pywin32** 로 작업" 권장 — pywin32 제거
- `[절대 금지 — HWP COM 자동화 실패 시]` 섹션 전체 (`regsvr32 HwpCtrl.ocx`,
  `HwpFrame.HwpObject` 등 COM 경로 언급)

→ 전부 삭제. 대신 **`[NEVER USE COM AUTOMATION — HARD RULE]`** 최상단 신설.
`win32com.client.Dispatch`, `HWPFrame.HwpObject`, `Excel.Application`, `pyhwpx`,
`pywin32` 등 구체 이름을 적어 **절대 사용 금지** 명시. Claude 가 답변에 이
단어들을 쓰는 것도 금지.

### 수정 2 — `core.hwp_merge` rhwp 전환
마지막까지 win32com 남아있던 HWP 병합 모듈. Claude 가 두 HWP 합치려고 이
모듈을 import 하면 `win32com.client.Dispatch("HWPFrame.HwpObject")` 코드를
보고 COM 경로를 시도하는 트리거였음.

새 구현: `read_all_paragraphs` (rhwp) + `insert_paragraphs` (rhwp) 조합으로
**텍스트 수준 병합**. 첫 파일을 base 로 복사 후 나머지 파일 문단을 append.
서식·표·이미지는 병합 안 되지만 텍스트 취합 용도로 충분. COM 의존 0.

### 효과
- Claude 가 `from core.hwp_merge import merge_hwp_files` 를 봐도 COM 코드
  전혀 보이지 않음 → 저수준 COM 시도 충동 제거
- Claude 응답에서 "HWP COM 자동화가 차단되어 있네요" 류 메시지 사라질 것
- 엑셀 작업 시 `Excel.Application` 경로 시도 없어짐

### 유지
- SDK 롤백 (v0.0.18), `-p` + `--continue` 방식 (v0.0.18), 번들 자동 해제
  (v0.0.19), rhwp WASM HWP 엔진 (v0.0.17), preflight 제거 (v0.0.15).

### `hwp_merge` 의 알려진 한계
- 서식 (폰트/여백/표/이미지) 병합 불가 — rhwp 의 Document merge API 업스트림
  이슈. 현재는 텍스트만 이어 붙임.
- 복잡한 레이아웃 병합이 필요하면 사용자가 수동 작업 안내 필요.

---

## v0.0.19 — 2026-04-22 (번들 assets 즉시 해제 + 재사용 가드)

### 배경
v0.0.18 까지 번들된 `core/` 와 `rhwp_bridge/` 는 사용자 첫 메시지에서
`_call_claude` 가 호출될 때 비로소 `~/.ddukddak/` 로 풀림. 새 PC 에서
첫 메시지 처리 도중 copytree 실행 → 타이밍 문제 + 매 호출마다 rmtree
+ copytree 반복으로 AV 스캔 반복 + 불필요한 I/O.

### 수정
- **앱 실행 즉시 백그라운드로 번들 해제** — `run()` 에서 mainloop 진입
  전에 `_prepare_bundled_assets` 스레드 가동. 사용자가 첫 메시지 보낼
  때는 이미 `~/.ddukddak/core/` 와 `~/.ddukddak/rhwp_bridge/` 준비됨.
- **재사용 가드 (`_assets_prepared` set)** — 프로세스 당 1회만 copytree.
  이후 호출은 존재 확인만. AV 반복 스캔 / I/O 오버헤드 제거.
- 예외 발생 시 다음 `_call_claude` 호출에서 자연스럽게 재시도.

### 효과 (새 PC 배포 시)
- 첫 HWP 작업 지연 감소 (앱 시작 후 몇 초 뒤엔 자산 준비 완료)
- 매 메시지마다 발생하던 3.9MB copytree + AV 스캔 없어짐
- `~/.ddukddak/rhwp_bridge/node_modules/@rhwp/core/rhwp_bg.wasm` 이 항상
  존재하므로 첫 HWP 관련 bash 호출에서 ModuleNotFoundError / "bridge 없음"
  에러 가능성 제거

### 유지
- SDK 롤백 상태 (v0.0.18), rhwp HWP 엔진, preflight 제거 상태 전부 동일.
- HWP 저장은 HWPX 자동 폴백 (rhwp 이슈 #197 미완).

---

## v0.0.18 — 2026-04-22 (SDK 롤백 + rhwp 유지 — `-p` subprocess 복귀)

### 배경
v0.0.14 ~ v0.0.17 의 `claude-agent-sdk` 기반 대화형 세션 방식이 일부 환경
(특히 테스트 PC) 에서 `Control request timeout: initialize` 를 반복 발생.
SDK 내부 control protocol handshake 가 stuck 되는 문제로 원격 진단 불가능.
한편 HWP 권한 문제는 v0.0.17 의 `@rhwp/core` 전환으로 근본 해결됐으므로,
SDK 로 우회하려 했던 "첫 도구 호출 hesitation" 이슈도 **COM 호출 자체가
사라진 지금은 체감 영향이 훨씬 적음**.

### 수정 — SDK 제거, v0.0.13 스타일 `-p` 서브프로세스로 복귀
- `claude-agent-sdk` 관련 모든 코드 제거 (`_sdk_connect`, `_sdk_send`,
  `_start_sdk_loop`, `_emit_tool_use`, `_dump_env_diagnostics`,
  `_prepare_sdk_for_new_dir`, 관련 필드/락/loop 전체).
- `_call_claude` 를 v0.0.13 스타일 `subprocess.Popen(["claude", "-p", ...])`
  + stream-json 파싱으로 복귀. `--continue` 플래그로 세션 연속성 유지.
- `_stop` 도 subprocess kill 방식으로 복원.
- `asyncio` import 제거. PyInstaller spec 의 SDK hiddenimports 삭제.

### 유지되는 것
- **`@rhwp/core` HWP 엔진**: `core/hwp_*.py` 는 그대로 Node.js bridge 로
  HWP 처리. COM 의존성 0 상태 유지.
- **`rhwp_bridge/` 번들 (3.9MB)**: PyInstaller 에 포함 + `_ensure_rhwp_bridge`
  로 첫 실행 시 `~/.ddukddak/rhwp_bridge/` 로 풀림.
- **HWP preflight 제거 상태**: `_needs_hwp_com`, `_preflight_hwp_check`
  없음. 한컴 OCX 미등록 PC 에서도 HWP 작업 가능.
- session_cache (`~/.ddukddak/current_session.md`), history 누적, 작업 폴더
  변경 시 리셋 등 UI 로직은 그대로.

### 트레이드오프
- SDK 의 대화형 세션에서 누렸던 "Claude 의 도구 호출 hesitation 감소" 효과는
  사라짐. 단 HWP COM 호출이 없어진 지금은 Claude 가 Bash/Read/Write 만 쓰면
  되고, 이들은 `-p` 모드에서도 비교적 자연스럽게 사용.
- `-p` + `--continue` 의 CLI 2.1.114 브랜치 버그는 여전히 존재 가능 — 첫 재개
  호출에서 권한 모드 리셋될 수 있음. 증상 재현 시 retry 또는 warmup 검토.

### 이번 릴리스의 목적
**성능 비교용**. v0.0.13 의 단순한 호출 방식 + v0.0.17 의 rhwp HWP 엔진 조합
이 실사용에서 어떻게 느껴지는지 실측. SDK 재도입이 필요한 증상이 재발하면
사용자 보고 기반으로 다시 판단.

---

## v0.0.17 — 2026-04-22 (HWP COM 의존성 제거 — @rhwp/core 전환)

### 배경
v0.0.16 까지 HWP 처리는 `win32com.client.Dispatch("HWPFrame.HwpObject")` 기반.
한컴오피스 설치 + HwpCtrl.ocx 레지스트리 등록이 필수여서 테스트 PC 마다
OCX 미등록으로 HWP 작업 차단되는 문제 반복 발생. preflight 로 감지해서
차단했지만 근본 해결 아니었음.

### 전환 — Rust+WASM 기반 오픈소스 엔진 `@rhwp/core`
[rhwp](https://github.com/edwardkim/rhwp) (edwardkim 작) 의 `@rhwp/core`
WASM 패키지로 전환. Node.js 에서 WASM 실행해 HWP 파싱/편집/저장. COM
의존성 0, 한컴 설치 여부 무관, 어떤 Windows PC 에서도 동작.

### 구현
- `pentong/rhwp_bridge/rhwp_bridge.js` 신설 — Python ↔ @rhwp/core 브리지
  (Node.js ESM). operation 별 entry point 제공: `read_full_text`,
  `read_all_paragraphs`, `get_document_info`, `find_text`, `find_and_replace`,
  `batch_replace`, `insert_text_at_end`, `insert_text_at_beginning`,
  `insert_paragraphs`.
- `core/hwp_reader.py` / `hwp_replace.py` / `hwp_insert.py` 전체 재작성 —
  win32com 대신 subprocess 로 `node rhwp_bridge.js <op>` 호출.
- `core/hwp_section.py` / `hwp_template.py` — `read_all_paragraphs` +
  `batch_replace` 위 순수 Python 이라 자동으로 rhwp 기반으로 동작.
- `pentong_chat.py` 의 `_needs_hwp_com`, `_preflight_hwp_check`, HWP 토큰
  리스트 4종 전부 **제거** (더 이상 COM 요구 판정 불필요).
- `_ensure_rhwp_bridge()` 신설 — 첫 실행 시 번들된 bridge 를
  `~/.ddukddak/rhwp_bridge/` 로 풀어놓음. Node.js 가 WASM 실행.
- PyInstaller spec 에 `rhwp_bridge/` 디렉토리 추가 (+ 3.9MB).

### 검증 (개발 모드)
- `read_full_text` — 1.2MB HWP 파일 124만자 추출 성공
- `find_and_replace` — "동서대학교" → "테스트대학교" 122회 치환 + 재읽기 검증 일치
- `insert_text_at_end` — 재읽기 검증 True
- `detect_sections` — 762개 섹션 탐지 정확
- COM 의존성 0 — win32com 호출 0회

### 알려진 한계
- HWP 바이너리 직접 저장이 rhwp 이슈 [#197](https://github.com/edwardkim/rhwp/issues/197)
  에서 미완료 — 편집본 저장 시 **HWPX 로 자동 폴백** (`.hwp` 요청 → `.hwpx`
  로 저장). HWPX 는 한컴/rhwp 뷰어 둘 다 열 수 있어 실사용 문제 없음.
- 대소문자 무시 (`ignore_case`), 온전한 단어 매칭 (`whole_word`) 는 rhwp
  replaceText 레벨에선 미지원. 현재는 인자만 받고 동작 안 함.
- 병합 (`hwp_merge.merge_hwp_files`) 은 이번 릴리스에서 미전환 — 옛 win32com
  코드 그대로 유지 (사용 빈도 낮음).

### 사용자 환경 영향
- 한컴오피스 미설치 PC 에서도 HWP 작업 가능 (읽기·검색·치환·삽입·템플릿)
- HwpCtrl.ocx 레지스트리 등록 불필요
- Node.js 는 기존 setup_helper 가 자동 설치 — 변화 없음
- exe 용량 +3.9MB (28→32MB 예상)

---

## v0.0.16 — 2026-04-21 (새 환경 적응 — 자동 재시도 + 환경 진단 로그)

### 배경
새 테스트 PC (다른 Windows 버전 / 한컴 버전 / AV 설정) 에서 v0.0.15 를 돌리니
`Control request timeout: initialize` 가 재현. 개발 PC 에선 잘 되는 세션 연결이
특정 환경에서 조용히 stuck — stderr 도 없어 원격 진단 어려움.

### 개선 1 — SDK connect 자동 재시도 (3회, 지수 백오프)
첫 connect 가 AV 스캔 / 첫 구동 지연 / pipe 인코딩 문제로 실패해도 2초 → 5초
간격으로 자동 재시도. 일시적 환경 이슈 자동 흡수.

### 개선 2 — 환경 진단 정보 자동 로그 덤프
connect 3회 모두 실패하면 `~/.ddukddak/sdk_debug.log` 에 다음 정보 자동 덤프:
- Windows 버전, 로캘/인코딩 (`getpreferredencoding`)
- Python / Claude CLI / Node.js 버전
- `claude -p ok` 비대화형 테스트 결과 (rc/stdout/stderr)
- 설정 파일 존재 여부

새 PC 에서 문제 발생 시 사용자는 이 로그 파일 하나만 공유하면 대부분 원인
특정 가능. "여러 번 왔다 갔다" 하는 진단 핑퐁 제거.

### 새 환경 적응 전략 (이번 릴리스 + 향후)
| 축 | 이번 | 계획 |
|---|---|---|
| Observability | 환경 진단 로그 덤프 | 설정 창에 "진단 정보 복사" 버튼 |
| Self-healing | connect 자동 재시도 3회 | SDK 실패 시 `-p` 폴백 |
| Pre-flight | — | 앱 최초 실행 시 CLI 버전·로그인·OCX 등록 일괄 점검 |
| Graceful degradation | — | 모든 조건 나빠도 최소 응답 가능한 mode |

---

## v0.0.15 — 2026-04-21 (HWP preflight 질문형 예외 + 세션 연결 에러 안내 개선)

### 개선 1 — HWP preflight 가 질문/안내 요청을 과차단하던 문제 수정
v0.0.14 까지는 "한글" / "hwp" 키워드만 있으면 안전차원에서 preflight 가 차단.
그래서 "관리자 권한으로 한글 실행해줘", "보안 경고 허용 방법" 같은 **Windows
설정 안내 질문**조차 HWP COM 미등록 에러로 응답.

수정: `_HWP_QUESTION_TOKENS` 신설 (`어떻게`, `방법`, `알려줘`, `설치`, `등록`,
`실행해`, `허용`, `권한`, `관리자`, `보안`, `경고`, `오류`, `?` 등).
HWP 키워드 + 이 질문 토큰 + **내용 편집 토큰 없음** 조합이면 preflight skip →
Claude 가 자연어로 답변하도록 통과.

HWP 문서 실제 편집 요청 (`읽어`, `편집`, `양식`, `찾아바꾸` 등) 은 계속 preflight
대상 — COM 미등록 상태에서 무한 루프 도는 걸 방지하는 원래 의도 그대로.

### 개선 2 — Claude 세션 연결 실패 에러 메시지 친절화
SDK connect 중 `Control request timeout: initialize` 에러가 나면 그동안은
불친절한 영문 원문만 노출. 새 테스트 PC (Claude 로그인 미완료 / CLI 첫 실행
느림 / 네트워크 차단) 에서 자주 발생.

수정: 에러 감지 시 3가지 원인 추정 (로그인 미완료 / 첫 실행 느림 / 네트워크
차단) 과 각 대응법, 로그 파일 경로를 한국어로 안내.

### 알려진 한계 (v0.0.15 로도 해결 안 되는 건)
- 테스트 PC 에 **HwpCtrl.ocx 가 실제로 등록 안 된 상태** 는 앱 차원에서 해결
  불가. 해당 PC 에서 관리자 cmd 로 `regsvr32 HwpCtrl.ocx` 필요.
- 그 PC 의 Claude 로그인 미완료도 앱이 자동 복구 불가 — 설정 창 2단계에서
  [Claude 로그인하기] 수동 진행 필요.

---

## v0.0.14 — 2026-04-21 (세션 유지 — `--continue` 로 전환)

### 배경
v0.0.13 까지는 Claude Code CLI 의 `--resume <session_id>` 로 멀티턴 대화를
유지. CLI 2.1.114 에서 `--resume` 시 첫 재개 호출이 무조건 `default` 권한
모드로 브랜치되는 회귀 재발 (2.1.112 에선 3초 버퍼로 우회 가능했으나 2.1.114
는 시간 무관). 사용자 증상: 두 번째 메시지부터 Claude 가 "권한이 필요합니다"
plain-text 응답, 도구 호출 없음 → "이전 대화 기억 못 함" 으로 체감.

### 최종 수정 — `--continue` 방식
옛 뚝딱비서 소스 9개를 디스어셈블 비교하던 중 (4) 버전에서만 유일하게
`--continue` 플래그를 쓴 흔적 발견. `--continue` 는 session_id 명시 없이 cwd
기반으로 최근 세션을 자동 이어감. `--resume <sid>` 의 브랜치 경로를 완전히
우회. 실측 3턴 시나리오 PASS (TURN 2 에서 도구 호출 45회 + 실제 xlsx 파일
생성, TURN 3 에서 "2번 스크립트" 맥락 정확히 인식).

구현:
- 첫 턴은 `--continue` 없이 (새 세션 시작).
- `self.history` 가 비어있지 않으면(= 2턴차부터) `--continue` 플래그 추가.
- `self.history` 는 첫 턴 판별 + session_cache 기록용으로만 유지.
- `_ensure_system_prompt_file` 은 base 프롬프트 복사만 수행 (history 주입 제거).
- 작업 폴더 변경 / 대화 초기화 시 `self.history = []` → 다음 호출에 --continue
  안 붙어서 자동 새 세션.
- `--dangerously-skip-permissions` 유지 (작업 폴더는 사용자가 명시 선택한 신뢰
  환경).
- `~/.ddukddak/current_session.md` self-managed memory 캐시 유지 (Claude 가
  시스템 프롬프트의 맥락이 부족하다고 느낄 때 Read 로 복원 가능).

### 검토 후 폐기한 대안들 (미래 회귀 방지용 기록)
- `--resume <sid>` + 3초/8초 버퍼: CLI 2.1.114 에서 시간 무관 실패.
- `--input-format stream-json` + stdin JSONL 멀티턴 주입: 마지막 user 메시지를
  비결정적으로 무시. 6턴 검증에서 TURN 3+ 모두 무력화.
- user prompt 에 history 직렬화: Claude 가 "끝난 과거 기록" 으로 보고 마무리
  톤 응답. 새 요청 무시.
- system prompt 에 history 직렬화: 컨텍스트 유지는 됐지만 첫 도구 호출 턴에서
  권한 자연어 hesitation. retry prompt 워딩 강화는 prompt-injection 의심 유발.
- CLI 다운그레이드(`@2.1.112`): 옛 방식 복원 가능하나 CLI 자동 업데이트 막고
  미래 기능 포기 필요.

### 핵심 발견 (기록용)
사용자의 "예전엔 세션이 잘 돌아갔다" 체감은 옛 코드가 우수해서가 아니라 CLI
2.1.112 이전의 `--resume` 안정성 덕분. 옛 소스 9개 모두 `--resume` 기반이
었고, 단 하나 (4) 버전만 `--continue` 를 시도한 흔적 — 그게 현재 CLI 2.1.114
에서도 동작하는 유일한 경로.

---

## v0.0.13 — 2026-04-20 (HWP preflight 오탐지 수정)

### 버그
테스터 PC(한컴 2022 + COM 미등록) 에서 "한글 파일 리스트 보여줘" 같은 **단순
파일시스템 요청**조차 HWP preflight 에 걸려서 "COM 등록하세요" 에러가 뜸.
`os.listdir` 만으로 가능한 작업인데도 차단되는 오탐지.

### 수정
`_prompt_mentions_hwp` 를 한 단계 더 세분화한 `_needs_hwp_com` 추가:
- `_HWP_FILE_ONLY_TOKENS` (리스트/목록/삭제/이동/복사/경로 등) 와
  `_HWP_CONTENT_ACTION_TOKENS` (읽/편집/양식/찾아바꾸/변환 등) 을 구분.
- HWP 키워드 + 파일-전용 패턴 + **내용 액션 없음** → preflight 스킵.
- 기본값은 preflight 실행(안전 우선) 유지.

에러 메시지도 개선: "파일 이름 조회/목록/이동/삭제는 COM 없이도 가능" 안내를
본문에 추가해서 사용자가 대안 경로로 진행할 수 있게.

---

## v0.0.12 — 2026-04-20 (.bak 자동 정리 E2E 검증용)

v0.0.11 과 기능 동일. v0.0.11 에서 추가한 "업데이트 성공 시 .bak 자동 삭제"
로직이 실제로 "v0.0.11 → v0.0.12" 업데이트에서 동작하는지 검증용 더미.

검증 체크리스트:
- [ ] v0.0.11 실행 → 업데이트 확인 → v0.0.12 로 자동 업데이트
- [ ] v0.0.12 창 뜬 후 Releases 폴더에 `뚝딱비서_v0.0.11.exe.bak` 없음
- [ ] `%TEMP%\\_ddukddak_update.log` 마지막 줄에 ".bak 정리 완료" 기록

---

## v0.0.11 — 2026-04-20 (업데이트 후 .bak 자동 정리)

### 개선
- **업데이트 성공 시 이전 버전 파일 자동 삭제**: 과거 에는 `뚝딱비서_v0.0.N.exe`
  가 업데이트 후 `.bak` 로 남아서 Releases 폴더가 지저분해졌음.
  이제는 새 버전 실행 후 2초간 살아있으면 업데이트 성공으로 간주하고
  `.bak` 자동 삭제.
- **안전장치**: 새 버전이 2초 내 종료(크래시) 되면 `.bak` 유지해서 사용자가
  수동 롤백 가능. 관련 로그 `%TEMP%\\_ddukddak_update.log` 에 남음.

---

## v0.0.10 — 2026-04-20 (자동 업데이트 E2E 검증용 — v0.0.9 이후)

v0.0.9 와 기능 동일. v0.0.9 에서 수정한 두 치명 버그
(`CREATE_NO_WINDOW` + `os._exit`) 이 실제로 "v0.0.9 → v0.0.10" 자동 업데이트
플로우에서 동작하는지 end-to-end 검증용 더미 릴리스.

검증 체크리스트:
- [ ] v0.0.9 실행 → 타이틀 `v0.0.9` 확인
- [ ] 설정 → 3단계 → [업데이트 확인] → 새 다이얼로그 → [예 (업데이트)]
- [ ] 프로그레스바 0→100%
- [ ] "업데이트 적용 중..." 표시 후 약 2–3초 내 창 닫힘
- [ ] v0.0.10 창 자동 실행, 타이틀 `v0.0.10` 확인
- [ ] `%TEMP%\\_ddukddak_update.log` 에 4줄(시작/백업/배치/실행) 타임스탬프

이 검증이 성공하면 자동 업데이트 시스템이 **처음으로** end-to-end 검증됨.

---

## v0.0.9 — 2026-04-20 (자동 업데이트 치명 버그 2개 실측 수정)

### v0.0.8 E2E 테스트 중 발견된 문제 2개

**v0.0.7 → v0.0.8 업데이트 실패** — 다운로드 100% 도달 후 "업데이트 적용 중..."
메시지 표시까진 되나 (a) 창이 안 닫히고 (b) %TEMP%\\_ddukddak_update.log 도 안 생김.

격리 테스트로 원인 2개 확정:

**버그 A — `DETACHED_PROCESS` 플래그가 PowerShell 을 즉사시킴**
- 이전 기록(v0.0.5 CHANGELOG) 엔 `DETACHED_PROCESS` 단독이 정답이라 써있었지만,
  이 시스템(Win11 + PS 5.1.26100) 에선 PS 가 spawn 직후 아무 코드도 실행 못 하고
  종료됨. stdin/out/err 전부 DEVNULL 연결해도 동일.
- 실측 결과: `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`
  조합이 정답. (DETACHED_PROCESS 가 들어가는 모든 조합은 실패)
- 수정 위치: `core/updater.py` → `DETACHED_PROCESS` → `CREATE_NO_WINDOW`.

**버그 B — `sys.exit(0)` in tkinter `after` 콜백이 프로세스 종료 안 시킴**
- tkinter/Tcl 의 이벤트 핸들러가 `SystemExit` 를 삼키고 mainloop 이 계속 돎.
  창은 열려 있고, 유저 입장에선 "재시작이 안 됨".
- 수정: `pentong_chat.py _apply_update` 의 `sys.exit(0)` → `os._exit(0)`.
  C 레벨 즉시 종료로 Python/Tcl 예외 처리 완전 우회.

### 주의: 기존 사용자 업그레이드 경로
v0.0.5 / 0.0.6 / 0.0.7 / 0.0.8 **모두 위 버그 있음** → 자동 업데이트로
v0.0.9 전환 불가. 사용자는 GitHub Releases 에서 `뚝딱비서_v0.0.9.exe` 를
수동으로 받아 교체해야 함. v0.0.9 이후 릴리스는 정상 동작 예정.

---

## v0.0.8 — 2026-04-20 (자동 업데이트 E2E 검증용)

v0.0.7 과 기능 동일. v0.0.7 에서 수정한 `CREATE_BREAKAWAY_FROM_JOB` + 2초 딜레이
가 실제로 동작하는지 "v0.0.7 → v0.0.8" 자동 업데이트로 end-to-end 검증용
더미 릴리스.

검증 체크리스트:
- [ ] v0.0.7 실행 → 설정 → 3단계 → [업데이트 확인] 클릭
- [ ] 새 커스텀 다이얼로그에 v0.0.8 노트 보이고 [예 (업데이트)] 버튼 정상 노출
- [ ] 다운로드 100% 후 "업데이트 적용 중 — 잠시 후 자동 재시작합니다..." 표시
- [ ] 부모 창 닫히고 약 2–3초 내 v0.0.8 창 자동 실행
- [ ] 타이틀 `뚝딱비서 v0.0.8 — ...`, 파일명 `뚝딱비서_v0.0.8.exe` 확인
- [ ] `%TEMP%\_ddukddak_update.log` 에 4줄(시작/백업/배치/실행) 타임스탬프

---

## v0.0.7 — 2026-04-20 (자동 업데이트 재시작 실패 수정)

### 치명 버그
- **v0.0.5/v0.0.6 에서 "업데이트" 클릭 → 다운로드 100% → 창 닫힘 → 새 버전
  실행 안 됨** 문제 근본 수정.
- 원인: Windows 가 Explorer 에서 띄운 프로세스를 **Job Object** 에 묶는데,
  `CREATE_BREAKAWAY_FROM_JOB` 플래그가 없으면 부모(뚝딱비서) 가 `sys.exit()`
  하는 순간 자식(PowerShell 헬퍼) 도 같이 끌려가 종료돼서 교체 스크립트가
  아예 실행되지 못함.
- 수정:
  1. `core/updater.py` Popen 에 `CREATE_BREAKAWAY_FROM_JOB` 추가.
     Breakaway 불허 환경은 해당 플래그 제외하고 폴백 재시도.
  2. 다운로드 완료 후 `sys.exit()` 딜레이 500ms → 2000ms. PowerShell 초기화
     (~1초) 중에 부모가 먼저 죽는 race condition 제거.
  3. UI 에 "업데이트 적용 중 — 잠시 후 자동 재시작합니다..." 안내 표시.

---

## v0.0.6 — 2026-04-20 (업데이트 다이얼로그 버튼 잘림 수정)

### 수정
- **업데이트 확인 다이얼로그 개선**: 릴리스 노트가 길 때 tk messagebox 가 세로로
  늘어나 [예]/[아니오] 버튼이 화면 밖으로 밀려 안 보이던 문제.
  → 커스텀 Toplevel 로 교체. 노트 영역은 스크롤 가능한 Text 위젯(10줄 고정),
  [예 (업데이트)] / [나중에] 버튼은 항상 하단에 고정. Enter/Esc 키 지원.

### 자동 업데이트 end-to-end 검증
- v0.0.5 → v0.0.6 실제 다운로드·재시작 플로우 확인용 릴리스.

---

## v0.0.5 — 2026-04-17 (자동 업데이트 대수정 + UX 개선)

### 자동 업데이트 버그 전면 수정
- **PowerShell 헬퍼 Popen 플래그 수정**: `CREATE_NO_WINDOW | DETACHED_PROCESS` 동시 지정
  시 CreateProcess 비정상 동작 → `DETACHED_PROCESS` 단독 + `-WindowStyle Hidden`.
  v0.0.4 에서 다운로드 후 창이 안 돌아오던 문제 근본 수정.
- **stdin/stdout/stderr DEVNULL 연결**: PS 가 stdio 핸들 없어서 초기화 중 죽는 것 방지.
- (v0.0.3 에서 이미 수정) 한글 경로에서 cmd `move` 실패 → PowerShell `Move-Item
  -LiteralPath` 로 교체.

### UX 개선
- **파일명에 버전 포함**: 업데이트 후 `뚝딱비서.exe` → `뚝딱비서_v0.0.5.exe`,
  다음은 `뚝딱비서_v0.0.6.exe` 등으로 저장. 탐색기에서 버전 한눈에.
  ⚠ **첫 업데이트 후 파일명이 바뀌니 바탕화면/작업표시줄 바로가기는 재작성** 필요.
- **단일 확인 다이얼로그**: [업데이트 확인] → 버튼 → 다이얼로그 (2단계) 에서
  [업데이트 확인] → 다이얼로그 (1단계) 로 단축. 새 버전 발견 즉시 "지금 업데이트?" 묻기.
- 업데이트 헬퍼 로그: `%TEMP%\_ddukddak_update.log` 에 단계별 타임스탬프 + 에러 기록.

---

## v0.0.4 — 2026-04-17 (자동 업데이트 end-to-end 검증용)

v0.0.3 과 기능 동일. PowerShell 기반 self-replace 검증용 더미 릴리스.
**이 버전은 batch move 한글 경로 버그 때문에 end-to-end 업데이트가 실제로
완료되지 않았음 (v0.0.5 에서 근본 해결).**

---

## v0.0.3 — 2026-04-17 (자동 업데이트 batch→PowerShell 전환)

- 긴 한글 경로에서 cmd batch 의 `move` 실패 → PowerShell `Move-Item -LiteralPath`
  로 교체 (unicode 경로 안전).
- 업데이트 로그를 `%TEMP%\_ddukddak_update.log` 에 남김.

---

## v0.0.2 — 2026-04-17 (자동 업데이트 end-to-end 검증용)

v0.0.1 과 기능 동일. 자동 업데이트 플로우 테스트용 더미 릴리스.

---

## v0.0.1 — 2026-04-17

초기 공개 버전.

### 주요 기능
- 한글(HWP)·엑셀 파일 AI 어시스턴트 (Claude Code CLI 기반)
- 파일 드래그 앤 드롭 첨부
- 양식 기반 자동 채움

### 안정성
- **세션 유지 버그 수정**: Claude CLI 2.1.x `--resume` 브랜치 버그 회피 (3초 버퍼 + `--settings` 강제)
- **중단 버튼**: 작업 중 비상정지 (빨간 "중단" 버튼)
- **HWP 사전 점검**: COM 미등록 상태 감지 시 즉시 안내 후 작업 차단 (무한 루프 방지)
- **루프 방지 프롬프트**: 같은 오류 3회 반복 시 자동 멈춤, 고급 COM 우회 시도 금지

### 작업 폴더 청결
- 중간 Python 스크립트는 `%TEMP%` 에만 생성, 작업 폴더에 쓰레기 안 남김
- `python -c` 인라인 실행 우선

### 엔진 자동 설치
- Python 3.12 / Git / Node.js / Claude CLI 자동 다운로드·설치
- pywin32, openpyxl, xlrd pip 패키지 자동 설치
- PowerShell 실행 정책 자동 해제

### 자동 업데이트
- 설정 화면 > 3단계 에서 "업데이트 확인" 버튼으로 최신 버전 내려받고 자동 재시작





 py 권한 관련 문제는 윈도우에서 안열려있는것도 잇지만 이게 사용자가 직접 열어주는게
  안되거든 일반사용자라 이런거 권한 안열려잇다고 니가 알아서 열어라 보다는 안열려있으면
  뚝딱비서가 열어주면 좋겟거든




● 내일 새 대화 첫 메시지로 이거 그대로 보내시면 됩니다:

  뚝딱비서 v0.0.14 가드레일 작업 이어서 진행하자

  이러면 자동으로 project_v0_0_14_session_redesign.md 메모리 끌어와서 작업 큐 (build.bat 자동
  테스트 hook → SESSION_CONTRACT.md → PyInstaller 빌드 → GitHub 릴리스) 부터 차례로 진행
  가능합니다.

  더 짧게 가시려면:
  v0.0.14 가드레일 이어서
  도 됩니다 — 키워드만 있어도 메모리 매칭됩니다.


