"""세션 유지 검증 — system prompt 주입 방식 (E: history 를 system prompt 에).

CLI 2.1.x --resume 브랜치 버그 영구 회피 + stream-json input 비결정성 회피.

설계:
  - 매 호출마다 새 세션 (--dangerously-skip-permissions, resume 없음)
  - 대화 이력을 base system prompt 뒤에 직렬화해서 임시 파일로 저장
  - --append-system-prompt-file <tmp> 로 주입
  - user prompt 는 새 메시지만 깨끗하게
  - Claude 입장: "내가 이런 사전 컨텍스트(이력) 를 가진 어시스턴트, 사용자가
    이번에 이렇게 새 메시지를 보냄" → 마지막 user 무시 같은 혼선 없음
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WORK_DIR = r"C:/Users/user/Desktop/pentong-20260416T024438Z-3-001/오전테스트실패후다시이관한/뚝딱비서"
TEMPLATE_PATH = r"C:/Users/user/Desktop/pentong-20260416T024438Z-3-001/오전테스트실패후다시이관한/뚝딱비서/테스트 문서.xlsx"
BASE_SYSTEM_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "pentong_system_prompt.txt")
CLAUDE_CMD = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")
_NO_WIN = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def build_system_prompt_with_history(history: list[dict]) -> str:
    """base system prompt + history 를 합쳐서 임시 파일에 쓰고 경로 반환."""
    with open(BASE_SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        base = f.read()
    if not history:
        return BASE_SYSTEM_PROMPT_FILE  # base 그대로

    parts = [base, "\n\n[지금까지 진행된 대화 이력 — 당신과 사용자의 이전 주고받음]\n"]
    parts.append("(아래는 이미 완료된 과거 턴들입니다. 사용자의 새 메시지는 이력 다음에 따로 옵니다.)\n")
    for i, turn in enumerate(history, 1):
        role = "[사용자 발화]" if turn["role"] == "user" else "[당신의 직전 응답]"
        parts.append(f"\n--- 턴 {(i+1)//2} {role} ---\n{turn['content']}\n")
    parts.append(
        "\n[이력 끝]\n"
        "위 이력을 모두 기억한 상태로, 사용자의 새 메시지에 자연스럽게 이어서 답하세요. "
        "필요하면 도구를 적극 사용하세요."
    )
    full = "".join(parts)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False,
        prefix="_ddukddak_sysprompt_",
    )
    tmp.write(full)
    tmp.close()
    return tmp.name


def _looks_like_permission_rejection(msg_types: list, raw: str) -> bool:
    """Claude 가 stream-json 안 내보내고 자연어로 끝낸 케이스를 모두 잡음.

    sandbox 권한 우회 플래그(--dangerously-skip-permissions) 가 켜져 있는데도
    Claude 가 자발적으로 "승인 필요/막혀있음/허용해주세요" 같은 자연어 응답으로
    끝나는 패턴. 마커 매칭은 너무 좁아서 회피되는 케이스가 많아 일반 fallback
    추가: stream-json 메시지가 0개이면서 raw 에 의미있는 분량의 텍스트가 있으면
    무조건 재시도 대상으로 본다 (정상 응답이라면 stream-json 으로 와야 함).
    """
    if msg_types:
        return False
    return len(raw.strip()) > 30


def _single_call(cmd: list, label: str) -> tuple[str, list, str, float, int]:
    start = time.time()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=WORK_DIR, text=True, encoding="utf-8", errors="replace",
        creationflags=_NO_WIN,
    )
    final_text = ""
    msg_types = []
    raw_lines = []
    for line in proc.stdout:
        raw_lines.append(line.rstrip())
        s = line.strip()
        if not s:
            continue
        try:
            msg = json.loads(s)
        except json.JSONDecodeError:
            continue
        msg_types.append(msg.get("type", "?"))
        if msg.get("type") == "result":
            r = msg.get("result", "")
            if r:
                final_text = r
    proc.wait()
    elapsed = time.time() - start
    return final_text, msg_types, "\n".join(raw_lines), elapsed, proc.returncode


def call_turn(history: list[dict], user_msg: str, label: str) -> tuple[str, list, str]:
    sysprompt_file = build_system_prompt_with_history(history)

    print(f"\n{'='*70}\n{label}\n{'='*70}")
    sysprompt_size = os.path.getsize(sysprompt_file)
    print(f"  [이력 턴 수] {len(history)//2}  (system prompt 파일 {sysprompt_size} bytes)")
    print(f"  [사용자 메시지 요약] {user_msg[:120].replace(chr(10), ' ')}")

    def _build_cmd(prompt_text: str) -> list:
        return [
            CLAUDE_CMD,
            "-p", prompt_text,
            "--verbose",
            "--output-format", "stream-json",
            "--model", "sonnet",
            "--append-system-prompt-file", sysprompt_file,
            "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
            "--dangerously-skip-permissions",
        ]

    final_text, msg_types, raw, elapsed, rc = _single_call(_build_cmd(user_msg), label)
    print(f"  [경과] {elapsed:.1f}s  [returncode] {rc}  "
          f"[메시지 종류 {len(msg_types)}] {msg_types[:8]}{'...' if len(msg_types)>8 else ''}")

    # 자동 재시도: Claude 가 첫 도구 호출에서 stream-json 못 내보내고 자연어로 끝낸 패턴.
    # 메타 지시 워딩(시스템 알림 등) 은 Claude 가 prompt injection 으로 의심해 더 거부함.
    # 가장 robust 한 방식은 "같은 prompt 한 번 더" — Claude 가 두 번째 시도에선
    # 결정을 바꿀 수 있고, 안 바꿔도 다음 turn 에서 자동 진행됨.
    if _looks_like_permission_rejection(msg_types, raw):
        print(f"  [재시도] 권한 거부 plain-text 감지 — 같은 prompt 로 1회 재시도")
        final_text, msg_types, raw, elapsed, rc = _single_call(_build_cmd(user_msg), label)
        print(f"  [재시도 결과 경과] {elapsed:.1f}s  [returncode] {rc}  "
              f"[메시지 종류 {len(msg_types)}]")

    if not msg_types and raw.splitlines():
        print(f"  [RAW STDOUT 첫 3줄]")
        for r in raw.splitlines()[:3]:
            print(f"    | {r[:200]}")
    print(f"\n  [응답 첫 400자]\n{final_text[:400]}")

    return final_text, msg_types, raw


def main():
    if not os.path.exists(BASE_SYSTEM_PROMPT_FILE):
        print(f"시스템 프롬프트 파일 없음: {BASE_SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    if not os.path.exists(CLAUDE_CMD):
        print(f"Claude CMD 없음: {CLAUDE_CMD}")
        sys.exit(1)

    template_hint = (
        f'\n\n[양식 지정] 작업 시 다음 양식 파일을 참고하세요: "{TEMPLATE_PATH}"\n'
        f"이 양식의 구조와 서식을 그대로 따라서 결과물을 만들어주세요. "
        f"양식 파일을 먼저 읽고 구조를 파악한 뒤 작업하세요."
    )

    history: list[dict] = []
    failures: list[str] = []

    # TURN 1
    user1 = "현재 파일 목록에 엑셀 한글파일 리스트 보여줘"
    text1, types1, _ = call_turn(history, user1, "TURN 1 — 파일 목록 요청")
    if not types1:
        failures.append("TURN 1 stream-json 0개")
    history.append({"role": "user", "content": user1})
    history.append({"role": "assistant", "content": text1})

    # TURN 2
    user2 = (
        f'"{WORK_DIR}/2024~25학년도 전체지원자.xls" 을 읽고 정산부서 기준으로 '
        f'연번, 정산부서, 프로그램과목명, 개수 를 정리해서 테스트 문서 양식 기준으로 '
        f'엑셀파일 생성해줘 24년(학과) 시트 기준으로 개수라는것은 프로그램 종류수로 하면돼'
        + template_hint
    )
    text2, types2, raw2 = call_turn(history, user2, "TURN 2 — xls 분석 + 양식 출력")
    if not types2:
        failures.append("TURN 2 stream-json 0개")
    if any(m in raw2 for m in ["권한 승인이 필요", "권한이 필요합니다", "requires approval"]):
        failures.append("TURN 2 권한 거부 plain-text 감지")
    history.append({"role": "user", "content": user2})
    history.append({"role": "assistant", "content": text2})

    # TURN 3 — 컨텍스트 의존 ("2번 스크립트")
    user3 = "2번 스크립트 파일생성해서 한번진행해봐 (작업후 삭제하지말고 일단 둬)"
    text3, types3, _ = call_turn(history, user3, "TURN 3 — 컨텍스트 의존 메시지")
    if not types3:
        failures.append("TURN 3 stream-json 0개")
    if any(p in text3 for p in ["메모리가 비어", "맥락을 파악할 수 없", "이전 대화 기록"]):
        failures.append(f"TURN 3 컨텍스트 손실")
    history.append({"role": "user", "content": user3})
    history.append({"role": "assistant", "content": text3})

    # TURN 4 — 정밀 회수: 짧고 정확한 답
    user4 = "위에서 1번에 있던 파일 이름을 정확히 다시 알려줘 (다른 설명 없이 파일명만)"
    text4, types4, _ = call_turn(history, user4, "TURN 4 — 누적 이력 정확도 검증")
    if not types4:
        failures.append("TURN 4 stream-json 0개")
    if "2024" not in text4 or "전체지원자" not in text4:
        failures.append(f"TURN 4 1번 파일명 회수 실패: {text4[:120]!r}")
    if len(text4) > 250:
        failures.append(f"TURN 4 응답 너무 김 ({len(text4)}자) — 직답 안 함, 파일목록 반복 의심")
    history.append({"role": "user", "content": user4})
    history.append({"role": "assistant", "content": text4})

    # TURN 5 — 후속 작업
    user5 = "방금 만든 결과 xlsx 파일의 헤더 행만 다시 확인해서 알려줘"
    text5, types5, _ = call_turn(history, user5, "TURN 5 — 후속 작업 (이전 결과 참조)")
    if not types5:
        failures.append("TURN 5 stream-json 0개")
    history.append({"role": "user", "content": user5})
    history.append({"role": "assistant", "content": text5})

    # TURN 6 — 최초 의도 회상 (요약)
    user6 = "맨 처음에 내가 너한테 뭐 시켰는지 한 줄로만 요약해봐. 다른 설명 금지."
    text6, types6, _ = call_turn(history, user6, "TURN 6 — 최초 의도 회상")
    if not types6:
        failures.append("TURN 6 stream-json 0개")
    if not any(k in text6 for k in ["목록", "리스트", "엑셀", "한글"]):
        failures.append(f"TURN 6 최초 요청 회상 실패: {text6[:120]!r}")
    if len(text6) > 250:
        failures.append(f"TURN 6 응답 너무 김 ({len(text6)}자) — 한 줄 요약 안 됨, 파일목록 반복 의심")
    history.append({"role": "user", "content": user6})
    history.append({"role": "assistant", "content": text6})

    # 판정
    print(f"\n\n{'#'*70}\n# 판정\n{'#'*70}")
    print(f"최종 history 턴 수: {len(history)//2}")
    if failures:
        print(f"\n[FAIL] 총 {len(failures)}개 이슈:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"\n[PASS] 6턴 누적 이력 + 직답 + 회상 모두 정상")


if __name__ == "__main__":
    main()
