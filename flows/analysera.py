import asyncio
import datetime
from drive import (
    las_google_doc,
    uppdatera_google_doc,
    hamta_fil_id,
    skapa_google_doc,
    lista_filer,
)
from prompts import (
    forlаgsredaktor_prompt,
    smaktranare_prompt,
    analytiker_uppdatera_prompt,
)


def hamta_utkastpar(service, utkast_mapp_id):
    """
    Returnerar lista med kapitelnamn där både
    _skrivaren och _manuell finns.
    """
    filer = lista_filer(service, utkast_mapp_id)
    filnamn = {f["name"]: f["id"] for f in filer}
    
    par = []
    for namn, fil_id in filnamn.items():
        if namn.endswith("_skrivaren"):
            bas = namn[:-len("_skrivaren")]
            manuell_namn = bas + "_manuell"
            if manuell_namn in filnamn:
                par.append({
                    "namn": bas,
                    "skrivaren_id": fil_id,
                    "manuell_id": filnamn[manuell_namn],
                    "display": bas.replace("_", " ").title(),
                })
    return par


def generera_diff(skrivaren_text, manuell_text):
    """
    Genererar en läsbar diff mellan skrivarens och
    användarens version på styckenivå.
    """
    import difflib

    skrivaren_stycken = [
        s.strip() for s in skrivaren_text.split("\n\n")
        if s.strip()
    ]
    manuell_stycken = [
        s.strip() for s in manuell_text.split("\n\n")
        if s.strip()
    ]

    diff = list(difflib.unified_diff(
        skrivaren_stycken,
        manuell_stycken,
        lineterm="",
        n=0,
    ))

    if not diff:
        return ""

    borttagna = []
    tillagda = []

    for rad in diff:
        if rad.startswith("-") and not rad.startswith("---"):
            borttagna.append(rad[1:].strip())
        elif rad.startswith("+") and not rad.startswith("+++"):
            tillagda.append(rad[1:].strip())

    resultat = []
    if borttagna:
        resultat.append("BORTTAGET ELLER ÄNDRAT:")
        for s in borttagna[:10]:
            resultat.append(f"  - {s[:200]}")
    if tillagda:
        resultat.append("\nTILLLAGT ELLER ERSATT MED:")
        for s in tillagda[:10]:
            resultat.append(f"  + {s[:200]}")

    return "\n".join(resultat)


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


async def kor_analytiker_uppdatering(service, projekt,
                                      llm_installningar,
                                      analytiker_typ,
                                      ny_text, status):
    """Kör en enskild analytiker och sparar uppdaterad rapport."""
    filnamn_karta = {
        "stilanalytiker": "stilguide",
        "karaktarskartlaggare": ["karaktarer", "kontext"],
        "dramaturgikonsult": ["dramaturgi", "dramaturgi_observationer"],
    }

    def las(filnamn):
        fil_id = projekt["filer"].get(filnamn)
        if not fil_id:
            return ""
        try:
            return las_google_doc(service, fil_id)
        except Exception:
            return ""

    befintlig = las(
        filnamn_karta[analytiker_typ]
        if isinstance(filnamn_karta[analytiker_typ], str)
        else filnamn_karta[analytiker_typ][0]
    )
    smakprofil = las("smakprofil")
    storyline = las("storyline")

    prompt = analytiker_uppdatera_prompt(
        ny_text=ny_text,
        befintlig_analys=befintlig,
        analytiker_typ=analytiker_typ,
        storyline=storyline,
        smakprofil=smakprofil,
    )

    llm_karta = {
        "stilanalytiker": "stilanalytikern",
        "karaktarskartlaggare": "karaktarskartlaggaren",
        "dramaturgikonsult": "dramaturgikonsulten",
    }
    llm_namn = llm_installningar.get(llm_karta[analytiker_typ], "claude")

    status(f"Startar {analytiker_typ} ({llm_namn})...")
    adapter = hamta_adapter(llm_namn)
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()
    svar = await adapter.skicka_meddelande(prompt)
    await adapter.stang()

    if not svar:
        status(f"Varning: {analytiker_typ} returnerade inget svar.")
        return

    if analytiker_typ == "stilanalytiker":
        fil_id = projekt["filer"].get("stilguide")
        if fil_id:
            uppdatera_google_doc(service, fil_id, svar)
            status("Stilguide uppdaterad.")

    elif analytiker_typ == "karaktarskartlaggare":
        if "===KONTEXT===" in svar:
            delar = svar.split("===KONTEXT===")
            karaktarer_text = delar[0].strip()
            kontext_text = delar[1].strip()
        else:
            karaktarer_text = svar
            kontext_text = ""

        fil_id = projekt["filer"].get("karaktarer")
        if fil_id:
            uppdatera_google_doc(service, fil_id, karaktarer_text)
        if kontext_text:
            fil_id = projekt["filer"].get("kontext")
            if fil_id:
                uppdatera_google_doc(service, fil_id, kontext_text)
        status("Karaktärer och kontext uppdaterade.")

    elif analytiker_typ == "dramaturgikonsult":
        if "===OBSERVATIONER===" in svar:
            delar = svar.split("===OBSERVATIONER===")
            dramaturgi_text = delar[0].strip()
            obs_text = delar[1].strip()
        else:
            dramaturgi_text = svar
            obs_text = ""

        fil_id = projekt["filer"].get("dramaturgi")
        if fil_id:
            uppdatera_google_doc(service, fil_id, dramaturgi_text)
        if obs_text:
            fil_id = projekt["filer"].get("dramaturgi_observationer")
            if fil_id:
                uppdatera_google_doc(service, fil_id, obs_text)
        status("Dramaturgi och observationer uppdaterade.")


