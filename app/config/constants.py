"""
Global constants for the MiniRates app.
Keep ONLY pure constants here (no heavy imports / logic).
"""

# --- App meta / behavior ---
BASE_URL = "https://alanchand.com/"
USER_AGENT = "MiniRateWidget/4.7 (+local)"
TIMEOUT = 12  # seconds
AUTO_REFRESH_MS = 5 * 60 * 1000  # 5 minutes
SETTINGS_FILE = "minirates_settings.json"

# Rows/scroll
ROW_HEIGHT = 28         # the row frame height you already use
ROW_VPAD = 2            # each row pack pady=2  (top+bottom => 4px)
VISIBLE_ROWS = 5        # show exactly 5 rows; others via vertical scroll

# --- Window config ---
WIN_W, WIN_H = 360, 220          # default startup size (first run)
MIN_W, MIN_H = 320, 200          # minimal size allowed
RESIZABLE = True                  # allow user-resizing the window
BORDERLESS = False                # <- switch to native Windows window frame
START_PINNED = False
TRANS_COLOR = "black"             # used for transparent window background

# --- Spark/Chart config ---
SPARK_W, SPARK_H = 60, 12          # initial canvas size; actual width will expand in rows.py
HISTORY_MAX = 64                    # must be >= SPARK_BAR_MAX_COUNT

SPARK_BAR_IDEAL_W = 14             # target per-bar width (px)
SPARK_BAR_MAX_COUNT = 30           # max bars when window is very wide
SPARK_BAR_MIN_COUNT = 10           # min bars when window is narrow

SPARK_VPAD = 2                     # vertical padding inside canvas (px)
SPARK_SOFT_MARGIN = 0.08           # amplitude soft headroom
SPARK_BAR_GAP = 2                  # <-- gap between bars (px), was 1
SPARK_DRAW_ZERO_LINE = True        # draw baseline (zero axis)
SPARK_BAR_MIN_W = 5                # minimum bar width (px)

# Legacy fixed-count (disable it!)
SPARK_BAR_COUNT = None             # or remove this line entirely

# Bar spark (fixed-count bar chart)
SPARK_VPAD = 2                      # vertical padding inside canvas (px)
SPARK_SOFT_MARGIN = 0.08            # amplitude soft headroom to avoid clipping
SPARK_BAR_GAP = 1                   # gap between bars (px)
SPARK_BAR_COUNT = 10                # always render exactly this many bars
SPARK_DRAW_ZERO_LINE = True         # draw baseline (zero axis)
SPARK_BAR_MIN_W = 5                 # minimum bar width (px)

# --- Fonts ---
# Order matters; first available font will be picked at runtime.
PREFERRED_FONTS = [
    "IRANSansWeb(FaNum)", "Vazirmatn", "IRANSans", "Shabnam", "Sahel",
    "Segoe UI Variable", "Segoe UI", "Tahoma", "Arial"
]

# Catalog cache
CATALOG_CACHE_FILE = "alanchand_catalog_cache.json"
CATALOG_TTL_SEC = 600  # seconds (10 minutes)
