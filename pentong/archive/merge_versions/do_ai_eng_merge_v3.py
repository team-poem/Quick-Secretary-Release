"""AI공학 섹션 교체 v3 — 빈 문단 포함한 정확한 커서 위치 계산.

v2 문제: read에서 빈 문단 스킵 → 커서 이동 시 번호 불일치
수정: 빈 문단도 포함하여 인덱스 계산
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정_v3.hwp')


def read_all_paragraphs_raw(hwp):
    """빈 문단 포함 모든 문단을 읽는다. 실제 문단 번호와 1:1 대응."""
    hwp.HAction.Run("MoveDocBegin")
    hwp.InitScan(0x0010)
    paras = []
    while True:
        state, text = hwp.GetText()
        paras.append(text if text else "")
        if state in (0, 1):
            break
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

        # === STEP 1: 수정본 읽기 ===
        print("\n[STEP 1] 수정본 읽기")
        hwp.Open(SOURCE)
        source_raw = read_all_paragraphs_raw(hwp)
        # 수정본은 strip된 버전으로 표시하되, 삽입 시 원본 사용
        source_paras = [p for p in source_raw if p.strip()]
        print(f"  전체 {len(source_raw)}개 문단 (내용 있는 것: {len(source_paras)}개)")
        for i, p in enumerate(source_paras[:5]):
            print(f"  [{i}] {p.strip()[:80]}")
        if len(source_paras) > 5:
            print(f"  ... ({len(source_paras)}개)")
        hwp.Clear(1)

        # === STEP 2: 마스터 열기 ===
        print("\n[STEP 2] 마스터 열기")
        hwp.Open(MASTER)
        master_raw = read_all_paragraphs_raw(hwp)
        print(f"  총 {len(master_raw)}개 문단 (빈 문단 포함)")

        # === STEP 3: 정확한 위치 찾기 ===
        print("\n[STEP 3] 위치 찾기")

        # "가. AI공학 융합연계전공" 과 "수정해야함" 찾기
        target_start = None
        target_end = None
        for i, p in enumerate(master_raw):
            if p.strip().startswith('가. AI공학'):
                target_start = i
                print(f"  시작: [{i}] \"{p.strip()[:60]}\"")
                # 이 다음부터 "다." 또는 "나." 시작하는 문단까지가 범위
                for j in range(i + 1, min(i + 30, len(master_raw))):
                    nxt = master_raw[j].strip()
                    if nxt.startswith(('나.', '다.', '라.', '마.')):
                        target_end = j  # 이 문단 직전까지 교체
                        print(f"  끝 (직전): [{j}] \"{nxt[:60]}\"")
                        break
                    elif nxt:
                        print(f"    [{j}] \"{nxt[:50]}\"")
                break

        if target_start is None:
            print("[FAIL] '가. AI공학' 찾지 못함")
            return

        if target_end is None:
            target_end = target_start + 2
            print(f"  끝을 못 찾아 기본값 사용: [{target_end}]")

        replace_count = target_end - target_start
        print(f"\n  교체 범위: [{target_start}]~[{target_end - 1}] ({replace_count}개 문단)")
        print(f"  보존될 다음 문단: [{target_end}] \"{master_raw[target_end].strip()[:60]}\"")

        # === STEP 4: 찾아서 교체 (FindReplace 대신 커서 이동) ===
        print(f"\n[STEP 4] 교체 실행")

        # 문서 처음으로 이동 후 target_start까지 문단 이동
        hwp.HAction.Run("MoveDocBegin")
        for _ in range(target_start):
            hwp.HAction.Run("MoveNextParaBegin")
        hwp.HAction.Run("MoveParaBegin")

        # 현재 위치 확인 (디버그)
        # 커서가 있는 문단의 텍스트를 읽어서 확인
        hwp.HAction.Run("MoveParaBegin")
        hwp.HAction.Run("MoveSelectParaEnd")
        # 선택 해제하고 다시 시작
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("MoveParaBegin")

        # 기존 문단 선택 (replace_count개)
        for _ in range(replace_count - 1):
            hwp.HAction.Run("MoveSelectNextParaBegin")
        hwp.HAction.Run("MoveSelectParaEnd")

        # 삭제
        hwp.HAction.Run("Delete")
        print(f"  {replace_count}개 문단 삭제")

        # 새 내용 삽입 (내용 있는 문단만)
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para.strip()
            hwp.HAction.Execute("InsertText", pset.HSet)
        print(f"  {len(source_paras)}개 문단 삽입")

        # === STEP 5: 검증 ===
        print(f"\n[STEP 5] 검증")
        verify_raw = read_all_paragraphs_raw(hwp)
        print(f"  교체 후: {len(verify_raw)}개 문단 (이전: {len(master_raw)}, 차이: {len(verify_raw)-len(master_raw):+d})")

        # 교체 영역 주변 확인
        print(f"\n  교체 영역 주변:")
        check_start = max(0, target_start - 2)
        check_end = min(len(verify_raw), target_start + len(source_paras) + 3)
        for i in range(check_start, check_end):
            p = verify_raw[i].strip()
            if not p:
                continue
            if target_start <= i < target_start + len(source_paras):
                marker = ">>"  # 새로 삽입된 부분
            else:
                marker = "  "
            print(f"  {marker} [{i}] {p[:70]}{'...' if len(p)>70 else ''}")

        # === STEP 6: 저장 ===
        print(f"\n[STEP 6] 저장")
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
            print("\n[OK] 한글 종료")


if __name__ == '__main__':
    main()
