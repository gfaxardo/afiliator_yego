"""
Auditoria post-commit de carga historica.
Verifica todas las condiciones GO/NO GO contra la DB.
Read-only. No modifica nada.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
errors = []

def run(label, sql, expected=None, silent=False):
    """Run query and print result. Optionally check against expected value."""
    rows = db.execute(text(sql)).fetchall()
    if rows and len(rows[0]) == 1:
        val = rows[0][0]
    else:
        val = rows
    if not silent:
        if expected is not None:
            mark = "OK" if val == expected else "DESVIADO"
            print(f"  {mark}: {label} = {val} (esperado {expected})")
        else:
            print(f"  {label} = {val}")
    if expected is not None and val != expected:
        errors.append(f"{label}: {val} != {expected}")
    return val

print("=" * 70)
print("AUDITORIA POST-COMMIT - CARGA HISTORICA")
print("=" * 70)

# ── 1. Total paid_history ──
print("\n--- 1. TOTAL PAID_HISTORY (historical_upload) ---")
total_ph = run("total", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
""")
total_amt = run("monto_total", """
    SELECT COALESCE(SUM(amount_paid),0) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
""")
# Expected: 1 (batch_id=2) + 245 (new commit) = 246
print(f"  (1 preexistente + ~245 nuevos)")

# ── 2. Por import_batch_id ──
print("\n--- 2. DESGLOSE POR import_batch_id ---")
rows = db.execute(text("""
    SELECT import_batch_id, COUNT(*), COALESCE(SUM(amount_paid),0)
    FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
    GROUP BY import_batch_id
    ORDER BY import_batch_id
""")).fetchall()
for r in rows:
    print(f"  batch_id={r[0]}: {r[1]} rows, S/ {r[2]}")
    if r[0] is None:
        errors.append(f"Hay {r[1]} registros con import_batch_id=NULL")

# ── 3. blocks_future_payment=true CON driver_id ──
print("\n--- 3. BLOQUEABLES VALIDOS (blocks=true + driver_id NOT NULL) ---")
blk_true_with_driver = run("count", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = true
      AND driver_id IS NOT NULL
""")
blk_true_amt = run("monto", """
    SELECT COALESCE(SUM(amount_paid),0) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = true
      AND driver_id IS NOT NULL
""")
# Expected: 72 (new) + 1 (batch_id=2) = 73? Or maybe batch_id=2 has blocks=true too?
# Let me check individually
blk_new_only = run("  de los cuales, con import_batch_id IS NOT NULL (nuevos):", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = true
      AND driver_id IS NOT NULL
      AND import_batch_id IS NOT NULL
""")
run("  batch_id=2 con blocks=true + driver:", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_batch_id = 2
      AND blocks_future_payment = true
      AND driver_id IS NOT NULL
""", silent=True)

# ── 4. blocks_future_payment=false (financieros no bloqueables) ──
print("\n--- 4. FINANCIEROS NO BLOQUEABLES (blocks=false) ---")
blk_false_count = run("count", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = false
""")
blk_false_amt = run("monto", """
    SELECT COALESCE(SUM(amount_paid),0) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = false
""")

# ── 5. CRITICO: blocks=true SIN driver_id ──
print("\n--- 5. CRITICO: blocks=true SIN driver_id (DEBE SER 0) ---")
bad_blocks = run("count", """
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = true
      AND driver_id IS NULL
""")
if bad_blocks != 0:
    errors.append(f"CRITICO: {bad_blocks} registros con blocks=true y driver_id=NULL")

# ── 6. Duplicados por unique_hash ──
print("\n--- 6. DUPLICADOS POR unique_hash (DEBE SER 0) ---")
dup_hashes = db.execute(text("""
    SELECT unique_hash, COUNT(*) as cnt
    FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND unique_hash IS NOT NULL
    GROUP BY unique_hash
    HAVING COUNT(*) > 1
""")).fetchall()
dup_count = len(dup_hashes)
print(f"  count = {dup_count}")
if dup_count > 0:
    for d in dup_hashes[:5]:
        print(f"    hash={d[0][:32]}... count={d[1]}")
    errors.append(f"CRITICO: {dup_count} unique_hash duplicados")

# Tambien verificar por driver_id+amount
print("\n--- 6b. DUPLICADOS POR driver_id+amount (blocks=true) ---")
dup_did = db.execute(text("""
    SELECT driver_id, amount_paid, COUNT(*) as cnt
    FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
      AND blocks_future_payment = true
      AND driver_id IS NOT NULL
    GROUP BY driver_id, amount_paid
    HAVING COUNT(*) > 1
""")).fetchall()
dup_did_count = len(dup_did)
print(f"  count = {dup_did_count}")
if dup_did_count > 0:
    for d in dup_did[:5]:
        print(f"    driver={d[0][:20]} amt={d[1]} count={d[2]}")
    errors.append(f"CRITICO: {dup_did_count} driver_id+amount duplicados con blocks=true")

# ── 7. Atribuciones historicas ──
print("\n--- 7. ATRIBUCIONES HISTORICAS ---")
attr_count = run("total", """
    SELECT COUNT(*) FROM scout_liq_historical_attributions
""")
attr_by_status = db.execute(text("""
    SELECT import_status, COUNT(*) 
    FROM scout_liq_historical_attributions 
    GROUP BY import_status 
    ORDER BY COUNT(*) DESC
""")).fetchall()
for r in attr_by_status:
    print(f"  {r[0]}: {r[1]}")

