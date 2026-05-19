"""한글 파일 취합 탭 UI."""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.hwp_merge import merge_hwp_files


class HwpMergeTab(ttk.Frame):
    """한글 취합 탭 — 여러 HWP/HWPX 파일을 하나로 합친다."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._page_break_var = tk.BooleanVar(value=True)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # 상단: 파일 추가/제거 버튼
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        ttk.Button(btn_frame, text="파일 추가", command=self._add_files).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="선택 제거", command=self._remove_selected).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="전체 제거", command=self._clear_files).pack(side="left")

        # 파일 목록
        list_frame = ttk.LabelFrame(self, text="취합할 파일 목록")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(list_frame, selectmode="extended", activestyle="dotbox")
        self._listbox.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)

        # 옵션
        opt_frame = ttk.LabelFrame(self, text="옵션")
        opt_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=4)

        ttk.Checkbutton(
            opt_frame,
            text="파일 사이에 페이지 나누기 삽입",
            variable=self._page_break_var,
        ).pack(anchor="w", padx=10, pady=4)

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
        ttk.Button(self, text="취합 실행", command=self._run).grid(
            row=4, column=0, pady=(4, 10)
        )

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="HWP/HWPX 파일 선택",
            filetypes=[
                ("한글 파일", "*.hwp *.hwpx"),
                ("모든 파일", "*.*"),
            ],
        )
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

    def _run(self) -> None:
        if not self._files:
            messagebox.showwarning("파일 없음", "취합할 HWP/HWPX 파일을 추가하세요.")
            return

        output_path = filedialog.asksaveasfilename(
            title="저장 위치 선택",
            defaultextension=".hwp",
            filetypes=[("한글 파일", "*.hwp")],
        )
        if not output_path:
            return

        files = list(self._files)
        out = Path(output_path)
        insert_page_break = self._page_break_var.get()

        self._set_ui_running(True)

        def worker() -> None:
            try:
                def on_progress(current: int, total: int, filename: str) -> None:
                    pct = current / total * 100
                    self.after(0, lambda: self._progress_var.set(pct))
                    self.after(0, lambda: self._status_var.set(f"처리 중 ({current}/{total}): {filename}"))

                merge_hwp_files(files, out, insert_page_break=insert_page_break, progress_cb=on_progress)
                self.after(0, lambda: self._on_done(True, str(out)))
            except Exception as exc:
                self.after(0, lambda: self._on_done(False, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, success: bool, message: str) -> None:
        self._set_ui_running(False)
        if success:
            self._status_var.set("완료")
            messagebox.showinfo("완료", f"파일이 저장되었습니다:\n{message}")
        else:
            self._status_var.set("오류 발생")
            messagebox.showerror("오류", message)

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
