"""全域常數"""

# SEC EDGAR API
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_TICKERS_URL     = "https://www.sec.gov/files/company_tickers.json"
SEC_ARCHIVES_URL    = "https://www.sec.gov/Archives/edgar/data"
RATE_LIMIT_DELAY    = 0.15   # 秒，維持在 SEC 10 req/s 限制內

# HTTP
DEFAULT_USER_AGENT = "SEC-Downloader-App research@example.com"
REQUEST_TIMEOUT    = 30
MAX_RETRIES        = 3

# 下載
DEFAULT_DOWNLOAD_DIR = "downloads"
SUPPORTED_FORMS      = ["10-K", "10-Q"]
MAX_FILINGS          = 40   # 每種類型最多取回幾筆

# 常用股票預設資料庫（模糊搜尋用）
POPULAR_TICKERS = [
    {"ticker": "AAPL",  "name": "Apple Inc.",                  "sector": "科技"},
    {"ticker": "MSFT",  "name": "Microsoft Corporation",       "sector": "科技"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.",               "sector": "科技"},
    {"ticker": "AMZN",  "name": "Amazon.com Inc.",             "sector": "電商/雲端"},
    {"ticker": "NVDA",  "name": "NVIDIA Corporation",          "sector": "半導體"},
    {"ticker": "META",  "name": "Meta Platforms Inc.",         "sector": "社群媒體"},
    {"ticker": "TSLA",  "name": "Tesla Inc.",                  "sector": "電動車"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway Inc.",     "sector": "金融"},
    {"ticker": "JPM",   "name": "JPMorgan Chase & Co.",        "sector": "金融"},
    {"ticker": "V",     "name": "Visa Inc.",                   "sector": "金融支付"},
    {"ticker": "UNH",   "name": "UnitedHealth Group Inc.",     "sector": "醫療"},
    {"ticker": "JNJ",   "name": "Johnson & Johnson",           "sector": "醫療"},
    {"ticker": "WMT",   "name": "Walmart Inc.",                "sector": "零售"},
    {"ticker": "XOM",   "name": "Exxon Mobil Corporation",     "sector": "能源"},
    {"ticker": "TSM",   "name": "Taiwan Semiconductor",        "sector": "半導體"},
    {"ticker": "AVGO",  "name": "Broadcom Inc.",               "sector": "半導體"},
    {"ticker": "LLY",   "name": "Eli Lilly and Company",       "sector": "醫療"},
    {"ticker": "MA",    "name": "Mastercard Incorporated",     "sector": "金融支付"},
    {"ticker": "HD",    "name": "The Home Depot Inc.",         "sector": "零售"},
    {"ticker": "COST",  "name": "Costco Wholesale Corporation","sector": "零售"},
    {"ticker": "NFLX",  "name": "Netflix Inc.",                "sector": "串流媒體"},
    {"ticker": "AMD",   "name": "Advanced Micro Devices Inc.", "sector": "半導體"},
    {"ticker": "INTC",  "name": "Intel Corporation",           "sector": "半導體"},
    {"ticker": "QCOM",  "name": "Qualcomm Incorporated",       "sector": "半導體"},
    {"ticker": "DIS",   "name": "The Walt Disney Company",     "sector": "娛樂"},
    {"ticker": "BA",    "name": "The Boeing Company",          "sector": "航太"},
    {"ticker": "GS",    "name": "Goldman Sachs Group Inc.",    "sector": "金融"},
    {"ticker": "PYPL",  "name": "PayPal Holdings Inc.",        "sector": "金融科技"},
    {"ticker": "UBER",  "name": "Uber Technologies Inc.",      "sector": "交通科技"},
    {"ticker": "SPOT",  "name": "Spotify Technology S.A.",     "sector": "串流媒體"},
]
