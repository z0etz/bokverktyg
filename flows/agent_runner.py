"""
Generell agent-runner med pausning och återupptagning.
Kan användas av alla flöden.
"""
import json
import datetime
from drive import (
    hamta_fil_id, las_google_doc,
    uppdatera_google_doc, skapa_google_doc
)

TILLSTAND_FILNAMN = "flodestillstand"


class FlodesPausad(Exception):
    """Kastas när ett agentanrop misslyckas och flödet pausas."""
    pass


def spara_tillstand(service, system_mapp_id, tillstand):
    tillstand["sparad"] = datetime.datetime.now().isoformat()
    innehall = json.dumps(tillstand, ensure_ascii=False, indent=2)
    fil_id = hamta_fil_id(service, TILLSTAND_FILNAMN, system_mapp_id)
    if fil_id:
        uppdatera_google_doc(service, fil_id, innehall)
    else:
        skapa_google_doc(
            service, TILLSTAND_FILNAMN, innehall, system_mapp_id
        )


def ladda_tillstand(service, system_mapp_id):
    fil_id = hamta_fil_id(service, TILLSTAND_FILNAMN, system_mapp_id)
    if not fil_id:
        return None
    try:
        innehall = las_google_doc(service, fil_id)
        data = json.loads(innehall)
        return data if data else None
    except Exception:
        return None


def rensa_tillstand(service, system_mapp_id):
    fil_id = hamta_fil_id(service, TILLSTAND_FILNAMN, system_mapp_id)
    if fil_id:
        uppdatera_google_doc(service, fil_id, "{}")


async def kor_agent(adapter, prompt, agent_namn,
                    service, system_mapp_id,
                    flode_namn, steg_namn,
                    projekt_id=None,
                    dokument_att_bifoga=None,
                    extra_context=None):
    print(f"\n{agent_namn} arbetar...")
    try:
        await adapter.starta(visa_webblasare=True)
        await adapter.ny_konversation()

        if dokument_att_bifoga and hasattr(adapter, 'bifoga_filer'):
            print(f"{agent_namn}: Bifogar {list(dokument_att_bifoga.keys())}...")
            resultat = await adapter.bifoga_filer(dokument_att_bifoga)
            if isinstance(resultat, dict) and resultat:
                extra = "\n\n".join(
                    f"## {k.upper()}\n{v}"
                    for k, v in resultat.items()
                )
                prompt = prompt + f"\n\n{extra}"

        svar = await adapter.skicka_meddelande(prompt)
        senaste_fel = getattr(adapter, 'senaste_fel', None)
        await adapter.stang()

    except Exception as e:
        fel_full = str(e)
        # Ta bara första raden av felmeddelandet
        fel = fel_full.split('\n')[0][:120]
        print(f"  {agent_namn} kraschade: {fel_full}")  # Fullt fel i terminalen
        try:
            await adapter.stang()
        except Exception:
            pass
        spara_tillstand(service, system_mapp_id, {
            "flode": flode_namn,
            "pausad_vid_steg": steg_namn,
            "fel": fel,
            "extra": extra_context or {},
        })
        raise FlodesPausad(f"{agent_namn}: {fel}")

    if not svar:
        fel = senaste_fel or f"Inget svar från {agent_namn}."
        print(f"  {agent_namn} misslyckades: {fel}")
        spara_tillstand(service, system_mapp_id, {
            "flode": flode_namn,
            "pausad_vid_steg": steg_namn,
            "fel": fel,
            "extra": extra_context or {},
        })
        raise FlodesPausad(f"{agent_namn}: {fel}")

    print(f"  {agent_namn}: {len(svar)} tecken mottagna.")
    return svar

async def kor_agent_session(adapter, dokument_att_bifoga=None):
    """
    Startar en adapter-session med bifogade filer.
    Returnerar adaptern redo för skicka_meddelande-anrop.
    Anroparen ansvarar för att anropa adapter.stang() när sessionen är klar.
    """
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()

    if dokument_att_bifoga and hasattr(adapter, 'bifoga_filer'):
        print(f"Bifogar {list(dokument_att_bifoga.keys())}...")
        resultat = await adapter.bifoga_filer(dokument_att_bifoga)
        if isinstance(resultat, dict) and resultat:
            return resultat  # extra text att lägga till i första prompt
    return {}


async def skicka_i_session(adapter, prompt, agent_namn,
                            service, system_mapp_id,
                            flode_namn, steg_namn,
                            extra_context=None):
    """
    Skickar ett meddelande i en redan startad session.
    Kastar FlodesPausad om inget svar.
    """
    try:
        svar = await adapter.skicka_meddelande(prompt)
        senaste_fel = getattr(adapter, 'senaste_fel', None)
    except Exception as e:
        fel_full = str(e)
        fel = fel_full.split('\n')[0][:120]
        print(f"  {agent_namn} kraschade: {fel_full}")
        spara_tillstand(service, system_mapp_id, {
            "flode": flode_namn,
            "pausad_vid_steg": steg_namn,
            "fel": fel,
            "extra": extra_context or {},
        })
        raise FlodesPausad(f"{agent_namn}: {fel}")

    if not svar:
        fel = senaste_fel or f"Inget svar från {agent_namn}."
        print(f"  {agent_namn} misslyckades: {fel}")
        spara_tillstand(service, system_mapp_id, {
            "flode": flode_namn,
            "pausad_vid_steg": steg_namn,
            "fel": fel,
            "extra": extra_context or {},
        })
        raise FlodesPausad(f"{agent_namn}: {fel}")

    print(f"  {agent_namn}: {len(svar)} tecken mottagna.")
    return svar