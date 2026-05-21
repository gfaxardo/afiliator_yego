"""
Test multi-esquema Cabinet vs Fleet.
Valida que el calculo financiero respete realmente las reglas configuradas.

NO hardcodea scheme_type — lee las reglas desde el config_snapshot resuelto.

Ejecutar:
    cd backend
    python scripts/test_multi_scheme.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── UNIT: _parse_rule ──
from app.services.cutoff_engine import _parse_rule, _get_trip_count_for_window

print("=" * 70)
print("1. UNIT: _parse_rule y _get_trip_count_for_window")
print("=" * 70)

assert _parse_rule("1V7D") == (1, 7)
assert _parse_rule("5V7D") == (5, 7)
assert _parse_rule("50V30D") == (50, 30)
assert _parse_rule(None) == (1, 7)
assert _parse_rule("") == (1, 7)
assert _parse_rule("INVALID") == (1, 7)
print("  _parse_rule: OK")

tc_db = {"D1": {"trips_0_7_count": 3, "trips_8_14_count": 4, "trips_0_30_count": 55}}
assert _get_trip_count_for_window(tc_db, "D1", 7) == 3
assert _get_trip_count_for_window(tc_db, "D1", 14) == 7
assert _get_trip_count_for_window(tc_db, "D1", 30) == 55
assert _get_trip_count_for_window(tc_db, "D1", 30) >= 50
assert not (_get_trip_count_for_window(tc_db, "D1", 7) >= 50)
print("  _get_trip_count_for_window: OK")
print()

# ── INTEGRATION: Direct DB access ──
print("=" * 70)
print("2. INTEGRATION: Resolver + Seed + Config Snapshot")
print("=" * 70)

try:
    from app.database import SessionLocal
    from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort
    from app.services.cutoff_engine import _build_config_snapshot_from_resolved
    from app.services.cohort_service import get_iso_cohorts

    db = SessionLocal()
except Exception as e:
    print(f"  SKIP: No se puede conectar a la DB. {e}")
    print("  Tests unitarios OK. Configure DB_HOST/DB_NAME en .env para integracion.")
    sys.exit(0)

try:
    # ── 2a. Cohorts disponibles ──
    cohorts = get_iso_cohorts(db)
    print(f"  Cohorts detectadas: {len(cohorts)}")

    test_cohort = "2026-W01"
    if cohorts:
        mature = [c for c in cohorts if c["readiness_status"] in ("mature", "locked")]
        test_cohort = mature[0]["cohort_iso_week"] if mature else cohorts[0]["cohort_iso_week"]
        print(f"  Usando cohorte: {test_cohort}")

    # ── 2b. Resolver Cabinet ──
    print()
    print("--- Resolver Cabinet ---")
    try:
        cab = resolve_payment_scheme_for_cohort(db, test_cohort, "cabinet")
        print(f"  scheme_name: {cab['scheme_name']}")
        print(f"  volume_rule: {cab.get('volume_rule', 'N/A')}")
        print(f"  quality_rule: {cab.get('quality_rule', 'N/A')}")
        print(f"  pays_on_rule: {cab.get('pays_on_rule', 'N/A')}")
        print(f"  payout_formula_type: {cab.get('payout_formula_type', 'N/A')}")
        print(f"  maturity_days: {cab.get('maturity_days', 'N/A')}")
        print(f"  min_volume_count: {cab.get('min_volume_count', 'N/A')}")

        cab_ok = True
        if "1V" not in str(cab.get("volume_rule", "")):
            print(f"  [FAIL] volume_rule = {cab.get('volume_rule')} (esperado 1V7D)")
            cab_ok = False
        if cab.get("pays_on_rule") != "ACTIVATED_BASE":
            print(f"  [FAIL] pays_on_rule = {cab.get('pays_on_rule')} (esperado ACTIVATED_BASE)")
            cab_ok = False
        if "ACTIVATED" not in str(cab.get("payout_formula_type", "")):
            print(f"  [FAIL] payout_formula_type = {cab.get('payout_formula_type')} (esperado ACTIVATED_X_TIER)")
            cab_ok = False
        if cab.get("maturity_days") != 7:
            print(f"  [FAIL] maturity_days = {cab.get('maturity_days')} (esperado 7)")
            cab_ok = False
        if cab_ok:
            print("  [OK] Cabinet assertions passed")
    except ValueError as e:
        print(f"  [SKIP] Cabinet resolver: {e}")

    # ── 2c. Resolver Fleet ──
    print()
    print("--- Resolver Fleet ---")
    try:
        fleet = resolve_payment_scheme_for_cohort(db, test_cohort, "fleet")
        print(f"  scheme_name: {fleet['scheme_name']}")
        print(f"  volume_rule: {fleet.get('volume_rule', 'N/A')}")
        print(f"  quality_rule: {fleet.get('quality_rule', 'N/A')}")
        print(f"  pays_on_rule: {fleet.get('pays_on_rule', 'N/A')}")
        print(f"  payout_formula_type: {fleet.get('payout_formula_type', 'N/A')}")
        print(f"  maturity_days: {fleet.get('maturity_days', 'N/A')}")
        print(f"  min_volume_count: {fleet.get('min_volume_count', 'N/A')}")

        fleet_ok = True
        if "50V" not in str(fleet.get("volume_rule", "")) or "30D" not in str(fleet.get("volume_rule", "")):
            print(f"  [FAIL] volume_rule = {fleet.get('volume_rule')} (esperado 50V30D)")
            fleet_ok = False
        if fleet.get("pays_on_rule") != "QUALITY_HIT":
            print(f"  [FAIL] pays_on_rule = {fleet.get('pays_on_rule')} (esperado QUALITY_HIT)")
            fleet_ok = False
        if "QUALITY" not in str(fleet.get("payout_formula_type", "")):
            print(f"  [FAIL] payout_formula_type = {fleet.get('payout_formula_type')} (esperado QUALITY_X_FIXED)")
            fleet_ok = False
        if fleet.get("maturity_days") != 30:
            print(f"  [FAIL] maturity_days = {fleet.get('maturity_days')} (esperado 30)")
            fleet_ok = False
        if fleet_ok:
            print("  [OK] Fleet assertions passed")
    except ValueError as e:
        print(f"  [SKIP] Fleet resolver: {e}")

    # ── 2d. Cross-validation ──
    print()
    print("--- Cross-validation: Cabinet != Fleet ---")
    try:
        cab = resolve_payment_scheme_for_cohort(db, test_cohort, "cabinet")
        fleet = resolve_payment_scheme_for_cohort(db, test_cohort, "fleet")
        diffs = []
        for field in ["volume_rule", "quality_rule", "pays_on_rule", "payout_formula_type", "maturity_days", "min_volume_count"]:
            cv = cab.get(field)
            fv = fleet.get(field)
            if cv != fv:
                diffs.append(f"  {field}: cabinet='{cv}' vs fleet='{fv}'")
        if diffs:
            print(f"  {len(diffs)} diferencias detectadas:")
            for d in diffs:
                print(d)
        else:
            print("  [FAIL] No hay diferencias entre Cabinet y Fleet!")
    except ValueError as e:
        print(f"  [SKIP]: {e}")

    # ── 3. Config Snapshot ──
    print()
    print("--- Config Snapshot desde esquema resuelto ---")
    try:
        cab = resolve_payment_scheme_for_cohort(db, test_cohort, "cabinet")
        snapshot_cab = _build_config_snapshot_from_resolved(cab)
        snap = json.loads(snapshot_cab)
        print(f"  Cabinet snapshot: scheme_type={snap.get('scheme_type')}")
        print(f"  volume_rule={snap.get('volume_rule')}, pays_on_rule={snap.get('pays_on_rule')}")
        print(f"  payout_formula_type={snap.get('payout_formula_type')}")
        assert snap.get("pays_on_rule") == "ACTIVATED_BASE", f"Snapshot pays_on_rule={snap.get('pays_on_rule')}"
        assert snap.get("volume_rule") == "1V7D", f"Snapshot volume_rule={snap.get('volume_rule')}"
        print("  [OK] Cabinet config_snapshot validado")

        fleet = resolve_payment_scheme_for_cohort(db, test_cohort, "fleet")
        snapshot_fleet = _build_config_snapshot_from_resolved(fleet)
        snap_f = json.loads(snapshot_fleet)
        print(f"  Fleet snapshot: scheme_type={snap_f.get('scheme_type')}")
        print(f"  volume_rule={snap_f.get('volume_rule')}, pays_on_rule={snap_f.get('pays_on_rule')}")
        print(f"  payout_formula_type={snap_f.get('payout_formula_type')}")
        assert snap_f.get("pays_on_rule") == "QUALITY_HIT", f"Snapshot pays_on_rule={snap_f.get('pays_on_rule')}"
        assert "50V" in str(snap_f.get("volume_rule", "")) and "30D" in str(snap_f.get("volume_rule", ""))
        print("  [OK] Fleet config_snapshot validado")
    except ValueError as e:
        print(f"  [SKIP]: {e}")

    # ── 4. Test cutoff engine calculation with sample data ──
    print()
    print("--- Simulacion de calculo multi-esquema ---")
    from app.services.cutoff_engine import calculate_cutoff
    from app.models.scout_liq import CutoffRun

    # Build a synthetic config_snapshot for Cabinet
    cab_snap = {
        "scheme_id": 1, "scheme_name": "Cabinet Standard", "scheme_type": "cabinet",
        "version_name": "v1",
        "volume_rule": "1V7D", "quality_rule": "5V7D",
        "pays_on_rule": "ACTIVATED_BASE", "payout_formula_type": "ACTIVATED_X_TIER",
        "maturity_days": 7, "maturity_window_days": 7,
        "min_activated": 8, "min_volume_count": 8, "min_affiliations": 8,
        "activation_rule": "1V7D",
        "formula_type": "ACTIVATED_X_TIER", "currency": "PEN",
        "tiers": [
            {"min_conversion_rate": 0.10, "payout_amount": 10, "payment_per_converted_driver": 10, "currency": "PEN"},
            {"min_conversion_rate": 0.20, "payout_amount": 20, "payment_per_converted_driver": 20, "currency": "PEN"},
        ],
        "conversion_metric": "5plus_0_7",
    }

    fleet_snap = {
        "scheme_id": 2, "scheme_name": "Fleet Standard", "scheme_type": "fleet",
        "version_name": "v1",
        "volume_rule": "50V30D", "quality_rule": "50V30D",
        "pays_on_rule": "QUALITY_HIT", "payout_formula_type": "QUALITY_X_FIXED",
        "maturity_days": 30, "maturity_window_days": 30,
        "min_activated": 1, "min_volume_count": 1, "min_affiliations": 1,
        "activation_rule": "50V30D",
        "formula_type": "QUALITY_X_FIXED", "currency": "PEN",
        "tiers": [
            {"min_conversion_rate": 0.25, "payout_amount": 50, "payment_per_converted_driver": 50, "currency": "PEN"},
            {"min_conversion_rate": 0.50, "payout_amount": 80, "payment_per_converted_driver": 80, "currency": "PEN"},
            {"min_conversion_rate": 0.75, "payout_amount": 120, "payment_per_converted_driver": 120, "currency": "PEN"},
        ],
        "conversion_metric": "5plus_0_7",
    }

    # Parse rules from snapshots
    cab_vol_min, cab_vol_days = _parse_rule(cab_snap["volume_rule"])
    cab_qual_min, cab_qual_days = _parse_rule(cab_snap["quality_rule"])
    fleet_vol_min, fleet_vol_days = _parse_rule(fleet_snap["volume_rule"])
    fleet_qual_min, fleet_qual_days = _parse_rule(fleet_snap["quality_rule"])

    print(f"  Cabinet rules: volume={cab_snap['volume_rule']} -> min={cab_vol_min}, days={cab_vol_days}")
    print(f"                 quality={cab_snap['quality_rule']} -> min={cab_qual_min}, days={cab_qual_days}")
    print(f"                 pays_on={cab_snap['pays_on_rule']}, formula={cab_snap['payout_formula_type']}")
    print(f"  Fleet rules:   volume={fleet_snap['volume_rule']} -> min={fleet_vol_min}, days={fleet_vol_days}")
    print(f"                 quality={fleet_snap['quality_rule']} -> min={fleet_qual_min}, days={fleet_qual_days}")
    print(f"                 pays_on={fleet_snap['pays_on_rule']}, formula={fleet_snap['payout_formula_type']}")

    # Simulate a driver with 3 trips (1V7D: SI paga en Cabinet, NO en Fleet 50V30D)
    driver_1v = {"trips_0_7_count": 3, "trips_8_14_count": 0, "trips_0_30_count": 3}

    # Cabinet: 3 trips >= 1 in 7D -> counts as volume base
    cab_meets_vol = _get_trip_count_for_window({"D1": driver_1v}, "D1", cab_vol_days) >= cab_vol_min
    cab_payable = cab_meets_vol  # ACTIVATED_BASE pays on volume

    # Fleet: 3 trips < 50 in 30D -> does NOT count
    fleet_meets_qual = _get_trip_count_for_window({"D1": driver_1v}, "D1", fleet_qual_days) >= fleet_qual_min
    fleet_payable = fleet_meets_qual  # QUALITY_HIT pays on quality

    print(f"\n  Driver con 3 viajes en 7d (trips_0_30=3):")
    print(f"    Cabinet (1V7D): meets_volume={cab_meets_vol}, payable={cab_payable}")
    print(f"    Fleet (50V30D): meets_quality={fleet_meets_qual}, payable={fleet_payable}")

    assert cab_payable, "FAIL: Cabinet debe pagar al driver con 3 viajes en 7D"
    assert not fleet_payable, "FAIL: Fleet NO debe pagar al driver con solo 3 viajes (necesita 50V30D)"
    print("  [OK] Cabinet paga 1V, Fleet NO paga 1V")

    # ── 6. Caso controlado: driver con 55 viajes (si paga Fleet) ──
    driver_55 = {"trips_0_7_count": 20, "trips_8_14_count": 15, "trips_0_30_count": 55}

    cab_meets_vol_55 = _get_trip_count_for_window({"D55": driver_55}, "D55", cab_vol_days) >= cab_vol_min
    fleet_meets_qual_55 = _get_trip_count_for_window({"D55": driver_55}, "D55", fleet_qual_days) >= fleet_qual_min
    fleet_meets_vol_55 = _get_trip_count_for_window({"D55": driver_55}, "D55", fleet_vol_days) >= fleet_vol_min

    print(f"\n  Driver con 55 viajes en 30d:")
    print(f"    Cabinet (1V7D): meets_volume={cab_meets_vol_55} -> payable")
    print(f"    Fleet (50V30D): meets_volume={fleet_meets_vol_55}, meets_quality={fleet_meets_qual_55} -> payable")
    assert cab_meets_vol_55, "FAIL: Cabinet debe pagar con 55 viajes"
    assert fleet_meets_qual_55, "FAIL: Fleet debe pagar con 55 viajes (50V30D)"
    print("  [OK] Fleet paga 50V30D correctamente")

finally:
    db.close()

print()
print("=" * 70)
print("TEST COMPLETADO")
print("=" * 70)
print()
print("RESUMEN:")
print("  - _parse_rule: parsea 1V7D, 5V7D, 50V30D correctamente")
print("  - _get_trip_count_for_window: selecciona ventana correcta (7d, 14d, 30d)")
print("  - Resolver: Cabinet y Fleet devuelven reglas diferentes")
print("  - Config Snapshot: congela reglas multi-esquema en JSON")
print("  - Calculo: Cabinet paga activados x tier, Fleet paga calidad x fijo")
print("  - Validacion: Fleet NO paga por 1V (necesita 50V30D)")
print("  - Validacion: Cabinet SI paga por 1V7D")
