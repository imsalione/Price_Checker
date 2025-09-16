# app/ui/rows.py
# -*- coding: utf-8 -*-
"""
Rates List (Rows) — strict DI theming, flicker-free updates, SparkBar integration.
[... docstring kept the same ...]
"""

from __future__ import annotations
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------- DI (required) ----------
from app.core.di import container  # must be available

# ---------- Optional Events (for publishing wheel scrolls; theming has its own bus) ----------
try:
    from app.core.events import EventBus, WheelScrolled  # type: ignore
except Exception:  # pragma: no cover
    EventBus = Any  # type: ignore
    class WheelScrolled:  # stub
        def __init__(self, area: str, delta: int) -> None: ...

# ---------- Constants ----------
try:
    from app.config import constants as C
except Exception:  # pragma: no cover
    class C:
        ROW_HEIGHT = 28
        ROW_VPAD = 2
        VISIBLE_ROWS = 10
        SPARK_W = 60
        SPARK_H = 12
        SPARK_W_MAX = 480

# ---------- Formatting helpers ----------
try:
    from app.utils.price import (
        # units
        to_toman,
        # compute
        compute_delta_amount, compute_delta_percent, compute_delta_24h_amount,
        # format
        format_thousands_toman, format_compact_toman,
        format_delta_toman, format_delta_percent,
        # digits/parsing
        to_persian_digits, to_english_digits, normalize_text, to_int_irr,
    )

except Exception:  # pragma: no cover
    def short_toman(v: float) -> str: return f"{v:,.0f}"
    def format_full_toman(v: float) -> str: return f"{v:,.0f}"
    def to_persian_digits(s: Any) -> str: return str(s)

# ---------- Tooltip ----------
try:
    from app.ui.tooltip import attach_tooltip
    from app.ui.tooltip import Tooltip as TooltipMgr
except Exception:  # pragma: no cover
    TooltipMgr = Any  # type: ignore
    def attach_tooltip(_w, _t): pass  # no-op if tooltip system is absent

# ---------- SparkBar (stateful; theming via per-row theme dict) ----------
from app.ui.sparkbar import SparkBar


__all__ = ["Rows", "RateRow"]


# ---------- Back-compat scroll facade ----------
class _ScrollFacade:
    def __init__(self, owner: "Rows") -> None:
        self._owner = owner

    def set_on_yview(self, cb: Optional[Callable[[float, float], None]]) -> None:
        self._owner.set_on_yview(cb)

    def smooth_scroll_to(self, target_first: float, duration_ms: int = 240) -> None:
        try:
            cur_first, _ = self._owner._get_yview()
        except Exception:
            cur_first = 0.0
        target_first = max(0.0, min(1.0, float(target_first)))
        steps = max(6, min(24, int(duration_ms / 16)))
        if steps <= 1:
            self._owner.canvas.yview_moveto(target_first)
            self._owner._notify_yview()
            return
        delta = (target_first - cur_first) / float(steps)
        def _tick(i=0, f=cur_first):
            nf = f + delta
            self._owner.canvas.yview_moveto(max(0.0, min(1.0, nf)))
            self._owner._notify_yview()
            if i + 1 < steps:
                self._owner.after(16, _tick, i + 1, nf)
        _tick()

    @property
    def canvas(self) -> tk.Canvas:
        return self._owner.canvas


def _require_di() -> tuple[Any, Any, Dict[str, Any]]:
    theme_srv = container.resolve("theme")
    bus = container.resolve("bus")
    tokens = dict(theme_srv.tokens())
    if not tokens:
        raise RuntimeError("ThemeService.tokens() returned empty mapping.")
    return theme_srv, bus, tokens


