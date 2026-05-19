"""AI공학 섹션 교체 — 수정본 → 마스터 삽입.

동작:
  1) 수정본(AI공학_대학요람_김효원선생님.hwpx) 전체 내용 읽기
  2) 마스터(2025교육혁신처_20260409.hwp) 열기
  3) 마스터에서 AI공학 섹션 찾기
  4) 해당 섹션 본문을 수정본 내용으로 교체
  5) _merged.hwp로 저장
"""
import sys, os, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, 'AI공학_대학요람_김효원선생님.hwpx')
MASTER = os.path.join(BASE, '2025교육혁신처_20260409.hwp')
OUTPUT = os.path.join(BASE, '2025교육혁신처_20260409_AI공학수정.hwp')


def read_all_paragraphs(hwp):
    """문서의 모든 문단 텍스트를 리스트로 반환."""
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
        print("[OK] 한글 프로그램 연결")

        # ============================================================
        # STEP 1: 수정본 읽기
        # ============================================================
        print(f"\n{'='*60}")
        print(f"[STEP 1] 수정본 읽기: {os.path.basename(SOURCE)}")
        print(f"{'='*60}")

        hwp.Open(SOURCE)
        source_paras = read_all_paragraphs(hwp)
        print(f"  총 {len(source_paras)}개 문단")
        for i, p in enumerate(source_paras[:10]):
            print(f"  [{i}] {p[:80]}{'...' if len(p)>80 else ''}")
        if len(source_paras) > 10:
            print(f"  ... (총 {len(source_paras)}개)")

        hwp.Clear(1)  # 수정본 닫기

        # ============================================================
        # STEP 2: 마스터 열기 + 구조 파악
        # ============================================================
        print(f"\n{'='*60}")
        print(f"[STEP 2] 마스터 열기: {os.path.basename(MASTER)}")
        print(f"{'='*60}")

        hwp.Open(MASTER)
        master_paras = read_all_paragraphs(hwp)
        print(f"  총 {len(master_paras)}개 문단")

        # ============================================================
        # STEP 3: AI공학 섹션 위치 찾기
        # ============================================================
        print(f"\n{'='*60}")
        print("[STEP 3] AI공학 섹션 위치 찾기")
        print(f"{'='*60}")

        # 수정본의 첫 줄로 매칭 시도
        source_first = source_paras[0] if source_paras else ""
        print(f"  수정본 첫 줄: \"{source_first}\"")

        # 마스터에서 AI공학 관련 문단 검색
        ai_hits = []
        for i, p in enumerate(master_paras):
            if 'AI공학' in p or 'AI 공학' in p:
                ai_hits.append((i, p))

        print(f"\n  마스터에서 'AI공학' 포함 문단 {len(ai_hits)}개:")
        for idx, (i, p) in enumerate(ai_hits):
            marker = "  "
            if len(p) < 50:
                marker = ">>"
            print(f"  {marker} [{i:5d}] {p[:90]}{'...' if len(p)>90 else ''}")

        # 본문 섹션 찾기: 학부 과정의 AI공학 (짧은 단독 제목)
        section_start = None
        for i, p in enumerate(master_paras):
            stripped = p.strip()
            # "AI공학전공" 또는 "AI공학 전공" 단독 제목
            if ('AI공학' in stripped and
                len(stripped) < 40 and
                ('전공' in stripped or '학과' in stripped or stripped.endswith('AI공학'))):
                # 주변 문맥 확인 (목차가 아닌 본문인지)
                # 문단번호가 큰 쪽이 본문일 가능성 높음
                if i > 3000:  # 목차 영역을 넘어선 곳
                    section_start = i
                    print(f"\n  >> 본문 섹션 시작 후보: [{i}] \"{stripped}\"")
                    # 주변 5문단 출력
                    for j in range(max(0, i-2), min(len(master_paras), i+5)):
                        print(f"     [{j}] {master_paras[j][:80]}")
                    break

        # 대안: 수정본 첫 줄과 정확히 매칭
        if section_start is None:
            for i, p in enumerate(master_paras):
                if p.strip() == source_first.strip() and i > 1000:
                    section_start = i
                    print(f"\n  >> 수정본 첫 줄과 매칭: [{i}] \"{p.strip()[:60]}\"")
                    for j in range(i, min(len(master_paras), i+5)):
                        print(f"     [{j}] {master_paras[j][:80]}")
                    break

        # 대안2: "AI공학" 포함 + 짧은 문단 중 가장 큰 인덱스
        if section_start is None:
            candidates = [(i, p) for i, p in ai_hits if len(p) < 40 and i > 1000]
            if candidates:
                section_start = candidates[-1][0]
                print(f"\n  >> 대안 매칭: [{section_start}] \"{candidates[-1][1]}\"")

        if section_start is None:
            print("\n  [FAIL] AI공학 섹션을 찾지 못했습니다.")
            print("  수동으로 확인이 필요합니다.")
            return

        # ============================================================
        # STEP 3b: 섹션 끝 찾기
        # ============================================================
        # 다음 학과/전공 제목이 나올 때까지
        section_end = None
        for i in range(section_start + 1, len(master_paras)):
            p = master_paras[i].strip()
            # 다른 전공/학과 제목 패턴
            if (len(p) < 40 and
                ('전공' in p or '학과' in p or '학부' in p) and
                'AI공학' not in p and 'AI 공학' not in p and
                i > section_start + 3):
                # 다음 줄에 영문명이나 ● 시작이면 확실한 새 섹션
                if i + 1 < len(master_paras):
                    nxt = master_paras[i + 1].strip()
                    if ('Department' in nxt or '●' in nxt or 'School' in nxt or
                        'Division' in nxt or nxt.startswith('￭')):
                        section_end = i
                        print(f"\n  >> 섹션 끝: [{i}] \"{p}\" (다음 학과 시작)")
                        break

        if section_end is None:
            section_end = min(section_start + 150, len(master_paras))
            print(f"\n  >> 섹션 끝을 못 찾아 {section_end - section_start}개 문단으로 제한")

        existing_body = master_paras[section_start:section_end]
        print(f"\n  마스터 기존 섹션: 문단 [{section_start}]~[{section_end-1}] ({len(existing_body)}개 문단)")
        print(f"  수정본 내용: {len(source_paras)}개 문단")

        # ============================================================
        # STEP 4: 섹션 교체
        # ============================================================
        print(f"\n{'='*60}")
        print("[STEP 4] 섹션 교체")
        print(f"{'='*60}")

        body_count = section_end - section_start  # 제목 포함 전체 교체

        # 해당 위치로 커서 이동
        hwp.HAction.Run("MoveDocBegin")
        for _ in range(section_start):
            hwp.HAction.Run("MoveNextParaBegin")
        hwp.HAction.Run("MoveParaBegin")
        print(f"  커서 이동: 문단 [{section_start}]")

        # 기존 내용 선택 + 삭제
        if body_count > 1:
            for _ in range(body_count - 1):
                hwp.HAction.Run("MoveSelectNextParaBegin")
        hwp.HAction.Run("MoveSelectParaEnd")
        hwp.HAction.Run("Delete")
        print(f"  기존 {body_count}개 문단 삭제")

        # 새 내용 삽입
        for i, para in enumerate(source_paras):
            if i > 0:
                hwp.HAction.Run("BreakPara")
            pset = hwp.HParameterSet.HInsertText
            hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp.HAction.Execute("InsertText", pset.HSet)
            if i % 20 == 0:
                print(f"  삽입 중... {i}/{len(source_paras)}")

        print(f"  새 내용 {len(source_paras)}개 문단 삽입 완료")

        # ============================================================
        # STEP 5: 저장
        # ============================================================
        print(f"\n{'='*60}")
        print("[STEP 5] 저장")
        print(f"{'='*60}")

        hwp.SaveAs(OUTPUT)
        print(f"  [OK] 저장 완료: {OUTPUT}")
        print(f"\n  요약:")
        print(f"    마스터: {os.path.basename(MASTER)}")
        print(f"    수정본: {os.path.basename(SOURCE)}")
        print(f"    결과물: {os.path.basename(OUTPUT)}")
        print(f"    교체범위: 문단 {section_start}~{section_end-1} ({body_count}개) → {len(source_paras)}개")

    except Exception as e:
        print(f"\n[FAIL] 오류: {e}")
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
