# app/main.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from app.core.di import register_default_services, container
from app.core.events import EventBus, RefreshRequested, NewsVisibilityToggled
from app.config.settings import SettingsManager
from app.ui.window import MiniRatesWindow


def main() -> None:
    # 1) Register default services (settings, baselines, tray, catalog, twitter)
    register_default_services()

    # 2) Shared EventBus in DI
    bus = EventBus()
    container.register("bus", lambda: bus, override=True)

    # 3) Resolve settings
    settings: SettingsManager = container.resolve("settings")

    # 4) Build UI
    app = MiniRatesWindow(bus=bus, settings=settings)

    # 5) Instantiate event-driven services + inject dispatcher (root.after)
    container.register(
        "price_service",
        lambda: __import__("app.services.price_service", fromlist=["PriceService"]).PriceService(bus),
        override=True
    )
    container.register(
        "news_service",
        lambda: __import__("app.services.news_service", fromlist=["NewsService"]).NewsService(bus),
        override=True
    )
    ps = container.resolve("price_service")
    ns = container.resolve("news_service")
    try:
        ps.set_dispatcher(app.after)  # publish events on main thread
        ns.set_dispatcher(app.after)
    except Exception:
        pass

    # 6) First events: initial refresh + news visibility
    bus.publish(RefreshRequested(source="startup"))
    bus.publish(NewsVisibilityToggled(visible=bool(settings.get("news_visible", False))))

    # 7) Run
    app.run()


if __name__ == "__main__":
    main()
