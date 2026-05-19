"""Full end-to-end: preview + commit + audit."""
import requests, json, time, os, csv
from datetime import datetime

BASE = "http://localhost:8000"
FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

# 1. Check existing
r = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=300", timeout=10)
ph_existing = r.json()
print(f"1. EXISTING paid_history (historical_upload): {ph_existing['total']}")
for i in ph_existing["items"][:3]:
    print(f"   PH#{i['id']} driver={i.get('driver_id','NULL')[:20] if i.get('driver_id') else 'NULL'} amt={i['amount_paid']} blocks={i.get('blocks_future_payment')}")

# 2. New preview
print("\n2. NEW PREVIEW...")
t0 = time.time()
with open(FILE, "rb") as f:
    r = requests.post(f"{BASE}/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
        files={"file": ("p.xlsx", f)}, timeout=300)
elapsed = time.time() - t0
p = r.json()
batch_id = p.get("batch_id")
attr = p.get("attribution", {})
fin = p.get("payment_financial", {})
blk = p.get("payment_blocking", {})
print(f"   Status: {r.status_code} ({elapsed:.1f}s) Batch #{batch_id}")
print(f"   Attribution: ready={attr.get('ready')} review={attr.get('manual_review')}")
print(f"   Financial: ready={fin.get('ready')} amount=S/ {fin.get('amount_ready')}")
print(f"   Blocking: ready={blk.get('ready')} manual_review={blk.get('manual_review')}")

# 3. Commit
print(f"\n3. COMMIT batch #{batch_id}...")
t0 = time.time()
r2 = requests.post(f"{BASE}/scout-liq/historical-imports/commit?batch_id={batch_id}&uploaded_by=audit", timeout=300)
elapsed = time.time() - t0
cr = r2.json()
print(f"   Status: {r2.status_code} ({elapsed:.1f}s)")
print(f"   paid_history_created: {cr.get('paid_history_created')}")
print(f"   attributions_saved: {cr.get('attributions_saved')}")
print(f"   assignments_created: {cr.get('assignments_created')}")
print(f"   conflicts: {cr.get('conflicts')}")
print(f"   manual_review_saved: {cr.get('manual_review_saved')}")
print(f"   amount_imported: S/ {cr.get('amount_imported', 0)}")

# 4. Post-commit audit
print(f"\n4. POST-COMMIT AUDIT")
r3 = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=500", timeout=10)
ph_all = r3.json()
items = ph_all["items"]
with_driver = [i for i in items if i.get("driver_id")]
without_driver = [i for i in items if not i.get("driver_id")]
blocks_true = [i for i in items if i.get("blocks_future_payment")]
blocks_false = [i for i in items if i.get("blocks_future_payment") == False]
total_amt = sum(float(i.get("amount_paid", 0)) for i in items)
print(f"   Total historical_upload: {ph_all['total']}")
print(f"   With driver_id: {len(with_driver)} (blocks_future_payment)")
print(f"   Without driver_id: {len(without_driver)} (financial only)")
print(f"   blocks_future_payment=true: {len(blocks_true)}")
print(f"   blocks_future_payment=false: {len(blocks_false)}")
print(f"   Total amount: S/ {total_amt:.2f}")

# Check blocks_true without driver (should be 0)
blocks_true_no_driver = [i for i in items if i.get("blocks_future_payment") == True and not i.get("driver_id")]
print(f"   BLOCKS_TRUE WITHOUT DRIVER_ID: {len(blocks_true_no_driver)} (must be 0)")

# Duplicates
hashes = [i.get("unique_hash") for i in items if i.get("unique_hash")]
dup_count = len(hashes) - len(set(hashes))
print(f"   Duplicate hashes: {dup_count} (must be 0)")

# 5. Attributions check
r4 = requests.get(f"{BASE}/scout-liq/attributions?limit=5", timeout=10)
at = r4.json()
print(f"\n5. Historical attributions: {at.get('total')}")

# 6. Export manual_review to CSV
print(f"\n6. Exporting manual_review CSV...")
r5 = requests.get(f"{BASE}/scout-liq/historical-imports/{batch_id}/lines?import_status=manual_review", timeout=10)
lines = r5.json()
print(f"   Manual review lines in batch: {len(lines)}")
if lines:
    export_dir = os.path.join(os.path.dirname(__file__), "..", "exports")
    os.makedirs(export_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(export_dir, f"manual_review_batch_{batch_id}_{ts}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source_row","scout_name_raw","driver_license_raw","driver_id_resolved",
            "amount_paid","attribution_status","attribution_reason","payment_financial_status",
            "payment_financial_reason","payment_blocking_status","payment_blocking_reason","final_status",
            "paid_history_id","import_status","import_reason"])
        w.writeheader()
        for l in lines[:2000]:
            w.writerow({k: l.get(k, "") for k in w.fieldnames})
    print(f"   CSV: {path} ({len(lines)} rows)")

# 7. Final verdict
print(f"\n=== VERDICT ===")
checks = [
    cr.get("paid_history_created", 0) > 0,
    len(blocks_true_no_driver) == 0,
    dup_count == 0,
    cr.get("attributions_saved", 0) > 0,
]
print(f"paid_history_created > 0: {'PASS' if checks[0] else 'FAIL'}")
print(f"blocks_true without driver = 0: {'PASS' if checks[1] else 'FAIL'}")
print(f"duplicates = 0: {'PASS' if checks[2] else 'FAIL'}")
print(f"attributions saved: {'PASS' if checks[3] else 'FAIL'}")
print(f"OVERALL: {'GO' if all(checks) else 'NO GO'}")
