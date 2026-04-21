import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

CHATGPT_URL = "https://chatgpt.com"
SESSION_FILE = "chatgpt_session.json"
COOKIES_FILE = "chatgpt_cookies.json"

TOKEN_MEDDELANDEN = [
    "you've reached your limit",
    "too many messages",
    "try again in",
    "rate limit",
]


def _hitta_token_tidpunkt(text):
    text = text.lower()
    monster = [
        r"try again in (\d+) hour",
        r"try again in (\d+) minute",
        r"resets in (\d+) hour",
        r"resets in (\d+) minute",
    ]
    for m in monster:
        match = re.search(m, text)
        if match:
            antal = int(match.group(1))
            if "hour" in m:
                return datetime.now() + timedelta(hours=antal)
            else:
                return datetime.now() + timedelta(minutes=antal)
    return datetime.now() + timedelta(hours=2)


class ChatGPTAdapter:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.sida = None
        self.redo = False
        self.token_slut = False
        self.token_aterställs = None

    async def _er_inloggad(self):
        try:
            await asyncio.sleep(3)
            sidtext = await self.sida.inner_text("body")
            sidtext_lower = sidtext.lower()
            return not (
                "log in" in sidtext_lower
                or "sign in" in sidtext_lower
                or "logga in" in sidtext_lower
            )
        except Exception:
            return False

    async def _vanta_pa_inloggning(self, timeout=300):
        print("ChatGPT: Väntar på inloggning (upp till 5 min)...")
        try:
            await self.sida.wait_for_url(
                "https://chatgpt.com/",
                timeout=timeout * 1000,
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(5)
        except Exception:
            print("ChatGPT: Timeout — inloggning tog för lång tid.")

    async def _spara_session(self):
        await self.context.storage_state(path=SESSION_FILE)

    async def _ladda_cookies(self):
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            
            samma_site_karta = {
                "no_restriction": "None",
                "unspecified": "None",
                "lax": "Lax",
                "strict": "Strict",
                "none": "None",
            }
            
            rensade = []
            for c in cookies:
                cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False),
                }
                same_site = c.get("sameSite", "None")
                if same_site:
                    cookie["sameSite"] = samma_site_karta.get(
                        same_site.lower(), "None"
                    )
                if c.get("expirationDate"):
                    cookie["expires"] = int(c["expirationDate"])
                rensade.append(cookie)
            
            await self.context.add_cookies(rensade)
            print("ChatGPT: Cookies laddade.")
            return True
        return False

    async def _hitta_inmatning(self):
        await asyncio.sleep(5)
        selectors = [
            "#prompt-textarea",
            'div[contenteditable="true"]',
            "textarea",
            'div[role="textbox"]',
        ]
        for selector in selectors:
            try:
                element = self.sida.locator(selector).first
                if await element.is_visible(timeout=2000):
                    print(f"ChatGPT: Inmatning hittad: {selector}")
                    return element
            except Exception:
                continue
        print("ChatGPT: Kunde inte hitta inmatningsfältet!")
        return None

    async def _kontrollera_klart(self):
        try:
            antal = await self.sida.locator(
                'button[aria-label="Stop streaming"],'
                'button[data-testid="stop-button"]'
            ).count()
            return antal == 0
        except Exception:
            return True

    async def _kontrollera_token_fel(self):
        try:
            sidtext = await self.sida.inner_text("body")
            for meddelande in TOKEN_MEDDELANDEN:
                if meddelande in sidtext.lower():
                    self.token_aterställs = _hitta_token_tidpunkt(sidtext)
                    print(
                        f"ChatGPT: Token-gräns nådd. "
                        f"Försöker igen: {self.token_aterställs}"
                    )
                    return True
        except Exception:
            pass
        return False

    async def _hamta_senaste_svar(self):
        try:
            alla_svar = await self.sida.locator(
                '[data-message-author-role="assistant"]'
            ).all()
            if alla_svar:
                return await alla_svar[-1].inner_text()
        except Exception:
            pass
        return ""

    async def starta(self, visa_webblasare=True):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=not visa_webblasare,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        try:
            self.context = await self.browser.new_context(
                storage_state=SESSION_FILE,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            print("ChatGPT: Sparad session hittad.")
        except Exception:
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            print("ChatGPT: Ingen sparad session.")

        self.sida = await self.context.new_page()
        await Stealth().apply_stealth_async(self.sida)

        cookies_laddade = await self._ladda_cookies()
        if cookies_laddade:
            await self.sida.goto(CHATGPT_URL)
            await self.sida.wait_for_load_state(
                "domcontentloaded", timeout=30000
            )
            await asyncio.sleep(3)
            if await self._er_inloggad():
                print("ChatGPT: Inloggad via cookies.")
                await self._spara_session()
                self.redo = True
                print("ChatGPT: Redo.")
                return

        await self.sida.goto(CHATGPT_URL)
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if not await self._er_inloggad():
            print("ChatGPT: Logga in i webbläsarfönstret. Väntar...")
            await self._vanta_pa_inloggning()
            print("ChatGPT: Inloggning klar!")

        await self._spara_session()
        self.redo = True
        print("ChatGPT: Redo.")

    async def ny_konversation(self):
        await self.sida.goto(CHATGPT_URL)
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

    async def skicka_meddelande(self, text, timeout=120):
        inmatning = await self._hitta_inmatning()
        if not inmatning:
            return None

        await inmatning.click()
        await asyncio.sleep(0.5)
        await inmatning.type(text, delay=10)
        await self.sida.keyboard.press("Enter")
        await asyncio.sleep(3)

        for _ in range(timeout):
            await asyncio.sleep(1)
            if await self._kontrollera_klart():
                break
            if await self._kontrollera_token_fel():
                self.token_slut = True
                return None

        return await self._hamta_senaste_svar()

    async def ladda_upp_kontext(self, text, etikett="Bokkontext"):
        meddelande = (
            f"Jag laddar upp följande dokument som kontext "
            f"för vårt samarbete. Bekräfta mottagandet med bara "
            f"'Kontext mottagen: {etikett}'.\n\n"
            f"---\n{text}\n---"
        )
        return await self.skicka_meddelande(meddelande)

    async def stang(self):
        await self._spara_session()
        await self.browser.close()
        await self.playwright.stop()
        self.redo = False
        print("ChatGPT: Stängd.")