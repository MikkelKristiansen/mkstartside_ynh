"""minecraftd — Minecraft-serverens tilstand i statusd's JSON-format.

Kører på minecraft-containeren i stedet for den almindelige statusd, fordi
`systemctl is-active minecraft` ikke er et ærligt svar her: unit'en har
Restart=always (screen afslutter altid med kode 0, så systemd kan ikke se
forskel på crash og pænt stop), og den er derfor grøn både midt i en
crash-loop og mens java'en hænger uden at svare nogen. Præcis de to tilfælde
man gerne vil opdage.

I stedet spørges serveren som en Minecraft-klient ville: et Server List Ping
på 25565 — samme forespørgsel din serverliste i spillet laver. Svarer den,
kan spillerne komme ind. Oveni kommer spillertal og version gratis.

Grundtallene måles som i statusd.py. Filerne er bevidst hver sin agent frem
for ét flag i statusd.py: protokol-koden nedenfor hører ikke hjemme i den
generiske agent, der skal kunne kopieres uændret til alle værter. Samme
opdeling som synologyd.py.

Miljøvariabler, sættes i unit-filen (se deploy/minecraftd.service):

    MINECRAFT_HOST=127.0.0.1   Serveren der pinges
    MINECRAFT_PORT=25565       Spil-porten (ikke voice-chat'ens UDP 24454)
    MINECRAFT_UNIT=minecraft   Navnet prikken får på startsiden
"""

import json
import os
import socket
import struct
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HOST = os.environ.get("MINECRAFT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))
UNIT = os.environ.get("MINECRAFT_UNIT", "minecraft")

# Serveren når at svare på et ping længe før den er spilbar. Tre sekunder er
# rigeligt på et LAN og kort nok til at startsiden ikke venter på en hængt
# server — kilder/status.py giver alligevel op efter to.
TIMEOUT = 3


def _varint(vaerdi):
    """Minecrafts tal-format: syv bit ad gangen, hvor ottende bit betyder
    "der kommer mere". Maskeringen gør, at -1 sendes som 32-bit
    two's complement, sådan som protokollen forventer."""
    vaerdi &= 0xFFFFFFFF
    ud = bytearray()
    while True:
        byte = vaerdi & 0x7F
        vaerdi >>= 7
        if vaerdi:
            ud.append(byte | 0x80)
        else:
            ud.append(byte)
            return bytes(ud)


def _laes_praecis(sock, antal):
    """recv() må gerne svare med færre bytes end der blev bedt om, så der
    skal læses i løkke. Lukker modparten undervejs, er svaret ubrugeligt."""
    buffer = bytearray()
    while len(buffer) < antal:
        klump = sock.recv(antal - len(buffer))
        if not klump:
            raise ConnectionError("forbindelsen lukkede midt i svaret")
        buffer += klump
    return bytes(buffer)


def _laes_varint(sock):
    tal = 0
    for skift in range(0, 35, 7):
        byte = _laes_praecis(sock, 1)[0]
        tal |= (byte & 0x7F) << skift
        if not byte & 0x80:
            return tal
    raise ValueError("varint uden afslutning")


def _pakke(krop):
    """Hver pakke sendes med sin egen længde foran."""
    return _varint(len(krop)) + krop


def ping():
    """Server List Ping. Returnerer serverens svar-JSON, eller None hvis den
    ikke svarer — hvilket er hele pointen med agenten, så enhver fejl her er
    et gyldigt "nede" og ikke noget der skal boble op som en agent-fejl."""
    vaert = HOST.encode()
    haandtryk = _pakke(
        b"\x00"            # pakke-id 0: handshake
        + _varint(-1)      # protokol-version; -1 = "spørger bare"
        + _varint(len(vaert)) + vaert
        + struct.pack(">H", PORT)
        + _varint(1)       # næste tilstand: 1 = status
    )
    try:
        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as sock:
            sock.settimeout(TIMEOUT)
            sock.sendall(haandtryk + _pakke(b"\x00"))  # status-forespørgsel

            _laes_varint(sock)                         # pakkens længde
            if _laes_varint(sock) != 0:                # pakke-id skal være 0
                return None
            svar = _laes_praecis(sock, _laes_varint(sock))
        return json.loads(svar.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


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

    return {"load": load, "mem_pct": mem_pct, "temp": temp,
            "uptime_h": uptime_s // 3600}


def tilstand():
    data = grundtal()
    svar = ping()

    # Samme felt som statusd's systemd-tjenester, så startsiden kan slå
    # tilstanden op som `unit:minecraft` og få den med i "nede"-listen uden
    # at vide at denne vært er speciel.
    data["units"] = [{"navn": UNIT, "oppe": svar is not None}]

    if svar:
        spillere = svar.get("players", {})
        if "online" in spillere and "max" in spillere:
            data["spillere"] = {"online": spillere["online"],
                                "max": spillere["max"]}
        data["version"] = svar.get("version", {}).get("name")
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
