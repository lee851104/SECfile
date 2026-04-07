"""
Filing 命名邏輯
根據 report_date 與公司財年結束月份，推算出 2024_FY / 2024_Q1 ... 等標籤
"""

from datetime import date
from core.edgar_client import FilingRecord


def infer_fiscal_year_end_month(filings: list[FilingRecord]) -> int:
    """
    從所有 10-K filings 的 report_date 月份推算財年結束月份。
    例如 Apple 的 10-K 多為 9 月底 → 回傳 9。
    若無 10-K 資料，預設回傳 12（曆年制）。
    """
    annual_months = []
    for f in filings:
        if f.form_type == "10-K" and f.report_date:
            try:
                month = int(f.report_date[5:7])
                annual_months.append(month)
            except (ValueError, IndexError):
                pass
    if not annual_months:
        return 12
    # 取眾數
    return max(set(annual_months), key=annual_months.count)


def resolve_label(filing: FilingRecord, fye_month: int) -> str:
    """
    回傳如 "2024_FY"、"2024_Q1" 的標籤字串。

    邏輯：
    - 10-K → 直接用 report_date 年份（fiscal year）
    - 10-Q → 計算該 report_date 在財年中屬於第幾季
    """
    if not filing.report_date:
        return filing.filing_date[:4] + ("_FY" if filing.form_type == "10-K" else "_Q?")

    try:
        rd = date.fromisoformat(filing.report_date)
    except ValueError:
        return filing.report_date[:4] + "_??"

    if filing.form_type == "10-K":
        # 財年年份 = 財年結束的日曆年
        fy = _fiscal_year_of(rd, fye_month)
        return f"{fy}_FY"
    else:
        # 10-Q
        fy, q = _fiscal_quarter_of(rd, fye_month)
        return f"{fy}_Q{q}"


def resolve_filename(filing: FilingRecord, fye_month: int) -> str:
    """回傳完整檔名，例如 '2024_FY.md'"""
    return resolve_label(filing, fye_month) + ".md"


# ── 內部輔助 ──────────────────────────────────────────────

def _fiscal_year_of(rd: date, fye_month: int) -> int:
    """
    判斷 rd 屬於哪個財年（以財年結束年份為標籤）。
    例如 fye=9，rd=2023-12 → 屬於 FY2024（財年 2023-10 ~ 2024-09）
    """
    if rd.month <= fye_month:
        # 在財年的後段（月份未超過 FYE）→ 同年財年
        return rd.year
    else:
        # 月份超過 FYE，屬於下一財年
        return rd.year + 1


def _fiscal_quarter_of(rd: date, fye_month: int) -> tuple[int, int]:
    """
    回傳 (fiscal_year, quarter_number)。
    財年從 FYE 後一個月開始，例如 FYE=9 → 財年從 10 月開始：
        10-12月 → Q1, 1-3月 → Q2, 4-6月 → Q3, 7-9月 → Q4(=10-K不出現)
    """
    fy = _fiscal_year_of(rd, fye_month)

    # 計算 rd.month 在財年中是第幾個月（1-indexed）
    fy_start_month = (fye_month % 12) + 1   # FYE=9 → start=10
    months_into_fy = (rd.month - fy_start_month) % 12 + 1

    quarter = (months_into_fy - 1) // 3 + 1
    quarter = min(quarter, 3)   # 10-Q 最多到 Q3

    return fy, quarter
