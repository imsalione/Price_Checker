# app/config/themes.py
# -*- coding: utf-8 -*-
"""
Theme tokens for MiniRates.

- Pure data (no logic): each theme is a dict of semantic tokens.
- UI layers (window/rows/footer/widgets) read from these tokens.
- Keep names stable so components can rely on them.

Conventions (must-have keys in every theme):
  SURFACE, SURFACE_VARIANT, BG,
  ON_SURFACE, ON_SURFACE_VARIANT,
  PRIMARY, PRIMARY_VARIANT,
  OUTLINE, SUCCESS, WARNING, ERROR,
  FONT_PRIMARY, FONT_BOLD, FONT_SMALL, FONT_TITLE,
  ROW_ODD, ROW_EVEN, SELECTED

Optional (helpful for charts/micro-visuals):
  SPARK_ACCENT_UP, SPARK_ACCENT_DOWN
"""

from __future__ import annotations
from typing import Dict

# ---------- Dark ----------
_DARK: Dict[str, object] = {
    "NAME": "dark",
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
    "GRADIENT_END":   "#0a0a0f",
    # Fonts (family injected later; sizes adjusted by UI scale)
    "FONT_PRIMARY": ("", 10),
    "FONT_BOLD":    ("", 10, "bold"),
    "FONT_SMALL":   ("", 9),
    "FONT_TITLE":   ("", 12, "bold"),
    # Rows
    "ROW_ODD": "#1a1a22",
    "ROW_EVEN": "#1f1f2a",
    "SELECTED": "#2a2a35",
    # Micro accents (sparklines, deltas)
    "SPARK_ACCENT_UP":   "#22d67e",
    "SPARK_ACCENT_DOWN": "#ff6b6b",
}

# ---------- Light ----------
_LIGHT: Dict[str, object] = {
    "NAME": "light",
    "BG": "#fbfcfe",
    "SURFACE": "#ffffff",
    "SURFACE_VARIANT": "#f6f7f9",
    "PRIMARY": "#0066cc",
    "PRIMARY_VARIANT": "#0052a3",
    "ON_SURFACE": "#1c1e21",
    "ON_SURFACE_VARIANT": "#5a6572",
    "OUTLINE": "#e1e4e8",
    "SUCCESS": "#28a745",
    "WARNING": "#fd7e14",
    "ERROR":   "#dc3545",
    "GRADIENT_START": "#ffffff",
    "GRADIENT_END":   "#f6f7f9",
    "FONT_PRIMARY": ("", 10),
    "FONT_BOLD":    ("", 10, "bold"),
    "FONT_SMALL":   ("", 9),
    "FONT_TITLE":   ("", 12, "bold"),
    "ROW_ODD": "#ffffff",
    "ROW_EVEN": "#f6f7f9",
    "SELECTED": "#e1e4e8",
    "SPARK_ACCENT_UP":   "#28a745",
    "SPARK_ACCENT_DOWN": "#dc3545",
}

# ---------- Minimal ----------
_MINIMAL: Dict[str, object] = {
    "NAME": "minimal",
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
    "ERROR":   "#f87171",
    "GRADIENT_START": "#1e1f26",
    "GRADIENT_END":   "#16171d",
    "FONT_PRIMARY": ("", 10),
    "FONT_BOLD":    ("", 10, "bold"),
    "FONT_SMALL":   ("", 9),
    "FONT_TITLE":   ("", 12, "bold"),
    "ROW_ODD": "#1e1f26",
    "ROW_EVEN": "#25262e",
    "SELECTED": "#2d2e36",
    "SPARK_ACCENT_UP":   "#10b981",
    "SPARK_ACCENT_DOWN": "#f87171",
}

THEMES: Dict[str, Dict[str, object]] = {
    "dark": _DARK,
    "light": _LIGHT,
    "minimal": _MINIMAL,
}

# Order to toggle through (first is default)
THEME_ORDER = ["dark", "light", "minimal"]

DEFAULT_THEME = "dark"


def get_theme(name: str) -> Dict[str, object]:
    """Return a theme dict by name with safe fallback to DEFAULT_THEME."""
    key = (name or "").strip().lower()
    return THEMES.get(key) or THEMES[DEFAULT_THEME]


def next_theme_name(current: str) -> str:
    """Return the next theme name in THEME_ORDER (cyclic)."""
    if not THEME_ORDER:
        return DEFAULT_THEME
    try:
        idx = THEME_ORDER.index((current or "").strip().lower())
    except ValueError:
        idx = -1
    return THEME_ORDER[(idx + 1) % len(THEME_ORDER)]
