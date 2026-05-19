"""Quick diagnostic of module_ct_cabinet_drivers via SQLAlchemy."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import engine
from sqlalchemy import text

RESULTS = {}

with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_name = 'module_ct_cabinet_drivers'"
    )).fetchall()
    RESULTS["schemas"] = [[row[0], row[1]] for row in r]
    for row in r:
        print(f"TABLE FOUND: {row[0]}.{row[1]}")

    r = conn.execute(text(
        "SELECT column_name, data_type, is_nullable, ordinal_position "
        "FROM information_schema.columns "
        "WHERE table_name = 'module_ct_cabinet_drivers' "
        "ORDER BY ordinal_position"
    )).fetchall()
    RESULTS["columns"] = [
        {"name": row[0], "type": row[1], "nullable": row[2], "pos": row[3]}
        for row in r
    ]
    print(f"\nCOLUMNS ({len(r)}):")
    for row in r:
        print(f"  {row[3]:3d}. {row[0]:45s} | {row[1]:20s} | null={row[2]}")

    col_names = [c["name"] for c in RESULTS["columns"]]

    total = conn.execute(text("SELECT COUNT(*) FROM module_ct_cabinet_drivers")).scalar()
    RESULTS["total_rows"] = total
    print(f"\nTOTAL ROWS: {total}")

    print(f"\nKEY COLUMN CHECKS:")
    for key in ["driver_id", "hire_date", "origin", "trips_7d", "trips_14d"]:
        exists = key in col_names
        print(f"  {key}: {'FOUND' if exists else 'NOT FOUND'}")

    # Check for origin-like columns
    origin_like = [c for c in col_names if any(
        kw in c.lower() for kw in ["origin", "cabinet", "fleet", "partner", "source", "park"]
    )]
    print(f"\nORIGIN-LIKE COLS: {origin_like}")

    # Check for trip-like columns
    trip_like = [c for c in col_names if any(
        kw in c.lower() for kw in ["trip", "viaje", "7d", "7_d", "14d", "14_d", "week", "day", "semana"]
    )]
    print(f"TRIP-LIKE COLS: {trip_like}")

    # Null checks for driver_id
    try:
        r = conn.execute(text("SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE driver_id IS NULL")).scalar()
        RESULTS["null_driver_id"] = r
        print(f"\nNULL driver_id: {r}")
    except Exception as e:
        print(f"\nNULL driver_id: ERROR - {e}")

    # Null checks for hire_date
    try:
        r = conn.execute(text("SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE hire_date IS NULL")).scalar()
        RESULTS["null_hire_date"] = r
        print(f"NULL hire_date: {r}")
    except Exception as e:
        print(f"NULL hire_date: ERROR - {e}")

    # Duplicates
    try:
        r = conn.execute(text(
            "SELECT driver_id, COUNT(*) AS cnt FROM module_ct_cabinet_drivers "
            "WHERE driver_id IS NOT NULL GROUP BY driver_id HAVING COUNT(*) > 1 "
            "ORDER BY cnt DESC LIMIT 10"
        )).fetchall()
        RESULTS["duplicates_top10"] = [[row[0], row[1]] for row in r]
        print(f"\nDUPLICATE driver_id (top 10):")
        for row in r:
            print(f"  {row[0]}: {row[1]}x")
    except Exception as e:
        print(f"\nDUPLICATES: ERROR - {e}")

    # Sample
    try:
        r = conn.execute(text("SELECT * FROM module_ct_cabinet_drivers LIMIT 2")).fetchall()
        RESULTS["sample_rows"] = [
            {k: str(v) for k, v in row._mapping.items()} for row in r
        ]
        print(f"\nSAMPLE ROWS (2):")
        for i, row in enumerate(r):
            for k, v in row._mapping.items():
                print(f"  [{k}] = {str(v)[:100]}")
            print("  ---")
    except Exception as e:
        print(f"\nSAMPLE: ERROR - {e}")

    # hire_date range
    try:
        r = conn.execute(text("SELECT MIN(hire_date), MAX(hire_date) FROM module_ct_cabinet_drivers")).first()
        RESULTS["hire_date_min"] = str(r[0]) if r and r[0] else None
        RESULTS["hire_date_max"] = str(r[1]) if r and r[1] else None
        print(f"\nHIRE_DATE RANGE: {RESULTS['hire_date_min']} -> {RESULTS['hire_date_max']}")
    except Exception as e:
        print(f"\nHIRE_DATE RANGE: ERROR - {e}")

print("\n=== DIAGNOSTIC COMPLETE ===")
