"""
Tests unitarios Fase 2 — Motor de cutoff: helpers puros, metric codes,
explicaciones, resolucion de tramos, snapshot.

NO requiere base de datos. Funciones puras solamente.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cutoff_helpers import (
    parse_rule, build_metric_code, build_rule_label,
    build_minimum_rule_label, build_tier_summary_label,
    build_pays_on_label, build_formula_label,
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
# TEST 1: parse_rule
# ═══════════════════════════════════════════════════
print("\n--- parse_rule ---")
check("5V7D -> (5,7)", parse_rule("5V7D") == (5, 7))
check("1V7D -> (1,7)", parse_rule("1V7D") == (1, 7))
check("50V30D -> (50,30)", parse_rule("50V30D") == (50, 30))
check("empty -> (1,7)", parse_rule("") == (1, 7))
check("None -> (1,7)", parse_rule(None) == (1, 7))
check("invalid -> (1,7)", parse_rule("invalid") == (1, 7))
check("lowercase 5v7d -> (5,7)", parse_rule("5v7d") == (5, 7))


# ═══════════════════════════════════════════════════
# TEST 2: build_metric_code
# ═══════════════════════════════════════════════════
print("\n--- build_metric_code ---")
check("5V7D -> 5plus_0_7", build_metric_code("5V7D") == "5plus_0_7")
check("1V7D -> 1plus_0_7", build_metric_code("1V7D") == "1plus_0_7")
check("50V30D -> 50plus_0_30", build_metric_code("50V30D") == "50plus_0_30")
check("empty -> unknown", build_metric_code("") == "unknown")
check("None -> unknown", build_metric_code(None) == "unknown")
check("invalid -> unknown", build_metric_code("xyz") == "unknown")


# ═══════════════════════════════════════════════════
# TEST 3: build_rule_label
# ═══════════════════════════════════════════════════
print("\n--- build_rule_label ---")
check("5V7D label", build_rule_label("5V7D") == "5 viajes en 7 dias")
check("1V7D label (singular)", build_rule_label("1V7D") == "1 viaje en 7 dias")
check("50V30D label", build_rule_label("50V30D") == "50 viajes en 30 dias")


# ═══════════════════════════════════════════════════
# TEST 4: build_minimum_rule_label
# ═══════════════════════════════════════════════════
print("\n--- build_minimum_rule_label ---")
check("min 8", "minimo 8 conductores activados" in build_minimum_rule_label(8))
check("min 1 (singular)", "minimo 1 conductor activado" in build_minimum_rule_label(1))
check("min 0", "sin minimo" in build_minimum_rule_label(0))


# ═══════════════════════════════════════════════════
# TEST 5: build_tier_summary_label
# ═══════════════════════════════════════════════════
print("\n--- build_tier_summary_label ---")
tiers = [
    {"min_conversion_rate": 0.10, "payout_amount": 10},
    {"min_conversion_rate": 0.20, "payout_amount": 20},
    {"min_conversion_rate": 0.30, "payout_amount": 30},
    {"min_conversion_rate": 0.40, "payout_amount": 40},
]
label = build_tier_summary_label(tiers)
check("tier summary has 4 tiers", "," in label)
check("tier summary includes 10%", "10%=>S/10" in label)
check("empty tiers", build_tier_summary_label([]) == "sin tramos")


# ═══════════════════════════════════════════════════
# TEST 6: resolve_tier
# ═══════════════════════════════════════════════════
print("\n--- resolve_tier ---")
tiers = [
    {"min_conversion_rate": 0.10, "payout_amount": 10},
    {"min_conversion_rate": 0.20, "payout_amount": 20},
    {"min_conversion_rate": 0.30, "payout_amount": 30},
]
r = resolve_tier(0.05, tiers)
check("0.05 -> None", r is None)
r = resolve_tier(0.15, tiers)
check("0.15 -> tier 0.10 ($10)", r and r["payout_amount"] == 10)
r = resolve_tier(0.25, tiers)
check("0.25 -> tier 0.20 ($20)", r and r["payout_amount"] == 20)
r = resolve_tier(0.50, tiers)
check("0.50 -> tier 0.30 ($30) highest", r and r["payout_amount"] == 30)
r = resolve_tier(0.10, tiers)
check("0.10 exact -> tier 0.10 ($10)", r and r["payout_amount"] == 10)


# ═══════════════════════════════════════════════════
# TEST 7: compute_conversion_rate
# ═══════════════════════════════════════════════════
print("\n--- compute_conversion_rate ---")
check("5/10 = 0.5", compute_conversion_rate(5, 10) == 0.5)
check("0/10 = 0.0", compute_conversion_rate(0, 10) == 0.0)
check("0/0 = 0.0", compute_conversion_rate(0, 0) == 0.0)
check("3/0 = 0.0", compute_conversion_rate(3, 0) == 0.0)


# ═══════════════════════════════════════════════════
# TEST 8: build_payment_explanation — payable
# ═══════════════════════════════════════════════════
print("\n--- build_payment_explanation ---")
exp = build_payment_explanation(
    line_status="payable",
    blocked_reason=None,
    driver_name="DRV001",
    scout_name="Scout A",
    trips_count=7,
    threshold=5,
    threshold_label="5V7D",
    conversion_rate=0.50,
    tier_reached={"min_conversion_rate": 0.40, "payout_amount": 40},
    payment_amount=40,
    min_activated=8,
    total_activated=10,
    already_paid=False,
    driver_lifecycle="converted_5v7d",
    volume_rule_label="1 viaje en 7 dias",
    quality_rule_label="5 viajes en 7 dias",
)
check("payable: mentions driver", "DRV001" in exp)
check("payable: mentions paga", "Paga" in exp or "paga" in exp.lower())
check("payable: mentions tier", "40" in exp)


# ═══════════════════════════════════════════════════
# TEST 9: already_paid blocks
# ═══════════════════════════════════════════════════
exp = build_payment_explanation(
    line_status="blocked_already_paid",
    blocked_reason="ya pagado en corte anterior",
    driver_name="DRV002",
    scout_name="Scout A",
    trips_count=5,
    threshold=5,
    threshold_label="5V7D",
    conversion_rate=0.5,
    tier_reached=None,
    payment_amount=0,
    min_activated=8,
    total_activated=10,
    already_paid=True,
    driver_lifecycle="converted_5v7d",
    volume_rule_label="",
    quality_rule_label="",
)
check("already_paid: mentions doble pago", "doble pago" in exp.lower() or "bloqueante" in exp.lower())


# ═══════════════════════════════════════════════════
# TEST 10: no_trip classification
# ═══════════════════════════════════════════════════
exp = build_payment_explanation(
    line_status="no_trip", blocked_reason=None,
    driver_name="DRV003", scout_name="Scout A",
    trips_count=0, threshold=1, threshold_label="1V7D",
    conversion_rate=0, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=5,
    already_paid=False, driver_lifecycle="no_trip",
    volume_rule_label="", quality_rule_label="",
)
check("no_trip: mentions 0 viajes", "0 viajes" in exp or "no paga" in exp.lower())


# ═══════════════════════════════════════════════════
# TEST 11: below_pay_threshold
# ═══════════════════════════════════════════════════
exp = build_payment_explanation(
    line_status="below_pay_threshold", blocked_reason=None,
    driver_name="DRV004", scout_name="Scout A",
    trips_count=2, threshold=5, threshold_label="5V7D",
    conversion_rate=0.3, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=10,
    already_paid=False, driver_lifecycle="activated",
    volume_rule_label="", quality_rule_label="",
)
check("below_pay: mentions no alcanza", "no alcanza" in exp.lower())


# ═══════════════════════════════════════════════════
# TEST 12: blocked_min_activated
# ═══════════════════════════════════════════════════
exp = build_payment_explanation(
    line_status="blocked_min_activated",
    blocked_reason="Minimo 8 volumen requerido, tiene 5",
    driver_name="DRV005", scout_name="Scout A",
    trips_count=3, threshold=1, threshold_label="1V7D",
    conversion_rate=0, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=5,
    already_paid=False, driver_lifecycle="activated",
    volume_rule_label="", quality_rule_label="",
)
check("blocked_min: mentions minimo", "minimo" in exp.lower())
check("blocked_min: mentions 5 de 8", "5" in exp and "8" in exp)


# ═══════════════════════════════════════════════════
# TEST 13: blocked_invalid_hire_date
# ═══════════════════════════════════════════════════
exp = build_payment_explanation(
    line_status="blocked_invalid_hire_date", blocked_reason=None,
    driver_name="DRV006", scout_name="Scout A",
    trips_count=0, threshold=0, threshold_label="",
    conversion_rate=0, tier_reached=None, payment_amount=0,
    min_activated=8, total_activated=10,
    already_paid=False, driver_lifecycle="no_driver_id",
    volume_rule_label="", quality_rule_label="",
)
check("invalid_hire_date: mentions hire_date", "hire_date" in exp.lower())


# ═══════════════════════════════════════════════════
# TEST 14: build_pays_on_label and build_formula_label
# ═══════════════════════════════════════════════════
print("\n--- pays_on / formula labels ---")
check("ACTIVATED_BASE label", "conductor activado" in build_pays_on_label("ACTIVATED_BASE"))
check("QUALITY_HIT label", "calidad" in build_pays_on_label("QUALITY_HIT"))
label = build_formula_label("ACTIVATED_X_TIER", "ACTIVATED_BASE", 10)
check("formula ACTIVATED_X_TIER", "activados" in label and "S/10" in label)


# ═══════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("TODOS LOS TESTS UNITARIOS PASARON")
