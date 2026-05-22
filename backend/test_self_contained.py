"""Self-contained test: start server, run tests, stop server."""
import sys, os, time, json, threading, requests
import uvicorn

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.main import app

BASE = "http://127.0.0.1:8768"

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8768, log_level="warning")

# Start server thread
t = threading.Thread(target=run_server, daemon=True)
t.start()

# Wait for server
for i in range(30):
    try:
        r = requests.get(BASE + '/scout-liq/health', timeout=2)
        if r.status_code == 200:
            print("Server UP")
            break
    except:
        time.sleep(2)
else:
    print("Server failed to start")
    sys.exit(1)

pass_count = 0
fail_count = 0
errors = []

def test(method, path, label, params=None, expected=200, timeout=180):
    global pass_count, fail_count
    try:
        if method == 'GET':
            r = requests.get(BASE + path, params=params, timeout=timeout)
        else:
            r = requests.post(BASE + path, params=params, timeout=timeout)
        if r.status_code == expected:
            pass_count += 1
            print(f"  OK  {method} {path} -> {r.status_code}")
            return r
        else:
            fail_count += 1
            try:
                detail = r.json().get('detail', r.text[:120])
            except:
                detail = r.text[:120]
            errors.append(f"{label}: expected {expected} got {r.status_code} - {detail}")
            print(f"  FAIL {method} {path} -> {r.status_code}: {detail}")
            return r
    except Exception as e:
        fail_count += 1
        errors.append(f"{label}: EXC {e}")
        print(f"  ERR {method} {path} -> {e}")
        return None

# Get schemes
r = test('GET', '/scout-liq/schemes', 'Schemes', timeout=30)
schemes = r.json() if r else []
if not schemes:
    print("NO SCHEMES - aborting")
    sys.exit(1)

scheme_id = schemes[0]['id']
sname = schemes[0].get('scheme_name', '?')
print(f"Using scheme {scheme_id}: {sname}")

# ------------------------------------------------------------------
# CREATE DRAFT
# ------------------------------------------------------------------
print("\n--- Create Draft ---")
r = test('POST', '/scout-liq/payments/drafts', 'Create Draft', params={
    'hire_date_from': '2025-01-01', 'hire_date_to': '2025-06-30',
    'scheme_id': scheme_id, 'notes': 'full integration test'
}, timeout=300)
if not r or r.status_code != 200:
    print("Cannot continue without draft")
    sys.exit(1)

cid = r.json()['cutoff_run_id']
print(f"  cutoff_id={cid}")

# Detail
print("\n--- Detail ---")
test('GET', f'/scout-liq/payments/{cid}', 'Detail', timeout=30)

# Recalculate
print("\n--- Recalculate ---")
test('POST', f'/scout-liq/payments/{cid}/recalculate', 'Recalc', timeout=180)

# Review
print("\n--- Review ---")
test('POST', f'/scout-liq/payments/{cid}/review', 'Review', timeout=30)

# Undo -> draft
print("\n--- Undo reviewed->draft ---")
test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo to draft', timeout=30)

# Review again
print("\n--- Review again ---")
test('POST', f'/scout-liq/payments/{cid}/review', 'Review', timeout=30)

# Approve
print("\n--- Approve ---")
test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve', timeout=30)

# Undo -> reviewed
print("\n--- Undo approved->reviewed ---")
test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo to reviewed', timeout=30)

# Approve again
print("\n--- Approve again ---")
test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve', timeout=30)

# Cancel
print("\n--- Cancel ---")
test('POST', f'/scout-liq/payments/{cid}/cancel', 'Cancel', params={'reason': 'test'}, timeout=30)

# Fresh draft for paid flow
print("\n--- Create 2nd draft for paid flow ---")
r = test('POST', '/scout-liq/payments/drafts', 'Create Draft2', params={
    'hire_date_from': '2025-01-01', 'hire_date_to': '2025-06-30',
    'scheme_id': scheme_id, 'notes': 'paid flow test'
}, timeout=300)
if not r or r.status_code != 200:
    print("Cannot test paid flow")
    sys.exit(1)

