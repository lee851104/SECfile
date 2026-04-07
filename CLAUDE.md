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

# Playwright browser (required for PDF)
py -m playwright install chromium

# Dependencies
pip install -r requirements.txt
```

On Windows use `py`, not `python3`.

## Web App Architecture

### Download Flow (critical to understand)

The server **never saves files to disk** (except a transient temp `.html` file used by Playwright for rendering, which is deleted immediately after). Instead:

1. Frontend calls `POST /api/get-filing` with a single `FilingRecord`
2. Server downloads HTML from SEC → `_clean_xbrl()` → `_prepare_html_for_pdf()` → `convert_html_to_pdf_bytes()` (Playwright)
3. Server returns raw PDF bytes in the HTTP response (`X-Filename` header carries the filename)
4. Frontend writes the bytes directly to the user's local disk using the **File System Access API** (`FileSystemDirectoryHandle.createWritable()`)
5. A `ticker/` subfolder is created automatically inside the user's chosen folder

### Folder Path Resolution (Open Folder button)

Browsers cannot expose full OS paths from `showDirectoryPicker()`. The workaround:

1. On "Open Folder" click (and on Browse), frontend writes a `.sec_marker_<uuid>` file into the selected folder
2. Frontend calls `POST /api/register-folder` with the UUID
3. Server searches `~/Desktop`, `~/Downloads`, `~/Documents`, `~`, and all drive roots (Windows) up to 4 levels deep for the marker file
4. Server caches `uuid → full_path` in `_folder_cache` dict (in-memory, lost on restart) and returns `path` in the response
5. Frontend stores `folderPath` and `markerId` in `localStorage` (survives page refresh)
6. Server calls `os.startfile()` / `open` / `xdg-open` with the resolved path

**Important:** Open Folder re-registers the marker on every click — it does not rely on a previously cached state. This makes it robust against server restarts and failed prior registrations. The `dirHandle` is persisted across page refreshes via **IndexedDB**.

**Render limitation:** `os.startfile()` runs on the server. Open Folder only works when Flask is running locally (localhost), not on Render.

### API Routes

| Route | Method | Purpose |
|---|---|---|
| `/api/search` | GET | Ticker → CIK → filings list + fye_month |
| `/api/autocomplete` | GET | Fuzzy search against POPULAR_TICKERS |
| `/api/get-filing` | POST | Returns single filing as PDF bytes |
| `/api/register-folder` | POST | Finds marker file → caches full path, returns `path` |
| `/api/open-folder` | POST | Opens folder in OS file explorer; accepts `folder_path` directly (preferred) or falls back to `marker_id` cache lookup |

## Core Modules

### `core/edgar_client.py`
- `EdgarClient.get_cik(ticker)` — downloads and caches full `company_tickers.json` (~1.5 MB) on first call; cached in `_ticker_map` for the process lifetime
- `EdgarClient.get_document_url(filing)` — queries the filing's `index.json`; prefers non-iXBRL `.htm` whose `type` matches the form type, falls back to any `.htm`, then to `primary_document`
- `EdgarClient.download_html(url)` — retries up to `MAX_RETRIES` with exponential backoff, 30s timeout
- `EdgarClient.session` — a `requests.Session` with SEC-required `User-Agent` header; must be passed to `_prepare_html_for_pdf()` so image downloads bypass SEC's 403 block on headless browsers
- Rate limiting: 0.15s between requests (`RATE_LIMIT_DELAY` in `utils/constants.py`)

### `core/downloader.py`
Key functions used by `app_web.py`:
- `_clean_xbrl(html)` — removes `display:none` divs (via BeautifulSoup), `<ix:*>` tags, namespace declarations
- `_prepare_html_for_pdf(html, base_url, session)` — strips `<script>`/`<style>`, embeds images as base64 (SEC blocks headless browser image requests with 403, so images must be pre-fetched using the `EdgarClient.session` which has the correct User-Agent), injects `_PDF_CSS`
- `convert_html_to_pdf_bytes(html)` — writes HTML to a temp file, Playwright Chromium renders to PDF, deletes temp file, returns `bytes | None`

The desktop app uses `FilingDownloader.download_batch()` which writes both `.pdf` and `.md` to `output_root/TICKER/FORM_TYPE/` — this is **not** used by the web app.

### `core/filing_resolver.py`
Fiscal year inference: reads 10-K `report_date` months to determine `fye_month` (e.g. Apple=9, NVIDIA=1). This affects how filings are labelled (`2025_Q1`, `2025_FY`, etc.) and how the year filter works in the UI.

`resolve_filename()` returns a `.md` extension by convention — callers in `app_web.py` replace it with `.pdf` via `.replace(".md", ".pdf")`.

## Fiscal Year Label Logic

`resolve_label(filing, fye_month)`:
- 10-K → `{fiscal_year}_FY` where fiscal year = calendar year the FYE falls in
- 10-Q → `{fiscal_year}_Q{1|2|3}` — quarter determined by months-since-fiscal-year-start

Example: NVIDIA FYE=January, report_date=2025-04 → FY2026_Q1 (April is Q1 of the fiscal year starting Feb 2025).

## Deployment (Render)

`render.yaml` configures:
- Build: `pip install -r requirements.txt && python -m playwright install chromium`
- Start: `gunicorn app_web:app`

`PORT` env var is respected. `DOWNLOAD_DIR` env var is no longer used (files go to user's browser).

The `_folder_cache` and `dirHandle` (IndexedDB) are per-session client-side state.

## Key Constants (`utils/constants.py`)

- `POPULAR_TICKERS` — 30-entry list for autocomplete; add entries here to expand search
- `SUPPORTED_FORMS = ["10-K", "10-Q"]`
- `MAX_FILINGS = 40` per form type
- `RATE_LIMIT_DELAY = 0.15` seconds
- `DEFAULT_USER_AGENT` — SEC requires a User-Agent with a contact email; change `research@example.com` if deploying publicly to avoid rate limiting
