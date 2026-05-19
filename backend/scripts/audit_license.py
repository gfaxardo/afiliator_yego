import requests, openpyxl

# get licenses from template
wb = openpyxl.load_workbook(r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx", read_only=True)
ws = wb["01_PAGOS_HISTORICOS"]
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).strip() if h else "" for h in rows[0]]
lic_col = None
for i, h in enumerate(headers):
    if h == "driver_license_raw":
        lic_col = i
        break
if lic_col is None:
    print("Could not find driver_license_raw column. Headers:", headers[:5])
    lic_col = 11  # fallback

licenses = set()
for r in rows[1:]:
    if r[lic_col]:
        lic = str(r[lic_col]).strip()
        if lic and lic != "X":
            licenses.add(lic)
print(f"Unique licenses in template: {len(licenses)}")

# check against source
r = requests.get("http://localhost:8000/scout-liq/source/drivers?limit=5", timeout=10)
drivers = r.json()["drivers"]
print(f"Source driver sample:")
for dr in drivers[:5]:
    print(f"  driver_id={dr.get('driver_id','')[:20]} lic={dr.get('license')}")

# check specific licenses from template
sample = sorted(licenses)[:5]
print(f"\nChecking template licenses against source:")
for lic in sample:
    r2 = requests.get(f"http://localhost:8000/scout-liq/source/drivers?limit=200", timeout=10)
    found = [d for d in r2.json().get("drivers", []) if d.get("license") == lic]
    print(f"  {lic} -> {'FOUND' if found else 'NOT FOUND'}")

# total source drivers with license
# Try to get count
r3 = requests.get("http://localhost:8000/scout-liq/source/summary", timeout=10)
summary = r3.json()
print(f"\nSource summary: total={summary.get('total_rows')}")

wb.close()
