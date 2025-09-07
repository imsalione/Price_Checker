# app/ui/tooltip.py
# -*- coding: utf-8 -*-
"""
Lightweight tooltip manager for Tkinter with two usage styles:

1) Manager style (recommended):
     tooltip = Tooltip(root, theme)
     tooltip.attach(widget, "static text")
     tooltip.attach(widget, lambda: dynamic_text())
     ...
     tooltip.detach(widget)
     # Or call tooltip.show(text, e.x_root, e.y_root) directly from canvas tag-binds.

2) Helper style (quick attach using a shared manager on the toplevel):
     from app.ui.tooltip import attach_tooltip, detach_tooltip
     attach_tooltip(widget, "text", theme)
     detach_tooltip(widget)

This module does NOT bind <MouseWheel> globally and should not interfere with scrolling.
"""

from __future__ import annotations
import tkinter as tk
from typing import Any, Callable, Dict, Optional, Tuple, Union

TextSource = Union[str, Callable[[], str]]


class Tooltip:
    """
    A single shared tooltip manager per toplevel window.

    Responsibilities:
      - Display a small popup near the cursor after a short delay.
      - Keep styling in sync with the application's theme.
      - Support both direct show/hide and managed attach/detach.

    Public API:
      - attach(widget, text_or_callable, *, delay=350, follow=True)
      - detach(widget)
      - show(text, x_root, y_root)
      - show_parts(delta_text, time_text, *, trend, x_root, y_root)  # rich two-part tooltip
      - hide()
      - refresh_theme(theme)

    Notes:
      - No bind_all("<MouseWheel>") is used here.
      - The popup window is over-the-top and borderless.
    """

    def __init__(self, root: tk.Misc, theme: Optional[Dict[str, str]] = None) -> None:
        self.root = root
        self.theme = dict(theme or {})
        self._tip: Optional[tk.Toplevel] = None
        self._frame: Optional[tk.Frame] = None
        self._lbl: Optional[tk.Label] = None

        self._visible: bool = False
        self._pending_after: Optional[str] = None
        self._cur_text: str = ""
        self._last_xy: Tuple[int, int] = (0, 0)

        # attached widgets → (widget, text_source, delay_ms, follow)
        self._attached: Dict[int, Tuple[tk.Widget, TextSource, int, bool]] = {}

        # Dimensions / paddings
        self._pad_x = 8
        self._pad_y = 5
        self._wrap = 320  # px
        self._offset = (12, 16)  # offset from mouse pointer (x, y)

        # Rich-mode widgets (built on demand in refresh_theme)
        self._rich: Optional[tk.Frame] = None
        self._icon: Optional[tk.Label] = None
        self._delta: Optional[tk.Label] = None
        self._sep: Optional[tk.Label] = None
        self._time: Optional[tk.Label] = None

        self.refresh_theme(self.theme)

    # ---------- Public: manager attachments ----------
    def attach(self, widget: tk.Widget, text_or_callable: TextSource, *, delay: int = 350, follow: bool = True) -> None:
        """
        Attach tooltip behavior to a widget.

        Args:
            widget: Target widget.
            text_or_callable: Either a static string or a zero-arg callable returning a string.
            delay: Show delay in milliseconds after pointer enters.
            follow: If True, tooltip repositions (and refreshes text) while the mouse moves.
        """
        wid = int(widget.winfo_id())
        self._attached[wid] = (widget, text_or_callable, int(delay), bool(follow))

        widget.bind("<Enter>", lambda _e, w=widget: self._on_enter(w), add="+")
        widget.bind("<Leave>", lambda _e, w=widget: self._on_leave(w), add="+")
        widget.bind("<Motion>", lambda e, w=widget: self._on_motion(w, e), add="+")

    def detach(self, widget: tk.Widget) -> None:
        """Detach a previously attached tooltip from a widget."""
        wid = int(widget.winfo_id())
        if wid in self._attached:
            del self._attached[wid]
        # Do not unbind other handlers; only ensure the popup is hidden if it belongs here.
        self.hide()

    # ---------- Public: direct show/hide ----------
    def show(self, text: str, x_root: int, y_root: int) -> None:
        """
        Show tooltip immediately at given screen coordinates (root-based).
        Intended for canvas tag binds: e.g., tooltip.show(txt, e.x_root, e.y_root)
        """
        if not text:
            return
        self._ensure_popup()
        # If rich layout was visible previously, hide it and use simple label
        try:
            if getattr(self, '_rich', None) is not None:
                self._rich.pack_forget()
        except Exception:
            pass

        self._cur_text = str(text)

        try:
            self._lbl.config(text=self._cur_text, wraplength=self._wrap, justify="left")
        except Exception:
            pass

        x, y = self._place_near(x_root, y_root)
        try:
            self._tip.geometry(f"+{x}+{y}")
            self._tip.deiconify()
            self._tip.lift()
        except Exception:
            pass
        self._visible = True
        self._last_xy = (x, y)

    def show_parts(self, delta_text: str, time_text: str, *, trend: int = 0, x_root: int, y_root: int) -> None:
        """
        Rich tooltip: [▲/▼ + delta_text]  •  [🕒 time_text]
        trend: 1=up (green ▲) | -1=down (red ▼) | 0=neutral (gray ◇)
        """
        self._ensure_popup()
        # Hide simple label and show rich layout
        try:
            if self._lbl is not None:
                self._lbl.pack_forget()
        except Exception:
            pass
        if getattr(self, "_rich", None) is None:
            # Fallback to plain text if rich UI not built yet
            return self.show(f"{delta_text}  •  {time_text}".strip(), x_root, y_root)

        # Colors
        up = self.theme.get('SUCCESS', '#22d67e')
        dn = self.theme.get('ERROR', '#ff6b6b')
        nt = self.theme.get('ON_SURFACE_VARIANT', '#9aa0a6')
        icon = '▲' if trend > 0 else ('▼' if trend < 0 else '◇')
        color = up if trend > 0 else (dn if trend < 0 else nt)

        try:
            self._icon.configure(text=icon, fg=color)
            self._delta.configure(text=str(delta_text or ""), fg=color)
            # add clock icon to time
            tt = f"🕒 {time_text}" if time_text else ""
            self._time.configure(text=tt)
            # place and show rich frame
            self._rich.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass

        x, y = self._place_near(int(x_root), int(y_root))
        try:
            self._tip.geometry(f"+{x}+{y}")
            self._tip.deiconify()
            self._tip.lift()
        except Exception:
            pass
        self._visible = True
        self._last_xy = (x, y)

    def hide(self) -> None:
        """Hide the tooltip popup immediately and cancel any pending show timers."""
        if self._pending_after:
            try:
                self.root.after_cancel(self._pending_after)
            except Exception:
                pass
            self._pending_after = None
        if self._tip and self._visible:
            try:
                self._tip.withdraw()
            except Exception:
                pass
        self._visible = False

    def refresh_theme(self, theme: Optional[Dict[str, str]]) -> None:
        """Update colors/fonts based on theme dictionary."""
        if theme:
            self.theme = dict(theme)

        bg = self.theme.get("SURFACE", "#1e1f27")
        fg = self.theme.get("ON_SURFACE", "#f0f2f5")
        outline = self.theme.get("OUTLINE", "#2a2a35")

        if self._tip is None:
            self._tip = tk.Toplevel(self.root)
            try:
                self._tip.wm_overrideredirect(True)
                self._tip.attributes("-topmost", True)
            except Exception:
                pass

            self._frame = tk.Frame(self._tip, bg=outline)
            self._frame.pack(fill=tk.BOTH, expand=True)

            self._lbl = tk.Label(
                self._frame,
                text="",
                bg=bg, fg=fg,
                padx=self._pad_x, pady=self._pad_y,
                justify="left",
                anchor="w",
                wraplength=self._wrap,
            )
            self._lbl.pack(padx=1, pady=1)
            self._tip.withdraw()

            # Build rich two-part layout once (icon ▲/▼, delta, separator, time)
            if self._rich is None:
                self._rich = tk.Frame(self._frame, bg=bg)
                self._icon = tk.Label(self._rich, text="", bg=bg, fg=self.theme.get("SUCCESS", "#22d67e"))
                self._icon.pack(side=tk.LEFT, padx=(self._pad_x, 4))
                self._delta = tk.Label(self._rich, text="", bg=bg, fg=self.theme.get("SUCCESS", "#22d67e"), justify="left")
                self._delta.pack(side=tk.LEFT)
                self._sep = tk.Label(self._rich, text="  •  ", bg=bg, fg=self.theme.get("ON_SURFACE_VARIANT", "#9aa0a6"))
                self._sep.pack(side=tk.LEFT, padx=6)
                self._time = tk.Label(self._rich, text="", bg=bg, fg=self.theme.get("ON_SURFACE_VARIANT", "#9aa0a6"), justify="left")
                self._time.pack(side=tk.LEFT, padx=(0, self._pad_x))
                self._rich.pack_forget()

        # Apply new colors if already built
        try:
            self._frame.configure(bg=outline)
            self._lbl.configure(bg=bg, fg=fg)
            # Sync rich widgets colors if present
            if getattr(self, '_rich', None) is not None:
                try:
                    self._rich.configure(bg=bg)
                    self._icon.configure(bg=bg)
                    self._delta.configure(bg=bg)
                    self._sep.configure(bg=bg, fg=self.theme.get('ON_SURFACE_VARIANT', '#9aa0a6'))
                    self._time.configure(bg=bg, fg=self.theme.get('ON_SURFACE_VARIANT', '#9aa0a6'))
                except Exception:
                    pass
        except Exception:
            pass

    def destroy(self) -> None:
        """Destroy the popup window, if any."""
        try:
            if self._tip is not None:
                self._tip.destroy()
        except Exception:
            pass
        finally:
            self._tip = None
            self._frame = None
            self._lbl = None

    # ---------- Internals ----------
    def _ensure_popup(self) -> None:
        if self._tip is None:
            self.refresh_theme(self.theme)

    def _on_enter(self, widget: tk.Widget) -> None:
        wid = int(widget.winfo_id())
        meta = self._attached.get(wid)
        if not meta:
            return
        _w, text_src, delay_ms, _follow = meta
        if self._pending_after:
            try:
                self.root.after_cancel(self._pending_after)
            except Exception:
                pass
            self._pending_after = None

        def _show():
            try:
                x_root = widget.winfo_pointerx()
                y_root = widget.winfo_pointery()
            except Exception:
                return
            try:
                txt = str(text_src() if callable(text_src) else text_src)
            except Exception:
                txt = ""
            self.show(txt, x_root, y_root)

        # Show after delay
        try:
            self._pending_after = self.root.after(int(delay_ms), _show)
        except Exception:
            pass

    def _on_leave(self, widget: tk.Widget) -> None:
        if self._pending_after:
            try:
                self.root.after_cancel(self._pending_after)
            except Exception:
                pass
            self._pending_after = None
        self.hide()

    def _on_motion(self, widget: tk.Widget, e: tk.Event) -> None:
        wid = int(widget.winfo_id())
        meta = self._attached.get(wid)
        if not meta:
            return
        _w, text_src, _delay_ms, follow = meta

        if not follow:
            return
        try:
            x, y = self._place_near(e.x_root, e.y_root)
            if callable(text_src):
                txt = str(text_src() or "")
                if txt and txt != self._cur_text:
                    self._cur_text = txt
                    self._lbl.config(text=self._cur_text, wraplength=self._wrap, justify="left")
            if self._tip and self._visible:
                self._tip.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _place_near(self, x_root: int, y_root: int) -> Tuple[int, int]:
        """
        Compute a near-mouse position that keeps the popup inside the screen.
        """
        x, y = x_root + self._offset[0], y_root + self._offset[1]
        try:
            self._tip.update_idletasks()
            tw = self._tip.winfo_width()
            th = self._tip.winfo_height()
            sw = self._tip.winfo_screenwidth()
            sh = self._tip.winfo_screenheight()
            if x + tw + 8 > sw:
                x = max(0, sw - tw - 8)
            if y + th + 8 > sh:
                y = max(0, sh - th - 8)
        except Exception:
            pass
        return x, y


