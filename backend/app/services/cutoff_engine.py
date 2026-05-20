"""
Cutoff Engine - Liquidador de Calidad Scouts Yego.
Calcula cortes de liquidacion usando conteos reales de viajes.
NO usa booleanos para calculo de pago.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    Scout, DriverAssignment, ConversionScheme, ConversionTier,
    CutoffRun, CutoffScoutSummary, CutoffDriverLine, PaidHistory,
)
from app.adapters.source_adapter import compute_trip_counts_batch
from app.services.cohort_service import iso_week_dates, cohort_maturity, get_iso_cohorts
from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort


def create_cutoff_run(
    db: Session,
    cutoff_name: str,
    hire_date_from: date,
    hire_date_to: date,
    scheme_id: int,
    origin_filter: Optional[str] = None,
    country_filter: Optional[str] = None,
    city_filter: Optional[str] = None,
    scout_type_filter: Optional[str] = None,
    created_by: Optional[str] = None,
) -> CutoffRun:
    scheme = db.query(ConversionScheme).filter(ConversionScheme.id == scheme_id).first()
    if not scheme:
        raise ValueError(f"Scheme {scheme_id} no encontrado")

    tiers = db.query(ConversionTier).filter(
        ConversionTier.scheme_id == scheme_id,
        ConversionTier.active == True,
    ).order_by(ConversionTier.min_conversion_rate).all()

    config_snapshot = {
        "scheme_id": scheme.id,
        "scheme_name": scheme.scheme_name,
        "origin": scheme.origin,
        "scout_type": scheme.scout_type,
        "min_affiliations": scheme.min_affiliations,
        "tiers": [
            {
                "min_conversion_rate": float(t.min_conversion_rate),
                "payment_per_converted_driver": float(t.payment_per_converted_driver),
                "currency": t.currency,
            }
            for t in tiers
        ],
        "conversion_metric": "5plus_0_7",
    }

    run = CutoffRun(
        cutoff_name=cutoff_name,
        hire_date_from=hire_date_from,
        hire_date_to=hire_date_to,
        origin_filter=origin_filter,
        country_filter=country_filter,
        city_filter=city_filter,
        scout_type_filter=scout_type_filter,
        status="draft",
        config_snapshot=json.dumps(config_snapshot),
        created_by=created_by,
        quality_data_contract_status="ok",
        conversion_metric_code="5plus_0_7",
        conversion_metric_status="pending",
        source_mapping_snapshot=json.dumps({
            "driver_id": "module_ct_cabinet_drivers.driver_id",
            "hire_date": "module_ct_cabinet_drivers.hire_date (CAST to DATE)",
            "origin": "module_ct_cabinet_drivers.origen",
            "trips_0_7_count": "JOIN trips_2025/trips_2026 via conductor_id (0-6 days inclusive, condicion=Completado)",
            "trips_8_14_count": "JOIN trips_2025/trips_2026 via conductor_id (7-13 days inclusive, condicion=Completado)",
            "conversion_rule": "5v7d_rate = converted_5v7d / activated_drivers",
            "payment_rule": "total_payable = activated_drivers × tier_amount",
        }),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _compute_lifecycle(trips_0_7: int, trips_8_14: int, trips_0_14: int) -> str:
    if trips_0_7 == 0 and trips_0_14 == 0:
        return "no_trip"
    if trips_0_7 >= 1 and trips_0_7 < 5:
        if trips_0_14 >= 5:
            return "converted_5v14d"
        return "activated"
    if trips_0_7 >= 5:
        return "converted_5v7d"
    if trips_0_14 >= 5:
        return "converted_5v14d"
    return "no_trip"


def calculate_cutoff(db: Session, cutoff_run_id: int) -> Dict[str, Any]:
    run = db.query(CutoffRun).filter(CutoffRun.id == cutoff_run_id).first()
    if not run:
        raise ValueError(f"Cutoff run {cutoff_run_id} no encontrado")
    if run.status not in ("draft",):
        raise ValueError(f"No se puede calcular cutoff en estado '{run.status}'")

    config = json.loads(run.config_snapshot) if run.config_snapshot else {}
    scheme = db.query(ConversionScheme).filter(ConversionScheme.id == config["scheme_id"]).first()
    tiers = sorted(config["tiers"], key=lambda t: t["min_conversion_rate"])
    min_aff = config.get("min_affiliations", 0)

    # Clean previous lines/summaries
    db.query(CutoffDriverLine).filter(CutoffDriverLine.cutoff_run_id == cutoff_run_id).delete()
    db.query(CutoffScoutSummary).filter(CutoffScoutSummary.cutoff_run_id == cutoff_run_id).delete()
    db.flush()

    # Get assignments matching window
    assignments = db.query(DriverAssignment, Scout).join(
        Scout, DriverAssignment.scout_id == Scout.id
    ).filter(
        DriverAssignment.status == "active",
        DriverAssignment.hire_date.is_(None) | (
            (DriverAssignment.hire_date >= run.hire_date_from)
            & (DriverAssignment.hire_date <= run.hire_date_to)
        ),
    )
    if run.origin_filter:
        assignments = assignments.filter(DriverAssignment.origin == run.origin_filter)
    if run.country_filter:
        assignments = assignments.filter(Scout.country == run.country_filter)
    assignments = assignments.all()

    # Also get assignments from source table directly for hire_date
    all_driver_ids = list(set(a.driver_id for a, _ in assignments))
    if not all_driver_ids:
        return {"status": "no_assignments", "message": "No hay asignaciones activas en la ventana"}

    # Compute real trip counts
    trip_counts = compute_trip_counts_batch(db, all_driver_ids)

    # Also get hire_date from source for drivers missing it in assignment
    source_dates = {}
    if all_driver_ids:
        placeholders = ", ".join(f":did{i}" for i in range(len(all_driver_ids)))
        params = {f"did{i}": did for i, did in enumerate(all_driver_ids)}
        rows = db.execute(text(
            f"SELECT driver_id, hire_date, origen, viajes_0_7, viajes_8_14, orders "
            f"FROM module_ct_cabinet_drivers WHERE driver_id IN ({placeholders})"
        ), params).fetchall()
        for r in rows:
            source_dates[r[0]] = {
                "hire_date_raw": r[1],
                "origin": r[2],
                "legacy_viajes_0_7": r[3],
                "legacy_viajes_8_14": r[4],
                "total_orders": r[5],
            }

    # Build lines grouped by scout
    scout_groups: Dict[int, Dict[str, Any]] = {}

    for assignment, scout in assignments:
        did = assignment.driver_id
        sid = scout.id

        if sid not in scout_groups:
            scout_groups[sid] = {
                "scout": scout,
                "scheme": scheme,
                "tiers": tiers,
                "lines": [],
            }

        src = source_dates.get(did, {})
        tc = trip_counts.get(did, {"trips_0_7_count": 0, "trips_8_14_count": 0})

        hire_date_raw = assignment.source_hire_date_raw or src.get("hire_date_raw")
        hire_date = assignment.hire_date
        if not hire_date and hire_date_raw:
            try:
                hire_date = datetime.strptime(str(hire_date_raw).strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

        trips_0_7 = tc["trips_0_7_count"]
        trips_8_14 = tc["trips_8_14_count"]
        trips_0_14 = trips_0_7 + trips_8_14

        q_status = "ok"
        warnings = []
        if not hire_date:
            q_status = "invalid_hire_date"
            warnings.append("Sin hire_date valida")

        line = CutoffDriverLine(
            cutoff_run_id=cutoff_run_id,
            scout_id=sid,
            driver_id=did,
            hire_date=hire_date,
            origin=assignment.origin or src.get("origin") or assignment.source_origin,
            trips_7d=trips_0_7,
            trips_14d=trips_0_14,
            trips_0_7_count=trips_0_7,
            trips_8_14_count=trips_8_14,
            trips_0_14_count=trips_0_14,
            total_orders=src.get("total_orders"),
            legacy_viajes_0_7_flag=src.get("legacy_viajes_0_7"),
            legacy_viajes_8_14_flag=src.get("legacy_viajes_8_14"),
            source_quality_status=q_status,
            source_warning="; ".join(warnings) if warnings else None,
            line_status="evaluating",
            already_paid=check_already_paid(db, did),
        )
        scout_groups[sid]["lines"].append(line)
        db.add(line)

    db.flush()

    # Compute summaries per scout
    for sid, group in scout_groups.items():
        lines = group["lines"]
        total_aff = len(lines)

        has_valid_date = [l for l in lines if l.source_quality_status == "ok" and l.trips_0_7_count is not None]
        drivers_1plus_0_7 = sum(1 for l in has_valid_date if (l.trips_0_7_count or 0) >= 1)
        drivers_5plus_0_7 = sum(1 for l in has_valid_date if (l.trips_0_7_count or 0) >= 5)
        drivers_1plus_8_14 = sum(1 for l in has_valid_date if (l.trips_8_14_count or 0) >= 1)
        drivers_5plus_0_14 = sum(1 for l in has_valid_date if (l.trips_0_14_count or 0) >= 5)
        not_converted = total_aff - drivers_5plus_0_7

        # Conversion rate: converted_5v7d / ACTIVATED (not total affiliates)
        total_activated = drivers_1plus_0_7
        rate_5plus = Decimal(str(drivers_5plus_0_7 / total_activated)) if total_activated > 0 else Decimal("0")
        rate_1plus = Decimal(str(drivers_1plus_0_7 / total_aff)) if total_aff > 0 else Decimal("0")
        rate_5plus_14 = Decimal(str(drivers_5plus_0_14 / total_activated)) if total_activated > 0 else Decimal("0")

        # Find applicable tier (based on conversion rate of activated drivers)
        tier_reached = None
        payment_per = Decimal("0")
        for t in tiers:
            if rate_5plus >= Decimal(str(t["min_conversion_rate"])):
                tier_reached = t
                payment_per = Decimal(str(t["payment_per_converted_driver"]))

        blocked_reason = None
        if total_activated < min_aff:
            blocked_reason = f"Minimo {min_aff} activados requerido, tiene {total_activated}"

        # Payment: activated_drivers × tier_amount (NOT converted × tier)
        amount = Decimal(str(total_activated)) * payment_per if tier_reached and not blocked_reason else Decimal("0")

        summary = CutoffScoutSummary(
            cutoff_run_id=cutoff_run_id,
            scout_id=sid,
            origin=group["lines"][0].origin if group["lines"] else None,
            total_affiliations=total_aff,
            total_activated=total_activated,
            converted_5trips_7d=drivers_5plus_0_7,
            total_converted_5v14d=drivers_5plus_0_14,
            not_converted=not_converted,
            conversion_rate=rate_5plus,
            conversion_rate_5v7d=rate_5plus,
            tier_reached=Decimal(str(tier_reached["min_conversion_rate"])) if tier_reached else None,
            payment_per_converted_driver=payment_per,
            payout_per_activated=payment_per,
            amount_calculated=amount,
            amount_approved=Decimal("0"),
            total_payable=amount,
            status="pending" if not blocked_reason else "blocked",
            blocked_reason=blocked_reason,
            drivers_1plus_0_7=drivers_1plus_0_7,
            drivers_5plus_0_7=drivers_5plus_0_7,
            drivers_1plus_8_14=drivers_1plus_8_14,
            drivers_5plus_0_14=drivers_5plus_0_14,
            conversion_1plus_0_7_rate=rate_1plus,
            conversion_5plus_0_7_rate=rate_5plus,
            conversion_5plus_0_14_rate=rate_5plus_14,
            metric_used="5plus_0_7",
            summary_status="ok",
        )
        db.add(summary)

        # Update line statuses with proper lifecycle states
        for l in lines:
            trips_0_7 = l.trips_0_7_count or 0
            trips_8_14 = l.trips_8_14_count or 0
            trips_0_14 = l.trips_0_14_count or 0

            if l.source_quality_status != "ok":
                l.line_status = "blocked_invalid_hire_date"
                l.blocked_reason = "sin hire_date valida"
                l.driver_lifecycle_status = "no_driver_id"
                l.eligible = False
            elif l.already_paid:
                l.line_status = "blocked_already_paid"
                l.blocked_reason = "ya pagado en corte anterior"
                l.payment_status = "blocked"
                l.driver_lifecycle_status = _compute_lifecycle(trips_0_7, trips_0_14 - trips_0_7, trips_0_14)
                l.eligible = False
            elif blocked_reason:
                l.line_status = "blocked_min_activated"
                l.blocked_reason = blocked_reason
                l.payment_status = "blocked"
                l.driver_lifecycle_status = _compute_lifecycle(trips_0_7, trips_0_14 - trips_0_7, trips_0_14)
                l.eligible = False
            else:
                l.driver_lifecycle_status = _compute_lifecycle(trips_0_7, trips_0_14 - trips_0_7, trips_0_14)
                l.is_converted_5trips_7d = trips_0_7 >= 5
                l.is_converted_5trips_14d = (trips_0_7 + trips_8_14) >= 5
                l.activated_flag = trips_0_7 >= 1

                if tier_reached and trips_0_7 >= 1:
                    l.line_status = "payable"
                    l.payment_status = "payable"
                    l.payout_eligible_flag = True
                    l.calculated_amount = payment_per
                    l.payment_rule = f"{tier_reached['min_conversion_rate']}% -> {payment_per} {tier_reached['currency']}"
                    l.eligible = True
                elif trips_0_7 >= 1:
                    l.line_status = "activated_no_tier"
                    l.payment_status = "blocked"
                    l.blocked_reason = "no_conversion_tier"
                    l.payout_eligible_flag = False
                    l.eligible = False
                else:
                    l.line_status = "no_trip"
                    l.payment_status = "blocked"
                    l.blocked_reason = "no_activation"
                    l.payout_eligible_flag = False
                    l.eligible = False

    run.status = "calculated"
    run.conversion_metric_status = "ok"
    excluded_invalid = sum(1 for _, g in scout_groups.items() for l in g["lines"] if l.source_quality_status != "ok")
    run.excluded_invalid_hire_date_count = excluded_invalid
    run.excluded_missing_trip_counts_count = 0
    run.total_source_drivers_count = len(all_driver_ids)
    run.unassigned_count = 0
    db.commit()

    return {"status": "calculated", "cutoff_run_id": cutoff_run_id, "scouts_evaluated": len(scout_groups)}


def check_already_paid(db: Session, driver_id: str) -> bool:
    row = db.execute(
        text("SELECT COUNT(*) FROM scout_liq_paid_history WHERE driver_id = :did AND blocks_future_payment = true"),
        {"did": driver_id},
    ).scalar()
    return (row or 0) > 0


def get_cutoff_summary(db: Session, cutoff_run_id: int) -> List[Dict]:
    rows = db.query(CutoffScoutSummary, Scout.scout_name).join(
        Scout, CutoffScoutSummary.scout_id == Scout.id
    ).filter(CutoffScoutSummary.cutoff_run_id == cutoff_run_id).order_by(
        CutoffScoutSummary.amount_calculated.desc()
    ).all()
    return [
        {
            "id": s.id,
            "scout_id": s.scout_id,
            "scout_name": name,
            "origin": s.origin,
            "total_affiliations": s.total_affiliations,
            "total_activated": s.total_activated,
            "drivers_1plus_0_7": s.drivers_1plus_0_7,
            "drivers_5plus_0_7": s.drivers_5plus_0_7,
            "drivers_1plus_8_14": s.drivers_1plus_8_14,
            "drivers_5plus_0_14": s.drivers_5plus_0_14,
            "total_converted_5v14d": s.total_converted_5v14d,
            "not_converted": s.not_converted,
            "conversion_rate": float(s.conversion_rate) if s.conversion_rate else 0,
            "conversion_rate_5v7d": float(s.conversion_rate_5v7d) if s.conversion_rate_5v7d else 0,
            "conversion_5plus_0_7_rate": float(s.conversion_5plus_0_7_rate) if s.conversion_5plus_0_7_rate else 0,
            "tier_reached": float(s.tier_reached) if s.tier_reached else None,
            "payment_per_converted_driver": float(s.payment_per_converted_driver) if s.payment_per_converted_driver else 0,
            "payout_per_activated": float(s.payout_per_activated) if s.payout_per_activated else 0,
            "amount_calculated": float(s.amount_calculated) if s.amount_calculated else 0,
            "amount_approved": float(s.amount_approved) if s.amount_approved else 0,
            "total_payable": float(s.total_payable) if s.total_payable else 0,
            "status": s.status,
            "blocked_reason": s.blocked_reason,
            "metric_used": s.metric_used,
        }
        for s, name in rows
    ]


def get_cutoff_lines(db: Session, cutoff_run_id: int, scout_id: Optional[int] = None) -> List[Dict]:
    q = db.query(CutoffDriverLine).filter(CutoffDriverLine.cutoff_run_id == cutoff_run_id)
    if scout_id:
        q = q.filter(CutoffDriverLine.scout_id == scout_id)
    lines = q.order_by(CutoffDriverLine.scout_id, CutoffDriverLine.trips_0_7_count.desc()).all()
    return [
        {
            "id": l.id,
            "scout_id": l.scout_id,
            "driver_id": l.driver_id,
            "hire_date": str(l.hire_date) if l.hire_date else None,
            "origin": l.origin,
            "trips_0_7_count": l.trips_0_7_count,
            "trips_8_14_count": l.trips_8_14_count,
            "trips_0_14_count": l.trips_0_14_count,
            "total_orders": l.total_orders,
            "legacy_viajes_0_7_flag": l.legacy_viajes_0_7_flag,
            "legacy_viajes_8_14_flag": l.legacy_viajes_8_14_flag,
            "activated_flag": l.activated_flag,
            "is_converted_5trips_7d": l.is_converted_5trips_7d,
            "is_converted_5trips_14d": l.is_converted_5trips_14d,
            "driver_lifecycle_status": l.driver_lifecycle_status,
            "line_status": l.line_status,
            "payment_status": l.payment_status,
            "blocked_reason": l.blocked_reason,
            "eligible": l.eligible,
            "already_paid": l.already_paid,
            "payout_eligible_flag": l.payout_eligible_flag,
            "calculated_amount": float(l.calculated_amount) if l.calculated_amount else None,
            "payment_rule": l.payment_rule,
            "source_quality_status": l.source_quality_status,
            "source_warning": l.source_warning,
        }
        for l in lines
    ]


def review_cutoff(db: Session, cutoff_run_id: int) -> Dict[str, Any]:
    run = db.query(CutoffRun).filter(CutoffRun.id == cutoff_run_id).first()
    if not run:
        raise ValueError(f"Cutoff run {cutoff_run_id} no encontrado")
    if run.status not in ("calculated",):
        raise ValueError(f"No se puede revisar cutoff en estado '{run.status}'")
    run.status = "reviewed"
    db.commit()
    return {"status": "reviewed", "cutoff_run_id": cutoff_run_id}


def approve_cutoff(db: Session, cutoff_run_id: int, approved_by: Optional[str] = None) -> Dict[str, Any]:
    run = db.query(CutoffRun).filter(CutoffRun.id == cutoff_run_id).first()
    if not run:
        raise ValueError(f"Cutoff run {cutoff_run_id} no encontrado")
    if run.status not in ("reviewed",):
        raise ValueError(f"No se puede aprobar cutoff en estado '{run.status}'")
    if run.quality_data_contract_status != "ok":
        raise ValueError("No se puede aprobar: quality_data_contract_status no es 'ok'")
    if run.conversion_metric_status != "ok":
        raise ValueError("No se puede aprobar: conversion_metric_status no es 'ok'")

    run.status = "approved"
    run.approved_by = approved_by
    run.approved_at = datetime.now()
    db.commit()
    return {"status": "approved", "cutoff_run_id": cutoff_run_id}


def mark_cutoff_paid(db: Session, cutoff_run_id: int) -> Dict[str, Any]:
    run = db.query(CutoffRun).filter(CutoffRun.id == cutoff_run_id).first()
    if not run:
        raise ValueError(f"Cutoff run {cutoff_run_id} no encontrado")
    if run.status != "approved":
        raise ValueError(f"No se puede pagar cutoff en estado '{run.status}'")

    summaries = db.query(CutoffScoutSummary).filter(
        CutoffScoutSummary.cutoff_run_id == cutoff_run_id,
        CutoffScoutSummary.status == "pending",
    ).all()

    for s in summaries:
        s.status = "paid"
        s.total_payable = s.amount_calculated
        s.amount_approved = s.amount_calculated
        lines = db.query(CutoffDriverLine).filter(
            CutoffDriverLine.cutoff_run_id == cutoff_run_id,
            CutoffDriverLine.scout_id == s.scout_id,
            CutoffDriverLine.payout_eligible_flag == True,
        ).all()
        for l in lines:
            config = json.loads(run.config_snapshot) if run.config_snapshot else {}
            scheme_id = config.get("scheme_id")
            scheme_name = config.get("scheme_name", "")
            ph = PaidHistory(
                cutoff_run_id=cutoff_run_id,
                scout_id=s.scout_id,
                driver_id=l.driver_id,
                origin=l.origin,
                payment_rule=l.payment_rule,
                amount_paid=l.calculated_amount or s.payout_per_activated,
                currency="PEN",
                paid_at=datetime.now(),
                import_source="cutoff_engine",
                payment_component="scout_driver_payment",
                payment_scheme_id=scheme_id,
                payment_scheme_name=scheme_name,
                payment_scheme_type="quality_conversion",
                cutoff_window_from=run.hire_date_from,
                cutoff_window_to=run.hire_date_to,
                status="paid",
                blocks_future_payment=True,
            )
            db.add(ph)
            l.line_status = "paid"
            l.payment_status = "paid"

    run.status = "paid"
    run.paid_at = datetime.now()
    db.commit()
    return {"status": "paid", "cutoff_run_id": cutoff_run_id, "scouts_paid": len(summaries)}


# ═══════════════════════════════════════════════════════════════════════════
# CORTE DESDE COHORTE ISO
# ═══════════════════════════════════════════════════════════════════════════

def create_cutoff_from_cohort(
    db: Session,
    cohort_iso_week: str,
    scheme_type: str,
    scheme_id: Optional[int] = None,
    origin_filter: Optional[str] = None,
    scout_type_filter: Optional[str] = None,
    created_by: Optional[str] = None,
    force_override: bool = False,
) -> Dict[str, Any]:
    """
    Crea un cutoff desde una cohorte ISO madura, resolviendo automaticamente
    la version de esquema de pago aplicable via payment_scheme_resolver.

    scheme_type: cabinet | fleet | custom (preferido)
    scheme_id: deprecado — solo para compatibilidad legacy con ConversionScheme
    """
    # ── 1. Buscar cohorte ──
    cohorts = get_iso_cohorts(db)
    cohort = next((c for c in cohorts if c["cohort_iso_week"] == cohort_iso_week), None)
    if not cohort:
        raise ValueError(f"Cohorte '{cohort_iso_week}' no encontrada. Use /operation/cohorts para ver las disponibles.")

    # ── 2. Validar madurez ──
    if cohort["readiness_status"] == "open":
        raise ValueError(
            f"Cohorte '{cohort_iso_week}' aun no ha madurado. "
            f"Madura el {cohort['maturity_completed_at']}. "
            f"Faltan {(datetime.strptime(cohort['maturity_completed_at'], '%Y-%m-%d').date() - date.today()).days} dias."
        )

    # ── 3. Resolver esquema de pago versionado ──
    if scheme_id and not scheme_type:
        # Legacy fallback: usar ConversionScheme
        legacy_scheme = db.query(ConversionScheme).filter(ConversionScheme.id == scheme_id).first()
        if not legacy_scheme:
            raise ValueError(f"Legacy scheme {scheme_id} no encontrado")
        resolved = _build_legacy_scheme_dict(legacy_scheme, db)
    else:
        if not scheme_type:
            raise ValueError(
                "Se requiere scheme_type (cabinet | fleet | custom) o scheme_id (legacy). "
                "Ejemplo: scheme_type=cabinet"
            )
        resolved = resolve_payment_scheme_for_cohort(db, cohort_iso_week, scheme_type)

    # ── 4. Validar no duplicar cortes activos ──
    existing = db.query(CutoffRun).filter(
        CutoffRun.cohort_iso_week == cohort_iso_week
    ).order_by(CutoffRun.created_at.desc()).all()

    if existing:
        latest = existing[0]
        if latest.status == "paid":
            raise ValueError(
                f"Cohorte '{cohort_iso_week}' ya tiene un corte PAGADO (id={latest.id}). "
                f"No se puede crear un nuevo corte."
            )
        if latest.status in ("approved", "reviewed", "calculated"):
            if force_override:
                db.query(CutoffDriverLine).filter(CutoffDriverLine.cutoff_run_id == latest.id).delete()
                db.query(CutoffScoutSummary).filter(CutoffScoutSummary.cutoff_run_id == latest.id).delete()
                latest.status = "draft"
                latest.origin_filter = origin_filter
                latest.scout_type_filter = scout_type_filter or None
                latest.maturity_days = resolved["maturity_days"]
                latest.maturity_completed_at = cohort_maturity(
                    latest.cohort_to, resolved["maturity_days"]
                ) if latest.cohort_to else None
                latest.snapshot_locked_at = datetime.now()
                latest.config_snapshot = _build_config_snapshot_from_resolved(resolved)
                db.commit()
                result = calculate_cutoff(db, latest.id)
                return _build_response(latest, cohort_iso_week, resolved, result, idempotent=True, previous_status="locked_recalculated")
            return _build_response(latest, cohort_iso_week, resolved,
                {"status": "existing", "message": f"Cutoff ya existe en estado '{latest.status}'"},
                idempotent=True, previous_status=latest.status)
        if latest.status == "draft":
            latest.config_snapshot = _build_config_snapshot_from_resolved(resolved)
            latest.maturity_days = resolved["maturity_days"]
            db.commit()
            result = calculate_cutoff(db, latest.id)
            return _build_response(latest, cohort_iso_week, resolved, result, idempotent=True, previous_status="draft")

    # ── 5. Crear cutoff con campos de cohorte + esquema versionado ──
    cohort_from_date = datetime.strptime(cohort["cohort_from"], "%Y-%m-%d").date()
    cohort_to_date = datetime.strptime(cohort["cohort_to"], "%Y-%m-%d").date()
    maturity_at = cohort_maturity(cohort_to_date, resolved["maturity_days"])
    config_snapshot = _build_config_snapshot_from_resolved(resolved)
    cutoff_name = f"Corte {resolved['scheme_type']} {cohort['cohort_label']} ({cohort_iso_week})"

    run = CutoffRun(
        cutoff_name=cutoff_name,
        hire_date_from=cohort_from_date,
        hire_date_to=cohort_to_date,
        origin_filter=origin_filter,
        scout_type_filter=scout_type_filter or resolved.get("scheme_type"),
        status="draft",
        config_snapshot=config_snapshot,
        created_by=created_by,
        quality_data_contract_status="ok",
        conversion_metric_code="5plus_0_7",
        conversion_metric_status="pending",
        source_mapping_snapshot=json.dumps({
            "driver_id": "module_ct_cabinet_drivers.driver_id",
            "hire_date": "module_ct_cabinet_drivers.hire_date (CAST to DATE)",
            "origin": "module_ct_cabinet_drivers.origen",
            "trips_0_7_count": "JOIN trips_2025/trips_2026 via conductor_id (0-6 days inclusive, condicion=Completado)",
            "trips_8_14_count": "JOIN trips_2025/trips_2026 via conductor_id (7-13 days inclusive, condicion=Completado)",
            "conversion_rule": "5v7d_rate = converted_5v7d / activated_drivers",
            "payment_rule": "total_payable = activated_drivers x tier_amount",
            "cohort_model": "ISO week based — ventana = cohort_from/cohort_to",
            "scheme_model": "versionado — PaymentScheme resolver",
        }),
        cohort_iso_week=cohort_iso_week,
        cohort_from=cohort_from_date,
        cohort_to=cohort_to_date,
        maturity_days=resolved["maturity_days"],
        maturity_completed_at=maturity_at,
        ready_to_liquidate=True,
        snapshot_locked_at=datetime.now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # ── 6. Calcular ──
    result = calculate_cutoff(db, run.id)

    return _build_response(run, cohort_iso_week, resolved, result, idempotent=False)


def _build_response(
    run: CutoffRun,
    cohort_iso_week: str,
    resolved: dict,
    calculation: dict,
    idempotent: bool = False,
    previous_status: Optional[str] = None,
) -> Dict[str, Any]:
    resp = {
        "cutoff_run_id": run.id,
        "cutoff_name": run.cutoff_name,
        "cohort_iso_week": cohort_iso_week,
        "scheme_name": resolved["scheme_name"],
        "scheme_type": resolved["scheme_type"],
        "scheme_version_id": resolved.get("scheme_version_id"),
        "version_name": resolved.get("version_name"),
        "status": run.status,
        "cohort_from": str(run.cohort_from) if run.cohort_from else None,
        "cohort_to": str(run.cohort_to) if run.cohort_to else None,
        "maturity_days": run.maturity_days,
        "maturity_completed_at": str(run.maturity_completed_at) if run.maturity_completed_at else None,
        "ready_to_liquidate": run.ready_to_liquidate,
        "snapshot_locked_at": str(run.snapshot_locked_at) if run.snapshot_locked_at else None,
        "calculation": calculation,
        "idempotent": idempotent,
    }
    if previous_status:
        resp["previous_status"] = previous_status
    return resp


def _build_legacy_scheme_dict(scheme, db: Session) -> dict:
    """Construye un dict compatible con el formato del resolver desde ConversionScheme legacy."""
    tiers = db.query(ConversionTier).filter(
        ConversionTier.scheme_id == scheme.id,
        ConversionTier.active == True,
    ).order_by(ConversionTier.min_conversion_rate).all()
    return {
        "scheme_id": scheme.id,
        "scheme_name": scheme.scheme_name,
        "scheme_type": scheme.scout_type or "cabinet",
        "description": None,
        "scheme_version_id": None,
        "version_name": "legacy",
        "valid_from_cohort_iso_week": None,
        "valid_to_cohort_iso_week": None,
        "maturity_days": 7,
        "min_activated": scheme.min_affiliations or 8,
        "activation_rule": "1V7D",
        "quality_rule": "5V7D",
        "formula_type": "ACTIVATED_X_TIER",
        "currency": "PEN",
        "tiers": [
            {
                "min_conversion_rate": float(t.min_conversion_rate),
                "payout_amount": float(t.payment_per_converted_driver),
                "sort_order": 0,
            }
            for t in tiers
        ],
    }


def _build_config_snapshot_from_resolved(resolved: dict) -> str:
    """Construye y congela config_snapshot JSON desde esquema versionado resuelto.
    Incluye campos legacy (min_affiliations, payment_per_converted_driver) para
    compatibilidad con calculate_cutoff existente.
    """
    return json.dumps({
        "scheme_id": resolved["scheme_id"],
        "scheme_name": resolved["scheme_name"],
        "scheme_type": resolved["scheme_type"],
        "scheme_version_id": resolved.get("scheme_version_id"),
        "version_name": resolved.get("version_name"),
        "valid_from_cohort_iso_week": resolved.get("valid_from_cohort_iso_week"),
        "valid_to_cohort_iso_week": resolved.get("valid_to_cohort_iso_week"),
        "maturity_days": resolved["maturity_days"],
        "min_activated": resolved["min_activated"],
        "activation_rule": resolved["activation_rule"],
        "quality_rule": resolved["quality_rule"],
        "formula_type": resolved["formula_type"],
        "currency": resolved["currency"],
        # Legacy compatibilidad con calculate_cutoff
        "min_affiliations": resolved["min_activated"],
        "origin": resolved.get("scheme_type"),
        "scout_type": resolved.get("scheme_type"),
        "tiers": [
            {
                "min_conversion_rate": t["min_conversion_rate"],
                "payout_amount": t["payout_amount"],
                "payment_per_converted_driver": t["payout_amount"],
                "currency": resolved["currency"],
                "sort_order": t.get("sort_order", 0),
            }
            for t in resolved["tiers"]
        ],
        "conversion_metric": "5plus_0_7",
        "frozen_at": datetime.now().isoformat(),
    })
