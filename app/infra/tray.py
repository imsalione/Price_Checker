"""
System tray service using pystray.
- When the window hides, we start the tray icon.
- Menu:
    • Show window  -> bring window to front
    • Exit   -> exit app entirely
"""

from __future__ import annotations
from typing import Optional, Callable
import threading

from PIL import Image, ImageDraw, ImageFont
import pystray


class TrayService:
    """A tiny wrapper over pystray.Icon running in its own thread."""

    def __init__(
        self,
        title: str = "MiniRates",
        on_show: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        icon_image: Optional[Image.Image] = None,
    ) -> None:
        self.title = title
        self.on_show = on_show
        self.on_exit = on_exit
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._image = icon_image or self._make_default_icon()

    # ---------- public ----------
    def start(self) -> None:
        """Start the tray icon in a background thread (idempotent)."""
        if self._running:
            return
        self._running = True

        def _run():
            try:
                menu = pystray.Menu(
                    pystray.MenuItem("Show window", self._menu_show),
                    pystray.MenuItem("Exit", self._menu_exit),
                )
                self._icon = pystray.Icon(name="MiniRates", title=self.title, icon=self._image, menu=menu)
                self._icon.run()
            finally:
                self._icon = None
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the tray icon if running."""
        try:
            if self._icon is not None:
                self._icon.stop()  # safe to call from any thread
        except Exception:
            pass
        self._icon = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    # ---------- menu handlers (these run on tray thread) ----------
    def _menu_show(self, icon, item):
        # Defer to main thread via provided callback
        if self.on_show:
            try:
                self.on_show()
            except Exception:
                pass

    def _menu_exit(self, icon, item):
        if self.on_exit:
            try:
                self.on_exit()
            except Exception:
                pass

    # ---------- icon factory ----------
    def _make_default_icon(self, size: int = 32) -> Image.Image:
        """Draw a minimal coin-like glyph as the tray icon."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # outer ring
        d.ellipse((1, 1, size - 2, size - 2), fill=(255, 204, 0, 255), outline=(180, 140, 0, 255), width=2)
        # inner disk
        m = 6
        d.ellipse((m, m, size - m, size - m), fill=(255, 229, 77, 255), outline=(180, 140, 0, 255), width=1)
        # simple "₮" like mark
        try:
            # Try to draw a T-like mark
            cx = size // 2
            d.line((cx - 6, cx - 4, cx + 6, cx - 4), fill=(80, 60, 0, 255), width=2)
            d.line((cx, cx - 6, cx, cx + 6), fill=(80, 60, 0, 255), width=2)
        except Exception:
            pass
        return img
