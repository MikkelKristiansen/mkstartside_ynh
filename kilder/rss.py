"""Seneste overskrift fra hvert RSS-feed."""

import sys
from concurrent.futures import ThreadPoolExecutor

import feedparser

from . import cache


def _hent_feed(feed):
    noegle = f"rss/{feed['url']}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt
    try:
        parsed = feedparser.parse(feed["url"])
        if parsed.entries:
            entry = parsed.entries[0]
            resultat = {
                "titel": feed["titel"],
                "seneste_titel": entry.get("title", "(Ingen titel)"),
                "seneste_url": entry.get("link", feed["url"]),
            }
            cache.gem(noegle, resultat, ttl=900)
            return resultat
    except Exception as e:
        print(f"RSS-fejl ({feed['titel']}): {e}", file=sys.stderr)
    return {"titel": feed["titel"], "seneste_titel": None, "seneste_url": None}


def hent(feeds):
    if not feeds:
        return []
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        return list(pool.map(_hent_feed, feeds))
