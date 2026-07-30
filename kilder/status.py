"""Driftsstatus fra statusd-agenterne, samlet til ét billede."""

from concurrent.futures import ThreadPoolExecutor

import requests

from . import cache

# Felterne i JSON'en fra statusd, og den forstavelse de får i opslaget.
# "unit" i ental, fordi det er sådan man skriver det i config.yaml:
# `status: unit:flask_dnd`.
FELTER = {"lxc": "lxc", "docker": "docker", "units": "unit"}


def _hent_vaert(server):
    noegle = f"server/{server['url']}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt
    try:
        resp = requests.get(server["url"], timeout=2)
        resp.raise_for_status()
        resultat = {"navn": server["navn"], "online": True, **resp.json()}
        cache.gem(noegle, resultat, ttl=30)
        return resultat
    except Exception:
        return {"navn": server["navn"], "online": False}


def hent(servere):
    """Alt agenterne kan fortælle, i fire dele:

    vaerter  load/RAM/temperatur/oppetid pr. vært
    opslag   {"docker:vikunja": True, ...}. En nøgle der IKKE findes betyder
             "ved det ikke" — fx alle LXC'er hvis Proxmox-agenten ikke svarer.
             Derfor er ukendt og nede to forskellige ting i visningen.
    lxc      containerne på Proxmox-værten, til driftsbjælken
    nede     alt der er nede, uanset hvor, til advarslen i driftsbjælken
    """
    if not servere:
        return {"vaerter": [], "opslag": {}, "lxc": [], "nede": []}

    with ThreadPoolExecutor(max_workers=len(servere)) as pool:
        vaerter = list(pool.map(_hent_vaert, servere))

    opslag, lxc, nede = {}, [], []
    for vaert in vaerter:
        # En vaert der er slukket efter skema er hverken oppe eller nede. Ved
        # slet ikke at saette noeglen faar den den graa "ukendt"-prik, og den
        # holdes ude af nede-listen — ellers ville NAS'en larme hver nat.
        if vaert.get("sover"):
            continue
        opslag[f"vaert:{vaert['navn']}"] = vaert["online"]
        if not vaert["online"]:
            nede.append({"vaert": vaert["navn"], "navn": "svarer ikke"})
            continue
        for felt, forstavelse in FELTER.items():
            for post in vaert.get(felt, []):
                opslag[f"{forstavelse}:{post['navn']}"] = post["oppe"]
                if not post["oppe"]:
                    nede.append({"vaert": vaert["navn"], "navn": post["navn"]})
        lxc.extend(vaert.get("lxc", []))

    return {"vaerter": vaerter, "opslag": opslag, "lxc": lxc, "nede": nede}
