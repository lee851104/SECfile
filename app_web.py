"""
SEC EDGAR Downloader - Flask Web App
用法：py app_web.py  → 開啟 http://localhost:5000

下載流程：
  後端負責從 SEC 下載 HTML、清理 XBRL、轉換成 PDF bytes 回傳給瀏覽器。
  前端用 File System Access API 把 PDF bytes 直接寫入使用者自己電腦的資料夾。
  伺服器不儲存任何檔案。
"""

import os
import sys
import subprocess
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request

from core.edgar_client import EdgarClient, FilingRecord, fuzzy_search
from core.downloader import _clean_xbrl, _prepare_html_for_pdf, convert_html_to_pdf_bytes
from core.filing_resolver import infer_fiscal_year_end_month, resolve_filename

app = Flask(__name__)
_client = EdgarClient()

# 快取使用者資料夾的完整路徑：marker_id -> full_path
_folder_cache: dict[str, str] = {}


# ── Routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/register-folder", methods=["POST"])
def register_folder():
    """
    前端在使用者選的資料夾寫入一個 .sec_marker_<id> 檔案後，
    呼叫這個端點。伺服器搜尋該標記檔案，找到後取得完整路徑並快取，
    以便之後的 open-folder 呼叫使用。
    """
    data      = request.json or {}
    marker_id = data.get("marker_id", "")
    if not marker_id:
        return jsonify({"error": "marker_id required"}), 400

    marker_name = f".sec_marker_{marker_id}"

    def search_for_marker():
        """在常用位置搜尋標記檔案。"""
        home = Path.home()
        search_roots = [
            home / "Desktop",
            home / "Downloads",
            home / "Documents",
            home,
        ]
        # Windows：加入所有磁碟根目錄
        if sys.platform == "win32":
            import string
            for drive in string.ascii_uppercase:
                p = Path(f"{drive}:\\")
                if p.exists() and p not in search_roots:
                    search_roots.append(p)

        for root in search_roots:
            if not root.exists():
                continue
            # 搜尋最多 4 層深度
            for depth in range(5):
                pattern = "/".join(["*"] * depth) + ("/" if depth else "") + marker_name
                for match in root.glob(pattern):
                    return match.parent  # 回傳包含標記檔案的資料夾
        return None

    found = search_for_marker()
    if found:
        _folder_cache[marker_id] = str(found)
        # 刪除標記檔案
        try:
            (found / marker_name).unlink()
        except Exception:
            pass
        return jsonify({"ok": True, "path": str(found)})
    else:
        return jsonify({"error": "Marker file not found"}), 404


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    """用快取的完整路徑在 OS 中開啟資料夾。"""
    data        = request.json or {}
    marker_id   = data.get("marker_id", "")
    folder_path = data.get("folder_path", "")   # 前端直接傳路徑（優先）
    ticker      = data.get("ticker", "")

    # 優先用前端傳來的路徑；若沒有則從快取查
    base_path = folder_path or _folder_cache.get(marker_id, "")
    if not base_path:
        return jsonify({"error": "Folder path not found. Please re-select the folder."}), 404

    # 基本安全檢查：路徑必須是絕對路徑
    p = Path(base_path)
    if not p.is_absolute():
        return jsonify({"error": "Invalid folder path."}), 400

    target = Path(base_path) / ticker if ticker else Path(base_path)
    target.mkdir(parents=True, exist_ok=True)

    try:
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
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
        cik         = _client.get_cik(ticker)
        name        = _client.get_company_name(cik)
        years       = _client.get_available_years(cik)
        all_filings = _client.get_filings(cik)
        fye_month   = infer_fiscal_year_end_month(all_filings)

        filings_data = [
            {
                "accession_number": f.accession_number,
                "form_type":        f.form_type,
                "filing_date":      f.filing_date,
                "report_date":      f.report_date,
                "primary_document": f.primary_document,
                "cik":              f.cik,
                "filename":         resolve_filename(f, fye_month).replace(".md", ".pdf"),
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


@app.route("/api/get-filing", methods=["POST"])
def get_filing():
    """
    下載單一 filing、轉成 PDF，直接回傳 bytes 給瀏覽器。
    前端收到後用 File System Access API 寫入使用者本機資料夾。
    """
    data      = request.json or {}
    ticker    = data.get("ticker", "")
    fye_month = int(data.get("fye_month", 12))
    f         = data.get("filing", {})

    if not f:
        return jsonify({"error": "filing data required"}), 400

    filing = FilingRecord(
        accession_number = f["accession_number"],
        form_type        = f["form_type"],
        filing_date      = f["filing_date"],
        report_date      = f["report_date"],
        primary_document = f["primary_document"],
        cik              = int(f["cik"]),
    )

    try:
        print(f"[get-filing] Downloading {filing.form_type} {filing.report_date} for {ticker}", flush=True)

        # 1. 從 SEC 下載 HTML
        url  = _client.get_document_url(filing)
        html = _client.download_html(url)

        # 2. 清理 XBRL
        html = _clean_xbrl(html)

        # 3. 準備 PDF 用的 HTML（嵌入圖片等）
        acc_clean = filing.accession_number.replace("-", "")
        base_url  = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{filing.cik}/{acc_clean}/"
        )
        pdf_html = _prepare_html_for_pdf(html, base_url=base_url, session=_client.session)

        # 4. 轉成 PDF bytes
        pdf_bytes = convert_html_to_pdf_bytes(pdf_html)
        if not pdf_bytes:
            return jsonify({"error": "PDF conversion failed"}), 500

        # 5. 回傳 PDF bytes 給瀏覽器
        filename = resolve_filename(filing, fye_month).replace(".md", ".pdf")
        print(f"[get-filing] Returning {len(pdf_bytes)} bytes as {filename}", flush=True)

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Filename": filename,
                "Access-Control-Expose-Headers": "X-Filename",
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"SEC Downloader web app running at http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
