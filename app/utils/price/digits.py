# app/utils/price/digits.py
# -*- coding: utf-8 -*-
"""
Digit conversion & lightweight parsing utilities (Persian ↔ English).

Scope
-----
This module provides:
  • Conversion between Persian digits/separators and ASCII (English) digits.
  • Text normalization for mixed Persian/English content.
  • Basic integer extraction from free-form text (e.g., "7,973,000 ریال" → 7973000).

Design principles
-----------------
- Keep functions *pure* and side‑effect free.
- Parsing remains intentionally minimal: it's a best‑effort extractor for UI feeds
  and headlines, not a full NLU parser.
- Formatting of Toman values happens in the dedicated formatter modules.
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = [
    # conversion
    "to_english_digits",
    "to_persian_digits",
    "digits_to_english",
    "digits_to_persian",
    # normalization / parsing
    "normalize_text",
    "to_int_irr",
]

# Translation maps
# Persian digits: ۰۱۲۳۴۵۶۷۸۹
# Persian separators: U+066C (Arabic thousands) or U+066B (Arabic decimal) are *not* used here.
# We explicitly map Persian thousands '٬' (U+066C ARABIC THOUSANDS SEPARATOR) to ','
# and Persian decimal  '٫' (U+066B ARABIC DECIMAL SEPARATOR)   to '.'
P2E = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,.")  # Persian → ASCII (note: ensure order covers Persian chars)
# Some keyboards may insert Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩). Map those too:
P2E_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

E2P = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")       # ASCII → Persian


def _to_english_core(s: str) -> str:
    """Internal: convert Persian/Arabic‑Indic digits & separators to ASCII digits/separators."""
    s = s.translate(P2E)           # Persian digits + Persian separators
    s = s.translate(P2E_ARABIC_INDIC)  # Arabic‑Indic digits (in case they appear)
    return s


def to_english_digits(s: str) -> str:
    """Convert Persian/Arabic‑Indic digits & separators to ASCII (English).

    Notes
    -----
    - Persian thousands (٬) → ','
    - Persian decimal  (٫) → '.'
    - Arabic‑Indic digits are also supported.
    """
    if not isinstance(s, str):
        return s
    return _to_english_core(s)


def to_persian_digits(s: str) -> str:
    """Convert ASCII digits to Persian digits (۰..۹). Non-digit characters are preserved."""
    if not isinstance(s, str):
        s = str(s)
    return s.translate(E2P)


def digits_to_persian(value: str | int | float) -> str:
    """Convenience wrapper to render any value with Persian digits."""
    try:
        return to_persian_digits(str(value))
    except Exception:
        return str(value)


def digits_to_english(value: str | int | float) -> str:
    """Convenience wrapper to convert any value to ASCII digits (and separators)."""
    try:
        return to_english_digits(str(value))
    except Exception:
        return str(value)


def normalize_text(s: str) -> str:
    """Normalize free-form text to a clean ASCII-digit string.

    Steps
    -----
    1) Strip leading/trailing whitespace
    2) Collapse internal whitespace to single spaces
    3) Convert all digits/separators to ASCII (English)
    """
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return _to_english_core(s)


def to_int_irr(text: str) -> Optional[int]:
    """Extract the first plausible integer from mixed text (ASCII or Persian digits).

    Strategy (in order)
    -------------------
    1) Look for grouped numbers: ddd,ddd[,ddd]...
    2) Else look for a sequence of ≥4 digits (to avoid tiny fragments)
    3) Else fallback to any digit sequence

    Parameters
    ----------
    text : str
        Free-form text (e.g., headlines, UI feeds). May contain Persian digits.

    Returns
    -------
    Optional[int]
        Extracted integer or None if not found.

    Examples
    --------
    >>> to_int_irr('قیمت امروز: 97,050')
    97050
    >>> to_int_irr('7,973,000 ریال')
    7973000
    >>> to_int_irr('حدوداً 950 تومن')
    950
    """
    t = normalize_text(text)
    if not t:
        return None

    m = re.search(r"(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)", t)
    if not m:
        m = re.search(r"(?<!\d)(\d{4,})(?!\d)", t)
        if not m:
            m = re.search(r"(?<!\d)(\d+)(?!\d)", t)
            if not m:
                return None

    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None
