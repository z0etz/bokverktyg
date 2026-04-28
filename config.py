import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "senaste_projekt": None,
    "aktuellt_projekt_id": None,
    "llm_per_agent": {
        "stilanalytikern": "claude",
        "karaktarskartlaggaren": "claude",
        "dramaturgikonsulten": "claude",
        "skrivaren": "claude",
        "bokredaktoren": "claude",
        "forlаgsredaktoren": "claude",
        "smaktranaren": "claude",
        "testlasaren": "claude",
    },
    "max_redaktor_varv": 3,
    "sprak": "sv",
}

TILLGANGLIGA_LLMS = ["claude", "chatgpt", "grok"]


def lас_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            sparad = json.load(f)
        config = DEFAULT_CONFIG.copy()
        config.update(sparad)
        return config
    return DEFAULT_CONFIG.copy()


def spara_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def uppdatera_senaste_projekt(projekt_id, projekt_titel):
    config = lас_config()
    config["senaste_projekt"] = {
        "id": projekt_id,
        "titel": projekt_titel,
    }
    spara_config(config)


def uppdatera_llm(agent, llm):
    config = lас_config()
    config["llm_per_agent"][agent] = llm
    spara_config(config)


def hamta_llm(agent):
    config = lас_config()
    return config["llm_per_agent"].get(agent, "claude")

def projekt_byttes(nytt_projekt_id):
    """
    Kollar om projektet byttes sedan senaste körningen.
    Uppdaterar aktuellt projekt och returnerar True om det byttes.
    """
    config = lас_config()
    gammalt_id = config.get("aktuellt_projekt_id")
    if gammalt_id != nytt_projekt_id:
        config["aktuellt_projekt_id"] = nytt_projekt_id
        spara_config(config)
        return True
    return False