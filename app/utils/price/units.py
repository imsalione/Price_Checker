# app/utils/price/units.py
# -*- coding: utf-8 -*-
"""
Unit normalization to **Toman**.

Scope
-----
This module converts incoming values (possibly in Rial) to **integer Toman**,
using financial-style *round-half-up* when dividing Rial by 10.

Public API
----------
to_toman(value, unit=None, round_half_up=True) -> int
    Convert numeric/str input to integer Toman. If `unit` is "rial"/"irr",
    value/10 is rounded half-up to the nearest integer Toman.
    Raises ValueError on unknown units or unparseable input.

Design notes
------------
- We *do not* guess units if not provided; callers must be explicit to avoid
  silent data issues. If you know a source is always in Rial or Toman, pass it.
- Parsing of Persian digits and grouping is delegated to the digits helpers.
- Keeping the function pure makes testing straightforward.
"""

from __future__ import annotations

from typing import Union, Optional

from .digits import digits_to_english

Number = Union[int, float]


__all__ = ["to_toman", "SUPPORTED_UNITS"]

# Supported canonical unit tokens (lowercase)
SUPPORTED_UNITS = {
    "toman", "tom", "irt",
    "rial", "irr",
}


def _parse_numeric(value: Number | str) -> float:
    """Parse a numeric or numeric-like string (with Persian/ASCII digits)."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"to_toman(): unsupported value type {type(value)!r}")
    # Convert any Persian/Arabic-Indic digits to ASCII and drop common grouping
    txt = digits_to_english(value).replace(",", "").replace(" ", "")
    return float(txt)


def _round_half_up(x: float) -> int:
    """Round-half-up for positive/negative values to the nearest integer."""
    import math
    if x >= 0:
        return int(math.floor(x + 0.5))
    else:
        return int(-math.floor(-x + 0.5))


def to_toman(value: Number | str, unit: Optional[str] = None, *, round_half_up: bool = True) -> int:
    """Convert `value` to **integer Toman**.

    Parameters
    ----------
    value : Number | str
        Numeric value or numeric-like string (ASCII or Persian digits).
    unit : Optional[str]
        Explicit unit hint:
          - "toman", "tom", "irt" -> already Toman
          - "rial", "irr"         -> Rial (will be divided by 10)
        If None, no guessing is applied; we assume value is already Toman.
    round_half_up : bool, default True
        For Rial→Toman conversion: if True, use financial round-half-up.
        If False, truncate toward zero.

    Returns
    -------
    int
        Integer amount in Toman.

    Raises
    ------
    ValueError
        If the `unit` is not one of the supported tokens or input is not numeric.
    """
    num = _parse_numeric(value)
    unit_norm = (unit or "toman").strip().lower()

    if unit_norm not in SUPPORTED_UNITS:
        raise ValueError(
            f"to_toman(): unsupported unit {unit!r}; expected one of {sorted(SUPPORTED_UNITS)}"
        )

    if unit_norm in ("toman", "tom", "irt"):
        out = num
    else:  # "rial", "irr"
        out = num / 10.0

    if round_half_up and unit_norm in ("rial", "irr"):
        return _round_half_up(out)
    # For already-toman or explicit truncation path:
    return int(out)
