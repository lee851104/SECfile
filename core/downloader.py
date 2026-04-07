"""
下載器
流程：HTML 下載 → XBRL 清理 → 同時輸出 .md（文字）和 .pdf（直接渲染）
"""

import re
from pathlib import Path
from typing import Callable

from core.edgar_client import EdgarClient, FilingRecord
from core.filing_resolver import resolve_filename
from utils.constants import DEFAULT_DOWNLOAD_DIR

# 注入 PDF 的簡潔 CSS（只補基本排版，邊框讓 SEC inline style 自己控制）
_PDF_CSS = """
<style>
    @page { margin: 2cm 2.5cm; }
    body {
        font-family: Arial, Helvetica, sans-serif;
        font-size: 9pt;
        line-height: 1.5;
        color: #000;
    }
    h1 { font-size: 13pt; font-weight: bold; text-align: center; margin: 10pt 0 6pt 0; }
    h2 { font-size: 11pt; font-weight: bold; margin: 8pt 0 4pt 0; }
    h3 { font-size: 10pt; font-weight: bold; margin: 6pt 0 3pt 0; }
    h4, h5, h6 { font-size: 9pt; font-weight: bold; margin: 4pt 0 2pt 0; }
    p  { margin: 3pt 0; }
    /* 不主動加邊框：SEC inline style 已有正確的 border 資訊 */
    td, th { padding: 2pt 5pt; vertical-align: top; }
    b, strong { font-weight: bold; }
    i, em { font-style: italic; }
    hr { border: none; border-top: 1px solid #999; margin: 6pt 0; }
    .center, [align="center"] { text-align: center; }
    [align="right"] { text-align: right; }
    img { max-width: 100%; height: auto; }
</style>
"""


def _clean_xbrl(html: str) -> str:
    """
    移除 inline XBRL 標籤和隱藏的 XBRL 定義區塊。
    保留可見的業務文字內容。
    """
    # 1. 移除 <div style="display:none">...</div>（XBRL 定義區塊）
    html = re.sub(
        r'<div\s+style="display\s*:\s*none"[^>]*>.*?</div>',
        '', html, flags=re.DOTALL | re.IGNORECASE
    )
    # 2. 移除 <ix:hidden>
    html = re.sub(r'<ix:hidden[^>]*>.*?</ix:hidden>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 3. 移除 XBRL 命名空間標籤（xbrli:*, link:*, 等）
    html = re.sub(r'<(/?)(?:xbrli|link|ixt|xlink):[^>]*>', '', html, flags=re.IGNORECASE)
    # 4. 移除 <ix:*> 標籤，保留文字內容
    html = re.sub(r'<(/?)ix:[^>]*>', '', html, flags=re.IGNORECASE)
    # 5. 移除 XBRL 屬性
    html = re.sub(r'\s+(?:contextref|unitref|escape|format|xlink:\w+)="[^"]*"', '', html, flags=re.IGNORECASE)
    # 6. 移除 namespace 宣告
    html = re.sub(r'\s+xmlns(?::[^=\s]*)?\s*=\s*"[^"]*"', '', html, flags=re.IGNORECASE)
    return html


def _prepare_html_for_pdf(html: str, base_url: str = None, session=None) -> str:
    """
    為 Playwright 準備 HTML：
    - 用 session 下載圖片並嵌入 base64（避免 Playwright 被 SEC 伺服器擋住）
    - 移除原始 <script> 和 <style>（避免干擾，保留 inline style）
    - 注入簡潔的閱讀 CSS
    """
    # Logo 修復：用 edgar client 的 session（有正確 User-Agent）下載圖片並 base64 嵌入
    if base_url and session:
        import base64, time

        def _embed_image(m):
            src = m.group(1)
            if src.startswith('data:'):
                return m.group(0)
            full_url = src if src.startswith('http') else base_url + src
            try:
                time.sleep(0.15)
                resp  = session.get(full_url, timeout=10)
                ctype = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0]
                b64   = base64.b64encode(resp.content).decode()
                return f'src="data:{ctype};base64,{b64}"'
            except Exception:
                return m.group(0)

        html = re.sub(r'src="([^"]*\.(?:jpg|jpeg|png|gif|svg)[^"]*)"',
                      _embed_image, html, flags=re.IGNORECASE)

    # 移除 script
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 移除原始外部 style（保留 inline style=""，那裡有表格邊框資訊）
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<link[^>]+stylesheet[^>]*/?\s*>', '', html, flags=re.IGNORECASE)

    # 注入 CSS
    if re.search(r'<head[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<head[^>]*>)', r'\1' + _PDF_CSS, html, count=1, flags=re.IGNORECASE)
    elif re.search(r'</head>', html, re.IGNORECASE):
        html = re.sub(r'</head>', _PDF_CSS + '</head>', html, count=1, flags=re.IGNORECASE)
    else:
        html = f"<html><head>{_PDF_CSS}</head><body>{html}</body></html>"

    return html


