"""Link-grupperne, gjort klar til visning.

Et link i config.yaml kan pege på en tjeneste med `status: docker:vikunja`.
Her slås den nøgle op i det statusd har fortalt, så skabelonen bare skal skrive
en prik i den rigtige farve og slipper for at kende noget til opslaget.
"""


def vaert_urls(grupper):
    """Adressen bag hvert `status: vaert:<navn>`, slået op på værtsnavnet.

    Driftskortet viser værterne med deres egne tal, og så ville Proxmox og
    NAS'en ellers skulle stå to gange: én gang som vært og én gang som link.
    I stedet gør det her værtslinjen selv klikbar. En vært uden link i
    config.yaml står bare uden — den er ikke mindre gyldig af det.
    """
    ud = {}
    for gruppe in grupper or []:
        for link in gruppe.get("links", []):
            noegle = link.get("status") or ""
            if noegle.startswith("vaert:") and link.get("url"):
                ud[noegle.split(":", 1)[1]] = link["url"]
    return ud


def drift_links(viste_grupper):
    """De links fra `plads: drift`-gruppen der IKKE er en vært.

    Værterne har deres egen linje i driftskortet med load og oppetid, så de
    ville stå dobbelt. Tilbage bliver det der hører til driften uden at være
    en maskine vi måler på — WatchYourLAN, EyeMaster og den slags.
    """
    return [
        link
        for gruppe in viste_grupper
        if gruppe.get("plads") == "drift"
        for link in gruppe.get("links", [])
        if not (link.get("status") or "").startswith("vaert:")
    ]


def til_visning(grupper, opslag):
    """Grupperne med `tilstand` sat på hvert link:

    "oppe" / "nede"   vi har spurgt, og fik svar
    "ukendt"          linket peger på en tjeneste, men værtens agent tav
    None              linket peger ikke på noget vi overvåger (fx Gemini)
    """
    ud = []
    for gruppe in grupper or []:
        vist = []
        for link in gruppe.get("links", []):
            noegle = link.get("status")
            if not noegle:
                tilstand = None
            elif (oppe := opslag.get(noegle)) is None:
                tilstand = "ukendt"
            else:
                tilstand = "oppe" if oppe else "nede"
            vist.append({**link, "tilstand": tilstand})
        # `plads` afgoer hvilket kort gruppen havner i. Uden den ender gruppen
        # i link-spalten, saa en config uden noeglen stadig giver en hel side.
        ud.append({
            "titel": gruppe.get("titel", ""),
            "plads": gruppe.get("plads"),
            "links": vist,
        })
    return ud
