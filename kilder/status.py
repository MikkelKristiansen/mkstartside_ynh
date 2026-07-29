"""Værtsstatus fra statusd-agenterne."""

from concurrent.futures import ThreadPoolExecutor

import requests

from . import cache


def _hent_server(server):
    noegle = f"server/{server['url']}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt
    try:
        resp = requests.get(server["url"], timeout=2)
        resp.raise_for_status()
        data = resp.json()
        resultat = {"navn": server["navn"], "online": True, **data}
        cache.gem(noegle, resultat, ttl=30)
        return resultat
    except Exception:
        return {"navn": server["navn"], "online": False}


def hent(servere):
    if not servere:
        return []
    with ThreadPoolExecutor(max_workers=len(servere)) as pool:
        return list(pool.map(_hent_server, servere))
