"""
Payment Scheme Admin Service — SOURCE OF TRUTH para administrar reglas de pago.

CRUD para PaymentScheme + PaymentSchemeVersion + PaymentSchemeTier.
Este es el UNICO sistema activo de configuracion. El legacy (ConversionScheme)
esta deprecado y es solo lectura historica.

Reglas de negocio:
1. No se editan versiones activas. Cambios crean nueva version.
2. Activar version cierra automaticamente la vigencia de la version activa anterior.
3. _check_overlap() garantiza que no haya 2 versiones activas solapadas en tiempo.
4. Resolver retorna exactamente 1 version por (cohorte, scheme_type).
5. No se puede archivar version usada por cutoff pagado/locked.
6. Tiers validados (rate 0-1, amount >= 0, sin duplicados, min 1 tier).
7. min_activated > 0, maturity_days > 0.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    PaymentScheme,
    PaymentSchemeVersion,
    PaymentSchemeTier,
)
from app.services.cohort_service import iso_week_dates

COHORT_RE = re.compile(r"^\d{4}-W\d{2}$")


def _validate_cohort_format(cohort_iso_week: str):
    if not COHORT_RE.match(cohort_iso_week):
        raise ValueError(f"Formato invalido: '{cohort_iso_week}'. Debe ser YYYY-WNN (ej. 2026-W18)")


def previous_iso_week(cohort_iso_week: str) -> str:
    """Devuelve la semana ISO anterior a la dada."""
    _validate_cohort_format(cohort_iso_week)
    yr_str, wk_str = cohort_iso_week.split("-W")
    yr, wk = int(yr_str), int(wk_str)
    monday, _ = iso_week_dates(yr, wk)
    prev_monday = monday - timedelta(days=7)
    prev_iso = prev_monday.isocalendar()
    return f"{prev_iso[0]}-W{prev_iso[1]:02d}"


# ═══════════════════════════════════════════════════════════════════════════
# LIST / DETAIL
# ═══════════════════════════════════════════════════════════════════════════

def list_payment_schemes(db: Session) -> List[Dict[str, Any]]:
    schemes = db.query(PaymentScheme).filter(PaymentScheme.is_active == True).order_by(PaymentScheme.name).all()
    result = []
    for s in schemes:
        active = (
            db.query(PaymentSchemeVersion)
            .filter(PaymentSchemeVersion.scheme_id == s.id, PaymentSchemeVersion.status == "active")
            .order_by(PaymentSchemeVersion.valid_from_cohort_iso_week.desc())
            .first()
        )
        result.append({
            "scheme_id": s.id,
            "name": s.name,
            "scheme_type": s.scheme_type,
            "description": s.description,
            "is_active": s.is_active,
            "active_version_id": active.id if active else None,
            "active_version_name": active.version_name if active else None,
            "active_since_cohort": active.valid_from_cohort_iso_week if active else None,
            "version_count": len(s.versions),
            "created_at": str(s.created_at) if s.created_at else None,
        })
    return result


def get_payment_scheme_detail(db: Session, scheme_id: int) -> Dict[str, Any]:
    scheme = db.query(PaymentScheme).filter(PaymentScheme.id == scheme_id).first()
    if not scheme:
        raise ValueError(f"Scheme {scheme_id} no encontrado")

    versions = []
    for v in sorted(scheme.versions, key=lambda x: x.valid_from_cohort_iso_week or ""):
        tiers = (
            db.query(PaymentSchemeTier)
            .filter(PaymentSchemeTier.scheme_version_id == v.id)
            .order_by(PaymentSchemeTier.min_conversion_rate)
            .all()
        )
        versions.append({
            "version_id": v.id,
            "version_name": v.version_name,
            "valid_from_cohort_iso_week": v.valid_from_cohort_iso_week,
            "valid_to_cohort_iso_week": v.valid_to_cohort_iso_week,
            "maturity_days": v.maturity_days,
            "maturity_window_days": v.maturity_window_days or v.maturity_days,
            "min_activated": v.min_activated,
            "min_volume_count": v.min_volume_count or v.min_activated,
            "activation_rule": v.activation_rule,
            "volume_rule": v.volume_rule or v.activation_rule,
            "quality_rule": v.quality_rule,
            "counts_volume_rule": v.counts_volume_rule or v.activation_rule,
            "counts_quality_rule": v.counts_quality_rule or v.quality_rule,
            "formula_type": v.formula_type,
            "pays_on_rule": v.pays_on_rule or "",
            "payout_formula_type": v.payout_formula_type or v.formula_type,
            "currency": v.currency,
            "status": v.status,
            "created_at": str(v.created_at) if v.created_at else None,
            "activated_at": str(v.activated_at) if v.activated_at else None,
            "archived_at": str(v.archived_at) if v.archived_at else None,
            "fixed_payout_amount": float(v.fixed_payout_amount) if v.fixed_payout_amount else None,
            "minimum_enabled": bool(v.minimum_enabled),
            "tiers": [
                {
                    "min_conversion_rate": float(t.min_conversion_rate),
                    "payout_amount": float(t.payout_amount),
                    "sort_order": t.sort_order,
                }
                for t in tiers
            ],
        })

    return {
        "scheme_id": scheme.id,
        "name": scheme.name,
        "scheme_type": scheme.scheme_type,
        "description": scheme.description,
        "is_active": scheme.is_active,
        "created_at": str(scheme.created_at) if scheme.created_at else None,
        "versions": versions,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CREATE SCHEME
# ═══════════════════════════════════════════════════════════════════════════

def create_payment_scheme(
    db: Session,
    name: str,
    scheme_type: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    if not name.strip():
        raise ValueError("name es requerido")
    scheme_type = scheme_type.lower().strip()
    if scheme_type not in ("cabinet", "fleet", "custom"):
        raise ValueError(f"scheme_type invalido: '{scheme_type}'. Use cabinet, fleet o custom")

    existing = db.query(PaymentScheme).filter(
        PaymentScheme.name == name.strip(),
        PaymentScheme.scheme_type == scheme_type,
    ).first()
    if existing:
        raise ValueError(f"Ya existe un esquema '{name}' con tipo '{scheme_type}' (id={existing.id})")

    scheme = PaymentScheme(
        name=name.strip(),
        scheme_type=scheme_type,
        description=description,
        is_active=True,
    )
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return {"scheme_id": scheme.id, "name": scheme.name, "scheme_type": scheme.scheme_type}


# ═══════════════════════════════════════════════════════════════════════════
# CREATE VERSION (DRAFT)
# ═══════════════════════════════════════════════════════════════════════════

def create_payment_scheme_version(
    db: Session,
    scheme_id: int,
    version_name: str,
    valid_from_cohort_iso_week: str,
    maturity_days: int,
    min_activated: int,
    activation_rule: str,
    quality_rule: str,
    formula_type: str,
    currency: str,
    tiers: List[Dict[str, Any]],
    volume_rule: Optional[str] = None,
    min_volume_count: Optional[int] = None,
    pays_on_rule: Optional[str] = None,
    payout_formula_type: Optional[str] = None,
    counts_volume_rule: Optional[str] = None,
    counts_quality_rule: Optional[str] = None,
    maturity_window_days: Optional[int] = None,
    fixed_payout_amount: Optional[float] = None,
    minimum_enabled: bool = True,
) -> Dict[str, Any]:
    scheme = db.query(PaymentScheme).filter(PaymentScheme.id == scheme_id).first()
    if not scheme:
        raise ValueError(f"Scheme {scheme_id} no encontrado")

    _validate_cohort_format(valid_from_cohort_iso_week)

    if maturity_days < 1:
        raise ValueError("maturity_days debe ser > 0")
    if min_activated < 1:
        raise ValueError("min_activated debe ser > 0")
    if not version_name.strip():
        raise ValueError("version_name es requerido")

    # Validate tiers
    _validate_tiers(tiers)

    # Check no duplicate version name for this scheme
    existing = db.query(PaymentSchemeVersion).filter(
        PaymentSchemeVersion.scheme_id == scheme_id,
        PaymentSchemeVersion.version_name == version_name.strip(),
    ).first()
    if existing:
        raise ValueError(f"Ya existe version '{version_name}' en este esquema (id={existing.id})")

    version = PaymentSchemeVersion(
        scheme_id=scheme_id,
        version_name=version_name.strip(),
        valid_from_cohort_iso_week=valid_from_cohort_iso_week,
        valid_to_cohort_iso_week=None,
        maturity_days=maturity_days,
        min_activated=min_activated,
        activation_rule=activation_rule,
        quality_rule=quality_rule,
        formula_type=formula_type,
        currency=currency,
        volume_rule=volume_rule or activation_rule,
        min_volume_count=min_volume_count or min_activated,
        pays_on_rule=pays_on_rule or ("ACTIVATED_BASE" if formula_type == "ACTIVATED_X_TIER" else "QUALITY_HIT" if formula_type == "QUALITY_X_FIXED" else formula_type),
        payout_formula_type=payout_formula_type or formula_type,
        counts_volume_rule=counts_volume_rule or activation_rule,
        counts_quality_rule=counts_quality_rule or quality_rule,
        maturity_window_days=maturity_window_days or maturity_days,
        fixed_payout_amount=Decimal(str(fixed_payout_amount)) if fixed_payout_amount else None,
        minimum_enabled=minimum_enabled,
        status="draft",
    )
    db.add(version)
    db.flush()

    for i, t in enumerate(tiers):
        db.add(PaymentSchemeTier(
            scheme_version_id=version.id,
            min_conversion_rate=Decimal(str(t["min_conversion_rate"])),
            payout_amount=Decimal(str(t["payout_amount"])),
            sort_order=i,
        ))

    db.commit()
    db.refresh(version)

    return {
        "version_id": version.id,
        "version_name": version.version_name,
        "scheme_id": scheme_id,
        "valid_from_cohort_iso_week": version.valid_from_cohort_iso_week,
        "status": version.status,
        "tiers_count": len(tiers),
    }


def _validate_tiers(tiers: List[Dict[str, Any]]):
    if not tiers:
        raise ValueError("Debe incluir al menos 1 tier")
    rates = []
    for t in tiers:
        rate = float(t.get("min_conversion_rate", 0))
        amount = float(t.get("payout_amount", 0))
        if rate < 0 or rate > 1:
            raise ValueError(f"min_conversion_rate debe estar entre 0 y 1: {rate}")
        if amount < 0:
            raise ValueError(f"payout_amount debe ser >= 0: {amount}")
        rates.append(rate)
    if len(rates) != len(set(rates)):
        raise ValueError("No se permiten min_conversion_rate duplicados")
    if rates != sorted(rates):
        raise ValueError("Los tiers deben estar ordenados ascendentemente por min_conversion_rate")


# ═══════════════════════════════════════════════════════════════════════════
# ACTIVATE VERSION
# ═══════════════════════════════════════════════════════════════════════════

def activate_payment_scheme_version(db: Session, version_id: int) -> Dict[str, Any]:
    version = db.query(PaymentSchemeVersion).filter(PaymentSchemeVersion.id == version_id).first()
    if not version:
        raise ValueError(f"Version {version_id} no encontrada")
    if version.status == "active":
        raise ValueError(f"Version {version_id} ya esta activa")
    if version.status == "archived":
        raise ValueError(f"Version {version_id} esta archivada, no se puede activar")

    scheme_id = version.scheme_id

    # Find current active version for this scheme
    current_active = db.query(PaymentSchemeVersion).filter(
        PaymentSchemeVersion.scheme_id == scheme_id,
        PaymentSchemeVersion.status == "active",
        PaymentSchemeVersion.id != version_id,
    ).order_by(PaymentSchemeVersion.valid_from_cohort_iso_week.desc()).first()

    if current_active:
        if version.valid_from_cohort_iso_week <= current_active.valid_from_cohort_iso_week:
            raise ValueError(
                f"La nueva version ({version.version_name}) empieza en {version.valid_from_cohort_iso_week}, "
                f"que es <= la version activa actual ({current_active.version_name}) "
                f"que empieza en {current_active.valid_from_cohort_iso_week}. "
                f"La nueva version debe empezar despues de la activa."
            )
        prev_week = previous_iso_week(version.valid_from_cohort_iso_week)
        current_active.valid_to_cohort_iso_week = prev_week

    # Activate new version
    version.status = "active"
    version.activated_at = datetime.now()

    # Check no overlap after modification
    _check_overlap(db, scheme_id)

    db.commit()
    db.refresh(version)

    return {
        "version_id": version.id,
        "version_name": version.version_name,
        "scheme_id": scheme_id,
        "status": version.status,
        "valid_from_cohort_iso_week": version.valid_from_cohort_iso_week,
        "activated_at": str(version.activated_at),
        "previous_active_archived": current_active.version_name if current_active else None,
        "previous_active_closed_at": str(current_active.valid_to_cohort_iso_week) if current_active else None,
    }


def _check_overlap(db: Session, scheme_id: int):
    """Verifica que no haya overlap entre versiones activas del mismo scheme."""
    active_versions = db.query(PaymentSchemeVersion).filter(
        PaymentSchemeVersion.scheme_id == scheme_id,
        PaymentSchemeVersion.status == "active",
    ).order_by(PaymentSchemeVersion.valid_from_cohort_iso_week).all()

    for i in range(len(active_versions)):
        for j in range(i + 1, len(active_versions)):
            a = active_versions[i]
            b = active_versions[j]
            a_end = a.valid_to_cohort_iso_week or "9999-W99"
            b_start = b.valid_from_cohort_iso_week
            if b_start <= a_end:
                raise ValueError(
                    f"Overlap detectado: version {a.version_name} ({a.valid_from_cohort_iso_week} -> {a.valid_to_cohort_iso_week or 'NULL'}) "
                    f"solapa con version {b.version_name} ({b.valid_from_cohort_iso_week} -> {b.valid_to_cohort_iso_week or 'NULL'})"
                )


# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVE VERSION
# ═══════════════════════════════════════════════════════════════════════════

def archive_payment_scheme_version(db: Session, version_id: int) -> Dict[str, Any]:
    version = db.query(PaymentSchemeVersion).filter(PaymentSchemeVersion.id == version_id).first()
    if not version:
        raise ValueError(f"Version {version_id} no encontrada")
    if version.status == "archived":
        raise ValueError(f"Version {version_id} ya esta archivada")
    if version.status == "active":
        raise ValueError(
            f"Version {version_id} esta activa. "
            f"Active una nueva version primero para cerrar esta automaticamente, "
            f"o use force_archive=true para forzar."
        )

    # Check not used by any cutoff (paid or locked)
    used = db.execute(text("""
        SELECT cr.id, cr.status, cr.cohort_iso_week
        FROM scout_liq_cutoff_runs cr
        WHERE cr.config_snapshot LIKE :pattern
    """), {"pattern": f"%\"scheme_version_id\": {version_id}%"}).fetchall()

    if used:
        ids = ", ".join(f"{r[0]}({r[1]})" for r in used[:5])
        raise ValueError(
            f"La version {version_id} esta siendo usada por {len(used)} corte(s): {ids}. "
            f"No se puede archivar una version usada."
        )

    version.status = "archived"
    version.archived_at = datetime.now()
    db.commit()
    return {"version_id": version.id, "status": version.status, "archived_at": str(version.archived_at)}


# ═══════════════════════════════════════════════════════════════════════════
# HISTORY
# ═══════════════════════════════════════════════════════════════════════════

def get_payment_schemes_history(
    db: Session,
    scheme_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = db.query(PaymentSchemeVersion).join(PaymentScheme)
    if scheme_type:
        q = q.filter(PaymentScheme.scheme_type == scheme_type.lower().strip())
    versions = q.order_by(
        PaymentScheme.scheme_type,
        PaymentSchemeVersion.valid_from_cohort_iso_week,
    ).all()

    result = []
    for v in versions:
        result.append({
            "version_id": v.id,
            "scheme_name": v.scheme.name,
            "scheme_type": v.scheme.scheme_type,
            "version_name": v.version_name,
            "valid_from_cohort_iso_week": v.valid_from_cohort_iso_week,
            "valid_to_cohort_iso_week": v.valid_to_cohort_iso_week,
            "maturity_days": v.maturity_days,
            "min_activated": v.min_activated,
            "status": v.status,
            "created_at": str(v.created_at) if v.created_at else None,
            "activated_at": str(v.activated_at) if v.activated_at else None,
            "archived_at": str(v.archived_at) if v.archived_at else None,
        })
    return result
