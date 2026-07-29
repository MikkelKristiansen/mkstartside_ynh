"""Vejret fra open-meteo — dagsoversigt og de næste seks timer."""

import sys
from datetime import datetime

import requests

from dato import TZ
from . import cache

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


def hent(lat, lon):
    noegle = f"vejr/{lat}/{lon}"
    if (gemt := cache.hent(noegle)) is not None:
        return gemt
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

        resultat = {"dagsoversigt": dagsoversigt, "timer": timer}
        cache.gem(noegle, resultat, ttl=1800)
        return resultat
    except Exception as e:
        print(f"Vejr-fejl: {e}", file=sys.stderr)
        return None
