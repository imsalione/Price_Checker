# app/scrapers/tgju_adapter.py
# -*- coding: utf-8 -*-
"""
TGJU scraper (defensive/heuristic) — aligned with Alanchand adapter schema.

Public API:
    scrape_tgju_all() -> {
        "timestamp": "YYYY-MM-DD HH:MM:SS",
        "fx":     [ {name, sell, buy, price, delta_dir, unit}, ... ],
        "gold":   [ {...} ],
        "crypto": [ {...} ]
    }

Notes:
  - TGJU shows numbers in IRR (rial). We convert all numeric outputs to Toman.
  - We filter out non-rate blocks via centralized DEFAULT_FILTERS.
  - Mandatory category match (fx/gold/crypto).
  - Numeric sanity checks after IRR→Toman conversion.
  - Output unit is always "toman".
"""

from __future__ import annotations
from typing import Dict, List, Optional, Union
from datetime import datetime
import re
from bs4.element import Tag

# Prefer configured constant; fallback to TGJU homepage if missing.
try:
    from app.config.constants import TGJU_BASE_URL as _TGJU_URL
except Exception:
    _TGJU_URL = "https://www.tgju.org/"

from app.utils.net import get_html_cache_bust
from app.utils.price import normalize_text, to_int_irr
from app.infra.adapters.name_filters import DEFAULT_FILTERS

# -----------------------------
# Classification heuristics (aligned)
# -----------------------------
PAT_GOLD = [
    r"سکه", r"طل[اآ]", r"مثقال", r"نیم\s*سکه", r"ربع\s*سکه",
    r"گرم(?:ی)?\s*18", r"۱۸\s*عیار",
]
PAT_CRYPTO = [
    r"\bBTC\b", r"\bETH\b", r"\bBNB\b", r"\bTRX\b", r"\bDOGE\b", r"\bADA\b",
    r"\bSOL\b", r"\bXRP\b", r"\bTON\b", r"\bAVAX\b", r"\bSHIB\b",
    r"بیت\s*کوین", r"اتریوم"
]
PAT_FX = [
    r"دلار", r"یورو", r"پوند", r"لیر", r"درهم", r"یوان", r"ین",
    r"\bUSD\b", r"\bEUR\b", r"\bGBP\b", r"\bAED\b", r"\bTRY\b",
    r"\bCNY\b", r"\bJPY\b", r"\bAUD\b"
]

# Cells that likely contain prices/directions (broad heuristics for TGJU DOM)
CLASS_PRICE_HINTS = ["price", "sell", "buy", "value", "current", "priceSymbol"]

# Numeric sanity (Toman)
MIN_TOMAN = 100  # anything below this is almost certainly noise


# -----------------------------
# Helpers
# -----------------------------
def _is_match_any(text: str, patterns: List[str]) -> bool:
    """Return True if text matches any regex in patterns (case-insensitive, normalized)."""
    if not text:
        return False
    t = normalize_text(text)
    for p in patterns:
        if re.search(p, t, flags=re.IGNORECASE):
            return True
    return False


def _classify_row(name_text: str) -> Optional[str]:
    """Return 'gold' | 'crypto' | 'fx' if matched; else None."""
    if _is_match_any(name_text, PAT_GOLD):
        return "gold"
    if _is_match_any(name_text, PAT_CRYPTO):
        return "crypto"
    if _is_match_any(name_text, PAT_FX):
        return "fx"
    return None


def _r2t(v: Optional[int]) -> Optional[int]:
    """Convert a rial integer to toman integer (floor division)."""
    if v is None:
        return None
    try:
        return int(v) // 10
    except Exception:
        return None


