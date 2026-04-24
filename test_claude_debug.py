import asyncio
from adapters.claude import ClaudeAdapter
from adapters.grok import GrokAdapter

# async def testa_claude():
#      adapter = ClaudeAdapter()
#      await adapter.starta(visa_webblasare=True)
#      await adapter.ny_konversation()
#      svar = await adapter.skicka_meddelande(
#          "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
#      )
#      print(f"Claude: '{svar}'")
#      await adapter.stang()

async def testa_grok():
    adapter = GrokAdapter()
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()
    
    inmatning = adapter.sida.locator('div[contenteditable="true"]').first
    await inmatning.click()
    await inmatning.fill("Svara bara: Hej!")
    await adapter.sida.keyboard.press("Enter")
    
    print("Väntar 15 sekunder...")
    await asyncio.sleep(15)
    
    print("Kollar klasser på element:")
    for selector in ["[class*='message']", "[class*='response']", 
                     "[class*='assistant']", "[class*='bubble']",
                     "[data-testid]"]:
        try:
            antal = await adapter.sida.locator(selector).count()
            if antal > 0:
                print(f"  '{selector}': {antal} element")
                forsta = adapter.sida.locator(selector).first
                klass = await forsta.get_attribute("class")
                data = await forsta.get_attribute("data-testid")
                print(f"    klass='{klass[:60] if klass else None}' data-testid='{data}'")
        except Exception:
            pass
    
    await adapter.stang()

async def main():
    # await testa_claude()
    await testa_grok()

asyncio.run(main())