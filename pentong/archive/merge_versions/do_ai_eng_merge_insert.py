"""AI공학 섹션 교체 — InsertFile 방식 (표/서식 100% 보존).

전략:
  1) 마스터에서 "가. AI공학 융합연계전공" → 고유 마커로 치환
  2) "수정해야함" 삭제
  3) 마커를 찾아서 해당 문단 삭제
  4) 커서 위치에 수정본 파일을 InsertFile → 표/서식 모두 보존
  5) 저장
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정.hwp')
MARKER = "PENTONG_REPLACE_MARKER_7X9K"


def all_replace(hwp, find, replace):
    """AllReplace 실행."""
    hwp.HAction.Run("MoveDocBegin")
    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("AllReplace", pset.HSet)
    pset.FindString = find
    pset.ReplaceString = replace
    pset.IgnoreMessage = 1
    pset.HSet.SetItem("IgnoreCase", 0)
    pset.Direction = 0
    pset.ReplaceMode = 1
    return hwp.HAction.Execute("AllReplace", pset.HSet)


def repeat_find(hwp, text):
    """RepeatFind — 텍스트를 찾아 선택."""
    hwp.HAction.Run("MoveDocBegin")
    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("RepeatFind", pset.HSet)
    pset.FindString = text
    pset.IgnoreMessage = 1
    return hwp.HAction.Execute("RepeatFind", pset.HSet)


def read_paras(hwp):
    hwp.HAction.Run("MoveDocBegin")
    hwp.InitScan(0x0010)
    paras = []
    while True:
        state, text = hwp.GetText()
        if state in (0, 1):
            if text and text.strip():
                paras.append(text.strip())
            break
        if text and text.strip():
            paras.append(text.strip())
    hwp.ReleaseScan()
    return paras


def main():
    import pythoncom
    pythoncom.CoInitialize()
    import win32com.client as win32

    hwp = None
    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
        hwp.XHwpWindows.Item(0).Visible = True
        print("[OK] 한글 연결")

        # === 마스터 열기 ===
        print("\n[1] 마스터 열기")
        hwp.Open(MASTER)

        # === "가. AI공학 융합연계전공"을 마커로 치환 ===
        print("\n[2] 제목 → 마커 치환")
        all_replace(hwp, "가. AI공학 융합연계전공", MARKER)
        print(f"  '가. AI공학 융합연계전공' → 마커")

        # === "수정해야함" 삭제 ===
        print("\n[3] '수정해야함' 삭제")
        all_replace(hwp, "수정해야함", "")
        print("  삭제 완료")

        # === 마커 찾아서 해당 문단 통째로 삭제 ===
        print("\n[4] 마커 문단 삭제 + InsertFile")
        found = repeat_find(hwp, MARKER)
        if not found:
            print("[FAIL] 마커를 찾지 못함")
            return
        print("  마커 발견")

        # 마커가 선택된 상태 → 문단 전체 선택 후 삭제
        hwp.HAction.Run("MoveParaBegin")
        hwp.HAction.Run("MoveSelectParaEnd")
        hwp.HAction.Run("Delete")
        # 빈 문단 자체도 삭제 (다음 문단과 합치기)
        hwp.HAction.Run("Delete")
        print("  마커 문단 삭제 완료")

        # === 커서 위치에 수정본 파일 삽입 ===
        print(f"\n[5] InsertFile: {os.path.basename(SOURCE)}")
        hwp.HAction.GetDefault("InsertFile", hwp.HParameterSet.HInsertFile.HSet)
        hwp.HParameterSet.HInsertFile.filename = SOURCE
        hwp.HParameterSet.HInsertFile.KeepSection = 0
        hwp.HParameterSet.HInsertFile.KeepCharshape = 1
        hwp.HParameterSet.HInsertFile.KeepParashape = 1
        hwp.HParameterSet.HInsertFile.KeepStyle = 1
        hwp.HAction.Execute("InsertFile", hwp.HParameterSet.HInsertFile.HSet)
        print("  삽입 완료 (표/서식 포함)")

        # === 검증 ===
        print("\n[6] 검증")
        verify = read_paras(hwp)
        for i, p in enumerate(verify):
            if 'AI공학' in p and ('가.' in p or '융합' in p):
                print("  결과:")
                for j in range(max(0, i-2), min(len(verify), i + 20)):
                    print(f"  [{j}] {verify[j][:70]}{'...' if len(verify[j])>70 else ''}")
                break

        # 마커/수정해야함 잔여 체크
        remain_marker = sum(1 for p in verify if MARKER in p)
        remain_modify = sum(1 for p in verify if '수정해야함' in p)
        print(f"\n  마커 잔여: {remain_marker}, '수정해야함' 잔여: {remain_modify}")

        # === 저장 ===
        print(f"\n[7] 저장")
        hwp.SaveAs(OUTPUT)
        print(f"  [OK] {os.path.basename(OUTPUT)}")

    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        if hwp:
            try:
                hwp.Clear(1)
                hwp.Quit()
            except:
                pass
            import gc; del hwp; gc.collect()
            pythoncom.CoUninitialize()
            print("[OK] 한글 종료")


if __name__ == '__main__':
    main()
