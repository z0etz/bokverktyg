import io
import os

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

MALLAR = {
    "bok.md": (
        "# {titel}\n\n"
        "*Lägg in godkänd text här. "
        "Märk varje kapitel med ~ nummer ~ följt av platsnamn på nästa rad.*\n\n"
        "~ 1 ~\n"
        "Plats\n\n"
        "*Text börjar här.*\n"
    ),
    "storyline.md": (
        "# Storyline — {titel}\n\n"
        "## Genre\n\n\n"
        "## Huvudtema\n\n\n"
        "## Berättarperspektiv\n\n\n"
        "## Karaktärer (kort)\n\n\n"
        "## Kapitelskiss\n\n"
        "Fyll i ett kapitel per block. Kopiera blocket för fler kapitel.\n\n"
        "### Kapitel 1\n"
        "- **Perspektiv:** \n"
        "- **Vad händer:** \n"
        "- **Syfte i berättelsen:** \n\n"
        "### Kapitel 2\n"
        "- **Perspektiv:** \n"
        "- **Vad händer:** \n"
        "- **Syfte i berättelsen:** \n\n"
        "## Övrigt\n\n"
    ),
    "stilguide.md": (
        "# Stilguide — {titel}\n\n"
        "*Skapas av Stilanalytikern. Redigera inte manuellt.*\n\n"
        "## Berättarröst\n\n"
        "## Meningsbyggnad\n\n"
        "## Ordval och register\n\n"
        "## Dialog\n\n"
        "## Rytm och tempo\n\n"
        "## Undvik\n\n"
        "## Exempelmeningar\n\n"
    ),
    "karaktarer.md": (
        "# Karaktärer — {titel}\n\n"
        "*Skapas av Karaktärskartläggaren. Redigera inte manuellt.*\n\n"
        "## Karaktärer\n\n"
        "## Relationsmatris\n\n"
        "## Öppna trådar per karaktär\n\n"
    ),
    "kontext.md": (
        "# Kontext — {titel}\n\n"
        "*Skapas av Karaktärskartläggaren. Uppdateras efter varje godkänt kapitel.*\n\n"
        "## Aktiva foreshadowing-trådar\n\n"
        "## Karaktärsstatus\n\n"
        "## Senaste händelser per perspektiv\n\n"
    ),
    "dramaturgi.md": (
        "# Dramaturgi — {titel}\n\n"
        "*Skapas av Dramaturgikonsulten. Redigera inte manuellt.*\n\n"
        "## Berättelsebåge\n\n"
        "## Foreshadowing-register\n\n"
        "## Spänningskurva\n\n"
        "## Tematiska linjer\n\n"
        "## Rekommendationer\n\n"
    ),
    "dramaturgi_observationer.md": (
        "# Dramaturgiska observationer — {titel}\n\n"
        "*Dramaturgikonsultens noteringar om avvikelser från storyline "
        "och olösta trådar.*\n\n"
        "## Avvikelser från storyline\n\n"
        "## Olösta trådar\n\n"
        "## Övrigt\n\n"
    ),
    "smakprofil.md": (
        "# Smakprofil — {titel}\n\n"
        "*Skapas av Smaktränaren. Växer med varje Analysera-session.*\n\n"
        "## Stilpreferenser\n\n"
        "## Karaktärspreferenser\n\n"
        "## Dramaturgiska preferenser\n\n"
    ),
}

UNDERMAPPAR = ["utkast", "exempeltexter", "agentlogg", "system"]


def get_drive_service():
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


def get_or_create_folder(service, name, parent_id=None):
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


def read_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")


def write_file(service, file_id, content):
    buffer = io.BytesIO(content.encode("utf-8"))
    media = MediaIoBaseUpload(buffer, mimetype="text/plain", resumable=False)
    service.files().update(
        fileId=file_id, media_body=media
    ).execute()


def create_file(service, name, content, parent_id):
    file_metadata = {"name": name, "parents": [parent_id]}
    buffer = io.BytesIO(content.encode("utf-8"))
    media = MediaIoBaseUpload(buffer, mimetype="text/plain", resumable=False)
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    return file["id"]


def list_files(service, folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query, fields="files(id, name)"
    ).execute()
    return results.get("files", [])


def get_file_id(service, name, folder_id):
    query = (
        f"name='{name}' and '{folder_id}' in parents"
        f" and trashed=false"
    )
    results = service.files().list(
        q=query, fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def skapa_projekt(service, titel, parent_folder_id=None):
    """Skapar hela projektmappstrukturen på Drive med tomma mallfiler."""
    print(f"Skapar projekt: {titel}")

    rot = get_or_create_folder(service, titel, parent_folder_id)
    print(f"  Rotmapp skapad: {titel}/")

    fil_ids = {}
    for filnamn, mall in MALLAR.items():
        innehall = mall.replace("{titel}", titel)
        fil_id = create_file(service, filnamn, innehall, rot)
        fil_ids[filnamn] = fil_id
        print(f"  Skapade: {filnamn}")

    mapp_ids = {}
    for mapp in UNDERMAPPAR:
        mapp_id = get_or_create_folder(service, mapp, rot)
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