# app/services/price_service.py
# -*- coding: utf-8 -*-
"""
PriceService: event-driven catalog refresh & publish.

Listens:
  - RefreshRequested(source="...")

Publishes:
  - PricesRefreshed(items: list[dict])

Notes:
  - Does network/cache I/O off the UI thread (threading).
  - Use set_dispatcher(root.after) from UI to marshal publishes to the main thread.
  - Works with DI facades registered in core/di.py ("catalog", "settings").
"""

from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional, Callable, Union

from app.core.events import EventBus, RefreshRequested, PricesRefreshed
from app.core.di import container


Number = Union[int, float]


class PriceService:
    """Fetches catalog, shapes minimal rows, and publishes PricesRefreshed."""

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._lock = threading.Lock()
        self._running = False
        self._dispatcher: Optional[Callable[[int, Callable], str]] = None  # e.g., root.after

        # subscribe to refresh requests
        self.bus.subscribe(RefreshRequested, self._on_refresh_requested)

        # lazy deps (via DI)
        self._catalog = None   # "catalog" facade from DI
        self._settings = None  # SettingsManager

    # ---------- public API ----------
    def set_dispatcher(self, after_callable: Callable[[int, Callable], str]) -> None:
        """UI injects root.after to ensure publishes happen on the UI thread."""
        self._dispatcher = after_callable

    def refresh(self, *, force: bool = False) -> None:
        """Trigger a background refresh if not already running."""
        with self._lock:
            if self._running:
                return
            self._running = True
        t = threading.Thread(
            target=self._worker,
            kwargs={"force": force},
            name=f"PriceServiceWorker(force={force})",
            daemon=True,
        )
        t.start()

    # ---------- internals ----------
    def _on_refresh_requested(self, evt: RefreshRequested) -> None:
        """
        Any source can trigger a refresh (UI/manual/auto).
        Convention: source == "ui" → force refresh.
        """
        self.refresh(force=(evt.source == "ui"))

    def _worker(self, *, force: bool) -> None:
        try:
            if self._catalog is None:
                self._catalog = container.resolve("catalog")
            if self._settings is None:
                self._settings = container.resolve("settings")

            # Hint the catalog to refresh cache if 'force' (depending on facade impl).
            # Our DI facade's build_view() fetches internally (from cache),
            # so an explicit fetch(force=True) here ensures fresh data if requested.
            if force:
                try:
                    self._catalog.fetch(force_refresh=True)
                except Exception:
                    # Facade may not expose fetch or may be already fresh; continue.
                    pass

            # Build the catalog view (pinned + categories) using current settings
            view = self._catalog.build_view(self._settings)

            # Flatten to minimal UI rows
            items = self._flatten_for_rows(view)

            # Publish on UI thread if dispatcher is provided
            self._publish(PricesRefreshed(items=items))

        finally:
            with self._lock:
                self._running = False

    # ---------- shaping ----------
    @staticmethod
    def _num(v: Any) -> Optional[Number]:
        """Coerce value to number if possible, else None."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return v
        try:
            s = str(v).replace(",", "").replace(" ", "")
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _format_price_str(v: Optional[Number]) -> str:
        """Return a human-friendly string like '123,456' or '—'."""
        if v is None:
            return "—"
        try:
            return f"{int(round(float(v))):,}"
        except Exception:
            return "—"

    def _flatten_for_rows(self, view: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Flatten pinned + categories into a single list; provide the minimal
        fields that UI (Rows) expects. Window/UI can further enrich (delta text,
        percent, localized digits, timestamps, etc.).
        """
        out: List[Dict[str, Any]] = []

        def map_item(it: Dict[str, Any], *, pinned: bool) -> Dict[str, Any]:
            name = (it.get("name") or it.get("title") or "—").strip()
            # choose price with gentle fallback to sell/buy
            price = self._num(it.get("price"))
            if price is None:
                price = self._num(it.get("sell"))
            if price is None:
                price = self._num(it.get("buy"))

            return {
                "title": name,
                "name": name,
                "price": price,
                "price_str": self._format_price_str(price),
                "full_price": price,
                "updated_at": "",                      # UI may fill
                "history": it.get("history") or [],    # optional
                "times": it.get("times") or [],        # optional
                "delta_str": "",                       # UI may fill
                "delta_pct_str": "",                   # UI may fill
                "delta_is_up": (str(it.get("delta_dir", "")).lower() == "up"),
                "pinned": bool(pinned),
                "symbol": it.get("_id") or name,       # stable-ish key for row
            }

        # pinned first (keep order)
        for it in (view.get("pinned") or []):
            out.append(map_item(it, pinned=True))

        # others by categories (fx, gold, crypto)
        others = view.get("others") or {}
        for cat in ("fx", "gold", "crypto"):
            for it in (others.get(cat) or []):
                out.append(map_item(it, pinned=False))

        return out

    def _publish(self, evt) -> None:
        """Publish on UI thread if dispatcher is set; else publish directly."""
        if self._dispatcher:
            try:
                self._dispatcher(0, lambda: self.bus.publish(evt))
                return
            except Exception:
                # Fallback to direct publish
                pass
        self.bus.publish(evt)
