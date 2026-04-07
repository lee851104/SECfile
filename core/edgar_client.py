"""
SEC EDGAR REST API 客戶端
負責：Ticker→CIK 查詢、取得 Filing 清單、建構文件 URL
"""

import time
import requests
from dataclasses import dataclass
from typing import Optional

from utils.constants import (
    SEC_SUBMISSIONS_URL, SEC_TICKERS_URL, SEC_ARCHIVES_URL,
    DEFAULT_USER_AGENT, RATE_LIMIT_DELAY, REQUEST_TIMEOUT,
    MAX_RETRIES, SUPPORTED_FORMS, MAX_FILINGS, POPULAR_TICKERS
)


@dataclass
class FilingRecord:
    accession_number: str   # "0000320193-24-000123"
    form_type:        str   # "10-K" or "10-Q"
    filing_date:      str   # "2024-11-01"
    report_date:      str   # "2024-09-28"  ← period of report
    primary_document: str   # "aapl-20240928.htm"
    cik:              int


def fuzzy_search(query: str) -> list[dict]:
    """
    從 POPULAR_TICKERS 做本地模糊搜尋（不分大小寫）。
    同時比對 ticker 和公司名稱。
    回傳最多 8 筆，格式: [{"ticker": ..., "name": ..., "sector": ...}]
    """
    q = query.strip().upper()
    if not q:
        return []

    results = []
    for item in POPULAR_TICKERS:
        ticker_match = q in item["ticker"].upper()
        name_match   = q.lower() in item["name"].lower()
        if ticker_match or name_match:
            results.append(item)

    # ticker 完全匹配優先排序
    results.sort(key=lambda x: (
        0 if x["ticker"].upper() == q else
        1 if x["ticker"].upper().startswith(q) else 2
    ))
    return results[:8]


class EdgarClient:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept":     "application/json",
        })
        self._ticker_map: Optional[dict] = None   # 快取 company_tickers.json

    # ── 公開方法 ──────────────────────────────────────────

    def get_cik(self, ticker: str) -> int:
        """
        從 SEC company_tickers.json 查詢 CIK。
        首次呼叫下載並快取全份 JSON（約 1.5 MB）。
        回傳整數 CIK。
        """
        if self._ticker_map is None:
            self._load_ticker_map()

        t = ticker.upper().strip()
        if t not in self._ticker_map:
            raise ValueError(f"找不到股票代碼 '{ticker}'，請確認代碼是否正確。")
        return self._ticker_map[t]

    def get_company_name(self, cik: int) -> str:
        """取得公司名稱"""
        data = self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        return data.get("name", "")

    def get_available_years(self, cik: int, form_types: list[str] = None) -> list[int]:
        """
        回傳該公司在 EDGAR 上有哪些年份的 filings（降序）。
        用於填充年份下拉選單。
        """
        if form_types is None:
            form_types = SUPPORTED_FORMS
        filings = self._fetch_filings(cik, form_types)
        years = sorted({int(f.report_date[:4]) for f in filings}, reverse=True)
        return years

    def get_filings(
        self,
        cik:        int,
        form_types: list[str] = None,
        year:       Optional[int] = None,
    ) -> list[FilingRecord]:
        """
        取得 Filing 清單，可選擇依年份篩選。
        回傳依 filing_date 降序排列的 FilingRecord list。
        """
        if form_types is None:
            form_types = SUPPORTED_FORMS
        filings = self._fetch_filings(cik, form_types)

        if year is not None:
            filings = [f for f in filings if f.report_date.startswith(str(year))]

        return filings

    def get_document_url(self, filing: FilingRecord) -> str:
        """
        建構並回傳主文件（.htm）的完整下載 URL。
        """
        acc_clean = filing.accession_number.replace("-", "")
        # 優先使用已知的 primary_document
        if filing.primary_document:
            return (
                f"{SEC_ARCHIVES_URL}/{filing.cik}"
                f"/{acc_clean}/{filing.primary_document}"
            )
        # 否則查 index JSON
        index_url = (
            f"{SEC_ARCHIVES_URL}/{filing.cik}"
            f"/{acc_clean}/{filing.accession_number}-index.json"
        )
        index_data = self._get_json(index_url)
        docs = index_data.get("documents", [])
        for doc in docs:
            if doc.get("type", "") in (filing.form_type, ""):
                return (
                    f"{SEC_ARCHIVES_URL}/{filing.cik}"
                    f"/{acc_clean}/{doc['filename']}"
                )
        raise ValueError(f"找不到 {filing.accession_number} 的主文件")

    def download_html(self, url: str) -> str:
        """下載 HTML 內容並回傳字串。"""
        for attempt in range(MAX_RETRIES):
            try:
                time.sleep(RATE_LIMIT_DELAY)
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            except requests.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(1.5 ** attempt)
        return ""

    # ── 私有方法 ──────────────────────────────────────────

    def _load_ticker_map(self):
        """下載並快取 Ticker→CIK 對應表。"""
        data = self._get_json(SEC_TICKERS_URL)
        # 格式: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
        self._ticker_map = {
            v["ticker"].upper(): int(v["cik_str"])
            for v in data.values()
        }

    def _fetch_filings(self, cik: int, form_types: list[str]) -> list[FilingRecord]:
        """從 submissions API 取得並解析 Filing 清單（含分頁）。"""
        data     = self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        recent   = data.get("filings", {}).get("recent", {})
        records  = self._parse_recent(recent, cik, form_types)

        # 處理歷史分頁（filings.files）
        for file_entry in data.get("filings", {}).get("files", []):
            if len(records) >= MAX_FILINGS:
                break
            sub_url  = f"https://data.sec.gov/submissions/{file_entry['name']}"
            sub_data = self._get_json(sub_url)
            records += self._parse_recent(sub_data, cik, form_types)

        # 降序排序
        records.sort(key=lambda r: r.filing_date, reverse=True)
        return records[:MAX_FILINGS]

    def _parse_recent(
        self, recent: dict, cik: int, form_types: list[str]
    ) -> list[FilingRecord]:
        """將 filings.recent 平行陣列解析成 FilingRecord list。"""
        records = []
        forms    = recent.get("form",            [])
        acc_nums = recent.get("accessionNumber", [])
        f_dates  = recent.get("filingDate",      [])
        r_dates  = recent.get("reportDate",      [])
        primary  = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form not in form_types:
                continue
            records.append(FilingRecord(
                accession_number = acc_nums[i] if i < len(acc_nums) else "",
                form_type        = form,
                filing_date      = f_dates[i]  if i < len(f_dates)  else "",
                report_date      = r_dates[i]  if i < len(r_dates)  else "",
                primary_document = primary[i]  if i < len(primary)  else "",
                cik              = cik,
            ))
        return records

    def _get_json(self, url: str) -> dict:
        """帶重試的 JSON GET 請求。"""
        for attempt in range(MAX_RETRIES):
            try:
                time.sleep(RATE_LIMIT_DELAY)
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(1.5 ** attempt)
        return {}
