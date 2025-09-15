# app/ui/window.py
# -*- coding: utf-8 -*-
"""
MiniRates - Main Window (Event-driven, native title bar, resizable, responsive scaling)

This window:
  - Renders rows + footer (+ optional news bar).
  - Publishes RefreshRequested on manual/auto refresh (no direct data fetching here).
  - Subscribes to:
        • PricesRefreshed(items) -> enrich deltas/spark + rows.update(items)
        • NewsUpdated(items)     -> update news bar (if visible)
        • ThemeToggled(name)     -> re-apply theme and refresh UI
  - Persists geometry, theme, alpha, always-on-top, and news visibility via SettingsManager.

DI theming alignment
--------------------
- Rows is DI-only for theming. We don't pass a `theme` argument:
      self.rows = Rows(self.rows_wrap, tooltip=self.tooltip, on_pin_toggle=...)
- When fonts/scale change, we call rows.apply_theme(self.t) so only font/size
  keys override the DI tokens, keeping colors 100% DI-driven.
- FooterBar/NewsBar still receive theme tokens here for backward compatibility.

Constructor:
    MiniRatesWindow(bus: EventBus, settings: SettingsManager)
"""

from __future__ import annotations

import os
import datetime as dt
import tkinter as tk
import inspect
from tkinter import font as tkfont
from typing import Any, Dict, List, Optional, Tuple

# --- UI components ---
from app.ui.footer import FooterBar
from app.ui.rows import Rows
from app.ui.news_bar import NewsBar
from app.ui.tooltip import Tooltip
from app.ui.header import HeaderBar

# --- Config / Settings / Themes ---
from app.config import constants as C
from app.config.themes import THEMES, get_theme
from app.config.settings import SettingsManager

# --- DI & Services ---
from app.core.di import container
from app.services.price_service import PriceService
from app.services.cache import get_catalog_cached_or_fetch
from app.services.catalog import build_display_lists, pin_item, unpin_item

# --- Events ---
from app.core.events import (
    EventBus, RefreshRequested,
    PricesRefreshed, NewsUpdated, NewsVisibilityToggled, ThemeToggled,
)

# --- Services used locally for enrichment/UI ---
from app.services.baselines import DailyBaselines

# --- Utils ---
from app.utils.formatting import short_toman
from app.utils.numbers import to_persian_digits

# --- Spark roll (upstream roll-10 lock) ---
try:
    # همان utility که SparkBar برای پنجرهٔ ثابت استفاده می‌کند
    from app.ui.sparkbar import roll_fixed_window
except Exception:  # pragma: no cover
    def roll_fixed_window(series, times, *, k=10, new_value=None, new_time=None):
        s = list(series or [])
        t = list(times or [])
        while len(s) < k: s.insert(0, None)
        while len(t) < k: t.insert(0, None)
        if len(s) > k: s = s[-k:]
        if len(t) > k: t = t[-k:]
        if (new_value is not None) or (new_time is not None):
            s = (s + [new_value])[-k:]
            t = (t + [new_time])[-k:]
        return s, t


# Brightness behavior (window alpha)
BRIGHTNESS_MIN = 0.35
BRIGHTNESS_MAX = 1.00
BRIGHTNESS_STEP = 0.05  # per wheel notch


