import requests
r = requests.get("http://localhost:8000/scout-liq/paid-history?limit=300", timeout=15)
d = r.json()
items = d["items"]
# Find all workbook-related records
wb_all = [i for i in items if (i.get("source_file") or "") in ("p.xlsx", "workbook_import")]
print(f"Total paid_history: {d['total']}")
print(f"Workbook records (any source): {len(wb_all)}")
if wb_all:
    for sfile in set(i.get("source_file") for i in wb_all):
        subset = [i for i in wb_all if i.get("source_file") == sfile]
        with_d = [i for i in subset if i.get("driver_id")]
        without = [i for i in subset if not i.get("driver_id")]
        print(f"  source_file={sfile}: {len(subset)} records, with_driver={len(with_d)}, without={len(without)}")
else:
    # Look at high IDs only
    high = [i for i in items if (i.get("id") or 0) >= 28]
    print(f"Records with ID >= 28: {len(high)}")
    for i in high[:5]:
        print(f"  PH#{i['id']} driver={i.get('driver_id','NULL')} amt={i['amount_paid']} file='{i.get('source_file','')}' sheet='{i.get('source_sheet','')}' src={i.get('import_source')}")
    # Check if scout_liq_scouts has the 49 new scouts
    r2 = requests.get("http://localhost:8000/scout-liq/scouts?status=active", timeout=10)
    scouts = r2.json()
    wb_scouts = [s for s in scouts if s.get("imported_from") == "workbook_import"]
    print(f"\nScouts from workbook_import: {len(wb_scouts)}")
    if wb_scouts:
        print(f"  Sample: {wb_scouts[0]['scout_name']}")
