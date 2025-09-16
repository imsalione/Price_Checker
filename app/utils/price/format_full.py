# app/utils/price/format_full.py
# -*- coding: utf-8 -*-
"""
Full (thousands-grouped) Toman formatter with Persian digits.

Scope
-----
- Render integer Toman values with thousands grouping and Persian digits.
- Keep unit suffix ("تومان") out of here to keep UI flexible.
- Respect shared policy constants (glyphs, placeholders).

Public API
----------
format_thousands_toman(n_toman) -> str
    Return a string like: '۱٬۲۳۴٬۵۶۷' (or '—' for None).

Aliases
-------
format_full_toman = format_thousands_toman
"""

from __future__ import annotations

from typing import Optional

from .digits import to_persian_digits
from .rules import THOUSANDS_SEP_FA, NEUTRAL_NONE

__all__ = ["format_thousands_toman", "format_full_toman"]


def _ascii_grouped(n: int) -> str:
    """Return ASCII thousands-grouped string: e.g., 1234567 -> '1,234,567'."""
    return f"{n:,}"


def _fa_grouped(n: int) -> str:
    """Return Persian-digit string with Persian thousands separator (e.g., '۱٬۲۳۴٬۵۶۷')."""
    ascii_grp = _ascii_grouped(n).replace(",", THOUSANDS_SEP_FA)
    return to_persian_digits(ascii_grp)


def format_thousands_toman(n_toman: Optional[int]) -> str:
    """Format a full integer Toman value with Persian digits and thousands separator.

    Notes
    -----
    - Does not append any unit label (e.g., ' تومان'); caller may add if needed.
    - Returns NEUTRAL_NONE ('—') for None.
    - Preserves sign for negative values.
    """
    if n_toman is None:
        return NEUTRAL_NONE

    n = int(n_toman)
    sign = "-" if n < 0 else ""
    body = _fa_grouped(abs(n))
    return sign + body


# Common alias used across the UI
format_full_toman = format_thousands_toman
