import asyncio
from flows.agent_runner import kor_agent_session, skicka_i_session, FlodesPausad

from drive import (
    las_google_doc,
    uppdatera_google_doc,
    hamta_fil_id,
    skapa_google_doc,
)
from prompts import (
    skrivare_ny_session_prompt_med_filer,
    skrivare_skriv_prompt,
    skrivare_full_kontext_prompt,
    skrivare_revidera_prompt,
    bokredaktor_prompt,
)
from bok_sync import (
    hamta_andrade_kapitel,
    spara_skrivaren_version,
    behover_full_bokuppdatering,
)


def hamta_projektdokument(service, projekt):
    """Läser alla dokument som behövs för skriv-flödet."""
    def las(filnamn):
        fil_id = projekt["filer"].get(filnamn)
        if not fil_id:
            return ""
        try:
            return las_google_doc(service, fil_id)
        except Exception as e:
            print(f"Kunde inte läsa {filnamn}: {e}")
            return ""

    return {
        "bok": las("bok"),
        "stilguide": las("stilguide"),
        "karaktarer": las("karaktarer"),
        "kontext": las("kontext"),
        "dramaturgi": las("dramaturgi"),
        "smakprofil": las("smakprofil"),
        "storyline": las("storyline"),
    }


def hamta_adapter(llm_namn):
    if llm_namn == "claude":
        from adapters.claude import ClaudeAdapter
        return ClaudeAdapter()
    elif llm_namn == "chatgpt":
        from adapters.chatgpt import ChatGPTAdapter
        return ChatGPTAdapter()
    elif llm_namn == "grok":
        from adapters.grok import GrokAdapter
        return GrokAdapter()
    raise ValueError(f"Okänd LLM: {llm_namn}")


