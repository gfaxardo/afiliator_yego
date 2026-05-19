import os, sys; sys.path.insert(0, '.')
from app.database import SessionLocal
from app.services.dashboard_service import (
    get_dashboard_overview, get_dashboard_by_scout, get_dashboard_by_week,
    get_dashboard_quality_funnel, get_dashboard_alerts
)
db = SessionLocal()
try:
    o = get_dashboard_overview(db)
    print("=== OVERVIEW ===")
    for k, v in o.items():
        print(f"  {k}: {v}")

    print("\n=== BY-SCOUT (top 5) ===")
    s = get_dashboard_by_scout(db)
    print(f"  Total scouts: {len(s)}")
    for r in s[:5]:
        print(f"  {r['scout_name'][:30]:30s} aff={r['affiliations_total']:4d} paid={r['paid_history_count']:3d} amt=S/{r['paid_history_amount']:8.0f} blocks={r['blocking_count']:2d}")

    print(f"\n=== BY-WEEK (top 5) ===")
    w = get_dashboard_by_week(db)
    print(f"  Total weeks: {len(w)}")
    for r in w[:5]:
        print(f"  {r['label']:10s} total={r['total']:4d} paid={r['paid_count']:3d} amt=S/{r['paid_amount']:8.0f} blocks={r['blocking_count']:2d} review={r['manual_review']:3d}")

    print(f"\n=== QUALITY FUNNEL ===")
    qf = get_dashboard_quality_funnel(db)
    print(f"  {qf}")

    print(f"\n=== ALERTS ===")
    al = get_dashboard_alerts(db)
    for k, v in al.items():
        print(f"  {k}: {v}")
finally:
    db.close()
