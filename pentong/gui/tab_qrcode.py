"""QR 코드 생성 탭 UI."""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from core.qrcode_gen import QROptions, batch_generate_qr, generate_qr_image


class QRCodeTab(ttk.Frame):
    """QR 코드 생성 탭.

    - 텍스트/URL 입력 → 실시간 QR 미리보기
    - 크기·전경색·배경색 옵션
    - PNG / SVG 저장
    - 여러 줄 입력 시 일괄 생성
    """

    _PREVIEW_SIZE = 280  # 미리보기 캔버스 크기 (픽셀)

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._fg_color = "#000000"
        self._bg_color = "#ffffff"
        self._format_var = tk.StringVar(value="PNG")
        self._size_var = tk.IntVar(value=300)
        self._preview_job: str | None = None  # after() job id
        self._tk_image = None  # PhotoImage — 참조 유지용
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(1, weight=1)

        # 왼쪽: 입력 + 옵션 + 버튼
        left = ttk.Frame(self)
        left.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(10, 4), pady=10)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        # 텍스트 입력
        input_frame = ttk.LabelFrame(left, text="텍스트 / URL 입력 (여러 줄 가능)")
        input_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        input_frame.columnconfigure(0, weight=1)

        self._text_input = tk.Text(input_frame, height=6, wrap="word")
        self._text_input.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        self._text_input.bind("<KeyRelease>", self._schedule_preview)

        sb = ttk.Scrollbar(input_frame, orient="vertical", command=self._text_input.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self._text_input.configure(yscrollcommand=sb.set)

        # 옵션
        opt_frame = ttk.LabelFrame(left, text="옵션")
        opt_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        # 크기
        ttk.Label(opt_frame, text="크기 (px):").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=4)
        ttk.Spinbox(
            opt_frame,
            textvariable=self._size_var,
            from_=50,
            to=2000,
            increment=50,
            width=7,
            command=self._schedule_preview,
        ).grid(row=0, column=1, sticky="w", pady=4)

        # 전경색
        ttk.Label(opt_frame, text="전경색:").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=4)
        self._fg_btn = tk.Button(
            opt_frame,
            bg=self._fg_color,
            width=4,
            relief="solid",
            command=self._pick_fg,
        )
        self._fg_btn.grid(row=1, column=1, sticky="w", pady=4)

        # 배경색
        ttk.Label(opt_frame, text="배경색:").grid(row=2, column=0, sticky="w", padx=(8, 4), pady=4)
        self._bg_btn = tk.Button(
            opt_frame,
            bg=self._bg_color,
            width=4,
            relief="solid",
            command=self._pick_bg,
        )
        self._bg_btn.grid(row=2, column=1, sticky="w", pady=4)

        # 저장 포맷
        ttk.Label(opt_frame, text="저장 포맷:").grid(row=3, column=0, sticky="w", padx=(8, 4), pady=4)
        fmt_frame = ttk.Frame(opt_frame)
        fmt_frame.grid(row=3, column=1, sticky="w", pady=4)
        ttk.Radiobutton(fmt_frame, text="PNG", variable=self._format_var, value="PNG").pack(side="left")
        ttk.Radiobutton(fmt_frame, text="SVG", variable=self._format_var, value="SVG").pack(side="left", padx=(8, 0))

        # 저장 버튼
        ttk.Button(left, text="QR 저장", command=self._save).grid(row=2, column=0, pady=(4, 0))

        # 오른쪽: 미리보기
        preview_frame = ttk.LabelFrame(self, text="미리보기")
        preview_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(4, 10), pady=10)

        self._canvas = tk.Canvas(
            preview_frame,
            width=self._PREVIEW_SIZE,
            height=self._PREVIEW_SIZE,
            bg="#f0f0f0",
        )
        self._canvas.pack(padx=8, pady=8)

        self._preview_label = ttk.Label(preview_frame, text="텍스트를 입력하면\n미리보기가 표시됩니다", foreground="gray")
        self._preview_label.pack(pady=(0, 8))

    # ------------------------------------------------------------------
    # 색상 선택
    # ------------------------------------------------------------------

    def _pick_fg(self) -> None:
        color = colorchooser.askcolor(color=self._fg_color, title="전경색 선택")
        if color and color[1]:
            self._fg_color = color[1]
            self._fg_btn.configure(bg=self._fg_color)
            self._update_preview()

    def _pick_bg(self) -> None:
        color = colorchooser.askcolor(color=self._bg_color, title="배경색 선택")
        if color and color[1]:
            self._bg_color = color[1]
            self._bg_btn.configure(bg=self._bg_color)
            self._update_preview()

    # ------------------------------------------------------------------
    # 미리보기
    # ------------------------------------------------------------------

    def _schedule_preview(self, _event: object = None) -> None:
        """키 입력 후 200ms 뒤에 미리보기를 갱신한다 (디바운스)."""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(200, self._update_preview)

    def _update_preview(self) -> None:
        self._preview_job = None
        text = self._text_input.get("1.0", "end").strip()
        if not text:
            self._canvas.delete("all")
            self._preview_label.configure(text="텍스트를 입력하면\n미리보기가 표시됩니다")
            return

        # 첫 번째 줄만 미리보기
        first_line = text.splitlines()[0].strip()
        if not first_line:
            return

        def worker() -> None:
            try:
                opts = self._build_options()
                # 미리보기는 항상 PREVIEW_SIZE로 고정
                preview_opts = QROptions(
                    size=self._PREVIEW_SIZE,
                    box_size=opts.box_size,
                    border=opts.border,
                    fg_color=opts.fg_color,
                    bg_color=opts.bg_color,
                    error_correction=opts.error_correction,
                )
                img = generate_qr_image(first_line, preview_opts)
                self.after(0, lambda: self._show_preview(img))
            except Exception as exc:
                self.after(0, lambda: self._preview_label.configure(text=f"오류: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_preview(self, img) -> None:  # noqa: ANN001
        try:
            from PIL import ImageTk  # type: ignore[import]
            self._tk_image = ImageTk.PhotoImage(img)
            self._canvas.delete("all")
            self._canvas.create_image(
                self._PREVIEW_SIZE // 2,
                self._PREVIEW_SIZE // 2,
                anchor="center",
                image=self._tk_image,
            )
            self._preview_label.configure(text="")
        except Exception as exc:
            self._preview_label.configure(text=f"미리보기 오류: {exc}")

    # ------------------------------------------------------------------
    # 저장
    # ------------------------------------------------------------------

    def _build_options(self) -> QROptions:
        try:
            size = int(self._size_var.get())
        except (tk.TclError, ValueError):
            size = 300
        return QROptions(
            size=max(50, min(size, 2000)),
            fg_color=self._fg_color,
            bg_color=self._bg_color,
        )

    def _save(self) -> None:
        text = self._text_input.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("입력 없음", "QR 코드로 변환할 텍스트를 입력하세요.")
            return

        lines = [l for l in text.splitlines() if l.strip()]
        fmt = self._format_var.get()

        if len(lines) == 1:
            # 단일 파일 저장
            ext = fmt.lower()
            path = filedialog.asksaveasfilename(
                defaultextension=f".{ext}",
                filetypes=[(f"{fmt} 파일", f"*.{ext}"), ("모든 파일", "*.*")],
                title="QR 코드 저장",
            )
            if not path:
                return
            out_path = Path(path)
            opts = self._build_options()
            try:
                if fmt == "SVG":
                    from core.qrcode_gen import save_qr_svg
                    save_qr_svg(lines[0], out_path, opts)
                else:
                    from core.qrcode_gen import save_qr_png
                    save_qr_png(lines[0], out_path, opts)
                messagebox.showinfo("저장 완료", f"QR 코드가 저장되었습니다:\n{out_path}")
            except Exception as exc:
                messagebox.showerror("오류", str(exc))
        else:
            # 일괄 저장
            output_dir = filedialog.askdirectory(title="저장 폴더 선택")
            if not output_dir:
                return
            opts = self._build_options()
            try:
                results = batch_generate_qr(lines, Path(output_dir), fmt=fmt, options=opts)
                messagebox.showinfo(
                    "저장 완료",
                    f"{len(results)}개 QR 코드가 저장되었습니다:\n{output_dir}",
                )
            except Exception as exc:
                messagebox.showerror("오류", str(exc))
