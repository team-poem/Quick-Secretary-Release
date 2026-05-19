"""HWP Bridge — Claude Code에서 직접 한글 프로그램을 제어하기 위한 브릿지.

사용법:
  python hwp_bridge.py connect              — 한글 프로그램 연결
  python hwp_bridge.py open "파일경로"       — 파일 열기
  python hwp_bridge.py read                  — 전체 텍스트 읽기
  python hwp_bridge.py structure             — 문서 구조 분석
  python hwp_bridge.py section "키워드"      — 섹션 읽기
  python hwp_bridge.py find "텍스트"         — 텍스트 검색
  python hwp_bridge.py replace "찾기" "바꾸기" — 찾아 바꾸기
  python hwp_bridge.py save                  — 저장
  python hwp_bridge.py saveas "경로"         — 다른 이름으로 저장
  python hwp_bridge.py replace_para 번호 "새텍스트" — 문단 교체
  python hwp_bridge.py replace_section "키워드" "새내용" — 섹션 교체
  python hwp_bridge.py quit                  — 한글 종료

COM 객체를 pickle로 저장할 수 없으므로, 한글 연결 상태를 유지하려면
connect 후 다른 명령들을 같은 프로세스에서 실행해야 한다.
→ 이 스크립트는 "서버 모드"로 동작: 파일 기반 명령 주고받기.
"""

import sys
import os
import json
import time

# hwp_controller.py가 같은 폴더에 있다고 가정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hwp_controller import HwpController

CMD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hwp_cmd.json")
RESULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hwp_result.json")


def run_server():
    """파일 기반 명령 서버. _hwp_cmd.json을 감시하고 결과를 _hwp_result.json에 쓴다."""
    # Windows 콘솔 인코딩 문제 방지
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    ctrl = HwpController()

    print("[HWP Bridge] 서버 시작. 한글 프로그램 연결 중...")
    try:
        result = ctrl.connect(visible=True)
        print(f"[HWP Bridge] {result}")
    except Exception as e:
        print(f"[HWP Bridge] 연결 실패: {e}")
        return

    # 기존 명령/결과 파일 정리
    for f in [CMD_FILE, RESULT_FILE]:
        if os.path.exists(f):
            os.remove(f)

    print(f"[HWP Bridge] 명령 대기 중... (명령 파일: {CMD_FILE})")
    print("[HWP Bridge] 종료하려면 Ctrl+C")

    try:
        while True:
            if os.path.exists(CMD_FILE):
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        cmd = json.load(f)
                    os.remove(CMD_FILE)

                    action = cmd.get("action", "")
                    print(f"[HWP Bridge] 명령 수신: {action}")

                    result = _dispatch(ctrl, cmd)
                    print(f"[HWP Bridge] 결과: {result[:100]}...")

                    with open(RESULT_FILE, "w", encoding="utf-8") as f:
                        json.dump({"result": result}, f, ensure_ascii=False)

                    if action == "quit":
                        break

                except Exception as e:
                    with open(RESULT_FILE, "w", encoding="utf-8") as f:
                        json.dump({"result": f"오류: {e}"}, f, ensure_ascii=False)

            time.sleep(0.3)

    except KeyboardInterrupt:
        print("\n[HWP Bridge] 종료 중...")
    finally:
        ctrl.disconnect()
        for f in [CMD_FILE, RESULT_FILE]:
            if os.path.exists(f):
                os.remove(f)
        print("[HWP Bridge] 종료 완료")


def _dispatch(ctrl: HwpController, cmd: dict) -> str:
    action = cmd.get("action", "")

    if action == "open":
        return ctrl.open_file(cmd["filepath"])
    elif action == "read":
        return ctrl.read_full_text()
    elif action == "structure":
        return ctrl.read_document_structure()
    elif action == "section":
        return ctrl.read_section(cmd["keyword"])
    elif action == "find":
        return ctrl.find_text(cmd["search_text"])
    elif action == "replace":
        return ctrl.replace_text(cmd["find_str"], cmd["replace_str"])
    elif action == "replace_section":
        return ctrl.replace_section_content(cmd["keyword"], cmd["new_content"])
    elif action == "replace_para":
        return ctrl.replace_paragraph(cmd["para_index"], cmd["new_text"])
    elif action == "save":
        return ctrl.save_file()
    elif action == "saveas":
        return ctrl.save_as(cmd["filepath"])
    elif action == "current":
        return ctrl.get_current_file()
    elif action == "quit":
        return ctrl.disconnect()
    else:
        return f"알 수 없는 명령: {action}"


def send_command(cmd: dict, timeout: float = 30.0) -> str:
    """외부에서 명령을 보내고 결과를 기다린다."""
    # 이전 결과 파일 제거
    if os.path.exists(RESULT_FILE):
        os.remove(RESULT_FILE)

    with open(CMD_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f, ensure_ascii=False)

    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(RESULT_FILE):
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            os.remove(RESULT_FILE)
            return data.get("result", "결과 없음")
        time.sleep(0.3)

    return "시간 초과: 한글 브릿지가 응답하지 않습니다."


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        run_server()
    else:
        print("사용법: python hwp_bridge.py server")
        print("  서버 모드로 실행하면 한글 프로그램에 연결하고 명령을 대기합니다.")
