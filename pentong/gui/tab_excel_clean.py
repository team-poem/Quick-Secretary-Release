"""엑셀 공백 행 제거 탭 UI."""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.excel_clean import count_blank_rows, remove_blank_rows


class ExcelCleanTab(ttk.Frame):
    """엑셀 공백 행 제거 탭 — xlsx 파일에서 빈 행을 제거한다."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._input_path: Path | None = None
        self._save_mode_var = tk.StringVar(value="overwrite")
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

        # 미리보기 영역
        preview_frame = ttk.LabelFrame(self, text="미리보기")
        preview_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        preview_frame.columnconfigure(0, weight=1)

        self._preview_var = tk.StringVar(value="파일을 선택하면 공백 행 수가 표시됩니다.")
        ttk.Label(preview_frame, textvariable=self._preview_var, foreground="gray").grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )

        # 저장 방식
        save_frame = ttk.LabelFrame(self, text="저장 방식")
        save_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=4)

        ttk.Radiobutton(
            save_frame,
            text="원본 파일 덮어쓰기",
            variable=self._save_mode_var,
            value="overwrite",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=4)

        ttk.Radiobutton(
            save_frame,
            text="새 파일로 저장",
            variable=self._save_mode_var,
            value="new",
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

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
        ttk.Button(self, text="공백 행 제거 실행", command=self._run).grid(
            row=4, column=0, pady=(4, 10)
        )

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(
            title="공백 행을 제거할 xlsx 파일 선택",
            filetypes=[("Excel 파일", "*.xlsx"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        self._input_path = Path(path)
        self._src_label.configure(text=str(self._input_path), foreground="black")
        self._preview_var.set("공백 행 수 계산 중...")
        threading.Thread(target=self._load_preview, daemon=True).start()

    def _load_preview(self) -> None:
        assert self._input_path is not None
        try:
            n = count_blank_rows(self._input_path)
            msg = f"{n}개 공백 행 발견" if n else "공백 행 없음"
            self.after(0, lambda: self._preview_var.set(msg))
            self.after(0, lambda: self._src_label.configure(foreground="black"))
        except Exception as exc:
            self.after(0, lambda: self._preview_var.set(f"오류: {exc}"))

    def _run(self) -> None:
        if not self._input_path:
            messagebox.showwarning("파일 없음", "처리할 xlsx 파일을 선택하세요.")
            return

        input_path = self._input_path
        save_mode = self._save_mode_var.get()

        if save_mode == "overwrite":
            output_path = input_path
        else:
            dest = filedialog.asksaveasfilename(
                title="저장할 파일 이름",
                defaultextension=".xlsx",
                filetypes=[("Excel 파일", "*.xlsx")],
                initialfile=f"{input_path.stem}_cleaned.xlsx",
                initialdir=str(input_path.parent),
            )
            if not dest:
                return
            output_path = Path(dest)

        self._set_ui_running(True)

        def worker() -> None:
            try:
                def on_progress(current: int, total: int, label: str) -> None:
                    pct = current / total * 100
                    self.after(0, lambda: self._progress_var.set(pct))
                    self.after(0, lambda: self._status_var.set(f"처리 중 ({current}/{total}): {label}"))

                removed = remove_blank_rows(input_path, output_path, progress_cb=on_progress)
                self.after(0, lambda: self._on_done(True, removed, str(output_path)))
            except Exception as exc:
                self.after(0, lambda: self._on_done(False, 0, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, success: bool, removed: int, message: str) -> None:
        self._set_ui_running(False)
        if success:
            self._status_var.set("완료")
            self._preview_var.set("공백 행 없음")
            messagebox.showinfo("완료", f"{removed}개 공백 행이 제거되었습니다.\n저장: {message}")
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
