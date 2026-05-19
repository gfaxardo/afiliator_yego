import requests
r = requests.get("http://localhost:8000/scout-liq/paid-history?limit=300", timeout=15)
d = r.json()
items = d["items"]
# Find workbook commit records
wb = [i for i in items if i.get("source_file") == "p.xlsx"]
print(f"Total paid_history: {d['total']}")
print(f"Workbook records (source_file=p.xlsx): {len(wb)}")
if wb:
    with_driver = [i for i in wb if i.get("driver_id")]
    without = [i for i in wb if not i.get("driver_id")]
    print(f"  With driver_id: {len(with_driver)}")
    print(f"  Without driver_id (BUG): {len(without)}")
    print(f"  Total amount: S/ {sum(float(i.get('amount_paid',0)) for i in wb):.2f}")
else:
    print("No workbook records found - check IDs:")
    for i in items[:5]:
        print(f"  PH#{i['id']} driver={i.get('driver_id','NULL')} amt={i['amount_paid']} file={i.get('source_file','')}")
