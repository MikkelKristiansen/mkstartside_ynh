"""Er der nye udgaver af docker-apps'ene?

Images er pinnet til konkrete versioner (`miniflux:2.3.3`, ikke `:latest`), så
en genstart aldrig i sig selv kan trække en ny major-version ind og brække en
database. Prisen er, at der ikke findes nogen notifikation: `docker compose
pull` på et pinnet tag henter ingenting, og man opdager først en ny udgave ved
at kigge manuelt. Paperless 3.0 lå ude i over en uge, før den blev opdaget.

Tjekket lå før på x1 som en ugentlig timer med `notify-send`. Det flyttede
hertil, fordi en bærbar er det forkerte sted at overvåge en server: er den
slukket, sker der ingenting, og en besked man klikker væk er væk for altid.
Startsiden kører på apps-mk, som er tændt døgnet rundt, og en linje på en side
kan læses igen i morgen.

Det kørende tag kommer fra statusd-agenten på docker-værten (`images` i
kilder/status.py), ikke fra en ssh herfra. Kilden er altså den samme som
prikkerne, og der er ingen ekstra nøgle at holde styr på.

Ændrer aldrig noget — rapporterer kun.
"""

import re
from concurrent.futures import ThreadPoolExecutor

import requests

from . import cache

GITHUB_API = "https://api.github.com/repos/{}/releases/latest"

# Suffikser i et image-tag, der siger noget om BYGGET og ikke om versionen:
# hvilket basis-image (`-alpine`), eller hvilket build-nummer bygherren er nået
# til (`-ls392`). De skal væk, før to versioner kan sammenlignes. Listen er
# eksplicit og ikke et generelt "alt efter foerste bindestreg", fordi
# forudgivelser som `-rc1` og `-beta2` netop ER en del af versionen og skal
# blive staaende — ellers ville en release candidate se ud som den endelige.
BYGGE_SUFFIKS = re.compile(
    r"-(?:ls\d+|alpine\d*(?:\.\d+)*|slim|debian|bookworm|bullseye|ubuntu|fpm|apache)$",
    re.IGNORECASE,
)

# GitHub tillader 60 opslag i timen uden token, og vi laver ét pr. app. Med et
# halvt døgn mellem opslagene er der ingen risiko for at ramme loftet, og en ny
# udgave er alligevel ikke noget man skal vide inden for den første time.
TTL_SVAR = 21600      # 6 timer
# Et mislykket opslag caches kortere: det kan være en forbigående rate limit
# eller et netværkshul, og der skal ikke gå seks timer, før siden retter sig.
TTL_FEJL = 1800       # 30 minutter


def _normaliser(version):
    """Gør to tags sammenlignelige.

    Projekterne er ikke enige med sig selv: shaarli udgiver "v0.16.3", miniflux
    "2.3.3", calibre-web kører LinuxServers "0.6.26-ls392" mod upstreams
    "0.6.26", og hedgedoc kører "1.11.1-alpine" mod upstreams "1.11.1". Uden
    det her ville hver eneste af dem se ud til at være bagud — og en advarsel
    der altid lyser er den samme som ingen advarsel.

    Løkken er der, fordi suffikserne kan stables ("1.2.3-fpm-alpine").
    """
    v = version.strip().lstrip("vV")
    while (kortere := BYGGE_SUFFIKS.sub("", v)) != v:
        v = kortere
    return v


def _klassificer(koerende, nyeste):
    """MAJOR, minor eller patch — så et 2→3-spring skiller sig visuelt ud fra
    et 2.3.2→2.3.3. Det er forskellen på "læs opgraderingsnoterne og tag backup
    først" og "kør pull".
    """
    a = koerende.split(".")
    b = nyeste.split(".")

    def tal(liste, i):
        try:
            return int(liste[i])
        except (IndexError, ValueError):
            return 0

    if tal(a, 0) != tal(b, 0):
        return "MAJOR"
    if tal(a, 1) != tal(b, 1):
        return "minor"
    return "patch"


