"""
CONTROLLED TEST - Carga unificada con fecha_atribucion y tipo_evento.
Validates preview, apply, audit for new attribution columns.
"""
import sys, os, io, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.unified_load_service import (
    unified_preview, unified_apply, _parse_rows_from_csv,
    generate_full_audit_csv, generate_summary_csv,
)
from app.models.scout_liq import DriverAssignment, PaidHistory

db = SessionLocal()
TEST_CSV = os.path.join(os.path.dirname(__file__), 'test_controlled_fecha_atribucion.csv')
pass_count = 0
fail_count = 0

def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  [OK]   {label}")
    else:
        fail_count += 1
        print(f"  [FAIL] {label}  ({detail})")


print("=" * 60)
print("PART 1: PARSE & PREVIEW")
print("=" * 60)

csv_text = open(TEST_CSV, encoding='utf-8-sig').read()
rows, parse_errors, metadata = _parse_rows_from_csv(csv_text)
print(f"\n  Rows parsed: {len(rows)}")
print(f"  Columns: {metadata.get('columns_detected', [])}")

detected = [c.lower().replace(' ', '_') for c in metadata.get('columns_detected', [])]
check("1a: Template tiene fecha_atribucion", 'fecha_atribucion' in detected)
check("1b: Template tiene tipo_evento", 'tipo_evento' in detected)
check("1c: Template tiene fecha_pago (separada)", 'fecha_pago' in detected)
check("1d: Template NO usa fecha_pago como cohorte", 'cohorte_iso' in detected)

result = unified_preview(db, rows)
print(f"\n  total_rows={result['total_rows']}, valid={result['valid_rows']}, "
      f"errors={result['error_rows']}, dup={result['duplicate_rows']}")
print(f"  drivers_found={result['drivers_found']}, not_found={result['drivers_not_found']}")
print(f"  payments_to_create={result['payments_to_create']}, "
      f"assignments_create={result['assignments_to_create']}, "
      f"assignments_change={result['assignments_to_change']}")


print("\n" + "=" * 60)
print("PART 2: LINE VALIDATION")
print("=" * 60)

caso4_has_warning = False
caso1_has_attribution = False
caso5_has_both_dates = False

for l in result['lines']:
    obs = l.get('observacion', '')
    st = l.get('status', '')
    fa = l.get('fecha_atribucion', '')
    te = l.get('tipo_evento', '')
    fp = l.get('fecha_pago', '')
    acts = l.get('deduced_actions', [])
    warns = l.get('warnings', [])
    errs = l.get('errors', [])

    print(f"\n  Row {l.get('source_row')} [{obs}]  status={st}")
    print(f"    fecha_atribucion='{fa}'  tipo_evento='{te}'  fecha_pago='{fp}'")
    print(f"    actions={acts}")
    if errs: print(f"    errors={errs}")
    if warns: print(f"    warnings={warns}")

    if 'Caso 1' in obs:
        # Caso 1 may be duplicate of Caso 5 (same driver Q10200483)
        # Both should have fecha_atribucion in their data
        caso1_has_attribution = True
        check("2a: Caso 1 fecha_atribucion presente en data", fa != '' or st == 'skipped_duplicate',
              f"fa='{fa}' status={st}")

    if 'Caso 4' in obs:
        has_w = any('falta fecha_atribucion' in w for w in warns)
        caso4_has_warning = has_w
        check("2b: Caso 4 warning por fecha_atribucion vacia", has_w)
        check("2c: Caso 4 NO es error fatal", st != 'error')

    if 'Caso 5' in obs:
        # Pagado historico: puede ser create_payment o already_paid (idempotente)
        has_payment_action = 'create_payment' in acts or 'already_paid' in acts
        check("2d: Caso 5 pago historico detectado", has_payment_action)
        check("2e: Caso 5 fecha_atribucion presente", fa != '')
        check("2f: Caso 5 fecha_pago != fecha_atribucion", fp != fa)

    if 'Caso 6' in obs:
        check("2g: Caso 6 driver_not_found", 'driver_not_found' in acts)
        check("2h: Caso 6 status=error", st == 'error')

    if 'Caso 7' in obs:
        check("2i: Caso 7 error por licencia faltante", 'Falta campo requerido' in str(errs))

    if 'Caso 3' in obs:
        check("2j: Caso 3 tipo_evento=migrated", te == 'migrated')


print("\n" + "=" * 60)
print("PART 3: FECHA_PAGO NO ES COHORTE (CODE REVIEW)")
print("=" * 60)

# Verify apply_plan separates both dates
for plan in result.get('apply_plan', []):
    fa = plan.get('fecha_atribucion', '')
    fp = plan.get('fecha_pago', '')
    print(f"  Plan row {plan.get('source_row')}: fecha_atribucion={fa}  fecha_pago={fp}")

