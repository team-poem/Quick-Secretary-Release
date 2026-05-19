"""엑셀 파일 분할 탭 UI."""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.excel_split import SplitMode, split_excel_file


class ExcelSplitTab(ttk.Frame):
    """엑셀 분할 탭 — 하나의 xlsx 파일을 여러 파일로 분할한다."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._input_path: Path | None = None
        self._output_dir: Path | None = None
        self._mode_var = tk.StringVar(value="sheet")
        self._rows_var = tk.StringVar(value="1000")
        self._col_var = tk.StringVar(value="1")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)

        # 원본 파일 선택
        src_frame = ttk.LabelFrame(self, text="원본 파일")
        src_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        src_frame.columnconfigure(1, weight=1)

        ttk.Button(src_frame, text="파일 선택", command=self._pick_input).grid(
            row=0, column=0, padx=(8, 4), pady=6
        )
        self._src_label = ttk.Label(src_frame, text="선택된 파일 없음", foreground="gray")
        self._src_label.grid(row=0, column=1, sticky="w", padx=(0, 8))

        # 출력 폴더 선택
        dst_frame = ttk.LabelFrame(self, text="출력 폴더")
        dst_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        dst_frame.columnconfigure(1, weight=1)

        ttk.Button(dst_frame, text="폴더 선택", command=self._pick_output_dir).grid(
            row=0, column=0, padx=(8, 4), pady=6
        )
        self._dst_label = ttk.Label(dst_frame, text="선택된 폴더 없음", foreground="gray")
        self._dst_label.grid(row=0, column=1, sticky="w", padx=(0, 8))

        # 분할 기준 선택
        mode_frame = ttk.LabelFrame(self, text="분할 기준")
        mode_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        mode_frame.columnconfigure(1, weight=1)

        ttk.Radiobutton(
            mode_frame,
            text="시트별 분할 (각 시트 → 개별 파일)",
            variable=self._mode_var,
            value="sheet",
            command=self._on_mode_change,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        ttk.Radiobutton(
            mode_frame,
            text="행 수 기준:",
            variable=self._mode_var,
            value="rows",
            command=self._on_mode_change,
        ).grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self._rows_entry = ttk.Entry(mode_frame, textvariable=self._rows_var, width=8)
        self._rows_entry.grid(row=1, column=1, sticky="w", padx=(0, 4))
        ttk.Label(mode_frame, text="행마다 파일 분할 (헤더 제외)").grid(row=1, column=2, sticky="w")

        ttk.Radiobutton(
            mode_frame,
            text="열 값 기준 (열 번호:",
            variable=self._mode_var,
            value="column",
            command=self._on_mode_change,
        ).grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self._col_entry = ttk.Entry(mode_frame, textvariable=self._col_var, width=5)
        self._col_entry.grid(row=2, column=1, sticky="w", padx=(0, 4))
        ttk.Label(mode_frame, text=")의 고유값마다 분할").grid(row=2, column=2, sticky="w")

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
        ttk.Button(self, text="분할 실행", command=self._run).grid(
            row=4, column=0, pady=(4, 10)
        )

        self._on_mode_change()

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        rows_state = "normal" if mode == "rows" else "disabled"
        col_state = "normal" if mode == "column" else "disabled"
        self._rows_entry.configure(state=rows_state)
        self._col_entry.configure(state=col_state)

    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(
            title="분할할 xlsx 파일 선택",
            filetypes=[("Excel 파일", "*.xlsx"), ("모든 파일", "*.*")],
        )
        if path:
            self._input_path = Path(path)
            self._src_label.configure(text=str(self._input_path), foreground="black")

    def _pick_output_dir(self) -> None:
        path = filedialog.askdirectory(title="결과 파일을 저장할 폴더 선택")
        if path:
            self._output_dir = Path(path)
            self._dst_label.configure(text=str(self._output_dir), foreground="black")

    def _run(self) -> None:
        if not self._input_path:
            messagebox.showwarning("파일 없음", "분할할 xlsx 파일을 선택하세요.")
            return
        if not self._output_dir:
            messagebox.showwarning("폴더 없음", "결과 파일을 저장할 폴더를 선택하세요.")
            return

        mode: SplitMode = self._mode_var.get()  # type: ignore[assignment]

        try:
            rows_per_file = int(self._rows_var.get())
            if rows_per_file < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("입력 오류", "행 수는 1 이상의 정수여야 합니다.")
            return

        try:
            column_index = int(self._col_var.get())
            if column_index < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("입력 오류", "열 번호는 1 이상의 정수여야 합니다.")
            return

        input_path = self._input_path
        output_dir = self._output_dir
        self._set_ui_running(True)

        def worker() -> None:
            try:
                def on_progress(current: int, total: int, label: str) -> None:
                    pct = current / total * 100
                    self.after(0, lambda: self._progress_var.set(pct))
                    self.after(0, lambda: self._status_var.set(f"처리 중 ({current}/{total}): {label}"))

                results = split_excel_file(
                    input_path,
                    output_dir,
                    mode=mode,
                    rows_per_file=rows_per_file,
                    column_index=column_index,
                    progress_cb=on_progress,
                )
                self.after(0, lambda: self._on_done(True, len(results), str(output_dir)))
            except Exception as exc:
                self.after(0, lambda: self._on_done(False, 0, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, success: bool, count: int, message: str) -> None:
        self._set_ui_running(False)
        if success:
            self._status_var.set("완료")
            messagebox.showinfo("완료", f"{count}개 파일이 저장되었습니다:\n{message}")
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
        else:
            self._on_mode_change()
