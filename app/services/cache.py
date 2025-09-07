"""
Catalog cache with TTL for Alanchand full catalog.
Saved as a JSON file on disk; can be bypassed on manual refresh.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import os
import json
import time
from datetime import datetime

from app.config.constants import CATALOG_CACHE_FILE, CATALOG_TTL_SEC
from app.infra.alanchand_adapter import scrape_alanchand_all


def _empty_catalog() -> Dict[str, Any]:
    """Return an empty catalog skeleton."""
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fx": [],
        "gold": [],
        "crypto": [],
    }


def load_catalog_cache() -> Optional[Dict[str, Any]]:
    """Load cached catalog if fresh within TTL; else None."""
    try:
        if not os.path.exists(CATALOG_CACHE_FILE):
            return None
        with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = data.get("cached_at")
        if not isinstance(cached_at, (int, float)):
            return None
        if (time.time() - cached_at) <= CATALOG_TTL_SEC:
            data.pop("cached_at", None)  # hide helper key
            return data
        return None
    except Exception:
        return None


def save_catalog_cache(catalog: Dict[str, Any]) -> None:
    """Persist catalog with 'cached_at' timestamp (best-effort)."""
    try:
        payload = dict(catalog)
        payload["cached_at"] = int(time.time())
        with open(CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_catalog_cached_or_fetch(force_refresh: bool = False) -> Dict[str, Any]:
    """Return catalog from cache if fresh (unless force_refresh), else scrape and cache."""
    if not force_refresh:
        cached = load_catalog_cache()
        if cached:
            return cached

    # Fetch fresh
    fresh = scrape_alanchand_all()
    if fresh and any((fresh.get("fx"), fresh.get("gold"), fresh.get("crypto"))):
        save_catalog_cache(fresh)
        return fresh

    # Fallback: stale cache or empty
    return load_catalog_cache() or _empty_catalog()
