import re
import threading
import time
from datetime import datetime
import json
import os
from typing import Dict, Optional, List
import webbrowser  # to open external links

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

import requests
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter, ImageTk

# Optional system tray and notifications
try:
    import pystray
    from pystray import MenuItem as TrayItem
    SYSTEM_TRAY_AVAILABLE = True
except ImportError:
    SYSTEM_TRAY_AVAILABLE = False

try:
    from plyer import notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False


# -----------------------------
# Config
# -----------------------------
BASE_URL = "https://alanchand.com/"
USER_AGENT = "MiniRateWidget/4.7 (+local)"  # bumped
TIMEOUT = 12
AUTO_REFRESH_MS = 5 * 60 * 1000  # 5 minutes
SETTINGS_FILE = "minirates_settings.json"

WIN_W, WIN_H = 280, 220
BORDERLESS = True
START_PINNED = False
TRANS_COLOR = 'black'

# Sparkline settings
SPARK_W, SPARK_H = 44, 12
HISTORY_MAX = 60

# Bar spark config (fixed count)
SPARK_VPAD = 2               # vertical canvas padding
SPARK_SOFT_MARGIN = 0.08     # headroom on amplitude
SPARK_BAR_GAP = 1            # gap between bars (px)
SPARK_BAR_COUNT = 10         # << always render exactly 10 bars
SPARK_DRAW_ZERO_LINE = True  # draw baseline (zero axis)

# Persian digits maps
P2E = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,.")
E2P = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

PREFERRED_FONTS = [
    "IRANSansWeb(FaNum)", "Vazirmatn", "IRANSans", "Shabnam", "Sahel",
    "Segoe UI Variable", "Segoe UI", "Tahoma", "Arial"
]

# Modern themes (simplified for minimalism)
THEMES = {
    "dark": {
        "BG": "#0a0a0f",
        "SURFACE": "#1a1a22",
        "SURFACE_VARIANT": "#1f1f2a",
        "PRIMARY": "#00e5c7",
        "PRIMARY_VARIANT": "#00b399",
        "ON_SURFACE": "#f0f2f5",
        "ON_SURFACE_VARIANT": "#a1a8b0",
        "OUTLINE": "#2a2a35",
        "SUCCESS": "#22d67e",
        "WARNING": "#ffb347",
        "ERROR": "#ff6b6b",
        "GRADIENT_START": "#1a1a22",
        "GRADIENT_END": "#0a0a0f",
        "FONT_PRIMARY": ("", 10),
        "FONT_BOLD": ("", 10, "bold"),
        "FONT_SMALL": ("", 9),
        "FONT_TITLE": ("", 12, "bold"),
        "ROW_ODD": "#1a1a22",
        "ROW_EVEN": "#1f1f2a",
        "SELECTED": "#2a2a35",
    },
    "light": {
        "BG": "#fafbfc",
        "SURFACE": "#ffffff",
        "SURFACE_VARIANT": "#f6f7f9",
        "PRIMARY": "#0066cc",
        "PRIMARY_VARIANT": "#0052a3",
        "ON_SURFACE": "#1c1e21",
        "ON_SURFACE_VARIANT": "#5a6572",
        "OUTLINE": "#e1e4e8",
        "SUCCESS": "#28a745",
        "WARNING": "#fd7e14",
        "ERROR": "#dc3545",
        "GRADIENT_START": "#ffffff",
        "GRADIENT_END": "#f6f7f9",
        "FONT_PRIMARY": ("", 10),
        "FONT_BOLD": ("", 10, "bold"),
        "FONT_SMALL": ("", 9),
        "FONT_TITLE": ("", 12, "bold"),
        "ROW_ODD": "#ffffff",
        "ROW_EVEN": "#f6f7f9",
        "SELECTED": "#e1e4e8",
    },
    "minimal": {
        "BG": "#16171d",
        "SURFACE": "#1e1f26",
        "SURFACE_VARIANT": "#25262e",
        "PRIMARY": "#8b5cf6",
        "PRIMARY_VARIANT": "#7c3aed",
        "ON_SURFACE": "#e4e7ec",
        "ON_SURFACE_VARIANT": "#9ca3af",
        "OUTLINE": "#2d2e36",
        "SUCCESS": "#10b981",
        "WARNING": "#f59e0b",
        "ERROR": "#f87171",
        "GRADIENT_START": "#1e1f26",
        "GRADIENT_END": "#16171d",
        "FONT_PRIMARY": ("", 10),
        "FONT_BOLD": ("", 10, "bold"),
        "FONT_SMALL": ("", 9),
        "FONT_TITLE": ("", 12, "bold"),
        "ROW_ODD": "#1e1f26",
        "ROW_EVEN": "#25262e",
        "SELECTED": "#2d2e36",
    }
}


# -----------------------------
# Settings Management
# -----------------------------
class SettingsManager:
    """Manages application settings, loading from and saving to a JSON file."""
    def __init__(self):
        self.default_settings = {
            "theme": "dark",
            "auto_refresh": True,
            "notifications": True,
            "price_threshold": 1000,
            "window_position": [100, 100],
            "always_on_top": False
        }
        self.settings = self.load_settings()

    def load_settings(self) -> dict:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return {**self.default_settings, **json.load(f)}
            except Exception:
                pass
        return self.default_settings.copy()

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    def set(self, key: str, value):
        self.settings[key] = value
        self.save_settings()


# -----------------------------
# Scraping
# -----------------------------
def normalize_text(s: str) -> str:
    """Normalizes and translates Persian digits to English."""
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s.strip())
    return s.translate(P2E)

def to_int_irr(text: str) -> Optional[int]:
    """Extracts and converts a price string to an integer, handling commas."""
    t = normalize_text(text)
    m = re.search(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,})(?!\d)", t)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None

