"""Test reconciliation service E2E."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.reconciliation_service import export_reconciliation_csv, compare_upload

db = SessionLocal()
try:
    csv_out = export_reconciliation_csv(db, limit=5)
    lines = csv_out.strip().split('\n')
    print(f"Export CSV: {len(lines)-1} data rows")
    header = lines[0]
    cols = header.split(',')
    print(f"Header columns: {len(cols)}")
    print(f"  Columns: {', '.join(cols[:8])}...")
    if len(lines) > 1:
        print(f"  First row: {lines[1][:150]}...")

    sample_csv = open(os.path.join(os.path.dirname(__file__), 'test_recon.csv'), encoding='utf-8-sig').read()
    result = compare_upload(db, sample_csv)
    print()
    print("Compare Upload Results:")
    for k, v in result.items():
        if k != 'details':
            print(f"  {k}: {v}")
    details = result.get('details', [])
    print(f"  details count: {len(details)}")
    for d in details[:3]:
        print(f"    driver={d.get('driver_id')} status={d.get('status')} reason={d.get('reason')}")

    print()
    print("[OK] Reconciliation service funciona")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
