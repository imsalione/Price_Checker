# app/services/news_service.py
# -*- coding: utf-8 -*-
"""
NewsService: event-driven X (Twitter) fetch.

Listens:
  - NewsVisibilityToggled(visible)
  - RefreshRequested(source="...")

Publishes:
  - NewsUpdated(items: list[dict])

Notes:
  - Background thread for network I/O.
  - Use set_dispatcher(root.after) from UI to marshal publishes to UI thread.
  - Respects SettingsManager.news_accounts() and visibility.
"""

from __future__ import annotations
import threading
from typing import List, Optional, Callable

from app.core.events import EventBus, RefreshRequested, NewsVisibilityToggled, NewsUpdated
from app.core.di import container


class NewsService:
    """Fetches latest tweets from configured accounts when visible or on refresh."""

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._lock = threading.Lock()
        self._running = False
        self._visible = False
        self._dispatcher: Optional[Callable[[int, Callable], str]] = None

        # subscribe
        self.bus.subscribe(NewsVisibilityToggled, self._on_visibility)
        self.bus.subscribe(RefreshRequested, self._on_refresh)

        # deps (lazy via DI)
        self._settings = None    # SettingsManager
        self._twitter = None     # TwitterService facade

    # ----- public -----
    def set_dispatcher(self, after_callable: Callable[[int, Callable], str]) -> None:
        self._dispatcher = after_callable

    # ----- internals -----
    def _on_visibility(self, evt: NewsVisibilityToggled) -> None:
        self._visible = bool(evt.visible)
        if self._visible:
            self._fetch_async()

    def _on_refresh(self, _evt: RefreshRequested) -> None:
        if self._visible:
            self._fetch_async()

    def _fetch_async(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self) -> None:
        try:
            if self._settings is None:
                self._settings = container.resolve("settings")
            if self._twitter is None:
                self._twitter = container.resolve("twitter")

            accounts: List[str] = self._settings.news_accounts() if hasattr(self._settings, "news_accounts") else []
            if not accounts:
                self._publish(NewsUpdated(items=[]))
                return

            # Try resolve; fall back gracefully
            try:
                accounts = self._twitter.resolve_usernames(accounts)
            except Exception:
                pass

            tweets = []
            try:
                tweets = self._twitter.fetch_latest(
                    accounts, per_user=3, exclude_replies=True, exclude_retweets=True
                )
            except Exception:
                tweets = []

            self._publish(NewsUpdated(items=tweets))
        finally:
            with self._lock:
                self._running = False

    def _publish(self, evt) -> None:
        if self._dispatcher:
            try:
                self._dispatcher(0, lambda: self.bus.publish(evt))
                return
            except Exception:
                pass
        self.bus.publish(evt)
