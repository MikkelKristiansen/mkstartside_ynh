"""synologyd — oversaetter Synology-NAS'ens SNMP til statusd's JSON-format.

NAS'en kan ikke selv koere en statusd-agent: DSM har ikke systemd, og noget
installeret i haanden ville ikke overleve en DSM-opdatering. I stedet koerer
denne oversaetter paa apps-mk, spoerger NAS'en over SNMP, og svarer i praecis
samme format som statusd. For startsiden er NAS'en dermed bare endnu en linje
i servere:, og hverken kilder/status.py eller skabelonen behoever vide at den
er speciel.

Miljoevariabler, saettes i unit-filen (se deploy/synologyd.service):

    SYNOLOGY_HOST=192.168.0.130   NAS'ens adresse
    SYNOLOGY_COMMUNITY=...        SNMPv2c community. Laeses fra
                                  /etc/synologyd.env og staar ikke i git.
    SYNOLOGY_SOVER=22:30-05:45    Planlagt sovetid — se sover() nedenfor.
"""

import json
import os
import subprocess
from datetime import datetime, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HOST = os.environ.get("SYNOLOGY_HOST", "192.168.0.130")
COMMUNITY = os.environ.get("SYNOLOGY_COMMUNITY", "")
SOVEVINDUE = os.environ.get("SYNOLOGY_SOVER", "")

# Grundtallene. Raekkefoelgen her er den raekkefoelge snmpget svarer i.
GRUND = [
    # hrSystemUptime og IKKE sysUpTime (1.3.6.1.2.1.1.3.0): sidstnaevnte er
    # SNMP-agentens oppetid, som nulstilles hver gang SNMP slaas til i DSM,
    # og den ville altsaa lyve om hvor laenge NAS'en har koert.
    "1.3.6.1.2.1.25.1.1.0",
    "1.3.6.1.4.1.2021.10.1.3.1",  # laLoad.1 — 1 minuts load, som streng
    "1.3.6.1.4.1.2021.4.5.0",     # memTotalReal
    "1.3.6.1.4.1.2021.4.6.0",     # memAvailReal
    "1.3.6.1.4.1.2021.4.14.0",    # memBuffer
    "1.3.6.1.4.1.2021.4.15.0",    # memCached
    "1.3.6.1.4.1.6574.1.2.0",     # Synologys egen systemtemperatur
]

# (navne-OID, tilstands-OID). Synology svarer 1 = Normal i begge tabeller;
# alt andet er noget vi vil se paa startsiden.
TABELLER = [
    ("1.3.6.1.4.1.6574.3.1.1.2", "1.3.6.1.4.1.6574.3.1.1.3"),  # volumes/RAID
    ("1.3.6.1.4.1.6574.2.1.1.2", "1.3.6.1.4.1.6574.2.1.1.5"),  # de fysiske diske
]

# -Oqvt: kun vaerdien, uden type-praefiks, og timeticks som raa tal.
# -t 2 -r 0: to sekunders taalmodighed og ingen gentagelser. Naar NAS'en er
# slukket skal vi fejle hurtigt, ikke lade startsiden vente.
SNMP_FLAG = ["-v2c", "-Oqvt", "-t", "2", "-r", "0"]


def _snmp(vaerktoej, oids):
    """Vaerdierne for oids, eller None hvis NAS'en ikke svarede.

    None og [] er to forskellige ting her: [] betyder "spurgt, ingen raekker"
    (et NAS uden diske), None betyder "fik intet svar".
    """
    if not COMMUNITY:
        return None
    try:
        faerdig = subprocess.run(
            [vaerktoej, *SNMP_FLAG, "-c", COMMUNITY, HOST, *oids],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if faerdig.returncode != 0:
        return None
    # Strenge kommer i citationstegn; tal goer ikke.
    return [linje.strip().strip('"') for linje in faerdig.stdout.splitlines() if linje.strip()]


def grundtal():
    svar = _snmp("snmpget", GRUND)
    if not svar or len(svar) < len(GRUND):
        return None

    uptime_ticks, load, total, avail, buffer, cached, temp = svar[:7]

    # SNMP giver os ikke MemAvailable som /proc/meminfo goer, saa vi lægger
    # den sammen af de dele der reelt kan frigives igen.
    total, brugbar = int(total), int(avail) + int(buffer) + int(cached)
    return {
        "load": float(load),
        "mem_pct": round(100 * (1 - brugbar / total)) if total else 0,
        "temp": float(temp),
        # hrSystemUptime er i hundrededele sekunder.
        "uptime_h": int(uptime_ticks) // 100 // 3600,
    }


def komponenter():
    """Volumes og diske som oppe/nede-poster, i statusd's `units`-form.

    De to walks svarer i samme raekkefoelge, saa navn nr. i hoerer til
    tilstand nr. i — samme antagelse som statusd goer om `systemctl is-active`.
    """
    ud = []
    for navne_oid, status_oid in TABELLER:
        navne = _snmp("snmpwalk", [navne_oid])
        tilstande = _snmp("snmpwalk", [status_oid])
        if not navne or not tilstande:
            continue
        for navn, tilstand in zip(navne, tilstande):
            ud.append({"navn": navn, "oppe": tilstand == "1"})
    return ud


def sover(nu=None):
    """Om vi er inde i den planlagte sovetid.

    NAS'en slukker helt efter skema, saa den svarer ikke om natten. Uden det
    her ville startsiden vise en roed alarm syv timer hver nat — og en alarm
    man laerer at ignorere er vaerre end ingen alarm. Inde i vinduet melder vi
    "sover" og faar en graa prik; uden for vinduet er tavshed en rigtig fejl.
    """
    if not SOVEVINDUE:
        return False
    try:
        fra, til = [time(*map(int, t.split(":"))) for t in SOVEVINDUE.split("-")]
    except ValueError:
        return False
    nu = (nu or datetime.now()).time()
    # Vinduet gaar over midnat, saa "fra <= nu <= til" holder ikke.
    return fra <= nu <= til if fra <= til else nu >= fra or nu <= til


def tilstand():
    data = grundtal()
    if data is None:
        return {"sover": True} if sover() else None
    data["units"] = komponenter()
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data = tilstand()
            # 503 og ikke 200: en NAS der er vaek uden for sovetiden er en
            # fejl, og startsiden skal vise den som "svarer ikke".
            body, kode = (json.dumps(data).encode(), 200) if data else (b"{}", 503)
        except Exception as e:
            body, kode = json.dumps({"fejl": str(e)}).encode(), 500
        self.send_response(kode)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9091), Handler).serve_forever()
