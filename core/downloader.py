"""
下載器
負責：下載 HTML → 嘗試轉 PDF（WeasyPrint），失敗時 fallback 儲存 .htm
"""

import os
import re
from pathlib import Path
from typing import Callable, Optional

from core.edgar_client import EdgarClient, FilingRecord
from core.filing_resolver import infer_fiscal_year_end_month, resolve_filename
from utils.constants import DEFAULT_DOWNLOAD_DIR, SEC_ARCHIVES_URL


def _check_weasyprint() -> bool:
    """檢查 WeasyPrint 是否可用（需要 GTK runtime）。"""
    try:
        import weasyprint  # noqa: F401
        weasyprint.HTML(string="<p>ok</p>").write_pdf()
        return True
    except Exception:
        return False


WEASYPRINT_AVAILABLE: Optional[bool] = None   # 首次呼叫時初始化


def _html_to_pdf(html: str, output_path: Path, base_url: str) -> bool:
    """
    Convert HTML to PDF using available methods.
    Returns True=success, False=fallback to .htm needed.
    Try: pdfkit -> reportlab -> WeasyPrint
    """
    # Try pdfkit (uses wkhtmltopdf)
    try:
        import pdfkit
        pdfkit.from_string(html, str(output_path), options={'quiet': ''})
        return True
    except Exception:
        pass

    # Try reportlab (pure Python, no external deps)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from io import BytesIO
        # Simple fallback: create a minimal PDF with text content
        c = canvas.Canvas(str(output_path), pagesize=letter)
        # Extract text from HTML
        import re
        text_content = re.sub(r'<[^>]+>', '', html)
        text_lines = text_content.split('\n')
        y = 750
        for line in text_lines[:100]:  # Limit to first 100 lines
            if line.strip():
                c.drawString(50, y, line[:80])
                y -= 15
                if y < 50:
                    break
        c.save()
        return True
    except Exception:
        pass

    # Try WeasyPrint
    global WEASYPRINT_AVAILABLE
    if WEASYPRINT_AVAILABLE is None:
        WEASYPRINT_AVAILABLE = _check_weasyprint()
    if WEASYPRINT_AVAILABLE:
        try:
            import weasyprint
            weasyprint.HTML(string=html, base_url=base_url).write_pdf(str(output_path))
            return True
        except Exception:
            pass

    return False


def _clean_xbrl(html: str) -> str:
    """
    移除 inline XBRL <ix:*> 標籤（保留文字內容），避免 PDF 轉換問題。
    使用正則表達式（避免強依賴 lxml/bs4）。
    """
    # 移除 ix: 開頭的 XML namespace 標籤，保留內容
    html = re.sub(r'<ix:[^>]+>', '', html)
    html = re.sub(r'</ix:[^>]+>', '', html)
    # 移除 XBRL namespace 宣告
    html = re.sub(r'\s+xmlns:ix="[^"]*"', '', html)
    return html


def _html_to_markdown(html: str) -> str:
    """將 HTML 轉換為 Markdown，優先使用 html2text 套件。"""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links      = False
        h.ignore_images     = True
        h.body_width        = 0          # 不自動換行
        h.single_line_break = True
        return h.handle(html)
    except ImportError:
        pass

    # Fallback：基本 regex 轉換
    md = html
    md = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<br\s*/?>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<p[^>]*>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'</p>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<tr[^>]*>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<td[^>]*>|<th[^>]*>', ' | ', md, flags=re.IGNORECASE)
    md = re.sub(r'<[^>]+>', '', md)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


class FilingDownloader:
    def __init__(
        self,
        client:       EdgarClient,
        output_root:  Path = Path(DEFAULT_DOWNLOAD_DIR),
        on_log:       Callable[[str, str], None] = None,   # (message, level)
        on_progress:  Callable[[int, int], None] = None,   # (done, total)
    ):
        self.client      = client
        self.output_root = output_root
        self.on_log      = on_log or (lambda msg, lvl: print(msg))
        self.on_progress = on_progress or (lambda d, t: None)

    def download_batch(
        self,
        ticker:      str,
        filings:     list[FilingRecord],
        fye_month:   int,
    ) -> list[tuple[FilingRecord, Path, bool]]:
        """
        批次下載一組 FilingRecord。
        回傳 [(filing, saved_path, success), ...]
        """
        results = []
        total   = len(filings)

        for idx, filing in enumerate(filings):
            self.on_progress(idx, total)
            try:
                path, ok = self._download_one(ticker, filing, fye_month)
                results.append((filing, path, ok))
                self.on_log(f"✓ {path.name}", "success")
            except Exception as e:
                self.on_log(f"✗ {filing.form_type} {filing.report_date}: {e}", "error")
                results.append((filing, Path(), False))

        self.on_progress(total, total)
        return results

    def _download_one(
        self, ticker: str, filing: FilingRecord, fye_month: int
    ) -> tuple[Path, bool]:
        """下載單一 Filing，回傳 (儲存路徑, 是否為HTM)。"""
        # 建立資料夾 downloads/AAPL/10-K/
        folder = self.output_root / ticker.upper() / filing.form_type
        folder.mkdir(parents=True, exist_ok=True)

        filename = resolve_filename(filing, fye_month)   # e.g. "2024_FY.md"
        md_path  = folder / filename

        # 若已存在則跳過
        if md_path.exists():
            self.on_log(f"⊙ 已存在，跳過: {md_path.name}", "info")
            return md_path, True

        # 取得文件 URL 並下載 HTML，轉為 Markdown
        url  = self.client.get_document_url(filing)
        html = self.client.download_html(url)
        html = _clean_xbrl(html)

        md = _html_to_markdown(html)
        md_path.write_text(md, encoding="utf-8")
        return md_path, True
