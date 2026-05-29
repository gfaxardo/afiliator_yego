"""Test hardened unified load rules: driver_not_found = error, no puede crear pago."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.unified_load_service import unified_preview, unified_apply, _parse_rows_from_csv

db = SessionLocal()
try:
    csv_text = open(os.path.join(os.path.dirname(__file__), 'test_unified.csv'), encoding='utf-8-sig').read()
    rows, errors, _ = _parse_rows_from_csv(csv_text)
    print(f"Parsed {len(rows)} rows")

    result = unified_preview(db, rows)

    print()
    print("=== PREVIEW ===")
    for k, v in result.items():
        if k != 'lines':
            print(f"  {k}: {v}")

    print()
    print("=== LINEAS ===")
    all_ok = True
    for l in result['lines']:
        src = l.get('source_row', 0)
        lic = l.get('licencia', '')
        st = l.get('status', '')
        drv = l.get('driver_id_resolved', '')
        acts = l.get('deduced_actions', [])
        errs = l.get('errors', [])
        warns = l.get('warnings', [])

        print(f"  Row {src}: lic={lic} status={st} driver={drv}")
        print(f"         actions={acts}")
        if errs:
            print(f"         ERRORS={errs}")
        if warns:
            print(f"         warnings={warns}")

        # Validaciones
        if lic == 'Q45406817':
            # Debe tener driver resuelto y create_payment
            if st == 'error':
                print(f"  [FAIL] Q45406817 deberia ser OK, tiene status=error")
                all_ok = False
            if 'create_payment' not in acts:
                print(f"  [FAIL] Q45406817 deberia tener create_payment")
                all_ok = False
            if not drv:
                print(f"  [FAIL] Q45406817 deberia tener driver_id resuelto")
                all_ok = False

        if lic == 'Q99999999':
            # NO debe tener create_payment, debe ser error
            if 'create_payment' in acts:
                print(f"  [FAIL] Q99999999 NO debe tener create_payment (driver no encontrado)")
                all_ok = False
            if st != 'error':
                print(f"  [FAIL] Q99999999 debe ser status=error (driver no encontrado)")
                all_ok = False
            if 'driver_not_found' not in acts:
                print(f"  [FAIL] Q99999999 debe tener driver_not_found")
                all_ok = False

        if lic == 'Q12345678':
            # NO debe tener attribution_only, debe ser error
            if 'attribution_only' in acts:
                print(f"  [FAIL] Q12345678 NO debe tener attribution_only (driver no encontrado)")
                all_ok = False
            if st != 'error':
                print(f"  [FAIL] Q12345678 debe ser status=error (driver no encontrado)")
                all_ok = False
            if 'driver_not_found' not in acts:
                print(f"  [FAIL] Q12345678 debe tener driver_not_found")
                all_ok = False

        if lic == '':
            # Debe ser error por falta de licencia
            if st != 'error':
                print(f"  [FAIL] Row sin licencia debe ser error")
                all_ok = False

    print()
    print(f"  payments_to_create={result['payments_to_create']} (debe ser 1, solo Q45406817)")
    if result['payments_to_create'] != 1:
        print(f"  [FAIL] payments_to_create={result['payments_to_create']}, esperado=1")
        all_ok = False

    print(f"  error_rows={result['error_rows']} (debe ser 3: Q99999999, Q12345678, row sin licencia)")
    if result['error_rows'] != 3:
        print(f"  [FAIL] error_rows={result['error_rows']}, esperado=3")
        all_ok = False

    print(f"  valid_rows={result['valid_rows']} (debe ser 1: solo Q45406817)")
    if result['valid_rows'] != 1:
        print(f"  [FAIL] valid_rows={result['valid_rows']}, esperado=1")
        all_ok = False

    print()
    if all_ok:
        print("[GO] Reglas duras validadas correctamente")
    else:
        print("[NO-GO] Hay fallos en las reglas duras")

except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
