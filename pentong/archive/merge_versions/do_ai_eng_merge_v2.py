"""AI공학 섹션 교체 v2 — 정확한 범위만 교체.

마스터에서:
  [3701] 가. AI공학 융합연계전공
  [3702] 수정해야함
이 2개 문단만 수정본 14개 문단으로 교체.
"다. AI콘텐츠" 등 다른 융합연계전공은 건드리지 않음.
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정_v2.hwp')


def read_all_paragraphs(hwp):
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

        # === STEP 1: 수정본 읽기 ===
        print("\n[STEP 1] 수정본 읽기")
        hwp.Open(SOURCE)
        source_paras = read_all_paragraphs(hwp)
        print(f"  {len(source_paras)}개 문단:")
        for i, p in enumerate(source_paras):
            print(f"  [{i}] {p[:80]}{'...' if len(p)>80 else ''}")
        hwp.Clear(1)

        # === STEP 2: 마스터 열기 + 정확한 위치 확인 ===
        print("\n[STEP 2] 마스터 열기")
        hwp.Open(MASTER)
        master_paras = read_all_paragraphs(hwp)
        print(f"  총 {len(master_paras)}개 문단")

        # "가. AI공학 융합연계전공" 찾기
        section_start = None
        for i, p in enumerate(master_paras):
            if p.strip().startswith('가. AI공학'):
                section_start = i
                break

        if section_start is None:
            print("[FAIL] '가. AI공학' 섹션을 찾지 못함")
            return

        # 섹션 끝 찾기: 다음 "나." 또는 "다." 등 형제 항목이 시작되는 곳
        section_end = section_start + 1
        for i in range(section_start + 1, min(section_start + 50, len(master_paras))):
            p = master_paras[i].strip()
            # 같은 레벨의 형제 항목: "나.", "다.", "라." 등 또는 상위 섹션
            if (p.startswith(('나.', '다.', '라.', '마.', '바.', '사.')) or
                p.startswith('▮') or
                p.startswith(('Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ'))):
                section_end = i
                break
        else:
            section_end = section_start + 2  # 최소 제목 + "수정해야함"

        replace_count = section_end - section_start

        print(f"\n  교체 범위: 문단 [{section_start}]~[{section_end - 1}] ({replace_count}개 문단)")
        for i in range(section_start, section_end):
            print(f"    [{i}] {master_paras[i][:70]}")
        print(f"  다음 문단 (유지): [{section_end}] {master_paras[section_end][:70]}")

        # === STEP 3: 교체 ===
        print(f"\n[STEP 3] 교체: {replace_count}개 문단 → {len(source_paras)}개 문단")

        # 커서를 section_start로 이동
        hwp.HAction.Run("MoveDocBegin")
        for _ in range(section_start):
            hwp.HAction.Run("MoveNextParaBegin")
        hwp.HAction.Run("MoveParaBegin")

        # 기존 내용 선택 + 삭제
        if replace_count > 1:
            for _ in range(replace_count - 1):
                hwp.HAction.Run("MoveSelectNextParaBegin")
        hwp.HAction.Run("MoveSelectParaEnd")
        hwp.HAction.Run("Delete")
        print(f"  기존 {replace_count}개 문단 삭제 완료")

        # 새 내용 삽입
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp.HAction.Execute("InsertText", pset.HSet)
        print(f"  새 내용 {len(source_paras)}개 문단 삽입 완료")

        # === STEP 4: 검증 ===
        print(f"\n[STEP 4] 검증")
        verify_paras = read_all_paragraphs(hwp)
        print(f"  교체 후 총 문단: {len(verify_paras)} (이전: {len(master_paras)}, 차이: {len(verify_paras)-len(master_paras):+d})")

        # 교체된 부분 확인
        print(f"\n  교체된 영역:")
        for i in range(section_start, min(section_start + len(source_paras) + 2, len(verify_paras))):
            marker = "  " if i >= section_start + len(source_paras) else ">>"
            print(f"  {marker} [{i}] {verify_paras[i][:70]}{'...' if len(verify_paras[i])>70 else ''}")

        # 다음 섹션이 살아있는지 확인
        next_section_idx = section_start + len(source_paras)
        if next_section_idx < len(verify_paras):
            nxt = verify_paras[next_section_idx].strip()
            if nxt.startswith('다.') or nxt.startswith('나.'):
                print(f"\n  [OK] 다음 섹션 정상 유지: \"{nxt[:60]}\"")
            else:
                print(f"\n  [WARN] 다음 문단 확인 필요: \"{nxt[:60]}\"")

        # === STEP 5: 저장 ===
        print(f"\n[STEP 5] 저장")
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
