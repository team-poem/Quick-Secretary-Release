"""PenTong 메인 윈도우 — ttk.Notebook 기반 탭 컨트롤러."""
import tkinter as tk
from tkinter import ttk

from gui.tab_excel_clean import ExcelCleanTab
from gui.tab_excel_merge import ExcelMergeTab
from gui.tab_excel_split import ExcelSplitTab
from gui.tab_hwp import HwpMergeTab
from gui.tab_pdf_text import PdfTextTab
from gui.tab_qrcode import QRCodeTab


class App(tk.Tk):
    """최상위 윈도우. Notebook으로 6개 탭을 구성한다."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PenTong")
        self.minsize(800, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # 한글 취합 — Phase 5
        hwp_merge_tab = HwpMergeTab(notebook)
        notebook.add(hwp_merge_tab, text="한글 취합")

        # 엑셀 취합 — Phase 2
        excel_merge_tab = ExcelMergeTab(notebook)
        notebook.add(excel_merge_tab, text="엑셀 취합")

        # 엑셀 분할 — Phase 3
        excel_split_tab = ExcelSplitTab(notebook)
        notebook.add(excel_split_tab, text="엑셀 분할")

        # 엑셀 공백 행 제거 — Phase 4
        excel_clean_tab = ExcelCleanTab(notebook)
        notebook.add(excel_clean_tab, text="엑셀 공백 행 제거")

        # PDF/텍스트 변환 — Phase 6
        pdf_text_tab = PdfTextTab(notebook)
        notebook.add(pdf_text_tab, text="PDF/텍스트 변환")

        # QR Code 생성 — Phase 7
        qrcode_tab = QRCodeTab(notebook)
        notebook.add(qrcode_tab, text="QR Code 생성")
