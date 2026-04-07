# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

SEC EDGAR Downloader is a Tkinter-based GUI application for downloading SEC financial filings (10-K and 10-Q forms) from the SEC EDGAR database. The application converts iXBRL HTML filings to Markdown for easy reading.

## Architecture

### Core Components

1. **`app.py`** — Main Tkinter GUI application
   - Left sidebar: ticker search, year/form filters, download folder picker
   - Right main area: download queue with file list and progress tracking
   - Threading for non-blocking search and download operations

2. **`core/edgar_client.py`** — SEC EDGAR API client
   - `EdgarClient` class: handles ticker→CIK lookup, filing queries, document URL resolution
   - `FilingRecord` dataclass: represents a single filing with accession number, form type, dates, etc.
   - `fuzzy_search()`: local search against `POPULAR_TICKERS` constant
   - Rate limiting (0.15s delay) to respect SEC's 10 req/s limit
   - Retry logic with exponential backoff

3. **`core/filing_resolver.py`** — Fiscal year inference and file naming
   - `infer_fiscal_year_end_month()`: infers company's fiscal year end from 10-K dates (e.g., NVDA = 1, AAPL = 9)
   - `resolve_label()`: converts FilingRecord → human-readable label (e.g., "2024_FY", "2026_Q1")
   - `resolve_filename()`: returns filename with `.md` extension
   - Internal helpers: `_fiscal_year_of()`, `_fiscal_quarter_of()` handle fiscal year math

4. **`core/downloader.py`** — Filing download and format conversion
   - `FilingDownloader.download_batch()`: batch download with progress callbacks
   - `_clean_xbrl()`: removes hidden XBRL `<div style="display:none">` blocks and `<ix:*>` namespace elements
   - `_prepare_html_for_pdf(html, base_url, session)`: strips scripts/styles, embeds images as base64 (using edgar client session to bypass SEC 403), injects clean CSS
   - `_convert_html_to_pdf(html, path)`: renders HTML to PDF via Playwright (Chromium)
   - `_html_to_markdown()`: converts cleaned HTML → Markdown with `ignore_tables=True` (no `---|---` artifacts)
   - Each filing outputs two files: `2024_FY.pdf` (readable) + `2024_FY.md` (plain text)
   - Downloaded files stored in `downloads/TICKER/FORM_TYPE/` directory

5. **`utils/constants.py`** — Global configuration
   - SEC EDGAR API endpoints and rate limiting
   - HTTP defaults (timeout, retries, user agent)
   - `POPULAR_TICKERS`: 30-ticker database for autocomplete

## Key Design Decisions

### Fiscal Year Handling

Different companies have different fiscal year ends (Apple: Sept, NVIDIA: Jan). The app infers this from 10-K filing dates and uses it to:
- Label filings correctly (e.g., NVIDIA's Q1 FY2026 has report_date in April 2025)
- Filter by fiscal year in the UI (not calendar year)

### iXBRL Cleaning

SEC filings use inline XBRL (iXBRL) for structured data. The HTML contains:
- `<div style="display:none">` blocks with XBRL unit/context definitions (biggest source of gibberish)
- `<ix:hidden>` blocks with raw XBRL values
- `<xbrli:*>`, `<link:*>` namespace tags and `xmlns:*` declarations

`_clean_xbrl()` removes all of these before conversion, preserving only visible business content.

### HTML → PDF Conversion (primary output)

- Uses **Playwright (Chromium)** to render cleaned HTML directly to PDF
- Images (company logos etc.) are downloaded via `EdgarClient.session` and embedded as base64 — necessary because SEC returns 403 to headless browser requests
- Original SEC inline `style=""` attributes are preserved (they carry table border info)
- External `<style>` blocks are stripped and replaced with a minimal clean CSS
- Output: `downloads/TICKER/FORM_TYPE/2024_FY.pdf`

### HTML → Markdown Conversion (secondary output)

- Uses `html2text` with `ignore_tables=True` to avoid `---|---` table artifacts
- Useful for text search or LLM ingestion
- Output: `downloads/TICKER/FORM_TYPE/2024_FY.md`

## Running the Application

```bash
py app.py
```

(On Windows, use `py` not `python3`)

## Dependencies

Install via:
```bash
pip install -r requirements.txt
pip install html2text  # for best Markdown conversion quality
```

Core requirements:
- `requests` — SEC EDGAR API calls
- `html2text` — HTML→Markdown conversion
- `playwright` — Chromium-based HTML→PDF rendering (run `py -m playwright install chromium` after pip install)
- `beautifulsoup4` + `lxml` — HTML parsing utilities
- `Pillow` — Image support

## Common Tasks

### Add a new ticker to autocomplete
Edit `POPULAR_TICKERS` in `utils/constants.py`.

### Adjust SEC rate limiting
Change `RATE_LIMIT_DELAY` in `utils/constants.py` (current: 0.15s = ~6.7 req/s, safe for 10 req/s limit).

### Change filing types
Modify `SUPPORTED_FORMS` in `utils/constants.py` or add CLI args to `EdgarClient.get_filings()`.

### Debug a filing download
Check:
1. `EdgarClient.get_document_url()` — returns correct document URL
2. `_clean_xbrl()` — validates XBRL removal
3. `_html_to_markdown()` — check Markdown output quality

## Testing Notes

- No automated tests yet; manual testing via GUI
- SEC EDGAR APIs are live; use cautiously to avoid rate limit bans
- Test ticker: AAPL (widely available filings)
- Test ticker: NVDA (non-calendar fiscal year)

## Recent Changes

- **Apr 7**: Switched to Playwright-based HTML→PDF rendering
  - Each download now produces both `.pdf` (readable) and `.md` (plain text)
  - PDF uses Playwright/Chromium to render HTML directly — preserves tables, headings, logos
  - Images embedded as base64 (SEC blocks headless browser image requests with 403)
  - XBRL cleaning improved: removes hidden `<div style="display:none">` blocks (was the main source of gibberish)
  - `edgar_client.get_document_url()` now checks filing index for best .htm file
  - Removed: WeasyPrint, reportlab, markdown-pdf (all had Windows compatibility issues)
