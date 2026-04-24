from drive import (
    hamta_drive_tjanst,
    hamta_eller_skapa_mapp,
    hamta_fil_id,
    lista_filer,
    skapa_projekt,
)
from config import lас_config, uppdatera_senaste_projekt

ROT_MAPP = "Bokverktyg"

PROJEKTFILER = [
    "bok",
    "storyline",
    "stilguide",
    "karaktarer",
    "kontext",
    "dramaturgi",
    "dramaturgi_observationer",
    "smakprofil",
]

PROJEKTMAPPAR = ["utkast", "exempeltexter", "agentlogg", "system"]


def hamta_rot(service):
    return hamta_eller_skapa_mapp(service, ROT_MAPP)


def lista_projekt(service):
    rot_id = hamta_rot(service)
    mappar = lista_filer(service, rot_id)
    projekt = []
    for mapp in mappar:
        if mapp["name"] != ROT_MAPP:
            projekt.append({
                "id": mapp["id"],
                "titel": mapp["name"],
            })
    return projekt


def ladda_projekt(service, projekt_id, projekt_titel):
    filer = {}
    for filnamn in PROJEKTFILER:
        fil_id = hamta_fil_id(service, filnamn, projekt_id)
        if fil_id:
            filer[filnamn] = fil_id

    mappar = {}
    for mappnamn in PROJEKTMAPPAR:
        mapp_id = hamta_fil_id(service, mappnamn, projekt_id)
        if mapp_id:
            mappar[mappnamn] = mapp_id

    projekt = {
        "id": projekt_id,
        "titel": projekt_titel,
        "filer": filer,
        "mappar": mappar,
        "system_mapp_id": mappar.get("system"),  # enkel åtkomst
    }

    uppdatera_senaste_projekt(projekt_id, projekt_titel)
    return projekt

def nytt_projekt(service, titel):
    rot_id = hamta_rot(service)
    projekt = skapa_projekt(service, titel, rot_id)
    uppdatera_senaste_projekt(projekt["rot_id"], titel)
    return projekt


def hamta_dokumentstatus(service, projekt):
    status = {}
    for filnamn, fil_id in projekt["filer"].items():
        status[filnamn] = fil_id is not None
    return status