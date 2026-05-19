import os, sys; sys.path.insert(0,'.')
from app.database import SessionLocal
from sqlalchemy import text
db=SessionLocal()
try:
    cols=db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='module_ct_cabinet_drivers' ORDER BY ordinal_position")).fetchall()
    print("SOURCE TABLE COLUMNS:")
    for c in cols:
        print(f"  {c[0]}")
    print()
    # Check sample data with names
    sample=db.execute(text("SELECT driver_id, driver_nombre, driver_apellido, license, hire_date FROM module_ct_cabinet_drivers WHERE driver_nombre IS NOT NULL LIMIT 3")).fetchall()
    print("SAMPLE WITH NAMES:")
    for r in sample:
        print(f"  id={r[0][:12] if r[0] else None} nombre={r[1]} apellido={r[2]} lic={r[3]}")
finally:
    db.close()
