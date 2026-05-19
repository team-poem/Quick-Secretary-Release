"""AI공학 섹션 교체 v4 — Find 기반 정확한 위치 잡기.

전략:
  1) 수정본 읽기
  2) 마스터에서 "가. AI공학 융합연계전공" 텍스트를 Find로 찾기 → 커서 위치 확정
  3) 거기서부터 "다. AI콘텐츠" 직전까지 선택 → 삭제
  4) 수정본 내용 삽입
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정_v4.hwp')


def read_paragraphs_with_content(hwp):
    """내용 있는 문단만 읽기."""
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


def find_text_position(hwp, search_text):
    """텍스트를 찾아 커서를 그 위치로 이동. 성공 여부 반환."""
    hwp.HAction.Run("MoveDocBegin")

    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("FindReplace", pset.HSet)
    pset.FindString = search_text
    pset.IgnoreMessage = 1
    pset.HSet.SetItem("IgnoreCase", 0)
    pset.HSet.SetItem("WholeWordOnly", 0)
    pset.Direction = 0

    return hwp.HAction.Execute("FindReplace", pset.HSet)


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
        source_paras = read_paragraphs_with_content(hwp)
        print(f"  {len(source_paras)}개 문단")
        for i, p in enumerate(source_paras):
            print(f"  [{i}] {p[:80]}{'...' if len(p)>80 else ''}")
        hwp.Clear(1)

        # === STEP 2: 마스터 열기 ===
        print("\n[STEP 2] 마스터 열기")
        hwp.Open(MASTER)

        # 교체 전 주변 확인
        print("\n  교체 전 주변 문단:")
        all_paras = read_paragraphs_with_content(hwp)
        for i, p in enumerate(all_paras):
            if '가. AI공학' in p:
                for j in range(max(0, i-1), min(len(all_paras), i+8)):
                    print(f"  [{j}] {all_paras[j][:70]}")
                break

        # === STEP 3: "가. AI공학 융합연계전공" 찾아서 선택 범위 잡기 ===
        print("\n[STEP 3] 정확한 위치 찾기 (Find)")

        # "가. AI공학 융합연계전공" 찾기
        found = find_text_position(hwp, "가. AI공학 융합연계전공")
        if not found:
            print("[FAIL] '가. AI공학 융합연계전공' 찾지 못함")
            return
        print("  '가. AI공학 융합연계전공' 발견")

        # 찾은 텍스트의 문단 처음으로 이동
        hwp.HAction.Run("MoveParaBegin")

        # 여기서부터 "다. AI콘텐츠" 직전까지 선택해야 함
        # 방법: 다음 문단으로 하나씩 이동하면서 "다." 시작하는 문단 찾기
        # 선택 모드로 이동하여 범위를 잡는다

        # 우선 "다. AI콘텐츠 융합연계전공"의 위치도 Find로 찾아두자
        # 현재 위치 저장
        pos_start = hwp.GetPos()
        print(f"  시작 위치: {pos_start}")

        # "다. AI콘텐츠" 찾기
        found2 = find_text_position(hwp, "다. AI콘텐츠 융합연계전공")
        if not found2:
            # 대안: "나." 로 찾기
            found2 = find_text_position(hwp, "나.")
        if found2:
            hwp.HAction.Run("MoveParaBegin")
            pos_end = hwp.GetPos()
            print(f"  끝 위치 (다. AI콘텐츠): {pos_end}")
        else:
            print("[FAIL] 다음 섹션을 찾지 못함")
            return

        # === STEP 4: 범위 선택 + 삭제 + 삽입 ===
        print("\n[STEP 4] 교체 실행")

        # "가. AI공학" 문단 처음으로 돌아가기
        hwp.SetPos(*pos_start)
        hwp.HAction.Run("MoveParaBegin")

        # "다. AI콘텐츠" 문단 직전까지 선택
        # SetPos로 끝 위치 설정은 안 되니까, 선택 모드로 이동
        # 방법: 블록 선택 시작 → 끝 위치로 이동

        # 블록 선택 방법 1: HAction으로 Select 범위 지정
        # MoveParaBegin에서 시작하여 SelectNextPara를 반복하면서 "다."를 만날 때까지
        hwp.HAction.Run("MoveParaBegin")

        # 최대 50번 시도 (안전장치)
        selected_count = 0
        for _ in range(50):
            # 현재 문단 텍스트 확인을 위해 한 문단 더 선택
            hwp.HAction.Run("MoveSelectNextParaBegin")
            selected_count += 1

            # 현재 커서 위치 확인
            cur_pos = hwp.GetPos()
            if cur_pos[0] == pos_end[0] and cur_pos[1] == pos_end[1] and cur_pos[2] == pos_end[2]:
                # "다. AI콘텐츠" 문단 시작에 도달
                print(f"  {selected_count}개 문단 선택 완료 (다. AI콘텐츠 직전까지)")
                break
        else:
            print(f"  [WARN] 50개 문단 선택 후 중단")

        # 선택 영역 삭제
        hwp.HAction.Run("Delete")
        print(f"  삭제 완료")

        # 새 내용 삽입
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp.HAction.Execute("InsertText", pset.HSet)

        # 마지막에 문단 구분 추가 (다음 섹션과 분리)
        hwp.HAction.Run("BreakPara")
        print(f"  {len(source_paras)}개 문단 삽입 완료")

        # === STEP 5: 검증 ===
        print("\n[STEP 5] 검증")
        verify_paras = read_paragraphs_with_content(hwp)

        # AI공학 주변 확인
        for i, p in enumerate(verify_paras):
            if '가. AI공학' in p:
                print(f"  교체 결과:")
                for j in range(max(0, i-1), min(len(verify_paras), i+18)):
                    marker = ">>" if i <= j < i + len(source_paras) else "  "
                    print(f"  {marker} [{j}] {verify_paras[j][:70]}{'...' if len(verify_paras[j])>70 else ''}")
                break

        # "수정해야함" 남아있는지 체크
        remaining = [p for p in verify_paras if p.strip() == '수정해야함']
        if remaining:
            print(f"\n  [INFO] '수정해야함' {len(remaining)}건 남아있음 (다른 섹션의 것일 수 있음)")
            for i, p in enumerate(verify_paras):
                if p.strip() == '수정해야함':
                    context = verify_paras[i-1][:50] if i > 0 else ""
                    print(f"    [{i}] 앞 문단: \"{context}\"")
        else:
            print(f"\n  [OK] '수정해야함' 완전히 제거됨")

        # === STEP 6: 저장 ===
        print("\n[STEP 6] 저장")
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
