import asyncio
from adapters.grok import GrokAdapter


async def main():
    adapter = GrokAdapter()

    print("Startar Grok...")
    await adapter.starta(visa_webblasare=True)

    print("\nNavigerar till ny konversation...")
    await adapter.ny_konversation()

    print("\nSkickar testmeddelande...")
    svar = await adapter.skicka_meddelande(
        "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
    )

    print(f"\nSvar från Grok:\n{svar}")

    print("\nStänger...")
    await adapter.stang()


asyncio.run(main())