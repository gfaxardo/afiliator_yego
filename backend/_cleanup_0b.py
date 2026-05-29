"""Fase 0B: Limpieza TOTAL de cortes y paid_history de prueba."""
import sys, os, csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import SessionLocal

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
DRY_RUN = "--dry-run" in sys.argv
EXECUTE = "--execute" in sys.argv

os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

db = SessionLocal()

try:
    tables_to_backup = [
        "scout_liq_cutoff_runs",
        "scout_liq_cutoff_scout_summary",
        "scout_liq_cutoff_driver_lines",
        "scout_liq_paid_history",
        "scout_liq_manual_overrides",
    ]

    tables_config = [
        "scout_liq_payment_schemes",
        "scout_liq_payment_scheme_versions",
        "scout_liq_payment_scheme_tiers",
        "scout_liq_conversion_schemes",
        "scout_liq_conversion_tiers",
        "scout_liq_scouts",
    ]

    print("=" * 60)
    print("FASE 0B — LIMPIEZA TOTAL DE CORTES Y PAID HISTORY")
    print("=" * 60)

    # --- COUNTS BEFORE ---
    print("\n--- COUNTS BEFORE ---")
    all_tables = tables_to_backup + tables_config
    counts_before = {}
    for t in all_tables:
        c = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        counts_before[t] = c
        flag = " [CONFIG - NO TOCAR]" if t in tables_config else ""
        print(f"  {t:50s} {c:>6d}{flag}")

    if DRY_RUN:
        print("\nDRY RUN. Use --execute to apply.")
        sys.exit(0)

    # --- BACKUP ---
    print("\n--- BACKUP ---")
    for t in all_tables:
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

    if not EXECUTE:
        print("\nNo --execute flag. Use --execute to apply cleanup.")
        sys.exit(0)

    # --- CLEANUP ---
    print("\n--- CLEANUP ---")

    # 1. Delete driver lines and summaries (should be 0 already)
    r = db.execute(text("DELETE FROM scout_liq_cutoff_driver_lines"))
    print(f"  DELETE cutoff_driver_lines (all): {r.rowcount} rows")

    r = db.execute(text("DELETE FROM scout_liq_cutoff_scout_summary"))
    print(f"  DELETE cutoff_scout_summary (all): {r.rowcount} rows")

    # 2. Delete paid_history (all 246)
    r = db.execute(text("DELETE FROM scout_liq_paid_history"))
    print(f"  DELETE paid_history (all): {r.rowcount} rows")

    # 3. Delete manual overrides (should be 0 already)
    r = db.execute(text("DELETE FROM scout_liq_manual_overrides"))
    print(f"  DELETE manual_overrides (all): {r.rowcount} rows")

    # 4. Delete cutoff runs (all 6)
    r = db.execute(text("DELETE FROM scout_liq_cutoff_runs"))
    print(f"  DELETE cutoff_runs (all): {r.rowcount} rows")

    db.commit()
    print("\n--- COMMIT OK ---")

    # --- VERIFY ---
    print("\n--- COUNTS AFTER ---")
    all_ok = True
    for t in all_tables:
        new_c = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        old_c = counts_before[t]
        delta = new_c - old_c
        flag = " [CONFIG - NO TOCAR]" if t in tables_config else ""
        print(f"  {t:50s} {new_c:>6d} ({delta:+d}){flag}")
        if t in tables_config and new_c != old_c:
            print(f"    *** ALERTA: Config modificada! Esperado {old_c}, obtenido {new_c}")
            all_ok = False

    if all_ok:
        print("\n*** VERIFICACION: Config intacta, cortes y paid_history eliminados ***")
    else:
        print("\n*** ALERTA: Config fue modificada! ***")

    print(f"\nBackups en: {BACKUP_DIR}")
    print("DONE")

finally:
    db.close()
