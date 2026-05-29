"""
FASE 0 — BACKUP Y LIMPIEZA DE DATOS DE PRUEBA SCOUT LIQ.

Objetivo: eliminar datos de prueba identificables sin tocar datos reales.
Antes de ejecutar: el usuario debe aprobar los conteos mostrados.
"""
import sys, os, csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import SessionLocal

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
DRY_RUN = "--dry-run" in sys.argv
EXECUTE = "--execute" in sys.argv

# ═══════════════════════════════════════════════════════════
# STEP 0: backups directory
# ═══════════════════════════════════════════════════════════
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"BACKUP DIR: {BACKUP_DIR}")
print(f"DRY RUN: {DRY_RUN}")
print(f"EXECUTE: {EXECUTE}")
print()

db = SessionLocal()

try:
    # ═══════════════════════════════════════════════════════
    # STEP 1: COUNTS BEFORE
    # ═══════════════════════════════════════════════════════
    tables = [
        "scout_liq_scouts",
        "scout_liq_driver_assignments",
        "scout_liq_cutoff_runs",
        "scout_liq_cutoff_scout_summary",
        "scout_liq_cutoff_driver_lines",
        "scout_liq_paid_history",
        "scout_liq_historical_import_batches",
        "scout_liq_historical_import_lines",
        "scout_liq_historical_attributions",
        "scout_liq_manual_overrides",
        "scout_liq_payment_schemes",
        "scout_liq_payment_scheme_versions",
        "scout_liq_payment_scheme_tiers",
        "scout_liq_conversion_schemes",
        "scout_liq_conversion_tiers",
        "scout_liq_manual_payments",
        "scout_liq_supervisor_commissions",
        "scout_liq_scout_bonuses",
        "scout_liq_scheme_versions",
        "scout_liq_scheme_change_log",
        "scout_liq_refresh_registry",
        "scout_liq_health_events",
    ]

    counts_before = {}
    print("=== COUNTS BEFORE ===")
    for t in tables:
        c = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        counts_before[t] = c
        print(f"  {t:50s} {c:>6d}")

    if DRY_RUN:
        print("\nDRY RUN mode. No changes made. Use --execute to apply.")
        sys.exit(0)

    # ═══════════════════════════════════════════════════════
    # STEP 2: BACKUP each table to CSV
    # ═══════════════════════════════════════════════════════
    print("\n=== BACKUP ===")
    for t in tables:
        c = counts_before[t]
        if c == 0:
            print(f"  SKIP {t} (empty)")
            continue
        rows = db.execute(text(f"SELECT * FROM {t}")).fetchall()
        cols = db.execute(text(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{t}' ORDER BY ordinal_position"
        )).fetchall()
        col_names = [r[0] for r in cols]
        fpath = os.path.join(BACKUP_DIR, f"{t}_{ts}.csv")
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(col_names)
            w.writerows(rows)
        print(f"  OK  {t} -> {fpath} ({c} rows)")

    # ═══════════════════════════════════════════════════════
    # STEP 3: IDENTIFY TEST DATA
    # ═══════════════════════════════════════════════════════
    print("\n=== TEST DATA IDENTIFICATION ===")

    # --- Test cutoff run IDs ---
    test_cutoff_ids = db.execute(text(
        "SELECT id FROM scout_liq_cutoff_runs "
        "WHERE cutoff_name ILIKE '%test%' "
        "   OR cutoff_name ILIKE '%qa%' "
        "   OR cutoff_name ILIKE '%dev%' "
        "   OR cutoff_name ILIKE '%mvp%' "
        "   OR cutoff_name ILIKE '%f3%' "
        "   OR notes ILIKE '%integration test%' "
        "   OR cutoff_name LIKE 'Legacy%' "
        "   OR cutoff_name LIKE 'Pago DEV%'"
    )).fetchall()
    test_cutoff_ids = [r[0] for r in test_cutoff_ids]
    print(f"  Test cutoff_run IDs: {test_cutoff_ids}")

    # --- Test scout IDs ---
    test_scout_ids = db.execute(text(
        "SELECT id FROM scout_liq_scouts "
        "WHERE scout_name ILIKE '%test%' "
        "   OR scout_name ILIKE '%scout a%' "
        "   OR scout_name ILIKE '%scout unificado%' "
        "   OR scout_name ILIKE '%scout validacion%' "
        "   OR scout_name ILIKE '%mvp%'"
    )).fetchall()
    test_scout_ids = [r[0] for r in test_scout_ids]
    print(f"  Test scout IDs: {test_scout_ids}")

    # --- Test import batch IDs ---
    test_batch_ids = db.execute(text(
        "SELECT id FROM scout_liq_historical_import_batches "
        "WHERE source_file ILIKE '%test%' "
        "   OR source_file ILIKE '%prueba%' "
        "   OR source_file ILIKE '%p.xlsx%' "
        "   OR source_file ILIKE '%PRUEBA%'"
    )).fetchall()
    test_batch_ids = [r[0] for r in test_batch_ids]
    print(f"  Test import_batch IDs: {test_batch_ids}")

    if not EXECUTE:
        print("\nNo --execute flag. Dry run complete. Add --execute to apply cleanup.")
        sys.exit(0)

    # ═══════════════════════════════════════════════════════
    # STEP 4: EXECUTE CLEANUP (with WHERE explicit)
    # ═══════════════════════════════════════════════════════
    print("\n=== EXECUTING CLEANUP ===")

    # 4a. Delete driver lines linked to test cutoffs
    if test_cutoff_ids:
        placeholders = ",".join(str(x) for x in test_cutoff_ids)
        sql = f"DELETE FROM scout_liq_cutoff_driver_lines WHERE cutoff_run_id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE cutoff_driver_lines WHERE cutoff_run_id IN ({placeholders}): {r.rowcount} rows")

    # 4b. Delete scout summaries linked to test cutoffs
    if test_cutoff_ids:
        placeholders = ",".join(str(x) for x in test_cutoff_ids)
        sql = f"DELETE FROM scout_liq_cutoff_scout_summary WHERE cutoff_run_id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE cutoff_scout_summary WHERE cutoff_run_id IN ({placeholders}): {r.rowcount} rows")

    # 4c. Delete paid_history linked to test cutoffs OR unified_load
    if test_cutoff_ids:
        placeholders = ",".join(str(x) for x in test_cutoff_ids)
        sql = f"DELETE FROM scout_liq_paid_history WHERE cutoff_run_id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE paid_history WHERE cutoff_run_id IN ({placeholders}): {r.rowcount} rows")

    r = db.execute(text(
        "DELETE FROM scout_liq_paid_history WHERE import_source = 'unified_load'"
    ))
    print(f"  DELETE paid_history WHERE import_source='unified_load': {r.rowcount} rows")

    # 4d. Delete test cutoff runs
    if test_cutoff_ids:
        placeholders = ",".join(str(x) for x in test_cutoff_ids)
        sql = f"DELETE FROM scout_liq_cutoff_runs WHERE id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE cutoff_runs WHERE id IN ({placeholders}): {r.rowcount} rows")

    # 4e. Delete assignments with test source files (NOT linked to test scouts - those handled in 4f)
    r = db.execute(text(
        "DELETE FROM scout_liq_driver_assignments WHERE source_file ILIKE '%PRUEBA%'"
    ))
    print(f"  DELETE assignments WHERE source_file ILIKE '%PRUEBA%': {r.rowcount} rows")

    r = db.execute(text(
        "DELETE FROM scout_liq_driver_assignments WHERE source_file = 'unified_load.csv'"
    ))
    print(f"  DELETE assignments WHERE source_file='unified_load.csv': {r.rowcount} rows")

    r = db.execute(text(
        "DELETE FROM scout_liq_driver_assignments WHERE source_file = 'test_attr.xlsx'"
    ))
    print(f"  DELETE assignments WHERE source_file='test_attr.xlsx': {r.rowcount} rows")

    # 4f. DELETE rows referencing test scouts (before deleting scouts themselves)
    if test_scout_ids:
        placeholders = ",".join(str(x) for x in test_scout_ids)
        for child_table in [
            "scout_liq_cutoff_driver_lines",
            "scout_liq_cutoff_scout_summary",
            "scout_liq_paid_history",
            "scout_liq_driver_assignments",
            "scout_liq_manual_payments",
            "scout_liq_scout_bonuses",
        ]:
            sql = f"DELETE FROM {child_table} WHERE scout_id IN ({placeholders})"
            r = db.execute(text(sql))
            print(f"  DELETE {child_table} WHERE scout_id IN ({placeholders}): {r.rowcount} rows")

        # Now safe to delete test scouts
        sql = f"DELETE FROM scout_liq_scouts WHERE id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE scouts WHERE id IN ({placeholders}): {r.rowcount} rows")

    # 4g. Delete historical import lines linked to test batches
    if test_batch_ids:
        placeholders = ",".join(str(x) for x in test_batch_ids)
        sql = f"DELETE FROM scout_liq_historical_import_lines WHERE batch_id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE historical_import_lines WHERE batch_id IN ({placeholders}): {r.rowcount} rows")

    # 4h. Delete test import batches
    if test_batch_ids:
        placeholders = ",".join(str(x) for x in test_batch_ids)
        sql = f"DELETE FROM scout_liq_historical_import_batches WHERE id IN ({placeholders})"
        r = db.execute(text(sql))
        print(f"  DELETE historical_import_batches WHERE id IN ({placeholders}): {r.rowcount} rows")

    # 4i. Delete all manual overrides (all 6 are test in dev)
    r = db.execute(text("DELETE FROM scout_liq_manual_overrides"))
    print(f"  DELETE manual_overrides (all): {r.rowcount} rows")

    # 4j. Delete health events and refresh registry (auto-regenerated)
    r = db.execute(text("DELETE FROM scout_liq_health_events"))
    print(f"  DELETE health_events (all): {r.rowcount} rows")
    r = db.execute(text("DELETE FROM scout_liq_refresh_registry"))
    print(f"  DELETE refresh_registry (all): {r.rowcount} rows")

    # 4k. Delete historical attributions without valid import_batch_id
    # (orphaned after batch deletion, or linked to test batches)
    r = db.execute(text(
        "DELETE FROM scout_liq_historical_attributions "
        "WHERE import_batch_id IS NULL "
        "   OR import_batch_id NOT IN (SELECT id FROM scout_liq_historical_import_batches)"
    ))
    print(f"  DELETE orphaned historical_attributions: {r.rowcount} rows")

    # ═══════════════════════════════════════════════════════
    # STEP 5: COMMIT
    # ═══════════════════════════════════════════════════════
    db.commit()
    print("\n=== COMMIT OK ===")

    # ═══════════════════════════════════════════════════════
    # STEP 6: COUNTS AFTER
    # ═══════════════════════════════════════════════════════
    print("\n=== COUNTS AFTER ===")
    for t in tables:
        new_c = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        old_c = counts_before[t]
        delta = new_c - old_c
        arrow = f"({delta:+d})" if delta != 0 else "(no change)"
        print(f"  {t:50s} {new_c:>6d} {arrow}")

    print("\n=== DONE ===")

finally:
    db.close()
