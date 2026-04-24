import os
import re
from drive import read_file, write_file, hamta_fil_id, create_file

SYNC_FILNAMN = "skrivaren_senaste_bok.txt"


def _dela_upp_kapitel(boktext: str) -> dict:
    kapitel = {}
    delar = re.split(r'(~\s*\d+\s*~)', boktext)
    nuvarande_nummer = None
    nuvarande_text = []

    for del_text in delar:
        match = re.match(r'~\s*(\d+)\s*~', del_text.strip())
        if match:
            if nuvarande_nummer is not None:
                kapitel[nuvarande_nummer] = "".join(
                    nuvarande_text
                ).strip()
            nuvarande_nummer = int(match.group(1))
            nuvarande_text = [del_text]
        elif nuvarande_nummer is not None:
            nuvarande_text.append(del_text)

    if nuvarande_nummer is not None:
        kapitel[nuvarande_nummer] = "".join(nuvarande_text).strip()

    return kapitel


def ladda_skrivaren_version(service, system_mapp_id: str) -> str:
    """
    Laddar skrivarens senast kända bokversion från Drive.
    Returnerar tom sträng om ingen version finns.
    """
    fil_id = hamta_fil_id(service, SYNC_FILNAMN, system_mapp_id)
    if not fil_id:
        return ""
    try:
        return read_file(service, fil_id)
    except Exception:
        return ""


def spara_skrivaren_version(service, system_mapp_id: str,
                             boktext: str):
    """
    Sparar hela den aktuella boken som skrivarens senast kända version.
    Anropas när skrivaren fått hela boken ELLER uppdaterade kapitel.
    """
    fil_id = hamta_fil_id(service, SYNC_FILNAMN, system_mapp_id)
    if fil_id:
        write_file(service, fil_id, boktext)
    else:
        create_file(service, SYNC_FILNAMN, boktext, system_mapp_id)


def hamta_andrade_kapitel(service, system_mapp_id: str,
                           bok_aktuell: str) -> str:
    """
    Jämför aktuell bok mot skrivarens senast kända version.

    Returnerar:
      Tom sträng om ingen tidigare version finns (hela boken skickas)
      Tom sträng om ingenting har ändrats
      Sträng med bara de kapitel som ändrats eller tillkommit
    """
    tidigare = ladda_skrivaren_version(service, system_mapp_id)
    if not tidigare:
        return ""
    if tidigare == bok_aktuell:
        return ""

    gamla_kapitel = _dela_upp_kapitel(tidigare)
    nya_kapitel = _dela_upp_kapitel(bok_aktuell)

    andrade = []

    for kap_nummer, ny_text in nya_kapitel.items():
        gammal_text = gamla_kapitel.get(kap_nummer, "")
        if ny_text != gammal_text:
            if kap_nummer not in gamla_kapitel:
                etikett = f"Kapitel {kap_nummer} -- nytt kapitel"
            else:
                etikett = f"Kapitel {kap_nummer} -- uppdaterat"
            andrade.append(f"[{etikett}]\n{ny_text}")

    for kap_nummer in gamla_kapitel:
        if kap_nummer not in nya_kapitel:
            andrade.append(
                f"[Kapitel {kap_nummer} -- borttaget av användaren]"
            )

    if not andrade:
        return ""

    return "\n\n---\n\n".join(andrade)


def behover_full_bokuppdatering(service, system_mapp_id: str) -> bool:
    """
    Returnerar True om ingen sparad skrivarversion finns --
    dvs. hela boken måste skickas.
    """
    fil_id = hamta_fil_id(service, SYNC_FILNAMN, system_mapp_id)
    return fil_id is None