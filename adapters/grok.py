import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

GROK_URL = "https://grok.com"
SESSION_FILE = "grok_session.json"
COOKIES_FILE = "grok_cookies.json"

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


class GrokAdapter:
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
                "sign in" in sidtext_lower
                or "log in" in sidtext_lower
                or "create account" in sidtext_lower
            )
        except Exception:
            return False

    async def _vanta_pa_inloggning(self, timeout=300):
        print("Grok: Väntar på inloggning (upp till 5 min)...")
        try:
            await self.sida.wait_for_function(
                """() => {
                    const text = document.body.innerText.toLowerCase();
                    return !text.includes('sign in')
                        && !text.includes('log in')
                        && !text.includes('create account');
                }""",
                timeout=timeout * 1000,
            )
            await asyncio.sleep(5)
        except Exception:
            print("Grok: Timeout — inloggning tog för lång tid.")

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
            print("Grok: Cookies laddade.")
            return True
        return False

    async def _hitta_inmatning(self):
        await asyncio.sleep(5)
        selectors = [
            "textarea",
            'div[contenteditable="true"]',
            'div[role="textbox"]',
            "[placeholder]",
        ]
        for selector in selectors:
            try:
                element = self.sida.locator(selector).first
                if await element.is_visible(timeout=2000):
                    print(f"Grok: Inmatning hittad: {selector}")
                    return element
            except Exception:
                continue
        print("Grok: Kunde inte hitta inmatningsfältet!")
        return None

    async def _kontrollera_klart(self):
        try:
            antal = await self.sida.locator(
                'button[aria-label="Stop"],'
                '[data-testid="stop-button"]'
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
                        f"Grok: Token-gräns nådd. "
                        f"Försöker igen: {self.token_aterställs}"
                    )
                    return True
        except Exception:
            pass
        return False

    # async def _hamta_senaste_svar(self):
    #     try:
    #         alla_svar = await self.sida.locator(
    #             ".message-bubble, "
    #             "[data-testid='message'], "
    #             ".response-content"
    #         ).all()
    #         if alla_svar:
    #             text = await alla_svar[-1].inner_text()
    #             rader = text.split("\n")
    #             filtrerade = [
    #                 rad for rad in rader
    #                 if not rad.strip().lower().startswith("thought for")
    #             ]
    #             return "\n".join(filtrerade).strip()
    #     except Exception:
    #         pass
    #     return ""

    async def _hamta_senaste_svar(self):
        try:
            alla_svar = await self.sida.locator(
                ".message-bubble, "
                "[data-testid='message'], "
                ".response-content"
            ).all()
            if alla_svar:
                text = await alla_svar[-1].inner_text()
                print(f"Grok debug: hämtade {len(text)} tecken")
                return text
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
            print("Grok: Sparad session hittad.")
        except Exception:
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            print("Grok: Ingen sparad session.")

        self.sida = await self.context.new_page()
        await Stealth().apply_stealth_async(self.sida)

        cookies_laddade = await self._ladda_cookies()
        if cookies_laddade:
            await self.sida.goto(GROK_URL)
            await self.sida.wait_for_load_state(
                "domcontentloaded", timeout=30000
            )
            await asyncio.sleep(3)
            if await self._er_inloggad():
                print("Grok: Inloggad via cookies.")
                await self._spara_session()
                self.redo = True
                print("Grok: Redo.")
                return

        await self.sida.goto(GROK_URL)
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if not await self._er_inloggad():
            print("Grok: Logga in i webbläsarfönstret. Väntar...")
            await self._vanta_pa_inloggning()
            print("Grok: Inloggning klar!")

        await self._spara_session()
        self.redo = True
        print("Grok: Redo.")

    async def ny_konversation(self):
        await self.sida.goto(GROK_URL)
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

    async def skicka_meddelande(self, text, timeout=120):
        inmatning = await self._hitta_inmatning()
        if not inmatning:
            return None

        antal_innan = await self._rakna_svar()

        await inmatning.click()
        await asyncio.sleep(0.5)
        await inmatning.fill(text)
        await asyncio.sleep(0.5)
        await self.sida.keyboard.press("Enter")
        await asyncio.sleep(5)

        for i in range(timeout):
            await asyncio.sleep(1)
            if await self._kontrollera_klart() and i > 3:
                antal_efter = await self._rakna_svar()
                if antal_efter > antal_innan:
                    await asyncio.sleep(30)
                    break
            if await self._kontrollera_token_fel():
                self.token_slut = True
                return None

        antal_efter = await self._rakna_svar()
        if antal_efter <= antal_innan:
            print("Grok: Inget nytt svar hittades.")
            return None

        return await self._hamta_senaste_svar()

    async def _rakna_svar(self):
        """Räknar antalet svar-element på sidan."""
        try:
            selectors = [
                ".message-bubble",
                "[data-testid='message']",
                ".response-content",
                "[class*='response']",
                "[class*='message']",
            ]
            for selector in selectors:
                antal = await self.sida.locator(selector).count()
                if antal > 0:
                    return antal
        except Exception:
            pass
        return 0

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
        print("Grok: Stängd.")

    async def bifoga_fil(self, innehall, filnamn):
        """
        Försöker ladda upp fil till Grok.
        Returnerar True om det lyckades, False annars.
        """
        import tempfile
        import os

        tmpfil = os.path.join(
            tempfile.gettempdir(), filnamn
        )
        with open(tmpfil, "w", encoding="utf-8") as f:
            f.write(innehall)

        try:
            fil_input = self.sida.locator("input[type='file']").first
            if await fil_input.count() == 0:
                print("Grok: Ingen file input hittad.")
                return False
            await fil_input.set_input_files(tmpfil)
            await asyncio.sleep(2)
            print(f"Grok: Bifogade fil '{filnamn}'")
            return True
        except Exception as e:
            print(f"Grok: Filuppladdning misslyckades: {e}")
            return False
        finally:
            if os.path.exists(tmpfil):
                os.remove(tmpfil)

    async def bifoga_filer(self, dokument):
        """
        Bifoga flera dokument. Returnerar de som misslyckades
        som en sammanslagen sträng för fallback-inklistring.
        """
        misslyckade = {}
        for filnamn, innehall in dokument.items():
            if innehall and innehall.strip():
                ok = await self.bifoga_fil(innehall, f"{filnamn}.txt")
                if not ok:
                    misslyckade[filnamn] = innehall
                await asyncio.sleep(1)
        return misslyckade
    
    async def _vanta_tills_text_stabil(self, selector, max_vantan=180):
        """
        Väntar tills texten i ett element slutar växa.
        Returnerar den slutliga texten.
        """
        forra_langd = 0
        stabil_raknar = 0
        
        for _ in range(max_vantan):
            await asyncio.sleep(3)
            try:
                element = self.sida.locator(selector).last
                text = await element.inner_text()
                nu_langd = len(text)
                
                if nu_langd == forra_langd and nu_langd > 0:
                    stabil_raknar += 1
                    if stabil_raknar >= 3:
                        print(f"Grok: Text stabil vid {nu_langd} tecken.")
                        return text
                else:
                    stabil_raknar = 0
                    forra_langd = nu_langd
            except Exception:
                pass
        
        return None


    async def _hamta_senaste_svar(self):
        selectors = [
            ".message-bubble",
            "[data-testid='message']",
            ".response-content",
            "[class*='response']",
            "[class*='assistant']",
        ]
        
        for selector in selectors:
            try:
                antal = await self.sida.locator(selector).count()
                if antal > 0:
                    text = await self._vanta_tills_text_stabil(selector)
                    if text:
                        rader = text.split("\n")
                        filtrerade = [
                            rad for rad in rader
                            if not rad.strip().lower().startswith("thought for")
                        ]
                        return "\n".join(filtrerade).strip()
            except Exception:
                pass
        return ""