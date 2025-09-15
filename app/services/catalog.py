"""
Catalog services:
- Stable IDs for items
- Pin/unpin helpers using SettingsManager
- Build display list: pinned (top) + the rest (by categories)
- NEW: Allow-list filtering to keep only the most relevant rows

Notes:
- We intentionally filter ONLY the "others" lists. Pinned items remain visible
  even if they don't match the allow-list, so users don't lose what they pinned.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import re

from app.config.settings import SettingsManager
from app.utils.numbers import normalize_text


# ---------- ID helpers ----------
def make_item_id(category: str, name: str) -> str:
    """Create a stable ID for an item based on category and normalized name."""
    norm = normalize_text(name)
    return f"{category}:{norm}"


def index_catalog(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build an ID->item index for quick lookups across all categories."""
    idx: Dict[str, Dict[str, Any]] = {}
    for cat in ("fx", "gold", "crypto"):
        for item in catalog.get(cat, []):
            _id = make_item_id(cat, item.get("name", ""))
            item2 = dict(item)
            item2["_category"] = cat
            item2["_id"] = _id
            idx[_id] = item2
    return idx


# ---------- Allow-list (compact, regex-friendly) ----------
# These patterns operate on normalize_text(name) (lowercased, Arabic variants unified, etc.)
# Adjust as needed.

# FX: keep only "Dollar" rates (various countries). We match Persian "دلار" or "USD".
_PAT_FX_ALLOW = [
    r"دلار",          # دلار آمریکا/کانادا/استرالیا/...
    r"لیر",          # لیر ترکیه
    r"یورو",         # یورو
    r"\bUSD\b",       # USD
]

# GOLD: keep only Coins (full, half, quarter) and 18k gram.
_PAT_GOLD_ALLOW = [
    r"سکه\s*(?:امامی|طرح\s*جدید|تمام)",    # سکه امامی/طرح جدید/تمام
    r"نیم\s*سکه",                           # نیم‌سکه
    r"ربع\s*سکه",                           # ربع‌سکه
    r"(?:گرم|گرمی)?\s*طل[اآ]?\s*(?:18|۱۸)\s*عیار",  # گرم طلای ۱۸ عیار (با/بی کلمه‌ی طلا/گرم)
    r"گرم\s*(?:18|۱۸)",                     # کوتاه: «گرم ۱۸»
]

# CRYPTO: keep major coins + Tether (USDT)
# We match both Persian names and common tickers.
_PAT_CRYPTO_ALLOW = [
    # Tether:
    r"\bUSDT\b", r"تتر",

    # Major coins (tickers or Persian names):
    r"\bBTC\b", r"بیت\s*کوین",
    r"\bETH\b", r"اتریوم",
    r"\bBNB\b",
    r"\bXRP\b",
    r"\bADA\b",
    r"\bSOL\b",
    r"\bDOGE\b",
    r"\bTRX\b",
    r"\bTON\b",
    r"\bAVAX\b",
    r"\bSHIB\b",
    r"\bLTC\b",
    r"\bDOT\b",
    r"\bMATIC\b",
]

def _is_allowed(category: str, name: str) -> bool:
    """
    Return True if the item name is allowed for the given category based on
    the project's requirements. Matching is done on normalized text and a few
    raw tickers using simple regex checks.
    """
    if not name:
        return False
    cat = (category or "").strip().lower()
    n = normalize_text(name)

    def _match_any(pats: List[str], text: str) -> bool:
        for p in pats:
            # First try against normalized (for Persian words, spaces, etc.)
            if re.search(p, text, flags=re.IGNORECASE):
                return True
        # Then a second pass for raw tickers in the original name (e.g., BTC, USDT)
        for p in pats:
            if re.search(p, name, flags=re.IGNORECASE):
                return True
        return False

    if cat == "fx":
        return _match_any(_PAT_FX_ALLOW, n)
    if cat == "gold":
        return _match_any(_PAT_GOLD_ALLOW, n)
    if cat == "crypto":
        return _match_any(_PAT_CRYPTO_ALLOW, n)
    # Other/unknown categories → exclude by default
    return False


# ---------- Pin management ----------
def get_pinned_ids(settings: SettingsManager) -> List[str]:
    """Return pinned IDs from settings (ordered)."""
    pins = settings.get("pinned_ids", [])
    return pins if isinstance(pins, list) else []


def set_pinned_ids(settings: SettingsManager, pins: List[str]) -> None:
    """Persist pinned IDs preserving order."""
    settings.set("pinned_ids", pins)


def pin_item(settings: SettingsManager, item_id: str) -> Tuple[bool, List[str]]:
    """Pin an item if not already pinned and within limit. Returns (changed, new_pins)."""
    pins = get_pinned_ids(settings)
    if item_id in pins:
        return False, pins
    limit = int(settings.get("pinned_limit", 5) or 5)
    if len(pins) >= limit:
        pins = pins[1:] + [item_id]  # drop oldest
    else:
        pins = pins + [item_id]
    set_pinned_ids(settings, pins)
    return True, pins


def unpin_item(settings: SettingsManager, item_id: str) -> Tuple[bool, List[str]]:
    """Unpin an item if pinned. Returns (changed, new_pins)."""
    pins = get_pinned_ids(settings)
    if item_id not in pins:
        return False, pins
    pins = [p for p in pins if p != item_id]
    set_pinned_ids(settings, pins)
    return True, pins


# ---------- Display building ----------
def build_display_lists(
    catalog: Dict[str, Any],
    settings: SettingsManager,
) -> Dict[str, Any]:
    """Return lists ready for UI:

    {
      "pinned": [items...],                  # exactly in pinned order (if exists in catalog)
      "others": {
          "fx": [...],
          "gold": [...],
          "crypto": [...]
      }
    }

    - Pinned items are preserved even if they don't match the allow-list.
    - The "others" lists are filtered by _is_allowed(...) so the UI stays compact.
    - Each item includes: name, sell/buy/price, delta_dir, unit, _category, _id
    """
    idx = index_catalog(catalog)
    pins = get_pinned_ids(settings)

    # Pinned (keep as-is if present in catalog)
    pinned_items: List[Dict[str, Any]] = []
    for pid in pins:
        it = idx.get(pid)
        if it:
            pinned_items.append(it)

    # Others (apply allow-list filtering)
    others = {"fx": [], "gold": [], "crypto": []}
    for cat in ("fx", "gold", "crypto"):
        for it in catalog.get(cat, []):
            _id = make_item_id(cat, it.get("name", ""))
            if _id in pins:
                # Skip from "others" if pinned (to avoid duplication)
                continue
            # Allow-list check
            name = str(it.get("name") or it.get("title") or "")
            if not _is_allowed(cat, name):
                continue
            it2 = dict(it)
            it2["_category"] = cat
            it2["_id"] = _id
            others[cat].append(it2)

    return {"pinned": pinned_items, "others": others}
