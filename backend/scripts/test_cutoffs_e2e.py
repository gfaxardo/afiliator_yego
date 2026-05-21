"""
E2E: Crear cortes Cabinet y Fleet, validar resultados.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.cohort_service import get_iso_cohorts
from app.services.cutoff_engine import create_cutoff_from_cohort, get_cutoff_summary, get_cutoff_lines, export_cutoff_financial_csv

db = SessionLocal()

try:
    cohorts = get_iso_cohorts(db)
    mature = [c for c in cohorts if c['readiness_status'] in ('mature', 'locked')]
    
    if not mature:
        print("No hay cohortes maduras. Necesita datos con hire_date y trips completados.")
        sys.exit(0)

    c = mature[0]
    cohort_week = c["cohort_iso_week"]
    print(f"Cohorte: {cohort_week} ({c['readiness_status']})")
    print(f"  Window: {c['cohort_from']} to {c['cohort_to']}")
    print(f"  Drivers: {c['total_drivers']} total, {c['drivers_with_scout']} con scout")

    # --- Crear cutoff Cabinet ---
    print("\n=== CABINET CUTOFF ===")
    try:
        cab = create_cutoff_from_cohort(db, cohort_week, "cabinet", created_by="test_e2e", force_override=True)
        cab_id = cab["cutoff_run_id"]
        print(f"  ID={cab_id} status={cab['status']}")
        print(f"  scheme: {cab['scheme_name']} ({cab['scheme_type']})")
        calc = cab.get("calculation", {})
        print(f"  scouts: {calc.get('scouts_evaluated', 'N/A')}")

        # Config snapshot
        from app.models.scout_liq import CutoffRun
        run = db.query(CutoffRun).filter(CutoffRun.id == cab_id).first()
        import json
        snap = json.loads(run.config_snapshot) if run.config_snapshot else {}
        print(f"  snapshot: volume_rule={snap.get('volume_rule')}, pays_on={snap.get('pays_on_rule')}")
        print(f"  snapshot: payout_formula={snap.get('payout_formula_type')}, maturity={snap.get('maturity_days')}")

        # Summary
        summaries = get_cutoff_summary(db, cab_id)
        print(f"  resumen: {len(summaries)} scouts")
        for s in summaries[:3]:
            print(f"    scout={s.get('scout_name')} activated={s.get('total_activated')} "
                  f"quality_5v7d={s.get('drivers_5plus_0_7')} "
                  f"conv_rate={s.get('conversion_rate_5v7d', 0):.2%} "
                  f"tier={s.get('tier_reached')} "
                  f"amount={s.get('amount_calculated', 0):.2f} "
                  f"status={s.get('status')}")

        # 5 lineas Cabinet
        lines = get_cutoff_lines(db, cab_id)
        cab_payable_count = 0
        cab_1v_payable = 0
        print(f"\n  --- 5 filas Cabinet ---")
        for l in lines[:5]:
            trips_0_7 = l.get('trips_0_7_count', 0) or 0
            payable = l.get('payout_eligible_flag')
            if payable:
                cab_payable_count += 1
            if trips_0_7 >= 1 and payable:
                cab_1v_payable += 1
            print(f"    driver={l.get('driver_id')} trips_0_7={trips_0_7} "
                  f"lifecycle={l.get('driver_lifecycle_status')} "
                  f"status={l.get('line_status')} "
                  f"payable={payable} amount={l.get('calculated_amount')}")

        print(f"  Cabinet: {cab_payable_count} drivers payable en primeras 5 filas")
        print(f"  Cabinet: {cab_1v_payable} drivers con >=1 viaje en 7d son payable")

        # Export CSV Cabinet
        csv_cab = export_cutoff_financial_csv(db, cab_id)
        lines_csv = csv_cab.strip().split('\n')
        print(f"\n  Export CSV Cabinet: {len(lines_csv)-1} lineas")
        if len(lines_csv) > 1:
            print(f"  Header: {lines_csv[0][:120]}...")
            print(f"  Row 1: {lines_csv[1][:150]}...")

        if "ACTIVATED_BASE" in csv_cab:
            print("  [OK] CSV contiene ACTIVATED_BASE")
        if "ACTIVATED_X_TIER" in csv_cab:
            print("  [OK] CSV contiene ACTIVATED_X_TIER")

    except ValueError as e:
        print(f"  SKIP Cabinet: {e}")

    # --- Crear cutoff Fleet ---
    print("\n=== FLEET CUTOFF ===")
    try:
        fleet = create_cutoff_from_cohort(db, cohort_week, "fleet", created_by="test_e2e", force_override=True)
        fleet_id = fleet["cutoff_run_id"]
        print(f"  ID={fleet_id} status={fleet['status']}")
        print(f"  scheme: {fleet['scheme_name']} ({fleet['scheme_type']})")
        calc = fleet.get("calculation", {})
        print(f"  scouts: {calc.get('scouts_evaluated', 'N/A')}")

        from app.models.scout_liq import CutoffRun
        run_f = db.query(CutoffRun).filter(CutoffRun.id == fleet_id).first()
        snap_f = json.loads(run_f.config_snapshot) if run_f.config_snapshot else {}
        print(f"  snapshot: volume_rule={snap_f.get('volume_rule')}, pays_on={snap_f.get('pays_on_rule')}")
        print(f"  snapshot: payout_formula={snap_f.get('payout_formula_type')}, maturity={snap_f.get('maturity_days')}")

        summaries_f = get_cutoff_summary(db, fleet_id)
        print(f"  resumen: {len(summaries_f)} scouts")
        for s in summaries_f[:3]:
            print(f"    scout={s.get('scout_name')} activated={s.get('total_activated')} "
                  f"quality_5v7d={s.get('drivers_5plus_0_7')} "
                  f"conv_rate={s.get('conversion_rate_5v7d', 0):.2%} "
                  f"tier={s.get('tier_reached')} "
                  f"amount={s.get('amount_calculated', 0):.2f} "
                  f"status={s.get('status')}")

        # 5 lineas Fleet
        lines_f = get_cutoff_lines(db, fleet_id)
        fleet_payable_count = 0
        fleet_1v_payable = 0
        print(f"\n  --- 5 filas Fleet ---")
        for l in lines_f[:5]:
            trips_0_7 = l.get('trips_0_7_count', 0) or 0
            payable = l.get('payout_eligible_flag')
            if payable:
                fleet_payable_count += 1
            if trips_0_7 >= 1 and payable:
                fleet_1v_payable += 1
            print(f"    driver={l.get('driver_id')} trips_0_7={trips_0_7} "
                  f"lifecycle={l.get('driver_lifecycle_status')} "
                  f"status={l.get('line_status')} "
                  f"payable={payable} amount={l.get('calculated_amount')} "
                  f"reason={l.get('blocked_reason', '')}")

        print(f"  Fleet: {fleet_payable_count} drivers payable en primeras 5 filas")
        print(f"  Fleet: {fleet_1v_payable} drivers con >=1 viaje en 7d son payable")
        
        # GO/NOGO
        if fleet_1v_payable == 0:
            print("\n  [GO] Fleet NO paga por 1V (como debe ser con 50V30D)")
        else:
            print(f"\n  [NO-GO] Fleet paga {fleet_1v_payable} drivers con solo 1V!")

        # Export CSV Fleet
        csv_fleet = export_cutoff_financial_csv(db, fleet_id)
        lines_csv_f = csv_fleet.strip().split('\n')
        print(f"\n  Export CSV Fleet: {len(lines_csv_f)-1} lineas")
        if "QUALITY_HIT" in csv_fleet:
            print("  [OK] CSV contiene QUALITY_HIT")
        if "QUALITY_X_FIXED" in csv_fleet:
            print("  [OK] CSV contiene QUALITY_X_FIXED")

    except ValueError as e:
        print(f"  SKIP Fleet: {e}")

    # --- Comparacion final ---
    print("\n=== COMPARATIVA FINAL ===")
    print(f"  Cabinet: paga basado en activados (1V7D) con ACTIVATED_X_TIER")
    print(f"  Fleet:   paga basado en calidad (50V30D) con QUALITY_X_FIXED")
    print(f"  Fleet NO debe pagar por drivers con solo 1 viaje en 7 dias")
    print(f"  Fleet madura a 30 dias, Cabinet a 7 dias")

finally:
    db.close()
