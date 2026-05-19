"""Fresh preview + commit + audit."""
import requests, json, time

BASE = "http://localhost:8000"
FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

# Preview
print("1. PREVIEW...")
t0 = time.time()
with open(FILE, "rb") as f:
    r = requests.post(f"{BASE}/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
        files={"file": ("p.xlsx", f)}, timeout=300)
elapsed = time.time() - t0
p = r.json()
batch_id = p["batch_id"]
fin = p["payment_financial"]
blk = p["payment_blocking"]
print(f"Status: {r.status_code} ({elapsed:.1f}s) Batch #{batch_id}")
print(f"Financial: ready={fin['ready']} amount={fin['amount_ready']}")
print(f"Blocking: ready={blk['ready']} manual_review={blk['manual_review']}")

# Check a sample line has fields
r2 = requests.get(f"{BASE}/scout-liq/historical-imports/{batch_id}/lines?limit=2", timeout=10)
lines = r2.json()
if lines:
    l = lines[0]
    print(f"\nSample line fields: attr={l.get('attribution_status')} fin={l.get('payment_financial_status')} blk={l.get('payment_blocking_status')} final={l.get('final_status')}")
    has_fields = bool(l.get('payment_financial_status') or l.get('attribution_status'))
    print(f"Has dual-layer fields: {has_fields}")

# Commit
print(f"\n2. COMMIT batch #{batch_id}...")
t0 = time.time()
r3 = requests.post(f"{BASE}/scout-liq/historical-imports/commit?batch_id={batch_id}", timeout=600)
elapsed = time.time() - t0
cr = r3.json()
print(f"Status: {r3.status_code} ({elapsed:.1f}s)")
print(f"paid_history_created: {cr.get('paid_history_created')}")
print(f"attributions_saved: {cr.get('attributions_saved')}")
print(f"assignments_created: {cr.get('assignments_created')}")
print(f"amount_imported: S/ {cr.get('amount_imported')}")

# Audit
print(f"\n3. AUDIT")
r4 = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=500", timeout=10)
items = r4.json()["items"]
with_d = len([i for i in items if i.get("driver_id")])
without_d = len([i for i in items if not i.get("driver_id")])
blocks_true_no_driver = len([i for i in items if i.get("blocks_future_payment") == True and not i.get("driver_id")])
total_amt = sum(float(i.get("amount_paid",0)) for i in items)
hashes = [i.get("unique_hash") for i in items if i.get("unique_hash")]
dupes = len(hashes) - len(set(hashes))

print(f"Total historical_upload: {len(items)}")
print(f"With driver: {with_d} | Without: {without_d}")
print(f"blocks_true without driver (BUG): {blocks_true_no_driver}")
print(f"Duplicate hashes: {dupes}")
print(f"Total amount: S/ {total_amt:.2f}")

print(f"\n=== VERDICT ===")
ok = cr.get("paid_history_created",0) > 0 and blocks_true_no_driver == 0 and dupes == 0
print(f"{'GO' if ok else 'NO GO'}")
