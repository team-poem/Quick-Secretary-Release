"""
Step 4: 섹션 내용 교체 (실제 업무 프로세스)
- 마스터 문서(요람)에서 특정 섹션을 찾고
- 수정본 파일의 전체 내용을 읽어서
- 마스터의 해당 섹션 본문을 수정본 내용으로 교체

실제 시나리오:
  각 전공에서 수정된 파일이 따로 옴 (해당 전공 내용만 들어있음)
  → 마스터 요람에서 해당 전공 섹션을 찾아서 내용 교체

사용법:
  python step04_section_replace.py 마스터.hwp 수정본.hwp "섹션키워드"

예시:
  python step04_section_replace.py 2025교육혁신처.hwp AI공학_수정본.hwpx "AI공학"
"""
import sys
import os


def extract_paragraphs(hwp):
    """문서에서 모든 문단을 추출"""
    hwp.HAction.Run("MoveDocBegin")
    hwp.InitScan(0x0010)

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
    return paragraphs


def is_heading(para):
    """제목 후보인지 판별"""
    return len(para) < 80 and (
        "전공" in para
        or "학과" in para
        or para.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))
        or para.startswith(("I.", "II.", "III.", "IV.", "V."))
        or para.startswith(("제1", "제2", "제3"))
        or para.startswith(("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"))
        or para.startswith(("▮", "∙"))
        or para.startswith(("가.", "나.", "다.", "라.", "마."))
    )


def find_section(paragraphs, keyword):
    """키워드가 포함된 섹션의 (시작, 끝, 제목) 목록 반환"""
    headings = []
    for i, para in enumerate(paragraphs):
        if is_heading(para):
            headings.append(i)

    results = []
    for hi, idx in enumerate(headings):
        if keyword in paragraphs[idx]:
            start = idx
            end = headings[hi + 1] if hi + 1 < len(headings) else len(paragraphs)
            results.append((start, end, paragraphs[idx]))

    return results


def main():
    if len(sys.argv) < 4:
        print('사용법: python step04_section_replace.py 마스터.hwp 수정본.hwp "섹션키워드"')
        return

    master_path = os.path.abspath(sys.argv[1])
    source_path = os.path.abspath(sys.argv[2])
    keyword = sys.argv[3]

    for path in [master_path, source_path]:
        if not os.path.exists(path):
            print(f"[FAIL] 파일 없음: {path}")
            return

    import win32com.client as win32
    hwp = None

    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")

        # 1) 수정본 전체 내용 읽기
        print(f"[1/4] 수정본 읽기: {os.path.basename(source_path)}")
        hwp.Open(source_path)
        source_paras = extract_paragraphs(hwp)
        print(f"  총 {len(source_paras)}개 문단")
        print(f"  첫 줄: {source_paras[0][:60] if source_paras else '(비어있음)'}...")
        hwp.Clear(1)

        # 2) 마스터 문서 열기 + 섹션 찾기
        print(f"\n[2/4] 마스터 문서 열기: {os.path.basename(master_path)}")
        hwp.Open(master_path)
        master_paras = extract_paragraphs(hwp)
        print(f"  총 {len(master_paras)}개 문단")

        master_sections = find_section(master_paras, keyword)
        if not master_sections:
            # 제목 후보가 아니더라도 키워드가 포함된 문단 검색
            print(f"  제목 후보에서 \"{keyword}\" 못 찾음. 전체 문단에서 검색...")
            for i, para in enumerate(master_paras):
                if keyword in para and len(para) < 100:
                    print(f"  [{i}] {para[:80]}")
            print(f"[FAIL] \"{keyword}\" 섹션을 찾지 못함")
            return

        # 여러 매칭 시 사용자에게 보여주기
        if len(master_sections) > 1:
            print(f"\n  \"{keyword}\" 포함 섹션 {len(master_sections)}개 발견:")
            for i, (start, end, title) in enumerate(master_sections):
                print(f"    [{i}] 문단 {start}~{end-1} ({end-start}개) : {title}")
            print(f"  → 첫 번째 섹션 사용")

        mst_start, mst_end, mst_title = master_sections[0]
        body_count = mst_end - mst_start - 1
        print(f"\n  대상 섹션: \"{mst_title}\"")
        print(f"  위치: 문단 {mst_start}~{mst_end - 1} (본문 {body_count}개 문단)")

        # 3) 비교: 현재 마스터 섹션 본문 vs 수정본 내용
        print(f"\n[3/4] 내용 비교")
        master_body = master_paras[mst_start + 1:mst_end]

        print(f"  마스터 본문: {len(master_body)}개 문단")
        for j, p in enumerate(master_body[:3]):
            print(f"    {p[:70]}{'...' if len(p) > 70 else ''}")
        if len(master_body) > 3:
            print(f"    ... ({len(master_body) - 3}개 더)")

        print(f"  수정본 내용: {len(source_paras)}개 문단")
        for j, p in enumerate(source_paras[:3]):
            print(f"    {p[:70]}{'...' if len(p) > 70 else ''}")
        if len(source_paras) > 3:
            print(f"    ... ({len(source_paras) - 3}개 더)")

        if master_body == source_paras:
            print("\n  내용이 동일합니다. 교체 불필요.")
            return

        print(f"\n  → 내용이 다릅니다. 교체를 진행합니다.")

        # 4) 교체 실행
        print(f"\n[4/4] 섹션 교체")

        # 제목 다음 문단(본문 시작)으로 커서 이동
        hwp.HAction.Run("MoveDocBegin")
        for _ in range(mst_start + 1):
            hwp.HAction.Run("MoveNextParaBegin")
        hwp.HAction.Run("MoveParaBegin")

        # 기존 본문 선택 및 삭제
        if body_count > 0:
            for _ in range(body_count - 1):
                hwp.HAction.Run("MoveSelectNextParaBegin")
            hwp.HAction.Run("MoveSelectParaEnd")
            hwp.HAction.Run("Delete")
            print(f"  기존 본문 {body_count}개 문단 삭제")

        # 새 내용 삽입
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp.HAction.Execute("InsertText", pset.HSet)

        print(f"  새 내용 {len(source_paras)}개 문단 삽입")

        # 다른 이름으로 저장
        name, ext = os.path.splitext(master_path)
        save_path = f"{name}_merged{ext}"
        hwp.SaveAs(save_path)
        print(f"\n[OK] 저장: {save_path}")
        print(f"  \"{mst_title}\" 섹션이 수정본 내용으로 교체되었습니다.")

    except Exception as e:
        print(f"[FAIL] 오류: {e}")
        import traceback
        traceback.print_exc()

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
