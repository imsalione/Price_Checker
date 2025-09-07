# app/scrapers/twitter_service.py
# -*- coding: utf-8 -*-
"""
Lightweight wrapper around Twitter (X) API v2 via tweepy.Client.

Auth:
    - Set env var X_BEARER_TOKEN (or .env with the same key).

Functions:
    resolve_usernames(usernames) -> List[str]
    fetch_latest_tweets(
        usernames, per_user=3, exclude_replies=False, exclude_retweets=False
    ) -> List[dict]

Behavior:
    - Does NOT block on rate limits. Instead, raises RuntimeError with:
        "RATE_LIMIT:<seconds>"
      so the UI can retry later without freezing.
    - Keeps a tiny disk cache for since_id per user to avoid duplicates.
"""

from __future__ import annotations
import os
import json
import time
from typing import List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# ---- env ----
load_dotenv()
BEARER = os.getenv("X_BEARER_TOKEN", "").strip()

# ---- client (lazy) ----
_client = None
def _client_ok() -> tweepy.Client | None:
    global _client
    if not BEARER:
        return None
    if _client is None:
        # IMPORTANT: don't sleep/block; we'll handle rate limits ourselves
        _client = tweepy.Client(bearer_token=BEARER, wait_on_rate_limit=False)
    return _client

# ---- tiny cache (since_id per user id) ----
CACHE_FILE = Path("x_tweets_cache.json")

def _load_cache() -> Dict[str, Any]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_cache(data: Dict[str, Any]) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# ---- rate-limit gate (process-local) ----
_RATE_LIMIT_UNTIL = 0  # epoch seconds

def _rate_limited_seconds() -> int:
    now = int(time.time())
    return max(0, _RATE_LIMIT_UNTIL - now)

def _trip_rate_limit(seconds: int) -> None:
    global _RATE_LIMIT_UNTIL
    _RATE_LIMIT_UNTIL = max(_RATE_LIMIT_UNTIL, int(time.time()) + max(1, int(seconds)))

def _raise_rl(seconds: int) -> None:
    _trip_rate_limit(seconds)
    raise RuntimeError(f"RATE_LIMIT:{int(seconds)}")

def _handle_tweepy_error(e: Exception) -> None:
    # Tweepy v4 raises tweepy.errors.TooManyRequests on 429
    try:
        if isinstance(e, tweepy.errors.TooManyRequests):
            reset = 0
            try:
                # x-rate-limit-reset is epoch seconds
                reset = int(e.response.headers.get("x-rate-limit-reset", "0"))
            except Exception:
                reset = 0
            if reset:
                wait = max(1, reset - int(time.time()))
            else:
                wait = 420  # default cool-down
            _raise_rl(wait)
    except Exception:
        pass

    msg = str(e)
    if "429" in msg or "Too Many Requests" in msg or "Rate limit exceeded" in msg:
        _raise_rl(420)

    # unknown error -> bubble up as RuntimeError
    raise RuntimeError(msg)

# ---- public ----
def resolve_usernames(usernames: List[str]) -> List[str]:
    """Validate/normalize a list of usernames. Returns the resolved list (may be empty)."""
    api = _client_ok()
    wanted = [str(u).lstrip("@").strip() for u in (usernames or []) if str(u).strip()]
    if not wanted:
        return []
    # If currently rate-limited, skip remote call and just return input to avoid UI freeze
    if _rate_limited_seconds() > 0 or api is None:
        return wanted
    try:
        resp = api.get_users(usernames=wanted, user_fields=["name"])
        out = []
        if resp and resp.data:
            for u in resp.data:
                out.append(u.username)
        return out
    except Exception as e:
        _handle_tweepy_error(e)

def fetch_latest_tweets(
    usernames: List[str],
    per_user: int = 3,
    *,
    exclude_replies: bool = False,
    exclude_retweets: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch latest tweets from given usernames. Returns newest-first list across all users.

    If no bearer token is configured, a RuntimeError is raised.
    If rate-limited, raises RuntimeError("RATE_LIMIT:<seconds>").
    """
    api = _client_ok()
    if api is None:
        raise RuntimeError("X_BEARER_TOKEN not set (.env).")

    # Clamp to at most 5 users (hard limit)
    names = [str(u).lstrip("@").strip() for u in (usernames or []) if str(u).strip()]
    if not names:
        return []
    names = names[:5]

    # respect rate-limit gate
    rl = _rate_limited_seconds()
    if rl > 0:
        _raise_rl(rl)

    # Map usernames -> user objects
    try:
        resp = api.get_users(usernames=names, user_fields=["name"])
    except Exception as e:
        _handle_tweepy_error(e)

    if not resp or not resp.data:
        return []

    users = {u.id: {"username": u.username, "name": getattr(u, "name", u.username)} for u in resp.data}
    ids = list(users.keys())

    cache = _load_cache()
    since_map = cache.get("since", {}) if isinstance(cache.get("since"), dict) else {}

    all_out: List[Dict[str, Any]] = []

    # pull timeline per user
    for uid in ids:
        params = {
            "exclude": [],
            "max_results": 5,  # small pull; we slice per_user
            "tweet_fields": ["created_at", "text"],
        }
        if exclude_replies:
            params["exclude"].append("replies")
        if exclude_retweets:
            params["exclude"].append("retweets")

        since_id = since_map.get(str(uid))
        if since_id:
            params["since_id"] = since_id

        try:
            tl = api.get_users_tweets(id=uid, **params)
        except Exception as e:
            _handle_tweepy_error(e)

        data = tl.data or []
        data = sorted(data, key=lambda t: t.created_at or datetime.now(timezone.utc), reverse=True)

        display_name = users[uid]["name"]
        username = users[uid]["username"]
        take = data[: per_user]

        latest = since_id
        for t in take:
            created = t.created_at or datetime.now(timezone.utc)
            all_out.append({
                "id": str(t.id),
                "username": username,
                "display_name": display_name,
                "text": getattr(t, "text", ""),
                "created_at": created.astimezone(timezone.utc).isoformat(),
                "url": f"https://x.com/{username}/status/{t.id}",
            })
            if latest is None or int(t.id) > int(latest or 0):
                latest = str(t.id)

        if latest:
            since_map[str(uid)] = latest

    cache["since"] = since_map
    _save_cache(cache)
    all_out.sort(key=lambda x: x["created_at"], reverse=True)
    return all_out
