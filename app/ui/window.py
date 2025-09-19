# app/ui/window.py
# -*- coding: utf-8 -*-
"""
MiniRates - Main Window (robust layout with grid, search toggle synced with Footer)

- HeaderBar (smart search) is now optional/visible based on footer 🔍 toggle.
- Footer 🔍 toggles HeaderBar on/off and persists the setting.
- Rows constructed with theme + tooltip so per-bar spark tooltips are active.
"""

from __future__ import annotations

import os
import datetime as dt
import tkinter as tk
import inspect
from tkinter import font as tkfont
from typing import Any, Dict, List, Optional, Tuple

# UI components
from app.ui.footer import FooterBar
from app.ui.rows import Rows
from app.ui.news_bar import NewsBar
from app.ui.tooltip import Tooltip
from app.ui.header import HeaderBar

# Config / Settings / Themes
from app.config import constants as C
from app.config.themes import THEMES, get_theme
from app.config.settings import SettingsManager

# DI & Services
from app.core.di import container
from app.services.price_service import PriceService
from app.services.cache import get_catalog_cached_or_fetch
from app.services.catalog import build_display_lists, pin_item, unpin_item

# Events
from app.core.events import (
    EventBus, RefreshRequested,
    PricesRefreshed, NewsUpdated, NewsVisibilityToggled, ThemeToggled,
)

# Enrichment utils
from app.services.baselines import DailyBaselines
from app.utils.price import short_toman
from app.utils.price import to_persian_digits

# Spark roll fallback
try:
    from app.ui.sparkbar import roll_fixed_window
    from app.ui.rows import Rows
except Exception:  # pragma: no cover
    def roll_fixed_window(series, times, *, k=10, new_value=None, new_time=None):
        s = list(series or []); t = list(times or [])
        while len(s) < k: s.insert(0, None)
        while len(t) < k: t.insert(0, None)
        if len(s) > k: s = s[-k:]
        if len(t) > k: t = t[-k:]
        if (new_value is not None) or (new_time is not None):
            s = (s + [new_value])[-k:]; t = (t + [new_time])[-k:]
        return s, t


BRIGHTNESS_MIN, BRIGHTNESS_MAX = 0.35, 1.00
BRIGHTNESS_STEP = 0.05


