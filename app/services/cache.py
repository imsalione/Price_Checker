# app/services/cache.py
# -*- coding: utf-8 -*-
"""
Multi-source catalog cache with TTL (AlanChand + TGJU) and safe merging.

Public API:
    get_catalog_cached_or_fetch(force_refresh: bool = False) -> Dict[str, Any]

Behavior:
    - Keeps a separate on-disk JSON cache per source (e.g., AlanChand, TGJU).
    - If a source cache is fresh (within TTL), uses it; otherwise scrapes that source only.
    - Merges sources into a single catalog (fx/gold/crypto), de-duplicated by (category, normalized name).
    - Source priority is taken from constants.CATALOG_SOURCES if present; else defaults to ('alanchand', 'tgju').

Notes:
    - Numeric values are assumed to be integers in Toman (aligned with adapters).
    - Import paths for adapters are resilient: tries infra/ -> scrapers/ -> flat fallbacks.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import os
import json
import time
from datetime import datetime

# ---------- Constants (with safe fallbacks) ----------
try:
    from app.config.constants import CATALOG_TTL_SEC as _TTL
except Exception:
    _TTL = 600  # seconds (10 minutes)

# Legacy AlanChand cache file (kept for backwards-compatibility)
try:
    from app.config.constants import CATALOG_CACHE_FILE as _ALAN_FILE
except Exception:
    _ALAN_FILE = "alanchand_catalog_cache.json"

# TGJU cache file (optional; fallback if not defined)
try:
    from app.config.constants import TGJU_CACHE_FILE as _TGJU_FILE
except Exception:
    _TGJU_FILE = "tgju_catalog_cache.json"

# Enabled sources & their merge priority (left-most wins on conflicts)
try:
    from app.config.constants import CATALOG_SOURCES as _SOURCES
    _SOURCES = tuple(str(s).strip().lower() for s in (_SOURCES or ()))
    if not _SOURCES:
        _SOURCES = ("alanchand", "tgju")
except Exception:
    _SOURCES = ("alanchand", "tgju")


# ---------- Adapters (import robustly) ----------
# AlanChand adapter
_scrape_alanchand = None
try:
    # Preferred (infra adapter)
    from app.infra.alanchand_adapter import scrape_alanchand_all as _scrape_alanchand
except Exception:
    try:
        # Common alternative (scrapers package)
        from app.scrapers.alanchand import scrape_alanchand_all as _scrape_alanchand
    except Exception:
        try:
            # Flat fallback (rare)
            from app.alanchand import scrape_alanchand_all as _scrape_alanchand
        except Exception:
            _scrape_alanchand = None

# TGJU adapter
_scrape_tgju = None
try:
    # Preferred (infra adapter)
    from app.infra.tgju_adapter import scrape_tgju_all as _scrape_tgju
except Exception:
    try:
        # Common alternative (scrapers package)
        from app.scrapers.tgju import scrape_tgju_all as _scrape_tgju
    except Exception:
        try:
            # Flat fallback (rare)
            from app.tgju import scrape_tgju_all as _scrape_tgju
        except Exception:
            _scrape_tgju = None


# ---------- Utilities ----------
try:
    from app.utils.numbers import normalize_text
except Exception:
    def normalize_text(s: str) -> str:
        """Ultra-light fallback normalizer (lowercase + trim)."""
        return (s or "").strip().lower()


def _empty_catalog() -> Dict[str, Any]:
    """Return an empty catalog skeleton with a current timestamp."""
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fx": [],
        "gold": [],
        "crypto": [],
    }


def _load_cache(path: str, ttl: int) -> Optional[Dict[str, Any]]:
    """Load cached catalog from disk if fresh within TTL; otherwise return None."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = data.get("cached_at")
        if not isinstance(cached_at, (int, float)):
            return None
        if (time.time() - cached_at) <= ttl:
            data.pop("cached_at", None)  # hide helper key
            return data
        return None
    except Exception:
        return None


def _save_cache(path: str, catalog: Dict[str, Any]) -> None:
    """Persist catalog to disk with a 'cached_at' timestamp (best-effort)."""
    try:
        payload = dict(catalog)
        payload["cached_at"] = int(time.time())
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _scrape_source(name: str) -> Dict[str, Any]:
    """Call the appropriate scraper function for a given source name."""
    n = (name or "").strip().lower()
    if n == "alanchand":
        return _scrape_alanchand() if _scrape_alanchand else _empty_catalog()
    if n == "tgju":
        return _scrape_tgju() if _scrape_tgju else _empty_catalog()
    # Unknown source → return empty
    return _empty_catalog()


def _cache_file_for(name: str) -> str:
    """Return the on-disk cache filename for the given source name."""
    n = (name or "").strip().lower()
    if n == "alanchand":
        return _ALAN_FILE
    if n == "tgju":
        return _TGJU_FILE
    # Fallback: one file per unknown name
    return f"{n}_catalog_cache.json"

