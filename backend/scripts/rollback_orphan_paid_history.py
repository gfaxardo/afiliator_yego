"""
Backup + Rollback controlado de registros huerfanos en scout_liq_paid_history.

      - Guarda CSV de respaldo en backups/
      - Valida conteo exacto = 72 antes de borrar
      - Ejecuta DELETE dentro de transaccion
      - Verifica post-condiciones (0 huerfanos, batch_id=2 intacto)
      - Aborta si algo no cuadra

Uso: python scripts/rollback_orphan_paid_history.py [--dry-run]
      --dry-run: solo verifica y genera backup, NO borra
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from sqlalchemy import text

DRY_RUN = "--dry-run" in sys.argv

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_FILE = os.path.join(BACKUP_DIR, f"backup_orphan_paid_history_{timestamp}.csv")

ORPHAN_CONDITION = """
    import_source = 'historical_upload'
    AND import_batch_id IS NULL
    AND resolution_status IS NULL
    AND blocks_future_payment = true
    AND driver_id IS NOT NULL
"""

COLUMNS = [
    "id", "import_batch_id", "scout_id", "driver_id", "driver_license_raw",
    "scout_name_raw", "amount_paid", "currency", "import_source",
    "source_file", "source_sheet", "source_row", "payment_rule",
    "payment_component", "resolution_status", "blocks_future_payment",
    "financial_record_status", "unique_hash", "status", "paid_at", "created_at"
]

db = SessionLocal()
try:
    print("=" * 60)
    print("ROLLBACK ORPHAN PAID HISTORY")
    if DRY_RUN:
        print("MODO: DRY-RUN (no se borrara nada)")
    print("=" * 60)

    # ── 1. COUNT ──
    count_sql = f"SELECT COUNT(*) FROM scout_liq_paid_history WHERE {ORPHAN_CONDITION}"
    count = db.execute(text(count_sql)).scalar()
    amount_sql = f"SELECT COALESCE(SUM(amount_paid),0) FROM scout_liq_paid_history WHERE {ORPHAN_CONDITION}"
    total_amount = db.execute(text(amount_sql)).scalar()

    print(f"\n  Huerfanos encontrados: {count}")
    print(f"  Monto total: S/ {total_amount}")

    if count != 72:
        print(f"\n  *** CRITICO: Se esperaban 72, hay {count}. ABORTADO. ***")
        db.close()
        sys.exit(1)

    # ── 2. BACKUP CSV ──
    print(f"\n  Creando backup: {BACKUP_FILE}")
    rows = db.execute(text(
        f"SELECT {', '.join(COLUMNS)} FROM scout_liq_paid_history WHERE {ORPHAN_CONDITION} ORDER BY id"
    )).fetchall()

    with open(BACKUP_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([str(v) if v is not None else "" for v in row])

    file_size = os.path.getsize(BACKUP_FILE)
    print(f"  Backup guardado: {os.path.basename(BACKUP_FILE)} ({file_size} bytes, {len(rows)} filas)")

    if len(rows) != 72:
        print(f"  *** CRITICO: Backup tiene {len(rows)} filas, esperadas 72. ABORTADO. ***")
        db.close()
        sys.exit(1)

    # ── 3. Pre-DELETE checks ──
    batch2 = db.execute(text(
        "SELECT COUNT(*) FROM scout_liq_paid_history WHERE import_batch_id = 2"
    )).scalar()
    print(f"\n  batch_id=2 antes de borrar: {batch2} registros")

    if batch2 != 1:
        print(f"  *** CRITICO: batch_id=2 deberia ser 1, es {batch2}. ABORTADO. ***")
        db.close()
        sys.exit(1)

    total_before = db.execute(text(
        "SELECT COUNT(*) FROM scout_liq_paid_history WHERE import_source = 'historical_upload'"
    )).scalar()
    print(f"  Total historical_upload antes: {total_before}")

    if DRY_RUN:
        print(f"\n  DRY-RUN: NO se ejecuto DELETE. Backup creado en {BACKUP_FILE}")
        db.close()
        sys.exit(0)

    # ── 4. DELETE ──
    print(f"\n  Ejecutando DELETE...")
    db.execute(text("BEGIN"))
    result = db.execute(text(f"DELETE FROM scout_liq_paid_history WHERE {ORPHAN_CONDITION}"))
    rows_deleted = result.rowcount

    # ── 5. Post-DELETE verification ──
    orphans_after = db.execute(text(
        f"SELECT COUNT(*) FROM scout_liq_paid_history WHERE {ORPHAN_CONDITION}"
    )).scalar()
    batch2_after = db.execute(text(
        "SELECT COUNT(*) FROM scout_liq_paid_history WHERE import_batch_id = 2"
    )).scalar()
    total_after = db.execute(text(
        "SELECT COUNT(*) FROM scout_liq_paid_history WHERE import_source = 'historical_upload'"
    )).scalar()

    print(f"\n  Post-DELETE:")
    print(f"  Huerfanos restantes: {orphans_after}")
    print(f"  batch_id=2: {batch2_after}")
    print(f"  Total historical_upload: {total_after}")

    errors = []
    if orphans_after != 0:
        errors.append(f"Huerfanos restantes = {orphans_after}, esperado 0")
    if batch2_after != 1:
        errors.append(f"batch_id=2 = {batch2_after}, esperado 1")
    if total_before - total_after != 72:
        errors.append(f"Se esperaba borrar 72, diferencia real = {total_before - total_after}")

    if errors:
        print("\n  *** ERRORES EN POST-VERIFICACION ***")
        for e in errors:
            print(f"    - {e}")
        print("  Ejecutando ROLLBACK...")
        db.execute(text("ROLLBACK"))
        db.close()
        sys.exit(1)

    db.execute(text("COMMIT"))
    print(f"\n  COMMIT exitoso.")
    print(f"  Registros eliminados: 72")
    print(f"  Backup: {BACKUP_FILE}")
    print(f"  batch_id=2 intacto: SI ({batch2_after} registro)")
    print(f"\n  LISTO. Ahora ejecutar:")
    print(f'  python scripts/audit_financial_blocking_rules.py "RUTA_XLSX" "01_PAGOS_HISTORICOS"')

finally:
    try:
        db.close()
    except Exception:
        pass
