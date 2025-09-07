# app/ui/footer.py
# -*- coding: utf-8 -*-
"""
Minimal emoji-only footer (monochrome icons, no bg, centered vertically).
- Emojis are rendered in **monochrome** using a symbol font + fg=ON_SURFACE.
- No hover/background color changes on buttons.
- Vertical centering via asymmetric pady=(top=1, bottom=2).
- Back-to-top button is **hidden by default** and only appears when you call
  set_back_top_visible(True) from the main window (e.g., on scroll).
"""

from __future__ import annotations
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Callable, Dict, Any, List

from app.utils.formatting import to_persian_digits

EMOJI_THEME   = "🌓"
EMOJI_BELL    = "🔔"
EMOJI_PIN_ON  = "📌"
EMOJI_PIN_OFF = "📍"
EMOJI_REFRESH = "🔴"
EMOJI_LOADING = "⏳"
EMOJI_UP      = "⬆"
EMOJI_BRIGHT  = "🔆"


def _pick_monochrome_symbol_family(root: tk.Misc) -> str:
    """
    Pick a non-color (monochrome) font so emojis render as glyphs with fg color.
    Order matters; first available wins.
    """
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    for name in (
        "Segoe UI Symbol",        # Windows
        "Noto Sans Symbols",      # Linux
        "Apple Symbols",          # macOS
        "DejaVu Sans",            # common fallback
        "Symbola",
        "Arial Unicode MS",
        "Liberation Sans",
        "Segoe UI",               # last resort (still mostly monochrome)
    ):
        if name in fams:
            return name
    return ""  # let Tk decide


class _EmojiBtn(tk.Label):
    """Minimal clickable emoji 'button' (monochrome via fg; no hover bg; no custom bg)."""
    def __init__(
        self,
        parent: tk.Misc,
        *,
        emoji: str,
        command: Optional[Callable[[], None]],
        theme: Dict[str, Any],
        tooltip_mgr: Any = None,
        tooltip_text: Optional[str] = None,
        font_family: str = "",
        font_size: int = 9,
        padx: int = 2,
    ) -> None:
        self.t = theme
        self._emoji = emoji
        self._cmd = command
        self._tooltip_mgr = tooltip_mgr

        # Keep both current and last non-empty tooltip texts to avoid blank popups on re-hover
        self._tooltip_text = (tooltip_text or "").strip()
        self._last_tooltip_text = self._tooltip_text

        fam = font_family or _pick_monochrome_symbol_family(parent)
        self._font = tkfont.Font(family=fam, size=font_size)

        super().__init__(
            parent,
            text=self._emoji,
            font=self._font,
            bg=self.t.get("SURFACE", "#1a1a22"),              # same as footer → looks bg-less
            fg=self.t.get("ON_SURFACE", "#f0f2f5"),           # enforce monochrome (light on dark)
            cursor="hand2",
            padx=padx, pady=0,
            bd=0, highlightthickness=0,
        )

        if self._cmd:
            self.bind("<Button-1>", lambda _e: self._cmd(), add="+")

        # Tooltip: capture provider that never returns empty after first non-empty display
        if self._tooltip_mgr and hasattr(self._tooltip_mgr, "attach"):
            def _provider(*_args, **_kwargs) -> str:
                txt = (self._tooltip_text or "").strip()
                if txt:
                    # cache last non-empty
                    self._last_tooltip_text = txt
                    return txt
                # fallback to last non-empty to prevent blank tooltip
                return self._last_tooltip_text or ""
            try:
                # Prefer close offset; if not supported, retry without it
                self._tooltip_mgr.attach(
                    self, _provider, delay=120, follow=True, offset=(6, 4)
                )
            except TypeError:
                # Older attach signature w/o offset → degrade gracefully
                try:
                    self._tooltip_mgr.attach(self, _provider, delay=120, follow=True)
                except Exception:
                    pass
            except Exception:
                pass

    def set_theme(self, theme: Dict[str, Any]) -> None:
        self.t = theme or self.t
        try:
            self.configure(
                bg=self.t.get("SURFACE", "#1a1a22"),
                fg=self.t.get("ON_SURFACE", "#f0f2f5"),
            )
        except Exception:
            pass

    def set_emoji(self, emoji: str) -> None:
        self._emoji = emoji
        try:
            self.configure(text=self._emoji)
        except Exception:
            pass

    def set_font(self, family: str, size: int) -> None:
        try:
            if family:
                self._font.configure(family=family)
            self._font.configure(size=size)
            self.configure(font=self._font)
        except Exception:
            pass

    def set_tooltip(self, text: str) -> None:
        # Update both current and (if non-empty) last shown text to keep consistency
        text = (text or "").strip()
        self._tooltip_text = text
        if text:
            self._last_tooltip_text = text


