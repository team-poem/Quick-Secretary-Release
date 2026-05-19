"""
Step 2: 텍스트 찾아 바꾸기
- COM으로 한글 문서를 열고
- 특정 텍스트를 찾아서 다른 텍스트로 바꾸고
- 결과를 다른 이름으로 저장

사용법:
  python step02_find_replace.py 파일.hwp "찾을텍스트" "바꿀텍스트"
"""
import sys
import os


def main():
    if len(sys.argv) < 4:
        print("사용법: python step02_find_replace.py 파일.hwp \"찾을텍스트\" \"바꿀텍스트\"")
        return

    filepath = os.path.abspath(sys.argv[1])
    find_text = sys.argv[2]
    replace_text = sys.argv[3]

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

        # 커서를 문서 처음으로 이동
        hwp.HAction.Run("MoveDocBegin")

        # 찾아 바꾸기 실행
        pset = hwp.HParameterSet.HFindReplace
        hwp.HAction.GetDefault("AllReplace", pset.HSet)
        pset.FindString = find_text
        pset.ReplaceString = replace_text
        pset.IgnoreMessage = 1  # 결과 메시지 박스 숨김
        pset.HSet.SetItem("IgnoreCase", 0)
        pset.HSet.SetItem("WholeWordOnly", 0)
        pset.HSet.SetItem("AllWordForms", 0)
        pset.HSet.SetItem("SeveralWords", 0)
        pset.HSet.SetItem("UseWildCards", 0)
        pset.HSet.SetItem("AutoSpell", 1)
        pset.Direction = 0  # 전체 방향
        pset.ReplaceMode = 1  # 모두 바꾸기

        result = hwp.HAction.Execute("AllReplace", pset.HSet)
        count = pset.FindEntireWord if hasattr(pset, 'FindEntireWord') else "?"
        print(f"[OK] 찾아 바꾸기 실행 (result={result}): \"{find_text}\" → \"{replace_text}\"")

        # 다른 이름으로 저장
        name, ext = os.path.splitext(filepath)
        save_path = f"{name}_modified{ext}"
        hwp.SaveAs(save_path)
        print(f"[OK] 저장 완료: {save_path}")

    except Exception as e:
        print(f"[FAIL] 오류: {e}")

    finally:
        if hwp:
            try:
                hwp.Clear(1)
                hwp.Quit()
                print("[OK] 한글 종료")
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
