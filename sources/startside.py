import sys
import os
import time
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

import feedparser
import requests
import yaml
from flask import Flask, render_template
from icalendar import Calendar
import recurring_ical_events

CONFIG_PATH = os.environ.get(
    "MKSTARTSIDE_CONFIG",
    os.path.join(os.path.dirname(__file__), "config.yaml"),
)
TZ = ZoneInfo("Europe/Copenhagen")

WMO_CODES = {
    0:  ("☀️",  "Klart"),
    1:  ("🌤️", "Mest klart"),
    2:  ("⛅",  "Delvist skyet"),
    3:  ("☁️",  "Overskyet"),
    45: ("🌫️", "Tåge"),
    48: ("🌫️", "Rimtåge"),
    51: ("🌦️", "Let støvregn"),
    53: ("🌦️", "Støvregn"),
    55: ("🌧️", "Kraftig støvregn"),
    61: ("🌧️", "Let regn"),
    63: ("🌧️", "Regn"),
    65: ("🌧️", "Kraftig regn"),
    71: ("🌨️", "Let sne"),
    73: ("🌨️", "Sne"),
    75: ("❄️",  "Kraftig sne"),
    77: ("🌨️", "Snekorn"),
    80: ("🌦️", "Let byger"),
    81: ("🌧️", "Byger"),
    82: ("⛈️",  "Kraftige byger"),
    85: ("🌨️", "Snebyger"),
    86: ("❄️",  "Kraftige snebyger"),
    95: ("⛈️",  "Tordenvejr"),
    96: ("⛈️",  "Tordenvejr med hagl"),
    99: ("⛈️",  "Kraftigt tordenvejr med hagl"),
}

DANISH_DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
DANISH_MONTHS = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]

app = Flask(__name__)

_cache: dict = {}

def _cache_get(key):
    entry = _cache.get(key)
    if entry and time.monotonic() < entry["exp"]:
        return entry["val"]
    return None

def _cache_set(key, val, ttl):
    _cache[key] = {"val": val, "exp": time.monotonic() + ttl}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_weather(lat, lon):
    cache_key = f"vejr/{lat}/{lon}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,precipitation_probability,weathercode"
            "&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum"
            "&timezone=Europe/Copenhagen&forecast_days=2"
        )
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        payload = resp.json()

        daily = payload["daily"]
        code = int(daily["weathercode"][0])
        emoji, beskrivelse = WMO_CODES.get(code, ("🌡️", "Ukendt vejr"))
        dagsoversigt = {
            "emoji": emoji,
            "beskrivelse": beskrivelse,
            "max_temp": round(daily["temperature_2m_max"][0], 1),
            "min_temp": round(daily["temperature_2m_min"][0], 1),
            "nedbor": round(daily["precipitation_sum"][0], 1),
        }

        now = datetime.now(tz=TZ)
        hourly = payload["hourly"]
        timer = []
        for i, t in enumerate(hourly["time"]):
            dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
            if dt >= now.replace(minute=0, second=0, microsecond=0) and len(timer) < 6:
                h_code = int(hourly["weathercode"][i])
                h_emoji, _ = WMO_CODES.get(h_code, ("🌡️", ""))
                timer.append({
                    "tid": dt.strftime("%H:%M"),
                    "emoji": h_emoji,
                    "temp": round(hourly["temperature_2m"][i], 1),
                    "nedbor_pct": int(hourly["precipitation_probability"][i]),
                })

        result = {"dagsoversigt": dagsoversigt, "timer": timer}
        _cache_set(cache_key, result, ttl=1800)
        return result
    except Exception as e:
        print(f"Vejr-fejl: {e}", file=sys.stderr)
        return None


def fetch_kalender(kalender):
    navn = kalender["navn"]
    farve = kalender["farve"]
    url = kalender["ics_url"]
    cache_key = f"kal/{url}/{date.today()}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        cal = Calendar.from_ical(resp.content)
        today = date.today()
        events = recurring_ical_events.of(cal).at(today)
        result = []
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
            result.append({
                "titel": str(e.get("SUMMARY", "(Uden titel)")),
                "start": start_str,
                "slut": slut_str,
                "hele_dagen": hele_dagen,
                "kalender_navn": navn,
                "kalender_farve": farve,
            })
        _cache_set(cache_key, result, ttl=300)
        return result
    except Exception as e:
        print(f"Kalender-fejl ({navn}): {e}", file=sys.stderr)
        return []


def fetch_feed(feed):
    cache_key = f"rss/{feed['url']}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    try:
        parsed = feedparser.parse(feed["url"])
        if parsed.entries:
            entry = parsed.entries[0]
            result = {
                "titel": feed["titel"],
                "seneste_titel": entry.get("title", "(Ingen titel)"),
                "seneste_url": entry.get("link", feed["url"]),
            }
            _cache_set(cache_key, result, ttl=900)
            return result
    except Exception as e:
        print(f"RSS-fejl ({feed['titel']}): {e}", file=sys.stderr)
    return {"titel": feed["titel"], "seneste_titel": None, "seneste_url": None}


def get_rss(feeds):
    if not feeds:
        return []
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        return list(pool.map(fetch_feed, feeds))


def fetch_server(server):
    cache_key = f"server/{server['url']}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    try:
        resp = requests.get(server["url"], timeout=2)
        resp.raise_for_status()
        data = resp.json()
        result = {"navn": server["navn"], "online": True, **data}
        _cache_set(cache_key, result, ttl=30)
        return result
    except Exception:
        return {"navn": server["navn"], "online": False}


def get_servere(servere):
    if not servere:
        return []
    with ThreadPoolExecutor(max_workers=len(servere)) as pool:
        return list(pool.map(fetch_server, servere))


def get_begivenheder(kalendere):
    alle = []
    with ThreadPoolExecutor(max_workers=len(kalendere) or 1) as pool:
        futures = {pool.submit(fetch_kalender, k): k for k in kalendere}
        for future in as_completed(futures):
            alle.extend(future.result())
    alle.sort(key=lambda x: (0 if x["hele_dagen"] else 1, x["start"] or ""))
    return alle


def dansk_dato(d: date) -> str:
    dag = DANISH_DAYS[d.weekday()]
    return f"{dag} d. {d.day}. {DANISH_MONTHS[d.month - 1]} {d.year}"


@app.route("/")
def index():
    config = load_config()
    today = date.today()

    vejr = get_weather(config["lokation"]["lat"], config["lokation"]["lon"])
    begivenheder = get_begivenheder(config.get("kalendere", []))
    rss = get_rss(config.get("rss", []))
    servere = get_servere(config.get("servere", []))

    return render_template(
        "index.html",
        links=config.get("links", []),
        rss=rss,
        servere=servere,
        by=config.get("by", ""),
        ugenummer=today.isocalendar()[1],
        dato_dansk=dansk_dato(today),
        vejr=vejr,
        begivenheder=begivenheder,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
