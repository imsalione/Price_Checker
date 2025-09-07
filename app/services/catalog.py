# app/services/catalog.py
# -*- coding: utf-8 -*-
"""
Catalog services:
- Stable IDs for items
- Pin/unpin helpers using SettingsManager
- Build display list: pinned (top) + the rest (by categories)

This module also does a *light* normalization on items so downstream
(PriceService/UI) can rely on minimal common fields:
  - name: str (trimmed)
  - price: float|int|None  (fallback: price -> sell -> buy)
  - delta_dir: "up"|"down"|"" (lower-cased, safe)
  - unit: str|None (if provided by adapter)
Other original fields are kept intact.

Output of build_display_lists:
{
  "pinned": [items...],                  # exactly in pinned order (if exists in catalog)
  "others": {
      "fx": [...],
      "gold": [...],
      "crypto": [...]
  }
}
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

from app.config.settings import SettingsManager
from app.utils.numbers import normalize_text


# ---------- ID helpers ----------

def make_item_id(category: str, name: str) -> str:
    """Create a stable ID for an item based on category and normalized name."""
    norm = normalize_text(name or "")
    return f"{category}:{norm}"


def _normalize_item_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Light, non-destructive normalization for downstream consumption.
    - Ensure 'name' exists and is a clean string.
    - Ensure 'price' exists when possible (fallback to sell/buy).
    - Normalize 'delta_dir' to up|down|"".
    - Keep 'unit' if present.
    """
    it = dict(item or {})

    # name
    name = str(it.get("name", "")).strip()
    it["name"] = name

    # price (prefer explicit 'price', otherwise sell/buy)
    price = it.get("price", None)
    if price is None:
        price = it.get("sell", None)
    if price is None:
        price = it.get("buy", None)
    it["price"] = price

    # delta_dir
    delta_dir = str(it.get("delta_dir", "") or "").strip().lower()
    if delta_dir not in ("up", "down"):
        delta_dir = ""
    it["delta_dir"] = delta_dir

    # unit (keep if present)
    # it["unit"] = it.get("unit")  # no-op; present if adapter provides

    return it


def index_catalog(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build an ID->item index for quick lookups across all categories."""
    idx: Dict[str, Dict[str, Any]] = {}
    for cat in ("fx", "gold", "crypto"):
        for item in catalog.get(cat, []) or []:
            name = str(item.get("name", "")).strip()
            _id = make_item_id(cat, name)
            item2 = _normalize_item_fields(item)
            item2["_category"] = cat
            item2["_id"] = _id
            idx[_id] = item2
    return idx


# ---------- Pin management ----------

def get_pinned_ids(settings: SettingsManager) -> List[str]:
    """Return pinned IDs from settings (ordered)."""
    pins = settings.get("pinned_ids", [])
    return pins if isinstance(pins, list) else []


def set_pinned_ids(settings: SettingsManager, pins: List[str]) -> None:
    """Persist pinned IDs preserving order."""
    settings.set("pinned_ids", pins)


def pin_item(settings: SettingsManager, item_id: str) -> Tuple[bool, List[str]]:
    """Pin an item if not already pinned and within limit.
    Returns (changed, new_pins).
    """
    pins = get_pinned_ids(settings)
    if item_id in pins:
        return False, pins
    limit = int(settings.get("pinned_limit", 5) or 5)
    if len(pins) >= limit:
        # drop the oldest (front) to keep size under limit
        pins = pins[1:] + [item_id]
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
    """Return lists ready for UI (pinned + per-category others)."""
    idx = index_catalog(catalog)
    pins = get_pinned_ids(settings)

    # Pinned, in order (skip missing IDs gracefully)
    pinned_items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for pid in pins:
        it = idx.get(pid)
        if it and pid not in seen:
            pinned_items.append(it)
            seen.add(pid)

    # Others (remove pinned)
    others = {"fx": [], "gold": [], "crypto": []}
    for cat in ("fx", "gold", "crypto"):
        for it in catalog.get(cat, []) or []:
            name = str(it.get("name", "")).strip()
            _id = make_item_id(cat, name)
            if _id in seen:
                continue
            it2 = _normalize_item_fields(it)
            it2["_category"] = cat
            it2["_id"] = _id
            others[cat].append(it2)

    return {"pinned": pinned_items, "others": others}
