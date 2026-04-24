import asyncio
from adapters.claude import ClaudeAdapter
from adapters.grok import GrokAdapter

async def testa_claude():
     adapter = ClaudeAdapter()
     await adapter.starta(visa_webblasare=True)
     await adapter.ny_konversation()
     svar = await adapter.skicka_meddelande(
         "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
     )
     print(f"Claude: '{svar}'")
     await adapter.stang()

async def testa_grok():
    adapter = GrokAdapter()
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()
    svar = await adapter.skicka_meddelande(
        "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
    )
    print(f"Grok: '{svar}'")
    await adapter.stang()

async def main():
    await testa_claude()
    await testa_grok()

asyncio.run(main())