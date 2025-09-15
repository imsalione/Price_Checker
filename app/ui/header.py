# app/ui/header.py
# -*- coding: utf-8 -*-
"""
HeaderBar — minimal smart search only (no sources UI).

What changed vs previous:
- Removed sources dropdown/checkbox UI from the *visual* level, but kept the
  constructor signature for backward compatibility:
      HeaderBar(parent, *, theme, on_source_change, on_search_change, tooltip)
  (on_source_change is accepted but intentionally ignored here.)

- Flat, minimal search box with subtle outline (no rounded corners).
- Auto RTL/LTR justification based on Arabic/Persian Unicode block.
- Persian-friendly typing: when Persian/Arabic characters are present in the
  text, the entry justifies to the RIGHT; otherwise LEFT.

Public API preserved:
    set_theme(theme)
    set_fonts(family)
    set_scale(s)
    set_query(text) / get_query()
    set_source(value) / get_source()   # legacy-compatible no-ops (stateful)
"""

from __future__ import annotations
import re
import tkinter as tk
from typing import Callable, Optional, Dict, Any


_AR_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")  # Arabic & Persian block


class HeaderBar(tk.Frame):
    """
    Top header container that currently provides a single smart search box.

    Args:
        parent: Tk container.
        theme: Theme token dict (colors/fonts).
        on_source_change: Legacy callback (kept for signature compatibility).
        on_search_change: Called with the current query (str) on every change.
        tooltip: Optional Tooltip manager for help text.
    """

    def __init__(
        self,
        parent,
        *,
        theme: Dict[str, Any],
        on_source_change: Callable[[str], None],   # kept for compatibility (unused)
        on_search_change: Callable[[str], None],
        tooltip=None,
    ) -> None:
        self.t = dict(theme or {})
        super().__init__(parent, bg=self.t.get("SURFACE", "#1a1a22"), highlightthickness=0, bd=0)

        # Callbacks (source change is intentionally ignored in this UI)
        self._on_search_change = on_search_change
        self._on_source_change = on_source_change
        self._tooltip = tooltip

        # State
        self._scale = 1.0
        self._q = tk.StringVar(value="")
        self._source_value = "both"  # legacy compatibility state

        # Layout wrapper
        wrap = tk.Frame(self, bg=self.t.get("SURFACE", "#1a1a22"), highlightthickness=0, bd=0)
        wrap.pack(fill=tk.X, pady=6, padx=8)

        left = tk.Frame(wrap, bg=self.t.get("SURFACE", "#1a1a22"))
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor="w")

        # Search box shell (subtle outline, flat)
        self._search_box = tk.Frame(
            left,
            bg=self.t.get("SURFACE_VARIANT", "#20202a"),
            highlightthickness=1,
            highlightbackground=self.t.get("OUTLINE", "#2a2a35"),
            highlightcolor=self.t.get("PRIMARY", "#00e5c7"),
            bd=0,
        )
        self._search_box.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=0)

        # Search entry
        self._search_entry = tk.Entry(
            self._search_box,
            textvariable=self._q,
            relief=tk.FLAT,
            bd=0,
            bg=self.t.get("SURFACE_VARIANT", "#20202a"),
            fg=self.t.get("ON_SURFACE", "#f0f2f5"),
            insertbackground=self.t.get("ON_SURFACE", "#f0f2f5"),
            font=self.t.get("FONT_PRIMARY", ("", 10)),
            justify="left",  # will auto-switch to "right" for Persian/Arabic
        )
        self._search_entry.pack(fill=tk.X, expand=True, padx=10, pady=4)

        # Tooltip (optional)
        if self._tooltip and hasattr(self._tooltip, "attach"):
            self._tooltip.attach(self._search_entry, "جستجوی نرخ‌ها")

        # Notify on change + auto-justify direction
        self._q.trace_add("write", lambda *_: (self._auto_justify(), self._notify_search_change()))
        self._auto_justify()

        # Helpful keybindings (UX niceties, non-intrusive)
        self._search_entry.bind("<Escape>", self._clear_query, add="+")
        self._search_entry.bind("<Control-l>", self._focus_query, add="+")
        self._search_entry.bind("<Control-L>", self._focus_query, add="+")

    # ---------- Public: theming ----------
    def set_theme(self, theme: Dict[str, Any]) -> None:
        """Apply color and font tokens from the theme."""
        self.t = dict(theme or self.t)
        try:
            self.configure(bg=self.t.get("SURFACE", "#1a1a22"))
        except Exception:
            pass
        try:
            self._search_box.configure(
                bg=self.t.get("SURFACE_VARIANT", "#20202a"),
                highlightbackground=self.t.get("OUTLINE", "#2a2a35"),
                highlightcolor=self.t.get("PRIMARY", "#00e5c7"),
            )
            self._search_entry.configure(
                bg=self.t.get("SURFACE_VARIANT", "#20202a"),
                fg=self.t.get("ON_SURFACE", "#f0f2f5"),
                insertbackground=self.t.get("ON_SURFACE", "#f0f2f5"),
                font=self.t.get("FONT_PRIMARY", ("", 10)),
            )
        except Exception:
            pass

    def set_fonts(self, family: str) -> None:
        """Re-apply theme fonts prepared upstream."""
        self.set_theme(self.t)

    def set_scale(self, s: float) -> None:
        """Optional scale hook (kept for compatibility with window)."""
        try:
            self._scale = float(max(0.8, min(1.75, s)))
        except Exception:
            self._scale = 1.0
        # Re-apply to ensure crisp borders/text
        self.set_theme(self.t)

    # ---------- Public: query accessors ----------
    def set_query(self, text: str) -> None:
        """Programmatically set the search query."""
        self._q.set(text or "")

    def get_query(self) -> str:
        """Return the current search query string."""
        return self._q.get()

    # ---------- Legacy stubs (compatibility only) ----------
    def set_source(self, value: str) -> None:
        """
        Keep a local state of selected source for backward compatibility.
        UI no longer provides a source picker here.
        """
        v = (value or "both").strip().lower()
        if v not in ("alanchand", "tgju", "both"):
            v = "both"
        self._source_value = v
        # Intentionally NOT calling self._on_source_change() here.

    def get_source(self) -> str:
        """Return last set source value ('both' by default)."""
        return self._source_value

    # ---------- Internals ----------
    def _auto_justify(self) -> None:
        """
        If the query contains any Arabic/Persian characters, right-justify the text
        to produce a Persian-friendly typing experience; otherwise left-justify.
        """
        txt = self._q.get() or ""
        is_rtl = bool(_AR_PERSIAN_RE.search(txt))
        try:
            self._search_entry.configure(justify=("right" if is_rtl else "left"))
        except Exception:
            pass

    def _notify_search_change(self) -> None:
        """Invoke the external search change callback with the current query."""
        try:
            self._on_search_change(self._q.get().strip())
        except Exception:
            pass

    # Small UX helpers
    def _clear_query(self, _e=None):
        self._q.set("")
        return "break"

    def _focus_query(self, _e=None):
        try:
            self._search_entry.focus_set()
            self._search_entry.select_range(0, tk.END)
        except Exception:
            pass
        return "break"