class Rows(tk.Frame):
    """Scrollable list of RateRow items implemented with an internal Canvas (stateful)."""

    def __init__(
        self,
        parent,
        *,
        tooltip: Optional[TooltipMgr] = None,
        on_pin_toggle: Optional[Callable[[str, bool], None]] = None,
        **kwargs
    ):
        self._theme_service, self._theme_bus, t = _require_di()

        super().__init__(parent, bg=t.get("SURFACE", "#111"), **kwargs)
        self.t = t
        self._tooltip_mgr: Optional[TooltipMgr] = tooltip
        self._on_pin_toggle: Optional[Callable[[str, bool], None]] = on_pin_toggle

        self._bus: Optional[EventBus] = None
        self._theme_bus_unsub = self._theme_bus.subscribe("ThemeToggled", self._on_theme_toggled)

        self._rows: List[RateRow] = []
        self._row_by_key: Dict[str, RateRow] = {}
        self._last_hovered_row: Optional[RateRow] = None
        self._layout_busy: bool = False
        self.scale: float = 1.0
        self.row_h: int = int(getattr(C, "ROW_HEIGHT", 28))
        self._viewport_h: int = int(self.row_h * int(getattr(C, "VISIBLE_ROWS", 10)))
        self._scroll_enabled: bool = True
        self._wheel_bound: bool = False

        self._on_yview: Optional[Callable[[float, float], None]] = None

        self.canvas = tk.Canvas(
            self,
            bg=self.t.get("SURFACE", "#111"),
            highlightthickness=0,
            bd=0,
            height=self._viewport_h,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.content = tk.Frame(self.canvas, bg=self.t.get("SURFACE", "#111"), highlightthickness=0, bd=0)
        self._content_window = self.canvas.create_window(0, 0, anchor="nw", window=self.content)

        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self.content.bind("<Configure>", self._on_content_configure, add="+")

        for w in (self, self.canvas, self.content):
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")

        self.bind_all("<Control-c>", self._copy_value)
        self.bind_all("<Control-C>", self._copy_value)
        self.bind_all("<Control-Shift-c>", self._copy_title_value)
        self.bind_all("<Control-Shift-C>", self._copy_title_value)

        self.sf = _ScrollFacade(self)

        self._apply_theme(self.t)
        self._update_scrollregion()
        self._auto_enable_wheel()

    def set_on_pin_toggle(self, cb: Optional[Callable[[str, bool], None]]) -> None:
        self._on_pin_toggle = cb

    def set_event_bus(self, bus: EventBus) -> None:
        self._bus = bus

    def update(self, items: List[Dict]) -> None:
        self._layout_busy = True
        try:
            items = list(items or [])

            def key_of(d: Dict[str, Any]) -> str:
                k = (d.get("_id") or d.get("symbol") or "").strip()
                if not k:
                    k = f"{d.get('_category') or ''}:{(d.get('name') or d.get('title') or '').strip()}"
                return k or (d.get("name") or d.get("title") or "")

            existing_map = self._row_by_key
            new_map: Dict[str, RateRow] = {}
            new_rows: List[RateRow] = []

            vpad = int(getattr(C, "ROW_VPAD", 2))

            for index, it in enumerate(items):
                k = key_of(it)
                row = existing_map.get(k)
                if row is None:
                    row = RateRow(
                        self.content,
                        item=it,
                        index=index,
                        tooltip=self._tooltip_mgr,
                        on_hover=self._remember_hover,
                        on_toggle_pin=self._on_toggle_pin_from_row,
                    )
                    row.configure(height=self.row_h)
                    row.pack_propagate(False)
                    row.apply_theme(self.t)
                else:
                    row.set_index(index)
                    row.update_item(it)

                new_map[k] = row
                new_rows.append(row)

            for k, row in list(existing_map.items()):
                if k not in new_map:
                    try:
                        row.destroy()
                    except Exception:
                        pass

            for r in new_rows:
                try:
                    if r.winfo_manager():
                        r.pack_forget()
                    r.pack(fill=tk.X, pady=vpad)
                except Exception:
                    pass

            self._row_by_key = new_map
            self._rows = new_rows

            self._refresh_view()
        finally:
            self._layout_busy = False

    def apply_theme(self, overrides: Optional[Dict[str, Any]] = None) -> None:
        base = dict(self._theme_service.tokens())
        if overrides:
            for k in ("FONT_PRIMARY", "FONT_BOLD", "FONT_SMALL",
                      "ROW_HEIGHT_SCALED", "SPARK_H_SCALED"):
                if k in overrides:
                    base[k] = overrides[k]
        self._apply_theme(base)

    def set_scale(self, s: float) -> None:
        try:
            self.scale = float(s)
        except Exception:
            self.scale = 1.0
        rh = int(self.t.get("ROW_HEIGHT_SCALED", getattr(C, "ROW_HEIGHT", 28)))
        self.row_h = max(18, rh)
        self._refresh_view()

    def set_viewport_height(self, h: int) -> None:
        self._viewport_h = max(60, int(h))
        try:
            self.configure(height=self._viewport_h)
            self.canvas.configure(height=self._viewport_h)
        except Exception:
            pass
        self._auto_enable_wheel()
        self._notify_yview()

    def set_max_height(self, h: int) -> None:
        self.set_viewport_height(h)

    def scroll_to_top(self) -> None:
        try:
            self.canvas.yview_moveto(0.0)
        except Exception:
            pass
        self._notify_yview()

    def set_on_yview(self, callback: Optional[Callable[[float, float], None]]) -> None:
        self._on_yview = callback

    def _apply_theme(self, theme: Dict[str, Any]) -> None:
        self.t = theme or self.t
        try:
            self.configure(bg=self.t["SURFACE"])
            self.canvas.configure(bg=self.t["SURFACE"])
            self.content.configure(bg=self.t["SURFACE"])
        except Exception:
            pass
        self.row_h = int(self.t.get("ROW_HEIGHT_SCALED", getattr(C, "ROW_HEIGHT", 28)))
        if self.row_h < 18:
            self.row_h = 18
        for r in self._rows:
            r.apply_theme(self.t)
        self._refresh_view()

    def _on_theme_toggled(self, *_args, **_kwargs) -> None:
        fresh = dict(self._theme_service.tokens())
        self._apply_theme(fresh)

    def _refresh_view(self) -> None:
        try:
            for r in self._rows:
                r.configure(height=self.row_h)
                r.set_spark_height(int(self.t.get("SPARK_H_SCALED", getattr(C, "SPARK_H", 12))))
                r.request_spark_width_update()
        except Exception:
            pass
        self._update_scrollregion()
        self._auto_enable_wheel()
        self._notify_yview()

    def _update_scrollregion(self) -> None:
        try:
            self.canvas.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _auto_enable_wheel(self) -> None:
        ch = self.content_height()
        need = ch > self._viewport_h + 1
        self.set_scroll_enabled(need)

    def _remember_hover(self, row: "RateRow") -> None:
        self._last_hovered_row = row
        try:
            self.canvas.focus_set()
        except Exception:
            pass
        if self._scroll_enabled:
            self._bind_wheels()

    def set_scroll_enabled(self, enabled: bool) -> None:
        self._scroll_enabled = bool(enabled)
        if not self._scroll_enabled:
            self._unbind_wheels()
        else:
            if self._is_pointer_inside():
                self._bind_wheels()

    def _on_enter(self, _e=None) -> None:
        try:
            self.canvas.focus_set()
        except Exception:
            pass
        if self._scroll_enabled:
            self._bind_wheels()

    def _on_leave(self, _e=None) -> None:
        self.after(10, self._maybe_unbind_if_really_out)

    def _maybe_unbind_if_really_out(self) -> None:
        if not self._is_pointer_inside():
            self._unbind_wheels()

    def _bind_wheels(self) -> None:
        if self._wheel_bound:
            return
        self.canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind("<Button-4>", self._on_btn4, add="+")
        self.canvas.bind("<Button-5>", self._on_btn5, add="+")
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind_all("<Button-4>", self._on_btn4, add="+")
        self.bind_all("<Button-5>", self._on_btn5, add="+")
        self._wheel_bound = True

    def _unbind_wheels(self) -> None:
        if not self._wheel_bound:
            return
        try:
            self.canvas.unbind("<MouseWheel>")
            self.canvas.unbind("<Button-4>")
            self.canvas.unbind("<Button-5>")
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass
        self._wheel_bound = False

    def _on_mousewheel(self, e) -> None:
        delta = int(getattr(e, "delta", 0))
        if delta == 0:
            return
        units = -1 if delta > 0 else 1
        self._yview_scroll(units * 3)
        if self._bus is not None:
            try:
                self._bus.publish(WheelScrolled(area="rows", delta=(+1 if units < 0 else -1)))
            except Exception:
                pass

    def _on_btn4(self, _e=None) -> None:
        self._yview_scroll(-3)
        if self._bus is not None:
            try: self._bus.publish(WheelScrolled(area="rows", delta=-1))
            except Exception: pass

    def _on_btn5(self, _e=None) -> None:
        self._yview_scroll(+3)
        if self._bus is not None:
            try: self._bus.publish(WheelScrolled(area="rows", delta=+1))
            except Exception: pass

    def _yview_scroll(self, units: int) -> None:
        try:
            self.canvas.yview_scroll(units, "units")
        except Exception:
            pass
        self._notify_yview()

    def _on_canvas_configure(self, _e=None) -> None:
        try:
            self.canvas.itemconfigure(self._content_window, width=self.canvas.winfo_width())
        except Exception:
            pass
        self._update_scrollregion()
        self._notify_yview()

    def _on_content_configure(self, _e=None) -> None:
        if getattr(self, "_layout_busy", False):
            return
        self._update_scrollregion()
        self._auto_enable_wheel()
        self._notify_yview()

    def _copy_value(self, _event=None) -> None:
        if self._last_hovered_row:
            try:
                self.clipboard_clear()
                self.clipboard_append(self._last_hovered_row.get_copy_value())
            except Exception:
                pass

    def _copy_title_value(self, _event=None) -> None:
        if self._last_hovered_row:
            try:
                self.clipboard_clear()
                self.clipboard_append(self._last_hovered_row.get_copy_title_value())
            except Exception:
                pass

    def content_height(self) -> int:
        bbox = self.canvas.bbox("all")
        return max(0, (bbox[3] - bbox[1])) if bbox else 0

    def _is_pointer_inside(self) -> bool:
        try:
            x_root = self.winfo_pointerx()
            y_root = self.winfo_pointery()
            x0 = self.winfo_rootx()
            y0 = self.winfo_rooty()
            x1 = x0 + self.winfo_width()
            y1 = y0 + self.winfo_height()
            return (x0 <= x_root <= x1) and (y0 <= y_root <= y1)
        except Exception:
            return False

    def _get_yview(self) -> Tuple[float, float]:
        try:
            return self.canvas.yview()
        except Exception:
            return (0.0, 1.0)

    def _notify_yview(self) -> None:
        if callable(self._on_yview):
            try:
                first, last = self._get_yview()
                self._on_yview(float(first), float(last))
            except Exception:
                pass

    def _on_toggle_pin_from_row(self, item_id: Optional[str], new_state: bool) -> None:
        if not item_id:
            return
        if callable(self._on_pin_toggle):
            try:
                self._on_pin_toggle(item_id, new_state)
            except Exception:
                pass

    def destroy(self) -> None:
        try:
            if hasattr(self, "_theme_bus_unsub") and self._theme_bus_unsub:
                self._theme_bus_unsub()
        except Exception:
            pass
        super().destroy()


class RateRow(tk.Frame):
    """
    A single row in the rates list (stateful).
    Visual layout (RTL-ish):
        [PRICE] [SPARK] [DELTA]        ...spacer...        [PIN] [TITLE]
    """

    def __init__(
        self,
        parent,
        *,
        item: Dict[str, Any],
        index: int,
        tooltip: Optional[TooltipMgr] = None,
        on_hover: Optional[Callable[["RateRow"], None]] = None,
        on_toggle_pin: Optional[Callable[[Optional[str], bool], None]] = None,
    ):
        self.item = dict(item or {})
        self._index = int(index)
        self._on_hover = on_hover
        self._tooltip_mgr = tooltip
        self._on_toggle_pin_cb = on_toggle_pin

        self.t: Dict[str, Any] = parent.master.master.t if hasattr(parent, "master") else {}
        self._bg = self._pick_bg(self.t)
        super().__init__(parent, bg=self._bg, highlightthickness=0, bd=0)

        self._font_small = self.t.get("FONT_SMALL", ("", 9))
        self._font_bold = self.t.get("FONT_BOLD", ("", 10, "bold"))
        self._font_primary = self.t.get("FONT_PRIMARY", ("", 10))

        self._accent = tk.Frame(self, width=3, bg=self.t.get("OUTLINE", "#2a2a35"),
                                height=1, highlightthickness=0, bd=0)
        self._accent.pack(side=tk.LEFT, fill=tk.Y)
        self._accent.pack_forget()

        right = tk.Frame(self, bg=self._bg, highlightthickness=0, bd=0)
        right.pack(side=tk.RIGHT, padx=6)

        self._pin_colors = {
            "on":  self.t.get("PRIMARY", "#825DD6"),
            "off": self.t.get("ON_SURFACE_VARIANT", "#9aa0a6"),
        }

        self.pin_label = tk.Label(
            right,
            text=self._pin_icon_text(),
            bg=self._bg,
            fg=self._pin_fg(),
            font=self.t.get("FONT_SMALL", self._font_small),
            cursor="hand2",
            padx=4, pady=0,
            bd=0, relief=tk.FLAT,
            highlightthickness=0,
            highlightbackground=self._bg,
            highlightcolor=self._bg,
            activebackground=self._bg,
            activeforeground=self._pin_fg(),
            takefocus=0,
        )
        self.pin_label.pack(side=tk.RIGHT)
        self.pin_label.bind("<Button-1>", self._toggle_pin, add="+")
        try:
            tip_text = "پین/لغو پین"
            if self._tooltip_mgr and hasattr(self._tooltip_mgr, "attach"):
                self._tooltip_mgr.attach(self.pin_label, tip_text)
            else:
                attach_tooltip(self.pin_label, tip_text)
        except Exception:
            pass

        self.title_label = tk.Label(
            right,
            text=self._title_text(),
            bg=self._bg,
            fg=self.t.get("ON_SURFACE", "#ddd"),
            font=self._font_bold,
            anchor="e",
            highlightthickness=0, bd=0,
            activebackground=self._bg,
        )
        self.title_label.pack(side=tk.RIGHT)

        self._left_cluster = tk.Frame(self, bg=self._bg, highlightthickness=0, bd=0)
        self._left_cluster.pack(side=tk.LEFT, padx=6)

        self.price_lbl = tk.Label(
            self._left_cluster,
            text=self._price_text(),
            bg=self._bg,
            fg=self.t.get("ON_SURFACE", "#ddd"),
            font=self._font_primary,
            padx=4,
            highlightthickness=0, bd=0,
            activebackground=self._bg,
        )
        self.price_lbl.pack(side=tk.LEFT)

        self.spark = tk.Canvas(
            self._left_cluster,
            width=int(self.t.get("SPARK_W_SCALED", getattr(C, "SPARK_W", 60))),
            height=int(self.t.get("SPARK_H_SCALED", getattr(C, "SPARK_H", 12))),
            bg=self._bg,
            highlightthickness=0,
            bd=0,
        )
        self.spark.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        themed = dict(self.t)
        themed["SPARK_BG"] = self._bg
        themed["ROW_BG"] = self._bg
        self._sparkbar = SparkBar(self.spark, themed, tooltip=self._tooltip_mgr)

        self._spark_cfg_after: Optional[str] = None
        def _debounced_refresh(_e=None):
            if self._spark_cfg_after:
                try:
                    self.after_cancel(self._spark_cfg_after)
                except Exception:
                    pass
            self._spark_cfg_after = self.after(16, self._sparkbar.refresh)
        self.spark.bind("<Configure>", _debounced_refresh, add="+")

        delta_txt, is_up = self._delta_text_and_dir()
        self.delta_lbl = tk.Label(
            self._left_cluster,
            text=delta_txt,
            bg=self._bg,
            fg=self.t.get("SUCCESS", "#22d67e") if is_up else self.t.get("ERROR", "#ff6b6b"),
            font=self._font_small,
            padx=4,
            anchor="w",
            highlightthickness=0, bd=0,
            activebackground=self._bg,
        )
        self.delta_lbl.pack(side=tk.LEFT)

        tip = self._build_tooltip_text()
        if tip:
            if self._tooltip_mgr and hasattr(self._tooltip_mgr, "attach"):
                try:
                    self._tooltip_mgr.attach(self.price_lbl, tip)
                except Exception:
                    attach_tooltip(self.price_lbl, tip)
            else:
                attach_tooltip(self.price_lbl, tip)

        for w in (
            self, right, self.pin_label, self.title_label,
            self._left_cluster, self.spark, self.delta_lbl, self.price_lbl
        ):
            w.bind("<Enter>", lambda _e, me=self: (self._on_hover and self._on_hover(me), self._hover_on()), add="+")
            w.bind("<Leave>", lambda _e, me=self: self._hover_off(), add="+")

        self._spark_resize_after: Optional[str] = None
        for w in (self, self._left_cluster, self.price_lbl, self.delta_lbl):
            w.bind("<Configure>", self._on_any_configure, add="+")
        self._render_spark_initial()
        self.after(1, self._update_spark_width)

    # -------- public --------
    def apply_theme(self, theme: Dict[str, Any]) -> None:
        self.t = theme or self.t
        self._bg = self._pick_bg(self.t)

        fg = self.t.get("ON_SURFACE", "#ddd")
        ok = self.t.get("SUCCESS", "#22d67e")
        err = self.t.get("ERROR", "#ff6b6b")

        try:
            self.configure(bg=self._bg)
            self._accent.configure(bg=self.t.get("OUTLINE", "#2a2a35"))
            for w in (self.price_lbl, self.title_label, self.delta_lbl, self.pin_label, self.spark, self._left_cluster):
                w.configure(bg=self._bg)

            self._pin_colors = {
                "on":  self.t.get("PRIMARY", "#825DD6"),
                "off": self.t.get("ON_SURFACE_VARIANT", "#9aa0a6"),
            }
            self.pin_label.configure(
                fg=self._pin_fg(),
                font=self.t.get("FONT_SMALL", ("", 9)),
                activebackground=self._bg,
                activeforeground=self._pin_fg(),
                highlightbackground=self._bg,
                highlightcolor=self._bg,
            )
            self.title_label.configure(fg=fg, font=self.t.get("FONT_BOLD", ("", 10, "bold")), activebackground=self._bg)
            is_up = self._delta_text_and_dir()[1]
            self.delta_lbl.configure(fg=(ok if is_up else err), font=self.t.get("FONT_SMALL", ("", 9)), activebackground=self._bg)
            self.price_lbl.configure(fg=fg, font=self.t.get("FONT_PRIMARY", ("", 10)), activebackground=self._bg)
            self.spark.configure(height=int(self.t.get("SPARK_H_SCALED", getattr(C, "SPARK_H", 12))))
        except Exception:
            pass

        themed = dict(self.t)
        themed["SPARK_BG"] = self._bg
        themed["ROW_BG"] = self._bg
        try:
            self._sparkbar.update_theme(themed)
        except Exception:
            pass

        self._sparkbar.refresh()
        self.request_spark_width_update()

    def set_index(self, idx: int) -> None:
        self._index = int(idx)
        self._bg = self._pick_bg(self.t)
        try:
            self.configure(bg=self._bg)
            for w in (self.price_lbl, self.title_label, self.delta_lbl, self.pin_label, self.spark, self._left_cluster):
                w.configure(bg=self._bg, activebackground=self._bg if hasattr(w, "configure") else None)
        except Exception:
            pass
        themed = dict(self.t)
        themed["SPARK_BG"] = self._bg
        themed["ROW_BG"] = self._bg
        try:
            self._sparkbar.update_theme(themed)
        except Exception:
            pass
        self.request_spark_width_update()

    def update_item(self, new_item: Dict[str, Any]) -> None:
        self.item = dict(new_item or {})
        try:
            self.title_label.configure(text=self._title_text())
            self.price_lbl.configure(text=self._price_text())
            self._refresh_pin_icon()
            self.pin_label.configure(fg=self._pin_fg(), activeforeground=self._pin_fg())
            delta_txt, is_up = self._delta_text_and_dir()
            self.delta_lbl.configure(text=delta_txt, fg=self.t.get("SUCCESS", "#22d67e") if is_up else self.t.get("ERROR", "#ff6b6b"))
        except Exception:
            pass

        tip = self._build_tooltip_text()
        if tip:
            try:
                if self._tooltip_mgr and hasattr(self._tooltip_mgr, "attach"):
                    self._tooltip_mgr.attach(self.price_lbl, tip)
                else:
                    attach_tooltip(self.price_lbl, tip)
            except Exception:
                pass

        series_new = self._coerce_series(self.item.get("history"))
        times_new  = self._coerce_times(self.item.get("times"), len(series_new))
        self._update_spark_statefully(series_new, times_new)
        self.request_spark_width_update()

    def get_copy_value(self) -> str:
        return self._price_text()

    def get_copy_title_value(self) -> str:
        return f"{self._title_text()}: {self._price_text()}"

    def set_spark_height(self, h: int) -> None:
        try:
            self.spark.configure(height=max(8, int(h)))
            self._sparkbar.refresh()
        except Exception:
            pass
        self.request_spark_width_update()

    def request_spark_width_update(self) -> None:
        self._throttle_spark_width_recompute()

    # -------- internals --------
    def _hover_on(self) -> None:
        try:
            hover_bg = self.t.get("SURFACE_VARIANT") or self._bg
            self.configure(bg=hover_bg)
            for w in (self.price_lbl, self.title_label, self.delta_lbl, self.pin_label, self.spark, self._left_cluster):
                w.configure(bg=hover_bg, activebackground=hover_bg if hasattr(w, "configure") else None)
            self.pin_label.configure(activeforeground=self._pin_fg())
            self._accent.pack(side=tk.LEFT, fill=tk.Y)
        except Exception:
            pass

    def _hover_off(self) -> None:
        try:
            self.configure(bg=self._bg)
            for w in (self.price_lbl, self.title_label, self.delta_lbl, self.pin_label, self.spark, self._left_cluster):
                w.configure(bg=self._bg, activebackground=self._bg if hasattr(w, "configure") else None)
            self.pin_label.configure(activeforeground=self._pin_fg())
            self._accent.pack_forget()
        except Exception:
            pass

    def _pin_fg(self) -> str:
        return self._pin_colors["on"] if bool(self.item.get("pinned")) else self._pin_colors["off"]

    def _pick_bg(self, theme: Dict[str, Any]) -> str:
        odd = theme.get("ROW_ODD", theme.get("SURFACE", "#111"))
        even = theme.get("ROW_EVEN", theme.get("SURFACE", "#111"))
        return odd if (self._index % 2 == 0) else even

    def _title_text(self) -> str:
        title = str(self.item.get("title") or self.item.get("name") or "—").strip()
        try:
            return to_persian_digits(title)
        except Exception:
            return title

    def _price_text(self) -> str:
        s = self.item.get("price_str")
        if not s:
            try:
                v = float(self.item.get("price"))
                s = short_toman(v)
            except Exception:
                s = "—"
        try:
            return to_persian_digits(s)
        except Exception:
            return s

    def _delta_text_and_dir(self) -> Tuple[str, bool]:
        ds = self.item.get("delta_str")
        is_up = bool(self.item.get("delta_is_up"))
        if not ds:
            return ("", is_up)
        s = str(ds).strip()
        if s in {"", "±0", "+0", "-0", "0", "0 تومان", "+0 تومان", "-0 تومان"}:
            return ("", is_up)
        try:
            return (to_persian_digits(s), is_up)
        except Exception:
            return (s, is_up)

    def _build_tooltip_text(self) -> str:
        full = self.item.get("full_price")
        time = self.item.get("updated_at")
        pct = self.item.get("delta_pct_str")
        pieces = []
        if full is not None:
            try:
                pieces.append(format_full_toman(float(full)))
            except Exception:
                pass
        if time:
            pieces.append(f"Refreshed in: {time}")
        if pct:
            pieces.append(f"تغییر: {pct}")
        try:
            return " · ".join([to_persian_digits(p) for p in pieces]) or ""
        except Exception:
            return " · ".join(pieces) or ""

    # ---- Pin helpers ----
    def _pin_icon_text(self) -> str:
        """Icon based on current pinned state."""
        return "📌" if bool(self.item.get("pinned")) else "📌"

    def _refresh_pin_icon(self) -> None:
        try:
            self.pin_label.configure(text=self._pin_icon_text())
        except Exception:
            pass

    def _item_id(self) -> Optional[str]:
        _id = (self.item.get("_id") or "").strip()
        if _id:
            return _id
        sym = (self.item.get("symbol") or "").strip()
        if sym:
            return sym
        cat = (self.item.get("_category") or "").strip()
        name = (self.item.get("name") or self.item.get("title") or "").strip()
        if cat and name:
            return f"{cat}:{name}"
        return None

    def _toggle_pin(self, _e=None) -> None:
        new_state = not bool(self.item.get("pinned"))
        self.item["pinned"] = new_state
        self._refresh_pin_icon()
        try:
            self.pin_label.configure(fg=self._pin_fg(), activeforeground=self._pin_fg())
        except Exception:
            pass
        item_id = self._item_id()
        if callable(self._on_toggle_pin_cb):
            try:
                self._on_toggle_pin_cb(item_id, new_state) 
            except Exception:
                pass

    # ---- Spark helpers ----
    def _render_spark_initial(self) -> None:
        try:
            series = self._coerce_series(self.item.get("history"))
            times  = self._coerce_times(self.item.get("times"), len(series))
            self._sparkbar.set_data(series, times)
            self._sparkbar.refresh()
        except Exception:
            pass

    def _update_spark_statefully(self, series_new: List[int], times_new: List[str]) -> None:
        try:
            series_old = getattr(self, "_series_old", None)
            times_old  = getattr(self, "_times_old", None)
            if not series_old or len(series_new) != len(series_old):
                self._sparkbar.set_data(series_new, times_new)
                self._sparkbar.refresh()
            else:
                rolled = (series_new[:-1] == series_old[1:]) and (times_new[:-1] == times_old[1:])
                if rolled:
                    self._sparkbar.append_point(
                        series_new[-1] if series_new else None,
                        times_new[-1] if times_new else ""
                    )
                    self._sparkbar.refresh()
                else:
                    self._sparkbar.set_data(series_new, times_new)
                    self._sparkbar.refresh()
            self._series_old, self._times_old = series_new, times_new
        except Exception:
            try:
                self._sparkbar.set_data(series_new, times_new)
                self._sparkbar.refresh()
                self._series_old, self._times_old = series_new, times_new
            except Exception:
                pass

    def _on_any_configure(self, _e=None) -> None:
        self._throttle_spark_width_recompute()

    def _throttle_spark_width_recompute(self) -> None:
        if getattr(self, "_spark_resize_after", None) is not None:
            try:
                self.after_cancel(self._spark_resize_after)
            except Exception:
                pass
        self._spark_resize_after = self.after(16, self._update_spark_width)

    def _update_spark_width(self) -> None:
        self._spark_resize_after = None
        try:
            self.update_idletasks()
            lc_w = max(0, int(self._left_cluster.winfo_width()))
            pw   = max(0, int(self.price_lbl.winfo_width()))
            dw   = max(0, int(self.delta_lbl.winfo_width()))
            padding = 16
            avail = lc_w - pw - dw - padding
            min_w = max(60, int(getattr(C, "SPARK_W", 60)))
            max_w = int(getattr(C, "SPARK_W_MAX", 480))
            target_w = max(min_w, min(max_w, int(avail)))
            if target_w <= 0:
                return
            self.spark.configure(width=target_w)
            self._sparkbar.refresh()
        except Exception:
            pass

    @staticmethod
    def _coerce_series(hist) -> List[int]:
        if not hist:
            return []
        out: List[int] = []
        for v in hist:
            try:
                out.append(int(round(float(v))))
            except Exception:
                out.append(0)
        return out

    @staticmethod
    def _coerce_times(times, n: int) -> List[str]:
        if not times or not isinstance(times, list):
            return [""] * n
        t = [str(x) if x is not None else "" for x in times]
        if len(t) < n:
            t = ([""] * (n - len(t))) + t
        elif len(t) > n:
            t = t[-n:]
        return t
