from drive import (
    get_drive_service,
    get_or_create_folder,
    get_file_id,
    list_files,
    skapa_projekt,
)
from config import lас_config, uppdatera_senaste_projekt

ROT_MAPP = "Bokverktyg"

PROJEKTFILER = [
    "bok.md",
    "storyline.md",
    "stilguide.md",
    "karaktarer.md",
    "kontext.md",
    "dramaturgi.md",
    "dramaturgi_observationer.md",
    "smakprofil.md",
]

PROJEKTMAPPAR = ["utkast", "exempeltexter", "agentlogg"]


def hamta_rot(service):
    return get_or_create_folder(service, ROT_MAPP)


def lista_projekt(service):
    rot_id = hamta_rot(service)
    mappar = list_files(service, rot_id)
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
        fil_id = get_file_id(service, filnamn, projekt_id)
        if fil_id:
            filer[filnamn] = fil_id

    mappar = {}
    for mappnamn in PROJEKTMAPPAR:
        mapp_id = get_file_id(service, mappnamn, projekt_id)
        if mapp_id:
            mappar[mappnamn] = mapp_id

    projekt = {
        "id": projekt_id,
        "titel": projekt_titel,
        "filer": filer,
        "mappar": mappar,
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