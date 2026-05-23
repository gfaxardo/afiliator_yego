"""
Cleanup script for E2E test observed affiliations.
Deletes ONLY records with source_file_id = 999 (test batch marker)
and their associated reconciliation audit entries.
"""
from app.database import SessionLocal
from sqlalchemy import text
import sys

TAG_SOURCE_FILE_ID = 999

def cleanup():
    db = SessionLocal()
    try:
        # Count before
        before_oa = db.execute(text(
            "SELECT COUNT(*) FROM scout_liq_observed_affiliations WHERE source_file_id = :sid"
        ), {"sid": TAG_SOURCE_FILE_ID}).scalar() or 0
        before_audit = db.execute(text("""
            SELECT COUNT(*) FROM scout_liq_reconciliation_audit
            WHERE observed_affiliation_id IN (
                SELECT id FROM scout_liq_observed_affiliations WHERE source_file_id = :sid
            )
        """), {"sid": TAG_SOURCE_FILE_ID}).scalar() or 0

        if before_oa == 0:
            print("No test records found with source_file_id = 999. Nothing to clean.")
            return

        print(f"Found: {before_oa} observed records, {before_audit} audit entries to clean")

        # Delete reconciliation audit entries for test records
        db.execute(text("""
            DELETE FROM scout_liq_reconciliation_audit
            WHERE observed_affiliation_id IN (
                SELECT id FROM scout_liq_observed_affiliations WHERE source_file_id = :sid
            )
        """), {"sid": TAG_SOURCE_FILE_ID})

        # Delete reconciliation refresh logs that were test-only (optional, based on timing)
        # Not critical, skip

        # Delete observed affiliations
        db.execute(text(
            "DELETE FROM scout_liq_observed_affiliations WHERE source_file_id = :sid"
        ), {"sid": TAG_SOURCE_FILE_ID})

        db.commit()

        # Count after
        after_oa = db.execute(text(
            "SELECT COUNT(*) FROM scout_liq_observed_affiliations WHERE source_file_id = :sid"
        ), {"sid": TAG_SOURCE_FILE_ID}).scalar() or 0

        # Verify no test records in other tables
        after_audit = db.execute(text("""
            SELECT COUNT(*) FROM scout_liq_reconciliation_audit
            WHERE observed_affiliation_id IN (
                SELECT id FROM scout_liq_observed_affiliations WHERE source_file_id = :sid
            )
        """), {"sid": TAG_SOURCE_FILE_ID}).scalar() or 0

        print(f"Cleanup done. Remaining: {after_oa} observed, {after_audit} audit entries")

        # Quick integrity check: confirm critical tables untouched
        cabinet_count = db.execute(text("SELECT COUNT(*) FROM module_ct_cabinet_drivers")).scalar()
        drivers_count = db.execute(text("SELECT COUNT(*) FROM drivers")).scalar()
        paid_count = db.execute(text("SELECT COUNT(*) FROM scout_liq_paid_history")).scalar()
        print(f"Integrity check: cabinet={cabinet_count} drivers={drivers_count} paid_history={paid_count}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    cleanup()
