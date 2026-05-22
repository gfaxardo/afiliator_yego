"""
Cutoff Helpers — Pure, testable functions for the cutoff engine.

NO database access. NO side effects. Input → output only.

Used by cutoff_engine.py for:
- Parsing volume/quality rules
- Building metric codes from rules
- Building human-readable labels
- Building payment explanations per driver
- Resolving tiers from conversion rates
"""
from typing import Dict, List, Optional, Tuple


def parse_rule(rule_str: Optional[str]) -> Tuple[int, int]:
    """
    Parse a volume/quality rule string like '1V7D' or '50V30D'.
    Returns (min_count, window_days). Defaults to (1, 7) if unparseable.

    >>> parse_rule("5V7D")
    (5, 7)
    >>> parse_rule("50V30D")
    (50, 30)
    >>> parse_rule("")
    (1, 7)
    >>> parse_rule("invalid")
    (1, 7)
    """
    import re
    if not rule_str:
        return (1, 7)
    m = re.match(r'(\d+)V(\d+)D', str(rule_str).strip(), re.IGNORECASE)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (1, 7)


def build_metric_code(rule_str: Optional[str]) -> str:
    """
    Derive a metric code from a quality/volume rule string.

    Examples:
        "5V7D"    → "5plus_0_7"
        "1V7D"    → "1plus_0_7"
        "50V30D"  → "50plus_0_30"
        ""        → "unknown"
        "invalid" → "unknown"

    >>> build_metric_code("5V7D")
    '5plus_0_7'
    >>> build_metric_code("1V7D")
    '1plus_0_7'
    >>> build_metric_code("50V30D")
    '50plus_0_30'
    """
    count, days = parse_rule(rule_str)
    if not rule_str or not isinstance(rule_str, str):
        return "unknown"
    import re
    if not re.match(r'^\d+V\d+D$', str(rule_str).strip(), re.IGNORECASE):
        return "unknown"
    return f"{count}plus_0_{days}"


def build_rule_label(rule_str: Optional[str]) -> str:
    """
    Build a human-readable label from a rule string.

    >>> build_rule_label("5V7D")
    '5 viajes en 7 dias'
    >>> build_rule_label("1V7D")
    '1 viaje en 7 dias'
    >>> build_rule_label("50V30D")
    '50 viajes en 30 dias'
    """
    count, days = parse_rule(rule_str)
    viajes = "viaje" if count == 1 else "viajes"
    return f"{count} {viajes} en {days} dias"


def build_minimum_rule_label(min_activated: int) -> str:
    """Build human-readable minimum rule label."""
    if min_activated <= 0:
        return "sin minimo de activados"
    conductores = "conductor" if min_activated == 1 else "conductores"
    return f"minimo {min_activated} {conductores} activados"


def build_tier_summary_label(tiers: List[Dict]) -> str:
    """Build a compact tier summary like '10%=>S/10, 20%=>S/20'."""
    if not tiers:
        return "sin tramos"
    parts = []
    for t in sorted(tiers, key=lambda x: x.get("min_conversion_rate", 0)):
        rate = t.get("min_conversion_rate", 0)
        amount = t.get("payout_amount", t.get("payment_per_converted_driver", 0))
        parts.append(f"{float(rate)*100:.0f}%=>S/{float(amount):.0f}")
    return ", ".join(parts)


def build_pays_on_label(pays_on_rule: str) -> str:
    """Build human-readable pays_on label."""
    labels = {
        "ACTIVATED_BASE": "paga por conductor activado",
        "QUALITY_HIT": "paga por conductor con calidad",
    }
    return labels.get(pays_on_rule, f"paga por: {pays_on_rule}")


def build_formula_type_label(payout_formula_type: str, fixed_payout_amount: Optional[float] = None) -> str:
    """Build human-readable formula type label."""
    if payout_formula_type == "FIXED_PER_DRIVER" and fixed_payout_amount is not None:
        return f"Pago fijo S/{fixed_payout_amount:.0f} por driver"
    return "Conversion por tramo"


