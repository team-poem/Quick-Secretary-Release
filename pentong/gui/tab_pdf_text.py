"""PDF ↔ 텍스트 변환 탭 UI."""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.pdf_text import batch_extract_pdfs, batch_convert_texts_to_pdf


class PdfTextTab(ttk.Frame):
    """PDF↔텍스트 변환 탭.

    - PDF→텍스트: 여러 PDF를 선택하여 .txt로 추출 (일괄 처리).
    - 텍스트→PDF: 여러 .txt 파일을 PDF로 변환 (일괄 처리).
    추출된 텍스트 미리보기 제공.
    """

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._direction_var = tk.StringVar(value="pdf_to_text")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # 변환 방향 선택
        dir_frame = ttk.LabelFrame(self, text="변환 방향")
        dir_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        ttk.Radiobutton(
            dir_frame,
            text="PDF → 텍스트",
            variable=self._direction_var,
            value="pdf_to_text",
            command=self._on_direction_change,
        ).pack(side="left", padx=(10, 20), pady=4)

        ttk.Radiobutton(
            dir_frame,
            text="텍스트 → PDF",
            variable=self._direction_var,
            value="text_to_pdf",
            command=self._on_direction_change,
        ).pack(side="left", padx=(0, 10), pady=4)

        # 파일 선택 버튼
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        ttk.Button(btn_frame, text="파일 추가", command=self._add_files).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="선택 제거", command=self._remove_selected).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="전체 제거", command=self._clear_files).pack(side="left")

        # 파일 목록 + 미리보기 (좌우 분할)
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)

        # 왼쪽: 파일 목록
        list_frame = ttk.LabelFrame(pane, text="파일 목록")
        pane.add(list_frame, weight=1)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(list_frame, selectmode="extended", activestyle="dotbox")
        self._listbox.grid(row=0, column=0, sticky="nsew")
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)

        sb_list = ttk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        sb_list.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb_list.set)

        # 오른쪽: 텍스트 미리보기
        preview_frame = ttk.LabelFrame(pane, text="텍스트 미리보기")
        pane.add(preview_frame, weight=2)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self._preview_text = tk.Text(preview_frame, state="disabled", wrap="word")
        self._preview_text.grid(row=0, column=0, sticky="nsew")

        sb_prev = ttk.Scrollbar(preview_frame, orient="vertical", command=self._preview_text.yview)
        sb_prev.grid(row=0, column=1, sticky="ns")
        self._preview_text.configure(yscrollcommand=sb_prev.set)

        # 진행 상태
        progress_frame = ttk.Frame(self)
        progress_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        progress_frame.columnconfigure(0, weight=1)

        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(
            progress_frame, variable=self._progress_var, maximum=100
        )
        self._progress_bar.grid(row=0, column=0, sticky="ew")

        self._status_var = tk.StringVar(value="대기 중")
        ttk.Label(progress_frame, textvariable=self._status_var, foreground="gray").grid(
            row=1, column=0, sticky="w"
        )

        # 실행 버튼
        ttk.Button(self, text="변환 실행", command=self._run).grid(
            row=4, column=0, pady=(4, 10)
        )

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _on_direction_change(self) -> None:
        self._clear_files()
        self._set_preview("")

    def _add_files(self) -> None:
        if self._direction_var.get() == "pdf_to_text":
            filetypes = [("PDF 파일", "*.pdf"), ("모든 파일", "*.*")]
            title = "PDF 파일 선택"
        else:
            filetypes = [("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
            title = "텍스트 파일 선택"

        paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
        for p in paths:
            path = Path(p)
            if path not in self._files:
                self._files.append(path)
                self._listbox.insert("end", str(path))

    def _remove_selected(self) -> None:
        indices = list(self._listbox.curselection())
        for i in reversed(indices):
            self._listbox.delete(i)
            self._files.pop(i)

    def _clear_files(self) -> None:
        self._listbox.delete(0, "end")
        self._files.clear()

    def _on_list_select(self, _event: object) -> None:
        indices = self._listbox.curselection()
        if not indices:
            return
        path = self._files[indices[0]]
        direction = self._direction_var.get()

        if direction == "pdf_to_text":
            # PDF에서 텍스트 미리보기 (백그라운드)
            self._status_var.set("미리보기 로딩 중...")
            threading.Thread(target=self._load_preview_pdf, args=(path,), daemon=True).start()
        else:
            # 텍스트 파일 직접 표시
            try:
                content = path.read_text(encoding="utf-8")
                self._set_preview(content)
            except Exception as exc:
                self._set_preview(f"[미리보기 오류] {exc}")

    def _load_preview_pdf(self, path: Path) -> None:
        try:
            from core.pdf_text import extract_text_from_pdf
            text = extract_text_from_pdf(path)
            if not text.strip():
                text = "[텍스트가 없습니다 — 이미지 전용 PDF일 수 있습니다]"
            self.after(0, lambda: self._set_preview(text))
            self.after(0, lambda: self._status_var.set("대기 중"))
        except Exception as exc:
            self.after(0, lambda: self._set_preview(f"[미리보기 오류] {exc}"))
            self.after(0, lambda: self._status_var.set("대기 중"))

    def _set_preview(self, content: str) -> None:
        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", "end")
        self._preview_text.insert("1.0", content)
        self._preview_text.configure(state="disabled")

    def _run(self) -> None:
        if not self._files:
            messagebox.showwarning("파일 없음", "변환할 파일을 추가하세요.")
            return

        output_dir = filedialog.askdirectory(title="저장 폴더 선택")
        if not output_dir:
            return

        files = list(self._files)
        out = Path(output_dir)
        direction = self._direction_var.get()

        self._set_ui_running(True)

        def worker() -> None:
            try:
                def on_progress(current: int, total: int, filename: str) -> None:
                    pct = current / total * 100
                    self.after(0, lambda: self._progress_var.set(pct))
                    self.after(0, lambda: self._status_var.set(f"처리 중 ({current}/{total}): {filename}"))

                if direction == "pdf_to_text":
                    results = batch_extract_pdfs(files, out, progress_cb=on_progress)
                else:
                    results = batch_convert_texts_to_pdf(files, out, progress_cb=on_progress)

                self.after(0, lambda: self._on_done(True, out, results))
            except Exception as exc:
                self.after(0, lambda: self._on_done(False, out, [], error=str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(
        self,
        success: bool,
        output_dir: Path,
        results: list[Path],
        error: str = "",
    ) -> None:
        self._set_ui_running(False)
        if success:
            self._progress_var.set(100)
            self._status_var.set("완료")
            messagebox.showinfo(
                "완료",
                f"{len(results)}개 파일이 저장되었습니다:\n{output_dir}",
            )
        else:
            self._status_var.set("오류 발생")
            messagebox.showerror("오류", error)

    def _set_ui_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for child in self.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
        if running:
            self._progress_var.set(0)
            self._status_var.set("실행 중...")