def get_html_cache_bust(url: str) -> Optional[BeautifulSoup]:
    """Fetches HTML content from a URL with cache busting and a User-Agent."""
    try:
        ts = int(time.time())
        full = f"{url}?_ts={ts}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
        resp = requests.get(full, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception:
        return None

CSS_SELECTORS = {
    "aud": "body > main > section.container.currencyTable.mt-4 > div > div:nth-child(1) > table > tbody > tr:nth-child(9) > td.sellPrice.text-center",
    "g18": "body > main > section.container.mt-5 > div.row > div:nth-child(2) > div > div > span",
    "emami": "body > main > section.container.mt-5 > div.row > div:nth-child(3) > div > div > span",
}

LABELS = {
    "usd": [r"دلار\s*آمریکا", r"دلار\s*آزاد", r"\bUSD\b"],
    "aud": [r"دلار\s*استرالیا", r"\bAUD\b"],
    "g18": [r"(?:طلای?|گرم(?:ی)?)\s*18\s*عیار", r"(?:طلای?|گرم(?:ی)?)\s*۱۸\s*عیار"],
    "emami": [r"سکه\s*(?:تمام\s*بهار\s*آزادی\s*)?طرح\s*جدید", r"سکه\s*امامی"],
}

def select_price_by_css(soup: BeautifulSoup, selector: str) -> Optional[int]:
    """Finds a price by CSS selector and converts it to an integer."""
    if not soup:
        return None
    try:
        el = soup.select_one(selector)
        return to_int_irr(el.get_text(" ", strip=True)) if el else None
    except Exception:
        return None

def find_row_price_by_label(soup: BeautifulSoup, label_regexes: List[str]) -> Optional[int]:
    """Finds a price by searching for a label regex in a row and then parsing."""
    if not soup:
        return None
    rows = soup.find_all(["tr", "li", "div", "section", "article"])
    regs = [re.compile(rx, re.IGNORECASE) for rx in label_regexes]
    
    for row in rows:
        row_text = normalize_text(row.get_text(" ", strip=True))
        if not row_text or not any(rx.search(row_text) for rx in regs):
            continue
        
        for selector_class in ["sellPrice", "priceSymbol"]:
            el = row.find(class_=lambda c: c and re.search(rf"\b{selector_class}\b", c, re.IGNORECASE))
            if el:
                val = to_int_irr(el.get_text(" ", strip=True))
                if val:
                    return val
        
        val = to_int_irr(row_text)
        if val:
            return val
    return None

def scrape_alanchand_precise() -> Dict[str, Optional[int]]:
    """Scrapes prices for multiple currencies/items from the target website."""
    soup = get_html_cache_bust(BASE_URL)
    out = {"usd": None, "aud": None, "g18": None, "emami": None}
    if not soup:
        return out
    
    out["usd"] = find_row_price_by_label(soup, LABELS["usd"])
    out["aud"] = select_price_by_css(soup, CSS_SELECTORS["aud"]) or find_row_price_by_label(soup, LABELS["aud"])
    out["g18"] = select_price_by_css(soup, CSS_SELECTORS["g18"]) or find_row_price_by_label(soup, LABELS["g18"])
    out["emami"] = select_price_by_css(soup, CSS_SELECTORS["emami"]) or find_row_price_by_label(soup, LABELS["emami"])
    
    return out

# -----------------------------
# Rounded/tray helpers
# -----------------------------
def get_rounded_mask(width: int, height: int, radius: int) -> Image.Image:
    """Creates a rounded corner mask for a window."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, width, height), radius, fill=255)
    return mask

if SYSTEM_TRAY_AVAILABLE:
    def create_premium_icon(size=64, theme_name="dark") -> Image.Image:
        """Creates a modern-looking icon for the system tray."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        colors = {
            "dark": [(0, 229, 199), (139, 92, 246)],
            "light": [(0, 102, 204), (88, 166, 255)],
            "minimal": [(139, 92, 246), (168, 85, 247)]
        }
        gradient_colors = colors.get(theme_name, colors["dark"])
        for i in range(size):
            r = int(gradient_colors[0][0] + (gradient_colors[1][0] - gradient_colors[0][0]) * i / size)
            g = int(gradient_colors[0][1] + (gradient_colors[1][1] - gradient_colors[0][1]) * i / size)
            b = int(gradient_colors[0][2] + (gradient_colors[1][2] - gradient_colors[0][2]) * i / size)
            draw.ellipse([(2, i), (size-2, i+2)], fill=(r, g, b, 200))
        center = size // 2
        symbol_size = size // 3
        draw.ellipse([(center - symbol_size//2, center - symbol_size//2),
                      (center + symbol_size//2, center + symbol_size//2)], 
                      fill=(255, 255, 255, 230))
        img = img.filter(ImageFilter.GaussianBlur(0.5))
        return img


# -----------------------------
# Ultra-compact modern app
# -----------------------------
class UltraCompactRateApp(tk.Tk):
    """The main application class for the rate widget."""
    def __init__(self):
        super().__init__()

        self.settings = SettingsManager()
        self.theme_name = self.settings.get("theme", "dark")
        if self.theme_name not in THEMES:
            self.theme_name = "dark"
        
        self.main_font = self._get_preferred_font(PREFERRED_FONTS)
        self._update_theme_fonts()
        # Force FaNum font for time label (with fallback if not installed)
        fa_candidates = ["IRANSansWeb(FaNum)", "IRANSansWeb FaNum", "IRANSans(FaNum)", "IRANSans FaNum"]
        available = set(tkfont.families())
        self.fa_num_family = next((f for f in fa_candidates if f in available), self.main_font)
        self.font_time_small = tkfont.Font(family=self.fa_num_family, size=9)
        self.font_trend_small = tkfont.Font(family=self.main_font, size=8)


        self.t = THEMES[self.theme_name]
        
        self.price_history = {}  # last numeric values for diff arrows
        # Sparkline series per key
        self.series_hist = {"usd": [], "aud": [], "g18": [], "emami": []}
        # Timestamps for each sample (aligned with series_hist points)
        self.series_times = {"usd": [], "aud": [], "g18": [], "emami": []}
        
        self.is_fetching = False
        self.refresh_job = None
        self.fade_job = None
        self.spinner_job = None
        self.spinner_frames = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        
        self.selected_row = None
        self.row_bgs = {}
        
        self._setup_window()
        self._setup_ui()
        self._setup_shortcuts()
        
        if SYSTEM_TRAY_AVAILABLE:
            self._start_tray()
        
        self.after(100, lambda: self._refresh(manual=False))
    
    # -------- formatting (compact, based on Toman) --------
    def _format_price_compact(self, n: Optional[int]) -> str:
        """Compact formatter based on Toman.
        Input n is in Toman, then:
          - < 1K Toman     : show plain Toman (no suffix), no decimals
          - 1K .. < 1M     : show in K (thousand Toman)
                             <100K -> 1 decimal, >=100K -> 0 decimals
          - >= 1M          : show in M (million Toman)
                             <10M -> 2 decimals, >=10M -> 0 decimals
        Digits are Persian; suffixes stay Latin (K/M)."""
        
        # Define dictionary for converting English digits to Persian
        E2P = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        
        # Check for None or non-numeric input
        if n is None:
            return "—"
        if not isinstance(n, (int, float)):
            return "—"
        
        # Use input directly as Toman
        toman = n
        
        # Handle negative numbers
        sign = "-" if toman < 0 else ""
        toman = abs(toman)
        
        # < 1K Toman: show plain number without suffix
        if toman < 1_000:
            s = f"{int(round(toman)):,}".replace(",", "٬")
            return sign + s.translate(E2P)
        
        # 1K .. < 1M Toman: show in thousands (K)
        if toman < 1_000_000:
            k = toman / 1_000.0
            if k < 100:
                s = f"{k:.1f}".rstrip("0").rstrip(".")
            else:
                s = f"{int(round(k)):,}".replace(",", "٬")
            return sign + s.translate(E2P) + " K"
        
        # >= 1M Toman: show in millions (M)
        m = toman / 1_000_000.0
        if m < 10:
            s = f"{m:.2f}".rstrip("0").rstrip(".")
        else:
            s = f"{int(round(m)):,}".replace(",", "٬")
        return sign + s.translate(E2P) + " M"

    
    def _ensure_tooltip(self):
        """Create tooltip window on demand."""
        if hasattr(self, "_tooltip_win") and self._tooltip_win:
            return
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.withdraw()
        self._tooltip_win.overrideredirect(True)
        self._tooltip_win.attributes("-topmost", True)
        self._tooltip_label = tk.Label(
            self._tooltip_win,
            text="",
            bg=self.t["SURFACE_VARIANT"],
            fg=self.t["ON_SURFACE"],
            font=self.t["FONT_SMALL"],
            padx=6, pady=2,
            bd=1, relief="solid"
        )

        # Use outline color for border
        self._tooltip_label.configure(highlightthickness=0)
        self._tooltip_label.pack()

    def _row_context_menu(self, event, key):
        """Context menu: copy value / copy row."""
        try:
            self._select_row(key)
            m = tk.Menu(self, tearoff=0)
            m.add_command(label="کپی مقدار", command=self._copy_value_selected)
            m.add_command(label="کپی عنوان+مقدار", command=self._copy_row_selected)
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _row_key_from_widget(self, widget):
        """Walk up the widget tree to find row key for a widget."""
        while widget and widget is not self:
            for key, rw in self.row_widgets.items():
                if widget in (rw["frame"], rw["inner"], rw["title_lbl"], rw["value_lbl"], rw.get("spark"), rw.get("trend_lbl")):
                    return key
            widget = getattr(widget, "master", None)
        return None

    def _copy_value_selected(self, event=None):
        """Copy the FULL numeric value + ' ریال' of the selected row (fallback: row under cursor)."""
        # Figure out which row
        key = self.selected_row
        if not key:
            w = event.widget if event and hasattr(event, "widget") else self.winfo_containing(*self.winfo_pointerxy())
            key = self._row_key_from_widget(w)
        if not key or key not in self.row_widgets:
            return

        # Prefer numeric from price_history (exact full value)
        val_num = self.price_history.get(key)

        # Fallback: parse from compact label (e.g., "۸.۱۵ M", "۶۴.۷ T")
        if val_num is None:
            raw = self.row_widgets[key]["value_lbl"].cget("text").strip()
            raw_en = raw.translate(P2E)  # Persian digits -> English
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([TM])?\s*$", raw_en)
            if m:
                num = float(m.group(1))
                suffix = m.group(2)
                if suffix == "M":
                    val_num = int(round(num * 1_000_000))
                elif suffix == "T":
                    val_num = int(round(num * 1_000))
                else:
                    val_num = int(round(num))

        if val_num is None:
            return  # nothing to copy

        # Format full value with thousands separators + Persian digits + unit
        txt = f"{self._format_price(val_num)} ریال"
        self.clipboard_clear()
        self.clipboard_append(txt)

        # Optional toast
        try:
            if NOTIFICATIONS_AVAILABLE:
                notification.notify(title="کپی شد", message="مقدار کامل کپی شد.", timeout=2)
        except Exception:
            pass

    def _copy_row_selected(self, event=None):
        """Copy 'Title: Value' of selected row."""
        key = self.selected_row
        if not key:
            w = event.widget if event and hasattr(event, "widget") else self.winfo_containing(*self.winfo_pointerxy())
            key = self._row_key_from_widget(w)
        if not key or key not in self.row_widgets:
            return
        rw = self.row_widgets[key]
        txt = f"{rw['title_lbl'].cget('text')}: {rw['value_lbl'].cget('text')}".strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        try:
            if NOTIFICATIONS_AVAILABLE:
                notification.notify(title="کپی شد", message="ردیف (عنوان: مقدار) کپی شد.", timeout=2)
        except Exception:
            pass

    def _tooltip_show(self, text: str, x: int, y: int):
        """Show tooltip near screen coordinates (x, y)."""
        self._ensure_tooltip()
        self._tooltip_label.config(
            text=text,
            bg=self.t["SURFACE_VARIANT"],
            fg=self.t["ON_SURFACE"]
        )
        # Slight offset so it doesn't sit exactly under the cursor
        self._tooltip_win.geometry(f"+{x+12}+{y+12}")
        self._tooltip_win.deiconify()
        self._tooltip_win.lift()

    def _tooltip_hide(self):
        """Hide tooltip if visible."""
        try:
            if hasattr(self, "_tooltip_win") and self._tooltip_win:
                self._tooltip_win.withdraw()
        except Exception:
            pass


    # -------- fonts/theme --------
    def _get_preferred_font(self, preferred_list: List[str]):
        """Finds the first available font from a list of preferred fonts."""
        available_fonts = tkfont.families()
        for font_name in preferred_list:
            if font_name in available_fonts:
                return font_name
        return "Arial"

    def _update_theme_fonts(self):
        """Updates the font families for all themes based on the detected font."""
        for theme_key in THEMES:
            theme = THEMES[theme_key]
            theme["FONT_PRIMARY"] = (self.main_font, 10)
            theme["FONT_BOLD"] = (self.main_font, 10, "bold")
            theme["FONT_SMALL"] = (self.main_font, 9)
            theme["FONT_TITLE"] = (self.main_font, 12, "bold")

    # -------- window --------
    def _setup_window(self):
        """Initializes the main application window properties."""
        self.title("MiniRates Pro")
        pos = self.settings.get("window_position", [100, 100])
        self.geometry(f"{WIN_W}x{WIN_H}+{pos[0]}+{pos[1]}")
        
        self.configure(bg=TRANS_COLOR)
        self.attributes('-transparentcolor', TRANS_COLOR)
        self.resizable(False, False)
        
        if BORDERLESS:
            self.overrideredirect(True)
        
        self.pinned = self.settings.get("always_on_top", START_PINNED)
        self.attributes("-topmost", self.pinned)
        
        self._drag_data = {"x": 0, "y": 0}
        
    # -------- UI --------
    def _setup_ui(self):
        """Sets up the main UI components and their layout."""
        t = self.t

        # Card (no extra padding)
        self.card = tk.Frame(self, bg=t["SURFACE"], highlightthickness=0, bd=0)
        self.card.pack(fill=tk.BOTH, expand=True)

        # Rounded background canvas
        self.card.bind("<Configure>", self._draw_rounded_corners_bg)
        self.rounded_bg_canvas = tk.Canvas(self.card, bg=TRANS_COLOR, highlightthickness=0)
        self.rounded_bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Header
        self.header_frame = self._create_compact_header(self.card)
        self.header_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(4, 1))
        
        self.divider1 = tk.Frame(self.card, bg=t["OUTLINE"], height=1)
        self.divider1.pack(fill=tk.X, padx=4, pady=(2, 0))
        
        # Rows
        self.rows_container = self._create_rows_table(self.card)
        self.rows_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 2))
        
        self.divider2 = tk.Frame(self.card, bg=t["OUTLINE"], height=1)
        self.divider2.pack(fill=tk.X, padx=4, pady=(0, 2))
        
        # Footer
        self.footer_frame = self._create_minimal_footer(self.card)
        self.footer_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        
        self.after(80, self._recalc_window_height)

    def _draw_rounded_corners_bg(self, event=None):
        """Draws the rounded corners on the background canvas."""
        t = self.t
        canvas = self.rounded_bg_canvas
        canvas.delete("rounded_bg")
        w, h = self.card.winfo_width(), self.card.winfo_height()
        
        def _create_rounded_rectangle(c, x1, y1, x2, y2, radius, **kwargs):
            points = []
            points += [(x1 + radius, y1), (x2 - radius, y1)]
            points += [(x2, y1), (x2, y1 + radius)]
            points += [(x2, y2 - radius), (x2, y2)]
            points += [(x2 - radius, y2), (x1 + radius, y2)]
            points += [(x1, y2), (x1, y2 - radius)]
            points += [(x1, y1 + radius), (x1, y1)]
            return c.create_polygon(points, smooth=True, **kwargs)

        _create_rounded_rectangle(canvas, 0, 0, w, h, 16, fill=t["SURFACE"], outline="", tags="rounded_bg")

    def _update_ui_theme(self):
        """Updates colors and fonts to the current theme."""
        t = self.t
        
        # If tooltip is visible, refresh its palette
        if hasattr(self, "_tooltip_win") and self._tooltip_win and self._tooltip_win.state() == "normal":
            try:
                self._tooltip_label.config(bg=self.t["SURFACE_VARIANT"], fg=self.t["ON_SURFACE"])
            except Exception:
                pass

        
        self.configure(bg=TRANS_COLOR)
        self.card.configure(bg=t["SURFACE"])
        self.rounded_bg_canvas.configure(bg=TRANS_COLOR)
        self.card.after(10, self._draw_rounded_corners_bg)
        
        # Header
        self.header_frame.configure(bg=t["SURFACE_VARIANT"])
        for child in self.header_frame.winfo_children():
            child.configure(bg=t["SURFACE_VARIANT"])
            if isinstance(child, tk.Frame):
                for subchild in child.winfo_children():
                    subchild.configure(bg=t["SURFACE_VARIANT"])
        self.app_title.configure(fg=t["ON_SURFACE"], bg=t["SURFACE_VARIANT"])
        self.pin_btn.configure(bg=t["SURFACE_VARIANT"], fg=t["ON_SURFACE_VARIANT"])
        self.minimize_btn.configure(bg=t["SURFACE_VARIANT"], fg=t["ON_SURFACE_VARIANT"])
        self.close_btn.configure(bg=t["SURFACE_VARIANT"])

        # Rows (apply bg consistently to frame/inner/labels/canvases)
        self.rows_container.configure(bg=t["SURFACE"])
        for idx, key in enumerate(self.row_widgets.keys()):
            bgc = t["ROW_ODD"] if idx % 2 == 0 else t["ROW_EVEN"]
            self.row_bgs[key] = bgc
            rw = self.row_widgets[key]
            current_bg = t["SELECTED"] if self.selected_row == key else bgc

            rw["frame"].configure(bg=current_bg)
            rw["inner"].configure(bg=current_bg)
            rw["title_lbl"].configure(bg=current_bg, fg=t["ON_SURFACE"])
            rw["value_lbl"].configure(bg=current_bg, fg=t["ON_SURFACE"])
            rw["trend_lbl"].configure(bg=current_bg, fg=t["ON_SURFACE_VARIANT"])
            rw["spark"].configure(bg=current_bg)
            self._render_spark(key)  # redraw with theme

        # Dividers
        self.divider1.configure(bg=t["OUTLINE"])
        self.divider2.configure(bg=t["OUTLINE"])
        
        # Footer
        self.footer_frame.configure(bg=t["SURFACE_VARIANT"])
        for child in self.footer_frame.winfo_children():
            child.configure(bg=t["SURFACE_VARIANT"])
            if isinstance(child, tk.Frame):
                for subchild in child.winfo_children():
                    subchild.configure(bg=t["SURFACE_VARIANT"])
        self.update_label.configure(bg=t["SURFACE_VARIANT"], fg=t["ON_SURFACE_VARIANT"], font=self.font_time_small)
        self.theme_btn.configure(fg=t["ON_SURFACE_VARIANT"], bg=t["SURFACE_VARIANT"])
        self.refresh_btn.configure(bg=t["SURFACE_VARIANT"])
        self._apply_refresh_state_color(idle=True)

    def _create_compact_header(self, parent):
        """Header: logo+title (vertically aligned) + controls with reversed order."""
        t = self.t

        header = tk.Frame(parent, bg=t["SURFACE_VARIANT"], height=28)
        header.pack_propagate(False)

        # Drag from header
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._do_drag)
        header.bind("<ButtonRelease-1>", self._stop_drag)

        # --- Left: combined Logo + Title for perfect vertical alignment ---
        left_group = tk.Frame(header, bg=t["SURFACE_VARIANT"])
        left_group.pack(side=tk.LEFT)

        # Load logo (20x20)
        logo_imgtk = None
        logo_url = "https://imsalione.ir/wp-content/uploads/2023/06/ImSalione-Logo-140x140.png"
        try:
            r = requests.get(logo_url, timeout=6)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            img = img.resize((20, 20), Image.LANCZOS)
            logo_imgtk = ImageTk.PhotoImage(img)
        except Exception:
            pass

        # Single label with image+text ensures vertical alignment
        self.app_title = tk.Label(
            left_group,
            text=" MiniRates",  # leading space for nicer spacing after icon
            image=logo_imgtk,
            compound="left",
            fg=t["ON_SURFACE"],
            bg=t["SURFACE_VARIANT"],
            font=t["FONT_TITLE"],
            cursor="hand2"
        )
        self.app_title.image = logo_imgtk  # keep reference
        self.app_title.pack(side=tk.LEFT, padx=(0, 4), pady=3)  # slight vertical centering
        self.app_title.bind("<Button-1>", lambda e: webbrowser.open_new_tab("https://imsalione.ir/"))
        # Also draggable
        self.app_title.bind("<Button-1>", self._start_drag, add="+")
        self.app_title.bind("<B1-Motion>", self._do_drag, add="+")

        # --- Right: controls (REVERSED order horizontally) ---
        right_controls = tk.Frame(header, bg=t["SURFACE_VARIANT"])
        right_controls.pack(side=tk.RIGHT)

        # Close button RIGHTMOST (exits app)
        self.close_btn = self._create_mini_button(right_controls, "✕", self._exit_app, danger=True)
        self.close_btn.pack(side=tk.RIGHT, padx=(2, 0))

        # Minimize (to tray) comes next
        self.minimize_btn = self._create_mini_button(right_controls, "─", self._hide_to_tray)
        self.minimize_btn.pack(side=tk.RIGHT, padx=1)

        # Pin (leftmost within the right group)
        self.pin_btn = self._create_mini_button(
            right_controls, "📌" if self.pinned else "📍", self._toggle_pin
        )
        self.pin_btn.pack(side=tk.RIGHT, padx=1)

        return header

    def _create_rows_table(self, parent):
        """Creates the main table for displaying exchange rates."""
        t = self.t

        rows_container = tk.Frame(parent, bg=t["SURFACE"])

        self.data_rows = {
            "usd": {"title": "دلار امریکا", "value": None},
            "aud": {"title": "دلار استرالیا", "value": None},
            "g18": {"title": "طلای ۱۸ عیار", "value": None},
            "emami": {"title": "سکه امامی", "value": None}
        }

        self.row_widgets = {}
        self.row_bgs = {}

        # helper for binding clicks per row
        def _bind_row_clicks(widget, k):
            widget.bind("<Button-1>",        lambda e, key=k: self._select_row(key))
            widget.bind("<Double-Button-1>", lambda e, key=k: (self._select_row(key), self._copy_value_selected()))
            widget.bind("<Button-3>",        lambda e, key=k: self._row_context_menu(e, key))  # right-click

        for idx, (key, row) in enumerate(self.data_rows.items()):
            bgc = t["ROW_ODD"] if idx % 2 == 0 else t["ROW_EVEN"]
            self.row_bgs[key] = bgc

            rf = tk.Frame(rows_container, bg=bgc, height=28)
            rf.pack(fill=tk.X, pady=2)
            rf.pack_propagate(False)

            inner = tk.Frame(rf, bg=bgc)
            inner.pack(fill=tk.BOTH, expand=True, padx=8)

            # value (left)
            value_lbl = tk.Label(inner, text="—", fg=t["ON_SURFACE"], bg=bgc, font=t["FONT_BOLD"], anchor="w")
            value_lbl.pack(side=tk.LEFT)

            # spark (left-middle)
            spark = tk.Canvas(inner, width=SPARK_W, height=SPARK_H, bg=bgc, highlightthickness=0, bd=0)
            spark.pack(side=tk.LEFT, padx=(4, 2))

            # trend (expand to take space)
            trend_lbl = tk.Label(inner, text="", fg=t["ON_SURFACE_VARIANT"], bg=bgc,
                                 font=self.font_trend_small, anchor="w")
            trend_lbl.pack(side=tk.LEFT, padx=(2, 6), expand=True, fill=tk.X)

            # title (right)
            title_lbl = tk.Label(inner, text=row["title"], fg=t["ON_SURFACE"], bg=bgc,
                                 font=t["FONT_PRIMARY"], anchor="e")
            title_lbl.pack(side=tk.RIGHT)

            # store refs
            self.row_widgets[key] = {
                "frame": rf,
                "inner": inner,
                "title_lbl": title_lbl,
                "value_lbl": value_lbl,
                "spark": spark,
                "trend_lbl": trend_lbl
            }

            # bind AFTER widgets exist
            for w in (rf, inner, title_lbl, value_lbl, spark, trend_lbl):
                _bind_row_clicks(w, key)

        return rows_container

    def _create_minimal_footer(self, parent):
        """Creates the footer with theme button, refresh button, and update time."""
        t = self.t
        
        footer = tk.Frame(parent, bg=t["SURFACE_VARIANT"], height=24)
        footer.pack_propagate(False)
        
        # Left side: Theme button
        self.theme_btn = tk.Label(
            footer, text=self._theme_icon_for(self.theme_name),
            fg=t["ON_SURFACE_VARIANT"], bg=t["SURFACE_VARIANT"],
            font=t["FONT_TITLE"], padx=6, cursor="hand2"
        )
        self.theme_btn.pack(side=tk.LEFT)
        self.theme_btn.bind("<Button-1>", lambda e: self._cycle_theme())

        # Right side: time + refresh
        right_controls = tk.Frame(footer, bg=t["SURFACE_VARIANT"])
        right_controls.pack(side=tk.RIGHT)
        
        self.refresh_btn = self._create_mini_button(right_controls, "⟳", self._manual_refresh)
        self.refresh_btn.pack(side=tk.RIGHT)
        
        self.update_label = tk.Label(
            footer, text="", fg=t["ON_SURFACE_VARIANT"], bg=t["SURFACE_VARIANT"],
            font=self.font_time_small
        )
        self.update_label.pack(side=tk.RIGHT, padx=(0, 4))
        
        return footer

    # -------- sparkline helpers --------
    def _push_history(self, key: str, value: int | None):
        """Append a point on every refresh (and its timestamp).
        - If value is None and we have previous, repeat last (flat forward).
        - Always append to move the chart horizontally.
        """
        series = self.series_hist.get(key)
        times = self.series_times.get(key)
        if series is None:
            self.series_hist[key] = series = []
        if times is None:
            self.series_times[key] = times = []

        # Determine value to append
        if value is None:
            if not series:
                return  # nothing to append yet
            value = series[-1]

        # Append value + timestamp (HH:MM)
        series.append(value)
        times.append(datetime.now().strftime('%H:%M'))

        # Trim to HISTORY_MAX for memory
        if len(series) > HISTORY_MAX:
            trim = len(series) - HISTORY_MAX
            del series[:trim]
            del times[:trim]

    def _render_spark(self, key: str):
        """Draw a fixed-count (10) positive/negative bar chart per row with tooltips.
        - Always renders exactly SPARK_BAR_COUNT bars.
        - Each bar represents diff between consecutive points.
        - Oldest bar drops from the left; newest bar appears at the right.
        - Bar color: green for up, red for down, neutral gray for zero.
        - Tooltip shows the time (HH:MM) the bar was created (timestamp of the newer sample).
        """
        rw = self.row_widgets.get(key)
        if not rw or "spark" not in rw:
            return
        cv = rw["spark"]
        cv.delete("all")

        series = self.series_hist.get(key, [])
        times = self.series_times.get(key, [])

        # Canvas size & padding
        w = int(cv.cget("width"))
        h = int(cv.cget("height"))
        pad_x = 1
        pad_y = max(1, SPARK_VPAD)

        # Build diffs and aligned bar-times/values (time & price of the NEWER point)
        if len(series) >= 2:
            diffs = [series[i] - series[i - 1] for i in range(1, len(series))]
            bar_times  = [times[i]  if i < len(times)  else None for i in range(1, len(series))]
            bar_values = [series[i] if i < len(series) else None for i in range(1, len(series))]
        else:
            diffs, bar_times, bar_values = [], [], []

            # Ensure exactly SPARK_BAR_COUNT bars
            if len(diffs) >= SPARK_BAR_COUNT:
                diffs      = diffs[-SPARK_BAR_COUNT:]
                bar_times  = bar_times[-SPARK_BAR_COUNT:]
                bar_values = bar_values[-SPARK_BAR_COUNT:]
            else:
                pad_len    = SPARK_BAR_COUNT - len(diffs)
                diffs      = [0]    * pad_len + diffs
                bar_times  = [None] * pad_len + bar_times
                bar_values = [None] * pad_len + bar_values


        # Compute per-bar width and scaling
        k = SPARK_BAR_COUNT
        total_gap = (k - 1) * SPARK_BAR_GAP
        bar_w = max(1, int((w - 2 * pad_x - total_gap) / k))

        # Amplitude scaling symmetric around zero with soft margin
        dmin, dmax = (min(diffs), max(diffs)) if diffs else (0, 0)
        amp = max(abs(dmin), abs(dmax))
        if amp == 0:
            amp = 1
        amp = amp * (1 + SPARK_SOFT_MARGIN)
        usable_half_h = max(1, (h - 2 * pad_y) / 2.0)
        scale = usable_half_h / amp

        # Baseline (zero) in the middle
        y0 = h / 2.0
        if SPARK_DRAW_ZERO_LINE:
            cv.create_line(pad_x, y0, w - pad_x, y0, fill=self.t["OUTLINE"], width=1)

        # Draw bars left->right; rightmost is the newest bar
        x = pad_x
        for i, d in enumerate(diffs):
            # Color per sign
            if d > 0:
                color = self.t["SUCCESS"]
            elif d < 0:
                color = self.t["ERROR"]
            else:
                color = self.t["ON_SURFACE_VARIANT"]

            # Build tooltip text (time on first line, full price on second)
            tlabel = bar_times[i]
            vlabel = bar_values[i]

            time_txt  = (tlabel.translate(E2P) if tlabel else "—")
            price_txt = (self._format_price_compact(vlabel)) if vlabel is not None else "—"

            tip_txt = f"{time_txt}\n{price_txt}"


            if d == 0:
                # Neutral thin segment on baseline
                item = cv.create_line(x, y0, x + bar_w, y0, fill=color, width=1)
            else:
                if d > 0:
                    y1, y2 = y0 - (d * scale), y0
                else:
                    y1, y2 = y0, y0 + (abs(d) * scale)
                # Clamp within vertical padding
                y1 = max(pad_y, min(h - pad_y, y1))
                y2 = max(pad_y, min(h - pad_y, y2))
                if abs(y2 - y1) < 1:
                    # Guarantee visibility
                    if y2 >= y1:
                        y2 = y1 + 1
                    else:
                        y1 = y2 + 1
                item = cv.create_rectangle(x, y1, x + bar_w, y2, outline=color, fill=color, width=0)

            # Bind tooltip to this bar item
            cv.tag_bind(item, "<Enter>", lambda e, txt=tip_txt: self._tooltip_show(txt, e.x_root, e.y_root))
            cv.tag_bind(item, "<Motion>", lambda e, txt=tip_txt: self._tooltip_show(txt, e.x_root, e.y_root))
            cv.tag_bind(item, "<Leave>", lambda e: self._tooltip_hide())
            cv.tag_bind(item, "<Button-1>", lambda e, key=key: self._select_row(key))

            x += bar_w + SPARK_BAR_GAP

    # -------- footer helpers --------
    def _theme_icon_for(self, theme_name: str) -> str:
        return {"dark": "🌙", "light": "☀", "minimal": "🌓"}.get(theme_name, "🌓")

    def _cycle_theme(self):
        order = ["dark", "light", "minimal"]
        i = order.index(self.theme_name) if self.theme_name in order else 0
        nxt = order[(i + 1) % len(order)]
        self._apply_theme(nxt)

    # -------- UI plumbing --------
    def _create_mini_button(self, parent, text, command, danger=False):
        """Small, styled label-as-button."""
        t = self.t
        color = t["ERROR"] if danger else t["ON_SURFACE_VARIANT"]
        
        btn = tk.Label(
            parent, text=text, fg=color, bg=parent.cget("bg"),
            font=t["FONT_SMALL"], cursor="hand2", padx=4
        )
        btn.bind("<Button-1>", lambda e: command())
        if text != "⟳":
            btn.bind("<Enter>", lambda e: btn.config(fg=t["PRIMARY"]))
            btn.bind("<Leave>", lambda e: btn.config(fg=color))
        return btn

    def _recalc_window_height(self):
        """Adjusts window height to content."""
        try:
            self.update_idletasks()
            content_height = self.card.winfo_reqheight()
            total_h = max(160, min(380, content_height))
            self.geometry(f"{WIN_W}x{int(total_h)}+{self.winfo_x()}+{self.winfo_y()}")
        except Exception:
            pass

    def _setup_shortcuts(self):
        """Keyboard shortcuts."""
        # Copy just the value (rate column)
        for seq in ("<Control-c>", "<Control-Key-c>", "<Control-C>"):
            self.bind_all(seq, self._copy_value_selected)
        # Copy "Title: Value"
        for seq in ("<Control-Shift-c>", "<Control-Shift-Key-c>"):
            self.bind_all(seq, self._copy_row_selected)

        self.bind_all("<Control-r>", lambda e: self._refresh(manual=True))
        self.bind_all("<F5>",       lambda e: self._refresh(manual=True))
        self.bind_all("<Escape>",   lambda e: self._hide_to_tray())
        self.bind_all("<Control-q>",lambda e: self._exit_app())

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _do_drag(self, event):
        x = self.winfo_pointerx() - self._drag_data["x"]
        y = self.winfo_pointery() - self._drag_data["y"]
        self.geometry(f"+{x}+{y}")
    
    def _stop_drag(self, event):
        pos = [self.winfo_x(), self.winfo_y()]
        self.settings.set("window_position", pos)
    
    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.attributes("-topmost", self.pinned)
        self.pin_btn.config(text="📌" if self.pinned else "📍")
        self.settings.set("always_on_top", self.pinned)
    
    # -------- refresh flow --------
    def _manual_refresh(self):
        """Manual refresh that respects is_fetching guard."""
        if not self.is_fetching:
            self._refresh(manual=True)
    
    def _refresh(self, manual=False):
        """Refresh with robust scheduling and error safety."""
        if self.is_fetching:
            return
        # Cancel any pending auto-refresh to avoid overlaps
        if self.refresh_job:
            try:
                self.after_cancel(self.refresh_job)
            except Exception:
                pass
            self.refresh_job = None

        self.is_fetching = True
        self._start_spinner()
        threading.Thread(target=self._fetch_data, args=(manual,), daemon=True).start()
    
    def _fetch_data(self, manual):
        """Fetch data with try/finally so UI always recovers."""
        try:
            data = scrape_alanchand_precise()
        except Exception:
            data = {"usd": None, "aud": None, "g18": None, "emami": None}
        finally:
            # Always update UI on main thread to stop spinner/reset state
            self.after(0, self._update_ui, data, manual)
    
    def _update_ui(self, data, manual):
        """Updates UI after fetching."""
        t = self.t
        success = any(data.values())
        
        for key, new_value in data.items():
            if key not in self.row_widgets:
                continue
            rw = self.row_widgets[key]
            old_value = self.price_history.get(key)
            
            # Update main value text
            formatted = self._format_price_compact(new_value)
            rw["value_lbl"].config(text=formatted)

            # Push point and re-draw sparkline (always progresses)
            self._push_history(key, new_value)
            self._render_spark(key)

            # Trend arrow + diff text (with unit 'ریال')
            if old_value is not None and new_value is not None:
                diff = new_value - old_value
                if diff > 0:
                    rw["trend_lbl"].config(text=f"▲ {self._format_price(abs(diff))} ریال", fg=t["SUCCESS"])
                elif diff < 0:
                    rw["trend_lbl"].config(text=f"▼ {self._format_price(abs(diff))} ریال", fg=t["ERROR"])
                else:
                    rw["trend_lbl"].config(text="•", fg=t["ON_SURFACE_VARIANT"])
            else:
                # No previous value to compare
                rw["trend_lbl"].config(text="", fg=t["ON_SURFACE_VARIANT"])

            # Keep last numeric
            if new_value is not None:
                self.price_history[key] = new_value

        # Update time
        now = datetime.now().strftime('%H:%M')
        self.update_label.config(text=now.translate(E2P))
        
        if not success and manual:
            self._show_error_notification()
        
        self._stop_spinner()
        self._apply_refresh_state_color(idle=False, success=success)
        self.is_fetching = False
        
        # Reschedule auto refresh
        try:
            if self.refresh_job:
                self.after_cancel(self.refresh_job)
        except Exception:
            pass
        self.refresh_job = self.after(AUTO_REFRESH_MS, lambda: self._refresh(manual=False))

        # Recalc window height in case content width changed
        self.after(10, self._recalc_window_height)

    @staticmethod
    def _format_price(n: Optional[int]) -> str:
        if n is None:
            return "—"
        s = f"{n:,}".replace(",", "٬")
        return s.translate(E2P)
    
    def _show_error_notification(self):
        if NOTIFICATIONS_AVAILABLE:
            notification.notify(
                title="خطا در بروزرسانی",
                message="امکان دریافت قیمت‌ها وجود ندارد",
                timeout=3
            )
    
    # -------- spinner/status colors --------
    def _start_spinner(self):
        self._spinner_idx = 0
        self._set_refresh_color(self.t["PRIMARY"])
        self._spin()

    def _spin(self):
        try:
            self.refresh_btn.config(text=self.spinner_frames[self._spinner_idx % len(self.spinner_frames)])
            self._spinner_idx += 1
            self.spinner_job = self.after(90, self._spin)
        except Exception:
            pass

    def _stop_spinner(self):
        if self.spinner_job:
            try:
                self.after_cancel(self.spinner_job)
            except Exception:
                pass
            self.spinner_job = None
        self.refresh_btn.config(text="⟳")

    def _apply_refresh_state_color(self, idle=True, success=True):
        if idle:
            self._set_refresh_color(self.t["ON_SURFACE_VARIANT"])
            return
        if success:
            self._set_refresh_color(self.t["SUCCESS"])
            self.after(900, lambda: self._apply_refresh_state_color(idle=True))
        else:
            self._set_refresh_color(self.t["ERROR"])
            self.after(1400, lambda: self._apply_refresh_state_color(idle=True))

    def _set_refresh_color(self, color):
        try:
            self.refresh_btn.config(fg=color)
        except Exception:
            pass

    # -------- theme & tray --------
    def _apply_theme(self, theme_name):
        if theme_name != self.theme_name:
            self.theme_name = theme_name
            self.settings.set("theme", theme_name)
            self.t = THEMES[theme_name]
            self._update_ui_theme()
            self.theme_btn.config(text=self._theme_icon_for(theme_name))
    
    def _start_tray(self):
        if not SYSTEM_TRAY_AVAILABLE:
            return
        def run_tray():
            menu = (
                TrayItem("Show", self._tray_show),
                TrayItem("Refresh", self._tray_refresh),
                TrayItem("Pin to top", self._tray_toggle_pin),
                TrayItem("Theme", pystray.Menu(
                    TrayItem("Dark", lambda: self._apply_theme("dark")),
                    TrayItem("Light", lambda: self._apply_theme("light")),
                    TrayItem("Minimal", lambda: self._apply_theme("minimal")),
                )),
                pystray.Menu.SEPARATOR,
                TrayItem("Exit", self._tray_exit),
            )
            icon_img = create_premium_icon(64, self.theme_name)
            self.tray_icon = pystray.Icon("MiniRates Pro", icon_img, "MiniRates Pro", menu)
            self.tray_icon.run()
        threading.Thread(target=run_tray, daemon=True).start()
    
    def _tray_show(self):
        self.after(0, self._show_from_tray)
    
    def _tray_refresh(self):
        self.after(0, lambda: self._refresh(manual=True))
    
    def _tray_toggle_pin(self):
        self.after(0, self._toggle_pin)
    
    def _tray_exit(self):
        self._cleanup_and_exit()
    
    def _show_from_tray(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", self.pinned)
    
    def _hide_to_tray(self):
        self.withdraw()
    
    def _exit_app(self):
        self._cleanup_and_exit()
    
    def _cleanup_and_exit(self):
        if self.refresh_job:
            try:
                self.after_cancel(self.refresh_job)
            except Exception:
                pass
        if self.fade_job:
            try:
                self.after_cancel(self.fade_job)
            except Exception:
                pass
        if self.spinner_job:
            try:
                self.after_cancel(self.spinner_job)
            except Exception:
                pass
        if hasattr(self, 'tray_icon') and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            pos = [self.winfo_x(), self.winfo_y()]
            self.settings.set("window_position", pos)
        except Exception:
            pass
        self.destroy()
    
    # -------- selection & copy --------
    def _select_row(self, key):
        """Selects a row and highlights it."""
        t = self.t
        if self.selected_row:
            old_key = self.selected_row
            old_bgc = self.row_bgs[old_key]
            old_rw = self.row_widgets[old_key]
            for p in ("frame", "inner", "title_lbl", "value_lbl", "spark", "trend_lbl"):
                old_rw[p].configure(bg=old_bgc)
        
        self.selected_row = key
        bgc = t["SELECTED"]
        rw = self.row_widgets[key]
        for p in ("frame", "inner", "title_lbl", "value_lbl", "spark", "trend_lbl"):
            rw[p].configure(bg=bgc)

    def _copy_selected(self, event):
        """Copies the selected row's content to clipboard (Title: Value)."""
        if self.selected_row:
            rw = self.row_widgets[self.selected_row]
            text = f"{rw['title_lbl'].cget('text')}: {rw['value_lbl'].cget('text')}".strip()
            self.clipboard_clear()
            self.clipboard_append(text)
            if NOTIFICATIONS_AVAILABLE:
                notification.notify(
                    title="کپی شد",
                    message="ردیف انتخاب‌شده به کلیپ‌بورد کپی شد.",
                    timeout=2
                )

    # -------- window protocol --------
    def fade_in(self, steps=8):
        def do_fade(step):
            if step <= steps:
                alpha = step / steps * 0.96
                try:
                    self.attributes("-alpha", alpha)
                    self.fade_job = self.after(20, lambda: do_fade(step + 1))
                except Exception:
                    pass
        do_fade(0)
    
    def fade_out(self, callback=None):
        def do_fade(step):
            if step >= 0:
                alpha = step / 8 * 0.96
                try:
                    self.attributes("-alpha", alpha)
                    self.fade_job = self.after(20, lambda: do_fade(step - 1))
                except Exception:
                    if callback:
                        callback()
            elif callback:
                callback()
        do_fade(8)

    def protocol_handler(self):
        if SYSTEM_TRAY_AVAILABLE:
            self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        else:
            self.protocol("WM_DELETE_WINDOW", self.destroy)


if __name__ == "__main__":
    try:
        app = UltraCompactRateApp()
        app.protocol_handler()
        app.attributes("-alpha", 0)
        app.after(100, app.fade_in)
        app.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()