# ── 8. Driver assignments ──
print("\n--- 8. DRIVER ASSIGNMENTS (historical_upload + workbook_import) ---")
assn_count = run("total", """
    SELECT COUNT(*) FROM scout_liq_driver_assignments
    WHERE assigned_by IN ('historical_upload', 'workbook_import')
""")
assn_by = db.execute(text("""
    SELECT assigned_by, COUNT(*) 
    FROM scout_liq_driver_assignments 
    WHERE assigned_by IN ('historical_upload', 'workbook_import')
    GROUP BY assigned_by
""")).fetchall()
for r in assn_by:
    print(f"  {r[0]}: {r[1]}")

# ── 9. HistoricalImportLine resumen ──
print("\n--- 9. HISTORICAL IMPORT LINES (ultimo batch) ---")
last_batch = db.execute(text("""
    SELECT id, status, imported_count, rejected_count, manual_review_count, 
           duplicate_count, amount_imported, total_rows
    FROM scout_liq_historical_import_batches
    ORDER BY id DESC LIMIT 1
""")).fetchone()
if last_batch:
    print(f"  batch_id={last_batch[0]} status={last_batch[1]}")
    print(f"  imported={last_batch[2]} rejected={last_batch[3]} review={last_batch[4]} duplicates={last_batch[5]}")
    print(f"  amount_imported={last_batch[6]} total_rows={last_batch[7]}")

    # Lines summary
    line_stats = db.execute(text(f"""
        SELECT final_status, COUNT(*)
        FROM scout_liq_historical_import_lines
        WHERE batch_id = {last_batch[0]}
        GROUP BY final_status
        ORDER BY COUNT(*) DESC
    """)).fetchall()
    print(f"  Lines by final_status:")
    for r in line_stats:
        print(f"    {r[0]}: {r[1]}")

    # Check paid_history_id linkage
    lines_with_ph = db.execute(text(f"""
        SELECT COUNT(*) FROM scout_liq_historical_import_lines
        WHERE batch_id = {last_batch[0]} AND paid_history_id IS NOT NULL
    """)).scalar()
    print(f"  Lines with paid_history_id: {lines_with_ph}")

    # Check blocks_future_payment on lines
    line_blk = db.execute(text(f"""
        SELECT blocks_future_payment, COUNT(*)
        FROM scout_liq_historical_import_lines
        WHERE batch_id = {last_batch[0]} AND blocks_future_payment IS NOT NULL
        GROUP BY blocks_future_payment
    """)).fetchall()
    print(f"  Lines by blocks_future_payment:")
    for r in line_blk:
        print(f"    {r[0]}: {r[1]}")

print("\n--- 10. CONFIRMACION import_batch_id=2 INTACTO ---")
b2_count = db.execute(text("""
    SELECT COUNT(*), COALESCE(SUM(amount_paid),0) 
    FROM scout_liq_paid_history WHERE import_batch_id = 2
""")).fetchone()
print(f"  batch_id=2: {b2_count[0]} registros, S/ {b2_count[1]}")

# ── 11. Resolucion status ──
print("\n--- 11. RESOLUTION STATUS ---")
res_stats = db.execute(text("""
    SELECT resolution_status, COUNT(*), COALESCE(SUM(amount_paid),0)
    FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
    GROUP BY resolution_status
    ORDER BY COUNT(*) DESC
""")).fetchall()
for r in res_stats:
    print(f"  {r[0]}: {r[1]} rows, S/ {r[2]}")

# ── 12. financial_record_status ──
print("\n--- 12. FINANCIAL RECORD STATUS ---")
fin_stats = db.execute(text("""
    SELECT financial_record_status, COUNT(*), COALESCE(SUM(amount_paid),0)
    FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload'
    GROUP BY financial_record_status
    ORDER BY COUNT(*) DESC
""")).fetchall()
for r in fin_stats:
    print(f"  {r[0]}: {r[1]} rows, S/ {r[2]}")

# ── DICTAMEN ──
print("\n" + "=" * 70)
print("DICTAMEN FINAL")
print("=" * 70)

# Calculate expected totals
new_ph_created = total_ph - 1  # subtract batch_id=2 pre-existing
new_amount = total_amt - 150  # subtract batch_id=2 S/150

print(f"\n  Registros nuevos creados: {new_ph_created}")
print(f"  Monto nuevo: S/ {new_amount}")
print(f"  blocks=true con driver: {blk_true_with_driver}")
print(f"  blocks=false: {blk_false_count}")
print(f"  blocks=true SIN driver: {bad_blocks}")
print(f"  unique_hash duplicados: {dup_count}")
print(f"  Atribuciones historicas: {attr_count}")
print(f"  Assignments: {assn_count}")

# Validate
checks = []
checks.append(("245 pagos nuevos", 240 <= new_ph_created <= 250))
checks.append(("blocks=true con driver >= 72", blk_true_with_driver >= 72))
checks.append(("blocks=true SIN driver = 0", bad_blocks == 0))
checks.append(("unique_hash dups = 0", dup_count == 0))
checks.append(("driver_id+amount dups = 0", dup_did_count == 0))
checks.append(("batch_id=2 intacto", b2_count[0] == 1))
checks.append(("no batch_id=NULL nuevos", db.execute(text("""
    SELECT COUNT(*) FROM scout_liq_paid_history
    WHERE import_source = 'historical_upload' AND import_batch_id IS NULL
""")).scalar() == 0))

all_ok = True
for label, ok in checks:
    mark = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {mark}: {label}")

print()
if errors:
    print(f"ESTADO: NO GO - {len(errors)} errores")
    for e in errors:
        print(f"  - {e}")
elif not all_ok:
    print("ESTADO: GO CON OBSERVACIONES")
else:
    print("ESTADO: GO")
    print("  Todos los checks pasaron.")
    print("  Carga historica validada correctamente.")
    print("  Se puede cerrar la carga historica.")

db.close()
