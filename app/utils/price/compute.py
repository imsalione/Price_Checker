# app/utils/price/compute.py
# -*- coding: utf-8 -*-
"""
Delta computations for Toman-denominated prices.

This module provides *pure* helpers to compute numeric differences independent
of any UI formatting. Always compute first, then format in presentation layers.

Public API
----------
compute_delta_amount(current_toman, previous_toman) -> int
    Signed Toman difference: current - previous (rounded to nearest int).

compute_delta_percent(current_toman, previous_toman) -> float
    Signed percent change. Returns 0.0 if previous is 0 to avoid division errors.

compute_delta_24h_amount(current_toman, previous_24h_toman=None, *, series=None, now=None) -> int
    Delta over the last 24 hours in Toman. Either pass the explicit price from
    ~24h ago (`previous_24h_toman`) or a time series of (timestamp, price) pairs.
    If `series` is provided, it must be sorted ascending by timestamp; the
    function selects the most recent value at or before `now - 24h`. If none are
    old enough, it falls back to the earliest known sample.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence, Tuple, Union

Number = Union[int, float]

__all__ = [
    "compute_delta_amount",
    "compute_delta_percent",
    "compute_delta_24h_amount",
]


def compute_delta_amount(current_toman: Number, previous_toman: Number) -> int:
    """Return signed **amount delta** (Toman) as integer: `current - previous`.

    Parameters
    ----------
    current_toman : Number
        Current price in Toman.
    previous_toman : Number
        Previous/reference price in Toman.

    Returns
    -------
    int
        Rounded integer difference (may be negative).
    """
    cur = float(current_toman)
    prev = float(previous_toman)
    return int(round(cur - prev))


def compute_delta_percent(current_toman: Number, previous_toman: Number) -> float:
    """Return signed **percent change** between two Toman values.

    Notes
    -----
    - If `previous_toman` is 0, returns 0.0 to avoid division by zero.
    - Result is a raw float (not formatted). Format in presentation layer.

    Parameters
    ----------
    current_toman : Number
        Current price in Toman.
    previous_toman : Number
        Previous/reference price in Toman.

    Returns
    -------
    float
        Percent change in the range (-∞, +∞). 0.0 if previous is 0.
    """
    cur = float(current_toman)
    prev = float(previous_toman)
    if prev == 0.0:
        return 0.0
    return ((cur - prev) / prev) * 100.0


def compute_delta_24h_amount(
    current_toman: Number,
    previous_24h_toman: Optional[Number] = None,
    *,
    series: Optional[Sequence[Tuple[datetime, Number]]] = None,
    now: Optional[datetime] = None,
) -> int:
    """Return signed **amount delta over the last 24 hours** in Toman.

    You may supply either:
      - `previous_24h_toman`: the observed price ~24 hours ago (in Toman), or
      - `series`: a sorted (ascending) sequence of (timestamp, price_toman).

    Selection rule when `series` is provided
    ---------------------------------------
    - Let `target = (now or datetime.utcnow()) - 24h`.
    - Pick the last sample with timestamp <= target.
    - If no sample satisfies the condition (i.e., all are newer than `target`),
      fall back to the earliest available sample to provide a stable baseline.

    Parameters
    ----------
    current_toman : Number
        Current price in Toman.
    previous_24h_toman : Optional[Number], default None
        Price from ~24 hours ago in Toman. If provided, `series` is ignored.
    series : Optional[Sequence[Tuple[datetime, Number]]], default None
        Optional time series sorted ascending by timestamp.
    now : Optional[datetime], default None
        Anchor time; defaults to `datetime.utcnow()`.

    Returns
    -------
    int
        Signed Toman delta over the last 24 hours. Returns 0 if neither
        `previous_24h_toman` nor a usable `series` is provided.
    """
    if previous_24h_toman is not None:
        return compute_delta_amount(current_toman, previous_24h_toman)

    if not series:
        return 0

    anchor = now or datetime.utcnow()
    target = anchor - timedelta(hours=24)

    prev_val: Optional[Number] = None
    for ts, price in series:
        if ts <= target:
            prev_val = price
        else:
            break

    if prev_val is None:
        # No sample old enough; use the earliest sample as a conservative baseline.
        prev_val = series[0][1]

    return compute_delta_amount(current_toman, prev_val)
