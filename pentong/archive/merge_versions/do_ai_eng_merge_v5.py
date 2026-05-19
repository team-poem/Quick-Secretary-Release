"""AI공학 섹션 교체 v5 — 문단 순회 + GetPos로 정확한 위치 확보.

전략:
  문단을 하나씩 MoveNextParaBegin으로 이동하면서 텍스트 확인.
  GetPos()로 절대 위치를 저장해두고, SetPos()로 정확히 돌아감.
  이 방식은 빈 문단 문제를 완전히 회피함.
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정_v5.hwp')


def read_source(hwp):
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


def get_current_para_text(hwp):
    """현재 커서가 있는 문단의 텍스트를 반환 (커서 위치 유지)."""
    pos = hwp.GetPos()
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelectParaEnd")

    # GetTextFile로 선택 영역 텍스트 가져오기
    # 대안: 짧게 읽기
    hwp.InitScan(0x0012)  # 선택 영역 스캔
    parts = []
    while True:
        state, text = hwp.GetText()
        if text:
            parts.append(text)
        if state in (0, 1):
            break
    hwp.ReleaseScan()

    hwp.HAction.Run("Cancel")  # 선택 해제
    hwp.SetPos(*pos)  # 원래 위치 복원
    return "".join(parts).strip()


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
        source_paras = read_source(hwp)
        print(f"  {len(source_paras)}개 문단")
        hwp.Clear(1)

        # === STEP 2: 마스터 열기 + 위치 찾기 ===
        print("\n[STEP 2] 마스터 열기 + 위치 탐색")
        hwp.Open(MASTER)

        # 문단을 순회하며 "가. AI공학"과 "다. AI콘텐츠" 위치를 찾는다
        hwp.HAction.Run("MoveDocBegin")

        pos_ai_start = None      # "가. AI공학" 문단 시작 위치
        pos_next_section = None   # "다. AI콘텐츠" 문단 시작 위치
        prev_pos = None

        for step in range(20000):  # 안전장치
            cur_pos = hwp.GetPos()

            # 무한루프 방지: 위치가 안 변하면 문서 끝
            if prev_pos and cur_pos == prev_pos:
                print(f"  문서 끝 도달 (step {step})")
                break
            prev_pos = cur_pos

            # 현재 문단 텍스트 확인 (빠른 방법: InitScan 대신 간단 체크)
            hwp.HAction.Run("MoveParaBegin")
            hwp.HAction.Run("MoveSelectParaEnd")
            # 선택 영역 스캔
            hwp.InitScan(0x0012)
            text = ""
            while True:
                st, t = hwp.GetText()
                if t:
                    text += t
                if st in (0, 1):
                    break
            hwp.ReleaseScan()
            hwp.HAction.Run("Cancel")
            text = text.strip()

            # "가. AI공학" 찾기
            if pos_ai_start is None and 'AI공학' in text and text.startswith('가.'):
                pos_ai_start = cur_pos
                print(f"  [step {step}] 발견: \"{text[:50]}\" pos={cur_pos}")

            # "가." 찾은 후 "다." 찾기
            if pos_ai_start is not None and pos_next_section is None:
                if text.startswith('다.') and '콘텐츠' in text:
                    pos_next_section = cur_pos
                    print(f"  [step {step}] 다음 섹션: \"{text[:50]}\" pos={pos_next_section}")
                    break

            # 다음 문단으로
            hwp.HAction.Run("MoveNextParaBegin")

            # 진행 표시
            if step % 1000 == 0 and step > 0:
                print(f"  ... {step}개 문단 탐색 중")

        if pos_ai_start is None:
            print("[FAIL] 'AI공학' 섹션 못 찾음")
            return
        if pos_next_section is None:
            print("[FAIL] 다음 섹션(다. AI콘텐츠) 못 찾음")
            return

        # === STEP 3: 교체 실행 ===
        print(f"\n[STEP 3] 교체 실행")

        # "가. AI공학" 문단 시작으로 이동
        hwp.SetPos(*pos_ai_start)
        hwp.HAction.Run("MoveParaBegin")

        # "다. AI콘텐츠" 문단 시작 직전까지 선택
        # SetPos로 끝 위치 잡고 선택은 안 됨 → 선택 모드로 이동
        # 방법: 현재 위치에서 Select 모드로 "다." 위치까지 이동

        # Shift+이동 = MoveSelect... 를 반복해서 pos_next_section까지 이동
        for _ in range(200):  # 안전장치 (최대 200 문단)
            cur = hwp.GetPos()
            if cur[0] == pos_next_section[0] and cur[1] == pos_next_section[1] and cur[2] >= pos_next_section[2]:
                break
            hwp.HAction.Run("MoveSelectNextParaBegin")
        else:
            print("[WARN] 선택 범위 제한 도달")

        # 선택 영역 삭제
        hwp.HAction.Run("Delete")
        print(f"  기존 내용 삭제 완료")

        # 새 내용 삽입
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp.HAction.Execute("InsertText", pset.HSet)

        # 다음 섹션과 구분용 줄바꿈
        hwp.HAction.Run("BreakPara")
        print(f"  {len(source_paras)}개 문단 삽입 완료")

        # === STEP 4: 검증 ===
        print(f"\n[STEP 4] 검증")
        verify = read_source(hwp)
        for i, p in enumerate(verify):
            if 'AI공학' in p and p.startswith('가.'):
                print("  교체 결과:")
                for j in range(max(0, i-1), min(len(verify), i+18)):
                    marker = ">>" if i <= j < i + len(source_paras) else "  "
                    print(f"  {marker} [{j}] {verify[j][:70]}{'...' if len(verify[j])>70 else ''}")
                break

        remain = sum(1 for p in verify if p.strip() == '수정해야함')
        if remain == 0:
            print(f"\n  [OK] '수정해야함' 완전 제거됨")
        else:
            print(f"\n  [INFO] '수정해야함' {remain}건 남음 (다른 섹션)")

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
            print("[OK] 한글 종료")


if __name__ == '__main__':
    main()
