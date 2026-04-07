"""
SEC EDGAR Downloader - Main Window
Professional, compact, Apple light design
"""

import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Import from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.edgar_client import EdgarClient, FilingRecord, fuzzy_search
from core.filing_resolver import infer_fiscal_year_end_month, resolve_filename
from core.downloader import FilingDownloader
from utils.constants import SUPPORTED_FORMS, DEFAULT_DOWNLOAD_DIR

# ── Colors ──────────────────────────────────────────────
C_BG_APP     = "#F5F5F7"
C_BG_CARD    = "#FFFFFF"
C_BG_SIDE    = "#FAFAFA"
C_BG_INPUT   = "#FFFFFF"
C_BORDER     = "#E5E5E7"
C_BORDER_FOC = "#0071E3"

C_TEXT       = "#1D1D1F"
C_TEXT_SUB   = "#6E6E73"
C_TEXT_MUTED = "#ADADB8"
C_TEXT_LABEL = "#86868B"

C_BLUE       = "#0071E3"
C_BLUE_DARK  = "#0058B0"
C_GREEN      = "#34C759"
C_ORANGE     = "#FF9F0A"
C_RED        = "#FF3B30"
C_GRAY_DOT   = "#C7C7CC"

C_ROW_HOVER  = "#F9F9FB"
C_BTN_DARK   = "#1D1D1F"
C_BTN_DARK_H = "#3A3A3C"

# ── Fonts ───────────────────────────────────────────────
F_TITLE  = ("Segoe UI", 12, "bold")     # Main title
F_BODY   = ("Segoe UI", 11)             # Body text
F_SMALL  = ("Segoe UI", 10)             # Secondary text
F_LABEL  = ("Segoe UI", 9, "bold")      # Labels
F_MONO   = ("Consolas", 10)             # Code/paths
F_TICKER = ("Segoe UI", 20, "bold")     # Ticker input