def _extract_name_from_row(row) -> str:
    """
    Heuristically extract a 'name' from a TGJU row-like element.
    - Prefer <th>, then the first <td> that doesn't look like a price cell.
    - Fallback: strip numeric parts from the full row text.
    """
    th = row.find("th")
    if th:
        txt = th.get_text(" ", strip=True)
        if txt:
            return txt

    tds = row.find_all("td")
    for td in tds:
        cls = " ".join(td.get("class") or [])
        if any(h in cls.lower() for h in CLASS_PRICE_HINTS):
            continue
        raw = td.get_text(" ", strip=True)
        # skip pure numeric cells
        if raw and re.search(r"\d", raw) and re.fullmatch(r"[\d\s,٬٫\.%\-+]+", raw):
            continue
        if raw:
            return raw

    # Fallback: non-numeric slice of the entire row
    raw = row.get_text(" ", strip=True)
    raw = re.sub(r"[\d\s,٬٫\.%\-+]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_prices_from_row(row) -> dict:
    """
    Extract 'sell'/'buy'/'price' and direction from a TGJU row-like element.

    Strategy:
      - Prefer explicit cells by common class hints (sell/buy/current/priceSymbol).
      - Otherwise pick a likely numeric cell as single price.
      - Direction is inferred from 'priceSymbol' classes containing 'up'/'down'.
      - Returned numbers are **in Toman** (we convert from IRR).
    """
    out: dict[str, Optional[Union[int, str]]] = {"sell": None, "buy": None, "price": None, "delta_dir": None}

    def _tgju_pick(cls_pat: str):
        return row.find(class_=lambda c: c and re.search(cls_pat, " ".join(c if isinstance(c, list) else [c]), re.I))

    sell_el = _tgju_pick(r"\bsell\b") or _tgju_pick(r"\bsellPrice\b")
    buy_el  = _tgju_pick(r"\bbuy\b")  or _tgju_pick(r"\bbuyPrice\b")
    # Tighten: look for priceSymbol first (less noise than generic "price/value/current")
    cur_el  = _tgju_pick(r"\bpriceSymbol\b") or _tgju_pick(r"\bprice\b|\bcurrent\b|\bvalue\b")

    if sell_el:
        irr = to_int_irr(sell_el.get_text(" ", strip=True))
        out["sell"] = _r2t(irr)
        sym = sell_el.find(class_=lambda c: c and "priceSymbol" in c)
        if sym:
            classes = " ".join(sym.get("class") or [])
            if "up" in classes:
                out["delta_dir"] = "up"
            elif "down" in classes:
                out["delta_dir"] = "down"

    if buy_el:
        irr = to_int_irr(buy_el.get_text(" ", strip=True))
        out["buy"] = _r2t(irr)
        if out["delta_dir"] is None:
            sym = buy_el.find(class_=lambda c: c and "priceSymbol" in c)
            if sym:
                classes = " ".join(sym.get("class") or [])
                if "up" in classes:
                    out["delta_dir"] = "up"
                elif "down" in classes:
                    out["delta_dir"] = "down"

    if out["sell"] is None and out["buy"] is None:
        target = cur_el or row
        irr = to_int_irr(target.get_text(" ", strip=True))
        out["price"] = _r2t(irr)

        sym = target.find(class_=lambda c: c and "priceSymbol" in c) or row.find(class_=lambda c: c and "priceSymbol" in c)
        if sym:
            classes = " ".join(sym.get("class") or [])
            if "up" in classes:
                out["delta_dir"] = "up"
            elif "down" in classes:
                out["delta_dir"] = "down"

    # Numeric sanity (very small values are usually noise)
    for k in ("sell", "buy", "price"):
        v = out[k]
        if v is not None and isinstance(v, int) and v < MIN_TOMAN:
            out[k] = None

    return out


# -----------------------------
# Public API
# -----------------------------
def scrape_tgju_all() -> Dict[str, List[dict]]:
    """Scrape TGJU and return a categorized catalog with Toman numbers."""
    soup = get_html_cache_bust(_TGJU_URL)
    catalog = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fx": [], "gold": [], "crypto": [],
    }
    if not soup:
        return catalog

    # Collect rows from tables
    rows = []
    for tb in soup.find_all("table"):
        if isinstance(tb, Tag):
            rows.extend(tb.find_all("tr"))

    # Collect prominent price spans/cards (tightened: only priceSymbol)
    spans = soup.find_all("span", class_=lambda c: bool(c) and "priceSymbol" in c)
    for sp in spans:
        parent = sp
        hop = 0
        while parent and hop < 3 and getattr(parent, "name", None) not in ("tr", "li", "article", "section", "div"):
            parent = parent.parent
            hop += 1
        if parent and parent not in rows:
            rows.append(parent)

    # --- de-dup set on (category, normalized_name) ---
    seen: set[tuple[str, str]] = set()

    for row in rows:
        try:
            name = _extract_name_from_row(row)
            if not name:
                continue

            # Centralized blacklist (skip non-price/news blocks)
            if DEFAULT_FILTERS.is_blacklisted(name):
                continue

            # Classification MUST match one of fx/gold/crypto
            cat = _classify_row(name)
            if cat is None:
                continue

            prices = _extract_prices_from_row(row)
            if not any([prices["sell"], prices["buy"], prices["price"]]):
                continue

            key = (cat, normalize_text(name))
            if key in seen:
                continue
            seen.add(key)

            item = {
                "name": name,
                "sell": prices["sell"],
                "buy": prices["buy"],
                "price": prices["price"],
                "delta_dir": prices["delta_dir"],
                "unit": "toman",  # converted from IRR
            }
            catalog[cat].append(item)
        except Exception:
            continue

    # Sort each bucket alphabetically by normalized name
    for k in ("fx", "gold", "crypto"):
        catalog[k].sort(key=lambda x: normalize_text(x.get("name", "")))

    return catalog
