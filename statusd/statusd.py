"""statusd — lille agent der rapporterer værtens tilstand som JSON.

Grundtallene (load, RAM, temperatur, oppetid) måles altid. Hvad der måles ud
over dem styres af miljøvariabler, så den samme fil kan kopieres uændret til
alle værter — det værtsspecifikke hører til i unit-filen, ikke i koden:

    STATUSD_LXC=1                    Proxmox-værten: alle LXC'er, og om de kører
    STATUSD_DOCKER=1                 docker-vært: alle containere, og om de kører
    STATUSD_UNITS=nginx,flask_dnd    systemd-tjenester der skal tjekkes

Kræver ikke root. LXC-tilstanden læses direkte af /sys/fs/cgroup og /etc/pve,
der begge er læsbare for alle, i stedet for at kalde `pct`. Docker kræver dog
medlemskab af docker-gruppen (SupplementaryGroups=docker i unit-filen).
"""

import json
import os
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CGROUP_LXC = Path("/sys/fs/cgroup/lxc")
PVE_LXC = Path("/etc/pve/lxc")
LXC_LIB = Path("/var/lib/lxc")


def _koer(kommando):
    """Kør en kommando og returnér dens stdout. Fejl giver tom streng."""
    try:
        faerdig = subprocess.run(kommando, capture_output=True, text=True, timeout=5)
        return faerdig.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def grundtal():
    with open("/proc/loadavg") as f:
        load = float(f.read().split()[0])

    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split()[0], int(line.split()[1])
            if key in ("MemTotal:", "MemAvailable:"):
                mem[key] = val
    mem_pct = round(100 * (1 - mem["MemAvailable:"] / mem["MemTotal:"]))

    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = round(int(f.read()) / 1000, 1)
    except OSError:
        temp = None

    with open("/proc/uptime") as f:
        uptime_s = int(float(f.read().split()[0]))
    uptime_h = uptime_s // 3600

    return {"load": load, "mem_pct": mem_pct, "temp": temp, "uptime_h": uptime_h}


def _lxc_navn(vmid):
    """Navnet på en LXC, læst af den genererede lxc-config i /var/lib/lxc.

    Det oplagte sted er /etc/pve/lxc/<vmid>.conf, men de filer er 640
    root:www-data. /var/lib/lxc/<vmid>/config er 644 og har samme navn som
    `lxc.uts.name`, så vi slipper for at give agenten www-data-adgang til hele
    Proxmox-konfigurationen bare for at kunne skrive "apps-mk" i stedet for
    "112". Kan den ikke læses, er vmid et brugbart fald-tilbage.
    """
    try:
        for linje in (LXC_LIB / vmid / "config").read_text().splitlines():
            if linje.startswith("lxc.uts.name"):
                return linje.split("=", 1)[1].strip()
    except OSError:
        pass
    return vmid


def lxc():
    """Alle LXC'er på værten, og om de kører.

    En kørende LXC har en mappe /sys/fs/cgroup/lxc/<vmid>. Listen af dem der
    findes, tages fra både /etc/pve/lxc og /var/lib/lxc — mappen /etc/pve/lxc
    kan listes selv om filerne i den ikke kan læses, og to kilder betyder at en
    ny container ikke kan nå at blive usynlig. Samme svar som `pct list`, men
    uden root.
    """
    vmids = {p.stem for p in PVE_LXC.glob("*.conf")} if PVE_LXC.is_dir() else set()
    if LXC_LIB.is_dir():
        vmids |= {p.name for p in LXC_LIB.iterdir() if p.is_dir() and p.name.isdigit()}
    if not vmids:
        return []

    koerende = set()
    if CGROUP_LXC.is_dir():
        koerende = {p.name for p in CGROUP_LXC.iterdir() if p.is_dir()}

    return [
        {"navn": _lxc_navn(vmid), "oppe": vmid in koerende}
        for vmid in sorted(vmids, key=lambda v: v.zfill(8))
    ]


def docker():
    """Alle containere, også stoppede — en container der er forsvundet fra
    listen ville ellers se ud som om alt var i orden.

    `image` kommer med, fordi det er den eneste kilde til hvilken VERSION der
    faktisk kører. Startsiden bruger det til at opdage nye udgaver (se
    kilder/versioner.py). Det er med vilje agenten der svarer på det, og ikke
    en ssh fra startsiden: agenten står her i forvejen og taler allerede med
    docker, mens en ssh-vej ville koste endnu en nøgle at holde styr på.
    """
    linjer = _koer(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Image}}"])
    resultat = []
    for linje in linjer.splitlines():
        felter = linje.split("\t")
        if len(felter) < 2:
            continue
        navn, tilstand = felter[0], felter[1]
        image = felter[2] if len(felter) > 2 else ""
        resultat.append({
            "navn": navn,
            "oppe": tilstand.strip() == "running",
            "image": image.strip(),
        })
    return sorted(resultat, key=lambda c: c["navn"])


def units(navne):
    """systemctl is-active svarer med én linje pr. unit i samme rækkefølge.
    Exit-koden er ikke-nul så snart bare én er inaktiv, så den ignoreres."""
    if not navne:
        return []
    svar = _koer(["systemctl", "is-active", *navne]).splitlines()
    svar += [""] * (len(navne) - len(svar))
    return [
        {"navn": navn, "oppe": svar[i].strip() == "active"}
        for i, navn in enumerate(navne)
    ]


def tilstand():
    data = grundtal()
    if os.environ.get("STATUSD_LXC"):
        data["lxc"] = lxc()
    if os.environ.get("STATUSD_DOCKER"):
        data["docker"] = docker()
    navne = [n.strip() for n in os.environ.get("STATUSD_UNITS", "").split(",") if n.strip()]
    if navne:
        data["units"] = units(navne)
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, kode = json.dumps(tilstand()).encode(), 200
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
    ThreadingHTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
