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
   - `_clean_xbrl()`: removes XBRL metadata, scripts, styles, and `<ix:*>` namespace elements
   - `_html_to_markdown()`: converts cleaned HTML → Markdown (uses `html2text` library with regex fallback)
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
- `<ix:hidden>` blocks with raw XBRL values (us-gaap:*, iso4217:USD, etc.)
- Namespace declarations (`xmlns:xbrli`, `xmlns:us-gaap`, etc.)
- These create gibberish when converted naively

`_clean_xbrl()` removes these completely before conversion to Markdown.

### HTML → Markdown Conversion

- Primary: `html2text` library (installed via requirements)
- Fallback: regex-based conversion if library unavailable
- Output: readable Markdown in `downloads/TICKER/FORM_TYPE/2024_FY.md`

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
- `reportlab` — PDF utilities (legacy, may be removed)
- `Pillow` — Image support (legacy)
- `html2text` — iXBRL→Markdown conversion

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

- **Apr 7**: Switched from PDF/HTM output to `.md` Markdown format
  - Removed WeasyPrint/reportlab PDF conversion complexity
  - Now uses `html2text` for clean, readable output
