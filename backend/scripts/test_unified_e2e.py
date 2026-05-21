"""Test unified load service E2E."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.unified_load_service import unified_preview, _parse_rows_from_csv

db = SessionLocal()
try:
    csv_text = open(os.path.join(os.path.dirname(__file__), 'test_unified.csv'), encoding='utf-8-sig').read()
    rows, errors = _parse_rows_from_csv(csv_text)
    print(f"Parsed {len(rows)} rows, {len(errors)} errors")

    result = unified_preview(db, rows)

    print()
    print("=== PREVIEW RESULT ===")
    for k, v in result.items():
        if k != 'lines':
            print(f"  {k}: {v}")

    print()
    print("=== LINEAS ===")
    for l in result['lines']:
        src = l.get('source_row', 0)
        lic = l.get('licencia', '')
        scout = l.get('scout', '')
        st = l.get('status', '')
        drv = l.get('driver_id_resolved', '')
        sid = l.get('scout_id_resolved', '')
        acts = l.get('deduced_actions', [])
        warns = l.get('warnings', [])
        errs = l.get('errors', [])
        print(f"  Row {src}: lic={lic} scout={scout} status={st} driver={drv} scout_id={sid} actions={acts} warnings={warns} errors={errs}")

    print()
    print("[OK] Unified load preview funciona")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
