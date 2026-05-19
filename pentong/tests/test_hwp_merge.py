"""core/hwp_merge.py 단위 테스트.

한글 COM 자동화는 Windows + 한컴 한글 설치 환경에서만 동작하므로,
COM 호출 부분은 unittest.mock으로 격리하여 테스트한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.hwp_merge import merge_hwp_files


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_hwp(path: Path) -> None:
    """테스트용 더미 hwp 파일 생성."""
    path.write_bytes(b"HWP dummy")


def _make_mock_hwp():
    """win32com HWP COM 객체 Mock."""
    hwp = MagicMock()
    hwp.HAction = MagicMock()
    hwp.HParameterSet = MagicMock()
    hwp.HParameterSet.HInsertFile.HSet = MagicMock()
    hwp.XHwpWindows = MagicMock()
    hwp.XHwpWindows.Item.return_value = MagicMock()
    return hwp


# ---------------------------------------------------------------------------
# 입력 유효성 검사
# ---------------------------------------------------------------------------

def test_empty_list_raises():
    with pytest.raises(ValueError, match="하나 이상"):
        merge_hwp_files([], Path("out.hwp"))


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        merge_hwp_files([tmp_path / "ghost.hwp"], tmp_path / "out.hwp")


# ---------------------------------------------------------------------------
# pywin32 미설치 시 에러
# ---------------------------------------------------------------------------

def test_no_pywin32_raises_runtime_error(tmp_path):
    hwp_file = tmp_path / "a.hwp"
    _make_hwp(hwp_file)

    with patch("core.hwp_merge._HAS_WIN32COM", False):
        with pytest.raises(RuntimeError, match="pywin32"):
            merge_hwp_files([hwp_file], tmp_path / "out.hwp")


# ---------------------------------------------------------------------------
# 한글 미설치 시 에러
# ---------------------------------------------------------------------------

def test_hwp_not_installed_raises(tmp_path):
    hwp_file = tmp_path / "a.hwp"
    _make_hwp(hwp_file)

    mock_client = MagicMock()
    mock_client.Dispatch.side_effect = Exception("COM 실패")

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        with pytest.raises(RuntimeError, match="한글 프로그램을 찾을 수 없습니다"):
            merge_hwp_files([hwp_file], tmp_path / "out.hwp")


# ---------------------------------------------------------------------------
# 정상 동작
# ---------------------------------------------------------------------------

def test_single_file_no_insert(tmp_path):
    """파일 1개는 InsertFile 없이 열고 저장만 한다."""
    hwp_file = tmp_path / "a.hwp"
    _make_hwp(hwp_file)
    out = tmp_path / "out.hwp"

    mock_hwp = _make_mock_hwp()
    mock_client = MagicMock()
    mock_client.Dispatch.return_value = mock_hwp

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        merge_hwp_files([hwp_file], out)

    mock_hwp.Open.assert_called_once()
    mock_hwp.HAction.Execute.assert_not_called()
    mock_hwp.SaveAs.assert_called_once()
    mock_hwp.Quit.assert_called_once()


def test_multiple_files_inserts_called(tmp_path):
    """파일 2개 이상이면 InsertFile이 n-1번 호출된다."""
    a = tmp_path / "a.hwp"
    b = tmp_path / "b.hwp"
    c = tmp_path / "c.hwp"
    for f in (a, b, c):
        _make_hwp(f)
    out = tmp_path / "out.hwp"

    mock_hwp = _make_mock_hwp()
    mock_client = MagicMock()
    mock_client.Dispatch.return_value = mock_hwp

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        merge_hwp_files([a, b, c], out, insert_page_break=False)

    assert mock_hwp.HAction.Execute.call_count == 2


def test_page_break_inserted_between_files(tmp_path):
    """insert_page_break=True 이면 BreakPage 액션이 실행된다."""
    a = tmp_path / "a.hwp"
    b = tmp_path / "b.hwp"
    for f in (a, b):
        _make_hwp(f)
    out = tmp_path / "out.hwp"

    mock_hwp = _make_mock_hwp()
    mock_client = MagicMock()
    mock_client.Dispatch.return_value = mock_hwp

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        merge_hwp_files([a, b], out, insert_page_break=True)

    run_calls = [str(c) for c in mock_hwp.HAction.Run.call_args_list]
    assert any("BreakPage" in c for c in run_calls)


def test_progress_callback_called(tmp_path):
    """progress_cb가 파일 수만큼 호출된다."""
    a = tmp_path / "a.hwp"
    b = tmp_path / "b.hwp"
    for f in (a, b):
        _make_hwp(f)
    out = tmp_path / "out.hwp"

    mock_hwp = _make_mock_hwp()
    mock_client = MagicMock()
    mock_client.Dispatch.return_value = mock_hwp

    calls: list[tuple[int, int, str]] = []

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        merge_hwp_files([a, b], out, progress_cb=lambda c, t, n: calls.append((c, t, n)))

    assert len(calls) == 2
    assert calls[0] == (1, 2, "a.hwp")
    assert calls[1] == (2, 2, "b.hwp")


def test_quit_called_on_exception(tmp_path):
    """예외 발생 시에도 Quit이 호출되어 프로세스 누수가 없어야 한다."""
    a = tmp_path / "a.hwp"
    b = tmp_path / "b.hwp"
    for f in (a, b):
        _make_hwp(f)

    mock_hwp = _make_mock_hwp()
    mock_hwp.HAction.Execute.side_effect = RuntimeError("COM 오류")
    mock_client = MagicMock()
    mock_client.Dispatch.return_value = mock_hwp

    with patch("core.hwp_merge._HAS_WIN32COM", True), \
         patch("core.hwp_merge._win32com_client", mock_client):
        with pytest.raises(RuntimeError):
            merge_hwp_files([a, b], tmp_path / "out.hwp")

    mock_hwp.Quit.assert_called_once()
