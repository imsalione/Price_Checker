# app/utils/price/format_compact.py
# -*- coding: utf-8 -*-
"""
Compact (K/M) Toman formatter with Persian digits and Latin suffixes.

Scope
-----
- Render Toman amounts in a compact human-readable style per policy:
    Rules:
      - < 1,000 Toman      : plain integer (no suffix), no decimals
      - 1,000 .. < 1,000,000: K (thousand Toman)
                              <100K -> 1 decimal, >=100K -> 0 decimals
      - >= 1,000,000      : M (million Toman)
                              <10M -> 2 decimals, >=10M -> 0 decimals
    Persian digits; suffixes remain Latin (K/M).

Public API
----------
format_compact_toman(n_toman) -> str
    Return a compact string like '۱۲.۳ K', '۴۵۶ K', '۹.۵ M', or '—' for None.

Aliases
-------
short_toman = format_compact_toman
"""

from __future__ import annotations

from typing import Optional, Union

from .digits import to_persian_digits
from .rules import (
    NEUTRAL_NONE,
    compact_spec_toman,
)

Number = Union[int, float]

__all__ = ["format_compact_toman", "short_toman"]


def _format_number(val: float, decimals: int) -> str:
    """Format a number with fixed decimals, trimming trailing zeros and dot."""
    s = f"{val:.{decimals}f}" if decimals > 0 else f"{val:.0f}"
    if decimals > 0:
        s = s.rstrip("0").rstrip(".")
    return s


def format_compact_toman(n_toman: Optional[Number]) -> str:
    """Format a Toman amount using K/M compact rules and Persian digits.

    Notes
    -----
    - Preserves sign prefix for negative values (ASCII sign).
    - Returns NEUTRAL_NONE ('—') for None.
    - Unit label ('تومان') is intentionally omitted for UI flexibility.
    """
    if n_toman is None:
        return NEUTRAL_NONE

    try:
        v = float(n_toman)
    except Exception:
        return NEUTRAL_NONE

    sign = "-" if v < 0 else ""
    v_abs = abs(v)

    suffix, scaled, decimals = compact_spec_toman(v_abs)

    if suffix == "":
        # Plain integer (no decimals, thousands grouping not applied here intentionally)
        body_ascii = _format_number(scaled, 0)
        body = to_persian_digits(body_ascii)
        return sign + body

    # K or M
    body_ascii = _format_number(scaled, int(decimals))
    body = to_persian_digits(body_ascii) + f" {suffix}"
    return sign + body


# Common alias used across the UI
short_toman = format_compact_toman
