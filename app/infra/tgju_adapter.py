# app/scrapers/tgju.py
# -*- coding: utf-8 -*-
"""
TGJU scraper (defensive/heuristic) — matches the AlanChand adapter schema.

Public API:
    scrape_tgju_all() -> {
        "timestamp": "YYYY-MM-DD HH:MM:SS",
        "fx":     [ {name, sell, buy, price, delta_dir, unit}, ... ],
        "gold":   [ {...} ],
        "crypto": [ {...} ]
    }

Notes:
  - All numeric values are parsed as integers in Toman (site convention).
  - Uses the same utils as Alanchand (cache-busted fetch, normalize, to_int_irr).
  - Heuristics are defensive to tolerate DOM variations on tgju.org.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime
import re

# Prefer configured constant; fallback to homepage if missing.
try:
    from app.config.constants import TGJU_BASE_URL as _TGJU_URL
except Exception:
    _TGJU_URL = "https://www.tgju.org/"

from app.utils.net import get_html_cache_bust
from app.utils.numbers import normalize_text, to_int_irr


# ----------- Classification patterns (fa/en) -----------
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

# DOM hints (class/data-attr) — tolerant & heuristic
CLASS_PRICE_HINTS = [
    "price", "value", "current", "last", "buyPrice", "sellPrice",
    "table-cell-price", "market-price"
]
CLASS_CHANGE_HINTS = ["change", "diff", "percent", "pc", "up", "down", "priceSymbol"]
ROW_HINTS = ["market-row", "data-row", "instrument", "symbol", "row"]


# ----------- helpers -----------
def _is_match_any(text: str, patterns: List[str]) -> bool:
    """Return True if text matches any regex in patterns (case-insensitive)."""
    if not text:
        return False
    t = normalize_text(text)
    for p in patterns:
        if re.search(p, t, flags=re.IGNORECASE):
            return True
    return False


def _looks_like_price_cell(el) -> bool:
    """Guess if an element is a price-ish cell via classes or data-* attributes."""
    cls = " ".join(el.get("class") or [])
    if any(h in cls for h in CLASS_PRICE_HINTS):
        return True
    for k, v in el.attrs.items():
        if k.startswith("data-") and isinstance(v, str) and re.search(r"(price|buy|sell|last)", v, re.I):
            return True
    return False


def _looks_like_change_cell(el) -> bool:
    """Guess if an element shows change/delta."""
    cls = " ".join(el.get("class") or [])
    if any(h in cls for h in CLASS_CHANGE_HINTS):
        return True
    txt = el.get_text(" ", strip=True)
    return bool(re.search(r"[+\-]\s*\d", txt))


def _extract_name_from_row(row) -> str:
    """Extract a human-friendly instrument name from a row-like element.

    Strategy:
      1) Prefer <th>, or elements with 'data-title' / 'data-market-title'
      2) Else, first <td>/<div> not recognized as price/change cell.
      3) Fallback: clean non-numeric text from the whole row.
    """
    th = row.find("th")
    if th:
        txt = th.get_text(" ", strip=True)
        if txt:
            return txt

    for attr in ("data-title", "data-market-title", "data-name", "data-symbol-name"):
        if row.has_attr(attr) and row[attr]:
            return str(row[attr]).strip()

    for child in row.find_all(True, recursive=True):
        for attr in ("data-title", "data-market-title", "data-name", "data-symbol-name"):
            if child.has_attr(attr) and child[attr]:
                t = str(child[attr]).strip()
                if t:
                    return t

    for el in row.find_all(["td", "div", "span", "a"], recursive=True):
        if _looks_like_price_cell(el) or _looks_like_change_cell(el):
            continue
        txt = el.get_text(" ", strip=True)
        if txt and not re.search(r"^\s*[\d,٬٫\.\s]+$", txt):
            return txt

    # Fallback: strip numerics/symbols from entire row text
    raw = row.get_text(" ", strip=True)
    raw = re.sub(r"[\d\s,٬٫\.%]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_delta_dir(row) -> Optional[str]:
    """Infer direction: 'up' | 'down' | None from classes or signs in change cells."""
    cls_all = " ".join(row.get("class") or [])
    if "up" in cls_all:
        return "up"
    if "down" in cls_all:
        return "down"

    for el in row.find_all(True, recursive=True):
        cls = " ".join(el.get("class") or [])
        if "up" in cls:
            return "up"
        if "down" in cls:
            return "down"
        txt = el.get_text(" ", strip=True)
        if txt:
            if re.search(r"\+\s*\d", txt):
                return "up"
            if re.search(r"-\s*\d", txt):
                return "down"
    return None


def _extract_prices_from_row(row) -> dict:
    """Extract sell/buy/price and direction from a row-like element (int Toman)."""
    out = {"sell": None, "buy": None, "price": None, "delta_dir": None}

    def _find_cell(regex: str):
        return row.find(class_=lambda c: c and re.search(regex, c, re.I)) or \
               row.find(attrs={"data-col": re.compile(regex, re.I)})

    sell_el = _find_cell(r"\b(sell|ask)\b")
    buy_el  = _find_cell(r"\b(buy|bid)\b")

    if sell_el:
        out["sell"] = to_int_irr(sell_el.get_text(" ", strip=True))
    if buy_el:
        out["buy"] = to_int_irr(buy_el.get_text(" ", strip=True))

    if out["sell"] is None and out["buy"] is None:
        price_el = row.find(class_=lambda c: c and re.search(r"(price|value|current|last)", c, re.I))
        if not price_el:
            for el in row.find_all(["td", "div", "span"], recursive=True):
                txt = el.get_text(" ", strip=True)
                if txt and re.search(r"\d", txt) and _looks_like_price_cell(el):
                    price_el = el
                    break
        if not price_el:
            price_el = row
        out["price"] = to_int_irr(price_el.get_text(" ", strip=True))

    out["delta_dir"] = _extract_delta_dir(row)
    return out


def _classify_row(name_text: str) -> str:
    """Return 'gold' | 'crypto' | 'fx' based on name heuristics."""
    if _is_match_any(name_text, PAT_GOLD):
        return "gold"
    if _is_match_any(name_text, PAT_CRYPTO):
        return "crypto"
    if _is_match_any(name_text, PAT_FX):
        return "fx"
    return "fx"


def _collect_candidate_rows(soup) -> List:
    """Collect likely 'row' containers from TGJU homepage/cards/tables defensively."""
    rows = []

    # Tables
    for tb in soup.find_all("table"):
        rows.extend(tb.find_all("tr"))

    # Row-like containers by class hints
    for cls in ROW_HINTS:
        rows.extend(soup.find_all(class_=lambda c: c and cls in c))

    # Card-like: anything with a price-ish span → bubble to a parent container
    spans = soup.find_all("span", class_=lambda c: c and any(h in c for h in CLASS_PRICE_HINTS))
    for sp in spans:
        parent = sp
        hop = 0
        while parent and hop < 4 and parent.name not in ("tr", "li", "article", "section", "div"):
            parent = parent.parent
            hop += 1
        if parent and parent not in rows:
            rows.append(parent)

    # De-duplicate while preserving order
    uniq, seen = [], set()
    for r in rows:
        if id(r) in seen:
            continue
        uniq.append(r); seen.add(id(r))
    return uniq


# ----------- public API -----------
def scrape_tgju_all() -> Dict[str, List[dict]]:
    """Scrape TGJU and return a categorized catalog of rates (integers in Toman)."""
    soup = get_html_cache_bust(_TGJU_URL)
    catalog = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fx": [],
        "gold": [],
        "crypto": [],
    }
    if not soup:
        return catalog

    rows = _collect_candidate_rows(soup)
    seen_names = set()

    for row in rows:
        try:
            name = _extract_name_from_row(row)
            if not name:
                continue

            key = normalize_text(name)
            if not key or key in seen_names:
                continue

            prices = _extract_prices_from_row(row)
            if not any([prices["sell"], prices["buy"], prices["price"]]):
                continue

            cat = _classify_row(name)
            item = {
                "name": name,
                "sell": prices["sell"],
                "buy": prices["buy"],
                "price": prices["price"],
                "delta_dir": prices["delta_dir"],
                "unit": "toman",
            }
            catalog[cat].append(item)
            seen_names.add(key)
        except Exception:
            # Defensive: skip malformed rows
            continue

    for k in ("fx", "gold", "crypto"):
        catalog[k].sort(key=lambda x: normalize_text(x.get("name", "")))

    return catalog
