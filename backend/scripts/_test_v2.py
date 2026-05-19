import os, sys; sys.path.insert(0, '.')
from app.database import SessionLocal
from app.services.operation_service import (
    get_operation_filters, get_operation_summary, get_affiliations,
    get_affiliation_detail
)

db = SessionLocal()
try:
    print("=== FILTERS (default week logic) ===")
    f = get_operation_filters(db)
    print(f"  current_iso_week: {f['current_iso_week']}")
    print(f"  current_label: {f['current_iso_week_label']}")
    print(f"  has_data_current: {f['has_data_for_current_week']}")
    print(f"  latest_with_data: {f['latest_iso_week_with_data']}")
    print(f"  latest_label: {f['latest_iso_week_with_data_label']}")
    print(f"  default_week: {f['default_week_iso']}")

    print("\n=== SUMMARY (week S18-2026) ===")
    s = get_operation_summary(db, week_iso="2026-W18")
    print(f"  total: {s['total_affiliations']}")
    print(f"  with_driver: {s['total_with_driver']}")
    print(f"  without_driver: {s['total_without_driver']}")
    print(f"  paid: {s['total_paid_history']}  amount: S/ {s['total_paid_amount']}")
    print(f"  blocks_future: {s['total_blocks_future']}")
    print(f"  financial_only: {s['total_financial_only']}")
    print(f"  CRITICAL alert count: {s['total_alerts_critical']}")
    print(f"  warning count: {s['total_alerts_warning']}")

    print("\n=== SUMMARY (all weeks) ===")
    s2 = get_operation_summary(db)
    print(f"  total: {s2['total_affiliations']}")
    print(f"  CRITICAL alert count: {s2['total_alerts_critical']}")
    print(f"  warning count: {s2['total_alerts_warning']}")

    print("\n=== AFFILIATIONS (first 5, week 18) ===")
    r = get_affiliations(db, week_iso="2026-W18", limit=5)
    print(f"  total: {r['total']}")
    for item in r['items']:
        print(f"  row={item['row_id']} week={item['iso_week_label_full']}")
        print(f"    driver={item['driver_display_name']} (id={str(item.get('driver_id',''))[:12]})")
        print(f"    scout={str(item.get('scout_name',''))[:25]}")
        print(f"    attr={item['attribution_status']} fin={item['payment_financial_status']}")
        print(f"    blk={item['payment_blocking_status']} blk_display={item['blocking_display']}")
        print(f"    blocks={item['blocks_future_payment']} amt={item.get('amount_paid',0)}")
        print(f"    alert={item['alert_level']} codes={item.get('alert_codes',[])}")
        print()

    print("=== PAID ROWS (only_paid, first 5) ===")
    rp = get_affiliations(db, only_paid=True, limit=5)
    print(f"  total paid: {rp['total']}")
    for item in rp['items'][:3]:
        print(f"  row={item['row_id']} blk_display={item['blocking_display']} alert={item['alert_level']} codes={item.get('alert_codes',[])} blocks={item['blocks_future_payment']}")

    print("\n=== DUPLICATE ROWS (week 18, first 3 duplicates) ===")
    rd = get_affiliations(db, week_iso="2026-W18", limit=100)
    dups = [i for i in rd['items'] if i['payment_blocking_status'] == 'payment_blocking_duplicate']
    print(f"  duplicates in week 18: {len(dups)}")
    for item in dups[:3]:
        print(f"  row={item['row_id']} paid_history_id={item['paid_history_id']} blk_display={item['blocking_display']} alert={item['alert_level']}")

finally:
    db.close()