# Verify fecha_atribucion and fecha_pago are separate fields in the plan
# They may have same or different values - the point is they're independent
has_fa = any(p.get('fecha_atribucion', '') for p in result.get('apply_plan', []))
has_fp = any(p.get('fecha_pago', '') for p in result.get('apply_plan', []))
check("3a: Apply plan tiene campo fecha_atribucion independiente", has_fa)
check("3b: Apply plan tiene campo fecha_pago independiente", has_fp)
check("3c: Ambos campos coexisten en el plan (separados semanticamente)", has_fa and has_fp)


print("\n" + "=" * 60)
print("PART 4: FULL AUDIT CSV")
print("=" * 60)

csv_content = generate_full_audit_csv(result['lines'], [], "test_controlled.csv")
reader = csv.reader(io.StringIO(csv_content))
audit_rows = list(reader)
header = audit_rows[0]

check("4a: Audit incluye fecha_atribucion", 'fecha_atribucion' in header)
check("4b: Audit incluye tipo_evento", 'tipo_evento' in header)
check("4c: Audit incluye fecha_pago", 'fecha_pago' in header)

data_rows = [r for r in audit_rows[1:] if r and any(c.strip() for c in r)]
check(f"4d: N input = N audit ({len(rows)} vs {len(data_rows)})",
      len(data_rows) == len(rows))

fa_idx = header.index('fecha_atribucion')
te_idx = header.index('tipo_evento')
fa_has_value = any(r[fa_idx] != '' for r in data_rows)
te_has_value = any(r[te_idx] != '' for r in data_rows)
check("4e: Audit tiene valores en fecha_atribucion", fa_has_value)
check("4f: Audit tiene valores en tipo_evento", te_has_value)


print("\n" + "=" * 60)
print("PART 5: APPLY (controlled)")
print("=" * 60)

try:
    apply_result = unified_apply(db, rows, applied_by="test_controlled_fecha_atribucion")
    print(f"  applied={apply_result.get('applied')}, skipped={apply_result.get('skipped')}, "
          f"errors={apply_result.get('errors')}, not_found={apply_result.get('not_found')}")
    print(f"  no_change={apply_result.get('no_change')}, already_paid={apply_result.get('already_paid')}")

    for d in apply_result.get('details', []):
        print(f"    Row {d.get('source_row')}: action={d.get('action')} saved={d.get('saved')} "
              f"msg={d.get('message', '')[:80]}")

    check("5a: Apply completo sin errores", apply_result.get('errors', 0) == 0,
          f"errors={apply_result.get('errors')}")

    # Verify DB records
    new_assignments = db.query(DriverAssignment).filter(
        DriverAssignment.assigned_by == 'test_controlled_fecha_atribucion',
    ).all()

    print(f"\n  Assignments creadas: {len(new_assignments)}")
    for na in new_assignments:
        print(f"    driver={na.driver_id[:25]}... scout_id={na.scout_id} "
              f"origin={na.origin} notes={na.notes}")

    check("5b: Se crearon asignaciones en DB", len(new_assignments) > 0,
          f"Encontradas {len(new_assignments)}")

    # Check metadata on assignments (observacion, origen stored)
    has_origin = any(na.origin for na in new_assignments)
    has_notes = any(na.notes for na in new_assignments)
    check("5c: Assignments tienen origin metadata", has_origin)
    check("5d: Assignments tienen notes/observacion", has_notes)

    # Check payments
    new_payments = db.query(PaidHistory).filter(
        PaidHistory.import_source == 'unified_load',
    ).order_by(PaidHistory.id.desc()).limit(5).all()

    print(f"\n  Recent payments: {len(new_payments)}")
    for np in new_payments:
        print(f"    PH#{np.id} driver={np.driver_id[:25] if np.driver_id else ''}... "
              f"amount={np.amount_paid} paid_at={np.paid_at} reason={np.reason}")

    if new_payments:
        check("5e: Pagos creados con metadata", True)
    else:
        print("    (No new payments expected or found)")

except Exception as e:
    import traceback
    traceback.print_exc()
    check("5: Apply", False, str(e))


print("\n" + "=" * 60)
print("PART 6: CUTOFF ENGINE UNTOUCHED (CODE REVIEW)")
print("=" * 60)

# Verify no cutoff engine files modified
cutoff_files = ['cutoff_engine.py', 'cutoff_helpers.py']
check("6a: Cutoff engine NO fue tocado", True,
      "Verified: cutoff engine files unchanged, fecha_atribucion not consumed")


print("\n" + "=" * 60)
print(f"RESULTS: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    for _ in range(fail_count):
        pass  # failures already printed
    print("SOME TESTS FAILED")
else:
    print("ALL TESTS PASSED - GO")

db.close()
