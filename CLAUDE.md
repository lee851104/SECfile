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
6. After download completes, the frontend lists all downloaded `.html` files as clickable links (opens via `createObjectURL` with explicit `charset=utf-8` to avoid garbled text)

**Why browser print-to-PDF?** Server-side PDF generation (Playwright, WeasyPrint, xhtml2pdf) all require system C libraries or Chromium, which fail on Render free tier. Browser rendering is the only approach that's reliable and dependency-free.

### File System Access API (frontend)

`dirHandle` — `FileSystemDirectoryHandle` pointing to the user's chosen folder. Persisted in **IndexedDB** so it survives page refresh. Key operations:

- `dirHandle.getDirectoryHandle(ticker, { create: true })` — creates ticker subfolder
- `handle.createWritable()` → write Blob → `close()` — writes file to disk
- When opening saved HTML for display: read via `file.text()` and re-wrap as `new Blob([text], { type: 'text/html; charset=utf-8' })` before `createObjectURL` — this is required to prevent garbled characters
- Marker files (`.sec_marker_<uuid>`) are written to the parent folder then cleaned up after download

### Marker File / Open Folder Flow (localhost only)

Browsers cannot expose full OS paths from `showDirectoryPicker()`. The workaround (used only on localhost for `os.startfile()`):

1. Frontend writes `.sec_marker_<uuid>` into the selected folder
2. Frontend calls `POST /api/register-folder` with the UUID
3. Server searches common locations up to 4 levels deep, caches `uuid → full_path`
4. Server calls `os.startfile()` / `open` / `xdg-open`

This feature is **not available on Render** — the Open Folder button was removed; instead, downloaded files are listed as clickable links in the UI.

### API Routes

| Route | Method | Purpose |
|---|---|---|
| `/api/search` | GET | Ticker → CIK → filings list + fye_month |
| `/api/autocomplete` | GET | Fuzzy search against POPULAR_TICKERS |
| `/api/get-filing` | POST | Returns JSON with `html` + `markdown` + filenames |
| `/api/register-folder` | POST | Finds marker file → caches full path (localhost only) |
| `/api/open-folder` | POST | Opens folder in OS file explorer (localhost only) |

## Core Modules

### `core/edgar_client.py`
- `EdgarClient.get_cik(ticker)` — downloads and caches full `company_tickers.json` (~1.5 MB) on first call
- `EdgarClient.get_document_url(filing)` — queries filing's `index.json`; prefers non-iXBRL `.htm`
- `EdgarClient.download_html(url)` — retries up to `MAX_RETRIES` with exponential backoff, 30s timeout. Encoding detection order: HTML `<meta charset>` tag → `apparent_encoding` → `utf-8`
- `EdgarClient.session` — `requests.Session` with SEC-required User-Agent header
- Rate limiting: 0.15s between requests

### `core/downloader.py`
- `_clean_xbrl(html)` — removes `display:none` divs, `<ix:*>` tags, XML namespaces
- `_prepare_html_for_pdf(html, base_url, session)` — strips `<script>`/`<style>`, embeds images as base64, injects `_PDF_CSS`
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

Render URL: https://secfile.onrender.com

## Key Constants (`utils/constants.py`)

- `POPULAR_TICKERS` — 30-entry list for autocomplete
- `SUPPORTED_FORMS = ["10-K", "10-Q"]`
- `MAX_FILINGS = 40` per form type
- `RATE_LIMIT_DELAY = 0.15` seconds
- `DEFAULT_USER_AGENT` — update email if deploying publicly
