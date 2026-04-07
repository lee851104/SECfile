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
# 支援環境變數設定下載資料夾 (用於遠程部署)
_download_dir = Path(os.environ.get("DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR)).resolve()
# 確保下載資料夾存在
_download_dir.mkdir(parents=True, exist_ok=True)

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
    """設定下載資料夾路徑。支援：
    1. 本地執行：File System Access API 選擇的完整路徑
    2. 限制環境：只能取得資料夾名稱（建立在應用目錄下）
    3. Render：使用環境變數或預設路徑
    """
    global _download_dir
    data = request.json or {}
    new_path = data.get("path", "").strip()

    debug_log = []
    debug_log.append(f"Received path: {repr(new_path)}")
    debug_log.append(f"Current _download_dir before: {_download_dir}")

    # 檢查是否只收到資料夾名稱（沒有完整路徑）
    is_folder_name_only = new_path and not ((':\\' in new_path) or new_path.startswith('/'))
    if is_folder_name_only:
        debug_log.append(f"⚠ Received folder name only: {new_path}")
        debug_log.append(f"ℹ Browser File System Access API cannot provide full path in this configuration")
        # 使用預設路徑加上資料夾名稱
        new_path = str(Path(DEFAULT_DOWNLOAD_DIR) / new_path)
        debug_log.append(f"ℹ Using default path with folder name: {new_path}")

    # 如果沒有提供路徑，檢查環境變數或使用預設
    if not new_path:
        env_path = os.environ.get("DOWNLOAD_DIR", "")
        if env_path:
            new_path = env_path
        else:
            # 在 Render 上，使用 /tmp/downloads
            import socket
            is_render = "render" in socket.getfqdn().lower() or os.environ.get("RENDER")
            if is_render:
                new_path = "/tmp/downloads"
            else:
                new_path = str(DEFAULT_DOWNLOAD_DIR)
        debug_log.append(f"Using default path: {new_path}")

    try:
        path_obj = Path(new_path).resolve()
        debug_log.append(f"Resolved to: {path_obj}")

        # 確保資料夾存在
        path_obj.mkdir(parents=True, exist_ok=True)
        debug_log.append(f"Folder created/verified")

        # 更新全局變數
        _download_dir = path_obj
        debug_log.append(f"Updated _download_dir to: {_download_dir}")

        response = {"path": str(_download_dir), "ok": True, "debug": debug_log}
        debug_log.append(f"Returning response with path: {_download_dir}")

        # 同時列印到終端
        for msg in debug_log:
            print(f"[browse_folder] {msg}", flush=True)

        return jsonify(response)
    except Exception as e:
        debug_log.append(f"Error: {e}")
        import traceback
        tb = traceback.format_exc()
        debug_log.append(f"Traceback: {tb}")

        # 列印到終端
        for msg in debug_log:
            print(f"[browse_folder] {msg}", flush=True)

        return jsonify({"error": str(e), "debug": debug_log}), 400


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

        # 調試：確認使用的路徑（使用當前的全局 _download_dir）
        current_dir = _download_dir
        print(f"[download] Using _download_dir: {current_dir}", flush=True)
        print(f"[download] _download_dir type: {type(current_dir)}", flush=True)

        dl = FilingDownloader(
            client      = _client,
            output_root = current_dir,
            on_log      = on_log,
            on_progress = on_progress,
        )
        try:
            on_log(f"Downloading to: {current_dir}", "info")
            on_log(f"Downloading {len(filings)} files for {ticker}...", "info")
            dl.download_batch(ticker, filings, fye_month)
            folder = str(_download_dir / ticker.upper())
            q.put({"type": "done", "folder": folder})
        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()
            q.put({"type": "error", "msg": error_msg})
            print(f"Download error:\n{tb}", file=sys.stderr)
            on_log(f"Error: {error_msg}", "error")

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
        idle_count = 0
        while True:
            try:
                # 增加超時到 60 秒（大檔案可能需要很久）
                event = q.get(timeout=60)
                idle_count = 0
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("done", "error"):
                    _tasks.pop(task_id, None)
                    break
            except queue.Empty:
                # 定期 ping 保持連線，避免 30 秒後被關閉
                idle_count += 1
                if idle_count > 10:
                    # 超過 10 分鐘無進度，推測出錯
                    _tasks.pop(task_id, None)
                    break
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"SEC Downloader web app running at http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
