import asyncio
from drive import las_google_doc, uppdatera_google_doc, hamta_fil_id, lista_filer
from prompts import analytiker_uppdatera_prompt
from flows.agent_runner import (
    kor_agent, FlodesPausad, ladda_tillstand,
    rensa_tillstand, spara_tillstand
)
from flows.flodes_state import ar_avbruten

PLATSHALLARE = [
    "Text börjar här.",
    "Lägg in godkänd text här.",
    "Skapas av",
    "Redigera inte manuellt.",
    "Uppdateras efter varje",
    "Växer med varje",
]

INITIERING_STEG_ORDNING = [
    "stilanalytiker",
    "karaktarskartlaggare",
    "dramaturgikonsult",
]


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
    else:
        raise ValueError(f"Okänd LLM: {llm_namn}")


def text_har_riktigt_innehall(text):
    if not text or not text.strip():
        return False
    rader = [r.strip() for r in text.split("\n") if r.strip()]
    riktiga_rader = []
    for rad in rader:
        ar_platshallare = any(p in rad for p in PLATSHALLARE)
        ar_rubrik = rad.startswith("#")
        ar_kapitelmarkor = rad.startswith("~")
        if not ar_platshallare and not ar_rubrik and not ar_kapitelmarkor:
            riktiga_rader.append(rad)
    return len(riktiga_rader) > 5


def ersatt_text_med_filreferens(prompt, dokument_att_bifoga):
    for filnamn, innehall in dokument_att_bifoga.items():
        if innehall and len(innehall) > 500:
            prompt = prompt.replace(
                innehall,
                f"(Se bifogad fil: {filnamn}.txt)"
            )
    return prompt


def hamta_exempeltexter(service, exempeltexter_mapp_id):
    filer = lista_filer(service, exempeltexter_mapp_id)
    exempeltexter = {}
    for fil in filer:
        try:
            text = las_google_doc(service, fil["id"])
            titel = fil["name"]
            exempeltexter[titel] = text
        except Exception as e:
            print(f"Kunde inte läsa exempeltextfil {fil['name']}: {e}")
    return exempeltexter if exempeltexter else None


def hamta_dokument(service, projekt):
    dokument = {}
    for filnamn in ["bok", "storyline", "stilguide",
                    "karaktarer", "kontext", "dramaturgi",
                    "dramaturgi_observationer", "smakprofil"]:
        fil_id = projekt["filer"].get(filnamn)
        if fil_id:
            try:
                innehall = las_google_doc(service, fil_id)
                dokument[filnamn] = innehall
            except Exception as e:
                print(f"Kunde inte läsa {filnamn}: {e}")
                dokument[filnamn] = ""
        else:
            dokument[filnamn] = ""
    dokument["exempeltexter"] = hamta_exempeltexter(
        service, projekt["mappar"]["exempeltexter"]
    )
    return dokument


def spara_analytiker_output(service, projekt, filnamn, innehall):
    fil_id = projekt["filer"].get(filnamn)
    if fil_id:
        uppdatera_google_doc(service, fil_id, innehall)
        print(f"  Sparade: {filnamn}")
    else:
        print(f"  Varning: Kunde inte hitta fil {filnamn} på Drive.")


def dela_upp_karaktarer_och_kontext(output):
    if "===KONTEXT===" in output:
        delar = output.split("===KONTEXT===")
        return delar[0].strip(), delar[1].strip()
    return output.strip(), ""


def dela_upp_dramaturgi_och_observationer(output):
    if "===OBSERVATIONER===" in output:
        delar = output.split("===OBSERVATIONER===")
        return delar[0].strip(), delar[1].strip()
    return output.strip(), ""


def _steg_fore(steg_namn):
    if steg_namn not in INITIERING_STEG_ORDNING:
        return []
    idx = INITIERING_STEG_ORDNING.index(steg_namn)
    return INITIERING_STEG_ORDNING[:idx]


