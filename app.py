import asyncio
import threading    
from flask import Flask, render_template, redirect, url_for, request, jsonify
from drive import hamta_drive_tjanst
from projekt import hamta_dokumentstatus, ladda_projekt, lista_projekt, nytt_projekt
from flows.flodes_state import satt_avbryt, rensa_avbryt
from flows.initiering import kor_initiering
from flows.agent_runner import ladda_tillstand, rensa_tillstand, FlodesPausad
from flows.skriv import kor_skriv_flode
from flows.analysera import hamta_utkastpar, kor_analysera_flode

from config import (
    DEFAULT_CONFIG,
    TILLGANGLIGA_LLMS,
    hamta_llm,
    lас_config,
    uppdatera_llm,
)

app = Flask(__name__)
app.secret_key = "bokverktyg-hemlig-nyckel"

_flodes_status = {}
_flodes_lock = threading.Lock()
_service = None

def get_service():
    global _service
    if _service is None:
        _service = hamta_drive_tjanst()
    return _service

def starta_trad(projekt_id, target):
    if not _flodes_lock.acquire(blocking=False):
        return False
    
    def wrapper():
        try:
            target()
        finally:
            _flodes_lock.release()
    
    trad = threading.Thread(target=wrapper)
    trad.start()
    return True

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
    data = request.get_json() or {}
    steg = data.get("steg", "full")
    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")
    projekt = ladda_projekt(service, projekt_id, titel)
    llm_installningar = config.get("llm_per_agent", {})

    rensa_avbryt(projekt_id)
    _flodes_status[projekt_id] = {"status": "kor"}

    def kor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                kor_initiering(
                    service, projekt, llm_installningar,
                    endast_steg=steg if steg != "full" else None,
                    projekt_id=projekt_id,
                    tvinga_nystart=True,
                )
            )
            if res and res.get("pausad"):
                _flodes_status[projekt_id] = {
                    "status": "pausad",
                    "steg": res.get("steg"),
                    "fel": res.get("fel"),
                }
            else:
                _flodes_status[projekt_id] = {"status": "klar"}
        except FlodesPausad as e:
            _flodes_status[projekt_id] = {
                "status": "pausad",
                "fel": str(e),
            }
        except Exception as e:
            print(f"Fel i initieringsflödet: {e}")
            _flodes_status[projekt_id] = {"status": "fel", "fel": str(e)}
        finally:
            loop.close()

    if not starta_trad(projekt_id, kor):
        return jsonify({"status": "upptagen"}), 409
    return jsonify({"status": "startad"})

@app.route("/avbryt/<projekt_id>", methods=["POST"])
def avbryt_route(projekt_id):
    satt_avbryt(projekt_id)
    _flodes_status[projekt_id] = {"status": "avbryter"}
    return jsonify({"status": "ok"})


@app.route("/aterupptas/<projekt_id>", methods=["POST"])
def aterupptas_route(projekt_id):
    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")
    projekt = ladda_projekt(service, projekt_id, titel)

    tillstand = ladda_tillstand(service, projekt.get("system_mapp_id"))
    if not tillstand or not tillstand.get("flode"):
        return jsonify({"status": "inget_tillstand"})

    rensa_avbryt(projekt_id)
    _flodes_status[projekt_id] = {"status": "kor"}

    flode = tillstand.get("flode")
    llm_installningar = config.get("llm_per_agent", {})

    def kor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if flode == "initiering":
                from flows.initiering import kor_initiering
                res = loop.run_until_complete(
                    kor_initiering(
                        service, projekt, llm_installningar,
                        projekt_id=projekt_id,
                    )
                )  
            elif flode == "skriv":
                res = loop.run_until_complete(
                    kor_skriv_flode(
                        service, projekt, llm_installningar,
                        uppgift=tillstand.get("uppgift", ""),
                        aterupptagning=True,
                        sparat_utkast=tillstand.get("utkast"),
                        sparat_feedback=tillstand.get("senaste_feedback"),
                    )
                )
            else:
                res = {"klar": True}

            if res and res.get("pausad"):
                _flodes_status[projekt_id] = {
                    "status": "pausad",
                    "steg": res.get("steg"),
                    "fel": res.get("fel"),
                }
            else:
                _flodes_status[projekt_id] = {"status": "klar"}
        except FlodesPausad as e:
            _flodes_status[projekt_id] = {
                "status": "pausad",
                "fel": str(e),
            }
        except Exception as e:
            print(f"Fel vid återupptagning: {e}")
            _flodes_status[projekt_id] = {"status": "fel", "fel": str(e)}
        finally:
            loop.close()
    if not starta_trad(projekt_id, kor):
        return jsonify({"status": "upptagen"}), 409
    return jsonify({"status": "startad"})

