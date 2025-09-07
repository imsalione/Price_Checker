# app/utils/net.py
# -*- coding: utf-8 -*-
"""
Network utilities:
- get_html_cache_bust: fetch HTML with robust headers + cache-busting query
- is_net_ok: check for basic internet connectivity
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import time

import requests
from bs4 import BeautifulSoup

from app.config.constants import USER_AGENT, TIMEOUT


def _default_headers() -> Dict[str, str]:
    """Build a sane default header set for scraping HTML."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }


def is_net_ok(timeout: int = 5) -> bool:
    """Check for basic internet connectivity."""
    try:
        # A simple, fast HEAD request to a reliable public server
        requests.head("https://www.google.com", timeout=timeout)
        return True
    except requests.exceptions.RequestException:
        return False


def get_html_cache_bust(url: str, timeout: Optional[int] = None, extra_headers: Optional[Dict[str, str]] = None) -> Optional[BeautifulSoup]:
    """Fetch a URL and return a BeautifulSoup document with 'lxml' parser.
    - Adds a cache-busting query param (_ts=current epoch seconds).
    - Uses robust default headers (can be extended via extra_headers).
    - Returns None on any error.
    """
    try:
        ts = int(time.time())
        sep = "&" if ("?" in url) else "?"
        full_url = f"{url}{sep}_ts={ts}"
        headers = {**_default_headers(), **(extra_headers or {})}
        response = requests.get(full_url, headers=headers, timeout=timeout or TIMEOUT)
        response.raise_for_status()  # raises an HTTPError for bad responses
        return BeautifulSoup(response.text, "lxml")
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching {url}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing HTML from {url}: {e}")
        return None
