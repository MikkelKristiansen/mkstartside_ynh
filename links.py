"""Link-grupperne, gjort klar til visning.

Et link i config.yaml kan pege på en tjeneste med `status: docker:vikunja`.
Her slås den nøgle op i det statusd har fortalt, så skabelonen bare skal skrive
en prik i den rigtige farve og slipper for at kende noget til opslaget.
"""


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
        ud.append({"titel": gruppe.get("titel", ""), "links": vist})
    return ud
