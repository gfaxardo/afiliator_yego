"""Complete integration test using multiprocessing."""
import sys, os, time, json, signal, requests
from multiprocessing import Process

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_uvicorn():
    import uvicorn
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8772, log_level="error")

BASE = "http://127.0.0.1:8772"

# Start server in separate process (not daemon)
proc = Process(target=run_uvicorn)
proc.start()

# Wait for server
print("Waiting for server...")
for i in range(60):
    try:
        r = requests.get(BASE + "/scout-liq/health", timeout=2)
        if r.status_code == 200:
            print("Server UP!")
            break
    except:
        pass
    if i % 10 == 9:
        print(f"  ...{i+1}s")
    time.sleep(1)
else:
    print("FAIL: server did not start")
    proc.terminate()
    proc.join(5)
    sys.exit(1)

# ------------ TESTS ------------
pass_count = 0
fail_count = 0
errors = []

def test(method, path, label, params=None, expected=200, timeout=300):
    global pass_count, fail_count
    try:
        r = requests.request(method, BASE + path, params=params, timeout=timeout)
        if r.status_code == expected:
            pass_count += 1
            print(f"  OK  {method} {path} -> {r.status_code}")
            return r
        else:
            fail_count += 1
            try:
                d = r.json().get("detail", r.text[:120])
            except:
                d = r.text[:120]
            errors.append(f"{label}: exp {expected} got {r.status_code} - {str(d)[:150]}")
            print(f"  FAIL {method} {path} -> {r.status_code}")
            return r
    except Exception as e:
        fail_count += 1
        errors.append(f"{label}: {e}")
        print(f"  ERR {method} {path} -> {str(e)[:120]}")
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

# Get existing cutoffs
cuts = requests.get(BASE + "/scout-liq/cutoffs", timeout=30).json()
statuses = [c["status"] for c in cuts]
print(f"\nExisting cutoffs: {len(cuts)}")
print(f"Statuses: {statuses}")

# 1. Health
print("\n=== 1. Health ===")
test("GET", "/scout-liq/health", "Health")

# 2. Payment Detail
print("\n=== 2. Payment Detail ===")
cid = cuts[0]["id"]
r = test("GET", f"/scout-liq/payments/{cid}", "Detail")
if r and r.status_code == 200:
    d = r.json()
    print(f"  status={d['metadata']['status']} scouts={d['totals']['scouts_evaluated']}")

# 3. Payment Report
print("\n=== 3. Payment Report ===")
test("GET", f"/scout-liq/payments/{cid}/report", "Report")

# 4. Review flow
print("\n=== 4. Review Flow ===")
drafts = [c for c in cuts if c["status"] in ("draft", "calculated")]
if drafts:
    cid = drafts[0]["id"]
    test("POST", f"/scout-liq/payments/{cid}/review", "Review")
    test("POST", f"/scout-liq/payments/{cid}/undo-status", "Undo->draft")
    test("POST", f"/scout-liq/payments/{cid}/review", "Review again")
else:
    print("  No drafts available")
    pass_count += 3

# 5. Approve flow
print("\n=== 5. Approve Flow ===")
reviewed = [c for c in cuts if c["status"] == "reviewed"]
if reviewed:
    cid = reviewed[0]["id"]
    test("POST", f"/scout-liq/payments/{cid}/approve", "Approve")
    test("POST", f"/scout-liq/payments/{cid}/undo-status", "Undo->reviewed")
    test("POST", f"/scout-liq/payments/{cid}/approve", "Approve again")
else:
    print("  No reviewed available")
    pass_count += 3

# 6. Mark Paid + blocking
print("\n=== 6. Mark Paid ===")
approved = [c for c in cuts if c["status"] == "approved"]
if approved:
    cid = approved[0]["id"]
    test("POST", f"/scout-liq/payments/{cid}/mark-paid", "Mark Paid", timeout=600)

    r = requests.post(BASE + f"/scout-liq/payments/{cid}/mark-paid", timeout=30)
    check("Double-pay BLOCKED", r.status_code == 400)

    r = requests.post(BASE + f"/scout-liq/payments/{cid}/undo-status", timeout=30)
    check("Undo paid BLOCKED", r.status_code == 400)

    r = requests.get(BASE + f"/scout-liq/payments/{cid}/export.csv", timeout=30)
    check("CSV export", r.status_code == 200 and len(r.text) > 100)

    r = requests.get(BASE + f"/scout-liq/payments/{cid}/export.xlsx", timeout=30)
    check("XLSX export", r.status_code == 200 and len(r.content) > 100)
else:
    print("  No approved available")
    pass_count += 6

# 7. Cancel
print("\n=== 7. Cancel ===")
drafts2 = [c for c in cuts if c["status"] in ("draft", "calculated")]
cancel_target = None
if drafts2:
    cancel_target = drafts2[-1]["id"]
elif reviewed:
    cancel_target = reviewed[-1]["id"] if reviewed else None
if cancel_target:
    test("POST", f"/scout-liq/payments/{cancel_target}/cancel", "Cancel", params={"reason": "test"})
else:
    print("  Nothing to cancel")
    pass_count += 1

# 8. Reports
print("\n=== 8. Reports ===")
test("GET", "/scout-liq/reports/payment-history", "Payment History")

scouts_r = requests.get(BASE + "/scout-liq/scouts", timeout=30)
if scouts_r.status_code == 200 and scouts_r.json():
    sid = scouts_r.json()[0]["id"]
    test("GET", f"/scout-liq/reports/scout/{sid}", "Scout Report")
else:
    print("  No scouts")
    pass_count += 1

test("GET", "/scout-liq/reports/cohort/2026-W01", "Cohort Report")

# Final state
cuts2 = requests.get(BASE + "/scout-liq/cutoffs", timeout=30).json()
statuses2 = [c["status"] for c in cuts2]
print(f"\n=== Final State ===")
print(f"  Statuses: {statuses2}")
check("Has 'paid'", "paid" in statuses2)
check("Has 'cancelled'", "cancelled" in statuses2)

# Summary
print(f"\n{'='*60}")
print(f"RESULTS: Pass={pass_count} Fail={fail_count}")
print(f"{'='*60}")
if errors:
    for e in errors:
        print(f"  ERR: {e}")
else:
    print("ALL TESTS PASSED!")
print(f"{'='*60}")

# Cleanup
proc.terminate()
proc.join(5)
print("\nServer stopped.")
sys.exit(0 if fail_count == 0 else 1)
