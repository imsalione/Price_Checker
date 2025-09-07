"""
Alanchand scraper (catalog only):
- scrape_alanchand_all: full categorized catalog (fx / gold / crypto)

All numbers are parsed as integers in Toman (site convention).
"""

from __future__ import annotations
from typing import Optional, Dict, List
from datetime import datetime
import re

from app.config.constants import BASE_URL
from app.utils.net import get_html_cache_bust
from app.utils.numbers import normalize_text, to_int_irr


# -----------------------------
# Classification heuristics
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

# Cells that likely contain prices/directions
CLASS_PRICE_CELLS = ["sellPrice", "buyPrice", "priceSymbol"]


# -----------------------------
# Helpers
# -----------------------------
def _is_match_any(text: str, patterns: List[str]) -> bool:
    """Return True if text matches any regex in patterns."""
    if not text:
        return False
    t = normalize_text(text)
    for p in patterns:
        if re.search(p, t, flags=re.IGNORECASE):
            return True
    return False


def _extract_name_from_row(row) -> str:
    """Heuristically extract a 'name' cell from a row-like element.
    Prefer <th>, then first <td> that is not a price cell; else strip numbers from whole row.
    """
    th = row.find("th")
    if th:
        return th.get_text(" ", strip=True)

    tds = row.find_all("td")
    for td in tds:
        cls = td.get("class") or []
        if any(any(pc in c for pc in CLASS_PRICE_CELLS) for c in cls):
            continue
        txt = td.get_text(" ", strip=True)
        if txt:
            return txt

    # Fallback: non-numeric part of row text
    raw = row.get_text(" ", strip=True)
    raw = re.sub(r"[\d\s,٬٫\.]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_prices_from_row(row) -> dict:
    """Extract sell/buy/single price and direction from a row-like element."""
    out = {"sell": None, "buy": None, "price": None, "delta_dir": None}

    # Try explicit cells first
    sell = row.find(class_=lambda c: c and re.search(r"\bsellPrice\b", c, re.IGNORECASE))
    buy  = row.find(class_=lambda c: c and re.search(r"\bbuyPrice\b",  c, re.IGNORECASE))

    if sell:
        out["sell"] = to_int_irr(sell.get_text(" ", strip=True))
        sym = sell.find(class_=lambda c: c and "priceSymbol" in c)
        if sym:
            classes = " ".join(sym.get("class") or [])
            if "up" in classes:
                out["delta_dir"] = "up"
            elif "down" in classes:
                out["delta_dir"] = "down"

    if buy:
        out["buy"] = to_int_irr(buy.get_text(" ", strip=True))
        if out["delta_dir"] is None:
            sym = buy.find(class_=lambda c: c and "priceSymbol" in c)
            if sym:
                classes = " ".join(sym.get("class") or [])
                if "up" in classes:
                    out["delta_dir"] = "up"
                elif "down" in classes:
                    out["delta_dir"] = "down"

    # Fallback: single price (e.g., gold/coin cards)
    if out["sell"] is None and out["buy"] is None:
        price_el = row.find(class_=lambda c: c and "priceSymbol" in c) or row
        out["price"] = to_int_irr(price_el.get_text(" ", strip=True))

    return out


def _classify_row(name_text: str) -> str:
    """Return 'gold' | 'crypto' | 'fx' based on name heuristics."""
    if _is_match_any(name_text, PAT_GOLD):
        return "gold"
    if _is_match_any(name_text, PAT_CRYPTO):
        return "crypto"
    if _is_match_any(name_text, PAT_FX):
        return "fx"
    return "fx"  # default bucket


# -----------------------------
# Public API
# -----------------------------
def scrape_alanchand_all() -> Dict[str, List[dict]]:
    """Scrape Alanchand and return a categorized catalog of rates.

    Output schema:
    {
      "timestamp": "YYYY-MM-DD HH:MM:SS",
      "fx":     [ {name, sell, buy, price, delta_dir, unit}, ... ],
      "gold":   [ {...} ],
      "crypto": [ {...} ]
    }
    Numbers are integers in Toman.
    """
    soup = get_html_cache_bust(BASE_URL)
    catalog = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fx": [],
        "gold": [],
        "crypto": [],
    }
    if not soup:
        return catalog

    # Collect rows from tables
    rows = []
    for tb in soup.find_all("table"):
        rows.extend(tb.find_all("tr"))

    # Also collect prominent price spans/cards (e.g., gold/coin cards)
    spans = soup.find_all("span", class_=lambda c: c and "priceSymbol" in c)
    for sp in spans:
        parent = sp
        hop = 0
        # climb up a few levels to get a meaningful container
        while parent and hop < 3 and parent.name not in ("tr", "li", "article", "section", "div"):
            parent = parent.parent
            hop += 1
        if parent and parent not in rows:
            rows.append(parent)

    seen = set()
    for row in rows:
        name = _extract_name_from_row(row)
        if not name:
            continue

        # Avoid duplicates by normalized name (rough heuristic)
        key = normalize_text(name)
        if key in seen:
            continue

        prices = _extract_prices_from_row(row)
        if not any([prices["sell"], prices["buy"], prices["price"]]):
            continue  # nothing usable

        cat = _classify_row(name)
        item = {
            "name": name,
            "sell": prices["sell"],
            "buy": prices["buy"],
            "price": prices["price"],
            "delta_dir": prices["delta_dir"],
            "unit": "toman",  # site convention
        }
        catalog[cat].append(item)
        seen.add(key)

    # Sort each bucket alphabetically by normalized name
    for k in ("fx", "gold", "crypto"):
        catalog[k].sort(key=lambda x: normalize_text(x.get("name", "")))

    return catalog
