"""Test unified apply flow with partial data (some rows missing pagado)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.unified_load_service import (
    unified_preview, unified_apply, _parse_rows_from_csv,
    REQUIRED_COLS, OPTIONAL_COLS,
)

print(f"REQUIRED_COLS: {REQUIRED_COLS}")
print(f"OPTIONAL_COLS: {OPTIONAL_COLS}")
print()

# Simulate user's scenario: some rows have pagado, some don't
csv_content = "licencia,scout,supervisor,pagado,monto_pagado,fecha_pago,observacion\n"
# Row with all fields
csv_content += "Q45406817,Scout A,Juan,SI,150,2026-01-15,ok\n"
# Row without pagado (should be optional now)
csv_content += "Q99999999,Scout B,Maria,,,,,\n"
# Row without pagado, monto, fecha
csv_content += "Q12345678,Scout C,Pedro,,,,,\n"
# Row with pagado = SI but no monto
csv_content += "Q87654321,Scout D,Ana,SI,,,\n"

rows, errors, meta = _parse_rows_from_csv(csv_content)
print(f"Parsed: {len(rows)} rows, {len(errors)} errors")
if errors:
    print(f"  Errors: {errors}")
print(f"  Metadata: {meta}")

db = SessionLocal()
try:
    preview = unified_preview(db, rows)
    print(f"\nPreview:")
    print(f"  total: {preview['total_rows']}")
    print(f"  valid: {preview['valid_rows']}")
    print(f"  errors: {preview['error_rows']}")
    print(f"  payments_to_create: {preview['payments_to_create']}")

    for l in preview['lines']:
        print(f"  Row {l['source_row']}: lic={l['licencia']} status={l['status']} actions={l['deduced_actions']} errors={l['errors']}")

    # Now test apply — this is where the bug was
    result = unified_apply(db, rows)
    print(f"\nApply:")
    print(f"  applied: {result['applied']}")
    print(f"  skipped: {result['skipped']}")
    print(f"  errors: {result.get('errors', 0)}")
    for d in result['details'][:10]:
        print(f"  Row {d['source_row']}: {d['status']} - {d.get('what_happened') or d.get('reason')}")

    # Verify: some rows should have been applied
    if result['applied'] > 0:
        print("\n[OK] Apply works with partial data")
    else:
        print(f"\n[FAIL] No rows applied! applied={result['applied']} skipped={result['skipped']}")

finally:
    db.rollback()  # Don't persist test data
    db.close()
