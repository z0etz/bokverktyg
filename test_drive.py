from drive import hamta_drive_tjanst, skapa_projekt

print("Ansluter till Google Drive...")
service = hamta_drive_tjanst()
print("Ansluten!\n")

projekt = skapa_projekt(service, "Min Testbok")

print("\nProjektstruktur:")
print(f"  Rot-ID: {projekt['rot_id']}")
print(f"  Filer: {list(projekt['filer'].keys())}")
print(f"  Mappar: {list(projekt['mappar'].keys())}")