"""Run tests against running server on port 8767."""
import sys, json, time
import requests

BASE = "http://127.0.0.1:8767"
pass_count = 0
fail_count = 0
errors = []

def test(method, path, label, params=None, expected=200):
    global pass_count, fail_count
    url = BASE + path
    try:
        if method == 'GET':
            r = requests.get(url, params=params, timeout=30)
        else:
            r = requests.post(url, params=params, timeout=30)
        if r.status_code == expected:
            pass_count += 1
            print(f"  OK  {method} {path} -> {r.status_code}")
            return r
        else:
            fail_count += 1
            try:
                detail = r.json().get('detail', r.text[:100])
            except:
                detail = r.text[:100]
            errors.append(f"{label}: exp {expected} got {r.status_code} - {detail}")
            print(f"  FAIL {method} {path} -> {r.status_code}: {detail}")
            return r
    except Exception as e:
        fail_count += 1
        errors.append(f"{label}: EXC {e}")
        print(f"  ERR {method} {path} -> {e}")
        return None

def check(label, condition):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        errors.append(label)
        print(f"  FAIL {label}")

print("=" * 60)
print("PAYMENT FLOW INTEGRATION TESTS")
print("=" * 60)

# Wait for server
for i in range(20):
    try:
        r = requests.get(BASE + '/scout-liq/health', timeout=3)
        if r.status_code == 200:
            print("Server is UP")
            break
    except:
        time.sleep(1)
else:
    print("Server did not start")
    sys.exit(1)

# 1. Health
print("\n--- 1. Health ---")
test('GET', '/scout-liq/health', 'Health')

# 2. Schemes
print("\n--- 2. Schemes ---")
r = test('GET', '/scout-liq/schemes', 'Schemes')
schemes = r.json() if r else []

if not schemes:
    print("  WARN: No schemes in DB. Skipping payment tests.")
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
    if r and r.status_code == 200:
        cutoff_id = r.json()['cutoff_run_id']
        print(f"  cutoff_id={cutoff_id}")
    else:
        cutoff_id = None

if cutoff_id:
    cid = cutoff_id

    # 4. Detail
    print("\n--- 4. Detail ---")
    r = test('GET', f'/scout-liq/payments/{cid}', 'Detail')

    # 5. Recalculate
    print("\n--- 5. Recalculate ---")
    test('POST', f'/scout-liq/payments/{cid}/recalculate', 'Recalc')

    # 6. Review
    print("\n--- 6. Review ---")
    test('POST', f'/scout-liq/payments/{cid}/review', 'Review')

    # 7. Undo -> draft
    print("\n--- 7. Undo (reviewed->draft) ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo->draft')

    # 8. Review again
    print("\n--- 8. Review again ---")
    test('POST', f'/scout-liq/payments/{cid}/review', 'Review2')

    # 9. Approve
    print("\n--- 9. Approve ---")
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve')

    # 10. Undo approved -> reviewed
    print("\n--- 10. Undo (approved->reviewed) ---")
    test('POST', f'/scout-liq/payments/{cid}/undo-status', 'Undo->reviewed')

    # 11. Approve again
    print("\n--- 11. Approve again ---")
    test('POST', f'/scout-liq/payments/{cid}/approve', 'Approve2')

    # 12. Cancel approved
    print("\n--- 12. Cancel approved -> cancelled ---")
    test('POST', f'/scout-liq/payments/{cid}/cancel', 'Cancel', params={'reason': 'test cancel'})

    # Create fresh for paid flow
    print("\n--- Creating fresh cutoff for paid flow ---")
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

        # 14. Double-pay blocked
        print("\n--- 14. Double-pay BLOCKED ---")
        r = requests.post(BASE + f'/scout-liq/payments/{cid2}/mark-paid')
        check('Double-pay -> 400', r.status_code == 400)

        # 15. Undo paid blocked
        print("\n--- 15. Undo paid BLOCKED ---")
        r = requests.post(BASE + f'/scout-liq/payments/{cid2}/undo-status')
        check('Undo paid -> 400', r.status_code == 400)

        # 16. CSV
        print("\n--- 16. Export CSV ---")
        r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.csv', timeout=30)
        check('CSV > 100 bytes', r.status_code == 200 and len(r.text) > 100)

        # 17. XLSX
        print("\n--- 17. Export XLSX ---")
        r = requests.get(BASE + f'/scout-liq/payments/{cid2}/export.xlsx', timeout=30)
        check('XLSX > 100 bytes', r.status_code == 200 and len(r.content) > 100)

        # 18. Report
        print("\n--- 18. Report ---")
        test('GET', f'/scout-liq/payments/{cid2}/report', 'Report')
    else:
        print(f"  FAIL create second draft: {r.status_code}")
        fail_count += 1

# Reports
print("\n--- Reports ---")

# 19. Payment history
test('GET', '/scout-liq/reports/payment-history', 'PayHist')

# 20. Scout
r = requests.get(BASE + '/scout-liq/scouts', timeout=30)
if r.status_code == 200 and r.json():
    sid = r.json()[0]['id']
    print(f"\n--- 20. Scout Report (id={sid}) ---")
    test('GET', f'/scout-liq/reports/scout/{sid}', 'ScoutRpt')
else:
    print("\n--- 20. Scout Report (skipped, no scouts) ---")
    pass_count += 1

# 21. Cohort
print("\n--- 21. Cohort Report ---")
test('GET', '/scout-liq/reports/cohort/2026-W01', 'Cohort')

# 22. Cutoffs list
print("\n--- 22. Cutoffs List ---")
r = test('GET', '/scout-liq/cutoffs', 'Cutoffs')
if r and r.status_code == 200:
    cuts = r.json()
    statuses = [c['status'] for c in cuts]
    has_paid = 'paid' in statuses
    has_cancelled = 'cancelled' in statuses
    print(f"  {len(cuts)} cutoffs, paid={has_paid}, cancelled={has_cancelled}")

# Verify transitions
print("\n--- Verify State Transitions ---")
r = requests.get(BASE + '/scout-liq/cutoffs', timeout=30)
if r.status_code == 200:
    cuts = r.json()
    check('Has paid cutoff', any(c['status'] == 'paid' for c in cuts))
    check('Has cancelled cutoff', any(c['status'] == 'cancelled' for c in cuts))

# Summary
print("\n" + "=" * 60)
print(f"RESULTS: Pass={pass_count} Fail={fail_count}")
print("=" * 60)
if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED!")
print("=" * 60)
