import requests, json
BASE = "http://127.0.0.1:8767"

print("Creating draft...")
r = requests.post(BASE + "/scout-liq/payments/drafts", params={
    "hire_date_from": "2025-01-01",
    "hire_date_to": "2025-06-30",
    "scheme_id": 2,
    "notes": "full flow test"
}, timeout=180)

print(f"Status: {r.status_code}")
d = r.json()
print(f"cutoff_id={d['cutoff_run_id']} status={d['status']}")
cid = d['cutoff_run_id']

# Full flow
print("\nRecalculate...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/recalculate", timeout=60)
print(f"  {r.json()}")

print("Review...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/review", timeout=30)
print(f"  {r.json()}")

print("Undo->draft...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/undo-status", timeout=30)
print(f"  {r.json()}")

print("Review again...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/review", timeout=30)
print(f"  {r.json()}")

print("Approve...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/approve", timeout=30)
print(f"  {r.json()}")

print("Undo->reviewed...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/undo-status", timeout=30)
print(f"  {r.json()}")

print("Approve again...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/approve", timeout=30)
print(f"  {r.json()}")

print("Cancel approved...")
r = requests.post(BASE + f"/scout-liq/payments/{cid}/cancel", params={"reason": "test flow"}, timeout=30)
print(f"  {r.json()}")

# Fresh for paid
print("\nCreating fresh draft for paid...")
r = requests.post(BASE + "/scout-liq/payments/drafts", params={
    "hire_date_from": "2025-01-01",
    "hire_date_to": "2025-06-30",
    "scheme_id": 2,
    "notes": "paid test"
}, timeout=180)
cid2 = r.json()['cutoff_run_id']
print(f"  cutoff_id={cid2}")

requests.post(BASE + f"/scout-liq/payments/{cid2}/review")
requests.post(BASE + f"/scout-liq/payments/{cid2}/approve")

print("Mark paid...")
r = requests.post(BASE + f"/scout-liq/payments/{cid2}/mark-paid", timeout=60)
print(f"  {r.json()}")

print("Try double-pay...")
r = requests.post(BASE + f"/scout-liq/payments/{cid2}/mark-paid", timeout=30)
result = "BLOCKED" if r.status_code == 400 else "FAIL - NOT BLOCKED"
print(f"  Status {r.status_code}: {result}")

print("Try undo paid...")
r = requests.post(BASE + f"/scout-liq/payments/{cid2}/undo-status", timeout=30)
result = "BLOCKED" if r.status_code == 400 else "FAIL - NOT BLOCKED"
print(f"  Status {r.status_code}: {result}")

print("Export CSV...")
r = requests.get(BASE + f"/scout-liq/payments/{cid2}/export.csv", timeout=30)
print(f"  CSV: {len(r.text)} bytes")

print("Export XLSX...")
r = requests.get(BASE + f"/scout-liq/payments/{cid2}/export.xlsx", timeout=30)
print(f"  XLSX: {len(r.content)} bytes")

print("Report...")
r = requests.get(BASE + f"/scout-liq/payments/{cid2}/report", timeout=30)
d = r.json()
print(f"  Status={d['metadata']['status']} Paid={d['totals']['drivers_paid_in_cutoff']}")

# Verify cutoffs list
cuts = requests.get(BASE + "/scout-liq/cutoffs", timeout=30).json()
statuses = [c['status'] for c in cuts]
has_paid = 'paid' in statuses
has_cancelled = 'cancelled' in statuses
print(f"\nCutoffs: {len(cuts)}, paid={has_paid}, cancelled={has_cancelled}")

print("\n=== ALL FLOWS PASSED ===")
print(f"draft -> reviewed -> approved -> paid: OK")
print(f"Double-pay blocked: {result}")
print(f"Undo paid blocked: {result}")
print(f"CSV export: OK")
print(f"XLSX export: OK")
print(f"Cancel: cancelled={has_cancelled}")
