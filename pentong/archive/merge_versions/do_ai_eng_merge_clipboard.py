"""AI공학 섹션 교체 — 클립보드 방식 (표/서식 보존).

전략:
  1) 수정본 열기 → 제목 빼고 본문만 선택 → 복사
  2) 마스터 열기 → "수정해야함" 찾기(선택됨) → 붙여넣기
  → 표, 서식, 이미지 모두 보존됨
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정.hwp')


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

        # ==============================
        # STEP 1: 수정본에서 본문 복사
        # ==============================
        print("\n[1] 수정본 열기 → 본문 복사")
        hwp.Open(SOURCE)

        # 첫 문단(제목 "가. AI공학 융합연계전공")을 건너뛰고 본문만 선택
        hwp.HAction.Run("MoveDocBegin")
        hwp.HAction.Run("MoveNextParaBegin")  # 제목 건너뜀 → 2번째 문단 시작
        hwp.HAction.Run("MoveParaBegin")

        # Ctrl+Shift+End: 현재 위치에서 문서 끝까지 선택
        hwp.HAction.Run("MoveSelectDocEnd")
        hwp.HAction.Run("Copy")
        print("  본문 복사 완료 (제목 제외, 표/서식 포함)")

        hwp.Clear(1)  # 수정본 닫기

        # ==============================
        # STEP 2: 마스터에서 "수정해야함" 찾아서 붙여넣기
        # ==============================
        print("\n[2] 마스터 열기 → '수정해야함' 교체")
        hwp.Open(MASTER)

        # "수정해야함" 찾기 (RepeatFind로 해당 텍스트가 선택됨)
        hwp.HAction.Run("MoveDocBegin")
        pset = hwp.HParameterSet.HFindReplace
        hwp.HAction.GetDefault("RepeatFind", pset.HSet)
        pset.FindString = "수정해야함"
        pset.IgnoreMessage = 1
        found = hwp.HAction.Execute("RepeatFind", pset.HSet)

        if not found:
            print("  [FAIL] '수정해야함' 찾지 못함")
            return

        print("  '수정해야함' 발견 → 선택 상태")

        # 선택된 "수정해야함"을 클립보드 내용으로 교체 (붙여넣기)
        hwp.HAction.Run("Paste")
        print("  붙여넣기 완료 (표/서식 포함)")

        # ==============================
        # STEP 3: 검증
        # ==============================
        print("\n[3] 검증")
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

        for i, p in enumerate(paras):
            if 'AI공학' in p and p.startswith('가.'):
                print("  교체 결과:")
                for j in range(i, min(len(paras), i + 18)):
                    print(f"  [{j}] {paras[j][:70]}{'...' if len(paras[j])>70 else ''}")
                break

        remain = sum(1 for p in paras if '수정해야함' in p)
        print(f"\n  '수정해야함' 잔여: {remain}건")

        # ==============================
        # STEP 4: 저장
        # ==============================
        print(f"\n[4] 저장")
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
