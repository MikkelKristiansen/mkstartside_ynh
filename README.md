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
| `disk:Volume 1` | Synology-NAS'en via `synologyd` |
| `unit:minecraft` | Minecraft-serveren via `minecraftd` |
| `vaert:Proxmox` | selve agenten — navnet fra `servere:` |

### Sidens to kort

Siden er et bånd med dag og vejr, og derunder to kort: **drift** til venstre og
**links** til højre. En gruppe havner i driftskortet ved at få `plads: drift`:

```yaml
  - titel: Drift
    plads: drift
    links: …
```

Inde i den gruppe deles linkene i to. Har et link `status: vaert:<navn>`, bliver
det til værtens egen linje med load, RAM og oppetid — navnet er stadig klikbart.
Resten står som en fodnote nederst i kortet. Det er derfor Proxmox og NAS'en ikke
optræder to gange. Grupper uden `plads` ender i link-kortet, så en `config.yaml`
uden nøglen giver stadig en hel side — koden og konfigurationen udrulles jo
hver for sig.

🟢 kører · 🔴 nede · ⚪ **ukendt** — nøglen fandtes ikke i svaret, typisk fordi
agenten ikke svarede. At en agent tier er ikke det samme som at tjenesten er
nede, og de to må ikke se ens ud. Links uden `status:` får ingen prik; det er
det rigtige for alt vi ikke selv driver.

### Backup-alder — den ene ting siden ikke selv henter

Nederst i driftskortet står en linje pr. backup-disk med hvor længe siden den
sidst kørte igennem. Den vises kun, hvis `config.yaml` har en `backup:`-blok —
se `config.example.yaml` for felterne.

Alt andet på siden **hentes**; det her **modtages**. Grunden er, at afsenderen er
en bærbar (x1). Spurgte siden efter status, ville svaret blive ⚪ ukendt, hver
gang maskinen var slukket — og advarslen ville altså forsvinde præcis når man har
været væk længe og derfor ikke har fået taget backup. I stedet skubber x1 et
tidsstempel herop efter hver kørsel, og bliver det ikke opdateret, vokser alderen
på siden af sig selv. Afsenderen er `~/bin/backup/publicer-backup-status.sh`;
modtageren er `/usr/local/sbin/modtag-backup-status` på apps-mk, låst til en
`command=`-begrænset ssh-nøgle, og filen lander i `state/backup-status.json`.

Farverne er tærskler, ikke oppe/nede, og tærsklen sættes pr. disk, fordi
kadencerne er forskellige: 🟢 frisk · 🟡 ved at blive gammel · 🔴 for længe siden
eller sidste kørsel gik ikke rent · ⚪ ingen melding. Gul findes **kun** her —
tjeneste-prikkerne har ingen ægte mellemtilstand.

### Nye udgaver af docker-apps'ene

Under backup-linjerne står de apps, der er bagud, med et link til
release-noterne. Blokken vises kun, hvis `config.yaml` har en `versioner:`-blok.

Images på apps-docker er pinnet til konkrete versionsnumre (`miniflux:2.3.3`,
ikke `:latest`), så en genstart aldrig i sig selv kan trække en ny major-version
ind og brække en database. Prisen er, at en ny udgave ikke opdages af sig selv:
`docker compose pull` på et pinnet tag henter ingenting.

Den kørende version kommer fra `statusd`-agentens `image`-felt — samme kilde som
prikkerne. En ssh herfra til docker-værten ville koste endnu en nøgle at holde
styr på, og agenten taler allerede med docker. Nyeste udgave slås op på GitHub og
caches seks timer; opslaget er anonymt, og loftet på 60 i timen er langt væk.

🟢 alle er nyeste · 🟡 minor eller patch · 🔴 **major** — læs opgraderingsnoterne
og tag backup først. Major står desuden som et lille mærkat, fordi farven alene
forsvinder for den farveblinde, og det er netop den ene forskel man ikke må
overse. Apps, der ikke kunne tjekkes, står som fodnote frem for at forsvinde: et
tjek der ikke nåede igennem er ikke et tjek der fandt ro.

Normaliseringen skelner mellem **bygge-suffikser** (`-alpine`, `-ls392`), der
skal væk før to versioner kan sammenlignes, og **forudgivelser** (`-rc1`), der er
en del af versionen. Uden det ville hedgedoc og calibre-web altid se bagud ud —
og en advarsel der altid lyser er den samme som ingen advarsel.

`GET /versioner.json` giver det samme som JSON. Det findes for x1's ugentlige
påmindelse (`~/bin/docker-versioner/`), som før lavede hele tjekket selv ud fra
sin egen liste — indtil de to lister drev fra hinanden, og tre containere aldrig
blev tjekket. Nu er der én liste, her i `config.yaml`, og laptoppen henter bare
svaret. Push og pull kan sagtens leve sammen; to konfigurationer kan ikke.

