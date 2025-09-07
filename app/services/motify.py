# app/ui/header.py
from __future__ import annotations
from typing import Optional, Callable, Dict
import webbrowser
import tkinter as tk
from tkinter import font as tkfont
from urllib.request import urlopen
from io import BytesIO
from PIL import Image, ImageTk


class HeaderBar(tk.Frame):
    """
    Top header bar:
      [Exit][Pin][Refresh] | [Logo][Title]

    - Exit is at far right (RTL requirement).
    - Pin sits left of Exit (toggle).
    - Refresh sits left of Pin.
    - Logo + Title on the left side of the bar with vertical alignment.
    - Whole header acts as a draggable area for borderless window.

    Callbacks:
      on_refresh(): None
      on_pin_toggle(pinned: bool): None
      on_exit(): None
    """

    def __init__(
        self,
        master,
        theme: Dict[str, str],
        title_text: str = "MiniRates",
        logo_url: str = "https://imsalione.ir/wp-content/uploads/2023/06/ImSalione-Logo-140x140.png",
        on_refresh: Optional[Callable[[], None]] = None,
        on_pin_toggle: Optional[Callable[[bool], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=theme["SURFACE"], height=36)
        self.t = theme
        self.on_refresh = on_refresh
        self.on_pin_toggle = on_pin_toggle
        self.on_exit = on_exit

        # fonts (family set later)
        self.font_title = tkfont.Font(size=11, weight="bold")
        self.font_btn = tkfont.Font(size=9)

        # state
        self._pinned = False
        self._drag_offset = (0, 0)
        self._logo_img = None
        self._logo_url = logo_url

        # layout: use pack with RTL optics (right cluster buttons, left logo/title)
        self.pack_propagate(False)

        # Right cluster (buttons)
        right_wrap = tk.Frame(self, bg=self.t["SURFACE"])
        right_wrap.pack(side=tk.RIGHT, fill=tk.Y)

        # Exit button (right-most)
        self.btn_exit = tk.Button(
            right_wrap, text="خروج", font=self.font_btn,
            bg=self.t["SURFACE_VARIANT"], fg=self.t["ON_SURFACE"],
            activebackground=self.t["SURFACE_VARIANT"], activeforeground=self.t["ON_SURFACE"],
            bd=0, padx=10, pady=4, cursor="hand2",
            command=self._on_exit_clicked
        )
        self.btn_exit.pack(side=tk.RIGHT, padx=(6, 6), pady=6)

        # Pin toggle (left of Exit)
        self.btn_pin = tk.Button(
            right_wrap, text="📌", font=self.font_btn,
            bg=self.t["SURFACE_VARIANT"], fg=self.t["ON_SURFACE"],
            activebackground=self.t["SURFACE_VARIANT"], activeforeground=self.t["ON_SURFACE"],
            bd=0, padx=8, pady=4, cursor="hand2",
            command=self._on_pin_clicked
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 0), pady=6)

        # Refresh (left of Pin)
        self.btn_refresh = tk.Button(
            right_wrap, text="⟳", font=self.font_btn,
            bg=self.t["SURFACE_VARIANT"], fg=self.t["ON_SURFACE"],
            activebackground=self.t["SURFACE_VARIANT"], activeforeground=self.t["ON_SURFACE"],
            bd=0, padx=8, pady=4, cursor="hand2",
            command=self._on_refresh_clicked
        )
        self.btn_refresh.pack(side=tk.RIGHT, padx=(0, 0), pady=6)

        # Left cluster (logo + title)
        left_wrap = tk.Frame(self, bg=self.t["SURFACE"])
        left_wrap.pack(side=tk.LEFT, fill=tk.Y)

        # Logo (clickable)
        self.logo_lbl = tk.Label(left_wrap, bg=self.t["SURFACE"], cursor="hand2")
        self.logo_lbl.pack(side=tk.LEFT, padx=(8, 6), pady=4)
        self.logo_lbl.bind("<Button-1>", lambda e: webbrowser.open_new_tab("https://imsalione.ir/"))
        self._load_logo_async(self._logo_url, target_size=18)

        # Title (vertically aligned with logo)
        self.title_lbl = tk.Label(left_wrap, text=title_text, font=self.font_title,
                                  bg=self.t["SURFACE"], fg=self.t["ON_SURFACE"], anchor="w")
        self.title_lbl.pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Draggable area: the whole bar
        for w in (self, right_wrap, left_wrap, self.title_lbl, self.logo_lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        self._refresh_palette()

    # ---------- public ----------
    def set_theme(self, theme: Dict[str, str]) -> None:
        self.t = theme
        self.configure(bg=self.t["SURFACE"])
        self._refresh_palette()

    def set_fonts(self, family: str) -> None:
        self.font_title.configure(family=family)
        self.font_btn.configure(family=family)
        # reapply
        self.title_lbl.configure(font=self.font_title)
        self.btn_exit.configure(font=self.font_btn)
        self.btn_pin.configure(font=self.font_btn)
        self.btn_refresh.configure(font=self.font_btn)

    def set_pin_state(self, pinned: bool) -> None:
        """Reflect external pin state (always-on-top)."""
        self._pinned = bool(pinned)
        self.btn_pin.config(text=("📌" if self._pinned else "📍"))

    # ---------- internals ----------
    def _refresh_palette(self) -> None:
        bg = self.t["SURFACE"]
        sv = self.t["SURFACE_VARIANT"]
        fg = self.t["ON_SURFACE"]
        self.configure(bg=bg)
        self.title_lbl.configure(bg=bg, fg=fg)
        self.logo_lbl.configure(bg=bg)
        for b in (self.btn_exit, self.btn_pin, self.btn_refresh):
            b.configure(bg=sv, fg=fg, activebackground=sv, activeforeground=fg)

    def _on_refresh_clicked(self) -> None:
        if self.on_refresh:
            try:
                self.on_refresh()
            except Exception:
                pass

    def _on_pin_clicked(self) -> None:
        self._pinned = not self._pinned
        self.set_pin_state(self._pinned)
        if self.on_pin_toggle:
            try:
                self.on_pin_toggle(self._pinned)
            except Exception:
                pass

    def _on_exit_clicked(self) -> None:
        if self.on_exit:
            try:
                self.on_exit()
            except Exception:
                pass

    # dragging (for borderless window)
    def _start_drag(self, event) -> None:
        try:
            self._drag_offset = (event.x_root, event.y_root)
            self._drag_win_xy = (self.winfo_toplevel().winfo_x(), self.winfo_toplevel().winfo_y())
        except Exception:
            self._drag_offset = (0, 0)
            self._drag_win_xy = (0, 0)

    def _on_drag(self, event) -> None:
        try:
            dx = event.x_root - self._drag_offset[0]
            dy = event.y_root - self._drag_offset[1]
            x = self._drag_win_xy[0] + dx
            y = self._drag_win_xy[1] + dy
            self.winfo_toplevel().geometry(f"+{x}+{y}")
        except Exception:
            pass

    # logo loader
    def _load_logo_async(self, url: str, target_size: int = 18) -> None:
        # Simple sync load (fast, tiny); can be threaded if needed
        try:
            with urlopen(url, timeout=5) as r:
                data = r.read()
            img = Image.open(BytesIO(data)).convert("RGBA")
            img = img.resize((target_size, target_size), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(img)
            self.logo_lbl.configure(image=self._logo_img)
        except Exception:
            # fallback: text logo
            self.logo_lbl.configure(text="◎")
