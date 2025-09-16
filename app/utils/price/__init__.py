# app/utils/price/__init__.py
# -*- coding: utf-8 -*-
"""
Unified Price Utils API (Toman-centric).

This package provides a cohesive, testable, and UI-friendly surface for:
  • Unit normalization: to_toman(...)
  • Delta computations: compute_delta_amount/percent/24h_amount
  • Formatting: full (thousands), compact (K/M), and deltas (toman/percent)
  • Digit helpers: Persian↔English digits, text normalization, int extraction

Import examples
---------------
from app.utils.price import (
    to_toman,
    compute_delta_amount, compute_delta_percent, compute_delta_24h_amount,
    format_thousands_toman, format_compact_toman, format_delta_toman, format_delta_percent,
    to_persian_digits, to_english_digits, normalize_text, to_int_irr,
)

Compatibility
-------------
- Provides an additional alias: `compute_daily_delta = compute_delta_24h_amount`
"""

from __future__ import annotations

from .units import to_toman
from .compute import (
    compute_delta_amount,
    compute_delta_percent,
    compute_delta_24h_amount,
)
from .digits import (
    to_persian_digits,
    to_english_digits,
    digits_to_persian,
    digits_to_english,
    normalize_text,
    to_int_irr,
)
from .format_full import (
    format_thousands_toman,
    format_full_toman,
)
from .format_compact import (
    format_compact_toman,
    short_toman,
)
from .format_delta import (
    format_delta_toman,
    format_delta_percent,
)

# Friendly alias
compute_daily_delta = compute_delta_24h_amount

__all__ = [
    # units
    "to_toman",
    # compute
    "compute_delta_amount",
    "compute_delta_percent",
    "compute_delta_24h_amount",
    "compute_daily_delta",
    # formatters
    "format_thousands_toman",
    "format_full_toman",
    "format_compact_toman",
    "short_toman",
    "format_delta_toman",
    "format_delta_percent",
    # digits/parsing
    "to_persian_digits",
    "to_english_digits",
    "digits_to_persian",
    "digits_to_english",
    "normalize_text",
    "to_int_irr",
]
