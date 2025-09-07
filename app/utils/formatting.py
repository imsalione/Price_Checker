# app/utils/formatting.py
# -*- coding: utf-8 -*-
"""
Formatting utilities (Toman-based):
- Persian/English digit conversion
- Thousand-grouped formatting (Toman)
- Compact Toman formatter for UI (K/M)
- Aliases to match project-wide naming: short_toman, format_full_toman
"""

from __future__ import annotations
from typing import Optional

__all__ = [
    "to_english_digits",
    "to_persian_digits",
    "format_price_full_toman",
    "format_price_compact",
    # Aliases used elsewhere in the project:
    "short_toman",
    "format_full_toman",
]

# Digit translation maps
P2E = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,.")
E2P = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# -------- digit helpers --------
def to_english_digits(s: str) -> str:
    """Convert Persian digits/separators to ASCII."""
    if not isinstance(s, str):
        return s
    return s.translate(P2E)


def to_persian_digits(s: str) -> str:
    """Convert ASCII digits to Persian digits."""
    if not isinstance(s, str):
        s = str(s)
    return s.translate(E2P)


# -------- base number formatting (Toman) --------
def _thousands_sep(n: int) -> str:
    """Return an ASCII thousands-separated string like 12,345,678."""
    return f"{n:,}"


def _fa_thousands_toman(n: int) -> str:
    """Return Persian-digit string with Persian thousands separator (٬)."""
    ascii_grp = _thousands_sep(n).replace(",", "٬")
    return to_persian_digits(ascii_grp)


def format_price_full_toman(n: Optional[int]) -> str:
    """Format a full integer Toman value with thousands grouping (digits in Persian).
    No unit suffix returned; caller can append ' تومان' if needed.
    """
    if n is None:
        return "—"
    sign = "-" if n < 0 else ""
    n_abs = abs(int(n))
    return sign + _fa_thousands_toman(n_abs)


# -------- compact Toman formatter for UI column (K/M) --------
def format_price_compact(n_toman: Optional[int]) -> str:
    """Compact formatter based on *Toman* (no unit suffix).
    Rules:
      - < 1,000 Toman      : plain integer (no suffix), no decimals
      - 1,000 .. < 1,000,000: K (thousand Toman)
                              <100K -> 1 decimal, >=100K -> 0 decimals
      - >= 1,000,000      : M (million Toman)
                              <10M -> 2 decimals, >=10M -> 0 decimals
    Persian digits; suffixes remain Latin (K/M).
    """
    if n_toman is None:
        return "—"

    t = float(n_toman)
    sign = "-" if t < 0 else ""
    t = abs(t)

    # < 1K: plain
    if t < 1_000:
        s = _fa_thousands_toman(int(round(t)))
        return sign + s if sign else s

    # 1K .. < 1M: K
    if t < 1_000_000:
        k = t / 1_000.0
        s = f"{k:.1f}" if k < 100 else f"{k:.0f}"
        s = s.rstrip("0").rstrip(".")
        s = to_persian_digits(s) + " K"
        return (sign + s) if sign else s

    # >= 1M: M
    m = t / 1_000_000.0
    s = f"{m:.2f}" if m < 10 else f"{m:.0f}"
    s = s.rstrip("0").rstrip(".")
    s = to_persian_digits(s) + " M"
    return (sign + s) if sign else s


# -------- Aliases to match other modules' expected names --------
# Many parts of the project import these names:
short_toman = format_price_compact
format_full_toman = format_price_full_toman
