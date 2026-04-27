import asyncio
import os
from adapters.chatgpt import ChatGPTAdapter
from adapters.claude import ClaudeAdapter

# async def testa_chatgpt_uppladdning():
#     adapter = ChatGPTAdapter()
#     await adapter.starta(visa_webblasare=True)
#     await adapter.ny_konversation()
#     await asyncio.sleep(3)
    
#     print("ChatGPT -- letar efter uppladdningsknappar:")
#     knappar = await adapter.sida.locator("button").all()
#     for knapp in knappar:
#         try:
#             aria = await knapp.get_attribute("aria-label")
#             if aria and any(ord in aria.lower() for ord in 
#                            ["attach", "file", "upload", "bifoga", 
#                             "fil", "ladda", "clip", "plus", "add"]):
#                 print(f"  Hittade: aria='{aria}'")
#         except Exception:
#             pass
    
#     inputs = await adapter.sida.locator("input[type='file']").all()
#     print(f"  File inputs: {len(inputs)}")
    
#     await adapter.stang()

# async def testa_claude_uppladdning():
#     adapter = ClaudeAdapter()
#     await adapter.starta(visa_webblasare=True)
#     await adapter.ny_konversation()
#     await asyncio.sleep(3)
    
#     print("Claude -- letar efter uppladdningsknappar:")
#     knappar = await adapter.sida.locator("button").all()
#     for knapp in knappar:
#         try:
#             aria = await knapp.get_attribute("aria-label")
#             if aria and any(ord in aria.lower() for ord in 
#                            ["attach", "file", "upload", "bifoga",
#                             "fil", "ladda", "clip", "plus", "add"]):
#                 print(f"  Hittade: aria='{aria}'")
#         except Exception:
#             pass

#     inputs = await adapter.sida.locator("input[type='file']").all()
#     print(f"  File inputs: {len(inputs)}")
    
#     await adapter.stang()

# async def main():
#     await testa_chatgpt_uppladdning()
#     await testa_claude_uppladdning()

# asyncio.run(main())

# async def testa_uppladdning():
#     adapter = ChatGPTAdapter()
#     await adapter.starta(visa_webblasare=True)
#     await adapter.ny_konversation()
    
#     await adapter.bifoga_filer({
#         "testfil": "Det här är ett testdokument med lite text."
#     })
    
#     svar = await adapter.skicka_meddelande(
#         "Vad står det i den bifogade filen?"
#     )
#     print(f"Svar: {svar[:200]}")
#     await adapter.stang()

# asyncio.run(testa_uppladdning())

# async def testa_claude_uppladdning():
#     adapter = ClaudeAdapter()
#     await adapter.starta(visa_webblasare=True)
#     await adapter.ny_konversation()
    
#     await adapter.bifoga_filer({
#         "testfil": "Det här är ett testdokument med lite text."
#     })
    
#     svar = await adapter.skicka_meddelande(
#         "Vad står det i den bifogade filen?"
#     )
#     print(f"Claude svar: {svar[:200] if svar else 'TOMT'}")
#     await adapter.stang()

# asyncio.run(testa_claude_uppladdning())

async def testa_grok_uppladdning():
    from adapters.grok import GrokAdapter
    adapter = GrokAdapter()
    await adapter.starta(visa_webblasare=True)
    await adapter.ny_konversation()
    
    misslyckade = await adapter.bifoga_filer({
        "testfil": "Det här är ett testdokument med lite text."
    })
    
    if misslyckade:
        print(f"Grok: Filuppladdning misslyckades för: {list(misslyckade.keys())}")
    
    svar = await adapter.skicka_meddelande(
        "Vad står det i den bifogade filen?"
    )
    print(f"Grok svar: {svar[:200] if svar else 'TOMT'}")
    await adapter.stang()

asyncio.run(testa_grok_uppladdning())