CATEGORY_RULES = [
    ("Small Cap", "Small Cap", "HDFCSML250.NS"),
    ("Mid Cap", "Mid Cap", "^NSEMDCP50"),
    ("Large & Mid Cap", "Large & Mid Cap", "^CRSLDX"),
    ("Large Cap", "Large Cap", "^NSEI"),
    ("Flexi Cap", "Flexi Cap", "^CRSLDX"),
    ("Multi Cap", "Multi Cap", "^CRSLDX"),
    ("ELSS", "ELSS", "^CRSLDX"),
    ("Focused", "Focused", "^CRSLDX"),
    ("Value", "Value", "^CRSLDX"),
    ("Contra", "Contra", "^CRSLDX"),
    ("Dividend Yield", "Dividend Yield", "^CRSLDX"),
    ("Sectoral", "Sectoral/Thematic", "^NSEI"),
    ("Thematic", "Sectoral/Thematic", "^NSEI"),
    ("Index Fund", "Index Fund", "^NSEI"),
    ("Debt", "Debt", None),
    ("Hybrid", "Hybrid", "^NSEI")
]

STYLE_FACTORS = {
    "Large Cap": "^NSEI",
    "Mid Cap": "^NSEMDCP50",
    "Small Cap": "HDFCSML250.NS"
}

DEFAULT_RISK_FREE_RATE = 0.065

SCHEME_LIST_CACHE_TTL = 86400  # 24 hours
NAV_HISTORY_CACHE_TTL = 21600  # 6 hours
BENCHMARK_CACHE_TTL = 21600    # 6 hours
