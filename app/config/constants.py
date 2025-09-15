"""
Global constants for the MiniRates app.
Keep ONLY pure constants here (no heavy imports / logic).
"""

# --- App meta / behavior ---
BASE_URL = "https://alanchand.com/"          # AlanChand base URL
USER_AGENT = "MiniRateWidget/4.7 (+local)"
TIMEOUT = 12  # seconds
AUTO_REFRESH_MS = 5 * 60 * 1000  # 5 minutes
SETTINGS_FILE = "minirates_settings.json"

# Rows/scroll
ROW_HEIGHT = 28         # the row frame height
ROW_VPAD = 2            # each row pack pady=2  (top+bottom => 4px)
VISIBLE_ROWS = 5        # show exactly 5 rows; others via vertical scroll

# --- Window config ---
WIN_W, WIN_H = 360, 220          # default startup size (first run)
MIN_W, MIN_H = 320, 200          # minimal size allowed
RESIZABLE = True                  # allow user-resizing the window
BORDERLESS = False                # switch to native Windows window frame
START_PINNED = False
TRANS_COLOR = "black"             # used for transparent window background

# --- Spark/Chart config (dynamic bar-count) ---
SPARK_W, SPARK_H = 70, 12          # initial canvas size; may expand in rows.py
HISTORY_MAX = 74                    # must be >= SPARK_BAR_MAX_COUNT

# Dynamic bar layout: compute count from available width
SPARK_BAR_IDEAL_W = 14             # target per-bar width (px)
SPARK_BAR_MAX_COUNT = 30           # max bars when window is very wide
SPARK_BAR_MIN_COUNT = 10           # min bars when window is narrow
SPARK_BAR_MIN_W = 5                # minimum bar width (px)
SPARK_BAR_GAP = 2                  # gap between bars (px)
SPARK_VPAD = 2                     # vertical padding inside canvas (px)
SPARK_SOFT_MARGIN = 0.08           # amplitude soft headroom
SPARK_DRAW_ZERO_LINE = True        # draw baseline (zero axis)

# IMPORTANT: disable legacy fixed-count mode
SPARK_BAR_COUNT = None

# --- Fonts ---
PREFERRED_FONTS = [
    "IRANSansWeb(FaNum)", "Vazirmatn", "IRANSans", "Shabnam", "Sahel",
    "Segoe UI Variable", "Segoe UI", "Tahoma", "Arial"
]

# --- Catalog cache (per source) ---
CATALOG_TTL_SEC = 600  # seconds (10 minutes)

# AlanChand cache file (legacy name kept)
CATALOG_CACHE_FILE = "alanchand_catalog_cache.json"

# TGJU integration
TGJU_BASE_URL = "https://www.tgju.org/"
TGJU_URL = TGJU_BASE_URL                     # alias for adapters using TGJU_URL
TGJU_CACHE_FILE = "tgju_catalog_cache.json"  # separate cache for TGJU

# Enabled sources and priority (left-most has higher priority on merge)
CATALOG_SOURCES = ("alanchand", "tgju")

# --- Money units (canonicalization) ---
CANONICAL_UNIT = "toman"  # internal standard for all prices

# Default unit per source (set truthfully based on each site):
# If TGJU shows Rial on your data, set "tgju": "rial"
# If AlanChand shows Toman, set "alanchand": "toman"
SOURCE_DEFAULT_UNITS = {
    "alanchand": "toman",
    "tgju": "rial",
}

# Pairwise conversion factors: (src_unit -> dst_unit)
UNIT_CONV_FACTORS = {
    ("rial", "toman"): 0.1,
    ("toman", "rial"): 10.0,
    ("toman", "toman"): 1.0,
    ("rial",  "rial"): 1.0,
}
