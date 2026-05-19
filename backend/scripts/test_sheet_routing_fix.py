"""
Test sheet routing fix.
Creates a synthetic template with 01 + 02 sheets and tests correct routing.
"""
import json, requests, sys, io, openpyxl, time

BASE = "http://localhost:8000"

# Check health
r = requests.get(f"{BASE}/scout-liq/health", timeout=5)
if r.status_code != 200:
    print("Backend not reachable")
    sys.exit(1)
print("Backend OK")

# Create synthetic test XLSX with 2 sheets
wb = openpyxl.Workbook()
wb.remove(wb.active)

# Sheet 01_PAGOS_HISTORICOS - 3 test rows
ws1 = wb.create_sheet("01_PAGOS_HISTORICOS")
for col, h in enumerate(['estado_pago','scout_name_raw','driver_license_raw','amount_paid','currency','payment_rule'], 1):
    ws1.cell(row=1, column=col, value=h)
ws1.cell(row=2, column=1, value='PAGADO')
ws1.cell(row=2, column=2, value='Scout Validacion F1.5')
ws1.cell(row=2, column=3, value='Q25822973')
ws1.cell(row=2, column=4, value='150.00')
ws1.cell(row=2, column=5, value='PEN')
ws1.cell(row=2, column=6, value='5_viajes')

# Sheet 02_SCOUTS - 3 test rows
ws2 = wb.create_sheet("02_SCOUTS")
for col, h in enumerate(['scout_name','document_number','scout_type'], 1):
    ws2.cell(row=1, column=col, value=h)
for i, name in enumerate(['TEST SCOUT A', 'TEST SCOUT B', 'TEST SCOUT C'], 2):
    ws2.cell(row=i, column=1, value=name)
    ws2.cell(row=i, column=2, value=f'DNI-{i}')
    ws2.cell(row=i, column=3, value='cabinet')

# Sheet 06_ATRIBUCIONES_HISTORICAS - empty
ws6 = wb.create_sheet("06_ATRIBUCIONES_HISTORICAS")
ws6.cell(row=1, column=1, value='scout_name_raw')
ws6.cell(row=1, column=2, value='driver_license_raw')

buf = io.BytesIO()
wb.save(buf)
buf.seek(0)

# ── TEST 1: xlsx-sheets endpoint (classification) ──
print("\n=== TEST 1: xlsx-sheets classification ===")
buf1 = io.BytesIO()
wb.save(buf1)
buf1.seek(0)
r = requests.post(f"{BASE}/scout-liq/templates/xlsx-sheets",
                  files={'file': ('test.xlsx', buf1, 'application/octet-stream')}, timeout=10)
if r.status_code == 200:
    data = r.json()
    for si in data.get('sheet_info', []):
        print(f"  {si['name']}: {si['import_type_label']} ({si['row_count']} filas)")
else:
    print(f"  ERROR: {r.status_code}")

# ── TEST 2: historical-imports/preview with 01_PAGOS_HISTORICOS ──
print("\n=== TEST 2: historical-imports/preview with 01_PAGOS_HISTORICOS ===")
buf2 = io.BytesIO()
wb.save(buf2)
buf2.seek(0)
r = requests.post(f"{BASE}/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
                  files={'file': ('test.xlsx', buf2, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Rows: {data['total_rows']} Ready: {data['ready_to_import']} Rejected: {data['rejected']}")
else:
    print(f"  Response: {r.text[:300]}")

# ── TEST 3: historical-imports/preview with 02_SCOUTS (MUST REJECT) ──
print("\n=== TEST 3: historical-imports/preview with 02_SCOUTS (should reject) ===")
buf3 = io.BytesIO()
wb.save(buf3)
buf3.seek(0)
r = requests.post(f"{BASE}/scout-liq/historical-imports/preview?sheet=02_SCOUTS",
                  files={'file': ('test.xlsx', buf3, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 400:
    detail = r.json().get('detail', {})
    print(f"  error={detail.get('error')} sheet_type={detail.get('sheet_type')}")
    print(f"  message={detail.get('message','')[:200]}")
    print("  PASS: Correctly rejected 02_SCOUTS as wrong sheet")
elif r.status_code == 200:
    print("  FAIL: Should have rejected 02_SCOUTS but processed as historical payments")
else:
    print(f"  Response: {r.text[:300]}")

# ── TEST 4: scouts/upload-preview with 02_SCOUTS ──
print("\n=== TEST 4: scouts/upload-preview with 02_SCOUTS ===")
buf4 = io.BytesIO()
wb.save(buf4)
buf4.seek(0)
r = requests.post(f"{BASE}/scout-liq/scouts/upload-preview?sheet=02_SCOUTS",
                  files={'file': ('test.xlsx', buf4, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Rows: {data['total_rows']} Create: {data['will_create']} Update: {data['will_update']}")
    print("  PASS: 02_SCOUTS correctly processed as scouts bulk")
elif r.status_code == 400:
    detail = r.json().get('detail', {})
    print(f"  Rejected: {detail.get('message','')}")
else:
    print(f"  Response: {r.text[:300]}")

# ── TEST 5: scouts/upload-preview with 01_PAGOS_HISTORICOS (MUST REJECT) ──
print("\n=== TEST 5: scouts/upload-preview with 01_PAGOS_HISTORICOS (should reject) ===")
buf5 = io.BytesIO()
wb.save(buf5)
buf5.seek(0)
r = requests.post(f"{BASE}/scout-liq/scouts/upload-preview?sheet=01_PAGOS_HISTORICOS",
                  files={'file': ('test.xlsx', buf5, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 400:
    print("  PASS: Correctly rejected 01_PAGOS_HISTORICOS for scouts endpoint")
else:
    print(f"  FAIL or unexpected: {r.status_code}")

# ── TEST 6: attributions/preview with 06_ATRIBUCIONES_HISTORICAS (empty sheet) ──
print("\n=== TEST 6: attributions/preview with 06_ATRIBUCIONES_HISTORICAS (empty) ===")
buf6 = io.BytesIO()
wb.save(buf6)
buf6.seek(0)
r = requests.post(f"{BASE}/scout-liq/attributions/preview?sheet=06_ATRIBUCIONES_HISTORICAS",
                  files={'file': ('test.xlsx', buf6, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Rows: {data.get('total_rows', 0)} Ready: {data.get('ready_to_import', 0)}")
    if data.get('total_rows', 0) == 0:
        print("  PASS: Empty sheet handled gracefully (no error)")
else:
    print(f"  Response: {r.text[:300]}")

# ── TEST 7: attributions/preview with 02_SCOUTS (should reject) ──
print("\n=== TEST 7: attributions/preview with 02_SCOUTS (should reject) ===")
buf7 = io.BytesIO()
wb.save(buf7)
buf7.seek(0)
r = requests.post(f"{BASE}/scout-liq/attributions/preview?sheet=02_SCOUTS",
                  files={'file': ('test.xlsx', buf7, 'application/octet-stream')}, timeout=10)
print(f"  Status: {r.status_code}")
if r.status_code == 400:
    print("  PASS: Correctly rejected 02_SCOUTS for attributions endpoint")
else:
    print(f"  FAIL or unexpected: {r.status_code}")

print("\n=== ALL TESTS DONE ===")
