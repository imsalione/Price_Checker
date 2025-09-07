# app/ui/sparkbar.py
# -*- coding: utf-8 -*-
"""
Theme-aware SparkBar (stateful) — adaptive bar count (10..30) by canvas width.

Summary
-------
- Computes effective bar count (K) from actual canvas width W:
      K_by_w = floor((W + GAP) / (IDEAL_W + GAP))
      K      = clamp(K_by_w, MIN..MAX, <= len(history))
- Uses SPARK_BAR_GAP for inter-bar spacing and SPARK_BAR_MIN_W for minimum bar width.
- Draws positive (UP), negative (DOWN), and zero (ZERO) bars centered around a baseline.
- Tooltips show "HH:MM  |  ±Δ تومان" (or just time when Δ=0 / first bar).
- History length is NOT managed here; caller should keep ≥ SPARK_BAR_MAX_COUNT data points.

Public API
----------
    SparkBar(canvas, theme, tooltip=None)
    set_data(series, times)
    append_point(value, time_label)
    update_theme(theme)
    refresh()

Optional legacy wrapper:
    render_bars(...) -> convenience one-shot wrapper using SparkBar internally.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Callable

# --- constants (safe import with fallbacks) ---
try:
    from app.config.constants import (
        SPARK_BAR_GAP,
        SPARK_BAR_MIN_W,
        SPARK_BAR_MIN_COUNT,
        SPARK_BAR_MAX_COUNT,
        SPARK_BAR_IDEAL_W,
        SPARK_DRAW_ZERO_LINE,
        HISTORY_MAX,
    )
except Exception:  # pragma: no cover
    SPARK_BAR_GAP = 4
    SPARK_BAR_MIN_W = 5
    SPARK_BAR_MIN_COUNT = 10
    SPARK_BAR_MAX_COUNT = 30
    SPARK_BAR_IDEAL_W = 14
    SPARK_DRAW_ZERO_LINE = True
    HISTORY_MAX = 64

# Persian digits
try:
    from app.utils.numbers import to_persian_digits
except Exception:  # pragma: no cover
    def to_persian_digits(s: Any) -> str:
        return str(s)

# Tooltip duck-type (we only duck-call .show(txt, x, y) / .hide())
try:
    from app.ui.tooltip import Tooltip  # noqa: F401
except Exception:  # pragma: no cover
    class Tooltip: ...  # type: ignore


# -------------- helpers --------------
def _resolve_bg(theme: Dict[str, Any]) -> str:
    """Resolve background color from theme fallbacks."""
    for k in ("SPARK_BG", "ROW_BG", "SURFACE", "BACKGROUND", "BG"):
        v = theme.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return "#121212"

def _colors(theme: Dict[str, Any]) -> Dict[str, str]:
    """Pick semantic colors with sensible fallbacks."""
    up = theme.get("SPARK_ACCENT_UP") or theme.get("SUCCESS") or "#22d67e"
    dn = theme.get("SPARK_ACCENT_DOWN") or theme.get("ERROR") or "#ff6b6b"
    nz = theme.get("ON_SURFACE_VARIANT") or "#9aa0a6"
    return {"UP": str(up), "DOWN": str(dn), "ZERO": str(nz)}

def _coerce_series(series: Sequence[Optional[int | float]] | None) -> List[Optional[int]]:
    """Convert input series to rounded ints, preserving None."""
    if not series:
        return []
    out: List[Optional[int]] = []
    for v in series:
        if v is None:
            out.append(None)
        else:
            try:
                out.append(int(round(float(v))))
            except Exception:
                out.append(None)
    return out

def _right_align(vals: List[Any], labs: List[str]) -> tuple[List[Any], List[str]]:
    """Align values and labels by keeping the rightmost min(len) items."""
    n = min(len(vals), len(labs)) if labs else len(vals)
    return (vals[-n:], labs[-n:] if labs else [""] * n)

def _clip_last(lst: List[Any], limit: int) -> List[Any]:
    """Return last `limit` items of the list if it exceeds the limit."""
    if limit and limit > 0 and len(lst) > limit:
        return lst[-limit:]
    return lst

def _build_diffs(values: List[Optional[int]]) -> List[int]:
    """Compute first-order differences (None segments treated as 0)."""
    if not values:
        return []
    diffs: List[int] = [0]
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if a is None or b is None:
            diffs.append(0)
        else:
            diffs.append(int(b - a))
    return diffs

def _fmt_delta(d: int) -> str:
    """Format delta with sign and thousand separators in Persian digits."""
    sign = "+" if d > 0 else ""
    return to_persian_digits(f"{sign}{int(d):,} تومان")


# -------------- main class --------------
class SparkBar:
    """Stateful, theme-aware, width-adaptive spark-bar (10..30 bars).

    Notes
    -----
    - Effective bar count K is recomputed at each `refresh()` from current canvas width.
    - Legacy `SPARK_BAR_COUNT` is intentionally ignored; only MIN/MAX/IDEAL/GAP control behavior.
    """

    def __init__(self, canvas, theme: Dict[str, Any], *, tooltip: Optional[Tooltip] = None) -> None:
        self.canvas = canvas
        self.t = dict(theme or {})
        self.tooltip = tooltip
        self._values: List[Optional[int]] = []
        self._labels: List[str] = []
        self._apply_bg()

    # ---- API ----
    def set_data(self, series: Sequence[Optional[int | float]], times: Sequence[str]) -> None:
        """Set full history; last HISTORY_MAX items are kept."""
        vals = _coerce_series(series)
        labels = [str(x) if x is not None else "" for x in (times or [])]
        vals, labels = _right_align(vals, labels)
        self._values = _clip_last(vals, int(HISTORY_MAX))
        self._labels = _clip_last(labels, int(HISTORY_MAX))

    def append_point(self, value: Optional[int | float], time_label: str) -> None:
        """Append a new (value,time) or update last if time matches; keep ≤ HISTORY_MAX."""
        v: Optional[int]
        if value is None:
            v = None
        else:
            try:
                v = int(round(float(value)))
            except Exception:
                v = None
        tl = str(time_label or "")
        if self._labels and tl == self._labels[-1]:
            if self._values:
                self._values[-1] = v
        else:
            self._values.append(v)
            self._labels.append(tl)
        if len(self._values) > int(HISTORY_MAX):
            self._values = self._values[-int(HISTORY_MAX):]
            self._labels = self._labels[-int(HISTORY_MAX):]

    def update_theme(self, theme: Dict[str, Any]) -> None:
        """Replace theme mapping and re-apply background."""
        self.t = dict(theme or self.t)
        self._apply_bg()

    def refresh(self) -> None:
        """Redraw bars with *adaptive* count based on current canvas width."""
        self._apply_bg()
        try:
            self.canvas.delete("all")
        except Exception:
            pass

        # Geometry
        try:
            W = max(1, int(self.canvas.winfo_width()))
            H = max(8, int(self.canvas.winfo_height()))
        except Exception:
            W, H = 60, 12
        if W <= 2 or H <= 2 or not self._values:
            return

        colors = _colors(self.t)
        gap = max(0, int(SPARK_BAR_GAP))
        min_w = max(1, int(SPARK_BAR_MIN_W))

        total_avail = len(self._values)
        ideal_w = max(min_w, int(SPARK_BAR_IDEAL_W))

        # Width -> bar count (approx inverse of K*ideal_w + (K-1)*gap <= W)
        k_by_w = max(1, int((W + gap) // (ideal_w + gap)))
        min_bars = max(1, int(SPARK_BAR_MIN_COUNT))
        max_bars = max(min_bars, int(SPARK_BAR_MAX_COUNT))

        K = max(min_bars, min(max_bars, k_by_w, total_avail))
        if K <= 0:
            return

        # Slice last K
        values = self._values[-K:]
        labels = self._labels[-K:]
        diffs = _build_diffs(values)

        # Per-bar width to fit exactly in W (respect min_w)
        bar_w = max(min_w, (W - (K - 1) * gap) // K)
        total_w = K * bar_w + (K - 1) * gap
        x = (W - total_w) // 2  # center horizontally

        baseline_y = H // 2
        max_mag = max(1, max(abs(d) for d in diffs))

        # Zero/baseline
        if SPARK_DRAW_ZERO_LINE:
            try:
                self.canvas.create_line(0, baseline_y, W, baseline_y, fill=colors["ZERO"])
            except Exception:
                pass

        # Draw bars
        for i, d in enumerate(diffs):
            h = max(1, int(round((abs(d) / max_mag) * (H // 2))))
            y1 = baseline_y - h if d > 0 else baseline_y
            y2 = baseline_y if d > 0 else baseline_y + h
            color = colors["UP"] if d > 0 else colors["DOWN"] if d < 0 else colors["ZERO"]

            item = self.canvas.create_line(
                x + bar_w // 2, y1,
                x + bar_w // 2, y2,
                width=bar_w,
                capstyle="round",
            )
            self.canvas.itemconfigure(item, fill=color)

            # Tooltip
            if self.tooltip:
                tm = labels[i] if i < len(labels) else ""
                time_txt = to_persian_digits(tm) if tm else ""
                if i == 0 or d == 0:
                    tip = time_txt
                else:
                    tip = f"{time_txt}  |  {_fmt_delta(d)}"

                self.canvas.tag_bind(item, "<Enter>",  lambda e, txt=tip: self.tooltip.show(txt, e.x_root, e.y_root))
                self.canvas.tag_bind(item, "<Motion>", lambda e, txt=tip: self.tooltip.show(txt, e.x_root, e.y_root))
                self.canvas.tag_bind(item, "<Leave>", lambda _e: self.tooltip.hide())

            x += bar_w + gap

    # -------------- internals --------------
    def _apply_bg(self) -> None:
        """Apply background to canvas (and parent if possible)."""
        bg = _resolve_bg(self.t)
        try:
            self.canvas.configure(bg=bg, highlightthickness=0, bd=0)
        except Exception:
            pass
        try:
            parent = self.canvas.master
            if hasattr(parent, "configure"):
                parent.configure(bg=bg)
        except Exception:
            pass


# ---------- Backward-compatible convenience ----------
def render_bars(
    canvas,
    *,
    series: Sequence[Optional[int | float]],
    times: Sequence[Optional[str]],
    theme: Dict[str, Any],
    tooltip=None,
    tip_builder: Optional[Callable[[Optional[int], Optional[str], int, int], str]] = None,
    on_click: Optional[Callable[[], None]] = None,
) -> None:
    """
    Stateless convenience wrapper (for legacy call sites).
    """
    lbls = [str(t) if t is not None else "" for t in (times or [])]
    sb = SparkBar(canvas, theme, tooltip=tooltip)
    sb.set_data(series, lbls)
    sb.refresh()
    if on_click is not None:
        try:
            canvas.bind("<Button-1>", lambda _e, cb=on_click: cb(), add="+")
        except Exception:
            pass
