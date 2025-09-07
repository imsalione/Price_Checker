# app/utils/numbers.py
# -*- coding: utf-8 -*-
"""
Numbers/text utilities:
- normalize_text: trim + collapse whitespace + Persian->ASCII digits
- to_int_irr: extract first large integer from a mixed string
  (site uses Toman, but we keep legacy name for compatibility)
"""

from __future__ import annotations
import re
from typing import Optional

from app.utils.formatting import to_english_digits, to_persian_digits


def normalize_text(s: str) -> str:
    """Trim, collapse internal whitespace, and convert Persian digits/separators to ASCII."""
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return to_english_digits(s)


def to_int_irr(text: str) -> Optional[int]:
    """
    Extract the first plausible integer (e.g., '97,050' or '7,973,000') from mixed text.

    Steps:
      1) normalize: Persian digits -> ASCII, collapse spaces
      2) find first numeric token:
         - grouped:  ddd,ddd[,ddd]...
         - or plain: dddd+ (>= 4 digits to avoid tiny fragments)
      3) strip commas and convert to int

    Returns None if nothing found.
    """
    t = normalize_text(text)
    if not t:
        return None

    # prefer grouped numbers like 12,345,678; else long ungrouped 4+ digits
    m = re.search(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,})(?!\d)", t)
    if not m:
        # fallback: shorter integers (e.g., '950' if that's all we have)
        m = re.search(r"(?<!\d)(\d+)(?!\d)", t)
        if not m:
            return None

    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None


# -------- Convenience wrappers --------
def digits_to_persian(value: str | int | float) -> str:
    """Convert digits in any input (int/float/str) to Persian."""
    try:
        return to_persian_digits(str(value))
    except Exception:
        return str(value)


def digits_to_english(value: str | int | float) -> str:
    """Convert digits in any input (int/float/str) to English (ASCII)."""
    try:
        return to_english_digits(str(value))
    except Exception:
        return str(value)
