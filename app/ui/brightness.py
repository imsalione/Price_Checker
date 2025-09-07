# app/ui/brightness.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from typing import Dict, Callable, Optional


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle on canvas."""
    points = [
        (x1+r, y1), (x2-r, y1),
        (x2, y1), (x2, y1+r),
        (x2, y2-r), (x2, y2),
        (x2-r, y2), (x1+r, y2),
        (x1, y2), (x1, y2-r),
        (x1, y1+r), (x1, y1),
    ]
    # Use create_polygon with smooth to simulate rounded rect
    return canvas.create_polygon(
        [
            points[0], points[1], points[2], points[3],
            points[4], points[5], points[6], points[7],
            points[8], points[9], points[10], points[11]
        ],
        smooth=True, **kwargs
    )


class BrightnessPopup(tk.Toplevel):
    """
    Minimal, borderless brightness/opacity popup:
    - Rounded card with theme colors
    - Custom slider (50..100) that updates window alpha in real time
    - Opens centered over parent window
    """

    def __init__(
        self,
        parent: tk.Tk,
        theme: Dict[str, str],
        on_change: Callable[[float], None],
        initial_alpha: float = 1.0
    ):
        super().__init__(parent)
        self.t = theme
        self.on_change = on_change
        self.initial_alpha = initial_alpha
        self._val = int(initial_alpha * 100)
        
        self.wm_overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg="white", bd=0) # Use a neutral background for drawing
        self.resizable(False, False)

        # Draw the rounded card on a canvas
        self.canvas = tk.Canvas(self, width=200, height=48, highlightthickness=0, bg=self.t.get("SURFACE"))
        self.canvas.pack(padx=10, pady=10)

        # Slider track
        self.slider_x = 20
        self.slider_w = 160
        self.slider_y = 24
        self.canvas.create_line(
            self.slider_x, self.slider_y, self.slider_x + self.slider_w, self.slider_y,
            fill=self.t.get("SURFACE_VARIANT"), width=4, capstyle=tk.ROUND
        )

        # Slider thumb
        self.thumb = self.canvas.create_oval(0, 0, 0, 0, fill=self.t.get("PRIMARY"), outline=self.t.get("ON_SURFACE"), width=1)
        
        # Labels
        self.min_lbl = self.canvas.create_text(
            self.slider_x - 5, self.slider_y, text="50%", anchor="e", font=self.t.get("FONT_SMALL"), fill=self.t.get("ON_SURFACE_VARIANT")
        )
        self.max_lbl = self.canvas.create_text(
            self.slider_x + self.slider_w + 5, self.slider_y, text="100%", anchor="w", font=self.t.get("FONT_SMALL"), fill=self.t.get("ON_SURFACE_VARIANT")
        )
        
        self.canvas.bind("<Button-1>", self._on_click_slider)
        self.canvas.bind("<B1-Motion>", self._on_drag_slider)

        self._render_slider()
        self.update_idletasks()
        
        # Center the popup
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        
        # Bind a global click handler to close the popup
        self._root_click_bind_id = parent.bind_all("<Button-1>", self._on_root_click, add=True)

    def _render_slider(self) -> None:
        """Update the thumb position and call the parent callback."""
        rel_val = (self._val - 50) / 50.0
        thumb_x = self.slider_x + int(rel_val * self.slider_w)
        thumb_r = 6
        
        self.canvas.coords(
            self.thumb,
            thumb_x - thumb_r, self.slider_y - thumb_r,
            thumb_x + thumb_r, self.slider_y + thumb_r
        )
        self.on_change(self._val / 100.0)

    def _clamp(self, value: int) -> int:
        return max(50, min(100, value))

    def _set_from_mouse(self, event) -> None:
        x = int(event.x)
        rel = x - self.slider_x
        ratio = rel / float(self.slider_w)
        val = 50 + int(round(50 * ratio))
        self._val = self._clamp(val)
        self._render_slider()

    def _on_click_slider(self, event) -> None:
        self._set_from_mouse(event)

    def _on_drag_slider(self, event) -> None:
        self._set_from_mouse(event)

    def _on_root_click(self, event) -> None:
        """Destroy popup when clicking anywhere outside this popup."""
        try:
            tl = event.widget.winfo_toplevel()
            if tl is self:
                return
        except Exception:
            pass
        
        try:
            self.destroy()
        except Exception:
            pass

    def destroy(self) -> None:
        """Ensure we clean up bindings before destroying."""
        try:
            if self._root_click_bind_id:
                self.master.unbind_all("<Button-1>", self._root_click_bind_id)
        except Exception:
            pass
        super().destroy()
