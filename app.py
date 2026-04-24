from flask import Flask, render_template, redirect, url_for, request, jsonify

from config import (
    DEFAULT_CONFIG,
    TILLGANGLIGA_LLMS,
    hamta_llm,
    lас_config,
    uppdatera_llm,
)
from drive import hamta_drive_tjanst
from projekt import hamta_dokumentstatus, ladda_projekt, lista_projekt, nytt_projekt

app = Flask(__name__)
app.secret_key = "bokverktyg-hemlig-nyckel"

_service = None


def get_service():
    global _service
    if _service is None:
        _service = hamta_drive_tjanst()
    return _service


@app.route("/")
def index():
    config = lас_config()
    senaste = config.get("senaste_projekt")
    if senaste:
        return redirect(url_for("projekt_vy", projekt_id=senaste["id"]))
    return redirect(url_for("huvudmeny"))


@app.route("/huvudmeny")
def huvudmeny():
    service = get_service()
    projekt = lista_projekt(service)
    return render_template("huvudmeny.html", projekt=projekt)


@app.route("/projekt/<projekt_id>")
def projekt_vy(projekt_id):
    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")

    projekt = ladda_projekt(service, projekt_id, titel)
    dokumentstatus = hamta_dokumentstatus(service, projekt)

    agenter = list(DEFAULT_CONFIG["llm_per_agent"].keys())
    llm_installningar = {
        agent: hamta_llm(agent) for agent in agenter
    }

    return render_template(
        "projekt.html",
        projekt=projekt,
        dokumentstatus=dokumentstatus,
        llm_installningar=llm_installningar,
        tillgangliga_llms=TILLGANGLIGA_LLMS,
        agenter=agenter,
    )


@app.route("/nytt-projekt", methods=["POST"])
def skapa_projekt_route():
    titel = request.form.get("titel", "").strip()
    if not titel:
        return redirect(url_for("huvudmeny?fel=tomt_namn"))
    service = get_service()
    befintliga = lista_projekt(service)
    if any(p["titel"].lower() == titel.lower() for p in befintliga):
        return redirect(url_for("huvudmeny") + "?fel=namn_finns")
    projekt = nytt_projekt(service, titel)
    return redirect(url_for("projekt_vy", projekt_id=projekt["rot_id"]))


@app.route("/api/llm", methods=["POST"])
def uppdatera_llm_route():
    data = request.get_json()
    agent = data.get("agent")
    llm = data.get("llm")
    if agent and llm:
        uppdatera_llm(agent, llm)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400


@app.route("/valjprojekt/<projekt_id>/<projekt_titel>")
def valj_projekt(projekt_id, projekt_titel):
    service = get_service()
    ladda_projekt(service, projekt_id, projekt_titel)
    return redirect(url_for("projekt_vy", projekt_id=projekt_id))

@app.route("/initiering/<projekt_id>", methods=["POST"])
def initiering_route(projekt_id):
    from flows.initiering import kor_initiering
    import asyncio

    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")

    projekt = ladda_projekt(service, projekt_id, titel)
    llm_installningar = config.get("llm_per_agent", {})

    def kor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                kor_initiering(service, projekt, llm_installningar)
            )
        finally:
            loop.close()

    import threading
    trad = threading.Thread(target=kor)
    trad.start()

    return jsonify({"status": "startad"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)