class MiniRatesWindow(tk.Tk):
    def __init__(self, *, bus: EventBus, settings: SettingsManager) -> None:
        super().__init__()

        # ---- Bus & Settings ----
        self.bus = bus
        self.settings = settings

        # ---- ThemeService (Optional) + Theme tokens ----
        self.theme_svc = None
        try:
            self.theme_svc = container.try_resolve("theme")
        except Exception:
            self.theme_svc = None

        if self.theme_svc:
            # Use ThemeService if available
            try:
                self.theme_name: str = self.theme_svc.current_name()
                self.t: Dict[str, Any] = dict(self.theme_svc.tokens())
            except Exception:
                self.theme_name = self.settings.theme_name()
                self.t = self._get_theme(self.theme_name)
        else:
            # fallback to local themes
            self.theme_name: str = self.settings.theme_name()
            self.t: Dict[str, Any] = self._get_theme(self.theme_name)

        # ---- Responsive scale state ----
        self.base_w = int(getattr(C, "WIN_W", 360))
        self.base_h = int(getattr(C, "WIN_H", 220))
        self.scale: float = float(self.settings.ui_scale())
        self._last_scaled: Optional[float] = None

        # Row histories for deltas/sparkbars (local visualization state)
        self._histories: Dict[str, List[int]] = {}
        self._time_hist: Dict[str, List[str]] = {}

        # ---- Native window basics ----
        self.title("MiniRates")
        self.configure(bg=self.t.get("SURFACE", "#1a1a22"))
        self._set_window_icon()

        # ---- Alpha & Always-on-top ----
        try:
            self.attributes("-alpha", float(self.settings.window_alpha()))
        except Exception:
            pass

        try:
            self.wm_attributes("-topmost", bool(self.settings.always_on_top()))
        except Exception:
            pass

        # ---- Resizability & Minimum size ----
        try:
            self.resizable(bool(getattr(C, "RESIZABLE", True)), bool(getattr(C, "RESIZABLE", True)))
        except Exception:
            pass
        try:
            self.minsize(int(getattr(C, "MIN_W", 320)), int(getattr(C, "MIN_H", 200)))
        except Exception:
            pass

        # ---- Header state (search & source) ----
        self._search_query: str = ""
        self._source_mode: str = "both"  # "alanchand" | "tgju" | "both"
        self._all_items_cache: list[dict] = []  # last full list (pre-filter)
        
        # ---- Restore geometry (size + position) ----
        self._last_saved_geom: Optional[Tuple[int, int, int, int]] = None
        self._apply_geometry_from_settings()

        # ---- Services (local, for enrichment only) ----
        self.baselines = DailyBaselines()

        # ---- Refresh timer state (event-driven, no I/O here) ----
        self.auto_refresh_ms: int = int(self.settings.auto_refresh_ms())
        self.refresh_job: Optional[str] = None
        self._is_loading: bool = False

        # ---- News state ----
        self.news_enabled: bool = bool(self.settings.news_visible())
        self.news_failed_once: bool = False

        # ---- Global tooltip ----
        self.tooltip = Tooltip(self, self.t)
        
        # ---- Build UI ----
        self._build_ui()

        # ---- Fonts ----
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        except Exception:
            pass

        # ---- Key bindings ----
        self.bind("<Escape>", lambda _e: self._hide_to_tray())
        self.bind("<Control-q>", lambda _e: self._quit_app())
        self.bind("<Control-r>", lambda _e: self._on_refresh_click())
        self.bind("<F2>", lambda _e: self._toggle_always_on_top())

        # Persist geometry on move/resize + responsive scale + viewport sync
        self.bind("<Configure>", self._on_configure)

        # Rows scroll → Back-to-top visibility (and "user is scrolling" hint)
        self._in_rows_scroll: bool = False
        self._in_rows_scroll_after_id = None
        try:
            if hasattr(self.rows, "sf") and hasattr(self.rows.sf, "set_on_yview"):
                self.rows.sf.set_on_yview(self._on_rows_yview)
        except Exception:
            pass

        # Throttle handle for viewport computation
        self._viewport_after_id = None
        self._last_avail_height: Optional[int] = None
        self._rows_scroll_enabled: Optional[bool] = None  # last applied state

        # ---- Safety: remove any old global wheel bindings (if existed) ----
        try: self.unbind_all("<MouseWheel>")
        except Exception: pass
        try:
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

        # ---- Ensure canvas receives focus on hover (Windows friendliness) ----
        try:
            self.rows.sf.canvas.bind("<Enter>", lambda _e: self.rows.sf.canvas.focus_set(), add="+")
        except Exception:
            pass

        # ---- Seed DI for PriceService (settings + catalog facade) ----
        class _CatalogFacade:
            def fetch(self, *, force_refresh: bool = False):
                return get_catalog_cached_or_fetch(force_refresh=force_refresh)
            def build_view(self, settings):
                return build_display_lists(self.fetch(force_refresh=False), settings)

        try:
            container.register("settings", lambda: self.settings, override=True)
        except Exception:
            pass

        try:
            if container.try_resolve("catalog") is None:
                container.register("catalog", lambda: _CatalogFacade(), override=True)
        except Exception:
            pass

        # ---- Create PriceService and marshal events onto UI thread ----
        self.price_service = PriceService(self.bus)
        self.price_service.set_dispatcher(self.after)

        # ---- Event subscriptions ----
        self._subscriptions: list[callable] = []
        self._subscriptions.append(self.bus.subscribe(PricesRefreshed, self._on_prices_refreshed))
        self._subscriptions.append(self.bus.subscribe(NewsUpdated, self._on_news_updated))
        # Theme toggling
        self._subscriptions.append(self.bus.subscribe(ThemeToggled, self._on_theme_toggled_evt))

        # ---- Initial refresh (event-driven) ----
        self.after(300, self._safe_initial_refresh)

    # ===================== UI =====================
    def _build_ui(self) -> None:
        """Builds the main layout: rows area + footer (+ optional news bar)."""
        self.root_frame = tk.Frame(self, bg=self.t["SURFACE"], highlightthickness=0, bd=0)
        self.root_frame.pack(fill=tk.BOTH, expand=True)

        # --- Header (source selector + realtime search) ---
        self.header = HeaderBar(
            self.root_frame,
            theme=self.t,
            on_source_change=self._on_source_change,
            on_search_change=self._on_search_change,
            tooltip=self.tooltip,
        )
        self.header.pack(fill=tk.X, side=tk.TOP, anchor="n")

        # Rows wrap: we control its height to shape the list viewport
        self.rows_wrap = tk.Frame(self.root_frame, bg=self.t["SURFACE"], highlightthickness=0, bd=0)
        self.rows_wrap.pack(fill=tk.BOTH, expand=True, side=tk.TOP, anchor="n")
        self.rows_wrap.pack_propagate(False)

        # --- Rows (DI-only theming; no theme passed) ---
        self.rows = Rows(self.rows_wrap, tooltip=self.tooltip, on_pin_toggle=self._on_row_pin_toggle)
        self.rows.pack(side=tk.TOP, anchor="n", fill=tk.X)

        # Footer: pass callbacks; refresh now only publishes events
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

        # Brightness control (wheel or slider + button) if supported by FooterBar
        try:
            params = inspect.signature(FooterBar.__init__).parameters
            if "on_brightness_change" in params or "get_brightness" in params:
                footer_kwargs.update(
                    on_brightness_change=lambda level: (self.attributes("-alpha", level), self.settings.set_window_alpha(level)),
                    get_brightness=lambda: float(self.attributes("-alpha") or 1.0),
                )
            elif "on_brightness_wheel" in params:
                footer_kwargs.update(on_brightness_wheel=None)
        except Exception:
            pass

        self.footer = FooterBar(self.root_frame, **footer_kwargs)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)

        # NewsBar (only if enabled)
        self.news_bar: Optional[NewsBar] = None
        if self.news_enabled:
            self._create_news_bar()

        # Sync footer pin state
        try:
            self.footer.set_pin_state(self._get_current_topmost())
        except Exception:
            pass

        # Initial news state color
        self._sync_news_state(
            "ok" if self.news_enabled and not self.news_failed_once
            else ("error" if self.news_failed_once else "hidden")
        )

    # ========== Theming / Fonts / Opacity ==========
    def _get_theme(self, name: str) -> Dict[str, Any]:
        # از themes.py جدید استفاده کن (get_theme)
        try:
            return dict(get_theme(name))
        except Exception:
            pass
        if isinstance(THEMES, dict) and name in THEMES:
            return THEMES[name]
        if isinstance(THEMES, dict) and THEMES:
            return next(iter(THEMES.values()))
        # Fallback minimal theme
        return {
            "SURFACE": "#1a1a22",
            "ON_SURFACE": "#f0f2f5",
            "PRIMARY": "#00e5c7",
            "ERROR": "#e74c3c",
            "SUCCESS": "#28a745",
            "OUTLINE": "#2a2a35",
        }

    def _pick_font_family(self) -> str:
        preferred = list(getattr(C, "PREFERRED_FONTS", []))
        for segoe in ("Segoe UI Variable", "Segoe UI"):
            if segoe in preferred:
                preferred.insert(0, preferred.pop(preferred.index(segoe)))
            else:
                preferred.insert(0, segoe)
        try:
            installed = set(tkfont.families())
        except Exception:
            installed = set()
        for name in preferred:
            if name in installed:
                return name
        return "Segoe UI"

    def _apply_font_family(self, family: str) -> None:
        """Apply scaled fonts to theme, footer, rows, and tooltip."""
        base_primary = 10
        base_bold    = 10
        base_small   = 9
        base_title   = 12

        s = float(self.scale)
        s = max(0.85, min(1.75, s))

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

        # Apply to root and wrappers (fix background theming)
        try:
            self.configure(bg=self.t["SURFACE"])
            self.root_frame.configure(bg=self.t["SURFACE"])
            self.rows_wrap.configure(bg=self.t["SURFACE"])
        except Exception:
            pass

        try:
            if hasattr(self, "header"):
                self.header.set_theme(self.t)
                self.header.set_fonts(family)
                if hasattr(self.header, "set_scale"):
                    self.header.set_scale(s)
        except Exception:
            pass

        # Footer / News
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

        # Rows (DI-only apply with font/size overrides merged)
        try:
            if hasattr(self.rows, "apply_theme"):
                # IMPORTANT: pass `self.t` so Rows can merge only font/size keys into DI tokens
                self.rows.apply_theme(self.t)
            if hasattr(self.rows, "set_scale"):
                self.rows.set_scale(s)
            elif hasattr(self.rows, "set_row_height"):
                self.rows.set_row_height(self.t["ROW_HEIGHT_SCALED"])
        except Exception:
            pass

        # Tooltip
        try:
            self.tooltip.refresh_theme(self.t)
        except Exception:
            pass

    # ================= Theme integration =================
    def _on_theme_toggled_evt(self, evt: ThemeToggled) -> None:
        """
        واکنش به ThemeToggled از ThemeService:
        - توکن‌های تم را بازخوانی می‌کنیم (از سرویس اگر باشد، وگرنه get_theme)
        - فونت‌ها و اندازه‌ها مجدد اعمال می‌شوند
        - Viewport ردیف‌ها همگام‌سازی می‌شود
        """
        try:
            self.theme_name = evt.theme_name or self.theme_name
        except Exception:
            pass

        if self.theme_svc:
            try:
                self.t = dict(self.theme_svc.tokens())
            except Exception:
                self.t = self._get_theme(self.theme_name)
        else:
            self.t = self._get_theme(self.theme_name)

        # Re-apply everywhere
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        finally:
            self._update_rows_viewport()

    def _on_toggle_theme(self) -> None:
        """
        دکمهٔ تغییر تم در فوتر:
        - اگر ThemeService وجود دارد، toggle() را صدا می‌زنیم (رویداد منتشر می‌شود).
        - در غیر اینصورت، fallback قبلی (چرخش محلی) انجام می‌شود.
        """
        if self.theme_svc:
            try:
                self.theme_svc.toggle()
                return
            except Exception:
                pass

        # Fallback (بدون سرویس)
        names = list(THEMES.keys()) if isinstance(THEMES, dict) else []
        try:
            i = names.index(self.theme_name)
        except Exception:
            i = -1
        self.theme_name = names[(i + 1) % len(names)] if names else "dark"
        self.t = self._get_theme(self.theme_name)
        self.settings.set_theme_name(self.theme_name)
        # Re-apply
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        finally:
            self._update_rows_viewport()

    # ================ Brightness via footer wheel ================
    def _on_brightness_wheel(self, steps: int) -> None:
        """Adjust window alpha when the mouse wheel moves over the footer."""
        try:
            cur = float(self.attributes("-alpha"))
        except Exception:
            cur = float(self.settings.window_alpha())

        new_alpha = cur + (BRIGHTNESS_STEP * float(steps))
        new_alpha = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, new_alpha))
        if abs(new_alpha - cur) < 1e-9:
            return

        try:
            self.attributes("-alpha", new_alpha)
        except Exception:
            pass
        self.settings.set_window_alpha(new_alpha)

    # ================= Pin / Always-on-top =================
    def _get_current_topmost(self) -> bool:
        try:
            return bool(self.attributes("-topmost"))
        except Exception:
            return bool(self.settings.always_on_top())

    def _toggle_always_on_top(self, force: bool | None = None) -> None:
        current = self._get_current_topmost()
        new_state = (not current) if force is None else bool(force)
        try:
            self.wm_attributes("-topmost", new_state)
        except Exception:
            pass
        self.settings.set_always_on_top(new_state)
        try:
            self.footer.set_pin_state(new_state)
        except Exception:
            pass

    # ================= Tray / Close =================
    def _hide_to_tray(self) -> None:
        try:
            self.withdraw()
        except Exception:
            pass
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
        self._cancel_refresh()
        try:
            tray = container.try_resolve("tray")
            if tray and tray.is_running():
                tray.stop()
        except Exception:
            pass
        try:
            self.tooltip.destroy()
        except Exception:
            pass
        self.destroy()

    # ================= Rows / Footer helpers =================
    def _on_rows_yview(self, first: float, _last: float) -> None:
        # mark: user is scrolling (throttle viewport recalcs a bit)
        self._in_rows_scroll = True
        if self._in_rows_scroll_after_id is not None:
            try:
                self.after_cancel(self._in_rows_scroll_after_id)
            except Exception:
                pass
        self._in_rows_scroll_after_id = self.after(120, self._clear_rows_scrolling)

        # NEW: toggle BackToTop visibility based on scroll position
        try:
            self.footer.set_back_top_visible(bool(first > 0.01))
        except Exception:
            pass

    def _on_row_pin_toggle(self, item_id: Optional[str], new_state: bool) -> None:
        """Handle pin/unpin requests coming from Rows/RateRow."""
        if not item_id:
            return
        changed = False
        try:
            if new_state:
                changed, _ = pin_item(self.settings, item_id)
            else:
                changed, _ = unpin_item(self.settings, item_id)
        except Exception:
            changed = False

        if not changed:
            return

        # Rebuild display lists and refresh rows (pinned items first)
        try:
            catalog_data = None
            try:
                catalog_data = getattr(self, '_catalog_cache', None) or self._get_catalog_cached()
            except Exception:
                catalog_data = None

            if catalog_data is None:
                catalog_data = self._fetch_catalog_data()

            view = build_display_lists(catalog_data or {}, self.settings)
            items = []
            pinned_list = view.get('pinned') or []
            items.extend(pinned_list)
            other_groups = view.get('groups') or view.get('others') or {}
            for cat in ("fx", "gold", "crypto"):
                items.extend(other_groups.get(cat, []) or [])
            if not items and isinstance(view, dict):
                for k, v in view.items():
                    if isinstance(v, list):
                        items.extend(v)
            try:
                items = self._enrich_with_deltas(items)
            except Exception:
                pass
            try:
                self.rows.update(items)
            except Exception:
                pass
            try:
                self._update_rows_viewport()
            except Exception:
                pass
        except Exception:
            pass

    def _clear_rows_scrolling(self) -> None:
        self._in_rows_scroll = False
        self._in_rows_scroll_after_id = None
        self._update_rows_viewport()

    def _on_back_to_top(self) -> None:
        try:
            if hasattr(self.rows, "sf") and hasattr(self.rows.sf, "smooth_scroll_to"):
                self.rows.sf.smooth_scroll_to(0.0, duration_ms=240)
        except Exception:
            pass

    # ================= Refresh: event-driven =================
    def _safe_initial_refresh(self) -> None:
        try:
            self._on_refresh_click()
        finally:
            self._schedule_next_refresh(self.auto_refresh_ms)

    def _on_refresh_click(self) -> None:
        if self._is_loading:
            return
        self._is_loading = True
        try:
            self.footer.set_loading(True)
        except Exception:
            pass
        self.bus.publish(RefreshRequested(source="ui"))

    def _on_prices_refreshed_done(self) -> None:
        self._is_loading = False
        try:
            self.footer.set_loading(False)
        except Exception:
            pass
        self._schedule_next_refresh(self.auto_refresh_ms)
        now = dt.datetime.now().strftime("%H:%M")
        try:
            self.footer.set_time_text(to_persian_digits(now))
        except Exception:
            self.footer.set_time_text(now)

    def _schedule_next_refresh(self, delay_ms: int) -> None:
        self._cancel_refresh()
        try:
            self.refresh_job = self.after(max(500, int(delay_ms)), self._on_refresh_click)
        except Exception:
            self.refresh_job = None

    def _cancel_refresh(self) -> None:
        if self.refresh_job is not None:
            try:
                self.after_cancel(self.refresh_job)
            except Exception:
                pass
            self.refresh_job = None

    # ================= Event handlers =================
    def _on_prices_refreshed(self, evt: PricesRefreshed) -> None:
        items = list(evt.items or [])
        items = self._enrich_with_deltas(items)

        # Keep full snapshot, then apply UI filters (search/source)
        self._all_items_cache = items
        items = self._apply_ui_filters(items)

        try:
            self.rows.update(items)
        except Exception:
            pass
        self._update_rows_viewport()
        self._on_prices_refreshed_done()

    def _on_news_updated(self, evt: NewsUpdated) -> None:
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
            try:
                setattr(self.news_bar, "_items", evt.items or [])
            except Exception:
                pass
        self._update_rows_viewport()

    # ================= Data enrichment (Δ & spark history) =================
    def _enrich_with_deltas(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compute deltas + lock rolling history window per symbol.

        Changes:
        - History window length K now uses SPARK_BAR_MAX_COUNT (defaults to 30) instead of a hard 10.
          This allows the sparkbar to render more bars on wide windows.
        """
        self.baselines.reset_if_new_day()
        out: List[Dict[str, Any]] = []
        if not hasattr(self, "_histories"):
            self._histories = {}
        if not hasattr(self, "_time_hist"):
            self._time_hist = {}

        try:
            from app.config import constants as C
            K = int(getattr(C, "SPARK_BAR_MAX_COUNT", 30))
        except Exception:
            K = 30
        K = 10 if K <= 10 else min(64, K)

        for it in (items or []):
            try:
                sym = it.get("symbol") or it.get("title") or "UNKNOWN"
                price = self._coerce_price(it.get("price"))

                # Daily baseline & deltas
                base = self.baselines.get_or_set(sym, price)
                delta = float(price - base)
                pct = float((delta / base) * 100.0) if base else 0.0

                it["delta_value"] = delta
                it["delta_pct"] = pct
                it["delta_str"] = self._format_delta_toman(delta)
                it["delta_pct_str"] = self._format_delta_percent(base, delta)
                it["delta_is_up"] = (delta > 0)

                time_label = str(it.get("updated_at") or dt.datetime.now().strftime("%H:%M")).strip()

                # Coerce history (full or roll)
                item_hist = it.get("history") or []
                item_times = it.get("times") or []

                def _coerce_hist(seq) -> List[Optional[float]]:
                    arr: List[Optional[float]] = []
                    for v in (seq or []):
                        try:
                            arr.append(float(v))
                        except Exception:
                            arr.append(None)
                    return arr

                if item_hist and item_times:
                    vals = _coerce_hist(item_hist)
                    times = [str(x) if x is not None else "" for x in (item_times or [])]
                    # normalize to last K (right-aligned)
                    if len(vals) < K: vals = ([None] * (K - len(vals))) + vals
                    if len(times) < K: times = ([""] * (K - len(times))) + times
                    if len(vals) > K: vals = vals[-K:]
                    if len(times) > K: times = times[-K:]
                else:
                    # roll from previous
                    prev_vals = self._histories.get(sym, [])
                    prev_times = self._time_hist.get(sym, [])
                    try:
                        from app.ui.sparkbar import roll_fixed_window
                        vals, times = roll_fixed_window(prev_vals, prev_times, k=K, new_value=price, new_time=time_label)
                    except Exception:
                        s = list(prev_vals or [])
                        t = list(prev_times or [])
                        while len(s) < K: s.insert(0, None)
                        while len(t) < K: t.insert(0, None)
                        if len(s) > K: s = s[-K:]
                        if len(t) > K: t = t[-K:]
                        s = (s + [price])[-K:]
                        t = (t + [time_label])[-K:]
                        vals, times = s, t

                # Save for next tick
                self._histories[sym] = list(vals)
                self._time_hist[sym] = list(times)

                # Inject into item for Rows/SparkBar
                it["history"] = list(vals)
                it["times"] = list(times)
            except Exception:
                pass

            out.append(it)

        # Cleanup removed symbols
        live_syms = { (i.get("symbol") or i.get("title") or "UNKNOWN") for i in out }
        for k in list(self._histories.keys()):
            if k not in live_syms:
                self._histories.pop(k, None)
                self._time_hist.pop(k, None)

        return out

    @staticmethod
    def _coerce_price(v) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            s = str(v).replace(",", "").replace(" ", "")
            return float(s)
        except Exception:
            return 0.0

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
        if self.news_bar:
            return
        try:
            self.news_bar = NewsBar(self.root_frame, usernames=self.settings.news_accounts(), theme=self.t)
            for hook in ("set_on_state", "on_state", "bind_state"):
                if hasattr(self.news_bar, hook) and callable(getattr(self.news_bar, hook)):
                    try:
                        getattr(self.news_bar, hook)(self._on_news_state)
                        break
                    except Exception:
                        pass
            self.news_bar.pack(fill=tk.X, side=tk.BOTTOM)
        except Exception:
            self.news_bar = None
            self.news_failed_once = True

    def _destroy_news_bar(self) -> None:
        if not self.news_bar:
            return
        try:
            self.news_bar.pack_forget()
            self.news_bar.destroy()
        except Exception:
            pass
        self.news_bar = None

    def _on_toggle_news(self) -> None:
        self.news_enabled = not self.news_enabled
        self.settings.set_news_visible(self.news_enabled)
        self.bus.publish(NewsVisibilityToggled(visible=self.news_enabled))

        if not self.news_enabled:
            self._destroy_news_bar()
            self._sync_news_state("hidden")
            self._update_rows_viewport()
            return

        self._create_news_bar()
        self._sync_news_state("loading")
        self._update_rows_viewport()

    def _on_news_state(self, state: str) -> None:
        self._sync_news_state(state)

    def _sync_news_state(self, state: str) -> None:
        try:
            self.footer.set_news_state(state)
        except Exception:
            pass
        self.news_failed_once = (state == "error")

    # ================= Geometry & Responsive Scale =================
    def _apply_geometry_from_settings(self) -> None:
        x, y, w, h = self.settings.window_rect()
        try:
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self._center_with_size(w, h)
        self._last_saved_geom = (w, h, self.winfo_x(), self.winfo_y())
        self._update_scale_from_size(w, h, force=True)

    def _center_with_size(self, w: int, h: int) -> None:
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            cx = int((sw - w) / 2)
            cy = int((sh - h) / 3)
            self.geometry(f"{w}x{h}+{cx}+{cy}")
        except Exception:
            self.geometry(f"{w}x{h}+200+120")

    def _on_configure(self, _e=None) -> None:
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

        self._update_rows_viewport()

    # --- Responsive helpers ---
    def _update_scale_from_size(self, w: int, h: int, force: bool = False) -> None:
        sw = max(0.4, min(3.0, w / float(self.base_w)))
        sh = max(0.4, min(3.0, h / float(self.base_h)))
        s = min(sw, sh)
        if (not force) and self._last_scaled is not None:
            if abs(s - self._last_scaled) < 0.05:
                return
        self.scale = s
        self._last_scaled = s
        self.settings.set_ui_scale(self.scale)
        try:
            ff = self._pick_font_family()
            self._apply_font_family(ff)
        except Exception:
            pass

    def _update_rows_viewport(self) -> None:
        if self._in_rows_scroll:
            if self._viewport_after_id is not None:
                try: self.after_cancel(self._viewport_after_id)
                except Exception: pass
            self._viewport_after_id = self.after(80, self._update_rows_viewport)
            return

        if self._viewport_after_id is not None:
            try: self.after_cancel(self._viewport_after_id)
            except Exception: pass
            self._viewport_after_id = None

        def _do():
            try:
                self.update_idletasks()
                total_h = self.winfo_height()
                footer_h = self.footer.winfo_height() if self.footer else 0
                news_h = self.news_bar.winfo_height() if self.news_bar else 0
                top_pad = max(4, int(6 * self.scale))
                avail = max(60, total_h - footer_h - news_h - top_pad)

                if self._last_avail_height is None or abs(avail - self._last_avail_height) > 1:
                    try:
                        self.rows_wrap.configure(height=avail)
                    except Exception:
                        pass
                    try:
                        if hasattr(self.rows, "set_viewport_height"):
                            self.rows.set_viewport_height(avail)
                        elif hasattr(self.rows, "fit_to_height"):
                            self.rows.fit_to_height(avail)
                        elif hasattr(self.rows, "set_max_height"):
                            self.rows.set_max_height(avail)
                    except Exception:
                        pass
                    self._last_avail_height = avail

                try:
                    content_h = getattr(self.rows, "content_height", lambda: avail)()
                    should_enable = bool(content_h > avail)
                    if self._rows_scroll_enabled is None or should_enable != self._rows_scroll_enabled:
                        if hasattr(self.rows, "set_scroll_enabled"):
                            self.rows.set_scroll_enabled(should_enable)
                        self._rows_scroll_enabled = should_enable
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._viewport_after_id = None

        self._viewport_after_id = self.after(16, _do)

    # ================= Icon / Logo =================
    def _set_window_icon(self) -> None:
        candidates = [
            "assets/logo.png",
            "assets/icon.png",
            "app/assets/logo.png",
            "app/assets/icon.png",
        ]
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

    # ================= Run =================
    def run(self) -> None:
        self.mainloop()


def main():
    from app.core.events import EventBus
    from app.config.settings import SettingsManager
    bus = EventBus()
    settings = SettingsManager()
    app = MiniRatesWindow(bus=bus, settings=settings)
    bus.publish(RefreshRequested(source="dev"))
    app.run()


if __name__ == "__main__":
    main()
