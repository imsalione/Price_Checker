# app/services/theme_service.py
# -*- coding: utf-8 -*-
"""
ThemeService: central theme state + event publishing.

Responsibilities
----------------
- Hold current theme name and tokens (dict).
- Persist choice via SettingsManager.
- Publish ThemeToggled(theme_name) on change so UI components can react.
- Provide a simple API: current_name(), tokens(), set_theme(name), toggle().

Usage
-----
from app.core.di import container
svc = container.resolve("theme")        # if registered in DI
svc.toggle()                            # will publish ThemeToggled(...)
tokens = svc.tokens()

Notes
-----
- Depends on EventBus and optionally SettingsManager (via DI).
"""

from __future__ import annotations
from typing import Dict, Optional

from app.core.events import EventBus, ThemeToggled
from app.config.themes import get_theme, next_theme_name, DEFAULT_THEME
from app.core.di import container


class ThemeService:
    """Central theme manager (event-driven)."""

    def __init__(self, bus: EventBus, default_theme: Optional[str] = None) -> None:
        self.bus = bus
        # lazy deps
        self._settings = None  # SettingsManager
        # state
        self._name: str = (default_theme or DEFAULT_THEME)
        self._tokens: Dict[str, object] = get_theme(self._name)

        # initialize from settings if possible
        try:
            self._settings = container.resolve("settings")
            name = getattr(self._settings, "theme_name", None)
            if callable(name):
                s = name()
                if s:
                    self._name = s
                    self._tokens = get_theme(self._name)
        except Exception:
            pass

    # ---------- public ----------
    def current_name(self) -> str:
        return self._name

    def tokens(self) -> Dict[str, object]:
        return self._tokens

    def set_theme(self, name: str) -> None:
        """Set specific theme by name and publish."""
        new_name = (name or "").strip().lower() or DEFAULT_THEME
        if new_name == self._name:
            return
        self._name = new_name
        self._tokens = get_theme(self._name)
        # persist
        try:
            if self._settings and hasattr(self._settings, "set_theme_name"):
                self._settings.set_theme_name(self._name)
        except Exception:
            pass
        # notify
        try:
            self.bus.publish(ThemeToggled(theme_name=self._name))
        except Exception:
            pass

    def toggle(self) -> str:
        """Cycle to the next theme in THEME_ORDER and publish ThemeToggled."""
        nxt = next_theme_name(self._name)
        self.set_theme(nxt)
        return self._name