# ---- unit normalization helpers ----
try:
    from app.config.constants import CANONICAL_UNIT, SOURCE_DEFAULT_UNITS, UNIT_CONV_FACTORS
except Exception:
    CANONICAL_UNIT = "toman"
    SOURCE_DEFAULT_UNITS = {"alanchand": "toman", "tgju": "toman"}
    UNIT_CONV_FACTORS = {("toman", "toman"): 1.0, ("rial", "toman"): 0.1, ("toman", "rial"): 10.0, ("rial", "rial"): 1.0}

def _get_factor(src_unit: str, dst_unit: str) -> float:
    src = (src_unit or "").strip().lower() or "toman"
    dst = (dst_unit or "").strip().lower() or "toman"
    return float(UNIT_CONV_FACTORS.get((src, dst), 1.0))

def _scale_value(v, factor: float):
    if v is None:
        return None
    try:
        return int(round(float(v) * factor))
    except Exception:
        return v

def _normalize_item_unit(item: Dict[str, Any], src_unit: str, target_unit: str) -> Dict[str, Any]:
    # if item carries its own unit, prefer it; else fall back to per-source unit
    u = (item.get("unit") or src_unit or "").strip().lower() or "toman"
    if u == target_unit:
        item["unit"] = target_unit
        return item
    f = _get_factor(u, target_unit)
    for key in ("price", "sell", "buy"):
        if key in item:
            item[key] = _scale_value(item[key], f)

    # Optional: normalize history arrays if present (absolute prices)
    if isinstance(item.get("history"), list):
        item["history"] = [_scale_value(x, f) for x in item["history"]]
    item["unit"] = target_unit
    return item

def _normalize_catalog_units(cat: Dict[str, Any], src_name: str, target_unit: str) -> Dict[str, Any]:
    """Convert all items in catalog from (source's unit or item.unit) to target_unit."""
    src_unit = (SOURCE_DEFAULT_UNITS.get(src_name) or "toman").strip().lower()
    out = {
        "timestamp": cat.get("timestamp"),
        "fx": [], "gold": [], "crypto": [],
    }
    for cat_name in ("fx", "gold", "crypto"):
        for item in cat.get(cat_name, []) or []:
            out[cat_name].append(_normalize_item_unit(dict(item), src_unit, target_unit))
    return out


def _merge_catalogs(prioritized_sources: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Merge multiple catalogs into one with category-wise de-duplication.

    Rules:
      - First source in the list has higher priority (its item wins on conflicts).
      - De-duplication key: (category, normalized name).
      - Timestamp: the newest non-empty timestamp across sources is used.
    """
    merged = {"timestamp": None, "fx": [], "gold": [], "crypto": []}

    # Pick the latest timestamp
    for _, cat in prioritized_sources:
        ts = str(cat.get("timestamp") or "")
        if ts and (merged["timestamp"] is None or ts > merged["timestamp"]):
            merged["timestamp"] = ts

    # Merge items category-wise with de-dup
    for cat_name in ("fx", "gold", "crypto"):
        seen: set[Tuple[str, str]] = set()
        for _src_name, src in prioritized_sources:
            for item in src.get(cat_name, []) or []:
                nm = str(item.get("name", "")).strip()
                key = (cat_name, normalize_text(nm))
                if not nm or key in seen:
                    continue
                merged[cat_name].append(dict(item))  # shallow copy keeps original fields
                seen.add(key)

    if merged["timestamp"] is None:
        merged["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return merged


# ---------- Public API ----------
def get_catalog_cached_or_fetch(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Return a merged catalog across enabled sources using per-source caches with TTL.

    Args:
        force_refresh: If True, bypass disk caches and scrape fresh for each source.

    Returns:
        A dict with the merged catalog:
        {
            "timestamp": "YYYY-MM-DD HH:MM:SS",
            "fx":     [ ... ],
            "gold":   [ ... ],
            "crypto": [ ... ]
        }
    """
    sources = list(_SOURCES)  # e.g., ("alanchand", "tgju")
    per_source_results: List[Tuple[str, Dict[str, Any]]] = []

    for name in sources:
        path = _cache_file_for(name)
        data: Optional[Dict[str, Any]] = None

        if not force_refresh:
            data = _load_cache(path, _TTL)

        if data is None:
            fresh = _scrape_source(name)
            if fresh and any((fresh.get("fx"), fresh.get("gold"), fresh.get("crypto"))):
                _save_cache(path, fresh)
                data = fresh
            else:
                data = _load_cache(path, _TTL) or _empty_catalog()

        # ✅ normalize units to canonical before merging
        data = _normalize_catalog_units(data, name, CANONICAL_UNIT)

        per_source_results.append((name, data))

    # Merge by declared priority order
    return _merge_catalogs(per_source_results)
