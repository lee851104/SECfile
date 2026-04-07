"""
SEC EDGAR Downloader - Flask Web App
用法：py app_web.py  → 開啟 http://localhost:5000
"""

import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from core.edgar_client import EdgarClient, FilingRecord, fuzzy_search
from core.downloader import FilingDownloader
from core.filing_resolver import infer_fiscal_year_end_month, resolve_filename
from utils.constants import DEFAULT_DOWNLOAD_DIR

app = Flask(__name__)

_client = EdgarClient()
_download_dir = Path(DEFAULT_DOWNLOAD_DIR).resolve()

# 進行中的下載任務：task_id -> {"queue": Queue, "thread": Thread}
_tasks: dict[str, dict] = {}


# ── Routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/folder")
def get_folder():
    return jsonify({"path": str(_download_dir)})


@app.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    """用 tkinter 開啟資料夾選擇器（本機執行，不需要前端支援）。"""
    global _download_dir
    import tkinter as tk
    from tkinter import filedialog

    result: dict = {}

    def pick():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(initialdir=str(_download_dir))
        root.destroy()
        result["path"] = path

    t = threading.Thread(target=pick)
    t.start()
    t.join(timeout=60)

    chosen = result.get("path")
    if chosen:
        _download_dir = Path(chosen).resolve()

    return jsonify({"path": str(_download_dir)})


@app.route("/api/open-folder")
def open_folder():
    """在系統檔案管理員開啟指定資料夾。"""
    path = request.args.get("path", str(_download_dir))
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/autocomplete")
def autocomplete():
    q = request.args.get("q", "")
    return jsonify(fuzzy_search(q))


@app.route("/api/search")
def search():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400

    try:
        cik        = _client.get_cik(ticker)
        name       = _client.get_company_name(cik)
        years      = _client.get_available_years(cik)
        all_filings = _client.get_filings(cik)
        fye_month  = infer_fiscal_year_end_month(all_filings)

        filings_data = [
            {
                "accession_number": f.accession_number,
                "form_type":        f.form_type,
                "filing_date":      f.filing_date,
                "report_date":      f.report_date,
                "primary_document": f.primary_document,
                "cik":              f.cik,
                "filename":         resolve_filename(f, fye_month),
            }
            for f in all_filings
        ]

        return jsonify({
            "ticker":    ticker,
            "name":      name,
            "cik":       cik,
            "years":     years,
            "fye_month": fye_month,
            "filings":   filings_data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def start_download():
    data      = request.json or {}
    ticker    = data.get("ticker", "")
    fye_month = int(data.get("fye_month", 12))
    raw       = data.get("filings", [])

    filings = [
        FilingRecord(
            accession_number = f["accession_number"],
            form_type        = f["form_type"],
            filing_date      = f["filing_date"],
            report_date      = f["report_date"],
            primary_document = f["primary_document"],
            cik              = int(f["cik"]),
        )
        for f in raw
    ]

    task_id = str(uuid.uuid4())
    q = queue.Queue()
    _tasks[task_id] = {"queue": q}

    def run():
        def on_log(msg, level="info"):
            q.put({"type": "log", "msg": msg, "level": level})

        def on_progress(done, total):
            q.put({"type": "progress", "done": done, "total": total})

        dl = FilingDownloader(
            client      = _client,
            output_root = _download_dir,
            on_log      = on_log,
            on_progress = on_progress,
        )
        try:
            dl.download_batch(ticker, filings, fye_month)
            folder = str(_download_dir / ticker.upper())
            q.put({"type": "done", "folder": folder})
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})

    t = threading.Thread(target=run, daemon=True)
    _tasks[task_id]["thread"] = t
    t.start()

    return jsonify({"task_id": task_id})


@app.route("/api/progress/<task_id>")
def progress_stream(task_id):
    if task_id not in _tasks:
        return jsonify({"error": "task not found"}), 404

    q = _tasks[task_id]["queue"]

    def generate():
        while True:
            try:
                event = q.get(timeout=25)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("done", "error"):
                    _tasks.pop(task_id, None)
                    break
            except queue.Empty:
                # 定期 ping 保持連線
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    print("SEC Downloader web app running at http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
