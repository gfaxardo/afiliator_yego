"""Quick check: did the commit succeed?"""
import requests
# Check paid_history count
r = requests.get("http://localhost:8000/scout-liq/paid-history?import_source=historical_upload&limit=5", timeout=10)
d = r.json()
print(f"Total historical_upload: {d['total']}")
for i in d["items"][:5]:
    driver = str(i.get("driver_id", ""))[:16] if i.get("driver_id") else "NULL"
    print(f"  PH#{i['id']} scout={i.get('scout_id','NULL')} driver={driver} amt={i['amount_paid']} blocks={i.get('blocks_future_payment')} res={i.get('resolution_status')}")

# Check attributions
r2 = requests.get("http://localhost:8000/scout-liq/attributions?limit=3", timeout=10)
a = r2.json()
print(f"\nAttributions total: {a.get('total')}")

# Count with/without driver
r3 = requests.get("http://localhost:8000/scout-liq/paid-history?import_source=historical_upload&limit=500", timeout=10)
items = r3.json()["items"]
with_d = [i for i in items if i.get("driver_id")]
without_d = [i for i in items if not i.get("driver_id")]
blocks_true = [i for i in items if i.get("blocks_future_payment") == True]
blocks_false = [i for i in items if i.get("blocks_future_payment") == False]
blocks_true_no_driver = [i for i in blocks_true if not i.get("driver_id")]
total_amt = sum(float(i.get("amount_paid", 0)) for i in items)
print(f"\n  With driver: {len(with_d)}")
print(f"  Without driver: {len(without_d)}")
print(f"  blocks_future_payment=true: {len(blocks_true)}")
print(f"  blocks_future_payment=false: {len(blocks_false)}")
print(f"  blocks_true WITHOUT driver (BUG if >0): {len(blocks_true_no_driver)}")
print(f"  Total amount: S/ {total_amt:.2f}")
# Duplicates
hashes = [i.get("unique_hash") for i in items if i.get("unique_hash")]
dupes = len(hashes) - len(set(hashes))
print(f"  Duplicate hashes: {dupes} (must be 0)")
