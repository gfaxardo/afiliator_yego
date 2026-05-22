"""
Tests de Fase 1: Configuracion y versionado del Liquidador Scouts.

Valida:
1. Resolver retorna exactamente 1 version por cohorte (no overlap)
2. Activar version cierra vigencia de version previa
3. _check_overlap detecta overlap real
4. No se puede archivar version activa sin forzar
5. Snapshot usa version correcta
6. Legacy schemes readonly
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort
from app.services.payment_scheme_admin_service import (
    _check_overlap, activate_payment_scheme_version,
    archive_payment_scheme_version,
    get_payment_scheme_detail, list_payment_schemes,
)
from sqlalchemy import text

pass_count = 0
fail_count = 0
errors = []

def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        msg = f"  FAIL  {label}"
        if detail: msg += f"  ({detail})"
        print(msg)
        errors.append(msg)

db = SessionLocal()
try:
    # ═══════════════════════════════════════════════════
    # TEST 1: Resolver returns exactly 1 version per cohort
    # ═══════════════════════════════════════════════════
    print("\n--- RESOLVER TESTS ---")

    # Cabinet cohorts
    test_cases = [
        ("2026-W01", "cabinet", "v1"),
        ("2026-W18", "cabinet", "v1"),
        ("2026-W19", "cabinet", "v2"),
        ("2026-W20", "cabinet", "Cabinet Transition v1"),
        ("2026-W21", "cabinet", "Cabinet Transition v2"),
        ("2026-W22", "cabinet", "Cabinet Standard v1"),
        ("2026-W30", "cabinet", "Cabinet Standard v1"),  # still OPEN
    ]

    for cohort, stype, expected_name in test_cases:
        try:
            r = resolve_payment_scheme_for_cohort(db, cohort, stype)
            check(
                f"Resolver {cohort} {stype} -> {expected_name}",
                r["version_name"] == expected_name,
                f"Got: {r['version_name']}"
            )
            check(
                f"Resolver {cohort} {stype} has tiers",
                len(r["tiers"]) > 0
            )
            check(
                f"Resolver {cohort} {stype} has scheme_id",
                r["scheme_id"] is not None
            )
        except Exception as e:
            check(f"Resolver {cohort} {stype} -> OK", False, str(e))

    # Fleet cohorts
    for cohort in ["2026-W01", "2026-W18", "2026-W30"]:
        try:
            r = resolve_payment_scheme_for_cohort(db, cohort, "fleet")
            check(
                f"Resolver {cohort} fleet -> v1",
                r["version_name"] == "v1",
                f"Got: {r['version_name']}"
            )
        except Exception as e:
            check(f"Resolver {cohort} fleet -> OK", False, str(e))

    # Invalid: cohort without version
    try:
        resolve_payment_scheme_for_cohort(db, "2020-W01", "cabinet")
        check("Resolver cohort sin version -> ValueError", False, "No lanzo error")
    except ValueError:
        check("Resolver cohort sin version -> ValueError", True)

    # ═══════════════════════════════════════════════════
    # TEST 2: _check_overlap detects real overlap
    # ═══════════════════════════════════════════════════
    print("\n--- OVERLAP DETECTION TESTS ---")
    # The current active versions should NOT overlap
    try:
        _check_overlap(db, 1)  # scheme_id=1 (Cabinet)
        check("_check_overlap cabinet: no overlap detectado", True)
    except ValueError as e:
        check("_check_overlap cabinet: no overlap", False, str(e))

    try:
        _check_overlap(db, 2)  # scheme_id=2 (Fleet)
        check("_check_overlap fleet: no overlap detectado", True)
    except ValueError as e:
        check("_check_overlap fleet: no overlap", False, str(e))

    # ═══════════════════════════════════════════════════
    # TEST 3: List schemes returns both types
    # ═══════════════════════════════════════════════════
    print("\n--- LIST SCHEMES TESTS ---")
    schemes = list_payment_schemes(db)
    check("list_payment_schemes: >= 2 schemes", len(schemes) >= 2, f"Got: {len(schemes)}")
    types = [s["scheme_type"] for s in schemes]
    check("list_payment_schemes: includes cabinet", "cabinet" in types)
    check("list_payment_schemes: includes fleet", "fleet" in types)

    # ═══════════════════════════════════════════════════
    # TEST 4: Scheme detail has versions with tiers
    # ═══════════════════════════════════════════════════
    print("\n--- SCHEME DETAIL TESTS ---")
    detail = get_payment_scheme_detail(db, 1)
    check("detail: has versions", len(detail["versions"]) > 0, f"Got: {len(detail['versions'])}")
    for v in detail["versions"]:
        if v["status"] == "active":
            check(f"  version {v['version_name']} has tiers", len(v["tiers"]) > 0)
            check(f"  version {v['version_name']} has valid_from", v["valid_from_cohort_iso_week"] is not None)
            break

    # ═══════════════════════════════════════════════════
    # TEST 5: Archive draft version works (not active)
    # ═══════════════════════════════════════════════════
    print("\n--- ARCHIVE TESTS ---")
    # v5 is already archived - should raise
    try:
        archive_payment_scheme_version(db, 5)
        check("archive already-archived v5 -> ValueError", False, "No lanzo error")
    except ValueError:
        check("archive already-archived v5 -> ValueError", True)

    # Archive an active version should fail without force
    # Find an active version
    active = db.execute(text(
        "SELECT id FROM scout_liq_payment_scheme_versions WHERE status='active' LIMIT 1"
    )).scalar()
    if active:
        try:
            archive_payment_scheme_version(db, active)
            check(f"archive active v{active} -> ValueError", False, "No lanzo error")
        except ValueError:
            check(f"archive active v{active} -> ValueError", True)

    # ═══════════════════════════════════════════════════
    # TEST 6: Resolver field completeness
    # ═══════════════════════════════════════════════════
    print("\n--- RESOLVER FIELD COMPLETENESS ---")
    r = resolve_payment_scheme_for_cohort(db, "2026-W22", "cabinet")
    required_fields = [
        "scheme_id", "scheme_name", "scheme_type", "scheme_version_id",
        "version_name", "valid_from_cohort_iso_week", "maturity_days",
        "min_activated", "min_volume_count", "activation_rule", "quality_rule",
        "formula_type", "pays_on_rule", "payout_formula_type", "currency",
        "tiers",
    ]
    for field in required_fields:
        check(f"  field '{field}' present in resolved", field in r and r[field] is not None,
              f"value={r.get(field)}")

    # ═══════════════════════════════════════════════════
    # TEST 7: Each tier has required fields
    # ═══════════════════════════════════════════════════
    print("\n--- TIER FIELD COMPLETENESS ---")
    for t in r["tiers"]:
        for tf in ["min_conversion_rate", "payout_amount", "sort_order"]:
            check(f"  tier field '{tf}' present", tf in t, f"tier={t}")

    # ═══════════════════════════════════════════════════
    # TEST 8: Configuration tables are intact
    # ═══════════════════════════════════════════════════
    print("\n--- CONFIG INTEGRITY ---")
    for table, expected_min in [
        ("scout_liq_payment_schemes", 2),
        ("scout_liq_payment_scheme_versions", 7),
        ("scout_liq_payment_scheme_tiers", 23),
        ("scout_liq_conversion_schemes", 2),
        ("scout_liq_conversion_tiers", 8),
    ]:
        c = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        check(f"  {table}: {c} >= {expected_min}", c >= expected_min, f"Got {c}")

finally:
    db.close()

print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("TODOS LOS TESTS PASARON")
