import asyncio
from drive import las_google_doc, uppdatera_google_doc, hamta_fil_id, lista_filer
from prompts import analytiker_uppdatera_prompt
from adapters.claude import ClaudeAdapter
from adapters.chatgpt import ChatGPTAdapter
from adapters.grok import GrokAdapter

PLATSHALLARE = [
    "Text börjar här.",
    "Lägg in godkänd text här.",
    "Skapas av",
    "Redigera inte manuellt.",
    "Uppdateras efter varje",
    "Växer med varje",
]


def hamta_adapter(llm_namn):
    if llm_namn == "claude":
        return ClaudeAdapter()
    elif llm_namn == "chatgpt":
        return ChatGPTAdapter()
    elif llm_namn == "grok":
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


async def kor_analytiker(adapter, prompt, agent_namn,
                          dokument_att_bifoga=None):
    print(f"\n{agent_namn} arbetar...")
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()

    if dokument_att_bifoga and hasattr(adapter, 'bifoga_filer'):
        print(f"{agent_namn}: Bifogar {list(dokument_att_bifoga.keys())}...")
        resultat = await adapter.bifoga_filer(dokument_att_bifoga)
        print(f"{agent_namn}: bifoga_filer returnerade: {resultat}")
        if isinstance(resultat, dict) and resultat:
            extra = "\n\n".join(
                f"## {k.upper()}\n{v}"
                for k, v in resultat.items()
            )
            prompt = prompt + f"\n\n{extra}"

    svar = await adapter.skicka_meddelande(prompt)
    await adapter.stang()
    if not svar:
        print(f"  Varning: {agent_namn} returnerade inget svar.")
    return svar or ""

def ersatt_text_med_filreferens(prompt, dokument_att_bifoga):
    """
    Ersätter långa textblock i prompten med referenser till bifogade filer.
    """
    for filnamn, innehall in dokument_att_bifoga.items():
        if innehall and len(innehall) > 500:
            prompt = prompt.replace(
                innehall,
                f"(Se bifogad fil: {filnamn}.txt)"
            )
    return prompt

async def kor_initiering(service, projekt, llm_installningar,
                          status_callback=None):
    def status(meddelande):
        print(meddelande)
        if status_callback:
            status_callback(meddelande)

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
    status("Startar Stilanalytikern...")
    stil_prompt = analytiker_uppdatera_prompt(
        ny_text=boktext,
        befintlig_analys=dokument.get("stilguide", ""),
        analytiker_typ="stilanalytiker",
        exempeltexter=exempeltexter,
        storyline=storyline,
        smakprofil=smakprofil,    )
    if dokument_att_bifoga:
        stil_prompt = ersatt_text_med_filreferens(
            stil_prompt, dokument_att_bifoga
        )
    stil_adapter = hamta_adapter(
        llm_installningar.get("stilanalytikern", "claude")
    )
    stilguide = await kor_analytiker(
        stil_adapter, stil_prompt, "Stilanalytikern",
        dokument_att_bifoga=dokument_att_bifoga,
    )
    if stilguide:
        spara_analytiker_output(service, projekt, "stilguide", stilguide)
        status("Stilguide sparad.")

    # Karaktärskartläggaren
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
        stil_prompt = ersatt_text_med_filreferens(
            stil_prompt, dokument_att_bifoga
    )
    kar_adapter = hamta_adapter(
        llm_installningar.get("karaktarskartlaggaren", "claude")
    )
    karaktarer_output = await kor_analytiker(
        kar_adapter, karaktarer_prompt, "Karaktärskartläggaren",
        dokument_att_bifoga=dokument_att_bifoga,
    )
    if karaktarer_output:
        karaktarer, kontext = dela_upp_karaktarer_och_kontext(
            karaktarer_output
        )
        spara_analytiker_output(service, projekt, "karaktarer", karaktarer)
        if kontext:
            spara_analytiker_output(service, projekt, "kontext", kontext)
        status("Karaktärsdokument och kontext sparade.")

    # Dramaturgikonsulten
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
        stil_prompt = ersatt_text_med_filreferens(
            stil_prompt, dokument_att_bifoga
    )
    dram_adapter = hamta_adapter(
        llm_installningar.get("dramaturgikonsulten", "claude")
    )
    dramaturgi_output = await kor_analytiker(
        dram_adapter, dram_prompt, "Dramaturgikonsulten",
        dokument_att_bifoga=dokument_att_bifoga,
    )
    if dramaturgi_output:
        dramaturgi, observationer = dela_upp_dramaturgi_och_observationer(
            dramaturgi_output
        )
        spara_analytiker_output(service, projekt, "dramaturgi", dramaturgi)
        if observationer:
            spara_analytiker_output(
                service, projekt, "dramaturgi_observationer", observationer
            )
        status("Dramaturgi och observationer sparade.")

    status("\nInitiering klar! Alla analysrapporter sparade på Drive.")
    return True