class FooterBar(tk.Frame):
    """Compact emoji-only footer with a minimal brightness popup (centered)."""

    def __init__(
        self,
        parent: tk.Misc,
        theme: Dict[str, Any],
        *,
        show_refresh_button: bool = True,
        on_refresh: Optional[Callable[[], None]] = None,
        on_theme_toggle: Optional[Callable[[], None]] = None,
        on_back_to_top: Optional[Callable[[], None]] = None,
        on_news_toggle: Optional[Callable[[], None]] = None,
        on_pin_toggle: Optional[Callable[[], None]] = None,
        on_brightness_change: Optional[Callable[[float], None]] = None,
        get_brightness: Optional[Callable[[], float]] = None,
        tooltip: Any = None,
    ) -> None:
        super().__init__(parent, bg=theme.get("SURFACE", "#1a1a22"))
        self.t = theme or {}
        self.tooltip = tooltip

        # Callbacks
        self.on_refresh = on_refresh
        self.on_theme_toggle = on_theme_toggle
        self.on_back_to_top = on_back_to_top
        self.on_news_toggle = on_news_toggle
        self.on_pin_toggle = on_pin_toggle
        self.on_brightness_change = on_brightness_change
        self.get_brightness = get_brightness

        # Fonts / sizes (ultra-compact)
        self.emoji_family = _pick_monochrome_symbol_family(self)
        self.emoji_size = 12
        self.clock_font = tkfont.Font(size=9, family="")  # UI font; fg applied below

        # Wraps
        self.left_wrap = tk.Frame(self, bg=self.t["SURFACE"])
        self.left_wrap.pack(side=tk.LEFT, padx=4, pady=0)
        self.right_wrap = tk.Frame(self, bg=self.t["SURFACE"])
        self.right_wrap.pack(side=tk.RIGHT, padx=4, pady=0)

        # ---- Left cluster ----
        self._btn_news = _EmojiBtn(
            self.left_wrap, emoji=EMOJI_BELL, command=self._on_news_toggle_clicked,
            theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="News",
            font_family=self.emoji_family, font_size=self.emoji_size,
        )
        self._btn_news.pack(side=tk.LEFT, padx=(0, 2), pady=(1, 2))

        self._btn_theme = _EmojiBtn(
            self.left_wrap, emoji=EMOJI_THEME, command=self._on_theme_toggled,
            theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="Change Theme",
            font_family=self.emoji_family, font_size=self.emoji_size,
        )
        self._btn_theme.pack(side=tk.LEFT, padx=(0, 2), pady=(1, 2))

        self._pin_state = False
        self._btn_pin = _EmojiBtn(
            self.left_wrap, emoji=EMOJI_PIN_OFF, command=self._on_pin_clicked,
            theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="Pin Window",
            font_family=self.emoji_family, font_size=self.emoji_size,
        )
        self._btn_pin.pack(side=tk.LEFT, padx=(0, 2), pady=(1, 2))

        # BackToTop: NOT packed by default; only via set_back_top_visible(True)
        self._back_top_visible = False
        self._btn_back_top = _EmojiBtn(
            self.left_wrap, emoji=EMOJI_UP, command=self._on_back_to_top_clicked,
            theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="Back to Top",
            font_family=self.emoji_family, font_size=self.emoji_size,
        )
        # do NOT pack here!

        self._btn_bright = _EmojiBtn(
            self.left_wrap, emoji=EMOJI_BRIGHT, command=self._open_brightness_popup,
            theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="Brightness",
            font_family=self.emoji_family, font_size=self.emoji_size,
        )
        self._btn_bright.pack(side=tk.LEFT, padx=(0, 2), pady=(1, 2))

        # ---- Right cluster ----
        self._btn_refresh: Optional[tk.Label] = None
        if show_refresh_button:
            self._btn_refresh = _EmojiBtn(
                self.right_wrap, emoji=EMOJI_REFRESH, command=self._on_refresh_clicked,
                theme=self.t, tooltip_mgr=self.tooltip, tooltip_text="Refresh",
                font_family=self.emoji_family, font_size=self.emoji_size,
            )
            self._btn_refresh.pack(side=tk.RIGHT, padx=(2, 0), pady=(1, 2))

        self._lbl_time = tk.Label(
            self.right_wrap, text="--:--",
            bg=self.t["SURFACE"],
            fg=self.t.get("ON_SURFACE", "#f0f2f5"),
            font=self.clock_font, padx=2, pady=0,
        )
        self._lbl_time.pack(side=tk.RIGHT, padx=(2, 0), pady=(1, 2))

        # News state for tooltip text
        self._news_state = "hidden"

        # Brightness popup refs
        self._bright_win: Optional[tk.Toplevel] = None
        self._bright_scale: Optional[tk.Scale] = None
        self._bright_wrap_out: Optional[tk.Frame] = None
        self._bright_wrap_in: Optional[tk.Frame] = None
        self._bright_header: Optional[tk.Frame] = None
        self._bright_val_lbl: Optional[tk.Label] = None

        # For scaling (do NOT include back_top to avoid accidental packing)
        self._emoji_widgets: List[tk.Widget] = [
            self._btn_news, self._btn_theme, self._btn_pin, self._btn_bright, self._btn_refresh
        ]

        self._apply_theme(self.t)

    # ---------- Public API ----------
    def set_theme(self, theme: Dict[str, Any]) -> None:
        self.t = theme or self.t
        try:
            self.configure(bg=self.t["SURFACE"])
            self.left_wrap.configure(bg=self.t["SURFACE"])
            self.right_wrap.configure(bg=self.t["SURFACE"])
            self._lbl_time.configure(bg=self.t["SURFACE"], fg=self.t.get("ON_SURFACE", "#f0f2f5"))
            for b in (self._btn_news, self._btn_theme, self._btn_pin, self._btn_back_top, self._btn_bright, self._btn_refresh):
                if b is not None:
                    b.set_theme(self.t)
        except Exception:
            pass
        self._apply_brightness_popup_theme()

    def set_fonts(self, family: str) -> None:
        """Affects only clock; emojis use the chosen symbol font."""
        try:
            self.clock_font.configure(family=family)
            self._lbl_time.configure(font=self.clock_font)
        except tk.TclError:
            pass

    def set_scale(self, s: float) -> None:
        """Keep compact height; adjust paddings & fonts proportionally."""
        try:
            s = float(s)
        except Exception:
            s = 1.0

        pad_x = max(2, int(4 * s))
        self.left_wrap.configure(padx=pad_x, pady=0)
        self.right_wrap.configure(padx=pad_x, pady=0)

        new_emoji = max(8, int(9 * s))
        if new_emoji != self.emoji_size:
            self.emoji_size = new_emoji
            for btn in (self._btn_news, self._btn_theme, self._btn_pin, self._btn_bright, self._btn_refresh, self._btn_back_top):
                if btn is not None:
                    btn.set_font(self.emoji_family, self.emoji_size)

        # --- Uniform vertical centering for all footer items ---
        top_pad    = max(1, int(round(1.0 * s)))
        bottom_pad = max(top_pad, int(round(2.0 * s)))  # slightly larger bottom

        # Adjust clock font size too
        try:
            self.clock_font.configure(size=max(8, int(round(8 * s))))
            self._lbl_time.configure(font=self.clock_font)
        except Exception:
            pass

        # Adjust pady for all emoji buttons + clock
        for w in [*self._emoji_widgets, self._lbl_time]:
            if w is None:
                continue
            try:
                w.pack_configure(pady=(top_pad, bottom_pad))
            except Exception:
                pass

        # If back_to_top is currently visible, keep its pady tuned as well
        if self._back_top_visible and self._btn_back_top:
            try:
                self._btn_back_top.pack_configure(pady=(max(1, int(1 * s)), max(2, int(2 * s))))
            except Exception:
                pass

    def set_pin_state(self, is_on_top: bool) -> None:
        self._pin_state = bool(is_on_top)
        try:
            self._btn_pin.set_emoji(EMOJI_PIN_ON if self._pin_state else EMOJI_PIN_OFF)
            self._btn_pin.set_tooltip("Unpin window" if self._pin_state else "Pin window")
        except Exception:
            pass

    def set_time_text(self, hhmm: str) -> None:
        try:
            self._lbl_time.configure(text=to_persian_digits(hhmm))
        except Exception:
            self._lbl_time.configure(text=hhmm)

    def set_loading(self, is_loading: bool) -> None:
        if self._btn_refresh is not None:
            try:
                self._btn_refresh.set_emoji(EMOJI_LOADING if is_loading else EMOJI_REFRESH)
            except Exception:
                pass

    def set_back_top_visible(self, visible: bool) -> None:
        """Control back-to-top visibility explicitly from the main window/scroll callback."""
        visible = bool(visible)
        if visible == self._back_top_visible:
            return
        self._back_top_visible = visible
        if visible:
            if self._btn_back_top is not None:
                self._btn_back_top.pack(side=tk.LEFT, padx=(0, 2), pady=(1, 2))
        else:
            try:
                if self._btn_back_top is not None:
                    self._btn_back_top.pack_forget()
            except Exception:
                pass

    def set_news_state(self, state: str) -> None:
        self._news_state = state  # for tooltip text logic if needed

    # ---------- Click handlers ----------
    def _on_refresh_clicked(self) -> None:
        if self.on_refresh:
            self.on_refresh()

    def _on_theme_toggled(self) -> None:
        if self.on_theme_toggle:
            self.on_theme_toggle()

    def _on_back_to_top_clicked(self) -> None:
        if self.on_back_to_top:
            self.on_back_to_top()

    def _on_news_toggle_clicked(self) -> None:
        if self.on_news_toggle:
            self.on_news_toggle()

    def _on_pin_clicked(self) -> None:
        if self.on_pin_toggle:
            self.on_pin_toggle()

    # ---------- Brightness popup (compact, minimal, centered) ----------
    def _open_brightness_popup(self) -> None:
        if self._bright_win and tk.Toplevel.winfo_exists(self._bright_win):
            try:
                self._bright_win.deiconify()
                self._bright_win.lift()
                self._bright_win.focus_force()
                self._animate_popup_entry()
            except Exception:
                pass
            return

        top = self.winfo_toplevel()
        self._bright_win = tk.Toplevel(top)
        self._bright_win.transient(top)
        self._bright_win.overrideredirect(True)  # clean look (no OS frame)
        self._bright_win.resizable(False, False)
        try:
            self._bright_win.attributes("-topmost", True)
            self._bright_win.attributes("-alpha", 0.05)  # start for fade-in
        except Exception:
            pass

        # ---- card (thin outline; no heavy shadows) ----
        outline = self.t.get("OUTLINE", "#45475a")
        surface = self.t.get("SURFACE", "#1e1e2e")
        on_surface = self.t.get("ON_SURFACE", "#cdd6f4")

        self._bright_card = tk.Frame(self._bright_win, bg=outline, bd=0, highlightthickness=0)
        self._bright_card.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._bright_body = tk.Frame(self._bright_card, bg=surface, bd=0, highlightthickness=1,
                                    highlightbackground=outline)
        self._bright_body.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # ---- header (emoji + title + close) ----
        self._bright_header = tk.Frame(self._bright_body, bg=surface)
        self._bright_header.pack(fill=tk.X, padx=10, pady=(8, 4))

        icon_font = tkfont.Font(family=self.emoji_family if hasattr(self, "emoji_family") else "", size=12)
        icon_lbl = tk.Label(self._bright_header, text=EMOJI_BRIGHT, font=icon_font,
                            bg=surface, fg=on_surface, padx=0, pady=0)
        icon_lbl.pack(side=tk.LEFT)

        title_lbl = tk.Label(self._bright_header, text="Brightness", bg=surface, fg=on_surface,
                            font=tkfont.Font(size=10))
        title_lbl.pack(side=tk.LEFT, padx=6)

        self._close_btn = tk.Label(self._bright_header, text="×", bg=surface,
                                fg=self.t.get("ON_SURFACE_VARIANT", on_surface),
                                font=tkfont.Font(size=11, weight="bold"),
                                padx=6, pady=0, cursor="hand2")
        self._close_btn.pack(side=tk.RIGHT)
        self._close_btn.bind("<Button-1>", lambda e: self._close_brightness_popup())

        # ---- content ----
        content = tk.Frame(self._bright_body, bg=surface)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._bright_val_lbl = tk.Label(content, text="100%", bg=surface, fg=on_surface,
                                        font=tkfont.Font(size=18, weight="bold"))
        self._bright_val_lbl.pack(pady=(2, 6))

        # slider (minimal)
        self._bright_scale = tk.Scale(
            content, from_=0.5, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
            bg=surface, troughcolor=self.t.get("SURFACE_VARIANT", "#313244"),
            highlightthickness=0, bd=0, length=220, sliderlength=12,
            showvalue=False, relief=tk.FLAT, sliderrelief=tk.FLAT,
            activebackground=self.t.get("PRIMARY", outline),
            command=lambda _v: self._on_brightness_changed(float(self._bright_scale.get())),
        )

        # current value
        cur = 1.0
        try:
            if callable(self.get_brightness):
                cur = float(self.get_brightness())
            else:
                cur = float(top.attributes("-alpha"))
        except Exception:
            pass
        cur = max(0.5, min(1.0, cur))
        self._bright_scale.set(cur)
        self._bright_scale.pack(fill=tk.X, pady=(0, 8))

        # presets (ghost buttons: outline-only, no heavy bg)
        presets_frame = tk.Frame(content, bg=surface)
        presets_frame.pack()

        self._preset_btns = []
        presets = [("50%", 0.5), ("75%", 0.75), ("90%", 0.9), ("100%", 1.0)]
        for txt, val in presets:
            b = tk.Label(
                presets_frame, text=txt,
                bg=surface, fg=on_surface, cursor="hand2",
                font=tkfont.Font(size=9),
                padx=10, pady=4, bd=1, relief=tk.FLAT,
                highlightthickness=1, highlightbackground=outline
            )
            b.pack(side=tk.LEFT, padx=2)
            b.bind("<Button-1>", lambda e, v=val: self._set_brightness_preset(v))
            b.bind("<Enter>", lambda e, btn=b: self._on_preset_hover(btn))
            b.bind("<Leave>", lambda e, btn=b: self._on_preset_leave(btn))
            self._preset_btns.append(b)

        # live label sync
        def _sync_val(_evt=None):
            try:
                v = float(self._bright_scale.get())
                self._bright_val_lbl.configure(text=f"{int(v*100)}%")
            except Exception:
                pass

        for ev in ("<B1-Motion>", "<ButtonRelease-1>", "<Motion>"):
            self._bright_scale.bind(ev, _sync_val)

        # keys (Left/Right for fine steps)
        self._bright_win.bind("<Left>",  lambda _e: self._nudge_brightness(-0.02))
        self._bright_win.bind("<Right>", lambda _e: self._nudge_brightness(+0.02))
        self._bright_win.bind("<Escape>", lambda _e: self._close_brightness_popup())
        self._bright_win.bind("<FocusOut>", self._on_popup_focus_out)

        # place + theme + animate
        self._position_brightness_popup(top)
        self._apply_brightness_popup_theme()
        self._animate_popup_entry()

    def _position_brightness_popup(self, parent) -> None:
        try:
            self._bright_win.update_idletasks()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()

            # Compact size: always smaller than parent
            ww = min(300, max(240, int(pw * 0.36)))
            wh = min(200, max(160, int(ph * 0.32)))

            x = px + (pw - ww) // 2
            y = py + (ph - wh) // 2

            # keep inside parent bounds
            x = max(px, min(x, px + pw - ww))
            y = max(py, min(y, py + ph - wh))

            self._bright_win.geometry(f"{ww}x{wh}+{x}+{y}")
            self._bright_win.focus_force()
        except Exception:
            pass

    def _animate_popup_entry(self) -> None:
        try:
            if not (self._bright_win and tk.Toplevel.winfo_exists(self._bright_win)):
                return
            steps = 10
            for i in range(steps + 1):
                alpha = 0.05 + (0.95 - 0.05) * (i / steps)
                self._bright_win.attributes("-alpha", alpha)
                self._bright_win.update_idletasks()
                self._bright_win.after(14)
        except Exception:
            pass

    def _nudge_brightness(self, delta: float) -> None:
        try:
            v = float(self._bright_scale.get()) + float(delta)
            v = max(0.5, min(1.0, v))
            self._bright_scale.set(v)
            self._on_brightness_changed(v)
            self._bright_val_lbl.configure(text=f"{int(v*100)}%")
        except Exception:
            pass

    def _set_brightness_preset(self, value: float) -> None:
        try:
            self._bright_scale.set(value)
            self._on_brightness_changed(value)
            self._bright_val_lbl.configure(text=f"{int(value*100)}%")
        except Exception:
            pass

    def _on_preset_hover(self, button) -> None:
        try:
            button.configure(highlightbackground=self.t.get("PRIMARY", "#89b4fa"))
        except Exception:
            pass

    def _on_preset_leave(self, button) -> None:
        try:
            button.configure(highlightbackground=self.t.get("OUTLINE", "#45475a"))
        except Exception:
            pass

    def _on_popup_focus_out(self, _e=None) -> None:
        # close only if focus left the popup entirely (not moved to its children)
        try:
            f = self._bright_win.focus_displayof() if self._bright_win else None
            if not f:
                self._bright_win.after(100, self._close_brightness_popup)
        except Exception:
            pass

    def _apply_brightness_popup_theme(self) -> None:
        if not (self._bright_win and tk.Toplevel.winfo_exists(self._bright_win)):
            return
        try:
            surface = self.t.get("SURFACE", "#1e1e2e")
            on_surface = self.t.get("ON_SURFACE", "#cdd6f4")
            outline = self.t.get("OUTLINE", "#45475a")
            self._bright_win.configure(bg=surface)
            self._bright_card.configure(bg=outline)
            self._bright_body.configure(bg=surface, highlightbackground=outline)
            self._bright_header.configure(bg=surface)
            self._bright_val_lbl.configure(bg=surface, fg=on_surface)
            if self._bright_scale:
                self._bright_scale.configure(bg=surface, troughcolor=self.t.get("SURFACE_VARIANT", "#313244"),
                                            activebackground=self.t.get("PRIMARY", outline))
            for b in getattr(self, "_preset_btns", []):
                b.configure(bg=surface, fg=on_surface, highlightbackground=outline)
        except Exception:
            pass

    def _on_brightness_changed(self, level: float) -> None:
        level = max(0.5, min(1.0, float(level)))
        if callable(self.on_brightness_change):
            try:
                self.on_brightness_change(level)
                return
            except Exception:
                pass
        try:
            self.winfo_toplevel().attributes("-alpha", level)
        except Exception:
            pass

    def _close_brightness_popup(self) -> None:
        if self._bright_win and tk.Toplevel.winfo_exists(self._bright_win):
            try:
                steps = 8
                for i in range(steps, -1, -1):
                    alpha = 0.05 + (0.95 - 0.05) * (i / steps)
                    self._bright_win.attributes("-alpha", alpha)
                    self._bright_win.update_idletasks()
                    self._bright_win.after(12)
                self._bright_win.destroy()
            except Exception:
                pass
        self._bright_win = None
        self._bright_scale = None
        self._bright_card = None
        self._bright_body = None
        self._bright_header = None
        self._bright_val_lbl = None
        self._preset_btns = []

    def _apply_theme(self, theme: Dict[str, Any]) -> None:
        self.set_theme(theme)
        # Apply theme to brightness popup if it exists
        if hasattr(self, '_bright_win') and self._bright_win:
            self._apply_brightness_popup_theme()
