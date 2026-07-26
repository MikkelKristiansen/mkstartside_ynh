# mkstartside

Personlig startside med vejr, kalender, RSS og links. Flask + gunicorn.

Kører på **https://start.mkuv.dk** — kun tilgængelig på LAN og over VPN.

## Hvor tingene ligger

| | Sti |
|---|---|
| Kode (dette repo) | `/srv/apps/mkstartside` på `apps-mk` (192.168.0.73, LXC 112) |
| Konfiguration | `/srv/apps/mkstartside/config.yaml` — **ikke i git** |
| Unit | `/etc/systemd/system/mkstartside.service` — kopi i `deploy/` |

`config.yaml` er den levende konfiguration og redigeres direkte på serveren.
Den er derfor i `.gitignore`; repoet har kun `config.example.yaml` som skabelon.
Så kan `git pull` aldrig overskrive dine links. Samme mønster som `haven.yaml`
i [have.py](https://github.com/MikkelKristiansen/have.py).

## Opdatering

```bash
# lokalt
git commit -am "..." && git push

# på serveren
ssh root@192.168.0.73
cd /srv/apps/mkstartside && sudo -u apps git pull
systemctl restart mkstartside
```

Er `requirements.txt` ændret:

```bash
sudo -u apps /srv/apps/mkstartside/venv/bin/pip install -r requirements.txt
```

## statusd — hører til, men bor et andet sted

Startsiden poller `statusd`, en lille JSON-server med load, RAM, temperatur og
uptime. Kilden ligger i `statusd/` her i repoet; den **kører** på
**Proxmox-værten** (192.168.0.67:9090) fra `/opt/statusd.py`, ikke i denne
container — hypervisorens tal siger mere end en enkelt LXC's, som er bundet af
sin egen RAM-kvote.

Opdatering er en filkopi, ikke et pull — den ligger uden for enhver app-mappe:

```bash
scp statusd/statusd.py root@192.168.0.67:/opt/statusd.py
ssh root@192.168.0.67 systemctl restart statusd
```

Unitten kører med `DynamicUser=yes`; scriptet læser kun `/proc`.

Der står stadig en ubrugt `statusd` i `apps-mk`. Den kan slås fra uden
konsekvens.

`servere:`-listen i `config.yaml` peger på Proxmox og på pihole2 (192.168.0.124).

## Tidligere YunoHost-app

Appen var pakket som YunoHost-app (`mkstartside 1.0~ynh1`). Efter migrationen til
Proxmox 26. juli 2026 kører den som almindelig systemd, og `manifest.toml`,
`conf/` og `scripts/` er fjernet. Koden er flyttet fra `sources/` op i roden.
