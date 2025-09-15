# app/ui/header.py
# -*- coding: utf-8 -*-
"""
HeaderBar — source selector + realtime search for MiniRates.

Features
--------
- Source selector: AlanChand | TGJU | Both
- Realtime search: filters visible rows by name/title/symbol
- DI-friendly theming (accepts token dict from Window)
- Stateless toward networking: emits callbacks to Window

Constructor
----------
HeaderBar(parent, *,
          theme: dict,
          on_source_change: Callable[[str], None],
          on_search_change: Callable[[str], None],
          tooltip: Optional[Tooltip])

Public API
---------
- set_theme(theme_dict): apply colors/fonts/metrics from tokens
- set_fonts(family: str): optional font family re-apply
- set_scale(scale: float): optional sizing adjustments
- set_source(value: str): programmatic source set (alan|tgju|both)
- get_source() -> str
- set_query(text: str)
- get_query() -> str
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, Any

class HeaderBar(tk.Frame):
    def __init__(
        self,
        parent,
        *,
        theme: Dict[str, Any],
        on_source_change: Callable[[str], None],
        on_search_change: Callable[[str], None],
        tooltip=None,
    ):
        self.t = dict(theme or {})
        super().__init__(parent, bg=self.t.get("SURFACE", "#1a1a22"), highlightthickness=0, bd=0)

        self._on_source_change = on_source_change
        self._on_search_change = on_search_change
        self._tooltip = tooltip

        # State
        self._scale = 1.0
        self._source_var = tk.StringVar(value="both")
        self._query_var  = tk.StringVar(value="")

        # Layout: [Right cluster: source] .... [Left cluster: search]
        wrap = tk.Frame(self, bg=self.t.get("SURFACE", "#1a1a22"), highlightthickness=0, bd=0)
        wrap.pack(fill=tk.X, pady=4, padx=6)

        right = tk.Frame(wrap, bg=self.t.get("SURFACE", "#1a1a22"))
        right.pack(side=tk.RIGHT)

        left = tk.Frame(wrap, bg=self.t.get("SURFACE", "#1a1a22"))
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ---- Source selector (compact segmented buttons) ----
        seg = tk.Frame(right, bg=self.t.get("SURFACE", "#1a1a22"))
        seg.pack(side=tk.RIGHT)

        def _mk_btn(text: str, val: str):
            btn = tk.Label(
                seg, text=text, cursor="hand2",
                bg=self._seg_bg(val), fg=self._seg_fg(val),
                padx=8, pady=2, bd=0, highlightthickness=0,
                font=self.t.get("FONT_SMALL", ("", 9))
            )
            btn.bind("<Button-1>", lambda _e, v=val: self._on_pick_source(v))
            if self._tooltip and hasattr(self._tooltip, "attach"):
                self._tooltip.attach(btn, f"منبع: {text}")
            return btn

        self._btn_alan = _mk_btn("AlanChand", "alanchand")
        self._btn_tgju = _mk_btn("TGJU", "tgju")
        self._btn_both = _mk_btn("Both", "both")

        # Tiny spacing + subtle outline via pad frames
        for i, b in enumerate((self._btn_alan, self._btn_tgju, self._btn_both)):
            b.pack(side=tk.LEFT)
            if i != 2:
                pad = tk.Frame(seg, width=1, height=1, bg=self.t.get("OUTLINE", "#2a2a35"))
                pad.pack(side=tk.LEFT, fill=tk.Y, padx=2)

        # ---- Search (Entry with real-time callback) ----
        search_wrap = tk.Frame(left, bg=self.t.get("SURFACE", "#1a1a22"))
        search_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._search_entry = tk.Entry(
            search_wrap,
            textvariable=self._query_var,
            bg=self.t.get("SURFACE", "#1a1a22"),
            fg=self.t.get("ON_SURFACE", "#f0f2f5"),
            insertbackground=self.t.get("ON_SURFACE", "#f0f2f5"),
            highlightthickness=1,
            highlightbackground=self.t.get("OUTLINE", "#2a2a35"),
            highlightcolor=self.t.get("PRIMARY", "#00e5c7"),
            relief=tk.FLAT,
            font=self.t.get("FONT_PRIMARY", ("", 10))
        )
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        if self._tooltip and hasattr(self._tooltip, "attach"):
            self._tooltip.attach(self._search_entry, "جستجو در نرخ‌ها (real-time)")

        def _on_type(*_):
            self._notify_search_change()
        self._query_var.trace_add("write", _on_type)

        # Initial visuals
        self._sync_segment_visuals()

    # ---------- public ----------
    def set_theme(self, theme: Dict[str, Any]) -> None:
        self.t = dict(theme or self.t)
        try:
            self.configure(bg=self.t.get("SURFACE", "#1a1a22"))
        except Exception:
            pass
        # Repaint children
        for w in (self,):
            try: w.configure(bg=self.t.get("SURFACE", "#1a1a22"))
            except Exception: pass
        # Entry colors
        try:
            self._search_entry.configure(
                bg=self.t.get("SURFACE", "#1a1a22"),
                fg=self.t.get("ON_SURFACE", "#f0f2f5"),
                insertbackground=self.t.get("ON_SURFACE", "#f0f2f5"),
                highlightbackground=self.t.get("OUTLINE", "#2a2a35"),
                highlightcolor=self.t.get("PRIMARY", "#00e5c7"),
                font=self.t.get("FONT_PRIMARY", ("", 10))
            )
        except Exception:
            pass
        self._sync_segment_visuals()

    def set_fonts(self, family: str) -> None:
        # Window already prepared scaled fonts in theme tokens
        self.set_theme(self.t)

    def set_scale(self, s: float) -> None:
        self._scale = float(max(0.8, min(1.75, s)))
        self.set_theme(self.t)

    def set_source(self, value: str) -> None:
        if value not in ("alanchand", "tgju", "both"):
            value = "both"
        if self._source_var.get() == value:
            return
        self._source_var.set(value)
        self._sync_segment_visuals()
        self._notify_source_change()

    def get_source(self) -> str:
        return self._source_var.get()

    def set_query(self, text: str) -> None:
        self._query_var.set(text or "")

    def get_query(self) -> str:
        return self._query_var.get()

    # ---------- internals ----------
    def _seg_bg(self, val: str) -> str:
        active = (self._source_var.get() == val)
        return (self.t.get("PRIMARY", "#00e5c7") if active else self.t.get("SURFACE", "#1a1a22"))

    def _seg_fg(self, val: str) -> str:
        active = (self._source_var.get() == val)
        return (self.t.get("ON_PRIMARY", "#000") if active else self.t.get("ON_SURFACE", "#f0f2f5"))

    def _sync_segment_visuals(self) -> None:
        try:
            for btn, val in (
                (self._btn_alan, "alanchand"),
                (self._btn_tgju, "tgju"),
                (self._btn_both, "both"),
            ):
                btn.configure(bg=self._seg_bg(val), fg=self._seg_fg(val), font=self.t.get("FONT_SMALL", ("", 9)))
        except Exception:
            pass

    def _on_pick_source(self, val: str) -> None:
        if val != self._source_var.get():
            self._source_var.set(val)
            self._sync_segment_visuals()
            self._notify_source_change()

    def _notify_source_change(self) -> None:
        try:
            self._on_source_change(self._source_var.get())
        except Exception:
            pass

    def _notify_search_change(self) -> None:
        try:
            self._on_search_change(self._query_var.get().strip())
        except Exception:
            pass
