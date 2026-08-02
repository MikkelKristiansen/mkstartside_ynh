"""mkstartside — personlig startside med vejr, kalender, RSS og links.

Selve dataene hentes i kilder/; her er kun Flask, konfigurationen og ruten.
"""

import os
from datetime import date

import yaml
from flask import Flask, render_template

import links
from dato import dansk_dato
from kilder import backup, kalender, rss, status, vejr

CONFIG_PATH = os.environ.get(
    "MKSTARTSIDE_CONFIG",
    os.path.join(os.path.dirname(__file__), "config.yaml"),
)

app = Flask(__name__)


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def link_grupper(config):
    """Grupperne fra config.yaml — eller den gamle flade `links:`-liste pakket
    som én gruppe uden titel.

    config.yaml ligger kun på serveren og er ikke i git, så koden og
    konfigurationen kan ikke opdateres i samme greb. Fald-tilbagen betyder at
    rækkefølgen er ligegyldig: en gammel config giver stadig en brugbar side.
    """
    if grupper := config.get("grupper"):
        return grupper
    return [{"titel": "Links", "links": config.get("links", [])}]


@app.route("/")
def index():
    config = load_config()
    today = date.today()
    drift = status.hent(config.get("servere", []))
    grupper = link_grupper(config)
    viste_grupper = links.til_visning(grupper, drift["opslag"])

    return render_template(
        "index.html",
        grupper=viste_grupper,
        drift_links=links.drift_links(viste_grupper),
        vaert_urls=links.vaert_urls(grupper),
        drift=drift,
        backup=backup.hent(config.get("backup")),
        rss=rss.hent(config.get("rss", [])),
        by=config.get("by", ""),
        ugenummer=today.isocalendar()[1],
        dato_dansk=dansk_dato(today),
        vejr=vejr.hent(config["lokation"]["lat"], config["lokation"]["lon"]),
        begivenheder=kalender.hent(config.get("kalendere", [])),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
