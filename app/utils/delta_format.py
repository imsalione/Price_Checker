# app/utils/delta_format.py
# -*- coding: utf-8 -*-
"""
Delta formatting utilities:
- format_delta_toman: signed compact Toman (±, +, -)
- format_delta_percent: signed percent with configurable decimals
"""

from typing import Optional
from app.utils.formatting import short_toman  # K/M compact
from app.utils.numbers import to_persian_digits


def format_delta_toman(delta_value: float) -> str:
    """Return a compact signed Toman string like: +1.2M / -350K / ±0."""
    if delta_value > 0:
        sign = "+"
    elif delta_value < 0:
        sign = "-"
    else:
        sign = "±"
    body = short_toman(abs(delta_value))
    return to_persian_digits(f"{sign}{body}")


def format_delta_percent(baseline: Optional[float], delta_value: float, decimals: int = 1) -> str:
    """Return a signed percent like: +2.3٪ / -0.7٪ / ±0.0٪."""
    if not baseline or baseline == 0:
        # Show a neutral zero with decimals
        if decimals > 0:
            zeros = "0" * decimals
            return to_persian_digits(f"±0.{zeros}٪")
        return to_persian_digits("±0٪")

    pct = (delta_value / baseline) * 100.0
    if pct > 0:
        sign = "+"
    elif pct < 0:
        sign = "-"
    else:
        sign = "±"

    fmt = f"{{:.{decimals}f}}".format(abs(pct))
    return to_persian_digits(f"{sign}{fmt}٪")
