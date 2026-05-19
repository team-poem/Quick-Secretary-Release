"""
Step 1: COM 연결 확인
- 한글 프로그램을 COM으로 열 수 있는지
- HWP 파일을 열고 텍스트를 읽어올 수 있는지
- 한글 프로그램을 정상 종료할 수 있는지

사용법:
  python step01_com_connect.py [hwp파일경로]

  파일경로 없이 실행하면 빈 문서로 테스트합니다.
"""
import sys
import os


def main():
    # COM 라이브러리 로드 확인
    try:
        import win32com.client as win32
        print("[OK] win32com 로드 성공")
    except ImportError:
        print("[FAIL] win32com 없음. 설치: pip install pywin32")
        return

    hwp = None
    try:
        # 한글 프로그램 인스턴스 생성
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        print("[OK] 한글 프로그램 연결 성공")

        # 보안 모듈 등록 (API 사용 허가)
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
        print("[OK] 보안 모듈 등록")

        # HWP 파일 열기 또는 빈 문서
        if len(sys.argv) > 1:
            filepath = os.path.abspath(sys.argv[1])
            if not os.path.exists(filepath):
                print(f"[FAIL] 파일 없음: {filepath}")
                return
            hwp.Open(filepath)
            print(f"[OK] 파일 열기 성공: {filepath}")
        else:
            print("[INFO] 파일 경로 없음 — 빈 문서로 테스트")

        # 문서 텍스트 읽기
        hwp.InitScan()
        text_parts = []
        while True:
            state, text = hwp.GetText()
            if state in (0, 1):  # 0=끝, 1=끝(마지막 텍스트 있음)
                if text:
                    text_parts.append(text)
                break
            if text:
                text_parts.append(text)

        hwp.ReleaseScan()

        full_text = "\n".join(text_parts)
        if full_text.strip():
            print(f"[OK] 텍스트 읽기 성공 ({len(full_text)}자)")
            print("--- 처음 500자 ---")
            print(full_text[:500])
            print("--- 끝 ---")
        else:
            print("[OK] 문서가 비어있거나 텍스트 없음 (빈 문서 정상)")

    except Exception as e:
        print(f"[FAIL] 오류 발생: {e}")
        # 흔한 에러 안내
        err_str = str(e)
        if "HWPFrame" in err_str or "Class not registered" in err_str:
            print("  → 한글 프로그램이 설치되지 않았거나 COM 등록이 안 되어 있습니다.")
        elif "SecurityModule" in err_str:
            print("  → 한글 보안 모듈 문제. 한글 > 도구 > 스크립트 매크로 보안 설정을 확인하세요.")

    finally:
        if hwp:
            try:
                hwp.Clear(1)  # 저장 안 하고 닫기
                hwp.Quit()
                print("[OK] 한글 프로그램 종료")
            except Exception:
                print("[WARN] 한글 종료 중 오류 (수동으로 닫아주세요)")


if __name__ == "__main__":
    main()