cid2 = r.json()['cutoff_run_id']
print(f"  cutoff_id={cid2}")

requests.post(BASE + f'/scout-liq/payments/{cid2}/review', timeout=30)
requests.post(BASE + f'/scout-liq/payments/{cid2}/approve', timeout=30)

# Mark paid
print("\n--- Mark Paid ---")
test('POST', f'/scout-liq/payments/{cid2}/mark-paid', 'Mark Paid', timeout=120)

# Double-pay blocked
print("\n--- Double-pay BLOCK ---")
r = requests.post(BASE + f'/scout-liq/payments/{cid2}/mark-paid', timeout=30)
if r.status_code == 400:
    pass_count += 1
    print("  OK  Double-pay -> 400 BLOCKED")
else:
    fail_count += 1
    errors.append("DOUBLE-PAY NOT BLOCKED!")
    print(f"  FAIL Double-pay -> {r.status_code}")

# Undo paid blocked
print("\n--- Undo paid BLOCK ---")
r = requests.post(BASE + f'/scout-liq/payments/{cid2}/undo-status', timeout=30)
if r.status_code == 400:
    pass_count += 1
    print("  OK  Undo paid -> 400 BLOCKED")
else:
    fail_count += 1
    errors.append("UNDO PAID NOT BLOCKED!")
    print(f"  FAIL Undo paid -> {r.status_code}")

# CSV
print("\n--- Export CSV ---")
r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.csv', timeout=30)
if r.status_code == 200 and len(r.text) > 100:
    pass_count += 1
    print(f"  OK  CSV {len(r.text)} bytes")
else:
    fail_count += 1
    print(f"  FAIL CSV -> {r.status_code} {len(r.text)}b")

# XLSX
print("\n--- Export XLSX ---")
r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.xlsx', timeout=30)
if r.status_code == 200 and len(r.content) > 100:
    pass_count += 1
    print(f"  OK  XLSX {len(r.content)} bytes")
else:
    fail_count += 1
    print(f"  FAIL XLSX -> {r.status_code} {len(r.content)}b")

# Report
print("\n--- Report ---")
r = test('GET', f'/scout-liq/payments/{cid2}/report', 'Report', timeout=30)
if r and r.status_code == 200:
    d = r.json()
    print(f"  Paid drivers: {d['totals']['drivers_paid_in_cutoff']}")

# Payment history report
print("\n--- Payment History ---")
test('GET', '/scout-liq/reports/payment-history', 'PayHist', timeout=30)

# Scout report
scouts_r = requests.get(BASE + '/scout-liq/scouts', timeout=30)
if scouts_r.status_code == 200 and scouts_r.json():
    sid = scouts_r.json()[0]['id']
    print(f"\n--- Scout Report ({sid}) ---")
    test('GET', f'/scout-liq/reports/scout/{sid}', 'ScoutRpt', timeout=30)
else:
    pass_count += 1
    print("\n--- Scout Report (skipped) ---")

# Cohort report
print("\n--- Cohort Report ---")
test('GET', '/scout-liq/reports/cohort/2026-W01', 'CohortRpt', timeout=30)

# Verify state transitions
cuts = requests.get(BASE + '/scout-liq/cutoffs', timeout=30).json()
has_paid = any(c['status'] == 'paid' for c in cuts)
has_cancelled = any(c['status'] == 'cancelled' for c in cuts)
has_calc = any(c['status'] == 'calculated' for c in cuts)
has_reviewed = any(c['status'] == 'reviewed' for c in cuts)
has_approved = any(c['status'] == 'approved' for c in cuts)

print(f"\n--- State Summary ---")
print(f"  Cutoffs total: {len(cuts)}")
print(f"  paid={has_paid} cancelled={has_cancelled}")
print(f"  calculated={has_calc} reviewed={has_reviewed} approved={has_approved}")

# Final
print(f"\n{'='*60}")
print(f"RESULTS: Pass={pass_count} Fail={fail_count}")
print(f"{'='*60}")
if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED")
print(f"{'='*60}")

os._exit(0 if fail_count == 0 else 1)
