"""Seneste overskrift fra hvert RSS-feed."""

from concurrent.futures import ThreadPoolExecutor

import feedparser

from . import cache


def _laes_feed(feed):
    parsed = feedparser.parse(feed["url"])
    if not parsed.entries:
        # feedparser rejser sjældent selv — et feed der ikke kunne nås, giver
        # bare ingen poster. Det skal tælle som en fejl, så de gamle overskrifter
        # bliver stående i stedet for at blive erstattet af ingenting.
        raise ValueError(f"ingen poster i {feed['titel']}")
    entry = parsed.entries[0]
    return {
        "titel": feed["titel"],
        "seneste_titel": entry.get("title", "(Ingen titel)"),
        "seneste_url": entry.get("link", feed["url"]),
    }


def _hent_feed(feed):
    return cache.hent_eller_opdater(
        f"rss/{feed['url']}", lambda: _laes_feed(feed),
        ttl=900, maks_alder=3600,
        ved_fejl={"titel": feed["titel"], "seneste_titel": None, "seneste_url": None},
    )


def hent(feeds):
    if not feeds:
        return []
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        return list(pool.map(_hent_feed, feeds))
