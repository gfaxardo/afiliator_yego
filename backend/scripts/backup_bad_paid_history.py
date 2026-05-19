"""
Backup bad paid_history records before rollback.
Exports CSV of all historical_upload records with driver_id=NULL.
"""
import csv, os, sys, json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import SessionLocal
from app.models.scout_liq import PaidHistory

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

db = SessionLocal()
try:
    bad = db.query(PaidHistory).filter(
        PaidHistory.import_source == "historical_upload",
        PaidHistory.driver_id == None,
    ).order_by(PaidHistory.id).all()

    print(f"[SCOUT_LIQ_ROLLBACK] bad_records_found={len(bad)}")

    if not bad:
        print("No bad records found. Nothing to backup.")
        sys.exit(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"backup_bad_paid_history_driver_null_{ts}.csv")

    fields = ["id", "cutoff_run_id", "scout_id", "driver_id", "driver_license_raw",
              "scout_name_raw", "amount_paid", "currency", "import_source",
              "source_file", "source_sheet", "source_row", "payment_rule",
              "payment_component", "unique_hash", "status", "created_at"]

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in bad:
            w.writerow({f: getattr(r, f, None) for f in fields})

    print(f"[SCOUT_LIQ_ROLLBACK] backup_created path={path}")
    print(f"  Records backed up: {len(bad)}")
    print(f"  ID range: {bad[0].id} - {bad[-1].id}")
    total = sum(float(r.amount_paid or 0) for r in bad)
    print(f"  Total amount: S/ {total:.2f}")

    # Show sample
    print("\nSample backed up records:")
    for r in bad[:5]:
        print(f"  PH#{r.id} scout={r.scout_id} lic={r.driver_license_raw} amt=S/ {r.amount_paid} row={r.source_row}")

finally:
    db.close()
