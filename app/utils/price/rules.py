# app/utils/price/rules.py
# -*- coding: utf-8 -*-
"""
Price rules & shared constants for the Toman-centric formatting system.

This module centralizes thresholds, decimal precision, and common glyphs used
across all formatters so behavior is consistent throughout the app.

Design notes
------------
- Keep *policy* here, *logic* in the dedicated format/compute modules.
- Only include very small, generic helpers that express policy (e.g., compact spec).
- Persian-specific glyphs are defined once to avoid drift across modules.
"""

from __future__ import annotations

from typing import Tuple

__all__ = [
    # thresholds
    "K", "M",
    # decimals policy
    "DEC_K_LT_100K", "DEC_K_GE_100K",
    "DEC_M_LT_10M", "DEC_M_GE_10M",
    # glyphs / symbols
    "THOUSANDS_SEP_FA", "PERCENT_SIGN_FA", "NEUTRAL_NONE",
    "SIGN_POS", "SIGN_NEG", "SIGN_ZERO",
    # policy helpers
    "compact_spec_toman",
]

# ------------------------------ Thresholds -----------------------------------

#: Thousand and million thresholds (in Toman)
K: int = 1_000
M: int = 1_000_000

# ------------------------------ Decimals policy -------------------------------
# Compact display decimals for K and M buckets.
#: For values in [1K .. <100K): show 1 decimal place
DEC_K_LT_100K: int = 1
#: For values in [100K .. <1M): show 0 decimal places
DEC_K_GE_100K: int = 0

#: For values in [1M .. <10M): show 2 decimal places
DEC_M_LT_10M: int = 2
#: For values in [10M .. ): show 0 decimal places
DEC_M_GE_10M: int = 0

# ------------------------------ Common glyphs --------------------------------
#: Persian thousands separator
THOUSANDS_SEP_FA: str = "٬"
#: Persian percent sign
PERCENT_SIGN_FA: str = "٪"
#: Placeholder for missing/None values
NEUTRAL_NONE: str = "—"

#: Sign symbols for deltas (kept ASCII for clarity; digits convert elsewhere)
SIGN_POS: str = "+"
SIGN_NEG: str = "-"
SIGN_ZERO: str = "±"

# ------------------------------ Policy helpers --------------------------------
def compact_spec_toman(value_toman: float) -> Tuple[str, float, int]:
    """Return compact-display *policy* for a Toman value.

    Parameters
    ----------
    value_toman : float
        Absolute Toman value (use abs() upstream if you need a sign).

    Returns
    -------
    (suffix, scaled, decimals) : (str, float, int)
        - suffix: one of "", "K", "M"
        - scaled: numeric value *in that unit* (e.g., 12.3 for "K")
        - decimals: number of decimals to show according to the rules below.

    Rules
    -----
    - < 1,000 Toman      : suffix "", no decimals (plain integer UI)
    - 1,000 .. < 1,000,000: suffix "K"
                            <100K -> 1 decimal, >=100K -> 0 decimals
    - >= 1,000,000      : suffix "M"
                            <10M -> 2 decimals, >=10M -> 0 decimals
    """
    v = float(value_toman)

    if v < K:
        return "", v, 0

    if v < M:
        k = v / K
        decimals = DEC_K_LT_100K if k < 100 else DEC_K_GE_100K
        return "K", k, decimals

    m = v / M
    decimals = DEC_M_LT_10M if m < 10 else DEC_M_GE_10M
    return "M", m, decimals