@app.route("/skriv/<projekt_id>", methods=["POST"])
def skriv_route(projekt_id):
    data = request.get_json()
    uppgift = data.get("uppgift", "").strip()
    full_kontext = data.get("full_kontext", False)

    if not uppgift:
        return jsonify({"fel": "Ingen uppgift angiven"}), 400

    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")
    projekt = ladda_projekt(service, projekt_id, titel)
    llm_installningar = config.get("llm_per_agent", {})

    resultat = {"status": "kor", "utkast": None, "godkant": None}
    def kor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            try:
                rensa_tillstand(service, projekt.get("system_mapp_id"))
            except Exception as e:
                print(f"Kunde inte rensa tillstånd: {e}")

            loop.run_until_complete(
                kor_skriv_flode(
                    service, projekt, llm_installningar,
                    uppgift, full_kontext=full_kontext,
                )
            )
            _flodes_status[projekt_id] = {"status": "klar"}
        except FlodesPausad as e:
            _flodes_status[projekt_id] = {
                "status": "pausad",
                "fel": str(e),
            }
        except Exception as e:
            print(f"Fel i skriv-flödet: {e}")
            _flodes_status[projekt_id] = {"status": "fel", "fel": str(e)}
        finally:
            loop.close()

    rensa_avbryt(projekt_id)
    _flodes_status[projekt_id] = {"status": "kor"}
    if not starta_trad(projekt_id, kor):
        return jsonify({"status": "upptagen"}), 409
    return jsonify({"status": "startad"})


@app.route("/analysera/utkast/<projekt_id>")
def hamta_utkastpar_route(projekt_id):
    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")
    projekt = ladda_projekt(service, projekt_id, titel)
    utkast_mapp_id = projekt["mappar"].get("utkast")
    if not utkast_mapp_id:
        return jsonify([])
    par = hamta_utkastpar(service, utkast_mapp_id)
    return jsonify(par)


@app.route("/analysera/<projekt_id>", methods=["POST"])
def analysera_route(projekt_id):
    data = request.get_json()
    kapitel_namn = data.get("kapitel_namn", "").strip()
    ignorera_flaggor = data.get("ignorera_flaggor", False)

    if not kapitel_namn:
        return jsonify({"fel": "Inget kapitel angivet"}), 400

    service = get_service()
    config = lас_config()
    senaste = config.get("senaste_projekt", {})
    titel = senaste.get("titel", "Okänt projekt")
    projekt = ladda_projekt(service, projekt_id, titel)
    llm_installningar = config.get("llm_per_agent", {})

    _flodes_status[projekt_id] = {"status": "kor"}

    def kor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                kor_analysera_flode(
                    service, projekt, llm_installningar,
                    kapitel_namn,
                    ignorera_flaggor=ignorera_flaggor,
                )
            )
            if res:
                _flodes_status[projekt_id] = res
            else:
                _flodes_status[projekt_id] = {"status": "fel"}
        except Exception as e:
            print(f"Fel i analysera-flödet: {e}")
            _flodes_status[projekt_id] = {"status": "fel", "fel": str(e)}
        finally:
            loop.close()

    rensa_avbryt(projekt_id)
    if not starta_trad(projekt_id, kor):
        return jsonify({"status": "upptagen"}), 409
    return jsonify({"status": "startad"})

_flodes_status = {}

@app.route("/status/<projekt_id>")
def hamta_status(projekt_id):
    return jsonify(_flodes_status.get(projekt_id, {"status": "okand"}))

@app.route("/knappstatus/<projekt_id>")
def knapp_status(projekt_id):
    status = _flodes_status.get(projekt_id, {}).get("status", "okand")
    
    # Vid aktiva statusar – returnera direkt utan Drive-anrop
    if status in ("kor", "avbryter"):
        return jsonify({
            "status": status,
            "har_sparat_tillstand": False,
        })
    
    # Bara kolla Drive om vi behöver veta om återuppta är möjligt
    har_sparat = False
    try:
        service = get_service()
        config = lас_config()
        senaste = config.get("senaste_projekt", {})
        titel = senaste.get("titel", "Okänt projekt")
        projekt = ladda_projekt(service, projekt_id, titel)
        tillstand = ladda_tillstand(service, projekt.get("system_mapp_id"))
        har_sparat = bool(tillstand and tillstand.get("flode"))
    except Exception as e:
        print(f"Knappstatus: kunde inte kolla Drive: {e}")
    
    return jsonify({
        "status": status,
        "har_sparat_tillstand": har_sparat,
    })

@app.route("/rensa-tillstand/<projekt_id>", methods=["POST"])
def rensa_tillstand_route(projekt_id):
    _flodes_status[projekt_id] = {"status": "okand"}
    
    def rensa():
        try:
            service = get_service()
            config = lас_config()
            senaste = config.get("senaste_projekt", {})
            titel = senaste.get("titel", "Okänt projekt")
            projekt = ladda_projekt(service, projekt_id, titel)
            rensa_tillstand(service, projekt.get("system_mapp_id"))
            print("Tillstånd rensat på Drive.")
        except Exception as e:
            print(f"Kunde inte rensa tillstånd: {e}")
    
    threading.Thread(target=rensa, daemon=True).start()
    return jsonify({"ok": True})

if __name__ == "__main__":
    # app.run(debug=True, port=5000)
    # app.run(debug=True, use_reloader=False)
    app.run(debug=False, port=5000)