def _nyeste_release(repo):
    """Nyeste release fra GitHub som (version, url) — eller (None, fejltekst)."""
    noegle = f"release/{repo}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt

    try:
        svar = requests.get(
            GITHUB_API.format(repo),
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
        )
        data = svar.json()
        if tag := data.get("tag_name"):
            resultat = (tag, data.get("html_url") or f"https://github.com/{repo}/releases")
            cache.gem(noegle, resultat, ttl=TTL_SVAR)
            return resultat
        # Typisk rate limit, eller et repo der ikke har nogen "latest".
        resultat = (None, data.get("message") or "intet svar")
    except Exception as e:
        resultat = (None, str(e) or "kunne ikke nås")

    cache.gem(noegle, resultat, ttl=TTL_FEJL)
    return resultat


def _tjek_app(app, images):
    titel = app.get("titel") or app.get("container", "")
    container = app.get("container", "")
    repo = app.get("repo", "")
    hjem = f"https://github.com/{repo}/releases"

    image = images.get(container)
    if not image:
        # Enten kører containeren ikke, eller også er agenten på værten for
        # gammel til at sende image. Begge dele er "ved det ikke" — og det er
        # ikke det samme som "alt er nyeste".
        return {"titel": titel, "tilstand": "ukendt", "url": hjem,
                "note": "kører ikke", "koerende": None}

    tag = image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else "latest"
    if tag == "latest":
        # Et rullende tag kan ikke sammenlignes med en release — `docker compose
        # pull` henter allerede det nyeste, så der er intet at opdage her.
        return {"titel": titel, "tilstand": "ukendt", "url": hjem,
                "note": "latest", "koerende": tag}

    # Andet felt er release-URL'en når opslaget lykkedes, og fejlteksten når det
    # ikke gjorde — de to udelukker hinanden, og `nyeste` fortæller hvilken.
    nyeste, url_eller_fejl = _nyeste_release(repo)
    if not nyeste:
        return {"titel": titel, "tilstand": "ukendt", "url": hjem,
                "note": url_eller_fejl, "koerende": tag}

    n_koer, n_ny = _normaliser(tag), _normaliser(nyeste)
    # Nogle projekter flytter et kortere tag med, når der kommer en hotfix:
    # Kavita udgav v0.9.1.4 uden noget 0.9.1.4-tag og flyttede i stedet 0.9.1.
    # Så er det kørende tag et forkortet navn for netop den nyeste udgave, og
    # et `docker compose pull` henter den — samme tankegang som ved `latest`.
    # Punktummet i sammenligningen sikrer, at 0.9.1 ikke matcher 0.9.10.
    if n_koer == n_ny or n_ny.startswith(n_koer + "."):
        return {"titel": titel, "tilstand": "nyeste", "url": url_eller_fejl,
                "koerende": tag, "nyeste": nyeste}

    slags = _klassificer(n_koer, n_ny)
    return {
        "titel": titel,
        # MAJOR er rød, fordi den kræver forberedelse; minor og patch er gule,
        # fordi de kan vente til på lørdag. Grøn hører til "intet at gøre".
        "tilstand": "major" if slags == "MAJOR" else "nyt",
        "slags": slags,
        "koerende": tag,
        "nyeste": nyeste,
        "url": url_eller_fejl,
    }


def hent(config_versioner, images):
    """Apps'ene fra config.yaml, hver med kørende og nyeste version.

    Uden en `versioner:`-blok returneres None, og blokken forsvinder fra siden
    — samme fald-tilbage som `backup:` og `plads: drift`: koden kan udrulles før
    konfigurationen, uden at der står noget halvt.
    """
    apps = (config_versioner or {}).get("apps") or []
    if not apps:
        return None

    with ThreadPoolExecutor(max_workers=min(8, len(apps))) as pool:
        resultat = list(pool.map(lambda a: _tjek_app(a, images), apps))

    bagud = [a for a in resultat if a["tilstand"] in ("major", "nyt")]
    ukendte = [a for a in resultat if a["tilstand"] == "ukendt"]

    return {
        "apps": resultat,
        "bagud": sorted(bagud, key=lambda a: (a["tilstand"] != "major", a["titel"])),
        "ukendte": ukendte,
        # Samlet tilstand til den ene linje, der står når der ikke er noget at
        # gøre. Ukendte apps må ikke se grønne ud: et tjek der ikke kunne
        # gennemføres er ikke et tjek der fandt ro.
        "tilstand": ("major" if any(a["tilstand"] == "major" for a in bagud)
                     else "nyt" if bagud
                     else "ukendt" if ukendte
                     else "nyeste"),
    }
