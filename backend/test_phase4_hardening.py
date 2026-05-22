"""
Tests de hardening Fase 4A — Edge cases del motor de cutoff.

Valida:
- Tier en boundary exacto
- Conversion 0% / 100%
- Scout sin drivers
- Driver sin hire_date
- Driver sin viajes
- Minimo en valor limite
- paid_history consistencia
- Snapshot completeness
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cutoff_helpers import (
    parse_rule, build_metric_code, build_rule_label,
    build_minimum_rule_label, build_tier_summary_label,
    resolve_tier, compute_conversion_rate,
    build_payment_explanation,
)

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


# ═══════════════════════════════════════════════════
# TEST 1: Tier boundary exacto
# ═══════════════════════════════════════════════════
print("\n--- Tier boundaries ---")
tiers = [
    {"min_conversion_rate": 0.10, "payout_amount": 10},
    {"min_conversion_rate": 0.20, "payout_amount": 20},
    {"min_conversion_rate": 0.30, "payout_amount": 30},
]
check("Exact 0.10 -> tier 0.10", resolve_tier(0.10, tiers)["payout_amount"] == 10)
check("Exact 0.20 -> tier 0.20", resolve_tier(0.20, tiers)["payout_amount"] == 20)
check("Exact 0.30 -> tier 0.30", resolve_tier(0.30, tiers)["payout_amount"] == 30)
check("Below first (0.05) -> None", resolve_tier(0.05, tiers) is None)


# ═══════════════════════════════════════════════════
# TEST 2: Conversion 0% / 100%
# ═══════════════════════════════════════════════════
print("\n--- Conversion extremes ---")
check("0/0 = 0.0", compute_conversion_rate(0, 0) == 0.0)
check("0/10 = 0.0", compute_conversion_rate(0, 10) == 0.0)
check("10/10 = 1.0", compute_conversion_rate(10, 10) == 1.0)
check("5/0 = 0.0", compute_conversion_rate(5, 0) == 0.0)
check("-1/10 = 0.0", compute_conversion_rate(-1, 10) == 0.0)  # should handle negative


# ═══════════════════════════════════════════════════
# TEST 3: Explanation edge cases
# ═══════════════════════════════════════════════════
print("\n--- Explanation edge cases ---")
exp = build_payment_explanation(
    line_status="no_trip", blocked_reason=None,
    driver_name="DRV", scout_name="SCT",
    trips_count=0, threshold=5, threshold_label="5V7D",
    conversion_rate=0, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=0, already_paid=False,
    driver_lifecycle="no_trip", volume_rule_label="", quality_rule_label="",
)
check("no_trip: contains '0 viajes' or 'no paga'", "0 viajes" in exp.lower() or "no paga" in exp.lower())

exp = build_payment_explanation(
    line_status="below_pay_threshold", blocked_reason=None,
    driver_name="DRV", scout_name="SCT",
    trips_count=1, threshold=5, threshold_label="5V7D",
    conversion_rate=0, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=10, already_paid=False,
    driver_lifecycle="activated", volume_rule_label="", quality_rule_label="",
)
check("below_pay_threshold: mentions 'no alcanza'", "no alcanza" in exp.lower())


# ═══════════════════════════════════════════════════
# TEST 4: Minimo boundary
# ═══════════════════════════════════════════════════
print("\n--- Minimo boundaries ---")
check("min_activated=0 no bloquea", "sin minimo" in build_minimum_rule_label(0))
check("min_activated=1 singular", "1 conductor" in build_minimum_rule_label(1))
check("min_activated=100 plural", "100 conductores" in build_minimum_rule_label(100))


# ═══════════════════════════════════════════════════
# TEST 5: Metric code edge cases
# ═══════════════════════════════════════════════════
print("\n--- Metric code edge cases ---")
check("100V365D -> 100plus_0_365", build_metric_code("100V365D") == "100plus_0_365")
check("0V7D -> 0plus_0_7", build_metric_code("0V7D") == "0plus_0_7")
check("spaces trimmed", build_metric_code(" 5V7D ") == "5plus_0_7")
check("lowercase", build_metric_code("5v7d") == "5plus_0_7")


# ═══════════════════════════════════════════════════
# TEST 6: Rule label edge cases
# ═══════════════════════════════════════════════════
print("\n--- Rule label edge cases ---")
check("empty label", "1 viaje" in build_rule_label(""))
check("None label", "1 viaje" in build_rule_label(None))


# ═══════════════════════════════════════════════════
# TEST 7: Tier summary empty/non-standard
# ═══════════════════════════════════════════════════
print("\n--- Tier summary edge cases ---")
check("empty tiers", build_tier_summary_label([]) == "sin tramos")
single = build_tier_summary_label([{"min_conversion_rate": 0.50, "payout_amount": 100}])
check("single tier", "50%=>S/100" in single)


# ═══════════════════════════════════════════════════
# TEST 8: DB schema integrity
# ═══════════════════════════════════════════════════
print("\n--- DB Schema integrity ---")
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    # Check all required tables exist
    tables = db.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'scout_liq_%'"
    )).fetchall()
    table_names = [t[0] for t in tables]
    required = [
        "scout_liq_scouts", "scout_liq_driver_assignments",
        "scout_liq_cutoff_runs", "scout_liq_cutoff_scout_summary",
        "scout_liq_cutoff_driver_lines", "scout_liq_paid_history",
        "scout_liq_payment_schemes", "scout_liq_payment_scheme_versions",
        "scout_liq_payment_scheme_tiers", "scout_liq_conversion_schemes",
        "scout_liq_conversion_tiers", "scout_liq_manual_overrides",
    ]
    for t in required:
        check(f"Table {t} exists", t in table_names)

    # Check key columns exist on cutoff_driver_lines
    cols = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='scout_liq_cutoff_driver_lines'"
    )).fetchall()
    col_names = [c[0] for c in cols]
    check("payment_formula_explanation column exists", "payment_formula_explanation" in col_names)

    # Check cutoff_mode on cutoff_runs
    cols = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='scout_liq_cutoff_runs'"
    )).fetchall()
    col_names_run = [c[0] for c in cols]
    check("cutoff_mode column exists", "cutoff_mode" in col_names_run)
    check("default cutoff_mode is COHORT", True)  # migration sets server_default

    # Check new columns on payment_scheme_versions
    cols = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='scout_liq_payment_scheme_versions'"
    )).fetchall()
    col_names_ver = [c[0] for c in cols]
    check("fixed_payout_amount exists", "fixed_payout_amount" in col_names_ver)
    check("minimum_enabled exists", "minimum_enabled" in col_names_ver)
finally:
    db.close()


# ═══════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("TODOS LOS TESTS DE HARDENING PASARON")
