# app/utils/price/format_delta.py
# -*- coding: utf-8 -*-
"""
Delta formatters (Toman & Percent) with Persian digits and policy-based signs.

Scope
-----
- Render signed deltas for amounts (compact K/M) and percents.
- Keep logic strictly presentational; numeric computations live in `compute.py`.

Public API
----------
format_delta_toman(delta_value) -> str
    '+۱.۲ K' / '-۳۵۰ K' / '±۰' or '—' for None

format_delta_percent(baseline, delta_value, decimals=1) -> str
    '+۲.۳٪' / '-۰.۷٪' / '±۰.۰٪' (baseline==0 → neutral zero), '—' if delta is None
"""

from __future__ import annotations

from typing import Optional, Union

from .digits import to_persian_digits
from .format_compact import format_compact_toman as short_toman
from .rules import (
    NEUTRAL_NONE,
    PERCENT_SIGN_FA,
    SIGN_POS, SIGN_NEG, SIGN_ZERO,
)

Number = Union[int, float]

__all__ = ["format_delta_toman", "format_delta_percent"]


def format_delta_toman(delta_value: Optional[Number]) -> str:
    """Return a compact signed Toman delta string.

    Examples
    --------
    >>> format_delta_toman(1200)   # '+۱.۲ K'
    >>> format_delta_toman(-350_000)  # '-۳۵۰ K'
    >>> format_delta_toman(0)      # '±۰'
    >>> format_delta_toman(None)   # '—'
    """
    if delta_value is None:
        return NEUTRAL_NONE

    try:
        v = float(delta_value)
    except Exception:
        return NEUTRAL_NONE

    if v > 0:
        sign = SIGN_POS
    elif v < 0:
        sign = SIGN_NEG
    else:
        sign = SIGN_ZERO

    body = short_toman(abs(v))
    # body already uses Persian digits; sign is ASCII by design.
    return to_persian_digits(f"{sign}{body}") if body != NEUTRAL_NONE else to_persian_digits(f"{sign}0")


def format_delta_percent(
    baseline: Optional[Number],
    delta_value: Optional[Number],
    decimals: int = 1,
) -> str:
    """Return a signed percent delta like '+2.3٪' / '-0.7٪' / '±0.0٪'.

    Policy
    ------
    - If baseline is None or 0, return a neutral zero with requested decimals.
    - If delta_value is None → NEUTRAL_NONE ('—').
    - Persian digits; percent glyph taken from rules (PERCENT_SIGN_FA).

    Parameters
    ----------
    baseline : Optional[Number]
        The reference value (previous). If falsy or 0 → neutral zero output.
    delta_value : Optional[Number]
        Difference (current - baseline). If None → '—'.
    decimals : int, default 1
        Number of decimal places to display.

    Returns
    -------
    str
        Signed percent string with Persian digits (and ASCII sign).
    """
    if delta_value is None:
        return NEUTRAL_NONE

    try:
        b = float(baseline) if baseline is not None else 0.0
    except Exception:
        b = 0.0

    if b == 0.0:
        # neutral zero
        if decimals > 0:
            zeros = "0" * decimals
            return to_persian_digits(f"{SIGN_ZERO}0.{zeros}{PERCENT_SIGN_FA}")
        return to_persian_digits(f"{SIGN_ZERO}0{PERCENT_SIGN_FA}")

    try:
        d = float(delta_value)
    except Exception:
        return NEUTRAL_NONE

    pct = (d / b) * 100.0
    if pct > 0:
        sign = SIGN_POS
    elif pct < 0:
        sign = SIGN_NEG
    else:
        sign = SIGN_ZERO

    # Format with fixed decimals then trim trailing zeros/dot if decimals>0
    s = f"{abs(pct):.{int(max(0, decimals))}f}"
    if decimals > 0:
        s = s.rstrip("0").rstrip(".")
        # If trimming removed all decimals but policy wanted decimals, it's fine—UI stays clean.
    return to_persian_digits(f"{sign}{s}{PERCENT_SIGN_FA}")
