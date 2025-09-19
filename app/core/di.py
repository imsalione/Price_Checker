# app/core/di.py
# -*- coding: utf-8 -*-
"""
Dependency Injection (DI) container for MiniRates.

Responsibilities
----------------
- Provide a tiny, explicit DI container with lazy singletons.
- Centralize wiring of app services (bus, settings, theme, tray, catalog, twitter).
- Keep consumers decoupled from construction details & concrete modules.

Usage
-----
    from app.core.di import container, register_default_services

    register_default_services()  # once at startup (e.g., in main.py)

    bus      = container.resolve("bus")
    settings = container.resolve("settings")
    theme    = container.resolve("theme")
    tray     = container.resolve("tray")
    catalog  = container.resolve("catalog")   # CatalogService facade
    twitter  = container.try_resolve("twitter")  # optional
"""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional


# ---------- Thin Facades (no heavy logic) ----------

class CatalogService:
    """
    A small facade over catalog/cache utilities (multi-source ready).

    Methods
    -------
    fetch(force_refresh: bool = False) -> dict
        Return the merged catalog (fx/gold/crypto). Bypasses caches if force_refresh=True.

    build_view(settings) -> dict
        Return UI-friendly structure using pins:
        {
          "pinned": [...],
          "others": {"fx":[...], "gold":[...], "crypto":[...]}
        }
    """
    def __init__(self, get_catalog_cached_or_fetch, build_display_lists):
        self._get = get_catalog_cached_or_fetch
        self._build = build_display_lists

    def fetch(self, *, force_refresh: bool = False):
        return self._get(force_refresh=force_refresh)

    def build_view(self, settings):
        catalog = self.fetch(force_refresh=False)
        return self._build(catalog, settings)


class TwitterService:
    """
    A light wrapper to make the Twitter (X) service DI-friendly.

    Methods
    -------
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


# ---------- Minimal DI Container ----------

class Container:
    """A minimal DI container with lazy, singleton-like instances."""
    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any], *, override: bool = False) -> None:
        """
        Register a factory under a unique name.

        Parameters
        ----------
        name : str
            Service name.
        factory : Callable[[], Any]
            Zero-argument callable returning a new instance.
        override : bool
            If True, replace existing registration and drop any cached instance.
        """
        if not callable(factory):
            raise TypeError(f"Factory for '{name}' must be callable.")
        if name in self._factories and not override:
            raise KeyError(f"Service already registered: {name}")
        self._factories[name] = factory
        if override and name in self._instances:
            self._instances.pop(name, None)

    def resolve(self, name: str) -> Any:
        """Return the (possibly newly constructed) instance for a registered service."""
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            raise KeyError(f"Service not registered: {name}")
        instance = self._factories[name]()
        self._instances[name] = instance
        return instance

    def try_resolve(self, name: str, default: Optional[Any] = None) -> Any:
        """Resolve a service if available; otherwise return default (no exception)."""
        try:
            return self.resolve(name)
        except KeyError:
            return default

    def clear_instances(self) -> None:
        """Drop all cached instances (factories remain)."""
        self._instances.clear()

    def reset(self) -> None:
        """Drop both factories and instances."""
        self._factories.clear()
        self._instances.clear()


# Global container instance
container = Container()


def register_default_services(*, override: bool = False) -> None:
    """
    Register core app services into the global container.

    Registered Names
    ----------------
    - "bus"       -> EventBus()
    - "settings"  -> SettingsManager()
    - "baselines" -> DailyBaselines()
    - "tray"      -> TrayService()
    - "theme"     -> ThemeService(bus)  (fallback no-op if missing)
    - "catalog"   -> CatalogService(get_catalog_cached_or_fetch, build_display_lists)
    - "twitter"   -> TwitterService(twitter_service_module) (optional)
    """
    # Local imports to avoid import-cycles at module import time
    from app.core.events import EventBus
    from app.config.settings import SettingsManager  # 
    from app.services.baselines import DailyBaselines  # 

    # Tray service
    from app.infra.tray import TrayService  # 

    # Catalog: multi-source cache + view builder
    # (Services live under app/services in this project)
    from app.services.cache import get_catalog_cached_or_fetch  # 
    from app.services.catalog import build_display_lists         # 

    # Theme service (graceful fallback if module not present)
    try:
        from app.services.theme_service import ThemeService
    except Exception:
        class FallbackThemeService:  # type: ignore
            """No-op fallback ThemeService used when the real module is absent."""
            def __init__(self, *_args, **_kwargs) -> None:
                pass
        ThemeService = FallbackThemeService

    # Twitter (X) service: prefer services path; fallback to scrapers path if needed
    twitter_mod = None
    try:
        from app.infra.adapters import twitter_adapter as _twitter_mod  # preferred  
        twitter_mod = _twitter_mod
    except Exception:
        try:
            from app.scrapers import twitter_service as _twitter_mod  # fallback (header shows scrapers)
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
