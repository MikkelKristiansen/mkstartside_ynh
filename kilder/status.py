"""Driftsstatus fra statusd-agenterne, samlet til ét billede."""

from concurrent.futures import ThreadPoolExecutor

import requests

from . import cache

# Felterne i JSON'en fra statusd, og den forstavelse de får i opslaget.
# "unit" i ental, fordi det er sådan man skriver det i config.yaml:
# `status: unit:flask_dnd`.
FELTER = {"lxc": "lxc", "docker": "docker", "units": "unit", "diske": "disk"}


def _spoerg_vaert(server):
    # Rejser aldrig: "svarer ikke" er også et svar, og det skal caches som et.
    # Før blev det ikke gemt, og en nede vært kostede derfor hver eneste
    # sidevisning de fulde 2 sekunders timeout.
    try:
        resp = requests.get(server["url"], timeout=2)
        resp.raise_for_status()
        return {"navn": server["navn"], "online": True, **resp.json()}
    except Exception:
        return {"navn": server["navn"], "online": False}


def _hent_vaert(server):
    # Status må højst være 3 minutter gammel, før vi hellere venter: en grøn
    # prik for noget, der er gået ned, er værre end et sekunds ventetid.
    return cache.hent_eller_opdater(
        f"server/{server['url']}", lambda: _spoerg_vaert(server),
        ttl=30, maks_alder=180,
    )


def hent(servere):
    """Alt agenterne kan fortælle, i fem dele:

    vaerter  load/RAM/temperatur/oppetid pr. vært
    opslag   {"docker:vikunja": True, ...}. En nøgle der IKKE findes betyder
             "ved det ikke" — fx alle LXC'er hvis Proxmox-agenten ikke svarer.
             Derfor er ukendt og nede to forskellige ting i visningen.
    lxc      containerne på Proxmox-værten, til driftsbjælken
    nede     alt der er nede, uanset hvor, til advarslen i driftsbjælken
    images   {"vikunja": "vikunja/vikunja:2.4.0", ...} til versionstjekket
    """
    if not servere:
        return {"vaerter": [], "opslag": {}, "lxc": [], "nede": [], "images": {}}

    with ThreadPoolExecutor(max_workers=len(servere)) as pool:
        vaerter = list(pool.map(_hent_vaert, servere))

    opslag, lxc, nede, images = {}, [], [], {}
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
                # `image` er kun med hvis agenten er ny nok til at sende det.
                # En gammel agent giver altså ingen versionslinjer frem for
                # forkerte — samme fald-tilbage som resten af siden.
                if felt == "docker" and post.get("image"):
                    images[post["navn"]] = post["image"]
        lxc.extend(vaert.get("lxc", []))

    return {
        "vaerter": vaerter, "opslag": opslag, "lxc": lxc,
        "nede": nede, "images": images,
    }
