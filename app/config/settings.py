# app/config/settings.py
# -*- coding: utf-8 -*-
"""
Persistent settings manager for MiniRates.

Features:
  - Loads/saves a small JSON file with user preferences and window state.
  - Works both in development and when frozen with PyInstaller (.exe).
  - Provides convenient helpers for common settings (theme, window rect, etc.).
"""

from __future__ import annotations
import json
import os
import sys
from typing import Any, Dict, List, Tuple, Optional

from .constants import SETTINGS_FILE, AUTO_REFRESH_MS  # default values live in constants


def _app_dir() -> str:
    """
    Return a writable directory to keep user settings:
      - If frozen by PyInstaller: next to the executable.
      - Else: current working directory (project root during dev).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running from a bundled executable
        return os.path.dirname(sys.executable)
    # Dev mode
    return os.getcwd()


def _settings_path() -> str:
    """Absolute path to the JSON settings file."""
    return os.path.join(_app_dir(), SETTINGS_FILE)


class SettingsManager:
    """Manages application settings, loading from and saving to a JSON file."""

    def __init__(self) -> None:
        # Defaults are minimal and safe; unknown keys in file are preserved on load.
        self.default_settings: Dict[str, Any] = {
            # UI / Theme
            "theme": "dark",
            "ui_scale": 1.0,
            "window_alpha": 0.95,
            "always_on_top": False,

            # Window state
            "window_position": [100, 100],     # [x, y]
            "window_size": [360, 220],         # [w, h]

            # Behavior
            "auto_refresh": True,
            "auto_refresh_ms": int(AUTO_REFRESH_MS),
            "notifications": True,

            # Catalog / pins
            "pinned_ids": [],                  # e.g. ["fx:usd", "gold:seke-emami"]
            "pinned_limit": 10,

            # News / X (Twitter)
            "news_accounts": [],               # e.g. ["Khosoosiat", "Tabnak"]
            "news_visible": False,
        }
        self._path = _settings_path()
        self.settings: Dict[str, Any] = self.load_settings()

    # ---------- load/save ----------
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from disk and overlay onto defaults. Never raises."""
        path = self._path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge loaded onto defaults; unknown keys are kept
                merged = {**self.default_settings, **(loaded or {})}
                return merged
            except (OSError, json.JSONDecodeError):
                pass
        return self.default_settings.copy()

    def save_settings(self) -> None:
        """Persist current settings to disk. Best-effort; failures are ignored."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # ---------- generic API ----------
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting, returning default if missing."""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting and save immediately."""
        self.settings[key] = value
        self.save_settings()
        
    # ---- helpers: catalog sources (optional) ----
    def rate_sources(self) -> list[str]:
        v = self.settings.get("catalog_sources", [])
        if isinstance(v, list) and v:
            return [str(x).strip().lower() for x in v if str(x).strip()]
        return ["alanchand", "tgju"]

    def set_rate_sources(self, sources: list[str]) -> None:
        cleaned = [str(x).strip().lower() for x in (sources or []) if str(x).strip()]
        if not cleaned:
            cleaned = ["alanchand", "tgju"]
        self.set("catalog_sources", cleaned)

    # ---------- helpers: theme ----------
    def theme_name(self) -> str:
        """Return the current theme name."""
        return str(self.settings.get("theme", self.default_settings["theme"]))

    def set_theme_name(self, name: str) -> None:
        """Set and persist the theme name."""
        self.set("theme", str(name or "dark"))

    # ---------- helpers: window rect / alpha / pin ----------
    def window_rect(self) -> Tuple[int, int, int, int]:
        """
        Return (x, y, w, h) from settings (clamped to integers).
        Defaults align with constants / defaults above.
        """
        x, y = self.settings.get("window_position", [100, 100])[:2]
        w, h = self.settings.get("window_size", [360, 220])[:2]
        try:
            return int(x), int(y), int(w), int(h)
        except Exception:
            return 100, 100, 360, 220

    def set_window_rect(self, x: int, y: int, w: int, h: int) -> None:
        """Persist window position and size."""
        self.settings["window_position"] = [int(x), int(y)]
        self.settings["window_size"] = [max(160, int(w)), max(120, int(h))]
        self.save_settings()

    def window_alpha(self) -> float:
        """Return window transparency (0.5..1.0)."""
        try:
            a = float(self.settings.get("window_alpha", 0.95))
            return max(0.5, min(1.0, a))
        except Exception:
            return 0.95

    def set_window_alpha(self, alpha: float) -> None:
        """Set window transparency and clamp it to [0.5, 1.0]."""
        try:
            a = float(alpha)
        except Exception:
            a = 0.95
        self.set("window_alpha", max(0.5, min(1.0, a)))

    def always_on_top(self) -> bool:
        """Return whether the window should be kept always on top."""
        return bool(self.settings.get("always_on_top", False))

    def set_always_on_top(self, value: bool) -> None:
        """Set pin (always-on-top) state."""
        self.set("always_on_top", bool(value))

    # ---------- helpers: refresh / behavior ----------
    def auto_refresh_enabled(self) -> bool:
        return bool(self.settings.get("auto_refresh", True))

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        self.set("auto_refresh", bool(enabled))

    def auto_refresh_ms(self) -> int:
        try:
            return int(self.settings.get("auto_refresh_ms", int(AUTO_REFRESH_MS)))
        except Exception:
            return int(AUTO_REFRESH_MS)

    def set_auto_refresh_ms(self, ms: int) -> None:
        self.set("auto_refresh_ms", max(5_000, int(ms)))

    # ---------- helpers: pins ----------
    def pinned_ids(self) -> List[str]:
        pins = self.settings.get("pinned_ids", [])
        return pins if isinstance(pins, list) else []

    def set_pinned_ids(self, pins: List[str]) -> None:
        if not isinstance(pins, list):
            pins = []
        self.set("pinned_ids", pins)

    def pinned_limit(self) -> int:
        try:
            return max(1, int(self.settings.get("pinned_limit", 10)))
        except Exception:
            return 10

    def set_pinned_limit(self, limit: int) -> None:
        self.set("pinned_limit", max(1, int(limit)))

    # ---------- helpers: news ----------
    def news_accounts(self) -> List[str]:
        acc = self.settings.get("news_accounts", [])
        if not isinstance(acc, list):
            return []
        return [str(x).lstrip("@").strip() for x in acc if str(x).strip()]

    def set_news_accounts(self, accounts: List[str]) -> None:
        cleaned = [str(x).lstrip("@").strip() for x in (accounts or []) if str(x).strip()]
        # Keep at most 5 to reduce API pressure
        self.set("news_accounts", cleaned[:5])

    def news_visible(self) -> bool:
        return bool(self.settings.get("news_visible", False))

    def set_news_visible(self, visible: bool) -> None:
        self.set("news_visible", bool(visible))

    # ---------- helpers: scale ----------
    def ui_scale(self) -> float:
        try:
            s = float(self.settings.get("ui_scale", 1.0))
            return max(0.75, min(1.75, s))
        except Exception:
            return 1.0

    def set_ui_scale(self, scale: float) -> None:
        try:
            s = float(scale)
        except Exception:
            s = 1.0
        self.set("ui_scale", max(0.75, min(1.75, s)))