**Listen skal holdes op mod `docker ps` på .71, hver gang der kommer en ny app** —
en container der ikke står i `versioner:`, bliver aldrig tjekket og larmer aldrig.
Det er samme slags kontrol som at holde `grupper:` op mod edges Caddyfile.

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
| apps-docker 192.168.0.71 | `statusd-apps-docker.service` | alle docker-containere + `image` | `/opt/statusd.py` |
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
- **systemd-tjenester** slås op med `systemctl is-active`. Alle *må* det, men
  ikke en `DynamicUser` — dbus-daemon kan ikke slå en UID op der ikke står i
  `/etc/passwd`, så opslaget fejler med "Transport endpoint is not connected"
  og hver eneste tjeneste ser ud til at være nede. `apps-mk` er derfor den ene
  agent der kører som en rigtig systembruger (`useradd --system
  --no-create-home --shell /usr/sbin/nologin statusd`) i stedet.

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

### synologyd — NAS'en, som ikke kan køre en agent

DSM har ikke systemd, og noget installeret i hånden på NAS'en ville ikke
overleve en DSM-opdatering. `statusd/synologyd.py` kører derfor **på apps-mk**,
spørger NAS'en over SNMP og svarer i præcis samme JSON-format på port 9091. For
startsiden er NAS'en dermed bare endnu en linje i `servere:` — den peger bare på
`192.168.0.73:9091` og ikke på NAS'ens egen adresse.

Slå SNMP til i DSM under **Kontrolpanel → Terminal & SNMP → SNMP** (v2c, LAN
only). Community'et er reelt et kodeord og sendes i klartekst, så det står
hverken i git eller i unit-filen:

```bash
install -m 640 /dev/null /etc/synologyd.env
echo "SYNOLOGY_COMMUNITY=..." > /etc/synologyd.env
```

Den rapporterer load, RAM, systemtemperatur, oppetid og hver disk/volume.
To fælder er værd at kende:

- **`sysUpTime` (`1.3.6.1.2.1.1.3.0`) er SNMP-agentens oppetid**, ikke systemets
  — den nulstilles hver gang SNMP slås til i DSM. Brug `hrSystemUptime`
  (`1.3.6.1.2.1.25.1.1.0`).
- **NAS'en slukker helt 22.30–05.45.** Er den tavs inde i det vindue
  (`SYNOLOGY_SOVER` i unit-filen), melder `synologyd` `sover` og får en grå
  prik. Uden for vinduet er tavshed en rigtig fejl, og prikken bliver rød. En
  rød alarm syv timer hver nat ville bare lære en at ignorere røde prikker.

### minecraftd — når `systemctl is-active` ikke er et ærligt svar

`minecraft.service` starter java'en gennem `screen`, og screen afslutter altid
med kode 0 — også når java'en er crashet. Systemd kan derfor ikke se forskel på
crash og pænt stop, og unit'en kører med `Restart=always`. Prisen er, at
`is-active` svarer **active** både midt i en crash-loop og mens java'en hænger
uden at svare nogen. Netop de to tilfælde man vil opdage.

`statusd/minecraftd.py` kører derfor **på minecraft-containeren** i stedet for
den almindelige `statusd`, og spørger serveren som en klient ville: et **Server
List Ping** på TCP 25565 — samme forespørgsel som serverlisten i spillet.
Svarer den, kan spillerne komme ind. Svaret giver desuden spillertal og version,
som vises i `Status`-blokken (🎮 2/20, med versionen som tooltip).

| Vært | Unit i `deploy/` | Måler | Sti |
|---|---|---|---|
| minecraft 192.168.0.68 | `minecraftd.service` | grundtal + ping af spil-porten | `/opt/minecraftd.py` |

Udrulning er en filkopi som på de andre repo-løse værter:

```bash
scp statusd/minecraftd.py root@192.168.0.68:/opt/minecraftd.py
ssh root@192.168.0.68 systemctl restart minecraftd
```

Den svarer på port **9090** som en almindelig `statusd`, så `servere:` peger
bare på `192.168.0.68:9090`. To ting værd at kende:

- **Porten er spil-porten.** Simple Voice Chat's UDP 24454 siger intet om,
  hvorvidt serveren tager imod spillere, og pinges ikke.
- **Værts-prikken og spil-prikken er ikke det samme.** Værten er grøn, så snart
  agenten svarer — den kører videre selv om java'en er væk. Det er `unit:minecraft`
  der bliver rød, og serveren dukker op i `nede`-listen.

## Tidligere YunoHost-app

Appen var pakket som YunoHost-app (`mkstartside 1.0~ynh1`). Efter migrationen til
Proxmox 26. juli 2026 kører den som almindelig systemd, og `manifest.toml`,
`conf/` og `scripts/` er fjernet. Koden er flyttet fra `sources/` op i roden.
