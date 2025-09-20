# app/infra/adapters/name_filters.py
# -*- coding: utf-8 -*-
"""
Centralized name filters for adapters (blacklist logic).
Use this to consistently drop non-price items (e.g., news/promos) across scrapers.

Example:
    from app.infra.adapters.name_filters import DEFAULT_FILTERS
    if DEFAULT_FILTERS.is_blacklisted(name):
        continue
"""

from __future__ import annotations
import re
from typing import Iterable, List, Optional
from app.utils.price import normalize_text


class NameFilters:
    """
    A reusable, centralized blacklist checker based on normalized text.

    Features:
      - Word-based blacklist (contains-any).
      - Optional regex-based rules for more advanced patterns.
      - Extensible at runtime via add_words/add_regexes.

    Notes:
      - All checks are applied to normalize_text(name) to unify variants/spaces.
      - Keep comments/docstrings in English (per user preference).
    """

    DEFAULT_BLACKLIST_WORDS: List[str] = [
        # General non-rate content in Persian
        "خبر", "اخبار", "ویدئو", "ویدیو", "تحلیل", "مجله", "گزارش", "مقاله", "پادکست",
        "آگهی", "تبلیغ", "اطلاعیه", "مصاحبه", "یادداشت", "بلاگ", "وبلاگ",
        # Generic UI/CTA-ish words that should not appear as rate names
        "بیشتر", "ادامه", "مطالعه", "بخوانید", "مشاهده", "کلیک", "انس", "هفته", "ماه", "سال",
        # Common noise phrases that are not actual items
        
    ]

    DEFAULT_BLACKLIST_REGEXES: List[str] = [
        # Example: anything that looks like an article/post slug-ish with hyphens and no currency words
        r"(?i)\b(خبر|گزارش|تحلیل)\b.*",
    ]

    def __init__(
        self,
        words: Optional[Iterable[str]] = None,
        regexes: Optional[Iterable[str]] = None,
    ) -> None:
        self._words: List[str] = list(words) if words else list(self.DEFAULT_BLACKLIST_WORDS)
        self._regexes: List[re.Pattern] = [re.compile(r) for r in (regexes or self.DEFAULT_BLACKLIST_REGEXES)]

    # ---------- public API ----------
    def is_blacklisted(self, name: str) -> bool:
        """Return True if the given display name is considered non-price/irrelevant."""
        if not name:
            return True  # empty/None names are not useful
        t = normalize_text(name)

        # word contains-any
        for w in self._words:
            if w and w in t:
                return True

        # regex rules
        for pat in self._regexes:
            if pat.search(t):
                return True

        return False

    def add_words(self, words: Iterable[str]) -> None:
        """Extend blacklist with additional words."""
        for w in words or []:
            w = (w or "").strip()
            if w and w not in self._words:
                self._words.append(w)

    def add_regexes(self, regexes: Iterable[str]) -> None:
        """Extend blacklist with additional regex patterns."""
        for r in regexes or []:
            r = (r or "").strip()
            if not r:
                continue
            try:
                self._regexes.append(re.compile(r))
            except re.error:
                # Ignore malformed patterns silently (or log if you have logging)
                pass


# A shared default instance that adapters can import
DEFAULT_FILTERS = NameFilters()