def build_formula_label(payout_formula_type: str, pays_on_rule: str, payment_per: float) -> str:
    """Build human-readable formula label."""
    if payout_formula_type == "ACTIVATED_X_TIER":
        base = "activados" if pays_on_rule == "ACTIVATED_BASE" else "calidad"
        return f"({base}) x S/{payment_per:.0f}"
    return f"{payout_formula_type}"


def resolve_tier(conversion_rate: float, tiers: List[Dict]) -> Optional[Dict]:
    """
    Find the highest applicable tier based on conversion rate.
    Tiers are walked in order; the last one whose min_conversion_rate
    is <= conversion_rate wins.

    >>> tiers = [
    ...   {"min_conversion_rate": 0.10, "payout_amount": 10},
    ...   {"min_conversion_rate": 0.20, "payout_amount": 20},
    ...   {"min_conversion_rate": 0.30, "payout_amount": 30},
    ... ]
    >>> resolve_tier(0.15, tiers)
    {'min_conversion_rate': 0.1, 'payout_amount': 10}
    >>> resolve_tier(0.25, tiers)
    {'min_conversion_rate': 0.2, 'payout_amount': 20}
    >>> resolve_tier(0.50, tiers)
    {'min_conversion_rate': 0.3, 'payout_amount': 30}
    >>> resolve_tier(0.05, tiers) is None
    True
    """
    tier_reached = None
    sorted_tiers = sorted(tiers, key=lambda t: t["min_conversion_rate"])
    for t in sorted_tiers:
        if conversion_rate >= t["min_conversion_rate"]:
            tier_reached = t
    return tier_reached


def compute_conversion_rate(numerator: int, denominator: int) -> float:
    """
    Compute conversion rate safely. Returns 0.0 if denominator is 0 or negative values.

    >>> compute_conversion_rate(5, 10)
    0.5
    >>> compute_conversion_rate(0, 0)
    0.0
    >>> compute_conversion_rate(3, 0)
    0.0
    >>> compute_conversion_rate(-1, 10)
    0.0
    """
    if denominator <= 0 or numerator < 0:
        return 0.0
    return numerator / denominator


def build_payment_explanation(
    line_status: str,
    blocked_reason: Optional[str],
    driver_name: str,
    scout_name: str,
    trips_count: int,
    threshold: int,
    threshold_label: str,
    conversion_rate: Optional[float],
    tier_reached: Optional[Dict],
    payment_amount: Optional[float],
    min_activated: int,
    total_activated: int,
    already_paid: bool,
    driver_lifecycle: str,
    volume_rule_label: str,
    quality_rule_label: str,
) -> str:
    """
    Build a human-readable explanation for why a driver was/wasn't paid.

    Returns a Spanish-language sentence explaining the decision.
    """
    if already_paid:
        return f"{driver_name}: ya tiene pago previo bloqueante. No paga (doble pago)."

    if line_status == "blocked_invalid_hire_date":
        return f"{driver_name}: sin hire_date valida. No se puede evaluar."

    if line_status == "blocked_min_activated":
        return (
            f"Scout {scout_name}: {total_activated} activados de {min_activated} requeridos. "
            f"No alcanza el minimo. {driver_name} no paga."
        )

    if line_status == "payable" and tier_reached:
        tier_pct = float(tier_reached.get("min_conversion_rate", 0)) * 100
        return (
            f"{driver_name}: {trips_count} viajes, cumple {threshold_label} (>= {threshold}). "
            f"Scout {scout_name}: conversion {conversion_rate*100:.1f}% alcanza tramo {tier_pct:.0f}%. "
            f"Paga S/{payment_amount:.0f}."
        )

    if line_status == "activated_no_tier":
        return (
            f"{driver_name}: cumple {threshold_label} ({trips_count} >= {threshold}), "
            f"pero scout {scout_name} no alcanzo ningun tramo (conv {conversion_rate*100:.1f}%). No paga."
        )

    if line_status == "no_trip":
        return f"{driver_name}: 0 viajes en ventana. No paga."

    if line_status == "below_pay_threshold":
        return (
            f"{driver_name}: {trips_count} viajes, no alcanza {threshold_label} "
            f"(requiere >= {threshold}). No paga."
        )

    return f"{driver_name}: estado={line_status}. Sin evaluacion de pago."
