"""
Audit workbook import consistency.
Checks paid_history records created by workbook_import/commit
against the preview classification rules.
"""
import requests, json, sys
from datetime import datetime

BASE = "http://localhost:8000"

def audit():
    # Get the most recent paid_history with workbook source
    r = requests.get(f"{BASE}/scout-liq/paid-history?import_source=historical_upload&limit=500", timeout=30)
    data = r.json()
    items = data.get("items", [])

    # Filter to workbook_import source_file
    wb_items = [i for i in items if i.get("source_file") in ("p.xlsx", "workbook_import", None) or (i.get("source_sheet") == "01_PAGOS_HISTORICOS" and i.get("paid_at", "").startswith("2026-05"))]

    if not wb_items:
        # Try getting from attributions
        r2 = requests.get(f"{BASE}/scout-liq/attributions?limit=50&import_status=imported", timeout=30)
        attr_data = r2.json()
        print(f"Attributions with import_status=imported: {attr_data.get('total', 0)}")

        # Get all recent paid_history
        print(f"\nTotal paid_history with historical_upload: {len(items)}")
        recent = [i for i in items if i.get("paid_at", "").startswith("2026-05")]
        print(f"Recent (May 2026): {len(recent)}")

        # Check which have driver_id vs not
        with_driver = [i for i in recent if i.get("driver_id")]
        without_driver = [i for i in recent if not i.get("driver_id")]
        print(f"With driver_id: {len(with_driver)}")
        print(f"Without driver_id: {len(without_driver)}")
        print(f"\nTotal amount with driver: S/ {sum(float(i.get('amount_paid',0)) for i in with_driver):.2f}")
        print(f"Total amount without driver: S/ {sum(float(i.get('amount_paid',0)) for i in without_driver):.2f}")

        if without_driver:
            print(f"\n=== PAID_HISTORY WITHOUT DRIVER_ID (SUSPICIOUS) ===")
            for i in without_driver[:10]:
                print(f"  PH#{i['id']} scout={i['scout_id']} lic={i.get('driver_license_raw')} amt=S/ {i.get('amount_paid')} file={i.get('source_file')} sheet={i.get('source_sheet')} row={i.get('source_row')} hash={i.get('unique_hash','')[:16]}...")
    else:
        with_driver = [i for i in wb_items if i.get("driver_id")]
        without_driver = [i for i in wb_items if not i.get("driver_id")]
        print(f"Workbook paid_history: {len(wb_items)}")
        print(f"With driver_id: {len(with_driver)}")
        print(f"Without driver_id (BUG): {len(without_driver)}")

    # Check for duplicates
    hashes = [i.get("unique_hash") for i in items if i.get("unique_hash")]
    dupes = len(hashes) - len(set(hashes))
    print(f"\nDuplicate hashes in paid_history: {dupes}")

    # Summary
    print(f"\n=== AUDIT SUMMARY ===")
    print(f"Total paid_history (historical_upload): {data.get('total', 0)}")
    print(f"Suspicious (no driver_id, workbook source): {len(without_driver) if 'without_driver' in dir() else 0}")
    print(f"Requires cleanup: {'YES' if len(without_driver) > 0 else 'NO'}")

if __name__ == "__main__":
    audit()
