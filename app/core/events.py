# app/core/events.py
# -*- coding: utf-8 -*-
"""
Lightweight event system for MiniRates.

- A minimal pub/sub EventBus with type-based subscriptions.
- Handlers are called synchronously on publish() (Tkinter main thread).
- Returns an unsubscribe() callable from subscribe() for easy cleanup.
- Optional 'subscribe_all' to observe every event (useful for logging).

Usage:
    from dataclasses import dataclass
    from app.core.events import EventBus, WheelScrolled

    bus = EventBus()

    def on_wheel(evt: WheelScrolled) -> None:
        print(evt.area, evt.delta)

    unsubscribe = bus.subscribe(WheelScrolled, on_wheel)
    bus.publish(WheelScrolled(area="rows", delta=+1))
    unsubscribe()  # stop observing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Generic, Protocol


# ---------- Base marker ----------

class Event:
    """Marker base class for all events."""
    ...


# ---------- Events (add here as the app grows) ----------

@dataclass(frozen=True)
class WheelScrolled(Event):
    """Mouse wheel normalized steps in a named area ('rows', 'footer', ...)."""
    area: str       # e.g., "rows" or "footer"
    delta: int      # +1 / -1 (or multi-step on fast wheels)


@dataclass(frozen=True)
class BrightnessChanged(Event):
    """Brightness level changed (0.0 .. 1.0)."""
    level: float


@dataclass(frozen=True)
class ThemeToggled(Event):
    """Theme changed to a given theme name."""
    theme_name: str


@dataclass(frozen=True)
class NewsVisibilityToggled(Event):
    """News bar visibility state changed."""
    visible: bool


@dataclass(frozen=True)
class PricesRefreshed(Event):
    """
    New prices available for rendering.
    'items' is already shaped for UI consumption (DTO/ViewModel or raw dicts).
    """
    items: list[dict]


@dataclass(frozen=True)
class NewsUpdated(Event):
    """New list of news items (tweets/etc.) ready for UI."""
    items: list[dict]


@dataclass(frozen=True)
class BackToTopRequested(Event):
    """Request to scroll rows to top (e.g., footer button)."""
    pass


@dataclass(frozen=True)
class RefreshRequested(Event):
    """Request to refresh data now (e.g., header/footer refresh button)."""
    source: str = "ui"  # "ui" | "timer" | "tray" | ...


@dataclass(frozen=True)
class PinStateChanged(Event):
    """Window always-on-top (pin) state changed."""
    pinned: bool


# ---------- Typing helpers ----------

E = TypeVar("E", bound=Event)


class EventHandler(Protocol, Generic[E]):
    """Callable protocol for event handlers."""
    def __call__(self, evt: E) -> None: ...


# ---------- EventBus ----------

class EventBus:
    """
    Type-based pub/sub event bus.

    - subscribe(EventType, handler) -> unsubscribe()
    - subscribe_all(handler) -> unsubscribe()
    - publish(EventInstance)

    Notes:
        * Handlers are invoked synchronously in the caller's thread.
          In Tkinter apps, call publish() from the main thread.
        * Handlers are isolated: an exception in one handler won't stop others.
    """

    def __init__(self) -> None:
        self._subs: Dict[Type[Event], List[Callable[[Event], None]]] = {}
        self._any_subs: List[Callable[[Event], None]] = []

    # ---- subscription ----
    def subscribe(self, etype: Type[E], handler: EventHandler[E]) -> Callable[[], None]:
        """
        Subscribe to a specific event type.

        Returns:
            A zero-arg function that, when called, unsubscribes this handler.
        """
        if etype not in self._subs:
            self._subs[etype] = []
        self._subs[etype].append(handler)  # type: ignore[arg-type]

        def _unsubscribe() -> None:
            lst = self._subs.get(etype, [])
            try:
                lst.remove(handler)  # type: ignore[arg-type]
            except ValueError:
                pass

        return _unsubscribe

    def subscribe_all(self, handler: Callable[[Event], None]) -> Callable[[], None]:
        """
        Subscribe to ALL events (useful for logging or global observers).

        Returns:
            A zero-arg function that unsubscribes this handler.
        """
        self._any_subs.append(handler)

        def _unsubscribe() -> None:
            try:
                self._any_subs.remove(handler)
            except ValueError:
                pass

        return _unsubscribe

    # ---- publish ----
    def publish(self, evt: Event) -> None:
        """Publish an event instance to matching subscribers."""
        # Dispatch to type-specific subscribers
        handlers = list(self._subs.get(type(evt), []))
        # Dispatch to 'any' subscribers
        any_handlers = list(self._any_subs)

        # Call specific handlers
        for h in handlers:
            try:
                h(evt)  # type: ignore[arg-type]
            except Exception:
                # Never let a single handler break the chain
                pass

        # Call 'any' handlers
        for h in any_handlers:
            try:
                h(evt)
            except Exception:
                pass

    # ---- management ----
    def clear(self) -> None:
        """Remove all subscriptions."""
        self._subs.clear()
        self._any_subs.clear()
