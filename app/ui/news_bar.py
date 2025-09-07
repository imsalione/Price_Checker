# app/ui/news_bar.py
# -*- coding: utf-8 -*-
"""
Compact news ticker bar.

Responsibilities:
  - Fetch short news items (e.g., tweets) for given usernames and display them inline.
  - Expose a small, stable API for the main window to control and theme the bar.
  - Report state transitions via a callback: "loading" → "ok" | "error".

Public API:
  - set_on_state(cb: Callable[[str], None])          # cb("loading"|"ok"|"error")
  - set_theme(theme: dict)
  - set_fonts(family: str)
  - set_usernames(usernames: list[str])
  - refresh_now()                                     # triggers fetch and updates UI

Notes:
  - No mouse-wheel handling here (single responsibility).
  - Uses twitter_service if available; otherwise shows empty/placeholder safely.
  - All docstrings are in English by request.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import tkinter as tk
from tkinter import font as tkfont

# Optional helpers for Persian digits (safe fallbacks)
try:
    from app.utils.numbers import to_persian_digits
except Exception:  # pragma: no cover
    def to_persian_digits(s: str) -> str:
        return str(s)

# Attempt to import a twitter service from common project paths
_TWITTER_SVC = None
try:
    from app.services import twitter_service as _TWITTER_SVC  # type: ignore
except Exception:
    try:
        from app.ui import twitter_service as _TWITTER_SVC  # type: ignore
    except Exception:
        _TWITTER_SVC = None


def _format_items_text(items: Sequence[Dict[str, Any]]) -> str:
    """
    Join news items into a compact single-line string.
    Each item should ideally include a 'text' field; time is optional.
    """
    parts: List[str] = []
    for it in (items or []):
        txt = str(it.get("text") or it.get("title") or "").strip()
        t = str(it.get("time") or it.get("created_at") or "").strip()
        if t:
            parts.append(f"{t} — {txt}")
        else:
            parts.append(txt)
    s = "  •  ".join(p for p in parts if p)
    try:
        return to_persian_digits(s)
    except Exception:
        return s


def _safe_fetch(usernames: Sequence[str], limit: int = 6) -> Tuple[List[Dict[str, Any]], Optional[Exception]]:
    """
    Try a few common function names on twitter_service, returning (items, error).
    Expected return shape (flexible): list of dicts with at least 'text' and optionally 'time'.
    """
    if not _TWITTER_SVC or not usernames:
        return ([], None)

    funcs = [
        ("fetch_latest_tweets", {"usernames": usernames, "limit": limit}),
        ("fetch_latest", {"usernames": usernames, "limit": limit}),
        ("get_latest", {"usernames": usernames, "limit": limit}),
        ("get_news", {"usernames": usernames, "limit": limit}),
        ("fetch", {"usernames": usernames, "limit": limit}),
    ]
    for fname, kwargs in funcs:
        try:
            fn = getattr(_TWITTER_SVC, fname, None)
            if callable(fn):
                res = fn(**kwargs)  # type: ignore
                if isinstance(res, (list, tuple)):
                    # normalize to list[dict]
                    out: List[Dict[str, Any]] = []
                    for x in res:
                        if isinstance(x, dict):
                            out.append(x)
                        else:
                            out.append({"text": str(x)})
                    return (out, None)
        except Exception as e:  # continue trying other shapes
            last_err = e
            continue
    try:
        return ([], last_err)  # type: ignore
    except Exception:
        return ([], Exception("No compatible twitter_service found."))


class NewsBar(tk.Frame):
    """
    A minimal, single-line news ticker.

    UI:
      ┌──────────────────────────────────────────┐
      │ [thin top border]                        │
      │ text • text • text …                     │
      └──────────────────────────────────────────┘

    It avoids heavy layouts and keeps the height compact while remaining readable.
    """

    def __init__(
        self,
        parent: tk.Misc,
        usernames: Optional[List[str]] = None,
        theme: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(parent, bg=(theme or {}).get("SURFACE", "#1a1a22"))
        self.t: Dict[str, str] = theme or {}
        self.usernames: List[str] = list(usernames or [])
        self._state_cb: Optional[Callable[[str], None]] = None

        # Fonts
        self.font_text = tkfont.Font(size=9)

        # Thin top border to separate from rows area
        self._separator = tk.Frame(self, height=1, bg=self.t.get("OUTLINE", "#2a2a35"))
        self._separator.pack(fill=tk.X, side=tk.TOP)

        # Content (single, compact label)
        self._lbl = tk.Label(
            self,
            text="",
            bg=self.t.get("SURFACE", "#1a1a22"),
            fg=self.t.get("ON_SURFACE", "#f0f2f5"),
            anchor="w",
            justify="left",
            font=self.font_text,
            padx=6,
            pady=2,
        )
        self._lbl.pack(fill=tk.X, side=tk.TOP)

    # ---------- Public API ----------

    def set_on_state(self, cb: Optional[Callable[[str], None]]) -> None:
        """Register a callback receiving 'loading'|'ok'|'error' after refresh attempts."""
        self._state_cb = cb

    def set_theme(self, theme: Dict[str, str]) -> None:
        """Apply theme colors to the bar."""
        self.t = theme or self.t
        try:
            self.configure(bg=self.t["SURFACE"])
            self._separator.configure(bg=self.t.get("OUTLINE", "#2a2a35"))
            self._lbl.configure(bg=self.t["SURFACE"], fg=self.t["ON_SURFACE"])
        except Exception:
            pass

    def set_fonts(self, family: str) -> None:
        """Apply font family (size remains compact)."""
        try:
            self.font_text.configure(family=family)
            self._lbl.configure(font=self.font_text)
        except Exception:
            pass

    def set_usernames(self, usernames: Sequence[str]) -> None:
        """Update the tracked usernames list."""
        try:
            self.usernames = list(usernames or [])
        except Exception:
            self.usernames = []

    def refresh_now(self) -> None:
        """
        Trigger a refresh; notifies state changes and updates the label text.
        Non-blocking on UI thread (uses `after` for a tiny delay).
        """
        self._notify_state("loading")
        self.after(10, self._do_refresh)

    # ---------- Internals ----------

    def _notify_state(self, state: str) -> None:
        """Push 'loading'|'ok'|'error' to the registered callback (if any)."""
        if self._state_cb:
            try:
                self._state_cb(state)
            except Exception:
                pass

    def _do_refresh(self) -> None:
        """Fetch and render items; set state accordingly."""
        try:
            items, err = _safe_fetch(self.usernames, limit=6)
            if err is not None:
                # Fetch failed → show error state; keep previous text (if any)
                self._notify_state("error")
                return

            text = _format_items_text(items)
            try:
                self._lbl.configure(text=text)
            except Exception:
                pass

            # OK if we could set text (even if empty); caller can color the dot as desired.
            self._notify_state("ok")
        except Exception:
            self._notify_state("error")
