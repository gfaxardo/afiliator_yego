"""
Execute controlled rollback of bad paid_history records.
Uses transaction: counts, deletes, verifies, commits.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import SessionLocal
from app.models.scout_liq import PaidHistory
from sqlalchemy import text

EXPECTED_RANGE = (8, 251)

db = SessionLocal()
try:
    before = db.query(PaidHistory).filter(
        PaidHistory.import_source == "historical_upload",
        PaidHistory.driver_id == None,
    ).count()
    print(f"[SCOUT_LIQ_ROLLBACK] bad_records_found={before}")

    if before == 0:
        print("Nothing to delete. Done.")
        sys.exit(0)

    # BEGIN transaction
    db.execute(text("BEGIN"))

    result = db.execute(text("""
        DELETE FROM scout_liq_paid_history
        WHERE import_source = 'historical_upload'
          AND driver_id IS NULL
    """))
    deleted = result.rowcount
    print(f"[SCOUT_LIQ_ROLLBACK] deleted={deleted}")

    remaining = db.query(PaidHistory).filter(
        PaidHistory.import_source == "historical_upload",
        PaidHistory.driver_id == None,
    ).count()
    print(f"[SCOUT_LIQ_ROLLBACK] remaining_bad={remaining}")

    if remaining != 0:
        print(f"ERROR: {remaining} bad records remain. ROLLBACK.")
        db.execute(text("ROLLBACK"))
        sys.exit(1)

    db.execute(text("COMMIT"))
    print("Rollback committed successfully.")

    # Final counts
    total = db.query(PaidHistory).count()
    historical = db.query(PaidHistory).filter(
        PaidHistory.import_source == "historical_upload"
    ).count()
    print(f"\nFinal state:")
    print(f"  Total paid_history: {total}")
    print(f"  historical_upload: {historical}")
    print(f"  historical_upload with driver_id=NULL: 0")

finally:
    db.close()
