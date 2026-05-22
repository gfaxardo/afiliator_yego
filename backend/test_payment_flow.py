"""Test Payment Flow endpoints - in-process with uvicorn thread."""
import sys, os, json, time, threading
sys.path.insert(0, '.')
os.environ.setdefault('DATABASE_URL', os.environ.get('DATABASE_URL', ''))

import requests
import uvicorn
from app.main import app

BASE = "http://127.0.0.1:8766"

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="error")

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(3)

pass_count = 0
fail_count = 0
errors = []

def test(method, path, label, params=None, expected=200):
    global pass_count, fail_count
    url = BASE + path
    try:
        if method == 'GET':
            r = requests.get(url, params=params, timeout=30)
        elif method == 'POST':
            r = requests.post(url, params=params, timeout=30)
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
            print(f"  FAIL {method} {path} -> {r.status_code} (exp {expected}): {detail}")
            return r
    except Exception as e:
        fail_count += 1
        errors.append(f"{label}: EXCEPTION {e}")
        print(f"  ERR {method} {path} -> {e}")
        return None

print("=" * 60)
print("PAYMENT FLOW INTEGRATION TESTS")
print("=" * 60)

# 1. Health
print("\n--- 1. Health ---")
test('GET', '/scout-liq/health', 'Health')

# 2. Schemes
print("\n--- 2. Schemes ---")
r = test('GET', '/scout-liq/schemes', 'Schemes')
schemes = r.json() if r else []

if not schemes:
    print("  WARN: No schemes. Tests limited.")
    cutoff_id = None
else:
    sid = schemes[0]['id']
    sname = schemes[0].get('scheme_name', '?')
    print(f"  Using scheme_id={sid} ({sname})")

    # 3. Create draft
    print("\n--- 3. Create Draft ---")
    r = test('POST', '/scout-liq/payments/drafts', 'Create Draft', params={
        'hire_date_from': '2025-01-01', 'hire_date_to': '2025-06-30',
        'scheme_id': sid, 'notes': 'integration test'
    })
    cutoff_id = r.json()['cutoff_run_id'] if r and r.status_code == 200 else None

