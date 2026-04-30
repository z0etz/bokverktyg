import io
import os

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

MALLAR = {
    "bok": (
        "# {titel}\n\n"
        "Lägg in godkänd text här. "
        "Märk varje kapitel med ~ nummer ~ följt av platsnamn på nästa rad.\n\n"
        "~ 1 ~\n"
        "Plats\n\n"
        "Text börjar här.\n"
    ),
    "storyline": (
        "# Storyline — {titel}\n\n"
        "## Genre\n\n\n"
        "## Huvudtema\n\n\n"
        "## Berättarperspektiv\n\n\n"
        "## Karaktärer (kort)\n\n\n"
        "## Kapitelskiss\n\n"
        "Fyll i ett kapitel per block. Kopiera blocket för fler kapitel.\n\n"
        "### Kapitel 1\n"
        "- Perspektiv: \n"
        "- Vad händer: \n"
        "- Syfte i berättelsen: \n\n"
        "### Kapitel 2\n"
        "- Perspektiv: \n"
        "- Vad händer: \n"
        "- Syfte i berättelsen: \n\n"
        "## Övrigt\n\n"
    ),
    "stilguide": (
        "# Stilguide — {titel}\n\n"
        "Skapas av Stilanalytikern. Redigera inte manuellt.\n\n"
        "## Berättarröst\n\n"
        "## Meningsbyggnad\n\n"
        "## Ordval och register\n\n"
        "## Dialog\n\n"
        "## Rytm och tempo\n\n"
        "## Undvik\n\n"
        "## Exempelmeningar\n\n"
    ),
    "karaktarer": (
        "# Karaktärer — {titel}\n\n"
        "Skapas av Karaktärskartläggaren. Redigera inte manuellt.\n\n"
        "## Karaktärer\n\n"
        "## Relationsmatris\n\n"
        "## Öppna trådar per karaktär\n\n"
    ),
    "kontext": (
        "# Kontext — {titel}\n\n"
        "Skapas av Karaktärskartläggaren. "
        "Uppdateras efter varje godkänt kapitel.\n\n"
        "## Aktiva foreshadowing-trådar\n\n"
        "## Karaktärsstatus\n\n"
        "## Senaste händelser per perspektiv\n\n"
    ),
    "dramaturgi": (
        "# Dramaturgi — {titel}\n\n"
        "Skapas av Dramaturgikonsulten. Redigera inte manuellt.\n\n"
        "## Berättelsebåge\n\n"
        "## Foreshadowing-register\n\n"
        "## Spänningskurva\n\n"
        "## Tematiska linjer\n\n"
        "## Rekommendationer\n\n"
    ),
    "dramaturgi_observationer": (
        "# Dramaturgiska observationer — {titel}\n\n"
        "Dramaturgikonsultens noteringar om avvikelser från storyline "
        "och olösta trådar.\n\n"
        "## Avvikelser från storyline\n\n"
        "## Olösta trådar\n\n"
        "## Övrigt\n\n"
    ),
    "smakprofil": (
        "# Smakprofil — {titel}\n\n"
        "Skapas av Smaktränaren. Växer med varje Analysera-session.\n\n"
        "## Stilpreferenser\n\n"
        "## Karaktärspreferenser\n\n"
        "## Dramaturgiska preferenser\n\n"
    ),
}

UNDERMAPPAR = ["utkast", "exempeltexter", "agentlogg", "system"]


def _hamta_credentials():
    """Hämtar och uppdaterar sparade credentials."""
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def hamta_drive_tjanst():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def hamta_docs_tjanst():
    """Returnerar en Google Docs API-tjänst."""
    return build("docs", "v1", credentials=_hamta_credentials())


def hamta_eller_skapa_mapp(service, name, parent_id=None):
    query = (
        f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
        f" and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(
        q=query, fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(
        body=metadata, fields="id"
    ).execute()
    return folder["id"]


def skapa_google_doc(service, name, content, parent_id):
    """Skapar ett Google Docs-dokument med textinnehåll."""
    fil_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [parent_id],
    }
    fil = service.files().create(
        body=fil_metadata, fields="id"
    ).execute()
    fil_id = fil["id"]
    if content and content.strip():
        uppdatera_google_doc(service, fil_id, content)
    return fil_id


def uppdatera_google_doc(service, fil_id, content):
    """Skriver över innehållet i ett Google Docs-dokument."""
    docs = hamta_docs_tjanst()
    dokument = docs.documents().get(documentId=fil_id).execute()
    slut_index = dokument["body"]["content"][-1]["endIndex"] - 1

    requests = []
    if slut_index > 1:
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": slut_index,
                }
            }
        })
    requests.append({
        "insertText": {
            "location": {"index": 1},
            "text": content,
        }
    })
    docs.documents().batchUpdate(
        documentId=fil_id,
        body={"requests": requests},
    ).execute()

def las_google_doc(service, fil_id):
    def _las():
        docs = hamta_docs_tjanst()
        dokument = docs.documents().get(documentId=fil_id).execute()
        text = ""
        for element in dokument["body"]["content"]:
            if "paragraph" in element:
                for para_element in element["paragraph"]["elements"]:
                    if "textRun" in para_element:
                        text += para_element["textRun"]["content"]
        return text
    return med_retry(_las)


def hamta_fil_id(service, name, folder_id):
    def _hamta():
        query = (
            f"name='{name}' and '{folder_id}' in parents"
            f" and trashed=false"
        )
        results = service.files().list(
            q=query, fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None
    return med_retry(_hamta)

def lista_filer(service, folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query, fields="files(id, name)"
    ).execute()
    return results.get("files", [])

def skapa_projekt(service, titel, parent_folder_id=None):
    """Skapar hela projektmappstrukturen på Drive med Google Docs-filer."""
    print(f"Skapar projekt: {titel}")

    rot = hamta_eller_skapa_mapp(service, titel, parent_folder_id)
    print(f"  Rotmapp skapad: {titel}/")

    fil_ids = {}
    for filnamn, mall in MALLAR.items():
        innehall = mall.replace("{titel}", titel)
        fil_id = skapa_google_doc(service, filnamn, innehall, rot)
        fil_ids[filnamn] = fil_id
        print(f"  Skapade: {filnamn}")

    mapp_ids = {}
    for mapp in UNDERMAPPAR:
        mapp_id = hamta_eller_skapa_mapp(service, mapp, rot)
        mapp_ids[mapp] = mapp_id
        print(f"  Skapade mapp: {mapp}/")

    projekt = {
        "titel": titel,
        "rot_id": rot,
        "filer": fil_ids,
        "mappar": mapp_ids,
    }

    print(f"\nProjekt '{titel}' skapat!")
    return projekt

def med_retry(funktion, max_forsok=5, vantan=2):
    """
    Kör en funktion och försöker igen vid nätverksfel.
    """
    import time
    for forsok in range(max_forsok):
        try:
            return funktion()
        except Exception as e:
            if forsok < max_forsok - 1:
                print(f"Drive: Försök {forsok + 1} misslyckades ({e}), försöker igen...")
                time.sleep(vantan)
            else:
                raise