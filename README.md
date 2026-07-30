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

## Links og status-prikker

Links står i `grupper:` — det er grupperingen der gør siden overskuelig.
Hvert link kan pege på en tjeneste med `status:`, og får så en prik:

```yaml
grupper:
  - titel: Egne apps
    links:
      - titel: DND
        url: https://dnd.mkuv.dk/
        status: unit:flask_dnd
```

Nøglen har formen `<slags>:<navn>` og slås op i det `statusd`-agenterne svarer:

| Nøgle | Kommer fra |
|---|---|
| `docker:vikunja` | vært med `STATUSD_DOCKER=1` |
| `unit:flask_dnd` | vært hvis `STATUSD_UNITS` nævner den |
| `lxc:apps-mk` | Proxmox-værten (`STATUSD_LXC=1`) |
| `vaert:Proxmox` | selve agenten — navnet fra `servere:` |

🟢 kører · 🔴 nede · ⚪ **ukendt** — nøglen fandtes ikke i svaret, typisk fordi
agenten ikke svarede. At en agent tier er ikke det samme som at tjenesten er
nede, og de to må ikke se ens ud. Links uden `status:` får ingen prik; det er
det rigtige for alt vi ikke selv driver.

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

## statusd — hører til, men bor flere andre steder

Startsiden poller `statusd`, en lille JSON-agent med load, RAM, temperatur og
uptime. Kilden ligger i `statusd/` her i repoet, men den **kører** på fire
værter — én fil, samme kode alle steder. Hvad den måler ud over grundtallene
styres af miljøvariabler i unit-filen, ikke af koden:

| Vært | Unit i `deploy/` | Måler også | Sti |
|---|---|---|---|
| Proxmox 192.168.0.67 | `statusd-proxmox.service` | alle LXC'er | `/opt/statusd.py` |
| apps-docker 192.168.0.71 | `statusd-apps-docker.service` | alle docker-containere | `/opt/statusd.py` |
| apps-mk 192.168.0.73 | `statusd-apps-mk.service` | systemd-tjenester | fra repoet |
| pihole2 192.168.0.124 | — | kun grundtal | `/opt/statusd.py` |

Grunden til at Proxmox-værten er med: hypervisorens tal siger mere end en enkelt
LXC's, som er bundet af sin egen RAM-kvote.

`statusd` kører med `DynamicUser=yes` og har **ingen rettigheder** ud over det
alle har — bortset fra ét sted:

- **LXC'er** læses af `/sys/fs/cgroup/lxc/<vmid>` (en mappe = containeren kører)
  og `/var/lib/lxc/<vmid>/config` (navnet). Ikke `pct`, som kræver root, og
  ikke `/etc/pve/lxc/*.conf`, som er 640 `root:www-data`.
- **Docker** kræver `SupplementaryGroups=docker`. Det er den eneste rigtige
  rettighed nogen af agenterne har, og den gives kun i apps-docker.
- **systemd-tjenester** slås op med `systemctl is-active`, som alle må.

Opdatering på de to værter uden repoet er en filkopi, ikke et pull:

```bash
scp statusd/statusd.py root@192.168.0.67:/opt/statusd.py
ssh root@192.168.0.67 systemctl restart statusd
```

Skal en tjeneste med i apps-mk's liste, er det unit-filen der rettes:

```
Environment=STATUSD_UNITS=nginx,flask_dnd,have_inbox,mkstartside
```

`update.sh` findes ikke her — unit-filerne i `deploy/` er kopier, og de
udrulles i hånden.

`servere:`-listen i `config.yaml` peger på alle fire.

## Tidligere YunoHost-app

Appen var pakket som YunoHost-app (`mkstartside 1.0~ynh1`). Efter migrationen til
Proxmox 26. juli 2026 kører den som almindelig systemd, og `manifest.toml`,
`conf/` og `scripts/` er fjernet. Koden er flyttet fra `sources/` op i roden.