async def kor_analysera_flode(service, projekt, llm_installningar,
                               kapitel_namn, ignorera_flaggor=False,
                               status_callback=None):
    """
    Kör analysera-flödet:
    1. Läser skrivarens och användarens version
    2. Förlagsredaktören granskar
    3. Om flaggor: visa för användaren och vänta
    4. Smaktränaren analyserar diff
    5. Berörda analytiker uppdateras
    """

    def status(meddelande):
        print(meddelande)
        if status_callback:
            status_callback(meddelande)

    utkast_mapp_id = projekt["mappar"].get("utkast")

    skrivaren_id = hamta_fil_id(
        service, kapitel_namn + "_skrivaren", utkast_mapp_id
    )
    manuell_id = hamta_fil_id(
        service, kapitel_namn + "_manuell", utkast_mapp_id
    )

    if not skrivaren_id or not manuell_id:
        status("Kunde inte hitta utkastparet på Drive.")
        return None

    status("Läser utkast från Drive...")
    skrivaren_text = las_google_doc(service, skrivaren_id)
    manuell_text = las_google_doc(service, manuell_id)

    def las(filnamn):
        fil_id = projekt["filer"].get(filnamn)
        if not fil_id:
            return ""
        try:
            return las_google_doc(service, fil_id)
        except Exception:
            return ""

    kontext = las("kontext")
    smakprofil = las("smakprofil")

    flaggor = None
    if not ignorera_flaggor:
        status(f"Startar Förlagsredaktören...")
        forlags_llm = llm_installningar.get(
            "forlаgsredaktoren", "claude"
        )
        forlags_adapter = hamta_adapter(forlags_llm)
        await forlags_adapter.starta(visa_webblasare=True)
        await forlags_adapter.ny_konversation()

        forlags_prompt = forlаgsredaktor_prompt(
            skrivaren_utkast=skrivaren_text,
            anvandare_utkast=manuell_text,
            kontext=kontext,
            smakprofil=smakprofil,
        )
        forlags_svar = await forlags_adapter.skicka_meddelande(
            forlags_prompt
        )
        await forlags_adapter.stang()

        if forlags_svar and "FLAGGAT" in forlags_svar.upper():
            status("Förlagsredaktören flaggade problem.")
            flaggor = forlags_svar
            return {
                "status": "flaggat",
                "flaggor": flaggor,
                "kapitel_namn": kapitel_namn,
            }
        else:
            status("Förlagsredaktören godkände -- fortsätter.")

    status("Startar Smaktränaren...")
    diff_text = generera_diff(skrivaren_text, manuell_text)

    smak_llm = llm_installningar.get("smaktranaren", "claude")
    smak_adapter = hamta_adapter(smak_llm)
    await smak_adapter.starta(visa_webblasare=True)
    await smak_adapter.ny_konversation()

    smak_prompt = smaktranare_prompt(
        skrivaren_utkast=skrivaren_text,
        anvandare_utkast=manuell_text,
        smakprofil=smakprofil,
        kontext=kontext,
        diff_text=diff_text,
    )
    smak_svar = await smak_adapter.skicka_meddelande(smak_prompt)
    await smak_adapter.stang()

    if not smak_svar:
        status("Smaktränaren returnerade inget svar.")
        return None

    ny_smakprofil = ""
    analytiker_tillagg = ""

    if "===SMAKPROFIL===" in smak_svar:
        delar = smak_svar.split("===SMAKPROFIL===")
        analytiker_tillagg = delar[0].strip()
        ny_smakprofil = delar[1].strip()
    else:
        ny_smakprofil = smak_svar

    if ny_smakprofil:
        smak_fil_id = projekt["filer"].get("smakprofil")
        if smak_fil_id:
            uppdatera_google_doc(service, smak_fil_id, ny_smakprofil)
            status("Smakprofil uppdaterad.")

    logg_mapp_id = projekt["mappar"].get("agentlogg")
    if logg_mapp_id and analytiker_tillagg:
        tidstampel = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        skapa_google_doc(
            service,
            f"smaktranare_analys_{tidstampel}",
            analytiker_tillagg,
            logg_mapp_id,
        )

    berorda = _hamta_berorda_analytiker(analytiker_tillagg)
    status(f"Berörda analytiker: {berorda}")

    kombinerad_text = manuell_text

    for analytiker in berorda:
        await kor_analytiker_uppdatering(
            service, projekt, llm_installningar,
            analytiker, kombinerad_text, status,
        )

    status("Analysera-flödet klart!")
    return {
        "status": "klar",
        "kapitel_namn": kapitel_namn,
        "smakprofil_uppdaterad": bool(ny_smakprofil),
        "analytiker_uppdaterade": berorda,
    }


def _hamta_berorda_analytiker(smaktranare_analys):
    """
    Läser Smaktränaren output och identifierar vilka
    analytiker som ska uppdateras.
    """
    berorda = []
    analys_lower = smaktranare_analys.lower()

    if "stilanalytiker" in analys_lower:
        berorda.append("stilanalytiker")
    if "karaktarskartlaggare" in analys_lower or "karaktär" in analys_lower:
        berorda.append("karaktarskartlaggare")
    if "dramaturgikonsult" in analys_lower or "dramaturgi" in analys_lower:
        berorda.append("dramaturgikonsult")

    if not berorda:
        berorda = ["karaktarskartlaggare", "dramaturgikonsult"]

    return berorda
