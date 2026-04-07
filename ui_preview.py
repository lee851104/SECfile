"""
SEC EDGAR 文件下載器 — UI Preview（僅介面展示，無實際功能）
執行: python ui_preview.py
"""

import tkinter as tk
from tkinter import ttk
import threading
import time

# ── 顏色系統 ─────────────────────────────────────────────
BG_DARK      = "#0F1117"   # 主背景
BG_PANEL     = "#161B22"   # 面板背景
BG_CARD      = "#1C2128"   # 卡片背景
BG_INPUT     = "#21262D"   # 輸入框背景
BG_HOVER     = "#262C36"   # 懸停背景
BORDER       = "#30363D"   # 邊框
BORDER_FOCUS = "#388BFD"   # 聚焦邊框（藍）

TEXT_PRIMARY   = "#E6EDF3"  # 主要文字
TEXT_SECONDARY = "#8B949E"  # 次要文字
TEXT_MUTED     = "#484F58"  # 淡化文字

ACCENT_BLUE    = "#388BFD"  # 主要強調色
ACCENT_GREEN   = "#3FB950"  # 成功 / 完成
ACCENT_ORANGE  = "#F0883E"  # 警告
ACCENT_RED     = "#F85149"  # 錯誤

BTN_PRIMARY_BG = "#238636"  # 主要按鈕背景
BTN_PRIMARY_FG = "#FFFFFF"
BTN_PRIMARY_HOVER = "#2EA043"

BTN_SECONDARY_BG = "#21262D"
BTN_SECONDARY_FG = "#C9D1D9"
BTN_SECONDARY_HOVER = "#30363D"

# ── 字型 ─────────────────────────────────────────────────
FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_BODY   = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_MONO   = ("Consolas", 9)
FONT_LABEL  = ("Segoe UI", 9)
FONT_TICKER = ("Segoe UI", 22, "bold")


class HoverButton(tk.Button):
    def __init__(self, master, bg_normal, bg_hover, **kwargs):
        super().__init__(master, bg=bg_normal, activebackground=bg_hover,
                         relief="flat", cursor="hand2", **kwargs)
        self._bg_normal = bg_normal
        self._bg_hover = bg_hover
        self.bind("<Enter>", lambda e: self.config(bg=bg_hover))
        self.bind("<Leave>", lambda e: self.config(bg=bg_normal))