class AutocompleteEntry(tk.Frame):
    """
    Ticker input with fuzzy search dropdown.
    Calls on_select(ticker, name) when selected.
    """
    def __init__(self, master, on_select=None, **kwargs):
        super().__init__(master, bg=C_BG_SIDE, **kwargs)
        self._on_select = on_select
        self._dropdown_open = False

        # 輸入框容器（模擬邊框聚焦）
        self._border_frame = tk.Frame(self, bg=C_BORDER, bd=0)
        self._border_frame.pack(fill="x")
        inner = tk.Frame(self._border_frame, bg=C_BG_INPUT)
        inner.pack(fill="x", padx=1, pady=1)

        self.var = tk.StringVar()
        self.var.trace_add("write", self._on_type)
        self.entry = tk.Entry(
            inner, textvariable=self.var,
            font=F_TICKER, fg=C_TEXT, bg=C_BG_INPUT,
            insertbackground=C_TEXT, relief="flat", bd=8
        )
        self.entry.pack(fill="x")
        self.entry.bind("<FocusIn>",  self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>",   lambda e: self._on_submit())
        self.entry.bind("<Escape>",   lambda e: self._close_dropdown())
        self.entry.bind("<Down>",     self._on_arrow)

        # 下拉選單（Toplevel）
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._suggestions: list[dict] = []

    def get(self) -> str:
        return self.var.get().strip().upper()

    def set(self, val: str):
        self.var.set(val)

    def _on_focus_in(self, e):
        self._border_frame.config(bg=C_BORDER_FOC)

    def _on_focus_out(self, e):
        self._border_frame.config(bg=C_BORDER)
        self.after(150, self._close_dropdown)

    def _on_type(self, *_):
        q = self.var.get()
        results = fuzzy_search(q)
        if results:
            self._suggestions = results
            self._show_dropdown(results)
        else:
            self._close_dropdown()

    def _show_dropdown(self, results: list[dict]):
        self._close_dropdown()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = self.winfo_width()

        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.geometry(f"{w}x{min(len(results)*34, 200)}+{x}+{y}")
        self._popup.config(bg=C_BORDER)

        self._listbox = tk.Listbox(
            self._popup,
            font=F_BODY, bg=C_BG_CARD, fg=C_TEXT,
            selectbackground=C_BLUE, selectforeground="white",
            relief="flat", bd=0, highlightthickness=0,
            activestyle="none",
        )
        self._listbox.pack(fill="both", expand=True, padx=1, pady=1)

        for item in results:
            self._listbox.insert("end", f"  {item['ticker']}  —  {item['name']}")

        self._listbox.bind("<ButtonRelease-1>", self._on_pick)
        self._listbox.bind("<Return>", self._on_pick)

    def _close_dropdown(self):
        if self._popup:
            self._popup.destroy()
            self._popup = None

    def _on_pick(self, e=None):
        if not self._listbox:
            return
        sel = self._listbox.curselection()
        if sel:
            item = self._suggestions[sel[0]]
            self.var.set(item["ticker"])
            self._close_dropdown()
            if self._on_select:
                self._on_select(item["ticker"], item["name"])

    def _on_arrow(self, e):
        if self._listbox:
            self._listbox.focus_set()
            self._listbox.selection_set(0)

    def _on_submit(self):
        self._close_dropdown()


class QueueRow(tk.Frame):
    """Single row in download queue"""
    STATUS_CFG = {
        "done":     (C_GREEN,    "✓ Done"),
        "progress": (C_BLUE,     "Downloading…"),
        "queued":   (C_GRAY_DOT, "Waiting"),
        "error":    (C_RED,      "✗ Error"),
        "skipped":  (C_ORANGE,   "Exists"),
    }

    def __init__(self, master, filing: FilingRecord, filename: str, **kwargs):
        super().__init__(master, bg=C_BG_CARD, **kwargs)
        self.filing   = filing
        self.filename = filename
        self._status  = "queued"

        # 整行懸停
        self.bind("<Enter>", lambda e: self.config(bg=C_ROW_HOVER))
        self.bind("<Leave>", lambda e: self.config(bg=C_BG_CARD))

        # 勾選框
        self.var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            self, variable=self.var, bg=C_BG_CARD,
            activebackground=C_ROW_HOVER,
            selectcolor=C_BG_INPUT, relief="flat",
            bd=0, highlightthickness=0, cursor="hand2"
        )
        chk.pack(side="left", padx=(10, 2))

        # 類型 badge
        type_color = C_BLUE if filing.form_type == "10-K" else "#9B59B6"
        tk.Label(self, text=filing.form_type, font=("Segoe UI", 8, "bold"),
                 fg=type_color, bg=C_BG_CARD, width=5).pack(side="left", padx=(0, 8))

        # 日期
        tk.Label(self, text=filing.filing_date, font=F_MONO,
                 fg=C_TEXT_SUB, bg=C_BG_CARD).pack(side="left", padx=(0, 12))

        # 檔名
        tk.Label(self, text=filename, font=("Segoe UI", 9, "bold"),
                 fg=C_TEXT, bg=C_BG_CARD).pack(side="left")

        # 狀態（右側）
        self._status_label = tk.Label(self, text="等待中", font=F_SMALL,
                                       fg=C_GRAY_DOT, bg=C_BG_CARD)
        self._status_label.pack(side="right", padx=14)

        # 讓子元件也繼承懸停效果
        for w in self.winfo_children():
            w.bind("<Enter>", lambda e: self.config(bg=C_ROW_HOVER))
            w.bind("<Leave>", lambda e: self.config(bg=C_BG_CARD))

    def set_status(self, status: str, extra: str = ""):
        """status: done / progress / queued / error / skipped"""
        color, label = self.STATUS_CFG.get(status, (C_GRAY_DOT, status))
        text = f"{label} {extra}".strip()
        self._status_label.config(text=text, fg=color)
        self._status = status


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SEC Downloader")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.configure(bg=C_BG_APP)

        self._client      = EdgarClient()
        self._filings:    list[FilingRecord]  = []
        self._fye_month:  int                 = 12
        self._queue_rows: list[QueueRow]      = []
        self._download_dir = Path(DEFAULT_DOWNLOAD_DIR)
        self._worker: threading.Thread | None = None

        self._build_ui()

    # ══════════════════════════════════════════════════
    # UI 建構
    # ══════════════════════════════════════════════════

    def _build_ui(self):
        # 外層卡片（白色圓角容器）
        outer = tk.Frame(self, bg=C_BG_APP)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        card = tk.Frame(outer, bg=C_BG_CARD, relief="flat", bd=1)
        card.pack(fill="both", expand=True)

        self._build_side(card)
        tk.Frame(card, bg=C_BORDER, width=1).pack(side="left", fill="y")
        self._build_main(card)

    # ── 左側控制面板 ──────────────────────────────────
    def _build_side(self, parent):
        side = tk.Frame(parent, bg=C_BG_SIDE, width=300)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        pad = {"padx": 24}

        tk.Frame(side, bg=C_BG_SIDE, height=22).pack()

        # 標題
        tk.Label(side, text="SEC DOWNLOADER", font=F_LABEL,
                 fg=C_BLUE, bg=C_BG_SIDE).pack(anchor="w", **pad)

        tk.Frame(side, bg=C_BG_SIDE, height=18).pack()

        # ── Ticker Input ──
        tk.Label(side, text="TICKER", font=F_LABEL,
                 fg=C_TEXT_LABEL, bg=C_BG_SIDE).pack(anchor="w", **pad)
        tk.Frame(side, bg=C_BG_SIDE, height=4).pack()

        self._ticker_entry = AutocompleteEntry(
            side, on_select=self._on_ticker_selected
        )
        self._ticker_entry.pack(fill="x", **pad)
        self._ticker_entry.set("AAPL")

        tk.Frame(side, bg=C_BG_SIDE, height=3).pack()
        self._ticker_hint = tk.Label(side, text="", font=F_SMALL,
                                      fg=C_GREEN, bg=C_BG_SIDE)
        self._ticker_hint.pack(anchor="w", **pad)

        tk.Frame(side, bg=C_BG_SIDE, height=14).pack()

        # ── Search Button ──
        self._btn_search = tk.Button(
            side, text="SEARCH", font=F_BODY,
            fg="white", bg=C_BLUE, relief="flat", bd=0, pady=9,
            cursor="hand2", command=self._on_search
        )
        self._btn_search.pack(fill="x", **pad)
        self._btn_search.bind("<Enter>", lambda e: self._btn_search.config(bg=C_BLUE_DARK))
        self._btn_search.bind("<Leave>", lambda e: self._btn_search.config(bg=C_BLUE))

        tk.Frame(side, bg=C_BORDER, height=1).pack(fill="x", padx=24, pady=18)

        # ── Year Dropdown ──
        tk.Label(side, text="YEAR", font=F_LABEL,
                 fg=C_TEXT_LABEL, bg=C_BG_SIDE).pack(anchor="w", **pad)
        tk.Frame(side, bg=C_BG_SIDE, height=4).pack()

        self._year_var = tk.StringVar(value="All")
        year_frame = tk.Frame(side, bg=C_BORDER)
        year_frame.pack(fill="x", **pad)
        year_inner = tk.Frame(year_frame, bg=C_BG_INPUT)
        year_inner.pack(fill="x", padx=1, pady=1)

        self._year_combo = ttk.Combobox(
            year_inner, textvariable=self._year_var,
            font=F_BODY, state="readonly",
            values=["All"]
        )
        self._year_combo.pack(fill="x", padx=6, pady=5)
        self._year_combo.bind("<<ComboboxSelected>>", self._on_year_changed)

        tk.Frame(side, bg=C_BG_SIDE, height=14).pack()

        # ── File Type ──
        tk.Label(side, text="TYPE", font=F_LABEL,
                 fg=C_TEXT_LABEL, bg=C_BG_SIDE).pack(anchor="w", **pad)
        tk.Frame(side, bg=C_BG_SIDE, height=6).pack()

        type_row = tk.Frame(side, bg=C_BG_SIDE)
        type_row.pack(fill="x", **pad)

        self._type_vars = {}
        for ft, label in [("10-K", "10-K Annual"), ("10-Q", "10-Q Quarterly")]:
            var = tk.BooleanVar(value=True)
            self._type_vars[ft] = var
            chk = tk.Checkbutton(
                type_row, text=label, variable=var,
                font=F_BODY, fg=C_TEXT, bg=C_BG_SIDE,
                selectcolor=C_BG_INPUT, activebackground=C_BG_SIDE,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                command=self._on_type_changed
            )
            chk.pack(anchor="w", pady=2)

        # ── Download Folder ──
        tk.Frame(side, bg=C_BORDER, height=1).pack(fill="x", padx=24, pady=18)

        tk.Label(side, text="FOLDER", font=F_LABEL,
                 fg=C_TEXT_LABEL, bg=C_BG_SIDE).pack(anchor="w", **pad)
        tk.Frame(side, bg=C_BG_SIDE, height=4).pack()

        dir_row = tk.Frame(side, bg=C_BG_SIDE)
        dir_row.pack(fill="x", **pad)

        self._dir_label = tk.Label(
            dir_row, text=str(self._download_dir),
            font=F_MONO, fg=C_TEXT_SUB, bg=C_BG_SIDE,
            anchor="w", wraplength=200
        )
        self._dir_label.pack(side="left", fill="x", expand=True)

        tk.Button(
            dir_row, text="…", font=F_SMALL, fg=C_TEXT_SUB,
            bg=C_BG_SIDE, relief="flat", bd=0, cursor="hand2",
            command=self._pick_dir
        ).pack(side="right")

        # ── 底部：Download 按鈕 ──
        spacer = tk.Frame(side, bg=C_BG_SIDE)
        spacer.pack(fill="both", expand=True)

        tk.Frame(side, bg=C_BORDER, height=1).pack(fill="x")
        btn_area = tk.Frame(side, bg=C_BG_SIDE)
        btn_area.pack(fill="x", padx=24, pady=16)

        self._btn_download = tk.Button(
            btn_area, text="⬇ DOWNLOAD", font=F_TITLE,
            fg="white", bg=C_BTN_DARK, relief="flat", bd=0, pady=11,
            cursor="hand2", command=self._on_download, state="disabled"
        )
        self._btn_download.pack(fill="x")
        self._btn_download.bind("<Enter>",
                                 lambda e: self._btn_download.config(bg=C_BTN_DARK_H)
                                 if self._btn_download["state"] != "disabled" else None)
        self._btn_download.bind("<Leave>",
                                 lambda e: self._btn_download.config(bg=C_BTN_DARK)
                                 if self._btn_download["state"] != "disabled" else None)

        self._selected_label = tk.Label(
            btn_area, text="No items selected", font=F_SMALL, fg=C_TEXT_MUTED, bg=C_BG_SIDE
        )
        self._selected_label.pack(pady=(5, 0))

    # ── 右側主區域 ────────────────────────────────────
    def _build_main(self, parent):
        main = tk.Frame(parent, bg=C_BG_CARD)
        main.pack(side="left", fill="both", expand=True)

        # 標題列
        header = tk.Frame(main, bg=C_BG_CARD)
        header.pack(fill="x", padx=24, pady=(22, 10))

        self._queue_title = tk.Label(
            header, text="Download Queue", font=F_TITLE,
            fg=C_TEXT, bg=C_BG_CARD
        )
        self._queue_title.pack(side="left")

        self._queue_count = tk.Label(
            header, text="", font=F_SMALL, fg=C_TEXT_MUTED, bg=C_BG_CARD
        )
        self._queue_count.pack(side="left", padx=8, pady=2)

        # Select All / Deselect All
        ctrl = tk.Frame(header, bg=C_BG_CARD)
        ctrl.pack(side="right")
        for txt, cmd in [("Select All", self._select_all), ("Deselect All", self._deselect_all)]:
            b = tk.Button(ctrl, text=txt, font=F_SMALL, fg=C_BLUE,
                          bg=C_BG_CARD, relief="flat", bd=0,
                          cursor="hand2", command=cmd)
            b.pack(side="left", padx=4)

        # Column Headers
        col_bar = tk.Frame(main, bg=C_BG_CARD)
        col_bar.pack(fill="x", padx=24)
        for txt in ["", "Type", "Filing Date", "Filename"]:
            tk.Label(col_bar, text=txt, font=F_SMALL,
                     fg=C_TEXT_MUTED, bg=C_BG_CARD,
                     width={"": 3, "Type": 6, "Filing Date": 12, "Filename": 0}.get(txt, 0),
                     anchor="w").pack(side="left")

        tk.Frame(main, bg=C_BORDER, height=1).pack(fill="x", padx=24, pady=(4, 0))

        # 捲動清單
        list_frame = tk.Frame(main, bg=C_BG_CARD)
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, bg=C_BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical",
                                   command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=C_BG_CARD)
        self._scroll_window = canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw"
        )
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._scroll_window, width=e.width))
        self._scroll_frame.bind("<Configure>",
                                 lambda e: canvas.configure(
                                     scrollregion=canvas.bbox("all")))
        self._canvas = canvas

        # Empty State
        self._empty_label = tk.Label(
            self._scroll_frame,
            text="Enter a ticker and click SEARCH",
            font=F_BODY, fg=C_TEXT_MUTED, bg=C_BG_CARD
        )
        self._empty_label.pack(pady=60)

        # 進度區
        tk.Frame(main, bg=C_BORDER, height=1).pack(fill="x")
        self._build_progress(main)

    def _build_progress(self, parent):
        prog_area = tk.Frame(parent, bg=C_BG_CARD)
        prog_area.pack(fill="x", padx=24, pady=12)

        top_row = tk.Frame(prog_area, bg=C_BG_CARD)
        top_row.pack(fill="x", pady=(0, 6))

        tk.Label(top_row, text="Progress", font=F_LABEL,
                 fg=C_TEXT_LABEL, bg=C_BG_CARD).pack(side="left")
        self._prog_count = tk.Label(top_row, text="", font=F_SMALL,
                                     fg=C_TEXT_MUTED, bg=C_BG_CARD)
        self._prog_count.pack(side="right")

        # 進度條背景
        bar_bg = tk.Frame(prog_area, bg=C_BORDER, height=4)
        bar_bg.pack(fill="x")
        bar_bg.pack_propagate(False)
        self._prog_fill = tk.Frame(bar_bg, bg=C_GREEN, height=4)
        self._prog_fill.place(x=0, y=0, relheight=1, relwidth=0)
        self._bar_bg = bar_bg

        # 日誌
        log_frame = tk.Frame(prog_area, bg=C_BG_CARD)
        log_frame.pack(fill="x", pady=(8, 0))

        self._log_text = tk.Text(
            log_frame, height=3, font=F_MONO,
            fg=C_TEXT_SUB, bg=C_BG_CARD,
            relief="flat", bd=0, state="disabled",
            highlightthickness=0, wrap="word"
        )
        self._log_text.pack(fill="x")
        self._log_text.tag_config("success", foreground=C_GREEN)
        self._log_text.tag_config("error",   foreground=C_RED)
        self._log_text.tag_config("warn",    foreground=C_ORANGE)
        self._log_text.tag_config("info",    foreground=C_TEXT_MUTED)

        # Open Folder Button
        path_row = tk.Frame(prog_area, bg=C_BG_CARD)
        path_row.pack(fill="x", pady=(8, 0))

        self._open_btn = tk.Button(
            path_row,
            text="📁 OPEN FOLDER",
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg=C_GREEN,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._open_folder
        )
        self._open_btn.pack(side="left")

        # Hover effect
        self._open_btn.bind("<Enter>", lambda _: self._open_btn.config(
            bg="#2ebd50" if self._open_btn["state"] != "disabled" else C_GREEN))
        self._open_btn.bind("<Leave>", lambda _: self._open_btn.config(bg=C_GREEN))

        # Path display
        path_label = tk.Label(path_row, text="", font=F_SMALL, fg=C_TEXT_MUTED, bg=C_BG_CARD)
        path_label.pack(side="right")
        self._path_display = path_label
        self._update_path_display()

    # ══════════════════════════════════════════════════
    # 事件處理
    # ══════════════════════════════════════════════════

    def _on_ticker_selected(self, ticker: str, name: str):
        self._ticker_hint.config(text=f"{name}", fg=C_GREEN)

    def _on_search(self):
        ticker = self._ticker_entry.get()
        if not ticker:
            messagebox.showwarning("Info", "Enter a ticker code")
            return
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Info", "Please wait for current operation")
            return

        self._log("Searching " + ticker + " …", "info")
        self._btn_search.config(state="disabled", text="SEARCHING…")
        self._queue_rows.clear()
        for w in self._scroll_frame.winfo_children():
            w.destroy()

        def task():
            try:
                cik  = self._client.get_cik(ticker)
                name = self._client.get_company_name(cik)

                # 更新 ticker hint
                self.after(0, lambda: self._ticker_hint.config(
                    text=f"{name}", fg=C_GREEN))

                # Load available years into dropdown
                years = self._client.get_available_years(cik)
                year_opts = ["All"] + [str(y) for y in years]
                self.after(0, lambda: self._year_combo.config(values=year_opts))
                self.after(0, lambda: self._year_var.set("All"))

                # Load filings
                selected_forms = [f for f, v in self._type_vars.items() if v.get()]
                filings = self._client.get_filings(cik, form_types=selected_forms)

                self._filings    = filings
                self._current_cik = cik

                # Calculate fiscal year
                all_filings = self._client.get_filings(cik)
                self._fye_month = infer_fiscal_year_end_month(all_filings)

                self.after(0, lambda: self._populate_queue(filings))
            except Exception as e:
                self.after(0, lambda: self._log(f"✗ Search failed: {e}", "error"))
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self._btn_search.config(
                    state="normal", text="SEARCH"))

        self._worker = threading.Thread(target=task, daemon=True)
        self._worker.start()

    def _on_year_changed(self, e=None):
        """Filter list when year dropdown changes (no API re-call)"""
        if not self._filings:
            return
        year_str = self._year_var.get()
        year     = None if year_str == "All" else int(year_str)

        selected_forms = [f for f, v in self._type_vars.items() if v.get()]
        filtered = [
            f for f in self._filings
            if f.form_type in selected_forms
            and (year is None or f.report_date.startswith(str(year)))
        ]
        self._populate_queue(filtered)

    def _on_type_changed(self):
        self._on_year_changed()

    def _populate_queue(self, filings: list[FilingRecord]):
        """Clear and repopulate queue"""
        for w in self._scroll_frame.winfo_children():
            w.destroy()
        self._queue_rows.clear()

        if not filings:
            tk.Label(self._scroll_frame, text="No matching files",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(pady=40)
            self._update_selected_count()
            return

        for filing in filings:
            fname = resolve_filename(filing, self._fye_month)
            row   = QueueRow(self._scroll_frame, filing, fname)
            row.pack(fill="x")
            tk.Frame(self._scroll_frame, bg=C_BORDER, height=1).pack(fill="x")
            row.var.trace_add("write", lambda *_: self._update_selected_count())
            self._queue_rows.append(row)

        self._update_selected_count()
        self._btn_download.config(state="normal")
        self._log(f"Found {len(filings)} files", "info")

    def _update_selected_count(self):
        sel   = sum(1 for r in self._queue_rows if r.var.get())
        total = len(self._queue_rows)
        self._queue_count.config(text=f"· {total} files, {sel} selected")
        self._selected_label.config(
            text=f"{sel} files selected" if sel > 0 else "No files selected"
        )

    def _select_all(self):
        for r in self._queue_rows:
            r.var.set(True)

    def _deselect_all(self):
        for r in self._queue_rows:
            r.var.set(False)

    def _on_download(self):
        selected = [r for r in self._queue_rows if r.var.get()]
        if not selected:
            messagebox.showinfo("Info", "Select at least one file")
            return
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Info", "Please wait for current operation")
            return

        self._btn_download.config(state="disabled")
        self._prog_fill.place(relwidth=0)
        self._prog_count.config(text=f"0 / {len(selected)}")

        for r in selected:
            r.set_status("queued")

        def task():
            filings_to_dl = [r.filing for r in selected]
            ticker        = self._ticker_entry.get()

            def on_log(msg, level="info"):
                self.after(0, lambda m=msg, l=level: self._log(m, l))

            def on_progress(done, total):
                pct = done / total if total > 0 else 0
                self.after(0, lambda: self._prog_fill.place(relwidth=pct))
                self.after(0, lambda: self._prog_count.config(
                    text=f"{done} / {total}"))
                if done < total:
                    self.after(0, lambda: selected[done].set_status("progress"))
                if done > 0:
                    self.after(0, lambda i=done - 1: selected[i].set_status("done"))

            dl = FilingDownloader(
                client      = self._client,
                output_root = self._download_dir,
                on_log      = on_log,
                on_progress = on_progress,
            )

            try:
                dl.download_batch(ticker, filings_to_dl, self._fye_month)
                # Mark last item as done
                if selected:
                    self.after(0, lambda: selected[-1].set_status("done"))
            except Exception as e:
                self.after(0, lambda: self._log(f"✗ Download failed: {e}", "error"))
            finally:
                self.after(0, lambda: self._btn_download.config(state="normal"))

        self._worker = threading.Thread(target=task, daemon=True)
        self._worker.start()

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=str(self._download_dir))
        if d:
            self._download_dir = Path(d)
            self._dir_label.config(text=d)
            self._update_path_display()

    def _update_path_display(self):
        """Update path display in progress section"""
        path_text = str(self._download_dir)
        # Remove 'downloads' suffix if present
        if path_text.endswith("downloads"):
            path_text = path_text[:-9].rstrip("\\/")
        if len(path_text) > 45:
            path_text = "..." + path_text[-42:]
        self._path_display.config(text=path_text)

    def _open_folder(self):
        path = str(self._download_dir)
        if sys.platform == "win32":
            os.startfile(path)

    def _log(self, msg: str, level: str = "info"):
        self._log_text.config(state="normal")
        self._log_text.insert("end", msg + "\n", level)
        self._log_text.see("end")
        self._log_text.config(state="disabled")


# ── 進入點 ───────────────────────────────────────────────
if __name__ == "__main__":
    # Windows 高 DPI 支援
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    app.mainloop()
