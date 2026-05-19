import requests, openpyxl

wb = openpyxl.load_workbook(r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx", read_only=True)
ws = wb["01_PAGOS_HISTORICOS"]
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).strip() if h else "" for h in rows[0]]
lic_col = 11
for i, h in enumerate(headers):
    if "driver_license" in h.lower():
        lic_col = i
        break

all_licenses = []
for r in rows[1:]:
    if r[lic_col]:
        lic = str(r[lic_col]).strip()
        if lic and lic != "X":
            all_licenses.append(lic)

unique_licenses = list(set(all_licenses))[:50]

# Check via batch SQL
r = requests.post("http://localhost:8000/scout-liq/templates/xlsx-sheets", timeout=10,
    files={"file": ("p.xlsx", open(r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx","rb"), "application/octet-stream")})

# Run preview to see what the batch cache found
r2 = requests.post("http://localhost:8000/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS", 
    files={"file": ("p.xlsx", open(r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx","rb"), "application/octet-stream")}, 
    timeout=300)

p = r2.json()
# Count lines with driver_id_resolved
with_driver = [l for l in p.get("lines", []) if l.get("driver_id_resolved")]
without_driver = [l for l in p.get("lines", []) if not l.get("driver_id_resolved")]
samples_with = [l for l in p.get("lines", []) if l.get("driver_id_resolved") and l.get("amount_paid") and float(l.get("amount_paid",0)) > 0]

print(f"Lines with driver_id_resolved: {len(with_driver)}")
print(f"Lines without driver_id_resolved: {len(without_driver)}")
print(f"Lines with driver + amount>0: {len(samples_with)}")

if samples_with:
    print(f"\nSample resolved rows:")
    for l in samples_with[:5]:
        print(f"  lic={l.get('driver_license_raw')} driver_id={l.get('driver_id_resolved')[:20]}... amt={l.get('amount_paid')} attr={l.get('attribution_status')} fin={l.get('payment_financial_status')}")

# Check attribution_ready
attr_ready = [l for l in p.get("lines", []) if l.get("attribution_status") == "attribution_ready"]
print(f"\nAttribution ready: {len(attr_ready)}")
if attr_ready:
    print(f"Sample:")
    for l in attr_ready[:3]:
        print(f"  lic={l.get('driver_license_raw')} driver_id={l.get('driver_id_resolved','')[:20]} amt={l.get('amount_paid')}")
wb.close()