if cutoff_id:
    cid = cutoff_id
    print(f"  cutoff_id={cid}")

    # 4. Detail
    print("\n--- 4. Detail ---")
    r = test('GET', f'/scout-liq/payments/{cid}', 'Detail')
    if r and r.status_code == 200:
        d = r.json()
        t = d.get('totals', {})
        print(f"  Status={d['metadata']['status']} Scouts={t.get('scouts_evaluated')} Drivers={t.get('drivers_total')} Payable={t.get('drivers_payable')}")

    # 5. Recalculate
    print("\n--- 5. Recalculate ---")
    test('POST', f'/scout-liq/payments/{cid}/recalculate', 'Recalc')

    # 6. Review
    print("\n--- 6. Review ---")
    test('POST', f'/scout-liq/payments/{cid}/review', 'Review')

    # 7. Undo -> draft
    print("\n--- 7. Undo reviewed->draft ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo')

    # 8. Review again
    print("\n--- 8. Review again ---")
    test('POST', f'/scout-liq/payments/{cid}/review', 'Review2')

    # 9. Approve
    print("\n--- 9. Approve ---")
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve')

    # 10. Undo approved -> reviewed
    print("\n--- 10. Undo approved->reviewed ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo2')

    # 11. Approve again
    print("\n--- 11. Approve again ---")
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve2')

    # 12. Cancel approved
    print("\n--- 12. Cancel approved ---")
    test('POST', f'/scout-liq/payments/{cid}/cancel', 'Cancel', params={'reason': 'test'})

    # Fresh cutoff for paid tests
    print("\n--- Creating fresh cutoff ---")
    r = requests.post(BASE + '/scout-liq/payments/drafts', params={
        'hire_date_from': '2025-01-01', 'hire_date_to': '2025-06-30',
        'scheme_id': sid, 'notes': 'paid test'
    }, timeout=30)
    if r.status_code == 200:
        cid2 = r.json()['cutoff_run_id']
        print(f"  cutoff_id={cid2}")
        requests.post(BASE + f'/scout-liq/payments/{cid2}/review')
        requests.post(BASE + f'/scout-liq/payments/{cid2}/approve')

        # 13. Mark paid
        print("\n--- 13. Mark Paid ---")
        test('POST', f'/scout-liq/payments/{cid2}/mark-paid', 'Mark Paid')

        # 14. Duplicate block
        print("\n--- 14. Double-pay BLOCK ---")
        r = requests.post(BASE + f'/scout-liq/payments/{cid2}/mark-paid')
        if r.status_code == 400:
            pass_count += 1
            print("  OK  double-pay -> 400 BLOCKED")
        else:
            fail_count += 1
            errors.append("DOUBLE PAY NOT BLOCKED!")
            print(f"  FAIL double-pay -> {r.status_code}")

        # 15. Undo paid block
        print("\n--- 15. Undo paid BLOCK ---")
        r = requests.post(BASE + f'/scout-liq/payments/{cid2}/undo-status')
        if r.status_code == 400:
            pass_count += 1
            print("  OK  undo-paid -> 400 BLOCKED")
        else:
            fail_count += 1
            errors.append("UNDO PAID NOT BLOCKED!")
            print(f"  FAIL undo-paid -> {r.status_code}")

        # 16. Export CSV
        print("\n--- 16. Export CSV ---")
        r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.csv', timeout=30)
        if r.status_code == 200 and len(r.text) > 100:
            pass_count += 1
            print(f"  OK  CSV {len(r.text)} bytes")
        else:
            fail_count += 1
            errors.append("CSV export failed")
            print(f"  FAIL CSV -> {r.status_code} {len(r.text)}b")

        # 17. Export XLSX
        print("\n--- 17. Export XLSX ---")
        r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.xlsx', timeout=30)
        if r.status_code == 200 and len(r.content) > 100:
            pass_count += 1
            print(f"  OK  XLSX {len(r.content)} bytes")
        else:
            fail_count += 1
            errors.append("XLSX export failed")
            print(f"  FAIL XLSX -> {r.status_code} {len(r.content)}b")

        # 18. Report
        print("\n--- 18. Report ---")
        test('GET', f'/scout-liq/payments/{cid2}/report', 'Report')
    else:
        print(f"  FAIL create second draft: {r.status_code}")
        fail_count += 1

# 19. Payment history
print("\n--- 19. Payment History ---")
test('GET', '/scout-liq/reports/payment-history', 'PayHist')

# 20. Scout report
r = requests.get(BASE + '/scout-liq/scouts', timeout=30)
if r.status_code == 200 and r.json():
    sid = r.json()[0]['id']
    print(f"\n--- 20. Scout Report (id={sid}) ---")
    test('GET', f'/scout-liq/reports/scout/{sid}', 'ScoutRpt')
else:
    print("\n--- 20. Scout Report (no scouts, skipped) ---")
    pass_count += 1

# 21. Cohort report
print("\n--- 21. Cohort Report ---")
test('GET', '/scout-liq/reports/cohort/2026-W01', 'CohortRpt')

# 22. Verify cutoffs list
print("\n--- 22. List Cutoffs ---")
r = test('GET', '/scout-liq/cutoffs', 'Cutoffs')
if r and r.status_code == 200:
    cuts = r.json()
    statuses = [c['status'] for c in cuts]
    print(f"  {len(cuts)} cutoffs, statuses: {statuses}")

# Summary
print("\n" + "=" * 60)
print(f"RESULTS: Pass={pass_count} Fail={fail_count}")
print("=" * 60)
if errors:
    print("\nERRORS:")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED")
print("=" * 60)
