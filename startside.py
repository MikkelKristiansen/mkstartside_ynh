"""mkstartside — personlig startside med vejr, kalender, RSS og links.

Selve dataene hentes i kilder/; her er kun Flask, konfigurationen og ruten.
"""

import os
from datetime import date

import yaml
from flask import Flask, jsonify, render_template

import links
from dato import dansk_dato
from kilder import backup, kalender, rss, status, vejr, versioner

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
        versioner=versioner.hent(config.get("versioner"), drift["images"]),
        rss=rss.hent(config.get("rss", [])),
        by=config.get("by", ""),
        ugenummer=today.isocalendar()[1],
        dato_dansk=dansk_dato(today),
        vejr=vejr.hent(config["lokation"]["lat"], config["lokation"]["lon"]),
        begivenheder=kalender.hent(config.get("kalendere", [])),
    )


@app.route("/versioner.json")
def versioner_json():
    """Versionstjekket som JSON, så andre maskiner kan spørge frem for at gætte.

    Findes for x1's ugentlige påmindelse: laptoppen lavede før det fulde tjek
    selv, med sin egen liste over apps — og de to lister drev fra hinanden, så
    tre containere aldrig blev tjekket. Nu er der én liste (config.yaml her),
    og x1 henter bare svaret. Push og pull kan sagtens leve sammen; to
    konfigurationer kan ikke.
    """
    config = load_config()
    drift = status.hent(config.get("servere", []))
    return jsonify(versioner.hent(config.get("versioner"), drift["images"]) or {})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
