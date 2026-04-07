# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Two entry points exist side by side:
- **`app.py`** — Tkinter desktop GUI (local only, writes files directly to disk)
- **`app_web.py`** — Flask web app (Render-deployable, files streamed to user's browser via File System Access API)

The web app is the primary focus. The desktop app is kept as a reference/fallback.

## Running

```bash
# Desktop GUI
py app.py

# Web app (local dev)
py app_web.py        # → http://localhost:5000

# Dependencies
pip install -r requirements.txt
```

On Windows use `py`, not `python3`.

## Web App Architecture

### Download Flow (critical to understand)

The server **never saves files to disk**. Instead:

1. Frontend calls `POST /api/get-filing` with a single `FilingRecord`
2. Server downloads HTML from SEC → `_clean_xbrl()` → `_prepare_html_for_pdf()`
3. Server returns JSON with two formats:
   - `html` — full HTML with embedded images for browser rendering
   - `markdown` — plaintext version
4. Frontend writes both files to user's local disk using **File System Access API**:
   - `.html` file — user opens in browser, presses Ctrl+P to save as PDF (browser's native print-to-PDF)
   - `.md` file — plaintext for searching/editing
5. A `ticker/` subfolder is created automatically inside the user's chosen folder
6. First `.html` file auto-opens in new browser tab with prompt to print

**Why browser print-to-PDF?** Server-side PDF generation (Playwright, WeasyPrint, xhtml2pdf) all require system C libraries or Chromium, which fail on Render free tier. Browser rendering is the only approach that's reliable and dependency-free.

### Folder Path Resolution (Open Folder button — localhost only)

Browsers cannot expose full OS paths from `showDirectoryPicker()`. The workaround:

1. On Browse, frontend writes a `.sec_marker_<uuid>` file into the selected folder
2. Frontend calls `POST /api/register-folder` with the UUID
3. Server searches `~/Desktop`, `~/Downloads`, `~/Documents`, `~`, and all drive roots (Windows) up to 4 levels deep
4. Server caches `uuid → full_path` in `_folder_cache` dict (in-memory) and returns `path`
5. Frontend stores `folderPath` and `markerId` in `localStorage` (survives page refresh)
6. On "Open Folder" click, frontend writes fresh marker and re-registers (robust against server restarts)
7. Server calls `os.startfile()` / `open` / `xdg-open`

**Render limitation:** Open Folder button is hidden on Render (detected via `window.location.hostname`). Works only on localhost because `os.startfile()` runs on server and cannot access user's local paths.

### API Routes

| Route | Method | Purpose |
|---|---|---|
| `/api/search` | GET | Ticker → CIK → filings list + fye_month |
| `/api/autocomplete` | GET | Fuzzy search against POPULAR_TICKERS |
| `/api/get-filing` | POST | Returns JSON with `html` (for print) + `markdown` (plaintext) + filenames |
| `/api/register-folder` | POST | Finds marker file → caches full path, returns `path` |
| `/api/open-folder` | POST | Opens folder in OS file explorer (localhost only) |

## Core Modules

### `core/edgar_client.py`
- `EdgarClient.get_cik(ticker)` — downloads and caches full `company_tickers.json` (~1.5 MB) on first call
- `EdgarClient.get_document_url(filing)` — queries filing's `index.json`; prefers non-iXBRL `.htm`
- `EdgarClient.download_html(url)` — retries up to `MAX_RETRIES` with exponential backoff, 30s timeout
- `EdgarClient.session` — `requests.Session` with SEC-required User-Agent header; passed to image embedding so SEC doesn't block 403
- Rate limiting: 0.15s between requests

### `core/downloader.py`
- `_clean_xbrl(html)` — removes `display:none` divs, `<ix:*>` tags, XML namespaces
- `_prepare_html_for_pdf(html, base_url, session)` — strips `<script>`/`<style>`, embeds images as base64 (SEC blocks headless browser requests), injects `_PDF_CSS`
- `_html_to_markdown(html)` — converts to plaintext (used for `.md` file)
- Desktop app's `FilingDownloader.download_batch()` writes `.pdf` + `.md` to disk — not used by web app

### `core/filing_resolver.py`
- `infer_fiscal_year_end_month(filings)` — reads 10-K report_date months to infer fiscal year end
- `resolve_label(filing, fye_month)` — returns label like `2025_FY` or `2025_Q1`
- `resolve_filename(filing, fye_month)` — returns filename; callers change `.md` to `.html` as needed

## Fiscal Year Label Logic

`resolve_label(filing, fye_month)`:
- 10-K → `{fiscal_year}_FY` where fiscal year = calendar year FYE falls in
- 10-Q → `{fiscal_year}_Q{1|2|3}` — quarter determined by months-since-fiscal-year-start

Example: NVIDIA FYE=January, report_date=2025-04 → FY2026_Q1.

## Deployment (Render)

`render.yaml`:
- Python 3.11.9 (pinned via `.python-version`)
- Build: `pip install -r requirements.txt` (no system dependencies needed)
- Start: `gunicorn app_web:app`
- `PORT` env var respected; `DOWNLOAD_DIR` unused (files go to browser)

Open Folder feature disabled on Render (auto-detected via hostname check).

## Key Constants (`utils/constants.py`)

- `POPULAR_TICKERS` — 30-entry list for autocomplete
- `SUPPORTED_FORMS = ["10-K", "10-Q"]`
- `MAX_FILINGS = 40` per form type
- `RATE_LIMIT_DELAY = 0.15` seconds
- `DEFAULT_USER_AGENT` — update email if deploying publicly
