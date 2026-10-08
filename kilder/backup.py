"""Hvor længe siden hver backup-disk sidst kørte igennem.

Filen læses her, men skrives af x1 og x270: `~/bin/backup/publicer-backup-status.sh`
skubber den herop efter hver kørsel, og modtageren fletter pr. disk, så den
nyeste kørsel vinder uanset maskine (feltet `vaert` siger hvilken). Retningen er valgt med vilje. Havde
startsiden i stedet spurgt x1, ville svaret blive "ukendt", hver gang den
bærbare var slukket — og advarslen ville altså forsvinde præcis når man har
været væk længe og derfor IKKE har fået taget backup. Nu står tidsstemplet
stille i stedet, og alderen vokser af sig selv.

Derfor er der heller ingen "ukendt = grå"-udgang for en disk, der står i filen:
et gammelt tidsstempel er ikke manglende viden, det er dårligt nyt.
"""

import json
import os
from datetime import datetime

# Kadencerne er vidt forskellige (SeaExt dagligt i dock, CryxtNasI koldt lager
# på arbejde), så tærsklerne hører i config.yaml. Det her er kun en nødtørftig
# bund, hvis en disk er tilføjet uden tal.
STANDARD_GUL_DAGE = 2
STANDARD_ROED_DAGE = 7


def _alder_tekst(alder_sekunder):
    """Alderen sagt som et menneske ville sige den."""
    timer = alder_sekunder / 3600
    if timer < 1:
        return "lige nu"
    if timer < 24:
        t = int(timer)
        return f"{t} time siden" if t == 1 else f"{t} timer siden"
    dage = int(timer // 24)
    if dage == 1:
        return "i går"
    if dage < 14:
        return f"{dage} dage siden"
    uger = dage // 7
    return f"{uger} uger siden"


def _tilstand(disk, alder_sekunder, gul_dage, roed_dage):
    """Én af: fejl, foraeldet, gammel, frisk.

    Rækkefølgen er ikke ligegyldig. En kørsel, der endte i `bit-advarsel`, er
    frisk *i tid* men må aldrig se grøn ud — det var hele pointen med at
    mk-backup.sh overhovedet skelner. Derfor slår resultatet alderen.
    """
    if (disk.get("resultat") or "ok") != "ok":
        return "fejl"
    if alder_sekunder > roed_dage * 86400:
        return "foraeldet"
    if alder_sekunder > gul_dage * 86400:
        return "gammel"
    return "frisk"


def _laes_fil(sti):
    try:
        with open(sti, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # Ingen fil, eller en fil vi ikke forstår: så har vi ingen melding, og
        # det siger visningen så. At vælte siden over en manglende statusfil
        # ville være helt ude af proportioner.
        return None


def hent(config_backup):
    """Diskene fra config.yaml, hver med tekst og tilstand — klar til visning.

    Uden en `backup:`-blok i config.yaml returneres en tom liste, og blokken
    forsvinder fra siden. Det er samme fald-tilbage som `plads: drift`: koden
    kan udrulles før konfigurationen, uden at der står noget halvt.
    """
    if not config_backup:
        return []

    sti = config_backup.get("fil", "")
    onskede = config_backup.get("diske", [])
    if not sti or not onskede:
        return []

    data = _laes_fil(os.path.expanduser(sti)) or {}
    meldt = {d.get("navn"): d for d in data.get("diske", [])}

    nu = datetime.now()
    ud = []
    for onsket in onskede:
        navn = onsket.get("navn")
        titel = onsket.get("titel") or navn
        kadence = onsket.get("kadence", "")
        disk = meldt.get(navn)

        if not disk or not disk.get("tidspunkt"):
            # Enten er filen slet ikke nået frem, eller også kender ingen maskine
            # disken. Begge dele er "ingen melding" — ikke "aldrig kørt", for
            # det ved vi netop ikke.
            ud.append({
                "titel": titel, "kadence": kadence, "tilstand": "ukendt",
                "tekst": "ingen melding", "resultat": None,
            })
            continue

        try:
            koert = datetime.strptime(disk["tidspunkt"], "%Y-%m-%d %H:%M")
        except ValueError:
            ud.append({
                "titel": titel, "kadence": kadence, "tilstand": "ukendt",
                "tekst": "ulæseligt tidsstempel", "resultat": None,
            })
            continue

        alder = max(0.0, (nu - koert).total_seconds())
        tilstand = _tilstand(
            disk, alder,
            onsket.get("gul_dage", STANDARD_GUL_DAGE),
            onsket.get("roed_dage", STANDARD_ROED_DAGE),
        )
        ud.append({
            "titel": titel,
            "kadence": kadence,
            "tilstand": tilstand,
            "tekst": _alder_tekst(alder),
            "resultat": disk.get("resultat") if tilstand == "fejl" else None,
            "tidspunkt": disk["tidspunkt"],
            "vaert": disk.get("vaert"),
        })

    return ud
