"""Test performance with real user file."""
import requests, time, json

FILE_PATH = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

print("Uploading real file...")
t0 = time.time()

with open(FILE_PATH, "rb") as f:
    r = requests.post(
        "http://localhost:8000/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
        files={"file": ("prueba1.xlsx", f, "application/octet-stream")},
        timeout=300,
    )

elapsed = time.time() - t0
print(f"Status: {r.status_code} (elapsed: {elapsed:.1f}s)")

if r.status_code == 200:
    data = r.json()
    print(f"Rows: {data['total_rows']} Ready: {data['ready_to_import']} "
          f"Review: {data['manual_review']} Rejected: {data['rejected']} Dup: {data['duplicate']}")
    print(f"Amount Ready: S/ {data.get('amount_ready', 0)}")
    if data.get('errors_by_type'):
        print(f"Top errors:")
        for k, v in sorted(data['errors_by_type'].items(), key=lambda x: -x[1])[:5]:
            print(f"  {k}: {v}")
else:
    print(f"Error: {r.text[:500]}")