async def kor_skriv_flode(service, projekt, llm_installningar,
                           uppgift, full_kontext=False,
                           max_varv=None, status_callback=None):
    def status(meddelande):
        print(meddelande)
        if status_callback:
            status_callback(meddelande)

    if max_varv is None:
        from config import lас_config
        config = lас_config()
        max_varv = config.get("max_redaktor_varv", 3)

    status("Läser projektdokument från Drive...")
    dok = hamta_projektdokument(service, projekt)
    system_mapp_id = projekt.get("system_mapp_id")

    skrivare_llm = llm_installningar.get("skrivaren", "claude")
    redaktor_llm = llm_installningar.get("bokredaktoren", "claude")

    # Bygg dokument att bifoga
    dokument_att_bifoga = {}
    if dok["bok"]: dokument_att_bifoga["bok"] = dok["bok"]
    if dok["stilguide"]: dokument_att_bifoga["stilguide"] = dok["stilguide"]
    if dok["karaktarer"]: dokument_att_bifoga["karaktarer"] = dok["karaktarer"]
    if dok["dramaturgi"]: dokument_att_bifoga["dramaturgi"] = dok["dramaturgi"]
    if dok["kontext"]: dokument_att_bifoga["kontext"] = dok["kontext"]

    # Starta skrivarsession
    status(f"Startar Skrivaren ({skrivare_llm})...")
    skrivare = hamta_adapter(skrivare_llm)
    try:
        extra = await kor_agent_session(skrivare, dokument_att_bifoga)
    except Exception as e:
        fel = str(e).split('\n')[0][:120]
        raise FlodesPausad(f"Skrivaren: {fel}")

    # Sessionsstart-prompt
    if full_kontext or behover_full_bokuppdatering(service, system_mapp_id):
        status("Laddar kontext till Skrivaren...")
        session_prompt = skrivare_ny_session_prompt_med_filer(
            boktext_filnamn="bok.txt",
            stilguide_filnamn="stilguide.txt",
            karaktarer_filnamn="karaktarer.txt",
            dramaturgi_filnamn="dramaturgi.txt",
            kontext_filnamn="kontext.txt",
            smakprofil=dok["smakprofil"],
            storyline=dok["storyline"],
        )
        if extra:
            session_prompt += "\n\n" + "\n\n".join(
                f"## {k.upper()}\n{v}" for k, v in extra.items()
            )
        try:
            bekraftelse = await skicka_i_session(
                skrivare, session_prompt, "Skrivaren",
                service, system_mapp_id,
                "skriv", "session_start",
            )
            status(f"Skrivaren bekräftade: {bekraftelse[:60]}")
        except FlodesPausad:
            await skrivare.stang()
            raise
        spara_skrivaren_version(service, system_mapp_id, dok["bok"])
        andrade_kapitel = None
    else:
        andrade_kapitel = hamta_andrade_kapitel(
            service, system_mapp_id, dok["bok"]
        )
        if andrade_kapitel:
            status("Hittade uppdaterade kapitel sedan senaste session.")
        else:
            status("Inga ändringar sedan senaste session.")

    # Skriv utkast
    status("Skrivaren skriver utkast...")
    if full_kontext:
        skriva_prompt = skrivare_full_kontext_prompt(
            uppgift=uppgift,
            boktext=dok["bok"],
            stilguide=dok["stilguide"],
            karaktarer=dok["karaktarer"],
            dramaturgi=dok["dramaturgi"],
            kontext=dok["kontext"],
            smakprofil=dok["smakprofil"],
            storyline=dok["storyline"],
        )
    else:
        skriva_prompt = skrivare_skriv_prompt(
            uppgift=uppgift,
            kontext=dok["kontext"],
            stilguide=dok["stilguide"],
            karaktarer=dok["karaktarer"],
            dramaturgi=dok["dramaturgi"],
            smakprofil=dok["smakprofil"],
            storyline=dok["storyline"],
            andrade_kapitel=andrade_kapitel,
        )

    try:
        utkast = await skicka_i_session(
            skrivare, skriva_prompt, "Skrivaren",
            service, system_mapp_id, "skriv", "skriva",
        )
    except FlodesPausad:
        await skrivare.stang()
        raise

    status(f"Utkast mottaget ({len(utkast)} tecken).")

    # Starta redaktörssession
    status(f"Startar Bokredaktören ({redaktor_llm})...")
    redaktor = hamta_adapter(redaktor_llm)

    # Redaktören får samma dokument minus bok (inte nödvändig)
    redaktor_dok = {k: v for k, v in dokument_att_bifoga.items() if k != "bok"}
    try:
        extra_red = await kor_agent_session(redaktor, redaktor_dok)
    except Exception as e:
        await skrivare.stang()
        fel = str(e).split('\n')[0][:120]
        raise FlodesPausad(f"Bokredaktören: {fel}")

    godkant = False
    slutligt_utkast = utkast
    all_feedback = []

    for varv in range(1, max_varv + 1):
        status(f"Bokredaktören granskar (varv {varv}/{max_varv})...")
        redaktor_prompt_text = bokredaktor_prompt(
            utkast=slutligt_utkast,
            stilguide=dok["stilguide"],
            karaktarer=dok["karaktarer"],
            dramaturgi=dok["dramaturgi"],
            smakprofil=dok["smakprofil"],
        )
        if extra_red and varv == 1:
            redaktor_prompt_text += "\n\n" + "\n\n".join(
                f"## {k.upper()}\n{v}" for k, v in extra_red.items()
            )

        try:
            feedback = await skicka_i_session(
                redaktor, redaktor_prompt_text, "Bokredaktören",
                service, system_mapp_id, "skriv", f"granska_varv_{varv}",
            )
        except FlodesPausad:
            await skrivare.stang()
            await redaktor.stang()
            raise

        all_feedback.append(f"VARV {varv}:\n{feedback}")
        print(f"Redaktörens feedback (varv {varv}):\n{feedback[:500]}")

        # Extrahera bara beslutsraden
        besluts_rad = ""
        for rad in feedback.split('\n'):
            rad_strip = rad.strip()
            if rad_strip.startswith("GODKÄNT") or rad_strip.startswith("OMSKRIVNING"):
                besluts_rad = rad_strip
                break

        if besluts_rad.startswith("GODKÄNT"):
            status("Bokredaktören godkände utkastet!")
            godkant = True
            break

        status(f"Bokredaktören begär omskrivning (varv {varv}).")

        if varv < max_varv:
            revidera_prompt = skrivare_revidera_prompt(
                utkast=slutligt_utkast,
                redaktor_feedback=feedback,
            )
            try:
                reviderat = await skicka_i_session(
                    skrivare, revidera_prompt, "Skrivaren",
                    service, system_mapp_id, "skriv", f"revidera_varv_{varv}",
                )
            except FlodesPausad:
                await skrivare.stang()
                await redaktor.stang()
                raise
            slutligt_utkast = reviderat
            status(f"Skrivaren reviderade ({len(reviderat)} tecken).")
        else:
            status(f"Max antal varv ({max_varv}) nått utan godkännande.")

    await skrivare.stang()
    await redaktor.stang()

    # Spara utkast
    kapitel_namn = _hamta_kapitelnamn(uppgift)
    utkast_mapp_id = projekt["mappar"].get("utkast")
    if utkast_mapp_id:
        befintlig_id = hamta_fil_id(service, kapitel_namn, utkast_mapp_id)
        if befintlig_id:
            uppdatera_google_doc(service, befintlig_id, slutligt_utkast)
        else:
            skapa_google_doc(service, kapitel_namn, slutligt_utkast, utkast_mapp_id)
        status(f"Utkast sparat som '{kapitel_namn}' i utkast-mappen.")

    spara_skrivaren_version(service, system_mapp_id, dok["bok"])

    logg_mapp_id = projekt["mappar"].get("agentlogg")
    if logg_mapp_id and all_feedback:
        import datetime
        tidstampel = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        logg_namn = f"redaktor_feedback_{tidstampel}"
        logg_innehall = "\n\n===VARV===\n\n".join(all_feedback)
        skapa_google_doc(service, logg_namn, logg_innehall, logg_mapp_id)

    return {
        "utkast": slutligt_utkast,
        "godkant": godkant,
        "kapitel_namn": kapitel_namn,
    }

def _hamta_kapitelnamn(uppgift):
    """
    Försöker extrahera ett kapitelnamn från uppgiften.
    Exempel: 'Skriv kapitel 12' -> 'kap_12_skrivaren'
    """
    import re
    match = re.search(r'kapitel\s*(\d+)', uppgift.lower())
    if match:
        return f"kap_{match.group(1)}_skrivaren"
    return "utkast_skrivaren"