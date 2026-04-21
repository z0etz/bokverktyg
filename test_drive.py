from drive import get_drive_service, skapa_projekt

print("Ansluter till Google Drive...")
service = get_drive_service()
print("Ansluten!\n")

projekt = skapa_projekt(service, "Min Testbok")

print("\nProjektstruktur:")
print(f"  Rot-ID: {projekt['rot_id']}")
print(f"  Filer: {list(projekt['filer'].keys())}")
print(f"  Mappar: {list(projekt['mappar'].keys())}")