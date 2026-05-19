import requests, json

# Check batch status
r = requests.get("http://localhost:8000/scout-liq/historical-imports", timeout=10)
batches = r.json()
for b in batches:
    if b["id"] == 17:
        print(f"Batch #17: status={b['status']} imported={b['imported_count']} "
              f"rejected={b['rejected_count']} review={b['manual_review_count']} "
              f"amount={b.get('amount_imported')}")

# Get a sample line from batch 17 to check fields
r2 = requests.get("http://localhost:8000/scout-liq/historical-imports/17/lines?limit=3", timeout=10)
lines = r2.json()
if lines:
    l = lines[0]
    print(f"\nSample line from batch 17:")
    print(f"  attr_status={l.get('attribution_status')}")
    print(f"  fin_status={l.get('payment_financial_status')}")
    print(f"  blk_status={l.get('payment_blocking_status')}")
    print(f"  paid_history_id={l.get('paid_history_id')}")
    print(f"  final_status={l.get('final_status')}")
    print(f"  All keys: {sorted(l.keys())}")
else:
    print("No lines in batch 17 - batch may not have saved lines properly")
