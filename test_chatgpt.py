import asyncio
from adapters.chatgpt import ChatGPTAdapter


async def main():
    adapter = ChatGPTAdapter()

    print("Startar ChatGPT...")
    await adapter.starta(visa_webblasare=True)

    print("\nNavigerar till ny konversation...")
    await adapter.ny_konversation()

    print("\nSkickar testmeddelande...")
    svar = await adapter.skicka_meddelande(
        "Svara bara med dessa exakta ord: Bokverktyget fungerar!"
    )

    print(f"\nSvar från ChatGPT:\n{svar}")

    print("\nStänger...")
    await adapter.stang()


asyncio.run(main())