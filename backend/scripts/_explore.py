import os, sys; sys.path.insert(0, '.')
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    print("=== CUTOFF RUNS ===")
    r = db.execute(text("SELECT id, status, week_start, week_end, total_drivers, total_amount FROM scout_liq_cutoff_runs ORDER BY id DESC")).fetchall()
    for row in r:
        print(f"  id={row[0]} status={row[1]} week={row[2]}–{row[3]} drivers={row[4]} amount={row[5]}")

    print("\n=== CUTOFF SCOUT SUMMARY (top 5) ===")
    r2 = db.execute(text("SELECT id, cutoff_run_id, scout_id, total_drivers, total_amount, trips_0_7_1plus, trips_0_7_5plus, trips_8_14_1plus, trips_0_14_5plus, conversion_5v_7d FROM scout_liq_cutoff_scout_summary ORDER BY id DESC LIMIT 5")).fetchall()
    for row in r2:
        print(f"  id={row[0]} cutoff={row[1]} scout={row[2]} drivers={row[3]} amt={row[4]} 1p0_7={row[5]} 5p0_7={row[6]} 1p8_14={row[7]} 5p0_14={row[8]} conv={row[9]}")

    print("\n=== CUTOFF DRIVER LINES (top 5) ===")
    r3 = db.execute(text("SELECT id, cutoff_run_id, driver_id, trips_0_7, trips_8_14, trips_0_14, conversion_5v_7d, conversion_rate, tier, calculated_amount, approved_amount, is_paid FROM scout_liq_cutoff_driver_lines ORDER BY id DESC LIMIT 5")).fetchall()
    for row in r3:
        print(f"  id={row[0]} cutoff={row[1]} driver={str(row[2])[:12]} 0_7={row[3]} 8_14={row[4]} 0_14={row[5]} 5v7d={row[6]} rate={row[7]} tier={row[8]} calc={row[9]} approved={row[10]} paid={row[11]}")

    print("\n=== COUNT BY TABLE ===")
    for tbl in ["scout_liq_cutoff_runs", "scout_liq_cutoff_scout_summary", "scout_liq_cutoff_driver_lines", "scout_liq_scouts", "scout_liq_driver_assignments"]:
        c = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        print(f"  {tbl}: {c}")

finally:
    db.close()