class MiniRatesWindow(tk.Tk):
    """Main application window (event-driven, responsive, DI-themed)."""

    def __init__(self, *, bus: EventBus, settings: SettingsManager) -> None:
        super().__init__()

        # ---------- Early flags ----------
        self._ui_built: bool = False
        self._in_rows_scroll: bool = False
        self._in_rows_scroll_after_id = None
        self._viewport_after_id = None
        self._last_avail_height: Optional[int] = None
        self._rows_scroll_enabled: Optional[bool] = None

        # ---------- Bus & Settings ----------
        self.bus = bus
        self.settings = settings

        # ---------- Theme tokens ----------
        self.theme_svc = None
        try:
            self.theme_svc = container.try_resolve("theme")
        except Exception:
            pass

        if self.theme_svc:
            try:
                self.theme_name: str = self.theme_svc.current_name()
                self.t: Dict[str, Any] = dict(self.theme_svc.tokens())
            except Exception:
                self.theme_name = self.settings.theme_name()
                self.t = self._get_theme(self.theme_name)
        else:
            self.theme_name: str = self.settings.theme_name()
            self.t: Dict[str, Any] = self._get_theme(self.theme_name)

        # ---------- Responsive scale ----------
        self.base_w = int(getattr(C, "WIN_W", 360))
        self.base_h = int(getattr(C, "WIN_H", 220))
        self.scale: float = float(self.settings.ui_scale())
        self._last_scaled: Optional[float] = None

        # ---------- Histories for spark/delta ----------
        self._histories: Dict[str, List[int]] = {}
        self._time_hist: Dict[str, List[str]] = {}

        # ---------- Native window basics ----------
        self.title("MiniRates")
        self.configure(bg=self.t.get("SURFACE", "#1a1a22"))
        self._set_window_icon()

        # Alpha & Always-on-top
        try: self.attributes("-alpha", float(self.settings.window_alpha()))
        except Exception: pass
        try: self.wm_attributes("-topmost", bool(self.settings.always_on_top()))
        except Exception: pass

        # Resizability & min size
        try: self.resizable(bool(getattr(C, "RESIZABLE", True)), bool(getattr(C, "RESIZABLE", True)))
        except Exception: pass
        try: self.minsize(int(getattr(C, "MIN_W", 320)), int(getattr(C, "MIN_H", 200)))
        except Exception: pass

        # ---------- UI state ----------
        self._search_query: str = ""
        self._source_mode: str = "both"  # alanchand | tgju | both
        self._all_items_cache: List[Dict[str, Any]] = []

        # Search visibility (persisted with backward compatibility)
        self.search_visible: bool = self._get_search_visible_initial()

        # ---------- Restore geometry ----------
        self._last_saved_geom: Optional[Tuple[int, int, int, int]] = None
        self._apply_geometry_from_settings()

        # ---------- Services ----------
        self.baselines = DailyBaselines()

        # Refresh schedule
        self.auto_refresh_ms: int = int(self.settings.auto_refresh_ms())
        self.refresh_job: Optional[str] = None
        self._is_loading: bool = False

        # News state
        self.news_enabled: bool = bool(self.settings.news_visible())
        self.news_failed_once: bool = False

        # Tooltip (shared manager for whole window)
        self.tooltip = Tooltip(self, self.t)

        # ---------- Build UI ----------
        self._build_ui()

        # Fonts
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        except Exception:
            pass

        # ---------- Key bindings ----------
        self.bind("<Escape>", lambda _e: self._hide_to_tray())
        self.bind("<Control-q>", lambda _e: self._quit_app())
        self.bind("<Control-r>", lambda _e: self._on_refresh_click())
        self.bind("<F2>", lambda _e: self._toggle_always_on_top())

        # Persist geometry + scale + viewport
        self.bind("<Configure>", self._on_configure)

        # Rows scroll → Back-to-top + throttle
        try:
            if hasattr(self.rows, "sf") and hasattr(self.rows.sf, "set_on_yview"):
                self.rows.sf.set_on_yview(self._on_rows_yview)
        except Exception:
            pass

        # Safety: remove any old global wheel bindings
        try: self.unbind_all("<MouseWheel>")
        except Exception: pass
        try:
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

        # Focus canvas on hover (Windows)
        try:
            self.rows.sf.canvas.bind("<Enter>", lambda _e: self.rows.sf.canvas.focus_set(), add="+")
        except Exception:
            pass

        # ---------- DI seed for PriceService ----------
        class _CatalogFacade:
            def fetch(self, *, force_refresh: bool = False):
                return get_catalog_cached_or_fetch(force_refresh=force_refresh)
            def build_view(self, settings):
                return build_display_lists(self.fetch(force_refresh=False), settings)

        try: container.register("settings", lambda: self.settings, override=True)
        except Exception: pass
        try:
            if container.try_resolve("catalog") is None:
                container.register("catalog", lambda: _CatalogFacade(), override=True)
        except Exception:
            pass

        # PriceService with UI-thread dispatcher
        self.price_service = PriceService(self.bus)
        self.price_service.set_dispatcher(self.after)

        # Subscriptions
        self._subscriptions: List[callable] = []
        self._subscriptions.append(self.bus.subscribe(PricesRefreshed, self._on_prices_refreshed))
        self._subscriptions.append(self.bus.subscribe(NewsUpdated, self._on_news_updated))
        self._subscriptions.append(self.bus.subscribe(ThemeToggled, self._on_theme_toggled_evt))

        # Initial refresh
        self.after(300, self._safe_initial_refresh)

        # UI ready → first stable viewport after initial layout
        self._ui_built = True
        self.after_idle(self._update_rows_viewport)

    # ===================== UI =====================
    def _build_ui(self) -> None:
        """Build main layout with grid: Header (optional) | Rows | Bottom(News+Footer)."""
        # Root uses grid (3 rows, 1 column)
        self.root_frame = tk.Frame(self, bg=self.t["SURFACE"], highlightthickness=0, bd=0)
        self.root_frame.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)   # let root_frame expand
        self.grid_columnconfigure(0, weight=1)

        # Inside root_frame, we also use grid for stability
        self.root_frame.grid_rowconfigure(0, weight=0)  # header (optional)
        self.root_frame.grid_rowconfigure(1, weight=1)  # rows area expands
        self.root_frame.grid_rowconfigure(2, weight=0)  # bottom area (news+footer)
        self.root_frame.grid_columnconfigure(0, weight=1)

        # Header (smart search) — created only if visible
        self.header: Optional[HeaderBar] = None
        if self.search_visible:
            self._create_header()

        # Rows wrapper (expands)
        self.rows_wrap = tk.Frame(self.root_frame, bg=self.t["SURFACE"], highlightthickness=0, bd=0)
        self.rows_wrap.grid(row=1, column=0, sticky="nsew")
        self.rows_wrap.grid_propagate(True)  # let it expand; we no longer force height

        # Construct Rows WITH theme + tooltip so spark tooltips are active
        self.rows = Rows(self.rows_wrap, tooltip=self.tooltip)
        self.rows.pack(side=tk.TOP, anchor="n", fill=tk.BOTH, expand=True)

        # Post-construction wiring (safe): use the actual setter if available
        if hasattr(self.rows, "set_tooltip"):
            try:
                self.rows.set_tooltip(self.tooltip)
            except Exception:
                pass
        elif hasattr(self.rows, "tooltip"):
            # legacy fallback (kept for backward-compat)
            try:
                setattr(self.rows, "tooltip", self.tooltip)
            except Exception:
                pass

        if hasattr(self.rows, "set_on_pin_toggle"):
            try: self.rows.set_on_pin_toggle(self._on_row_pin_toggle)
            except Exception: pass
        elif hasattr(self.rows, "on_pin_toggle"):
            try: setattr(self.rows, "on_pin_toggle", self._on_row_pin_toggle)
            except Exception: pass

        # Bottom wrap (holds NewsBar (top) + Footer (bottom))
        self.bottom_wrap = tk.Frame(self.root_frame, bg=self.t["SURFACE"], highlightthickness=0, bd=0)
        self.bottom_wrap.grid(row=2, column=0, sticky="ew")
        self.bottom_wrap.grid_propagate(True)

        # Footer
        footer_kwargs = dict(
            theme=self.t,
            show_refresh_button=True,
            on_refresh=self._on_refresh_click,
            on_theme_toggle=self._on_toggle_theme,
            on_back_to_top=self._on_back_to_top,
            on_news_toggle=self._on_toggle_news,
            on_pin_toggle=self._toggle_always_on_top,
            tooltip=self.tooltip,
        )
        try:
            params = inspect.signature(FooterBar.__init__).parameters
            # Legacy brightness popup
            if "on_brightness_change" in params or "get_brightness" in params:
                footer_kwargs.update(
                    on_brightness_change=lambda level: (self.attributes("-alpha", level),
                                                        self.settings.set_window_alpha(level)),
                    get_brightness=lambda: float(self.attributes("-alpha") or 1.0),
                )
            # New hover wheel brightness
            if "on_brightness_wheel" in params:
                footer_kwargs.update(on_brightness_wheel=self._on_brightness_wheel)
            # Sources menu
            if "on_sources_change" in params:
                footer_kwargs.update(on_sources_change=self._on_source_change)
            # Search toggle
            if "on_search_toggle" in params:
                footer_kwargs.update(on_search_toggle=self._on_toggle_search)
        except Exception:
            pass

        self.footer = FooterBar(self.bottom_wrap, **footer_kwargs)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)

        # Reflect initial states on footer
        try: self.footer.set_pin_state(self._get_current_topmost())
        except Exception: pass
        try: self.footer.set_search_active(self.search_visible)
        except Exception: pass

        # NewsBar (optional) ABOVE footer
        self.news_bar: Optional[NewsBar] = None
        if self.news_enabled:
            self._create_news_bar()  # packs TOP inside bottom_wrap, ensures footer stays bottom

        # Sync news color
        self._sync_news_state("ok" if self.news_enabled and not self.news_failed_once
                              else ("error" if self.news_failed_once else "hidden"))

    # ---------- Header helpers ----------
    def _create_header(self) -> None:
        if self.header:
            return
        try:
            self.header = HeaderBar(
                self.root_frame,
                theme=self.t,
                on_source_change=self._on_source_change,   # kept for compat
                on_search_change=self._on_search_change,
                tooltip=self.tooltip,
            )
            self.header.grid(row=0, column=0, sticky="ew")
        except Exception:
            self.header = None

    def _destroy_header(self) -> None:
        if not self.header:
            return
        try:
            self.header.grid_forget()
            self.header.destroy()
        except Exception:
            pass
        self.header = None

    # ================= Theming / Fonts =================
    def _get_theme(self, name: str) -> Dict[str, Any]:
        """Return theme tokens by name with safe fallbacks."""
        try: return dict(get_theme(name))
        except Exception: pass
        if isinstance(THEMES, dict) and name in THEMES: return THEMES[name]
        if isinstance(THEMES, dict) and THEMES:         return next(iter(THEMES.values()))
        return {"SURFACE": "#1a1a22", "ON_SURFACE": "#f0f2f5", "PRIMARY": "#00e5c7",
                "ERROR": "#e74c3c", "SUCCESS": "#28a745", "OUTLINE": "#2a2a35"}

    def _pick_font_family(self) -> str:
        preferred = list(getattr(C, "PREFERRED_FONTS", []))
        for segoe in ("Segoe UI Variable", "Segoe UI"):
            if segoe in preferred:
                preferred.insert(0, preferred.pop(preferred.index(segoe)))
            else:
                preferred.insert(0, segoe)
        try: installed = set(tkfont.families())
        except Exception: installed = set()
        for name in preferred:
            if name in installed: return name
        return "Segoe UI"

    def _apply_font_family(self, family: str) -> None:
        """Apply scaled fonts to theme tokens and propagate to children."""
        base_primary, base_bold, base_small, base_title = 10, 10, 9, 12
        s = max(0.85, min(1.75, float(self.scale)))

        def mk(size: int, weight: str | None = None):
            scaled = max(8, int(round(size * s)))
            return (family, scaled) if weight is None else (family, scaled, weight)

        t = dict(self.t)
        t["FONT_PRIMARY"] = mk(base_primary)
        t["FONT_BOLD"]    = mk(base_bold, "bold")
        t["FONT_SMALL"]   = mk(base_small)
        t["FONT_TITLE"]   = mk(base_title, "bold")
        t["ROW_HEIGHT_SCALED"] = max(22, int(round(getattr(C, "ROW_HEIGHT", 28) * s)))
        t["SPARK_H_SCALED"]    = max(10, int(round(getattr(C, "SPARK_H", 12) * s)))
        self.t = t

        # Apply backgrounds
        try:
            self.configure(bg=self.t["SURFACE"])
            self.root_frame.configure(bg=self.t["SURFACE"])
            self.rows_wrap.configure(bg=self.t["SURFACE"])
            self.bottom_wrap.configure(bg=self.t["SURFACE"])
        except Exception:
            pass

        # Header / Footer / News
        if self.header:
            try:
                self.header.set_theme(self.t)
                self.header.set_fonts(family)
                if hasattr(self.header, "set_scale"):
                    self.header.set_scale(s)
            except Exception:
                pass

        try:
            self.footer.set_theme(self.t)
            self.footer.set_fonts(family)
            if hasattr(self.footer, "set_scale"):
                self.footer.set_scale(s)
        except Exception:
            pass

        try:
            if self.news_bar:
                self.news_bar.set_theme(self.t)
                self.news_bar.set_fonts(family)
        except Exception:
            pass

        # Rows
        try:
            if hasattr(self.rows, "apply_theme"):
                self.rows.apply_theme(self.t)
            if hasattr(self.rows, "set_scale"):
                self.rows.set_scale(s)
            elif hasattr(self.rows, "set_row_height"):
                self.rows.set_row_height(self.t["ROW_HEIGHT_SCALED"])
        except Exception:
            pass

        # Tooltip
        try: self.tooltip.refresh_theme(self.t)
        except Exception: pass

    # ================= Theme events =================
    def _on_theme_toggled_evt(self, evt: ThemeToggled) -> None:
        """React to ThemeToggled: refresh tokens & fonts and sync viewport."""
        try: self.theme_name = evt.theme_name or self.theme_name
        except Exception: pass

        if self.theme_svc:
            try: self.t = dict(self.theme_svc.tokens())
            except Exception: self.t = self._get_theme(self.theme_name)
        else:
            self.t = self._get_theme(self.theme_name)

        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        finally:
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)

    def _on_toggle_theme(self) -> None:
        """Footer toggle: use ThemeService if present; otherwise cycle locally."""
        if self.theme_svc:
            try:
                self.theme_svc.toggle()
                return
            except Exception:
                pass

        names = list(THEMES.keys()) if isinstance(THEMES, dict) else []
        try: i = names.index(self.theme_name)
        except Exception: i = -1
        self.theme_name = names[(i + 1) % len(names)] if names else "dark"
        self.t = self._get_theme(self.theme_name)
        self.settings.set_theme_name(self.theme_name)
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        finally:
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)

    # ================= Brightness via footer wheel =================
    def _on_brightness_wheel(self, steps: int) -> None:
        """Adjust window alpha when the mouse wheel moves over the footer."""
        try: cur = float(self.attributes("-alpha"))
        except Exception: cur = float(self.settings.window_alpha())
        new_alpha = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, cur + (BRIGHTNESS_STEP * float(steps))))
        if abs(new_alpha - cur) < 1e-9:
            return
        try: self.attributes("-alpha", new_alpha)
        except Exception: pass
        self.settings.set_window_alpha(new_alpha)

    # ================= Pin / Always-on-top =================
    def _get_current_topmost(self) -> bool:
        try: return bool(self.attributes("-topmost"))
        except Exception: return bool(self.settings.always_on_top())

    def _toggle_always_on_top(self, force: bool | None = None) -> None:
        """Toggle '-topmost' flag and reflect it in footer + settings."""
        current = self._get_current_topmost()
        new_state = (not current) if force is None else bool(force)
        try: self.wm_attributes("-topmost", new_state)
        except Exception: pass
        self.settings.set_always_on_top(new_state)
        try: self.footer.set_pin_state(new_state)
        except Exception: pass

    # ================= Tray / Close =================
    def _hide_to_tray(self) -> None:
        """Hide window and start tray (if available) for quick restore."""
        try: self.withdraw()
        except Exception: pass
        try:
            tray = container.try_resolve("tray")
            if tray and not tray.is_running():
                tray.start()
        except Exception:
            pass

    def _show_from_tray(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _quit_app(self) -> None:
        """Gracefully stop timers, tray, tooltip, and destroy window."""
        self._cancel_refresh()
        try:
            tray = container.try_resolve("tray")
            if tray and tray.is_running():
                tray.stop()
        except Exception:
            pass
        try: self.tooltip.destroy()
        except Exception: pass
        self.destroy()

    # ================= Rows / Footer helpers =================
    def _on_rows_yview(self, first: float, _last: float) -> None:
        """
        Rows scroll callback (via SmoothFrame):
        - Throttle viewport recalcs while user is actively scrolling.
        - Toggle BackToTop button visibility based on scroll position.
        """
        self._in_rows_scroll = True
        if self._in_rows_scroll_after_id is not None:
            try: self.after_cancel(self._in_rows_scroll_after_id)
            except Exception: pass
        self._in_rows_scroll_after_id = self.after(120, self._clear_rows_scrolling)
        try: self.footer.set_back_top_visible(bool(first > 0.01))
        except Exception: pass

    def _on_row_pin_toggle(self, item_id: Optional[str], new_state: bool) -> None:
        """Handle pin/unpin requests coming from Rows/RateRow."""
        if not item_id:
            return
        changed = False
        try:
            changed, _ = (pin_item if new_state else unpin_item)(self.settings, item_id)
        except Exception:
            changed = False
        if not changed:
            return

        # Rebuild view and refresh rows
        try:
            catalog_data = self._get_catalog_cached() or self._fetch_catalog_data() or {}
            view = build_display_lists(catalog_data, self.settings)
            items: List[Dict[str, Any]] = []
            items.extend(view.get('pinned') or [])
            other = view.get('groups') or view.get('others') or {}
            for cat in ("fx", "gold", "crypto"):
                items.extend(other.get(cat, []) or [])
            if not items and isinstance(view, dict):
                for _k, v in view.items():
                    if isinstance(v, list):
                        items.extend(v)
            items = self._enrich_with_deltas(items)
            self.rows.update(items)
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)
        except Exception:
            pass

    def _clear_rows_scrolling(self) -> None:
        self._in_rows_scroll = False
        self._in_rows_scroll_after_id = None
        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    def _on_back_to_top(self) -> None:
        try:
            if hasattr(self.rows, "sf") and hasattr(self.rows.sf, "smooth_scroll_to"):
                self.rows.sf.smooth_scroll_to(0.0, duration_ms=240)
        except Exception:
            pass

    # ================= Refresh: event-driven =================
    def _safe_initial_refresh(self) -> None:
        """Kick the first refresh and arm the next scheduled one."""
        try:
            self._on_refresh_click()
        finally:
            # اگر تا 1 ثانیه بعد چیزی نیامد، fallback محلی بزن
            def _fallback_if_empty():
                try:
                    # اگه rows پره، کاری نکن
                    has_rows = bool(getattr(self.rows, "_rows", []))
                    if has_rows:
                        return
                    # fallback: کش/کاتالوگ را مستقیم بخوان
                    catalog_data = self._get_catalog_cached() or self._fetch_catalog_data() or {}
                    from app.services.catalog import build_display_lists
                    view = build_display_lists(catalog_data, self.settings)
                    items = []
                    items.extend(view.get("pinned") or [])
                    other = view.get("groups") or view.get("others") or {}
                    for cat in ("fx", "gold", "crypto"):
                        items.extend(other.get(cat, []) or [])
                    items = self._enrich_with_deltas(items)
                    # فیلترهای UI (سورس/سرچ)
                    items = self._apply_ui_filters(items)
                    self._all_items_cache = list(items)
                    self.rows.update(items)
                    if self._ui_built:
                        self.after_idle(self._update_rows_viewport)
                    print("[MiniRates] Fallback filled rows with", len(items), "items.")
                except Exception as e:
                    print("[MiniRates] Fallback failed:", e)
            self.after(1000, _fallback_if_empty)
    
            # برنامه‌ریزی رفرش بعدی مثل قبل
            self._schedule_next_refresh(self.auto_refresh_ms)
    

    def _on_refresh_click(self) -> None:
        """Publish a refresh request and set loading state."""
        if self._is_loading:
            return
        self._is_loading = True
        try: self.footer.set_loading(True)
        except Exception: pass
        self.bus.publish(RefreshRequested(source="ui"))

    def _on_prices_refreshed_done(self) -> None:
        """Reset loading indicators, reschedule, and update clock text."""
        self._is_loading = False
        try: self.footer.set_loading(False)
        except Exception: pass
        self._schedule_next_refresh(self.auto_refresh_ms)
        now = dt.datetime.now().strftime("%H:%M")
        try: self.footer.set_time_text(to_persian_digits(now))
        except Exception: self.footer.set_time_text(now)

    def _schedule_next_refresh(self, delay_ms: int) -> None:
        self._cancel_refresh()
        try: self.refresh_job = self.after(max(500, int(delay_ms)), self._on_refresh_click)
        except Exception: self.refresh_job = None

    def _cancel_refresh(self) -> None:
        if self.refresh_job is not None:
            try: self.after_cancel(self.refresh_job)
            except Exception: pass
            self.refresh_job = None

    # ================= Event handlers =================
    def _on_prices_refreshed(self, evt: PricesRefreshed) -> None:
        raw = list(evt.items or [])
        print("[MiniRates] PricesRefreshed raw:", len(raw))
        items = self._enrich_with_deltas(raw)
        self._all_items_cache = list(items)
        filtered = self._apply_ui_filters(items)
        print("[MiniRates] PricesRefreshed filtered:", len(filtered))
        try:
            self.rows.update(filtered)
        except Exception as e:
            print("[MiniRates] rows.update error:", e)
        if self._ui_built:
            self.after_idle(self._update_rows_viewport)
        self._on_prices_refreshed_done()

    def _on_news_updated(self, evt: NewsUpdated) -> None:
        """Update NewsBar with new items (if visible) and sync footer state."""
        state = "ok" if (evt.items or []) else ("error" if self.news_enabled else "hidden")
        self._sync_news_state(state)
        if not self.news_enabled:
            return
        if not self.news_bar:
            self._create_news_bar()
        if not self.news_bar:
            return

        updated = False
        for meth in ("set_items", "update_items", "render_items", "refresh_with_items"):
            if hasattr(self.news_bar, meth) and callable(getattr(self.news_bar, meth)):
                try:
                    getattr(self.news_bar, meth)(evt.items or [])
                    updated = True
                    break
                except Exception:
                    pass
        if not updated:
            try: setattr(self.news_bar, "_items", evt.items or [])
            except Exception: pass

        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    def _apply_ui_filters(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply UI-level filters on items:
          - source mode (if item contains `source` / `_source`)
          - search query (matches name/title/symbol)
        """
        out = list(items or [])

        # Hint upstream settings/cache for sources
        try:
            if hasattr(self.settings, "set_rate_sources"):
                if self._source_mode == "both":
                    self.settings.set_rate_sources(["alanchand", "tgju"])
                elif self._source_mode == "alanchand":
                    self.settings.set_rate_sources(["alanchand"])
                elif self._source_mode == "tgju":
                    self.settings.set_rate_sources(["tgju"])
        except Exception:
            pass

        # UI source filter
        try:
            if self._source_mode != "both":
                def _match_src(it):
                    s = (it.get("_source") or it.get("source") or "").lower().strip()
                    return (self._source_mode in s) if s else True
                out = [it for it in out if _match_src(it)]
        except Exception:
            pass

        # Search filter
        q = (self._search_query or "").strip().lower()
        if q:
            def _hay(it):
                for k in ("name", "title", "symbol"):
                    v = (it.get(k) or "").lower()
                    if q in v:
                        return True
                return False
            out = [it for it in out if _hay(it)]

        return out

    def _on_source_change(self, mode: str) -> None:
        """
        Handle source selection changes (footer popup / legacy header).
        Persist preference, patch cache._SOURCES, re-apply filters, then refresh.
        """
        self._source_mode = (mode or "both").strip().lower()
        try:
            if hasattr(self.settings, "set_rate_sources"):
                if self._source_mode == "both":
                    self.settings.set_rate_sources(["alanchand", "tgju"])
                else:
                    self.settings.set_rate_sources([self._source_mode])
            import app.services.cache as _cache_mod
            if self._source_mode == "both":
                _cache_mod._SOURCES = ("alanchand", "tgju")
            elif self._source_mode == "alanchand":
                _cache_mod._SOURCES = ("alanchand",)
            elif self._source_mode == "tgju":
                _cache_mod._SOURCES = ("tgju",)
        except Exception:
            pass

        try:
            filtered = self._apply_ui_filters(self._all_items_cache)
            self.rows.update(filtered)
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)
        except Exception:
            pass

        try: self._on_refresh_click()
        except Exception: pass

    def _on_search_change(self, query: str) -> None:
        """Apply search filter on the enriched cached snapshot, without refetching."""
        self._search_query = (query or "").strip()
        try:
            filtered = self._apply_ui_filters(self._all_items_cache)
            self.rows.update(filtered)
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)
        except Exception:
            pass

    # NEW: Footer 🔍 → toggle header visibility
    def _on_toggle_search(self) -> None:
        self.search_visible = not self.search_visible
        self._persist_search_visible(self.search_visible)

        if self.search_visible:
            self._create_header()
        else:
            self._destroy_header()
            # Clear query when hiding search; show unfiltered
            self._search_query = ""
            try:
                filtered = self._apply_ui_filters(self._all_items_cache)
                self.rows.update(filtered)
            except Exception:
                pass

        try: self.footer.set_search_active(self.search_visible)
        except Exception: pass

        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    # ================= Enrichment (Δ & spark history) =================
    def _enrich_with_deltas(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compute deltas + keep a rolling history window per symbol."""
        self.baselines.reset_if_new_day()
        out: List[Dict[str, Any]] = []
        try: K = int(getattr(C, "SPARK_BAR_MAX_COUNT", 30))
        except Exception: K = 30
        K = 10 if K <= 10 else min(64, K)

        for it in (items or []):
            try:
                sym = it.get("symbol") or it.get("title") or "UNKNOWN"
                price = self._coerce_price(it.get("price"))
                base = self.baselines.get_or_set(sym, price)
                delta = float(price - base)
                pct = float((delta / base) * 100.0) if base else 0.0

                it["delta_value"] = delta
                it["delta_pct"] = pct
                it["delta_str"] = self._format_delta_toman(delta)
                it["delta_pct_str"] = self._format_delta_percent(base, delta)
                it["delta_is_up"] = (delta > 0)

                time_label = str(it.get("updated_at") or dt.datetime.now().strftime("%H:%M")).strip()

                item_hist = it.get("history") or []
                item_times = it.get("times") or []

                def _coerce_hist(seq):
                    arr = []
                    for v in (seq or []):
                        try: arr.append(float(v))
                        except Exception: arr.append(None)
                    return arr

                if item_hist and item_times:
                    vals = _coerce_hist(item_hist)
                    times = [str(x) if x is not None else "" for x in (item_times or [])]
                    if len(vals) < K:  vals = ([None] * (K - len(vals))) + vals
                    if len(times) < K: times = ([""] * (K - len(times))) + times
                    if len(vals) > K:  vals = vals[-K:]
                    if len(times) > K: times = times[-K:]
                else:
                    prev_vals = self._histories.get(sym, [])
                    prev_times = self._time_hist.get(sym, [])
                    try:
                        vals, times = roll_fixed_window(prev_vals, prev_times, k=K,
                                                        new_value=price, new_time=time_label)
                    except Exception:
                        s = list(prev_vals or []); t = list(prev_times or [])
                        while len(s) < K: s.insert(0, None)
                        while len(t) < K: t.insert(0, None)
                        if len(s) > K: s = s[-K:]
                        if len(t) > K: t = t[-K:]
                        s = (s + [price])[-K:]; t = (t + [time_label])[-K:]
                        vals, times = s, t

                self._histories[sym] = list(vals)
                self._time_hist[sym] = list(times)
                it["history"] = list(vals)
                it["times"] = list(times)
            except Exception:
                pass
            out.append(it)

        live_syms = {(i.get("symbol") or i.get("title") or "UNKNOWN") for i in out}
        for k in list(self._histories.keys()):
            if k not in live_syms:
                self._histories.pop(k, None)
                self._time_hist.pop(k, None)

        return out

    @staticmethod
    def _coerce_price(v) -> float:
        if v is None: return 0.0
        if isinstance(v, (int, float)): return float(v)
        try: return float(str(v).replace(",", "").replace(" ", ""))
        except Exception: return 0.0

    @staticmethod
    def _format_delta_toman(delta_value: float) -> str:
        sign = "+" if delta_value > 0 else ("-" if delta_value < 0 else "±")
        body = short_toman(abs(delta_value))
        return to_persian_digits(f"{sign}{body}")

    @staticmethod
    def _format_delta_percent(baseline: float, delta_value: float, decimals: int = 1) -> str:
        if not baseline:
            zeros = "0" * decimals
            return to_persian_digits(f"±0.{zeros}٪")
        pct = (delta_value / baseline) * 100.0
        sign = "+" if pct > 0 else ("-" if pct < 0 else "±")
        fmt = f"{{:.{decimals}f}}".format(abs(pct))
        return to_persian_digits(f"{sign}{fmt}٪")

    # ================= News UI helpers =================
    def _create_news_bar(self) -> None:
        """Create NewsBar inside bottom_wrap (above footer)."""
        if self.news_bar:
            return
        try:
            self.news_bar = NewsBar(self.bottom_wrap, usernames=self.settings.news_accounts(), theme=self.t)
            for hook in ("set_on_state", "on_state", "bind_state"):
                if hasattr(self.news_bar, hook) and callable(getattr(self.news_bar, hook)):
                    try:
                        getattr(self.news_bar, hook)(self._on_news_state)
                        break
                    except Exception:
                        pass
            # Pack news at TOP, footer already at BOTTOM in bottom_wrap
            self.news_bar.pack(fill=tk.X, side=tk.TOP)
            # Ensure footer is last in bottom_wrap
            try:
                self.footer.pack_forget()
                self.footer.pack(fill=tk.X, side=tk.BOTTOM)
            except Exception:
                pass
        except Exception:
            self.news_bar = None
            self.news_failed_once = True

    def _destroy_news_bar(self) -> None:
        """Safely remove NewsBar and keep footer pinned to bottom."""
        if not self.news_bar:
            return
        try:
            self.news_bar.pack_forget()
            self.news_bar.destroy()
        except Exception:
            pass
        self.news_bar = None
        try:
            self.footer.pack_forget()
            self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        except Exception:
            pass

    def _on_toggle_news(self) -> None:
        """Footer toggle for news visibility."""
        self.news_enabled = not self.news_enabled
        self.settings.set_news_visible(self.news_enabled)
        self.bus.publish(NewsVisibilityToggled(visible=self.news_enabled))

        if not self.news_enabled:
            self._destroy_news_bar()
            self._sync_news_state("hidden")
            if self._ui_built:
                self.after_idle(self._update_rows_viewport)
            return

        self._create_news_bar()
        self._sync_news_state("loading")
        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    def _on_news_state(self, state: str) -> None:
        self._sync_news_state(state)

    def _sync_news_state(self, state: str) -> None:
        """Reflect news state in footer (e.g., color/badge)."""
        try: self.footer.set_news_state(state)
        except Exception: pass
        self.news_failed_once = (state == "error")

    # ================= Geometry & Responsive =================
    def _apply_geometry_from_settings(self) -> None:
        """Restore window rect (x, y, w, h) and set initial scale."""
        x, y, w, h = self.settings.window_rect()
        try: self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception: self._center_with_size(w, h)
        self._last_saved_geom = (w, h, self.winfo_x(), self.winfo_y())
        self._update_scale_from_size(w, h, force=True)

    def _center_with_size(self, w: int, h: int) -> None:
        """Center the window as a fallback when geometry cannot be restored."""
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            cx = int((sw - w) / 2); cy = int((sh - h) / 3)
            self.geometry(f"{w}x{h}+{cx}+{cy}")
        except Exception:
            self.geometry(f"{w}x{h}+200+120")

    def _on_configure(self, _e=None) -> None:
        """Persist geometry and trigger responsive recalculation."""
        try:
            g = self.geometry()  # "WxH+X+Y"
            wh, x, y = g.split("+")
            w, h = wh.split("x")
            w, h, x, y = int(w), int(h), int(x), int(y)
            cur = (w, h, x, y)
            if cur != self._last_saved_geom:
                self._last_saved_geom = cur
                self.settings.set_window_rect(x, y, w, h)
            self._update_scale_from_size(w, h)
        except Exception:
            pass

        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    def _update_scale_from_size(self, w: int, h: int, force: bool = False) -> None:
        """Compute a UI scale factor from window size and propagate font/layout changes."""
        sw = max(0.4, min(3.0, w / float(self.base_w)))
        sh = max(0.4, min(3.0, h / float(self.base_h)))
        s = min(sw, sh)
        if (not force) and self._last_scaled is not None and abs(s - self._last_scaled) < 0.05:
            return
        self.scale = s
        self._last_scaled = s
        self.settings.set_ui_scale(self.scale)
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        except Exception:
            pass
        if self._ui_built:
            self.after_idle(self._update_rows_viewport)

    def _update_rows_viewport(self) -> None:
        """
        Fit rows to current viewport and toggle scroll if needed.
        With grid layout, available height for rows is rows_wrap.winfo_height().
        """
        if not self._ui_built:
            return

        # Defer while user is actively scrolling
        if self._in_rows_scroll:
            if self._viewport_after_id is not None:
                try: self.after_cancel(self._viewport_after_id)
                except Exception: pass
            self._viewport_after_id = self.after(80, self._update_rows_viewport)
            return

        # Debounce to ~60fps
        if self._viewport_after_id is not None:
            try: self.after_cancel(self._viewport_after_id)
            except Exception: pass
            self._viewport_after_id = None

        def _do():
            try:
                self.update_idletasks()
                avail = int(self.rows_wrap.winfo_height() or 0)
                if avail <= 0:
                    self._viewport_after_id = self.after(50, self._update_rows_viewport)
                    return

                # Inform rows about height (no need to force wrapper height)
                try:
                    if hasattr(self.rows, "set_viewport_height"):
                        self.rows.set_viewport_height(avail)
                    elif hasattr(self.rows, "fit_to_height"):
                        self.rows.fit_to_height(avail)
                    elif hasattr(self.rows, "set_max_height"):
                        self.rows.set_max_height(avail)
                except Exception:
                    pass

                # Enable/disable scroll based on content height
                try:
                    content_h = getattr(self.rows, "content_height", lambda: avail)()
                    should_enable = bool(content_h > avail)
                    if self._rows_scroll_enabled is None or should_enable != self._rows_scroll_enabled:
                        if hasattr(self.rows, "set_scroll_enabled"):
                            self.rows.set_scroll_enabled(should_enable)
                        self._rows_scroll_enabled = should_enable
                except Exception:
                    pass
            finally:
                self._viewport_after_id = None

        self._viewport_after_id = self.after(16, _do)

    # ================= Icon / Logo =================
    def _set_window_icon(self) -> None:
        """Load and set an app icon if available (PNG)."""
        candidates = ["assets/logo.png", "assets/icon.png", "app/assets/logo.png", "app/assets/icon.png"]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    img = tk.PhotoImage(file=p)
                    self._icon_img = img
                    self.iconphoto(True, img)
                    return
                except Exception:
                    continue
        return

    # ================= Data helpers =================
    def _get_catalog_cached(self):
        """Return cached catalog if available (safe)."""
        try: return get_catalog_cached_or_fetch(force_refresh=False)
        except Exception: return {}

    def _fetch_catalog_data(self):
        """Force fetch catalog (safe)."""
        try: return get_catalog_cached_or_fetch(force_refresh=True)
        except Exception: return {}

    # ================= Search visible persistence helpers =================
    def _get_search_visible_initial(self) -> bool:
        """Read search visibility from settings with backward compatibility."""
        # Prefer dedicated methods if present
        if hasattr(self.settings, "search_visible"):
            try:
                return bool(self.settings.search_visible())
            except Exception:
                pass
        # Fall back to generic get
        try:
            return bool(self.settings.get("search_visible", False))
        except Exception:
            return False

    def _persist_search_visible(self, value: bool) -> None:
        """Persist search visibility with backward compatibility."""
        if hasattr(self.settings, "set_search_visible"):
            try:
                self.settings.set_search_visible(bool(value))
                return
            except Exception:
                pass
        try:
            self.settings.set("search_visible", bool(value))
        except Exception:
            pass

    # ================= Run =================
    def run(self) -> None:
        """Start Tk mainloop."""
        self.mainloop()
