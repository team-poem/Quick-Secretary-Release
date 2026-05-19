"""컴퓨터공학과 섹션을 추출하여 별도 HWP 파일로 저장하는 스크립트.

사용법:
  python hwp_extract_section.py
"""
import sys
import os
import io
import json
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CMD = '_hwp_cmd.json'
RES = '_hwp_result.json'


def send(cmd, timeout=60):
    if os.path.exists(RES):
        os.remove(RES)
    with open(CMD, 'w', encoding='utf-8') as f:
        json.dump(cmd, f, ensure_ascii=False)
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(RES):
            with open(RES, 'r', encoding='utf-8') as f:
                data = json.load(f)
            os.remove(RES)
            return data.get('result', '')
        time.sleep(0.3)
    return 'TIMEOUT'


def main():
    # 1) 전체 텍스트 읽기
    print("[1/4] 전체 문서 텍스트 읽기...")
    full_text = send({'action': 'read'}, timeout=60)
    if full_text.startswith('TIMEOUT') or full_text.startswith('오류'):
        print(f"실패: {full_text}")
        return

    paragraphs = [p for p in full_text.split('\n') if p.strip()]
    print(f"  총 {len(paragraphs)}개 문단")

    # 2) 학부 컴퓨터공학과 섹션 찾기
    # 목차가 아닌 실제 본문 섹션을 찾아야 함
    # "컴퓨터공학과" 단독 제목 + 다음에 "Department Of Computer Engineering" 오는 패턴
    print("\n[2/4] 컴퓨터공학과 섹션 위치 탐색...")

    section_start = None
    for i, para in enumerate(paragraphs):
        # "컴퓨터공학과"가 단독으로 있고, 바로 다음에 영문 학과명이 있는 곳
        if para.strip() == '컴퓨터공학과' or para.strip().startswith('컴퓨터공학과\t'):
            if i + 1 < len(paragraphs) and 'Department' in paragraphs[i + 1]:
                section_start = i
                print(f"  본문 시작 발견: 문단 [{i}] {para}")
                print(f"    다음: [{i+1}] {paragraphs[i+1]}")
                break

    if section_start is None:
        # 대안: ▮컴퓨터공학과 패턴으로 대학원 섹션이라도 찾기
        for i, para in enumerate(paragraphs):
            if '컴퓨터공학과' in para and len(para.strip()) < 30 and i > 1000:
                section_start = i
                print(f"  발견: 문단 [{i}] {para}")
                break

    if section_start is None:
        print("  컴퓨터공학과 섹션을 찾지 못했습니다.")
        return

    # 3) 섹션 끝 찾기: 다음 학과 제목이 나올 때까지
    # 학과 구분 패턴: 단독 학과명 (짧은 문단 + 다음에 영문 Department 또는 ● 시작)
    section_end = None
    for i in range(section_start + 2, len(paragraphs)):
        para = paragraphs[i].strip()
        # 다음 학과 시작 패턴들
        if (len(para) < 30 and (
            (para.endswith('학과') or para.endswith('전공') or para.endswith('학부'))
            and '컴퓨터공학' not in para
            and i + 1 < len(paragraphs)
            and ('Department' in paragraphs[i+1] or '●' in paragraphs[i+1] or 'School' in paragraphs[i+1])
        )):
            section_end = i
            print(f"  다음 섹션 시작: 문단 [{i}] {para}")
            break

    if section_end is None:
        # 끝까지 못 찾으면 일정 범위로 제한
        section_end = min(section_start + 200, len(paragraphs))
        print(f"  다음 섹션을 못 찾아서 {section_end - section_start}개 문단으로 제한")

    section_paras = paragraphs[section_start:section_end]
    print(f"\n  추출 범위: 문단 [{section_start}] ~ [{section_end - 1}] ({len(section_paras)}개 문단)")
    print(f"  처음: {section_paras[0][:60]}")
    print(f"  마지막: {section_paras[-1][:60]}")

    # 4) 추출된 내용을 파일로 저장 (텍스트)
    output_txt = os.path.join(os.path.dirname(os.path.abspath(__file__)), '컴퓨터공학과_추출.txt')
    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(section_paras))
    print(f"\n[3/4] 텍스트 저장: {output_txt}")

    # 5) HWP로 내보내기: 새 문서 열고 내용 삽입 후 저장
    # 브릿지로는 새 문서 생성이 어려우므로, 직접 COM 사용
    print("\n[4/4] HWP 파일 생성 중...")
    try:
        import pythoncom
        pythoncom.CoInitialize()
        import win32com.client as win32

        hwp2 = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp2.RegisterModule("FilePathCheckDLL", "SecurityModule")
        hwp2.XHwpWindows.Item(0).Visible = True

        # 빈 문서에 내용 삽입
        for i, para in enumerate(section_paras):
            if i > 0:
                hwp2.HAction.Run("BreakPara")
            pset = hwp2.HParameterSet.HInsertText
            hwp2.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = para
            hwp2.HAction.Execute("InsertText", pset.HSet)

            if i % 50 == 0:
                print(f"  삽입 중... {i}/{len(section_paras)}")

        output_hwp = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '컴퓨터공학과_추출.hwp'
        )
        hwp2.SaveAs(output_hwp)
        print(f"\n[OK] HWP 저장 완료: {output_hwp}")

        hwp2.Clear(1)
        hwp2.Quit()

        pythoncom.CoUninitialize()

    except Exception as e:
        print(f"[FAIL] HWP 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n텍스트 파일은 저장되어 있습니다: {output_txt}")


if __name__ == '__main__':
    main()
