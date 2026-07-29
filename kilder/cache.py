"""Lille TTL-cache i hukommelsen, delt af alle kilder.

Der er ingen grund til at hente vejret igen ved hver sidevisning når det kun
opdateres hver halve time. Cachen lever i processen og forsvinder ved genstart
— det er med vilje, for så er `systemctl restart` også måden at tømme den på.
"""

import time

_poste: dict = {}


def hent(noegle):
    post = _poste.get(noegle)
    if post and time.monotonic() < post["udloeb"]:
        return post["vaerdi"]
    return None


def gem(noegle, vaerdi, ttl):
    _poste[noegle] = {"vaerdi": vaerdi, "udloeb": time.monotonic() + ttl}
