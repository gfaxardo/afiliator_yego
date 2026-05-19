"""Test dual-layer metrics with real file."""
import requests, json, time

FILE_PATH = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

t0 = time.time()
with open(FILE_PATH, "rb") as f:
    r = requests.post(
        "http://localhost:8000/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
        files={"file": ("p.xlsx", f, "application/octet-stream")}, timeout=300)
elapsed = time.time() - t0
print(f"Status: {r.status_code} ({elapsed:.1f}s)")
data = r.json()

# Dual-layer metrics
attr = data.get("attribution", {})
pay = data.get("payment", {})
print(f"\n=== ATRIBUCIONES ===")
print(f"  Total: {attr.get('total')}  Ready: {attr.get('ready')}  Manual Review: {attr.get('manual_review')}  Conflicts: {attr.get('conflicts')}")
print(f"\n=== PAGOS ===")
print(f"  Total: {pay.get('total')}  Ready: {pay.get('ready')}  Not Applicable: {pay.get('not_applicable')}  Manual Review: {pay.get('manual_review')}  Duplicates: {pay.get('duplicates')}")
print(f"  Amount Ready: S/ {pay.get('amount_ready', 0)}")

# Sample lines
print(f"\n=== MUESTRA (primeras 5 filas con datos) ===")
count = 0
for l in data.get("lines", []):
    if count >= 5: break
    if l.get("scout_name_raw") and l.get("driver_license_raw"):
        print(f"  Row={l.get('source_row')} scout={l.get('scout_name_raw','')} lic={l.get('driver_license_raw','')} "
              f"amt={l.get('amount_paid')} attr={l.get('attribution_status','')} pay={l.get('payment_status','')} final={l.get('final_status','')}")
        count += 1

# Show some rejected rows
print(f"\n=== FILAS RECHAZADAS (verdaderas) ===")
count = 0
for l in data.get("lines", []):
    if count >= 3: break
    if l.get("final_status") == "rejected":
        print(f"  Row={l.get('source_row')} attr={l.get('attribution_reason','')} pay={l.get('payment_reason','')}")
        count += 1

print(f"\n=== ESTADISTICAS POR FINAL_STATUS ===")
from collections import Counter
c = Counter(l.get("final_status") for l in data.get("lines", []))
for k, v in c.most_common():
    print(f"  {k}: {v}")
