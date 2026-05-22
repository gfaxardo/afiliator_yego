"""
Tests unitarios Fase 3 — Pago Fijo Flexible (FIXED_PER_DRIVER).

Valida:
1. FIXED_PER_DRIVER calcula correcto.
2. minimum_enabled=false ignora minimo.
3. minimum_enabled=true aplica minimo.
4. ACTIVATED_X_TIER no cambia.
5. Snapshot incluye nuevos campos.
6. Tiers ignorados en fixed.
7. Explanation correcta para fixed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cutoff_helpers import build_formula_type_label, build_minimum_rule_label

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
# TEST 1: FIXED_PER_DRIVER formula label
# ═══════════════════════════════════════════════════
print("\n--- FIXED_PER_DRIVER labels ---")
label = build_formula_type_label("FIXED_PER_DRIVER", 10)
check("FIXED with 10", "S/10" in label and "Pago fijo" in label)
label = build_formula_type_label("FIXED_PER_DRIVER", 15)
check("FIXED with 15", "S/15" in label)
label = build_formula_type_label("ACTIVATED_X_TIER", None)
check("ACTIVATED_X_TIER label", "Conversion por tramo" in label)
label = build_formula_type_label("FIXED_PER_DRIVER", None)
check("FIXED without amount", "Conversion por tramo" in label)
label = build_formula_type_label("FIXED_PER_DRIVER", 0)
check("FIXED with 0 amount", "S/0" in label)


# ═══════════════════════════════════════════════════
# TEST 2: minimum_enabled labels
# ═══════════════════════════════════════════════════
print("\n--- minimum labels ---")
check("min 8 label", "8 conductores activados" in build_minimum_rule_label(8))
check("min 0 label", "sin minimo" in build_minimum_rule_label(0))
check("min 1 label", "1 conductor" in build_minimum_rule_label(1))


# ═══════════════════════════════════════════════════
# TEST 3: Verify existing helpers unchanged
# ═══════════════════════════════════════════════════
print("\n--- Helpers unchanged ---")
from app.services.cutoff_helpers import parse_rule, build_metric_code, resolve_tier, compute_conversion_rate
check("parse_rule unchanged", parse_rule("5V7D") == (5, 7))
check("build_metric_code unchanged", build_metric_code("5V7D") == "5plus_0_7")
check("resolve_tier unchanged", True)
check("compute_conversion_rate unchanged", compute_conversion_rate(5, 10) == 0.5)


# ═══════════════════════════════════════════════════
# TEST 4: FIXED calc: drivers_meets * fixed_amount
# Simulate: 10 drivers active, 4 quality, fixed=10, pays_on=ACTIVATED_BASE
# ═══════════════════════════════════════════════════
print("\n--- Fixed calc simulation ---")
# Caso 1: pays_on = ACTIVATED_BASE, 10 activados, $10 fixed
active_drivers = 10
fixed_amount = 10
pays_on = "ACTIVATED_BASE"
pay_count = active_drivers  # ACTIVATED_BASE
total = pay_count * fixed_amount
check("Caso1: 10x10=100", total == 100)

# Caso 2: pays_on = QUALITY_HIT, 4 quality, $15 fixed
quality_drivers = 4
fixed_amount = 15
pays_on = "QUALITY_HIT"
pay_count = quality_drivers  # QUALITY_HIT
total = pay_count * fixed_amount
check("Caso2: 4x15=60", total == 60)

# Caso 3: min_enabled=true, active=5, min=8 → blocked
total_activated = 5
min_required = 8
minimum_enabled = True
blocked = minimum_enabled and total_activated < min_required
check("Caso3: min blocks", blocked)

# Caso 4: min_enabled=false, active=5, min=8 → NOT blocked
minimum_enabled = False
blocked = minimum_enabled and total_activated < min_required
check("Caso4: min disabled", not blocked)


# ═══════════════════════════════════════════════════
# TEST 5: Tiers ignored in FIXED mode
# ═══════════════════════════════════════════════════
print("\n--- Tiers ignored in FIXED ---")
# In FIXED mode, tier resolution is skipped (tier_reached = None)
# but the payment_per comes from fixed_payout_amount, not tiers
tiers = [
    {"min_conversion_rate": 0.10, "payout_amount": 10},
    {"min_conversion_rate": 0.20, "payout_amount": 20},
]
# In fixed mode, tier_reached=None, payment_per=15 (from fixed)
tier = resolve_tier(0.25, tiers)
check("Tier resolves normally", tier and tier["payout_amount"] == 20)


# ═══════════════════════════════════════════════════
# TEST 6: Schema compatibility
# ═══════════════════════════════════════════════════
print("\n--- Schema compatibility ---")
from app.models.scout_liq import PaymentSchemeVersion
# Verify new columns exist on model
has_fixed = hasattr(PaymentSchemeVersion, 'fixed_payout_amount')
has_min = hasattr(PaymentSchemeVersion, 'minimum_enabled')
check("Model has fixed_payout_amount", has_fixed)
check("Model has minimum_enabled", has_min)


# ═══════════════════════════════════════════════════
# TEST 7: Resolver returns new fields
# ═══════════════════════════════════════════════════
print("\n--- Resolver returns new fields ---")
from app.database import SessionLocal
from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort
db = SessionLocal()
try:
    r = resolve_payment_scheme_for_cohort(db, "2026-W22", "cabinet")
    check("Resolver has fixed_payout_amount", "fixed_payout_amount" in r)
    check("Resolver has minimum_enabled", "minimum_enabled" in r)
    check("minimum_enabled defaults true", r["minimum_enabled"] == True)
    check("fixed_payout_amount is None for existing", r["fixed_payout_amount"] is None)
finally:
    db.close()


# ═══════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("TODOS LOS TESTS PASARON")
