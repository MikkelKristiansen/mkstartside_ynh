"""mkstartside — personlig startside med vejr, kalender, RSS og links.

Selve dataene hentes i kilder/; her er kun Flask, konfigurationen og ruten.
"""

import os
from datetime import date

import yaml
from flask import Flask, render_template

from dato import dansk_dato
from kilder import kalender, rss, status, vejr

CONFIG_PATH = os.environ.get(
    "MKSTARTSIDE_CONFIG",
    os.path.join(os.path.dirname(__file__), "config.yaml"),
)

app = Flask(__name__)


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.route("/")
def index():
    config = load_config()
    today = date.today()

    return render_template(
        "index.html",
        links=config.get("links", []),
        rss=rss.hent(config.get("rss", [])),
        servere=status.hent(config.get("servere", [])),
        by=config.get("by", ""),
        ugenummer=today.isocalendar()[1],
        dato_dansk=dansk_dato(today),
        vejr=vejr.hent(config["lokation"]["lat"], config["lokation"]["lon"]),
        begivenheder=kalender.hent(config.get("kalendere", [])),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
