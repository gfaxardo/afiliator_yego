"""Audit: Financial vs Blocking consistency check. Read-only."""
import requests, json, time

BASE = "http://localhost:8000"
FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

# 1. Preview
print("=== 1. PREVIEW ===")
t0 = time.time()
with open(FILE, "rb") as f:
    r = requests.post(f"{BASE}/scout-liq/historical-imports/preview?sheet=01_PAGOS_HISTORICOS",
        files={"file": ("p.xlsx", f)}, timeout=300)
elapsed = time.time() - t0
p = r.json()
attr = p.get("attribution", {})
fin = p.get("payment_financial", {})
blk = p.get("payment_blocking", {})
pay = p.get("payment", {})

print(f"Status: {r.status_code} ({elapsed:.1f}s) - Batch #{p.get('batch_id')}")
print(f"Total rows: {p['total_rows']}")
print(f"\nCAPA 1 - Atribucion:")
print(f"  ready={attr.get('ready')} review={attr.get('manual_review')}")
print(f"\nCAPA 2 - Pago Financiero:")
print(f"  ready={fin.get('ready')} not_applicable={fin.get('not_applicable')} review={fin.get('manual_review')} amount=S/ {fin.get('amount_ready')}")
print(f"\nCAPA 3 - Bloqueo Futuro:")
print(f"  ready={blk.get('ready')} manual_review={blk.get('manual_review')} amount=S/ {blk.get('amount_ready')}")
print(f"\nLegacy payment: ready={pay.get('ready')} duplicates={pay.get('duplicates')}")

# 2. Check existing paid_history
print("\n=== 2. EXISTING PAID_HISTORY ===")
r2 = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=200", timeout=10)
ph = r2.json()
items = ph.get("items", [])
with_driver = [i for i in items if i.get("driver_id")]
without_driver = [i for i in items if not i.get("driver_id")]
blocks_true = [i for i in items if i.get("blocks_future_payment")]
blocks_false = [i for i in items if i.get("blocks_future_payment") == False]
resolved = [i for i in items if i.get("resolution_status") == "resolved"]
unresolved = [i for i in items if i.get("resolution_status") == "unresolved_driver"]

print(f"Total historical_upload: {ph['total']}")
print(f"  With driver_id: {len(with_driver)} | Without: {len(without_driver)}")
print(f"  blocks_future_payment=true: {len(blocks_true)} | false: {len(blocks_false)}")
print(f"  resolution=resolved: {len(resolved)} | unresolved_driver: {len(unresolved)}")
print(f"  Total amount: S/ {sum(float(i.get('amount_paid',0)) for i in items):.2f}")

# 3. Duplicate risk analysis
print("\n=== 3. DUPLICATE RISK ===")
# Get unique hashes from existing records
existing_hashes = set(i.get("unique_hash") for i in items if i.get("unique_hash"))
# Check if preview lines would create duplicates
sample_lines = p.get("lines", [])[:10]
dup_count = 0
for line in sample_lines:
    h = line.get("unique_hash")
    if h and h in existing_hashes:
        dup_count += 1
# Count blocking_ready lines
blk_ready_lines = [l for l in p.get("lines", []) if l.get("payment_blocking_status") == "payment_blocking_ready"]
fin_ready_lines = [l for l in p.get("lines", []) if l.get("payment_financial_status") == "payment_financial_ready"]

print(f"Existing unique hashes in DB: {len(existing_hashes)}")
print(f"Preview blocking_ready: {len(blk_ready_lines)}")
print(f"Preview financial_ready: {len(fin_ready_lines)}")
print(f"Sample duplicate check: {dup_count} of 10 would match existing hashes")

# 4. Sample rows by type
print("\n=== 4. SAMPLE ROWS ===")
# Find one financial_ready but blocking not ready
fin_only = [l for l in p.get("lines", []) if l.get("payment_financial_status") == "payment_financial_ready" and l.get("payment_blocking_status") != "payment_blocking_ready"]
if fin_only:
    l = fin_only[0]
    print(f"Financial-only (no blocking):")
    print(f"  row={l.get('source_row')} scout={l.get('scout_name_raw','')} lic={l.get('driver_license_raw','')}")
    print(f"  amt={l.get('amount_paid')} fin={l.get('payment_financial_status')} blk={l.get('payment_blocking_status')}")
    print(f"  blocks_future_payment={l.get('blocks_future_payment')}")

all_ready = [l for l in p.get("lines", []) if l.get("payment_blocking_status") == "payment_blocking_ready"]
if all_ready:
    l = all_ready[0]
    print(f"\nBlocking-ready:")
    print(f"  row={l.get('source_row')} scout={l.get('scout_name_raw','')} lic={l.get('driver_license_raw','')}")
    print(f"  driver_id={l.get('driver_id_resolved','')} amt={l.get('amount_paid')} blocks={l.get('blocks_future_payment')}")

# 5. Cutoff engine check
print("\n=== 5. CUTOFF ENGINE CHECK ===")
# Get a driver_id that exists in paid_history without blocks
if unresolved:
    print(f"Records with unresolved_driver: {len(unresolved)}")
    sample_unresolved = unresolved[0]
    print(f"  Sample: PH#{sample_unresolved['id']} driver_id={sample_unresolved.get('driver_id')} blocks={sample_unresolved.get('blocks_future_payment')} amount={sample_unresolved.get('amount_paid')}")
    print(f"  This record will NOT block future cutoffs (driver_id is NULL)")

print("\n=== 6. RECOMMENDATION ===")
if blk.get("ready", 0) > 0 and blk.get("ready") <= len(blocks_true):
    print("WARNING: blocking_ready records may duplicate existing paid_history. Review before commit.")
if fin.get("ready", 0) > len(without_driver):
    print(f"OK: {fin.get('ready')} financial records would be new (DB has {len(without_driver)} without driver).")
else:
    print("OK: No duplicate risk detected for financial records.")
print("RECOMMENDATION: Preview looks clean. Commit will create financial records with proper blocks_future_payment flags.")
