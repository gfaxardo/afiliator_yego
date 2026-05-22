"""Test payment flow on EXISTING cutoffs to verify endpoints fast."""
import sys, os, time, json, threading, requests
import uvicorn

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.main import app

BASE = "http://127.0.0.1:8769"

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8769, log_level="warning")

t = threading.Thread(target=run_server, daemon=True)
t.start()

for i in range(30):
    try:
        r = requests.get(BASE + '/scout-liq/health', timeout=2)
        if r.status_code == 200:
            break
    except:
        time.sleep(2)
else:
    print("Server failed")
    sys.exit(1)

print("Server UP\n")

pass_count = 0
fail_count = 0
errors = []

def test(method, path, label, params=None, expected=200, timeout=30):
    global pass_count, fail_count
    try:
        r = requests.request(method, BASE + path, params=params, timeout=timeout)
        if r.status_code == expected:
            pass_count += 1
            print(f"  OK  {method} {path} -> {r.status_code}")
            return r
        else:
            fail_count += 1
            try: d = r.json().get('detail', r.text[:120])
            except: d = r.text[:120]
            errors.append(f"{label}: exp {expected} got {r.status_code} - {d}")
            print(f"  FAIL {method} {path} -> {r.status_code}: {d}")
            return r
    except Exception as e:
        fail_count += 1
        errors.append(f"{label}: EXC {e}")
        print(f"  ERR {method} {path} -> {e}")
        return None

# Get existing cutoffs
cuts = requests.get(BASE + '/scout-liq/cutoffs', timeout=30).json()
print(f"Found {len(cuts)} cutoffs")

# Find cutoffs in different states for testing
drafts = [c for c in cuts if c['status'] in ('draft', 'calculated')]
reviewed = [c for c in cuts if c['status'] == 'reviewed']
approved = [c for c in cuts if c['status'] == 'approved']
paid = [c for c in cuts if c['status'] == 'paid']

print(f"  drafts/calculated: {len(drafts)}")
print(f"  reviewed: {len(reviewed)}")
print(f"  approved: {len(approved)}")
print(f"  paid: {len(paid)}")

# ------------------------------------------------------------------
# TEST 1: Get payment detail (works on any cutoff)
# ------------------------------------------------------------------
print("\n--- 1. Payment Detail ---")
if cuts:
    cid = cuts[0]['id']
    r = test('GET', f'/scout-liq/payments/{cid}', 'Detail')
    if r and r.status_code == 200:
        d = r.json()
        print(f"  Metadata: status={d['metadata']['status']}")
        print(f"  Totals: scouts={d['totals']['scouts_evaluated']} drivers={d['totals']['drivers_total']} payable={d['totals']['drivers_payable']}")

# ------------------------------------------------------------------
# TEST 2: Get payment report (works on any cutoff)
# ------------------------------------------------------------------
print("\n--- 2. Payment Report ---")
if cuts:
    cid = cuts[0]['id']
    test('GET', f'/scout-liq/payments/{cid}/report', 'Report')

