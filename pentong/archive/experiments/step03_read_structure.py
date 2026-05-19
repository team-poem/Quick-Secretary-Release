"""
Step 3: 문서 구조 읽기 — 제목/본문 단위로 섹션 파악
- 한글 문서를 열고
- 문단별로 텍스트와 스타일(제목, 본문 등)을 읽어서
- "XX전공" 같은 섹션 위치를 찾을 수 있는지 검증

사용법:
  python step03_read_structure.py 파일.hwp
  python step03_read_structure.py 파일.hwp "검색할섹션"
"""
import sys
import os


def main():
    if len(sys.argv) < 2:
        print('사용법: python step03_read_structure.py 파일.hwp ["검색할섹션"]')
        return

    filepath = os.path.abspath(sys.argv[1])
    search_section = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(filepath):
        print(f"[FAIL] 파일 없음: {filepath}")
        return

    import win32com.client as win32
    hwp = None

    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
        hwp.Open(filepath)
        print(f"[OK] 파일 열기: {filepath}")

        # 문서 처음으로 이동
        hwp.HAction.Run("MoveDocBegin")

        paragraphs = []
        para_idx = 0

        # 문단별로 탐색: ctrl 이동으로 문단 순회
        while True:
            # 현재 문단 정보 수집
            # GetCurParaShape로 현재 문단 스타일 ID 가져오기
            para_shape_id = hwp.ParaShapeID

            # 현재 문단의 글자 모양 (크기로 제목 여부 판단)
            char_shape_id = hwp.CharShapeID

            # 현재 줄 텍스트 가져오기: 현재 문단 선택 후 텍스트 추출
            hwp.HAction.Run("MoveParaBegin")
            hwp.HAction.Run("MoveParaEnd")
            # Select로 현재 문단 선택
            hwp.HAction.Run("MoveParaBegin")
            hwp.HAction.GetDefault("SelectAll", hwp.HParameterSet.HSelectionOpt.HSet)

            # GetText 방식 대신: 문단 시작~끝 선택해서 텍스트 가져오기
            hwp.HAction.Run("MoveParaBegin")
            start_pos = hwp.GetPos()
            hwp.HAction.Run("MoveParaEnd")
            end_pos = hwp.GetPos()

            # 문단 텍스트 추출 (선택 후 복사)
            hwp.HAction.Run("MoveParaBegin")
            hwp.HAction.Run("Select")
            hwp.HAction.Run("MoveParaEnd")

            text = hwp.GetTextFile("TEXT", "")
            # GetTextFile은 전체 문서를 반환할 수 있으므로,
            # 대안: InitScan/GetText로 현재 위치에서 읽기

            # 더 간단한 방법: InitScan + GetText로 한 문단씩
            hwp.HAction.Run("Cancel")  # 선택 해제
            break  # 이 방법은 복잡 — 아래에서 InitScan 방식 사용

        # --- InitScan 방식으로 문단 구조 추출 ---
        hwp.HAction.Run("MoveDocBegin")
        hwp.InitScan(0x0010)  # 문단 단위 스캔

        paragraphs = []
        while True:
            state, text = hwp.GetText()
            if state in (0, 1):
                if text and text.strip():
                    paragraphs.append(text.strip())
                break
            if text and text.strip():
                paragraphs.append(text.strip())

        hwp.ReleaseScan()
        print(f"[OK] 총 {len(paragraphs)}개 문단 추출")

        # 문단별 글자 크기로 제목/본문 구분 시도
        # 제목 후보: 짧은 문단(50자 이하)
        print("\n=== 문서 구조 ===")
        sections = []
        for i, para in enumerate(paragraphs):
            # 제목 후보 판별: 짧고, 줄바꿈 없고, 숫자/마침표로 시작하거나 "전공" 포함
            is_heading = len(para) < 80 and (
                "전공" in para
                or "학과" in para
                or "제목" in para
                or para.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))
                or para.startswith(("I.", "II.", "III.", "IV.", "V."))
                or para.startswith(("제1", "제2", "제3"))
                or para.startswith(("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"))
            )

            if is_heading:
                marker = ">> "
                sections.append({"index": i, "title": para})
            else:
                marker = "   "

            # 처음 30개 문단 또는 제목인 경우 출력
            if i < 30 or is_heading:
                preview = para[:100] + ("..." if len(para) > 100 else "")
                print(f"  [{i:3d}] {marker}{preview}")

        print(f"\n[OK] 제목 후보 {len(sections)}개 발견:")
        for s in sections:
            print(f"  [{s['index']:3d}] {s['title']}")

        # 특정 섹션 검색
        if search_section:
            print(f"\n=== \"{search_section}\" 섹션 검색 ===")
            found = False
            for i, s in enumerate(sections):
                if search_section in s["title"]:
                    found = True
                    start = s["index"]
                    # 다음 섹션까지가 이 섹션의 본문
                    if i + 1 < len(sections):
                        end = sections[i + 1]["index"]
                    else:
                        end = len(paragraphs)

                    print(f"[OK] 발견! 문단 [{start}] ~ [{end - 1}] ({end - start}개 문단)")
                    print(f"  제목: {s['title']}")
                    print(f"  본문 미리보기:")
                    for j in range(start, min(start + 5, end)):
                        preview = paragraphs[j][:80] + ("..." if len(paragraphs[j]) > 80 else "")
                        print(f"    [{j}] {preview}")
                    if end - start > 5:
                        print(f"    ... ({end - start - 5}개 문단 더)")

            if not found:
                print(f"[WARN] \"{search_section}\" 포함된 섹션 없음")

    except Exception as e:
        print(f"[FAIL] 오류: {e}")

    finally:
        if hwp:
            try:
                hwp.Clear(1)
                hwp.Quit()
                print("\n[OK] 한글 종료")
            except Exception:
                print("[WARN] 한글 종료 중 오류")
            finally:
                import gc
                del hwp
                gc.collect()
                import pythoncom
                pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
