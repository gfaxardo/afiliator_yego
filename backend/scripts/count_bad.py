import requests, json
r = requests.get("http://localhost:8000/scout-liq/paid-history?import_source=historical_upload&limit=500", timeout=30)
items = r.json().get("items", [])
bad = [i for i in items if not i.get("driver_id") and i.get("source_sheet") == "01_PAGOS_HISTORICOS"]
good = [i for i in items if i.get("driver_id") and i.get("source_sheet") == "01_PAGOS_HISTORICOS"]
print(f"Total historical_upload: {len(items)}")
print(f"Bad (no driver_id): {len(bad)} - amount=S/ {sum(float(i.get('amount_paid',0)) for i in bad):.2f}")
print(f"Good (with driver_id): {len(good)} - amount=S/ {sum(float(i.get('amount_paid',0)) for i in good):.2f}")
if bad:
    ids = [i["id"] for i in bad]
    print(f"\nBad IDs range: {min(ids)}-{max(ids)}")
    print(f"Sample:")
    for i in bad[:3]:
        print(f"  PH#{i['id']} scout={i['scout_id']} lic={i.get('driver_license_raw')} amt=S/ {i.get('amount_paid')} row={i.get('source_row')}")
    print(f"\nSQL to rollback:")
    print(f"  DELETE FROM scout_liq_paid_history WHERE id BETWEEN {min(ids)} AND {max(ids)} AND driver_id IS NULL AND source_sheet = '01_PAGOS_HISTORICOS';")
    print(f"\nWARNING: {len(bad)} records will be deleted. Review before executing.")
