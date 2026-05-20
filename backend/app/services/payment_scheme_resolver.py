"""
Payment Scheme Resolver — Resuelve que version de reglas aplica para una cohorte ISO y tipo de esquema.

Dado cohort_iso_week (ej. "2026-W18") y scheme_type (cabinet | fleet | custom),
devuelve exactamente la version activa con sus tiers configurables.
"""

import re
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.scout_liq import (
    PaymentScheme,
    PaymentSchemeVersion,
    PaymentSchemeTier,
)

COHORT_RE = re.compile(r"^\d{4}-W\d{2}$")


def resolve_payment_scheme_for_cohort(
    db: Session,
    cohort_iso_week: str,
    scheme_type: str,
) -> Dict[str, Any]:
    """
    Resuelve la version de esquema de pago aplicable para una cohorte ISO.

    Raises:
        ValueError: cohorte invalida, tipo inexistente, overlap, sin tiers.
    """
    # ── 1. Validate cohort_iso_week format ──
    if not COHORT_RE.match(cohort_iso_week):
        raise ValueError(
            f"Formato de cohort_iso_week invalido: '{cohort_iso_week}'. "
            f"Formato esperado: YYYY-WNN (ej. 2026-W18)"
        )

    # ── 2. Normalize scheme_type ──
    scheme_type = scheme_type.lower().strip()

    # ── 3. Resolve version ──
    versions = (
        db.query(PaymentSchemeVersion)
        .join(PaymentScheme)
        .filter(
            PaymentScheme.is_active == True,
            PaymentScheme.scheme_type == scheme_type,
            PaymentSchemeVersion.status == "active",
            PaymentSchemeVersion.valid_from_cohort_iso_week <= cohort_iso_week,
            (
                (PaymentSchemeVersion.valid_to_cohort_iso_week == None)
                | (cohort_iso_week <= PaymentSchemeVersion.valid_to_cohort_iso_week)
            ),
        )
        .order_by(PaymentSchemeVersion.valid_from_cohort_iso_week.desc())
        .all()
    )

    if not versions:
        raise ValueError(
            f"No existe version activa de esquema '{scheme_type}' "
            f"para la cohorte '{cohort_iso_week}'."
        )

    if len(versions) > 1:
        names = ", ".join(
            f"{v.version_name} (desde {v.valid_from_cohort_iso_week})"
            for v in versions
        )
        raise ValueError(
            f"Overlap de versiones activas para esquema '{scheme_type}' "
            f"en cohorte '{cohort_iso_week}': {names}. "
            f"Corrija los rangos de vigencia."
        )

    version = versions[0]
    scheme = version.scheme

    # ── 4. Load tiers ──
    tiers = (
        db.query(PaymentSchemeTier)
        .filter(PaymentSchemeTier.scheme_version_id == version.id)
        .order_by(PaymentSchemeTier.min_conversion_rate)
        .all()
    )

    if not tiers:
        raise ValueError(
            f"El esquema '{scheme.name}' version '{version.version_name}' "
            f"no tiene tiers configurados."
        )

    return {
        "scheme_id": scheme.id,
        "scheme_name": scheme.name,
        "scheme_type": scheme.scheme_type,
        "description": scheme.description,
        "scheme_version_id": version.id,
        "version_name": version.version_name,
        "valid_from_cohort_iso_week": version.valid_from_cohort_iso_week,
        "valid_to_cohort_iso_week": version.valid_to_cohort_iso_week,
        "maturity_days": version.maturity_days,
        "maturity_window_days": version.maturity_window_days or version.maturity_days,
        "min_activated": version.min_activated,
        "min_volume_count": version.min_volume_count or version.min_activated,
        "activation_rule": version.activation_rule,
        "volume_rule": version.volume_rule or version.activation_rule,
        "quality_rule": version.quality_rule,
        "counts_volume_rule": version.counts_volume_rule or version.activation_rule,
        "counts_quality_rule": version.counts_quality_rule or version.quality_rule,
        "formula_type": version.formula_type,
        "pays_on_rule": version.pays_on_rule or "",
        "payout_formula_type": version.payout_formula_type or version.formula_type,
        "currency": version.currency,
        "tiers": [
            {
                "min_conversion_rate": float(t.min_conversion_rate),
                "payout_amount": float(t.payout_amount),
                "sort_order": t.sort_order,
            }
            for t in tiers
        ],
    }
