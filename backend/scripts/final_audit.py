"""Post-rollback integrity check + workbook re-commit test."""
import requests, json, time

BASE = "http://localhost:8000"

# 1. Check scouts intact
r = requests.get(f"{BASE}/scout-liq/scouts?status=active", timeout=10)
scouts = r.json()
wb_scouts = [s for s in scouts if s.get("imported_from") == "workbook_import"]
print(f"1. Scouts from workbook_import: {len(wb_scouts)} (expected 49)")

# 2. Check attributions
r2 = requests.get(f"{BASE}/scout-liq/attributions?limit=5", timeout=10)
attr = r2.json()
print(f"2. Historical attributions: {attr.get('total', 0)}")

# 3. Check paid_history is clean
r3 = requests.get(f"{BASE}/scout-liq/paid-history?limit=10", timeout=10)
ph = r3.json()
bad_remaining = [i for i in ph.get("items", []) if not i.get("driver_id") and i.get("import_source") == "historical_upload"]
print(f"3. Paid history total: {ph['total']}")
print(f"   Bad remaining: {len(bad_remaining)} (expected 0)")

# 4. Re-execute workbook commit with fix
print("\n4. Re-executing workbook commit...")
FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"
t0 = time.time()
with open(FILE, "rb") as f:
    r4 = requests.post(f"{BASE}/scout-liq/workbook-import/commit",
        files={"file": ("prueba1.xlsx", f, "application/octet-stream")}, timeout=300)
elapsed = time.time() - t0
cr = r4.json()
print(f"   Commit completed in {elapsed:.1f}s")
print(f"   paid_history_created: {cr.get('paid_history_created')}")
print(f"   scouts_created: {cr.get('scouts_created')} (should be 0 - already exist)")
print(f"   scout_supervisor_links_created: {cr.get('scout_supervisor_links_created')}")
print(f"   historical_attributions_created: {cr.get('historical_attributions_created')}")

# 5. Post-commit audit
print("\n5. Post-commit audit...")
r5 = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=200", timeout=10)
ph2 = r5.json()
items = ph2.get("items", [])
bad_now = [i for i in items if not i.get("driver_id")]
without_driver = len(bad_now)
with_driver = [i for i in items if i.get("driver_id")]
total_amount = sum(float(i.get("amount_paid", 0)) for i in items)
print(f"   historical_upload total: {ph2['total']}")
print(f"   With driver_id: {len(with_driver)}")
print(f"   Without driver_id (BAD): {without_driver} (expected 0)")
print(f"   Total amount: S/ {total_amount:.2f} (expected S/ 1980.00)")

# 6. Duplicate check
r6 = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=200", timeout=10)
ph3 = r6.json()
hashes = [i.get("unique_hash") for i in ph3.get("items", []) if i.get("unique_hash")]
dupes = len(hashes) - len(set(hashes))
print(f"   Duplicate hashes: {dupes} (expected 0)")

# 7. Summary
paid_created = cr.get("paid_history_created", 0)
preview_match = paid_created == 72
amount_match = abs(total_amount - 1980.0) < 1.0
print(f"\n=== FINAL VERDICT ===")
print(f"  paid_history_created={paid_created} vs payment_ready=72: {'PASS' if preview_match else 'FAIL'}")
print(f"  amount={total_amount:.2f} vs amount_ready=1980.00: {'PASS' if amount_match else 'FAIL'}")
print(f"  bad without driver_id={without_driver}: {'PASS' if without_driver == 0 else 'FAIL'}")
print(f"  duplicates={dupes}: {'PASS' if dupes == 0 else 'FAIL'}")
if preview_match and amount_match and without_driver == 0 and dupes == 0:
    print("  OVERALL: GO")
else:
    print("  OVERALL: FAIL")
