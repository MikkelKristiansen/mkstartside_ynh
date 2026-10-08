"""Lille TTL-cache i hukommelsen, delt af alle kilder.

Der er ingen grund til at hente vejret igen ved hver sidevisning når det kun
opdateres hver halve time. Cachen lever i processen og forsvinder ved genstart
— det er med vilje, for så er `systemctl restart` også måden at tømme den på.

To måder at bruge den på:

- `hent`/`gem`: den simple. Er posten udløbet, henter kilden selv igen, og
  sidevisningen venter imens. Bruges af versionstjekket, der caches i timevis.
- `hent_eller_opdater`: udløbne data vises med det samme, mens nye hentes i
  baggrunden. Før ventede første visning efter en pause 3-4 sekunder på Googles
  kalendere og statusagenterne. `maks_alder` sætter grænsen for, hvor gamle
  data må vises, før vi alligevel venter — ellers kunne en side, der havde
  stået ubrugt en time, vise en times gamle status-prikker.
  mkstartside-varm.timer kalder siden hvert minut, så grænsen nås i praksis
  aldrig, og det er timeren og ikke et menneske, der venter på hentningen.
"""

import sys
import threading
import time

_poste: dict = {}
_i_gang: set = set()
_laas = threading.Lock()


def hent(noegle):
    post = _poste.get(noegle)
    if post and time.monotonic() < post["udloeb"]:
        return post["vaerdi"]
    return None


def gem(noegle, vaerdi, ttl):
    _poste[noegle] = {
        "vaerdi": vaerdi,
        "udloeb": time.monotonic() + ttl,
        "hentet": time.monotonic(),
    }


def _opdater_i_baggrunden(noegle, hent_fn, ttl):
    try:
        gem(noegle, hent_fn(), ttl)
    except Exception as e:
        # De gamle data bliver stående, og næste visning prøver igen. Det er
        # bedre end at erstatte gårsdagens kalender med en tom.
        print(f"Cache: baggrundshentning af {noegle} fejlede: {e}", file=sys.stderr)
    finally:
        with _laas:
            _i_gang.discard(noegle)


def hent_eller_opdater(noegle, hent_fn, ttl, maks_alder, ved_fejl=None):
    """Værdien for `noegle` — helst uden at vente.

    hent_fn   henter nye data; rejser en undtagelse, hvis det ikke lykkes
    ttl       sekunder, data regnes for friske
    maks_alder sekunder, udløbne data stadig må vises, mens nye hentes
    ved_fejl  hvad der returneres, hvis vi MÅTTE vente, og hentningen fejlede
    """
    post = _poste.get(noegle)
    nu = time.monotonic()

    if post and nu < post["udloeb"]:
        return post["vaerdi"]

    if post and nu - post["hentet"] < maks_alder:
        # Udløbet, men ikke for gammel: vis den og hent nye bag om ryggen. Låsen
        # sikrer, at fire samtidige visninger ikke starter fire hentninger.
        with _laas:
            start = noegle not in _i_gang
            _i_gang.add(noegle)
        if start:
            threading.Thread(
                target=_opdater_i_baggrunden,
                args=(noegle, hent_fn, ttl),
                daemon=True,
            ).start()
        return post["vaerdi"]

    # Intet i cachen (lige efter genstart, eller en ny dag i kalenderen), eller
    # for gammelt: så må vi vente.
    try:
        vaerdi = hent_fn()
    except Exception as e:
        print(f"Cache: hentning af {noegle} fejlede: {e}", file=sys.stderr)
        return ved_fejl
    gem(noegle, vaerdi, ttl)
    return vaerdi