class CheckRow(tk.Frame):
    """單一文件列（帶勾選框）"""
    def __init__(self, master, form_type, filing_date, label, is_checked=True, **kwargs):
        super().__init__(master, bg=BG_CARD, **kwargs)
        self.var = tk.BooleanVar(value=is_checked)
        self._normal_bg = BG_CARD

        # 整行懸停效果
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        # 標籤顏色
        type_color = ACCENT_BLUE if form_type == "10-K" else "#BC8CFF"

        # 勾選框
        chk = tk.Checkbutton(
            self, variable=self.var, bg=BG_CARD, activebackground=BG_HOVER,
            selectcolor=BG_INPUT, fg=TEXT_PRIMARY,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2"
        )
        chk.pack(side="left", padx=(12, 4))

        # 標籤 badge
        badge = tk.Label(
            self, text=form_type, font=("Segoe UI", 8, "bold"),
            fg=type_color, bg=BG_CARD,
            width=5, anchor="center"
        )
        badge.pack(side="left", padx=(0, 10))

        # 日期
        tk.Label(self, text=filing_date, font=FONT_MONO,
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(side="left", padx=(0, 14))

        # 檔名（主要）
        tk.Label(self, text=label, font=("Segoe UI", 9, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")

        # PDF badge
        tk.Label(self, text="PDF", font=("Segoe UI", 7, "bold"),
                 fg=TEXT_MUTED, bg=BG_CARD).pack(side="right", padx=14)

        for widget in self.winfo_children():
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, e):
        self._set_bg(BG_HOVER)

    def _on_leave(self, e):
        self._set_bg(BG_CARD)

    def _set_bg(self, color):
        self.config(bg=color)
        for w in self.winfo_children():
            try:
                w.config(bg=color)
            except Exception:
                pass


class LogLine(tk.Frame):
    def __init__(self, master, icon, text, color, **kwargs):
        super().__init__(master, bg=BG_PANEL, **kwargs)
        tk.Label(self, text=icon, font=FONT_SMALL, fg=color,
                 bg=BG_PANEL, width=2).pack(side="left", padx=(0, 6))
        tk.Label(self, text=text, font=FONT_MONO, fg=color,
                 bg=BG_PANEL, anchor="w").pack(side="left", fill="x")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SEC EDGAR 文件下載器")
        self.geometry("980x680")
        self.minsize(860, 580)
        self.configure(bg=BG_DARK)
        self.resizable(True, True)

        self._build_titlebar()
        self._build_body()
        self._demo_progress()

    # ── 頂部標題列 ────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=BG_PANEL, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # 左側 logo + 標題
        left = tk.Frame(bar, bg=BG_PANEL)
        left.pack(side="left", padx=20, pady=10)

        tk.Label(left, text="⬡", font=("Segoe UI", 16),
                 fg=ACCENT_BLUE, bg=BG_PANEL).pack(side="left", padx=(0, 8))
        tk.Label(left, text="SEC EDGAR", font=("Segoe UI", 12, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_PANEL).pack(side="left")
        tk.Label(left, text=" 文件下載器", font=("Segoe UI", 12),
                 fg=TEXT_SECONDARY, bg=BG_PANEL).pack(side="left")

        # 右側版本標籤
        tk.Label(bar, text="v1.0  |  SEC EDGAR REST API",
                 font=FONT_SMALL, fg=TEXT_MUTED, bg=BG_PANEL).pack(
            side="right", padx=20)

        # 底部分割線
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    # ── 主體（左右分割）─────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True)

        # 左側控制面板（固定寬度 280）
        self._build_left(body)

        # 垂直分割線
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # 右側結果 + 進度
        self._build_right(body)

    # ── 左側面板 ──────────────────────────────────────────
    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG_PANEL, width=280)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        pad = dict(padx=20)

        # ── Ticker 搜尋 ──
        tk.Frame(left, bg=BG_PANEL, height=24).pack()

        tk.Label(left, text="股票代碼", font=FONT_LABEL,
                 fg=TEXT_SECONDARY, bg=BG_PANEL, anchor="w").pack(fill="x", **pad)
        tk.Frame(left, bg=BG_PANEL, height=4).pack()

        # 輸入框容器（模擬聚焦邊框）
        entry_frame = tk.Frame(left, bg=BORDER_FOCUS, bd=0)
        entry_frame.pack(fill="x", padx=20)
        inner = tk.Frame(entry_frame, bg=BG_INPUT)
        inner.pack(fill="x", padx=1, pady=1)

        ticker_var = tk.StringVar(value="AAPL")
        entry = tk.Entry(inner, textvariable=ticker_var,
                         font=FONT_TICKER, fg=TEXT_PRIMARY,
                         bg=BG_INPUT, insertbackground=TEXT_PRIMARY,
                         relief="flat", bd=8, justify="center")
        entry.pack(fill="x")

        tk.Frame(left, bg=BG_PANEL, height=4).pack()
        tk.Label(left, text="Apple Inc.  ·  NASDAQ", font=FONT_SMALL,
                 fg=ACCENT_GREEN, bg=BG_PANEL).pack(**pad, anchor="w")

        tk.Frame(left, bg=BG_PANEL, height=16).pack()

        # 搜尋按鈕
        HoverButton(
            left, bg_normal=ACCENT_BLUE, bg_hover="#4A9EFF",
            text="  搜尋文件  ", font=("Segoe UI", 10, "bold"),
            fg="white", padx=0, pady=8
        ).pack(fill="x", **pad)

        # ── 分割線 ──
        tk.Frame(left, bg=BG_PANEL, height=20).pack()
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", **pad)
        tk.Frame(left, bg=BG_PANEL, height=20).pack()

        # ── 文件類型篩選 ──
        tk.Label(left, text="文件類型", font=FONT_LABEL,
                 fg=TEXT_SECONDARY, bg=BG_PANEL, anchor="w").pack(fill="x", **pad)
        tk.Frame(left, bg=BG_PANEL, height=8).pack()

        for label, desc, color in [
            ("10-K  年報", "完整財務年度報告", ACCENT_BLUE),
            ("10-Q  季報", "每季財務報告", "#BC8CFF"),
        ]:
            row = tk.Frame(left, bg=BG_CARD, pady=2)
            row.pack(fill="x", **pad, pady=2)
            row.pack_propagate(False)

            chk_var = tk.BooleanVar(value=True)
            tk.Checkbutton(row, variable=chk_var, bg=BG_CARD,
                           activebackground=BG_CARD, selectcolor=BG_INPUT,
                           relief="flat", bd=0, highlightthickness=0,
                           cursor="hand2").pack(side="left", padx=(8, 4), pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 9, "bold"),
                     fg=color, bg=BG_CARD).pack(side="left")
            tk.Label(row, text=desc, font=FONT_SMALL,
                     fg=TEXT_MUTED, bg=BG_CARD).pack(side="left", padx=8)

        # ── 分割線 ──
        tk.Frame(left, bg=BG_PANEL, height=20).pack()
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", **pad)
        tk.Frame(left, bg=BG_PANEL, height=20).pack()

        # ── 下載位置 ──
        tk.Label(left, text="下載位置", font=FONT_LABEL,
                 fg=TEXT_SECONDARY, bg=BG_PANEL, anchor="w").pack(fill="x", **pad)
        tk.Frame(left, bg=BG_PANEL, height=6).pack()

        dir_frame = tk.Frame(left, bg=BORDER)
        dir_frame.pack(fill="x", padx=20)
        dir_inner = tk.Frame(dir_frame, bg=BG_INPUT)
        dir_inner.pack(fill="x", padx=1, pady=1)

        dir_row = tk.Frame(dir_inner, bg=BG_INPUT)
        dir_row.pack(fill="x")
        tk.Label(dir_row, text="📁", font=FONT_BODY,
                 fg=TEXT_MUTED, bg=BG_INPUT).pack(side="left", padx=(8, 4), pady=6)
        tk.Label(dir_row, text="C:\\downloads\\SEC", font=FONT_MONO,
                 fg=TEXT_SECONDARY, bg=BG_INPUT).pack(side="left")

        tk.Frame(left, bg=BG_PANEL, height=6).pack()
        HoverButton(
            left, bg_normal=BTN_SECONDARY_BG, bg_hover=BTN_SECONDARY_HOVER,
            text="選擇資料夾", font=FONT_SMALL,
            fg=BTN_SECONDARY_FG, pady=6
        ).pack(fill="x", padx=20)

        # ── 底部下載按鈕（固定在底部）──
        spacer = tk.Frame(left, bg=BG_PANEL)
        spacer.pack(fill="both", expand=True)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        btn_area = tk.Frame(left, bg=BG_PANEL)
        btn_area.pack(fill="x", padx=20, pady=16)

        HoverButton(
            btn_area, bg_normal=BTN_PRIMARY_BG, bg_hover=BTN_PRIMARY_HOVER,
            text="⬇  下載選取文件", font=("Segoe UI", 10, "bold"),
            fg=BTN_PRIMARY_FG, pady=10
        ).pack(fill="x")

        tk.Label(btn_area, text="已選取 4 個文件",
                 font=FONT_SMALL, fg=TEXT_MUTED, bg=BG_PANEL).pack(pady=(6, 0))

    # ── 右側面板 ──────────────────────────────────────────
    def _build_right(self, parent):
        right = tk.Frame(parent, bg=BG_DARK)
        right.pack(side="left", fill="both", expand=True)

        # 上方：結果清單（可捲動）
        self._build_results(right)

        # 分割線
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")

        # 下方：進度 + 日誌
        self._build_progress(right)

    def _build_results(self, parent):
        # 標頭列
        header = tk.Frame(parent, bg=BG_DARK)
        header.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(header, text="搜尋結果", font=("Segoe UI", 11, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_DARK).pack(side="left")
        tk.Label(header, text="  AAPL  ·  6 筆文件", font=FONT_SMALL,
                 fg=TEXT_MUTED, bg=BG_DARK).pack(side="left", pady=2)

        # 全選控制
        right_ctrl = tk.Frame(header, bg=BG_DARK)
        right_ctrl.pack(side="right")
        for txt in ["全選", "全不選"]:
            HoverButton(right_ctrl, bg_normal=BG_DARK, bg_hover=BG_HOVER,
                        text=txt, font=FONT_SMALL, fg=TEXT_SECONDARY,
                        pady=4, padx=8).pack(side="left", padx=2)

        # 欄位標頭
        col_header = tk.Frame(parent, bg=BG_DARK)
        col_header.pack(fill="x", padx=20, pady=(0, 4))
        for txt, w in [("", 2), ("類型", 6), ("提交日期", 12), ("檔案名稱", 20)]:
            tk.Label(col_header, text=txt, font=FONT_SMALL,
                     fg=TEXT_MUTED, bg=BG_DARK, width=w, anchor="w").pack(side="left")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=20)
        tk.Frame(parent, bg=BG_DARK, height=4).pack()

        # 捲動容器
        canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical",
                                 command=canvas.yview, bg=BG_PANEL)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True, padx=(20, 0))

        scroll_frame = tk.Frame(canvas, bg=BG_DARK)
        scroll_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(scroll_window, width=e.width)
        canvas.bind("<Configure>", on_resize)
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(
                              scrollregion=canvas.bbox("all")))

        # 範例資料
        filings = [
            ("10-K", "2024-11-01", "2024_FY.pdf",  True),
            ("10-Q", "2024-08-02", "2024_Q3.pdf",  True),
            ("10-Q", "2024-05-03", "2024_Q2.pdf",  True),
            ("10-Q", "2024-02-01", "2024_Q1.pdf",  True),
            ("10-K", "2023-11-03", "2023_FY.pdf",  False),
            ("10-Q", "2023-08-04", "2023_Q3.pdf",  False),
        ]

        for i, (ftype, date, fname, checked) in enumerate(filings):
            row = CheckRow(scroll_frame, ftype, date, fname, is_checked=checked)
            row.pack(fill="x", pady=1)
            # 偶數行微調背景
            if i % 2 == 0:
                pass

    def _build_progress(self, parent):
        area = tk.Frame(parent, bg=BG_PANEL, height=210)
        area.pack(fill="x")
        area.pack_propagate(False)

        tk.Frame(area, bg=BG_PANEL, height=12).pack()

        # 進度標題列
        prog_header = tk.Frame(area, bg=BG_PANEL)
        prog_header.pack(fill="x", padx=20)
        tk.Label(prog_header, text="下載進度", font=("Segoe UI", 9, "bold"),
                 fg=TEXT_SECONDARY, bg=BG_PANEL).pack(side="left")
        self._prog_label = tk.Label(prog_header, text="3 / 4  已完成",
                                     font=FONT_SMALL, fg=TEXT_MUTED, bg=BG_PANEL)
        self._prog_label.pack(side="right")

        tk.Frame(area, bg=BG_PANEL, height=8).pack()

        # 進度條（自製）
        bar_bg = tk.Frame(area, bg=BORDER, height=4)
        bar_bg.pack(fill="x", padx=20)
        self._prog_fill = tk.Frame(bar_bg, bg=ACCENT_GREEN, height=4, width=0)
        self._prog_fill.place(x=0, y=0, relheight=1)

        tk.Frame(area, bg=BG_PANEL, height=10).pack()

        # 日誌區
        log_frame = tk.Frame(area, bg=BG_PANEL)
        log_frame.pack(fill="both", expand=True, padx=20)

        self._logs = [
            ("✓", "downloads/AAPL/10-K/2024_FY.pdf  已完成", ACCENT_GREEN),
            ("✓", "downloads/AAPL/10-Q/2024_Q3.pdf  已完成", ACCENT_GREEN),
            ("✓", "downloads/AAPL/10-Q/2024_Q2.pdf  已完成", ACCENT_GREEN),
            ("↓", "downloads/AAPL/10-Q/2024_Q1.pdf  正在下載…", ACCENT_BLUE),
        ]
        self._log_widgets = []
        for icon, text, color in self._logs:
            w = LogLine(log_frame, icon, text, color)
            w.pack(fill="x", pady=1)
            self._log_widgets.append(w)

        tk.Frame(area, bg=BG_PANEL, height=8).pack()

        # 儲存進度條父容器寬度用
        self._bar_bg = bar_bg

    def _demo_progress(self):
        """模擬進度條動畫，純展示用"""
        def animate():
            for pct in range(0, 81, 1):
                time.sleep(0.015)
                self._bar_bg.update_idletasks()
                w = int(self._bar_bg.winfo_width() * pct / 100)
                self._prog_fill.place(x=0, y=0, relheight=1, width=max(w, 0))
        threading.Thread(target=animate, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
