import asyncio
import re
from datetime import datetime, timedelta

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

CLAUDE_URL = "https://claude.ai"
SESSION_FILE = "claude_session.json"

TOKEN_MEDDELANDEN = [
    "you've reached your limit",
    "du har nått din gräns",
    "rate limit",
    "too many messages",
    "try again in",
    "försök igen om",
]


def _hitta_token_tidpunkt(text):
    text = text.lower()
    monster = [
        r"try again in (\d+) hour",
        r"try again in (\d+) minute",
        r"försök igen om (\d+) timm",
        r"försök igen om (\d+) minut",
        r"resets in (\d+) hour",
        r"resets in (\d+) minute",
    ]
    for m in monster:
        match = re.search(m, text)
        if match:
            antal = int(match.group(1))
            if "hour" in m or "timm" in m:
                return datetime.now() + timedelta(hours=antal)
            else:
                return datetime.now() + timedelta(minutes=antal)
    return datetime.now() + timedelta(hours=2)

def _rensa_svar(text):
    """Tar bort dubblerat prefix som Claude-gränssnittet lägger till."""
    if not text:
        return ""
    rader = text.split("\n")
    if len(rader) >= 2 and rader[0].strip() == rader[1].strip():
        return "\n".join(rader[1:]).strip()
    if rader[0].startswith("Claude responded:"):
        return "\n".join(rader[1:]).strip()
    return text.strip()

class ClaudeAdapter:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.sida = None
        self.redo = False
        self.token_slut = False
        self.token_aterställs = None

    async def _behover_logga_in(self):
        try:
            url = self.sida.url
            return (
                "login" in url
                or "authenticate" in url
                or url == "https://claude.ai/"
                and "claude_session" not in str(
                    await self.context.cookies()
                )
            )
        except Exception:
            return False

    async def _vanta_pa_inloggning(self, timeout=300):
        print("Claude: Väntar på inloggning (upp till 5 min)...")
        try:
            await self.sida.wait_for_url(
                "**/new**",
                timeout=timeout * 1000,
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(5)
        except Exception:
            print("Claude: Timeout — inloggning tog för lång tid.")

    async def _spara_session(self):
        await self.context.storage_state(path=SESSION_FILE)

    async def _hitta_inmatning(self):
        await asyncio.sleep(5)
        selectors = [
            'div[contenteditable="true"]',
            'div[contenteditable="true"][data-placeholder]',
            ".ProseMirror",
            'div[role="textbox"]',
            "textarea",
            'p[data-placeholder]',
            '[contenteditable]',
        ]
        for selector in selectors:
            try:
                element = self.sida.locator(selector).first
                if await element.is_visible(timeout=2000):
                    print(f"Claude: Inmatning hittad: {selector}")
                    return element
            except Exception:
                continue
        print("Claude: Kunde inte hitta inmatningsfältet!")
        return None

    # async def _kontrollera_klart(self):
    #     try:
    #         antal = await self.sida.locator(
    #             'button[aria-label="Stop"]'
    #         ).count()
    #         return antal == 0
    #     except Exception:
    #         return True

    async def _kontrollera_klart(self):
        try:
            antal = await self.sida.locator(
                'button[aria-label="Give positive feedback"],'
                'button[aria-label="Give negative feedback"]'
            ).count()
            return antal > 0
        except Exception:
            return False

    async def _kontrollera_token_fel(self):
        try:
            sidtext = await self.sida.inner_text("body")
            for meddelande in TOKEN_MEDDELANDEN:
                if meddelande in sidtext.lower():
                    self.token_aterställs = _hitta_token_tidpunkt(sidtext)
                    print(
                        f"Claude: Token-gräns nådd. "
                        f"Försöker igen: {self.token_aterställs}"
                    )
                    return True
        except Exception:
            pass
        return False

    async def _hamta_senaste_svar(self):
        try:
            alla_svar = await self.sida.locator(
                ".font-claude-message"
            ).all()
            if alla_svar:
                text = await alla_svar[-1].inner_text()
                return _rensa_svar(text)
        except Exception:
            pass
        try:
            alla_svar = await self.sida.locator(
                '[data-is-streaming="false"]'
            ).all()
            if alla_svar:
                text = await alla_svar[-1].inner_text()
                return _rensa_svar(text)
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
            print("Claude: Sparad session hittad.")
        except Exception:
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            print("Claude: Ingen sparad session.")

        self.sida = await self.context.new_page()
        await Stealth().apply_stealth_async(self.sida)
        await self.sida.goto(CLAUDE_URL)
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if await self._behover_logga_in():
            print("Claude: Logga in i webbläsarfönstret. Väntar...")
            await self._vanta_pa_inloggning()
            print("Claude: Inloggning klar!")

        await self._spara_session()
        self.redo = True
        print("Claude: Redo.")

    async def ny_konversation(self):
        await self.sida.goto(CLAUDE_URL + "/new")
        await self.sida.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(8)

    async def skicka_meddelande(self, text, timeout=120):
        inmatning = await self._hitta_inmatning()
        if not inmatning:
            print("Claude: Kunde inte hitta inmatningsfältet.")
            return None

        await inmatning.click()
        await asyncio.sleep(0.5)
        await inmatning.fill(text)
        await asyncio.sleep(1)

        skicka_knapp = self.sida.locator('button[aria-label="Send message"]')
        try:
            await skicka_knapp.click(timeout=5000)
        except Exception:
            print("Claude: Kunde inte klicka på skicka-knappen.")
            return None

        await asyncio.sleep(5)

        for i in range(timeout):
            await asyncio.sleep(1)
            klart = await self._kontrollera_klart()
            if i % 10 == 0:
                print(f"Claude: Väntar... ({i}s) klart={klart}")
            if klart and i > 3:
                print(f"Claude: Klar efter {i}s")
                break
            if await self._kontrollera_token_fel():
                self.token_slut = True
                print("Claude: Token-gräns nådd.")
                return None
            if i > 0 and i % 30 == 0:
                sidtext = await self.sida.inner_text("body")
                print(f"Claude debug sidtext (första 300 tecken): {sidtext[:300]}") #Debug
                for felord in ["something went wrong", "error", 
                            "try again", "försök igen",
                            "overloaded", "hög belastning"]:
                    if felord in sidtext.lower():
                        print(f"Claude: Fel detekterat efter {i}s: '{felord}'")
                        self.senaste_fel = felord
                        return None
        else:
            print(f"Claude: Timeout efter {timeout}s -- inget svar.")
            self.senaste_fel = "timeout"
            return None

        svar = await self._hamta_senaste_svar()
        print(f"Claude: Svar längd={len(svar) if svar else 0}")
        return svar

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
        print("Claude: Stängd.")

    async def bifoga_fil(self, innehall, filnamn):
        """
        Skapar en temporär fil och laddar upp den till Claude.
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
            await fil_input.set_input_files(tmpfil)
            await asyncio.sleep(2)
            print(f"Claude: Bifogade fil '{filnamn}'")
        finally:
            os.remove(tmpfil)

    async def bifoga_filer(self, dokument):
        """
        Bifoga flera dokument som separata filer.
        dokument: dict med {filnamn: innehall}
        """
        for filnamn, innehall in dokument.items():
            if innehall and innehall.strip():
                await self.bifoga_fil(innehall, f"{filnamn}.txt")
                await asyncio.sleep(1)