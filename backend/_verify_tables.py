"""Verify scout_liq tables exist and run seed."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE 'scout_liq_%' ORDER BY table_name"
    )).fetchall()
    print(f"TABLAS scout_liq ({len(r)}):")
    for row in r:
        print(f"  [OK] {row[0]}")

    # Verify alembic version table
    r = conn.execute(text(
        "SELECT version_num FROM alembic_version_scout_liq"
    )).fetchall()
    print(f"\nALEMBIC VERSION: {r[0][0] if r else 'NONE'}")