def _kolla_avbryt(projekt_id, system_mapp_id, service,
                   steg_namn, flode_namn):
    """
    Kollar avbryt-flaggan mellan steg.
    Sparar tillstånd och kastar FlodesPausad om avbruten.
    """
    if projekt_id and ar_avbruten(projekt_id):
        print(f"Flöde avbrutet av användaren före: {steg_namn}")
        spara_tillstand(service, system_mapp_id, {
            "flode": flode_namn,
            "pausad_vid_steg": steg_namn,
            "fel": "Avbrutet av användaren",
        })
        raise FlodesPausad("Avbrutet av användaren")


async def kor_initiering(service, projekt, llm_installningar,
                          status_callback=None, endast_steg=None,
                          projekt_id=None):
    def status(meddelande):
        print(meddelande)
        if status_callback:
            status_callback(meddelande)

    system_mapp_id = projekt.get("system_mapp_id")
    rensa_tillstand(service, system_mapp_id)

    if endast_steg:
        hoppa_over = [s for s in INITIERING_STEG_ORDNING
                      if s != endast_steg]
        avsluta_efter = endast_steg
        status(f"Kör endast: {endast_steg}")
    else:
        avsluta_efter = None
        tillstand = ladda_tillstand(service, system_mapp_id)
        if tillstand and tillstand.get("flode") == "initiering":
            pausad_vid = tillstand.get("pausad_vid_steg")
            hoppa_over = _steg_fore(pausad_vid)
            status(f"Återupptar från: {pausad_vid}")
        else:
            hoppa_over = []

    status("Läser dokument från Drive...")
    dokument = hamta_dokument(service, projekt)

    boktext = dokument.get("bok", "")
    if not text_har_riktigt_innehall(boktext):
        print("OBS: Ingen riktig boktext -- analytikerna körs utan boktext.")
        boktext = ""
    storyline = dokument.get("storyline", "")
    smakprofil = dokument.get("smakprofil", "")
    exempeltexter = dokument.get("exempeltexter")

    dokument_att_bifoga = {}
    if boktext:
        dokument_att_bifoga["bok"] = boktext
    if storyline and text_har_riktigt_innehall(storyline):
        dokument_att_bifoga["storyline"] = storyline
    if exempeltexter:
        for titel, text in exempeltexter.items():
            dokument_att_bifoga[f"exempel_{titel}"] = text

    # Stilanalytikern
    if "stilanalytiker" not in hoppa_over:
        _kolla_avbryt(projekt_id, system_mapp_id, service,
                      "stilanalytiker", "initiering")
        status("Startar Stilanalytikern...")
        stil_prompt = analytiker_uppdatera_prompt(
            ny_text=boktext,
            befintlig_analys=dokument.get("stilguide", ""),
            analytiker_typ="stilanalytiker",
            exempeltexter=exempeltexter,
            storyline=storyline,
            smakprofil=smakprofil,
        )
        if dokument_att_bifoga:
            stil_prompt = ersatt_text_med_filreferens(
                stil_prompt, dokument_att_bifoga
            )
        try:
            stilguide = await kor_agent(
                adapter=hamta_adapter(
                    llm_installningar.get("stilanalytikern", "claude")
                ),
                prompt=stil_prompt,
                agent_namn="Stilanalytikern",
                service=service,
                system_mapp_id=system_mapp_id,
                flode_namn="initiering",
                steg_namn="stilanalytiker",
                projekt_id=projekt_id,
                dokument_att_bifoga=dokument_att_bifoga,
            )
            spara_analytiker_output(service, projekt, "stilguide", stilguide)
            status("Stilguide sparad.")
            if avsluta_efter == "stilanalytiker":
                rensa_tillstand(service, system_mapp_id)
                return {"klar": True}
        except FlodesPausad as e:
            status(f"Initiering pausad: {e}")
            return {"pausad": True, "steg": "stilanalytiker",
                    "fel": str(e)}
    else:
        status("Hoppar över Stilanalytikern (redan klar).")

    # Karaktärskartläggaren
    if "karaktarskartlaggare" not in hoppa_over:
        _kolla_avbryt(projekt_id, system_mapp_id, service,
                      "karaktarskartlaggare", "initiering")
        status("Startar Karaktärskartläggaren...")
        karaktarer_prompt = analytiker_uppdatera_prompt(
            ny_text=boktext,
            befintlig_analys=dokument.get("karaktarer", ""),
            analytiker_typ="karaktarskartlaggare",
            exempeltexter=exempeltexter,
            storyline=storyline,
            smakprofil=smakprofil,
        )
        if dokument_att_bifoga:
            karaktarer_prompt = ersatt_text_med_filreferens(
                karaktarer_prompt, dokument_att_bifoga
            )
        try:
            karaktarer_output = await kor_agent(
                adapter=hamta_adapter(
                    llm_installningar.get("karaktarskartlaggaren", "claude")
                ),
                prompt=karaktarer_prompt,
                agent_namn="Karaktärskartläggaren",
                service=service,
                system_mapp_id=system_mapp_id,
                flode_namn="initiering",
                steg_namn="karaktarskartlaggare",
                projekt_id=projekt_id,
                dokument_att_bifoga=dokument_att_bifoga,
            )
            karaktarer, kontext = dela_upp_karaktarer_och_kontext(
                karaktarer_output
            )
            spara_analytiker_output(
                service, projekt, "karaktarer", karaktarer
            )
            if kontext:
                spara_analytiker_output(
                    service, projekt, "kontext", kontext
                )
            status("Karaktärsdokument och kontext sparade.")
            if avsluta_efter == "karaktarskartlaggare":
                rensa_tillstand(service, system_mapp_id)
                return {"klar": True}
        except FlodesPausad as e:
            status(f"Initiering pausad: {e}")
            return {"pausad": True, "steg": "karaktarskartlaggare",
                    "fel": str(e)}
    else:
        status("Hoppar över Karaktärskartläggaren (redan klar).")

    # Dramaturgikonsulten
    if "dramaturgikonsult" not in hoppa_over:
        _kolla_avbryt(projekt_id, system_mapp_id, service,
                      "dramaturgikonsult", "initiering")
        status("Startar Dramaturgikonsulten...")
        dram_prompt = analytiker_uppdatera_prompt(
            ny_text=boktext,
            befintlig_analys=dokument.get("dramaturgi", ""),
            analytiker_typ="dramaturgikonsult",
            exempeltexter=exempeltexter,
            storyline=storyline,
            smakprofil=smakprofil,
        )
        if dokument_att_bifoga:
            dram_prompt = ersatt_text_med_filreferens(
                dram_prompt, dokument_att_bifoga
            )
        try:
            dramaturgi_output = await kor_agent(
                adapter=hamta_adapter(
                    llm_installningar.get("dramaturgikonsulten", "claude")
                ),
                prompt=dram_prompt,
                agent_namn="Dramaturgikonsulten",
                service=service,
                system_mapp_id=system_mapp_id,
                flode_namn="initiering",
                steg_namn="dramaturgikonsult",
                projekt_id=projekt_id,
                dokument_att_bifoga=dokument_att_bifoga,
            )
            dramaturgi, observationer = dela_upp_dramaturgi_och_observationer(
                dramaturgi_output
            )
            spara_analytiker_output(
                service, projekt, "dramaturgi", dramaturgi
            )
            if observationer:
                spara_analytiker_output(
                    service, projekt,
                    "dramaturgi_observationer", observationer
                )
            status("Dramaturgi och observationer sparade.")
            if avsluta_efter == "dramaturgikonsult":
                rensa_tillstand(service, system_mapp_id)
                return {"klar": True}
        except FlodesPausad as e:
            status(f"Initiering pausad: {e}")
            return {"pausad": True, "steg": "dramaturgikonsult",
                    "fel": str(e)}
    else:
        status("Hoppar över Dramaturgikonsulten (redan klar).")

    rensa_tillstand(service, system_mapp_id)
    status("Initiering klar!")
    return {"klar": True}