# ---------- Helper: quick one-off attach using a shared manager ----------

def _get_shared_mgr(widget: tk.Widget, theme: Optional[Dict[str, str]]) -> Tooltip:
    """Get or create a shared Tooltip manager on the widget's toplevel."""
    try:
        top = widget.winfo_toplevel()
    except Exception:
        top = widget
    mgr: Optional[Tooltip] = getattr(top, "_shared_tooltip_mgr", None)  # type: ignore[attr-defined]
    if isinstance(mgr, Tooltip):
        return mgr
    mgr = Tooltip(top, theme=theme)
    setattr(top, "_shared_tooltip_mgr", mgr)  # type: ignore[attr-defined]
    return mgr


def attach_tooltip(widget: tk.Widget, text_or_callable: TextSource, theme: Optional[Dict[str, str]] = None, *, delay: int = 350, follow: bool = True) -> None:
    """Attach a tooltip using a shared manager on the widget's toplevel."""
    mgr = _get_shared_mgr(widget, theme)
    mgr.attach(widget, text_or_callable, delay=delay, follow=follow)


def detach_tooltip(widget: tk.Widget) -> None:
    """Detach a previously attached tooltip from the shared manager (if present)."""
    try:
        top = widget.winfo_toplevel()
    except Exception:
        top = widget
    mgr: Optional[Tooltip] = getattr(top, "_shared_tooltip_mgr", None)  # type: ignore[attr-defined]
    if isinstance(mgr, Tooltip):
        try:
            mgr.detach(widget)
        except Exception:
            pass