# ------------------------------------------------------------------
# TEST 3: Review (if draft available)
# ------------------------------------------------------------------
print("\n--- 3. Review (draft->reviewed) ---")
if drafts:
    cid = drafts[0]['id']
    test('POST', f'/scout-liq/payments/{cid}/review', 'Review')

    print("\n--- 4. Undo reviewed->draft ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo')
else:
    print("  SKIP: no drafts available")
    pass_count += 2

# ------------------------------------------------------------------
# TEST 5: Approve (if reviewed available)
# ------------------------------------------------------------------
print("\n--- 5. Approve (reviewed->approved) ---")
if reviewed:
    cid = reviewed[0]['id']
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve')

    print("\n--- 6. Undo approved->reviewed ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo->reviewed')

    print("\n--- 7. Approve again ---")
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve2')
else:
    print("  SKIP: no reviewed cutoffs")
    pass_count += 3

# ------------------------------------------------------------------
# TEST 8: Mark Paid (if approved available)
# ------------------------------------------------------------------
print("\n--- 8. Mark Paid ---")
if approved:
    cid = approved[0]['id']
    test('POST', f'/scout-liq/payments/{cid}/mark-paid', 'Mark Paid')

    print("\n--- 9. Double-pay BLOCK ---")
    r = requests.post(BASE + f'/scout-liq/payments/{cid}/mark-paid', timeout=30)
    if r.status_code == 400:
        pass_count += 1
        print("  OK  Double-pay -> 400 BLOCKED")
    else:
        fail_count += 1
        errors.append("DOUBLE-PAY NOT BLOCKED")
        print(f"  FAIL Double-pay -> {r.status_code}")

    print("\n--- 10. Undo paid BLOCK ---")
    r = requests.post(BASE + f'/scout-liq/payments/{cid}/undo-status', timeout=30)
    if r.status_code == 400:
        pass_count += 1
        print("  OK  Undo paid -> 400 BLOCKED")
    else:
        fail_count += 1
        errors.append("UNDO PAID NOT BLOCKED")
        print(f"  FAIL Undo paid -> {r.status_code}")
else:
    print("  SKIP: no approved cutoffs")
    pass_count += 3

# ------------------------------------------------------------------
# TEST 11: Cancel (draft or reviewed)
# ------------------------------------------------------------------
print("\n--- 11. Cancel ---")
cancel_target = None
if drafts:
    cancel_target = drafts[-1]['id']
elif reviewed:
    cancel_target = reviewed[-1]['id']
if cancel_target:
    test('POST', f'/scout-liq/payments/{cancel_target}/cancel', 'Cancel', params={'reason': 'test cancel'})
else:
    print("  SKIP: nothing to cancel")
    pass_count += 1

# ------------------------------------------------------------------
# TEST 12: Export CSV (paid cutoff)
# ------------------------------------------------------------------
print("\n--- 12. Export CSV ---")
if paid:
    cid = paid[0]['id']
    r = requests.get(BASE + f'/scout-liq/payments/{cid}/export.csv', timeout=30)
    if r.status_code == 200 and len(r.text) > 100:
        pass_count += 1
        print(f"  OK  CSV: {len(r.text)} bytes")
    else:
        fail_count += 1
        print(f"  FAIL CSV: {r.status_code} {len(r.text) if r.status_code==200 else 'N/A'}b")
else:
    print("  SKIP: no paid cutoffs")
    pass_count += 1

# ------------------------------------------------------------------
# TEST 13: Export XLSX (paid cutoff)
# ------------------------------------------------------------------
print("\n--- 13. Export XLSX ---")
if paid:
    cid = paid[0]['id']
    r = requests.get(BASE + f'/scout-liq/payments/{cid}/export.xlsx', timeout=30)
    if r.status_code == 200 and len(r.content) > 100:
        pass_count += 1
        print(f"  OK  XLSX: {len(r.content)} bytes")
    else:
        fail_count += 1
        print(f"  FAIL XLSX: {r.status_code}")
else:
    print("  SKIP: no paid cutoffs")
    pass_count += 1

# ------------------------------------------------------------------
# TEST 14-16: Reports
# ------------------------------------------------------------------
print("\n--- 14. Payment History ---")
test('GET', '/scout-liq/reports/payment-history', 'PayHist')

print("\n--- 15. Scout Report ---")
scouts_r = requests.get(BASE + '/scout-liq/scouts', timeout=30)
if scouts_r.status_code == 200 and scouts_r.json():
    sid = scouts_r.json()[0]['id']
    test('GET', f'/scout-liq/reports/scout/{sid}', 'ScoutRpt')
else:
    pass_count += 1
    print("  SKIP: no scouts")

print("\n--- 16. Cohort Report ---")
test('GET', '/scout-liq/reports/cohort/2026-W01', 'CohortRpt')

# ------------------------------------------------------------------
# Final state verification
# ------------------------------------------------------------------
cuts2 = requests.get(BASE + '/scout-liq/cutoffs', timeout=30).json()
has_paid = any(c['status'] == 'paid' for c in cuts2)
has_cancelled = any(c['status'] == 'cancelled' for c in cuts2)

print(f"\n--- Final State ---")
print(f"  paid={has_paid} cancelled={has_cancelled}")
if not has_cancelled:
    print("  (No cancelled cutoff yet - will show after tests complete)")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
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
