"""
SEC EDGAR 文件下載器 — 緊湊設計版本
簡潔、專業、迷你工具風格
執行: python ui_preview_compact.py
"""

import tkinter as tk
from tkinter import ttk
import threading
import time

# ── 配色 ─────────────────────────────────────────────
BG_MAIN       = "#F5F5F7"   # 主背景（亮灰）
BG_SIDE       = "#FAFAFA"   # 左側面板背景
BG_INPUT      = "#FFFFFF"   # 輸入框背景
BORDER_COLOR  = "#E8E8E8"   # 邊框
TEXT_PRIMARY  = "#1D1D1F"   # 主文字
TEXT_MUTED    = "#8E8E93"   # 淡化文字
TEXT_LABEL    = "#A6A6A6"   # 標籤文字

ACCENT_BLUE   = "#0071E3"   # 主要強調色（Apple藍）
BTN_DARK      = "#1D1D1F"   # 深色按鈕
BTN_DARK_HOVER= "#2D2D2F"
STATUS_GREEN  = "#34C759"   # 完成（綠）
STATUS_BLUE   = "#0071E3"   # 進行中（藍）
STATUS_GRAY   = "#C7C7CC"   # 待處理（灰）

# ── 字型 ─────────────────────────────────────────────
FONT_TITLE   = ("Segoe UI", 10, "bold")
FONT_BODY    = ("Segoe UI", 9)
FONT_SMALL   = ("Segoe UI", 8)
FONT_LABEL   = ("Segoe UI", 8, "bold")
FONT_MONO    = ("Consolas", 8)


class CompactApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SEC Downloader")
        self.geometry("620x420")
        self.minsize(600, 400)
        self.configure(bg=BG_MAIN)
        self.resizable(True, True)

        # 移除預設邊框（Windows 風格）
        self.wm_attributes("-transparentcolor", BG_MAIN)

        # 主容器（白色卡片）
        self._build_card()

    def _build_card(self):
        card = tk.Frame(self, bg="white")
        card.pack(fill="both", expand=True, padx=20, pady=20)

        # 設置陰影（用邊框模擬）
        card.configure(relief="flat", bd=1, bg="white")

        # 左側面板
        self._build_left(card)

        # 垂直分割線
        tk.Frame(card, bg=BORDER_COLOR, width=1).pack(side="left", fill="y")

        # 右側主區域
        self._build_right(card)

    # ── 左側面板 ──────────────────────────────────────
    def _build_left(self, parent):
        side = tk.Frame(parent, bg=BG_SIDE)
        side.pack(side="left", fill="y", padx=20, pady=20)

        # 標題
        tk.Label(side, text="SEC DOWNLOADER", font=("Segoe UI", 9, "bold"),
                 fg=ACCENT_BLUE, bg=BG_SIDE).pack(anchor="w", pady=(0, 16))

        # ── Ticker 輸入 ──
        tk.Label(side, text="TICKER", font=FONT_LABEL,
                 fg=TEXT_LABEL, bg=BG_SIDE).pack(anchor="w", pady=(0, 4))

        ticker_frame = tk.Frame(side, bg=BG_INPUT, relief="solid", bd=1)
        ticker_frame.pack(fill="x", pady=(0, 12))
        ticker_frame.configure(bg=BG_INPUT)

        self.ticker_var = tk.StringVar(value="AAPL")
        tk.Entry(ticker_frame, textvariable=self.ticker_var,
                 font=("Segoe UI", 12, "bold"), fg=TEXT_PRIMARY,
                 bg=BG_INPUT, relief="flat", bd=0, padx=8, pady=6).pack(
            fill="x", side="left")

        # ── 年度選擇 ──
        tk.Label(side, text="YEAR", font=FONT_LABEL,
                 fg=TEXT_LABEL, bg=BG_SIDE).pack(anchor="w", pady=(0, 4))

        year_frame = tk.Frame(side, bg=BG_INPUT, relief="solid", bd=1)
        year_frame.pack(fill="x", pady=(0, 12))

        self.year_var = tk.StringVar(value="2024")
        year_combo = tk.Entry(year_frame, textvariable=self.year_var,
                              font=FONT_BODY, fg=TEXT_PRIMARY,
                              bg=BG_INPUT, relief="flat", bd=0, padx=8, pady=6)
        year_combo.pack(fill="x")

        # ── 文件類型選擇 ──
        tk.Label(side, text="TYPE", font=FONT_LABEL,
                 fg=TEXT_LABEL, bg=BG_SIDE).pack(anchor="w", pady=(0, 6))

        type_frame = tk.Frame(side, bg=BG_SIDE)
        type_frame.pack(fill="x", pady=(0, 14))

        self.type_var = tk.StringVar(value="10-K")
        for btn_text in ["10-K", "10-Q"]:
            btn = tk.Button(type_frame, text=btn_text, font=FONT_LABEL,
                            width=8, pady=6, cursor="hand2",
                            relief="flat", bd=0)
            btn.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._setup_type_button(btn, btn_text)

        # ── Fetch 按鈕 ──
        fetch_btn = tk.Button(side, text="FETCH REPORTS", font=FONT_LABEL,
                              fg="white", bg=ACCENT_BLUE,
                              relief="flat", bd=0, pady=8, cursor="hand2")
        fetch_btn.pack(fill="x", pady=(0, 12))
        fetch_btn.bind("<Enter>", lambda e: fetch_btn.config(bg="#005FCC"))
        fetch_btn.bind("<Leave>", lambda e: fetch_btn.config(bg=ACCENT_BLUE))

    def _setup_type_button(self, btn, btn_text):
        """設置類型按鈕的狀態切換"""
        def on_click():
            self.type_var.set(btn_text)
            # 更新所有按鈕外觀
            for widget in btn.master.winfo_children():
                if isinstance(widget, tk.Button):
                    if widget.cget("text") == btn_text:
                        widget.config(bg=BTN_DARK, fg="white")
                    else:
                        widget.config(bg="#E8E8E8", fg=TEXT_MUTED)
        btn.config(command=on_click)
        # 初始狀態
        if btn_text == "10-K":
            btn.config(bg=BTN_DARK, fg="white")
        else:
            btn.config(bg="#E8E8E8", fg=TEXT_MUTED)

    # ── 右側面板 ──────────────────────────────────────
    def _build_right(self, parent):
        right = tk.Frame(parent, bg="white")
        right.pack(side="left", fill="both", expand=True, padx=20, pady=20)

        # 標題列
        header = tk.Frame(right, bg="white")
        header.pack(fill="x", pady=(0, 12))

        tk.Label(header, text="DOWNLOAD QUEUE", font=FONT_LABEL,
                 fg=TEXT_LABEL, bg="white").pack(side="left")

        # 打開資料夾按鈕
        folder_btn = tk.Button(header, text="📁  OPEN FOLDER", font=FONT_SMALL,
                               fg=ACCENT_BLUE, bg="white", relief="flat", bd=0,
                               cursor="hand2", padx=0)
        folder_btn.pack(side="right")
        folder_btn.bind("<Enter>", lambda e: folder_btn.config(fg="#005FCC"))
        folder_btn.bind("<Leave>", lambda e: folder_btn.config(fg=ACCENT_BLUE))

        # 分割線
        tk.Frame(right, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(0, 12))

        # 佇列清單（可捲動）
        canvas = tk.Canvas(right, bg="white", highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(scroll_window, width=e.width - 20)
        canvas.bind("<Configure>", on_resize)
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(
                              scrollregion=canvas.bbox("all")))

        # 範例下載項目
        self._items = [
            ("AAPL_2024_10K.pdf", "DONE", STATUS_GREEN),
            ("AAPL_2024_Q3.pdf", "45%", STATUS_BLUE),
            ("AAPL_2024_Q2.pdf", "QUEUED", STATUS_GRAY),
        ]

        self._item_frames = []
        for filename, status, color in self._items:
            item = tk.Frame(scroll_frame, bg="white")
            item.pack(fill="x", pady=(0, 1))

            # 左側：狀態點 + 檔名
            left_box = tk.Frame(item, bg="white")
            left_box.pack(side="left", fill="both", expand=True)

            status_dot = tk.Frame(left_box, bg=color, width=8, height=8)
            status_dot.pack(side="left", padx=(0, 8), pady=6)
            status_dot.pack_propagate(False)

            tk.Label(left_box, text=filename, font=FONT_BODY,
                     fg=TEXT_PRIMARY, bg="white").pack(side="left", anchor="w")

            # 右側：狀態標籤
            status_label = tk.Label(item, text=status, font=FONT_SMALL,
                                    fg=color if status != "DONE" else STATUS_GREEN,
                                    bg="white")
            status_label.pack(side="right", padx=8)

            # 分割線
            tk.Frame(scroll_frame, bg=BORDER_COLOR, height=1).pack(fill="x")

            self._item_frames.append((item, status_dot, status_label))

        # 底部路徑顯示
        bottom = tk.Frame(right, bg="white")
        bottom.pack(fill="x", pady=(12, 0))

        tk.Frame(bottom, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(0, 8))
        tk.Label(bottom, text="PATH: C:\\Downloads\\SEC\\",
                 font=FONT_MONO, fg=TEXT_MUTED, bg="white").pack(anchor="w")


if __name__ == "__main__":
    app = CompactApp()
    app.mainloop()
