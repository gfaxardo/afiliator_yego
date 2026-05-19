import requests, json
r = requests.get("http://localhost:8000/scout-liq/paid-history?limit=20", timeout=10)
d = r.json()
print(f"Total: {d['total']}")
for i in d["items"]:
    print(f"  PH#{i['id']} driver={i.get('driver_id','NULL')} amt={i['amount_paid']} src={i['import_source']} sheet={i.get('source_sheet','')} row={i.get('source_row')}")
