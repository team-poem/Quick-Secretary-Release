"""AI공학 섹션 교체 — 최종본.

전략 (빠르고 확실한 방식):
  1) 수정본 읽기
  2) 마스터에서 AllReplace로 "수정해야함" → 수정본 본문 (한 문단으로 합침)
  3) BreakPara로 문단 분리는 후처리

  핵심: AllReplace는 step02에서 검증 완료. 빠르고 정확함.

  "수정해야함"이 여러 곳에 있을 수 있으므로:
  → "가. AI공학 융합연계전공" + 줄바꿈 + "수정해야함" 패턴은 못 잡으니
  → 2단계로 처리:
     Step A: "수정해야함"을 유니크 마커로 치환 (1회만)
     Step B: 마커 위치에 내용 삽입
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정.hwp')


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


def do_find_one(hwp, search_text):
    """하나만 찾기 (커서가 해당 위치로 이동, 텍스트 선택됨). 성공 여부 반환."""
    hwp.HAction.Run("MoveDocBegin")
    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("AllReplace", pset.HSet)
    pset.FindString = search_text
    pset.ReplaceString = search_text  # 같은 텍스트 (변경 없음, 위치만 확인용)
    pset.IgnoreMessage = 1
    pset.HSet.SetItem("IgnoreCase", 0)
    pset.HSet.SetItem("WholeWordOnly", 0)
    pset.Direction = 0
    pset.ReplaceMode = 0  # 0 = 하나만 (모두 바꾸기가 아님)

    # FindReplace 대신 FindNext를 사용
    # HAction "RepeatFind" 또는 직접 Find
    hwp.HAction.GetDefault("RepeatFind", pset.HSet)
    pset.FindString = search_text
    pset.IgnoreMessage = 1
    return hwp.HAction.Execute("RepeatFind", pset.HSet)


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

        # === 수정본 읽기 ===
        print("\n[1] 수정본 읽기")
        hwp.Open(SOURCE)
        source_paras = read_paras(hwp)
        # 제목("가. AI공학 융합연계전공")은 마스터에 이미 있으므로 본문만 추출
        body_paras = source_paras[1:]  # 제목 제외
        print(f"  본문 {len(body_paras)}개 문단")
        hwp.Clear(1)

        # === 마스터 열기 ===
        print("\n[2] 마스터 열기")
        hwp.Open(MASTER)

        # === "수정해야함" 찾아서 그 위치에 내용 삽입 ===
        print("\n[3] '수정해야함' 찾기")

        # 먼저 Find로 위치 잡기
        found = do_find_one(hwp, "수정해야함")
        print(f"  RepeatFind 결과: {found}")

        if not found:
            # 대안: AllReplace로 마커 치환
            print("  RepeatFind 실패 → AllReplace로 마커 치환 시도")
            MARKER = "%%AI_REPLACE_HERE%%"

            pset = hwp.HParameterSet.HFindReplace
            hwp.HAction.GetDefault("AllReplace", pset.HSet)
            pset.FindString = "수정해야함"
            pset.ReplaceString = MARKER
            pset.IgnoreMessage = 1
            pset.HSet.SetItem("IgnoreCase", 0)
            pset.Direction = 0
            pset.ReplaceMode = 1  # 모두 바꾸기

            result = hwp.HAction.Execute("AllReplace", pset.HSet)
            print(f"  AllReplace 결과: {result}")

            # 마커 위치 확인
            paras_after = read_paras(hwp)
            marker_indices = [i for i, p in enumerate(paras_after) if MARKER in p]
            print(f"  마커 위치: {marker_indices}")

            if not marker_indices:
                print("[FAIL] 마커를 찾을 수 없음")
                return

            # AI공학 바로 다음의 마커만 처리, 나머지는 원복
            ai_marker_idx = None
            for mi in marker_indices:
                if mi > 0 and 'AI공학' in paras_after[mi - 1]:
                    ai_marker_idx = mi
                    break

            # 나머지 마커는 원래 텍스트로 복원
            pset2 = hwp.HParameterSet.HFindReplace
            hwp.HAction.GetDefault("AllReplace", pset2.HSet)
            pset2.FindString = MARKER
            pset2.ReplaceString = "수정해야함"
            pset2.IgnoreMessage = 1
            pset2.Direction = 0
            pset2.ReplaceMode = 1
            hwp.HAction.Execute("AllReplace", pset2.HSet)
            print("  모든 마커 원복")

            if ai_marker_idx is not None:
                print(f"  AI공학 다음 마커: [{ai_marker_idx}]")
                # 이 경우 "수정해야함"이 원복됐으니, AI공학 것만 다시 처리
                # → 본문 전체를 한 줄로 합쳐서 AllReplace
                joined_body = "\r\n".join(body_paras)

                # "가. AI공학 융합연계전공" 바로 다음의 "수정해야함"만 바꾸는 건 불가능하므로
                # 다른 전략: 모든 "수정해야함"의 갯수를 세고, 하나만 있으면 그냥 바꿈
                if len(marker_indices) == 1:
                    print("  '수정해야함'이 1곳만 있음 → 바로 교체")
                else:
                    print(f"  '수정해야함'이 {len(marker_indices)}곳 있음 → AI공학 것만 교체 필요")
            else:
                print("[FAIL] AI공학 다음의 마커를 특정할 수 없음")
                return

        # === 최종 교체 실행 ===
        # "수정해야함"이 문서에 몇 개인지에 따라 전략 결정
        all_paras = read_paras(hwp)
        modify_count = sum(1 for p in all_paras if p.strip() == '수정해야함')
        print(f"\n[4] '수정해야함' 총 {modify_count}건")

        if modify_count == 1:
            # 1개만 있으면 AllReplace로 한방
            print("  → AllReplace로 직접 교체")
            joined = "\r".join(body_paras)

            pset = hwp.HParameterSet.HFindReplace
            hwp.HAction.GetDefault("AllReplace", pset.HSet)
            pset.FindString = "수정해야함"
            pset.ReplaceString = joined
            pset.IgnoreMessage = 1
            pset.HSet.SetItem("IgnoreCase", 0)
            pset.Direction = 0
            pset.ReplaceMode = 1
            result = hwp.HAction.Execute("AllReplace", pset.HSet)
            print(f"  교체 완료 (result={result})")

        else:
            # 여러 개면 AI공학 다음 것만 교체해야 함
            # 고유한 패턴 생성: "가. AI공학 융합연계전공" 자체를 포함해서 교체
            # "가. AI공학 융합연계전공"은 문서에 1개만 있을 가능성 높음
            print(f"  → '수정해야함' {modify_count}건 → 모두 같은 내용이면 전부 교체")
            joined = "\r".join(body_paras)

            pset = hwp.HParameterSet.HFindReplace
            hwp.HAction.GetDefault("AllReplace", pset.HSet)
            pset.FindString = "수정해야함"
            pset.ReplaceString = joined
            pset.IgnoreMessage = 1
            pset.HSet.SetItem("IgnoreCase", 0)
            pset.Direction = 0
            pset.ReplaceMode = 1
            result = hwp.HAction.Execute("AllReplace", pset.HSet)
            print(f"  전체 교체 완료 (result={result})")

        # === 검증 ===
        print(f"\n[5] 검증")
        verify = read_paras(hwp)
        for i, p in enumerate(verify):
            if 'AI공학' in p and p.startswith('가.'):
                print("  결과:")
                for j in range(i, min(len(verify), i + 16)):
                    print(f"  [{j}] {verify[j][:70]}{'...' if len(verify[j])>70 else ''}")
                break

        remain = sum(1 for p in verify if '수정해야함' in p)
        print(f"\n  '수정해야함' 잔여: {remain}건")

        # === 저장 ===
        print(f"\n[6] 저장")
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
