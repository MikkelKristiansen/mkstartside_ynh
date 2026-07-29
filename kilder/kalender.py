"""Dagens begivenheder fra Google-kalendernes ICS-feeds."""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import recurring_ical_events
import requests
from icalendar import Calendar

from dato import TZ
from . import cache


def _hent_kalender(kalender):
    navn = kalender["navn"]
    farve = kalender["farve"]
    url = kalender["ics_url"]
    noegle = f"kal/{url}/{date.today()}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        cal = Calendar.from_ical(resp.content)
        today = date.today()
        events = recurring_ical_events.of(cal).at(today)
        resultat = []
        for e in events:
            dtstart = e.get("DTSTART").dt
            dtend = e.get("DTEND").dt if e.get("DTEND") else None
            hele_dagen = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
            if hele_dagen:
                start_str = None
                slut_str = None
            else:
                if dtstart.tzinfo is None:
                    dtstart = dtstart.replace(tzinfo=TZ)
                dtstart = dtstart.astimezone(TZ)
                start_str = dtstart.strftime("%H:%M")
                if dtend:
                    if dtend.tzinfo is None:
                        dtend = dtend.replace(tzinfo=TZ)
                    slut_str = dtend.astimezone(TZ).strftime("%H:%M")
                else:
                    slut_str = None
            resultat.append({
                "titel": str(e.get("SUMMARY", "(Uden titel)")),
                "start": start_str,
                "slut": slut_str,
                "hele_dagen": hele_dagen,
                "kalender_navn": navn,
                "kalender_farve": farve,
            })
        cache.gem(noegle, resultat, ttl=300)
        return resultat
    except Exception as e:
        print(f"Kalender-fejl ({navn}): {e}", file=sys.stderr)
        return []


def hent(kalendere):
    """Alle kalenderes begivenheder i dag, slået sammen og sorteret —
    heldagsting først, derefter efter klokkeslæt."""
    alle = []
    with ThreadPoolExecutor(max_workers=len(kalendere) or 1) as pool:
        futures = {pool.submit(_hent_kalender, k): k for k in kalendere}
        for future in as_completed(futures):
            alle.extend(future.result())
    alle.sort(key=lambda x: (0 if x["hele_dagen"] else 1, x["start"] or ""))
    return alle
