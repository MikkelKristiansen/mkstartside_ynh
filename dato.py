"""Dansk tid og dansk datoformat.

Det eneste sted ugedags- og månedsnavne står skrevet, og det eneste sted
tidszonen defineres — både vejret og kalenderen regner i den.
"""

from datetime import date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Copenhagen")

DANISH_DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
DANISH_MONTHS = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def dansk_dato(d: date) -> str:
    dag = DANISH_DAYS[d.weekday()]
    return f"{dag} d. {d.day}. {DANISH_MONTHS[d.month - 1]} {d.year}"
