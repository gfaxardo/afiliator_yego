"""
Tests: Motor Avanzado de Reglas de Pago
Modalidades: driver_milestone, cohort_quality_tier, aggregate_volume_bonus
origin_scope: cabinet, fleet, all
block_scope: driver_global, driver_rule, driver_metric_origin, none
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cutoff_engine import _build_config_snapshot_from_resolved
from app.services.cutoff_helpers import (
    parse_rule, build_metric_code, build_rule_label,
    resolve_tier, compute_conversion_rate,
)

pass_count = 0
fail_count = 0

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

# ─────────────────────────────────────────────────
# TEST 1: Cabinet calidad porcentual (cohort_quality_tier)
# ─────────────────────────────────────────────────
print("\n--- Test 1: Cabinet calidad porcentual ---")
resolved = {
    "scheme_id": 1, "scheme_name": "Cabinet Standard", "scheme_type": "cabinet",
    "scheme_version_id": 10, "version_name": "v1",
    "valid_from_cohort_iso_week": "2026-W20",
    "maturity_days": 7, "maturity_window_days": 7,
    "min_activated": 10, "min_volume_count": 10,
    "activation_rule": "1V7D", "volume_rule": "1V7D",
    "quality_rule": "5V7D",
    "counts_volume_rule": "1V7D", "counts_quality_rule": "5V7D",
    "formula_type": "ACTIVATED_X_TIER",
    "pays_on_rule": "QUALITY_HIT",
    "payout_formula_type": "ACTIVATED_X_TIER",
    "currency": "PEN",
    "tiers": [
        {"min_conversion_rate": 0.10, "payout_amount": 10.0, "sort_order": 0},
        {"min_conversion_rate": 0.20, "payout_amount": 20.0, "sort_order": 1},
        {"min_conversion_rate": 0.30, "payout_amount": 30.0, "sort_order": 2},
        {"min_conversion_rate": 0.40, "payout_amount": 40.0, "sort_order": 3},
    ],
}
snap = json.loads(_build_config_snapshot_from_resolved(resolved))
check("rule_type = cohort_quality_tier", snap.get("rule_type") == "cohort_quality_tier")
check("origin_scope = cabinet", snap.get("origin_scope") == "cabinet")
check("min_activated = 10", snap.get("min_activated") == 10)
check("quality_rule = 5V7D", snap.get("quality_rule") == "5V7D")
check("has tiers (4)", len(snap.get("tiers", [])) == 4)
check("tiers min 10%", snap["tiers"][0]["min_conversion_rate"] == 0.10)
check("rule_type_label mentions calidad", "calidad" in snap.get("rule_type_label", "").lower())

# ─────────────────────────────────────────────────
# TEST 2: Fleet hito individual (driver_milestone)
# ─────────────────────────────────────────────────
print("\n--- Test 2: Fleet hito individual ---")
resolved2 = {
    "scheme_id": 2, "scheme_name": "Fleet Milestone 50V/30D", "scheme_type": "fleet",
    "scheme_version_id": 20, "version_name": "v1",
    "valid_from_cohort_iso_week": "2026-W20",
    "maturity_days": 7, "maturity_window_days": 30,
    "min_activated": 0, "min_volume_count": 0,
    "activation_rule": "1V7D", "volume_rule": "1V7D",
    "quality_rule": "50V30D",
    "counts_volume_rule": "1V7D", "counts_quality_rule": "50V30D",
    "formula_type": "FIXED_PER_DRIVER",
    "pays_on_rule": "QUALITY_HIT",
    "payout_formula_type": "FIXED_PER_DRIVER",
    "currency": "PEN",
    "fixed_payout_amount": 20.0,
    "minimum_enabled": False,
    "tiers": [],
}
snap2 = json.loads(_build_config_snapshot_from_resolved(resolved2))
check("rule_type = driver_milestone", snap2.get("rule_type") == "driver_milestone")
check("origin_scope = fleet", snap2.get("origin_scope") == "fleet")
check("payout_formula_type = FIXED_PER_DRIVER", snap2.get("payout_formula_type") == "FIXED_PER_DRIVER")
check("fixed amount = 20", snap2.get("fixed_payout_amount") == 20.0)
check("rule_type_label mentions hito", "hito" in snap2.get("rule_type_label", "").lower())

# ─────────────────────────────────────────────────
# TEST 3: Fleet bono agregado (aggregate_volume_bonus)
# ─────────────────────────────────────────────────
print("\n--- Test 3: Fleet bono agregado ---")
resolved3 = {
    "scheme_id": 3, "scheme_name": "Fleet Bonus 50V/30D", "scheme_type": "fleet",
    "scheme_version_id": 30, "version_name": "v1",
    "valid_from_cohort_iso_week": "2026-W20",
    "maturity_days": 7, "maturity_window_days": 30,
    "min_activated": 0, "min_volume_count": 0,
    "activation_rule": "1V7D", "volume_rule": "1V7D",
    "quality_rule": "50V30D",
    "counts_volume_rule": "1V7D", "counts_quality_rule": "50V30D",
    "formula_type": "AGGREGATE_VOLUME_BONUS",
    "pays_on_rule": "QUALITY_HIT",
    "payout_formula_type": "AGGREGATE_VOLUME_BONUS",
    "currency": "PEN",
    "fixed_payout_amount": 500.0,
    "cohort_target_count": 30,
    "block_scope": "driver_metric_origin",
    "minimum_enabled": False,
    "tiers": [],
}
snap3 = json.loads(_build_config_snapshot_from_resolved(resolved3))
check("rule_type = aggregate_volume_bonus", snap3.get("rule_type") == "aggregate_volume_bonus")
check("origin_scope = fleet", snap3.get("origin_scope") == "fleet")
check("cohort_target_count = 30", snap3.get("cohort_target_count") == 30)
check("block_scope = driver_metric_origin", snap3.get("block_scope") == "driver_metric_origin")
check("fixed bonus = 500", snap3.get("fixed_payout_amount") == 500.0)
check("rule_type_label mentions bono", "bono" in snap3.get("rule_type_label", "").lower())

# ─────────────────────────────────────────────────
# TEST 4: origin_scope = all
# ─────────────────────────────────────────────────
print("\n--- Test 4: origin_scope = all ---")
resolved4 = {
    "scheme_id": 4, "scheme_name": "All 1V/7D", "scheme_type": "all",
    "scheme_version_id": 40, "version_name": "v1",
    "valid_from_cohort_iso_week": "2026-W20",
    "maturity_days": 7, "maturity_window_days": 7,
    "min_activated": 0, "min_volume_count": 0,
    "activation_rule": "1V7D", "volume_rule": "1V7D",
    "quality_rule": "1V7D",
    "counts_volume_rule": "1V7D", "counts_quality_rule": "1V7D",
    "formula_type": "FIXED_PER_DRIVER",
    "pays_on_rule": "ACTIVATED_BASE",
    "payout_formula_type": "FIXED_PER_DRIVER",
    "currency": "PEN",
    "fixed_payout_amount": 10.0,
    "minimum_enabled": False,
    "tiers": [],
}
snap4 = json.loads(_build_config_snapshot_from_resolved(resolved4))
check("origin_scope = all", snap4.get("origin_scope") == "all")
check("rule_type = driver_milestone for all", snap4.get("rule_type") == "driver_milestone")

# ─────────────────────────────────────────────────
# TEST 5: Tiers resolucion (funciones puras)
# ─────────────────────────────────────────────────
print("\n--- Test 5: Tier resolution ---")
tiers = [
    {"min_conversion_rate": 0.10, "payout_amount": 10.0, "currency": "PEN"},
    {"min_conversion_rate": 0.20, "payout_amount": 20.0, "currency": "PEN"},
    {"min_conversion_rate": 0.30, "payout_amount": 30.0, "currency": "PEN"},
    {"min_conversion_rate": 0.40, "payout_amount": 40.0, "currency": "PEN"},
]
check("30% conv -> tier 30%", resolve_tier(0.30, tiers)["min_conversion_rate"] == 0.30)
check("30% conv -> amount 30", resolve_tier(0.30, tiers)["payout_amount"] == 30.0)
check("5% conv -> None", resolve_tier(0.05, tiers) is None)
check("50% conv -> highest (40%)", resolve_tier(0.50, tiers)["min_conversion_rate"] == 0.40)

# ─────────────────────────────────────────────────
# TEST 6: Metric code mapping
# ─────────────────────────────────────────────────
print("\n--- Test 6: Metric codes ---")
check("1V7D -> 1plus_0_7", build_metric_code("1V7D") == "1plus_0_7")
check("5V7D -> 5plus_0_7", build_metric_code("5V7D") == "5plus_0_7")
check("50V30D -> 50plus_0_30", build_metric_code("50V30D") == "50plus_0_30")

# ─────────────────────────────────────────────────
# TEST 7: Snapshot no pierde campos (completitud)
# ─────────────────────────────────────────────────
print("\n--- Test 7: Snapshot completeness ---")
required_keys = ["scheme_id", "scheme_name", "scheme_type", "version_name",
                 "rule_type", "rule_type_label", "origin_scope",
                 "min_activated", "currency", "tiers"]
for k in required_keys:
    check(f"snapshot has '{k}'", k in snap, f"missing {k}")

# ─────────────────────────────────────────────────
# TEST 8: Block scope propagation
# ─────────────────────────────────────────────────
print("\n--- Test 8: Block scope in snapshot ---")
check("default block_scope = driver_global", snap.get("block_scope") == "driver_global")
check("custom block_scope = driver_metric_origin", snap3.get("block_scope") == "driver_metric_origin")

# ─────────────────────────────────────────────────
# TEST 9: Cohort target count for aggregate
# ─────────────────────────────────────────────────
print("\n--- Test 9: Cohort target in snapshot ---")
check("aggregate has cohort_target_count=30", snap3.get("cohort_target_count") == 30)
check("non-aggregate lacks cohort_target_count or is 0", snap.get("cohort_target_count", 0) == 0)

print("\n==================================================")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count == 0:
    print("TODOS LOS TESTS DEL MOTOR AVANZADO PASARON")
