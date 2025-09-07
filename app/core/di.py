# app/core/di.py
# -*- coding: utf-8 -*-
"""
Dependency Injection (DI) container for MiniRates.

Responsibilities:
  - Provide a central registry for app services (singleton by default).
  - Lazily construct instances via factories (functions with no args).
  - Decouple construction/wiring from consumers (UI, presentation, etc.).

Usage:
  from app.core.di import container, register_default_services

  register_default_services()  # once at startup (e.g., in main.py)
  settings = container.resolve("settings")
  tray     = container.resolve("tray")
  catalog  = container.resolve("catalog")     # see CatalogService facade
  twitter  = container.resolve("twitter")     # see TwitterService facade
  bus      = container.resolve("bus")
"""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional


# ---- Thin facades (no heavy logic) ----
class CatalogService:
    """
    Facade over catalog/cache utilities.

    Methods:
      fetch(force_refresh=False) -> dict                 # raw catalog (fx/gold/crypto)
      build_view(settings) -> dict                       # {"pinned": [...], "others": {...}}
    """
    def __init__(self, get_catalog_cached_or_fetch, build_display_lists):
        self._get = get_catalog_cached_or_fetch
        self._build = build_display_lists

    def fetch(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        return self._get(force_refresh=force_refresh)

    def build_view(self, settings) -> Dict[str, Any]:
        # Note: If you want to reuse last fetched catalog, call fetch(False) here.
        catalog = self.fetch(force_refresh=False)
        return self._build(catalog, settings)


class TwitterService:
    """
    Facade over twitter adapter/service to make it DI-friendly.

    Methods:
      resolve_usernames(usernames: list[str]) -> list[str]
      fetch_latest(usernames: list[str], per_user=3,
                   exclude_replies=False, exclude_retweets=False) -> list[dict]
    """
    def __init__(self, mod):
        self._mod = mod

    def resolve_usernames(self, usernames):
        return self._mod.resolve_usernames(usernames)

    def fetch_latest(self, usernames, per_user: int = 3,
                     *, exclude_replies: bool = False, exclude_retweets: bool = False):
        return self._mod.fetch_latest_tweets(
            usernames, per_user=per_user,
            exclude_replies=exclude_replies,
            exclude_retweets=exclude_retweets
        )


# ---- Minimal container implementation ----
class Container:
    """A minimal DI container with lazy singleton factories."""
    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any], *, override: bool = False) -> None:
        """
        Register a service factory by name.

        Args:
            name: Unique service name.
            factory: Zero-arg callable returning a new instance.
            override: If True, replace existing registration and drop cached instance.
        """
        if not callable(factory):
            raise TypeError(f"Factory for '{name}' must be callable.")
        if name in self._factories and not override:
            raise KeyError(f"Service already registered: {name}")
        self._factories[name] = factory
        if override and name in self._instances:
            self._instances.pop(name, None)

    def resolve(self, name: str) -> Any:
        """Get (and lazily construct) a service instance by name."""
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            raise KeyError(f"Service not registered: {name}")
        instance = self._factories[name]()
        self._instances[name] = instance
        return instance

    def try_resolve(self, name: str, default: Optional[Any] = None) -> Any:
        """Resolve a service if registered; otherwise return default."""
        try:
            return self.resolve(name)
        except KeyError:
            return default

    def clear_instances(self) -> None:
        """Clear cached instances (factories remain)."""
        self._instances.clear()

    def reset(self) -> None:
        """Clear both factories and instances."""
        self._factories.clear()
        self._instances.clear()


# Global container instance
container = Container()


def register_default_services(*, override: bool = False) -> None:
    """
    Register core app services into the global container.
    Safe to call once at startup (e.g., main.py). Set override=True to re-wire.

    Registered names:
      - "bus"         -> EventBus()
      - "settings"    -> SettingsManager()
      - "baselines"   -> DailyBaselines()
      - "tray"        -> TrayService()
      - "theme"       -> ThemeService(bus)
      - "catalog"     -> CatalogService(cache.get_catalog_cached_or_fetch, catalog.build_display_lists)
      - "twitter"     -> TwitterService(twitter_module)
    """
    # Local imports to avoid import cycles on module import
    from app.core.events import EventBus
    from app.config.settings import SettingsManager
    from app.services.baselines import DailyBaselines

    # Tray (may vary by platform)
    try:
        from app.infra.tray import TrayService
    except Exception:
        TrayService = lambda: object()  # type: ignore

    # Catalog helpers
    from app.services.cache import get_catalog_cached_or_fetch
    from app.services.catalog import build_display_lists

    # Theme service (needs bus)
    from app.services.theme_service import ThemeService

    # Twitter adapter/service (name may vary between projects)
    twitter_mod = None
    try:
        from app.infra import twitter_adapter as _twitter_mod  # preferred
        twitter_mod = _twitter_mod
    except Exception:
        try:
            from app.infra import twitter_adapter as _twitter_mod  # fallback
            twitter_mod = _twitter_mod
        except Exception:
            twitter_mod = None

    # ---- Register base services ----
    container.register("bus", lambda: EventBus(), override=override)
    container.register("settings", lambda: SettingsManager(), override=override)
    container.register("baselines", lambda: DailyBaselines(), override=override)
    container.register("tray", lambda: TrayService(), override=override)
    container.register("theme", lambda: ThemeService(container.resolve("bus")), override=override)

    # ---- Facades ----
    container.register(
        "catalog",
        lambda: CatalogService(get_catalog_cached_or_fetch, build_display_lists),
        override=override,
    )
    if twitter_mod is not None:
        container.register(
            "twitter",
            lambda: TwitterService(twitter_mod),
            override=override,
        )
