import asyncio
from adapters.claude import ClaudeAdapter


async def main():
    adapter = ClaudeAdapter()

    print("Startar Claude...")
    await adapter.starta(visa_webblasare=True)

    print("\nVäntar 5 sekunder så du kan se webbläsaren...")
    await asyncio.sleep(5)

    print("\nNavigerar till ny konversation...")
    await adapter.ny_konversation()
    await asyncio.sleep(2)

    print("\nSkickar testmeddelande...")
    svar = await adapter.skicka_meddelande(
        "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
    )

    print(f"\nSvar från Claude:\n{svar}")

    print("\nStänger...")
    await adapter.stang()


asyncio.run(main())