def _html_to_markdown(html: str) -> str:
    """將 HTML 轉換為純文字 Markdown（忽略表格格式，輸出平坦文字）。"""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links      = False
        h.ignore_images     = True
        h.ignore_tables     = True   # 不產生 ---|--- 符號
        h.body_width        = 0
        h.single_line_break = True
        md = h.handle(html)
    except ImportError:
        md = re.sub(r'<[^>]+>', ' ', html)

    md = re.sub(r'\n{3,}', '\n\n', md)
    md = re.sub(r'[ \t]{2,}', ' ', md)
    return md.strip()


def _convert_html_to_pdf(html: str, output_path: Path) -> bool:
    """
    用 Playwright（Chromium）將清理後的 HTML 渲染為 PDF。
    表格、粗體、標題均保留原始 HTML 結構，品質接近瀏覽器列印效果。
    """
    import tempfile, os
    tmp = None
    try:
        from playwright.sync_api import sync_playwright

        # 將 HTML 寫入暫存檔
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', encoding='utf-8', delete=False
        ) as f:
            f.write(html)
            tmp = f.name

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(f"file:///{tmp.replace(os.sep, '/')}")
            page.wait_for_load_state("networkidle", timeout=15000)
            page.pdf(
                path          = str(output_path),
                format        = "A4",
                margin        = {"top": "2cm", "bottom": "2cm",
                                 "left": "2.5cm", "right": "2.5cm"},
                print_background = True,
            )
            browser.close()
        return True
    except Exception:
        return False
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


class FilingDownloader:
    def __init__(
        self,
        client:      EdgarClient,
        output_root: Path = Path(DEFAULT_DOWNLOAD_DIR),
        on_log:      Callable[[str, str], None] = None,
        on_progress: Callable[[int, int], None] = None,
    ):
        self.client      = client
        self.output_root = output_root
        self.on_log      = on_log or (lambda msg, lvl: print(msg))
        self.on_progress = on_progress or (lambda d, t: None)

    def download_batch(
        self,
        ticker:    str,
        filings:   list[FilingRecord],
        fye_month: int,
    ) -> list[tuple[FilingRecord, Path, bool]]:
        results = []
        total   = len(filings)

        for idx, filing in enumerate(filings):
            self.on_progress(idx, total)
            try:
                path, ok = self._download_one(ticker, filing, fye_month)
                results.append((filing, path, ok))
                self.on_log(f"OK {path.name}", "success")
            except Exception as e:
                self.on_log(f"Failed {filing.form_type} {filing.report_date}: {e}", "error")
                results.append((filing, Path(), False))

        self.on_progress(total, total)
        return results

    def _download_one(
        self, ticker: str, filing: FilingRecord, fye_month: int
    ) -> tuple[Path, bool]:
        folder = self.output_root / ticker.upper() / filing.form_type
        folder.mkdir(parents=True, exist_ok=True)

        base_name = resolve_filename(filing, fye_month).replace(".md", "")
        md_path   = folder / f"{base_name}.md"
        pdf_path  = folder / f"{base_name}.pdf"

        if md_path.exists() and pdf_path.exists():
            self.on_log(f"Skip (exists): {base_name}", "info")
            return pdf_path, True

        # 下載並清理 XBRL
        url  = self.client.get_document_url(filing)
        html = self.client.download_html(url)
        html = _clean_xbrl(html)

        # 輸出 .md（純文字，供搜尋/閱讀）
        md = _html_to_markdown(html)
        md_path.write_text(md, encoding="utf-8")

        # 組出 EDGAR 文件目錄的 base URL（讓圖片相對路徑正確解析）
        acc_clean = filing.accession_number.replace("-", "")
        base_url  = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{filing.cik}/{acc_clean}/"
        )

        # 輸出 .pdf（Playwright 直接渲染 HTML，圖片和表格均正確）
        pdf_html = _prepare_html_for_pdf(html, base_url=base_url, session=self.client.session)
        ok = _convert_html_to_pdf(pdf_html, pdf_path)
        if not ok:
            self.on_log(f"PDF conversion failed: {base_name}", "warn")

        return pdf_path, ok
