"""
Attribution Reconciliation Service — Gobernanza de atribuciones.

Reconcilia atribuciones oficiales vs observadas vs operacion real.
Detecta gaps de data, conflictos, y crea cola operacional de revision.
"""

import csv as _csv
import io
import json
import time
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    ObservedAffiliation, ReconciliationAudit, CutoffDriverLine,
    DriverAssignment, PaidHistory, Scout,
    ReconciliationRefreshLog,
)

_logger = logging.getLogger("attribution_reconciliation")


def classify_driver(
    db: Session,
    driver_id: Optional[str],
    observed: Optional[ObservedAffiliation] = None,
) -> Dict[str, Any]:
    """
    Clasifica un driver en una de las categorias de reconciliacion:
    - both_matched: en ambas fuentes y matchea
    - official_only: solo en fuente oficial
    - observed_only: solo en observadas
    - official_without_scout: en oficial pero sin scout asignado
    - conflicting_scouts: multi-match o conflicto
    - orphan_driver: sin driver_id
    - operational_without_attribution: atribucion sin corte
    """
    result = {
        "driver_id": driver_id,
        "classification": "unknown",
        "confidence": "LOW",
        "in_official": False,
        "in_observed": observed is not None,
        "has_active_assignment": False,
        "has_paid_blocking": False,
        "has_cutoff_line": False,
        "match_status": None,
        "match_confidence": None,
        "official_source_status": None,
    }

    if not driver_id:
        if observed and observed.match_status == "manual_review":
            result["classification"] = "conflicting_scouts"
            result["confidence"] = "LOW"
        else:
            result["classification"] = "orphan_driver"
            result["confidence"] = "BLOCKED"
        return result

    result["in_official"] = _check_official(db, driver_id)

    if observed:
        result["match_status"] = observed.match_status
        result["match_confidence"] = observed.match_confidence
        result["official_source_status"] = observed.official_source_status
        result["has_cutoff_line"] = db.query(CutoffDriverLine).filter(
            CutoffDriverLine.observed_affiliation_id == observed.id
        ).count() > 0

    result["has_active_assignment"] = db.query(DriverAssignment).filter(
        DriverAssignment.driver_id == driver_id,
        DriverAssignment.status == "active",
    ).count() > 0

    result["has_paid_blocking"] = db.execute(
        text("SELECT COUNT(*) FROM scout_liq_paid_history WHERE driver_id = :did AND blocks_future_payment = true"),
        {"did": driver_id},
    ).scalar() > 0

    if not observed and result["in_official"]:
        if not result["has_active_assignment"]:
            result["classification"] = "official_without_scout"
        else:
            result["classification"] = "official_only"
        result["confidence"] = "HIGH"
    elif not observed and not result["in_official"]:
        result["classification"] = "operational_without_attribution"
        result["confidence"] = "BLOCKED"
    elif observed and result["in_official"]:
        if observed.match_status == "matched":
            result["classification"] = "both_matched"
            result["confidence"] = (
                "HIGH" if observed.match_confidence == "high" else "MEDIUM"
            )
        elif observed.match_status == "manual_review":
            result["classification"] = "conflicting_scouts"
            result["confidence"] = "LOW"
        else:
            result["classification"] = "official_without_scout"
            result["confidence"] = "LOW"
    elif observed and not result["in_official"]:
        if observed.match_status == "manual_review":
            result["classification"] = "conflicting_scouts"
            result["confidence"] = "LOW"
        else:
            result["classification"] = "observed_only"
            result["confidence"] = (
                "MEDIUM" if observed.match_confidence in ("high", "medium") else "LOW"
            )
    else:
        result["classification"] = "operational_without_attribution"
        result["confidence"] = "BLOCKED"

    return result


def _check_official(db: Session, driver_id: str) -> bool:
    row = db.execute(
        text("SELECT 1 FROM module_ct_cabinet_drivers WHERE driver_id = :did LIMIT 1"),
        {"did": driver_id},
    ).scalar()
    return row is not None


def detect_conflicts(db: Session) -> List[Dict[str, Any]]:
    """Detecta conflictos entre observadas y oficiales."""
    conflicts = []
    observed = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.match_status == "manual_review"
    ).all()
    for o in observed:
        if o.matched_driver_id:
            cls_result = classify_driver(db, o.matched_driver_id, o)
            if cls_result["classification"] in ("conflicting_scouts", "orphan_driver"):
                conflicts.append(cls_result)
    return conflicts


def detect_observed_now_official(db: Session) -> List[Dict[str, Any]]:
    """
    Detecta observados que AHORA aparecen en la fuente oficial.
    Retorna lista para reconciliacion automatica/semi-automatica.
    """
    results = []
    observed = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.official_source_status == "official_missing",
        ObservedAffiliation.review_status.in_([
            "observed_pending_review", "observed_validated",
        ]),
        ObservedAffiliation.matched_driver_id.isnot(None),
    ).all()

    for o in observed:
        if not o.matched_driver_id:
            continue
        in_official_now = _check_official(db, o.matched_driver_id)
        if in_official_now:
            results.append({
                "observed_id": o.id,
                "driver_id": o.matched_driver_id,
                "reported_scout_name": o.reported_scout_name,
                "reported_driver_name": o.reported_driver_name,
                "original_official_status": o.official_source_status,
                "now_in_official": True,
                "suggested_action": "reconcile_observed_to_official",
            })
    return results


def reconcile_observed_vs_official(
    db: Session,
    observed_id: int,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reconciliar un observado que ahora esta en la fuente oficial.
    Actualiza official_source_status a 'official_found' y cierra discrepancia.
    NO duplica pago.
    """
    oa = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.id == observed_id
    ).first()
    if not oa:
        return {"error": "Not found", "observed_id": observed_id}

    before_state = {
        "official_source_status": oa.official_source_status,
        "review_status": oa.review_status,
        "match_status": oa.match_status,
    }

    in_official_now = _check_official(db, oa.matched_driver_id) if oa.matched_driver_id else False

    if not in_official_now:
        return {
            "error": "Driver not yet in official source",
            "observed_id": observed_id,
            "driver_id": oa.matched_driver_id,
        }

    oa.official_source_status = "official_found"
    oa.review_status = "observed_validated"
    oa.review_notes = (oa.review_notes or "") + f"\n[Reconciled] Driver now in official source. Actor: system_operator"
    oa.updated_at = datetime.now()

    after_state = {
        "official_source_status": oa.official_source_status,
        "review_status": oa.review_status,
        "match_status": oa.match_status,
    }

    audit = ReconciliationAudit(
        driver_id=oa.matched_driver_id or "unknown",
        observed_affiliation_id=oa.id,
        action="reconcile_observed_to_official",
        before_state=json.dumps(before_state),
        after_state=json.dumps(after_state),
        actor="system_operator",
        reason="Driver detected in official source after being observed-only",
        reconciliation_status="done",
    )
    db.add(audit)
    db.commit()

    return {
        "observed_id": oa.id,
        "driver_id": oa.matched_driver_id,
        "action": "reconciled",
        "before": before_state,
        "after": after_state,
    }


def approve_reconciliation(
    db: Session,
    observed_id: int,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Aprueba una observacion y la marca como validada."""
    oa = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.id == observed_id
    ).first()
    if not oa:
        return {"error": "Not found"}

    if oa.review_status == "observed_rejected":
        return {"error": "Cannot approve a rejected observation. Create a new one instead."}

    if oa.match_status == "manual_review" and not oa.matched_driver_id:
        return {
            "error": "Cannot approve observation with manual_review and no driver_id. Requires manual resolution.",
            "observed_id": observed_id,
        }

    before_state = {"review_status": oa.review_status}

    oa.review_status = "observed_validated"
    oa.review_notes = (oa.review_notes or "") + f"\n[Approved] {reason or 'Approved by system_operator'}"
    oa.updated_at = datetime.now()

    after_state = {"review_status": oa.review_status}

    audit = ReconciliationAudit(
        driver_id=oa.matched_driver_id or "unknown",
        observed_affiliation_id=oa.id,
        action="approve",
        before_state=json.dumps(before_state),
        after_state=json.dumps(after_state),
        actor="system_operator",
        reason=reason,
        reconciliation_status="done",
    )
    db.add(audit)
    db.commit()

    return {
        "observed_id": oa.id,
        "action": "approved",
        "before": before_state,
        "after": after_state,
    }


def reject_reconciliation(
    db: Session,
    observed_id: int,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Rechaza una observacion."""
    oa = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.id == observed_id
    ).first()
    if not oa:
        return {"error": "Not found"}

    before_state = {"review_status": oa.review_status}

    oa.review_status = "observed_rejected"
    oa.review_notes = (oa.review_notes or "") + f"\n[Rejected] {reason or 'Rejected by system_operator'}"
    oa.updated_at = datetime.now()

    after_state = {"review_status": oa.review_status}

    audit = ReconciliationAudit(
        driver_id=oa.matched_driver_id or "unknown",
        observed_affiliation_id=oa.id,
        action="reject",
        before_state=json.dumps(before_state),
        after_state=json.dumps(after_state),
        actor="system_operator",
        reason=reason,
        reconciliation_status="done",
    )
    db.add(audit)
    db.commit()

    return {
        "observed_id": oa.id,
        "action": "rejected",
        "before": before_state,
        "after": after_state,
    }


def merge_observed_to_official(
    db: Session,
    observed_id: int,
    assign_scout: bool = False,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Merge: convierte un observado en atribucion oficial.
    Si assign_scout=True, crea DriverAssignment.
    NO duplica pago. Valida paid_history antes de merge.
    """
    oa = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.id == observed_id
    ).first()
    if not oa:
        return {"error": "Not found"}

    if oa.review_status == "observed_rejected":
        return {"error": "Cannot merge rejected observation. Use approve first.", "observed_id": observed_id}

    if oa.match_status == "manual_review":
        return {
            "error": "Cannot auto-merge conflicting scout attribution. Requires manual review first.",
            "observed_id": observed_id,
            "suggestion": "Resolve the conflict manually before merging.",
        }

    if not oa.matched_driver_id:
        return {"error": "Cannot merge without matched_driver_id", "observed_id": observed_id}

    # Check for duplicate payment before merge
    from app.services.observed_affiliation_service import check_double_payment_observed
    paid_check = check_double_payment_observed(db, oa.matched_driver_id, cutoff_run_id=-1)
    if paid_check["blocked"] and paid_check["reason"] == "blocked_already_paid":
        return {
            "error": "Driver already has blocking payment. Cannot merge.",
            "observed_id": observed_id,
            "driver_id": oa.matched_driver_id,
            "detail": paid_check["explanation"],
        }

    before_state = {
        "review_status": oa.review_status,
        "official_source_status": oa.official_source_status,
    }

    in_official = _check_official(db, oa.matched_driver_id) if oa.matched_driver_id else False
    if not in_official and oa.matched_driver_id:
        cls_result = classify_driver(db, oa.matched_driver_id, oa)
        oa.review_status = "observed_validated"
        oa.review_notes = (oa.review_notes or "") + "\n[Merge] Aceptado como observed, pendiente de aparecer en oficial"
        assignment_created = False
    else:
        oa.review_status = "observed_validated"
        oa.official_source_status = "official_found" if in_official else oa.official_source_status
        oa.review_notes = (oa.review_notes or "") + f"\n[Merge] Merge completado. Actor: system_operator"
        assignment_created = False

        if assign_scout and oa.matched_driver_id and oa.reported_scout_name:
            scout = db.query(Scout).filter(
                Scout.scout_name == oa.reported_scout_name
            ).first()
            if scout:
                existing = db.query(DriverAssignment).filter(
                    DriverAssignment.driver_id == oa.matched_driver_id,
                    DriverAssignment.scout_id == scout.id,
                ).first()
                if not existing:
                    da = DriverAssignment(
                        driver_id=oa.matched_driver_id,
                        scout_id=scout.id,
                        origin=oa.reported_origin or "observed_merge",
                        license_raw=oa.reported_license,
                        status="active",
                        assigned_by="system_operator",
                    )
                    db.add(da)
                    assignment_created = True

    oa.updated_at = datetime.now()

    after_state = {
        "review_status": oa.review_status,
        "official_source_status": oa.official_source_status,
        "assignment_created": assignment_created,
    }

    audit = ReconciliationAudit(
        driver_id=oa.matched_driver_id or "unknown",
        observed_affiliation_id=oa.id,
        action="merge",
        before_state=json.dumps(before_state),
        after_state=json.dumps(after_state),
        actor="system_operator",
        reason="Merge observed to official attribution",
        reconciliation_status="done",
    )
    db.add(audit)
    db.commit()

    return {
        "observed_id": oa.id,
        "action": "merged",
        "before": before_state,
        "after": after_state,
        "assignment_created": assignment_created,
    }


def get_reconciliation_summary(db: Session) -> Dict[str, Any]:
    """KPIs de integridad de atribucion."""
    total_observed = db.query(ObservedAffiliation).count()
    total_pending = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_pending_review"
    ).count()
    total_validated = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_validated"
    ).count()
    total_rejected = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_rejected"
    ).count()

    matched_high = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.match_confidence == "high"
    ).count()
    matched_medium = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.match_confidence == "medium"
    ).count()
    manual_review = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.match_status == "manual_review"
    ).count()
    unmatched = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.match_status == "unmatched"
    ).count()
    official_missing = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.official_source_status == "official_missing"
    ).count()
    official_found = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.official_source_status == "official_found"
    ).count()

    total_source_drivers = db.execute(
        text("SELECT COUNT(*) FROM module_ct_cabinet_drivers")
    ).scalar() or 0
    total_drivers_table = db.execute(
        text("SELECT COUNT(*) FROM drivers")
    ).scalar() or 0

    auto_detectable = len(detect_observed_now_official(db))

    aging = _compute_aging(db)
    conflicts = len(detect_conflicts(db))

    rate = 0.0
    if total_observed > 0:
        rate = round((total_validated / total_observed) * 100, 1)

    scouts_with_conflicts = []
    conflict_rows = db.execute(text("""
        SELECT o.reported_scout_name, COUNT(*) as cnt
        FROM scout_liq_observed_affiliations o
        WHERE o.match_status = 'manual_review'
        GROUP BY o.reported_scout_name
        ORDER BY cnt DESC LIMIT 10
    """)).fetchall()
    for row in conflict_rows:
        scouts_with_conflicts.append({"scout": row[0], "count": row[1]})

    return {
        "attribution_integrity_pct": rate,
        "total_observed": total_observed,
        "total_pending": total_pending,
        "total_validated": total_validated,
        "total_rejected": total_rejected,
        "matched_high": matched_high,
        "matched_medium": matched_medium,
        "manual_review": manual_review,
        "unmatched": unmatched,
        "official_missing": official_missing,
        "official_found": official_found,
        "operational_gaps": total_source_drivers - official_found,
        "total_source_drivers": total_source_drivers,
        "total_drivers_in_db": total_drivers_table,
        "auto_detectable_reconciliations": auto_detectable,
        "active_conflicts": conflicts,
        "aging": aging,
        "scouts_with_most_conflicts": scouts_with_conflicts,
    }


def _compute_aging(db: Session) -> Dict[str, int]:
    now = datetime.now()
    pending_24h = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_pending_review",
        ObservedAffiliation.created_at >= now - timedelta(hours=24),
    ).count()
    pending_1_3d = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_pending_review",
        ObservedAffiliation.created_at < now - timedelta(hours=24),
        ObservedAffiliation.created_at >= now - timedelta(days=3),
    ).count()
    pending_gt_3d = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status == "observed_pending_review",
        ObservedAffiliation.created_at < now - timedelta(days=3),
    ).count()
    return {
        "pending_24h": pending_24h,
        "pending_1_3d": pending_1_3d,
        "pending_gt_3d": pending_gt_3d,
    }


def get_reconciliation_list(
    db: Session,
    reconciliation_class: Optional[str] = None,
    confidence: Optional[str] = None,
    review_status: Optional[str] = None,
    scout: Optional[str] = None,
    origin: Optional[str] = None,
    aging: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Lista paginada de registros de reconciliacion con filtros."""
    q = db.query(ObservedAffiliation)

    if review_status:
        q = q.filter(ObservedAffiliation.review_status == review_status)
    if scout:
        q = q.filter(ObservedAffiliation.reported_scout_name.ilike(f"%{scout}%"))
    if origin:
        q = q.filter(ObservedAffiliation.reported_origin == origin)

    if confidence and confidence != "all":
        q = q.filter(ObservedAffiliation.match_confidence == confidence)
    elif not review_status:
        # Default: only pending_review and validated unless a specific review_status is requested
        q = q.filter(
            ObservedAffiliation.review_status.in_([
                "observed_pending_review",
                "observed_validated",
            ])
        )

    if aging and aging != "all":
        now = datetime.now()
        if aging == "pending_24h":
            q = q.filter(ObservedAffiliation.created_at >= now - timedelta(hours=24))
        elif aging == "pending_1_3d":
            q = q.filter(
                ObservedAffiliation.created_at < now - timedelta(hours=24),
                ObservedAffiliation.created_at >= now - timedelta(days=3),
            )
        elif aging == "pending_gt_3d":
            q = q.filter(ObservedAffiliation.created_at < now - timedelta(days=3))

    total = q.count()
    items = q.order_by(ObservedAffiliation.created_at.desc()).offset(offset).limit(limit).all()

    enriched = []
    for oa in items:
        cls = classify_driver(db, oa.matched_driver_id, oa)
        enriched.append({
            "observed_id": oa.id,
            "driver_id": oa.matched_driver_id,
            "reported_driver_name": oa.reported_driver_name,
            "reported_scout_name": oa.reported_scout_name,
            "reported_supervisor_name": oa.reported_supervisor_name,
            "reported_origin": oa.reported_origin,
            "reported_license": oa.reported_license,
            "reported_phone": oa.reported_phone,
            "match_status": oa.match_status,
            "match_confidence": oa.match_confidence,
            "match_reason": oa.match_reason,
            "official_source_status": oa.official_source_status,
            "review_status": oa.review_status,
            "review_notes": oa.review_notes,
            "reported_affiliation_date": str(oa.reported_affiliation_date) if oa.reported_affiliation_date else None,
            "observed_created_at": str(oa.created_at) if oa.created_at else None,
            "classification": cls["classification"],
            "confidence_level": cls["confidence"],
            "in_official": cls["in_official"],
            "has_active_assignment": cls["has_active_assignment"],
            "has_paid_blocking": cls["has_paid_blocking"],
            "has_cutoff_line": cls["has_cutoff_line"],
            "aging": _compute_single_aging(oa.created_at) if oa.created_at else "unknown",
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": enriched,
    }


def _compute_single_aging(created_at: datetime) -> str:
    now = datetime.now()
    if created_at >= now - timedelta(hours=24):
        return "pending_24h"
    elif created_at >= now - timedelta(days=3):
        return "pending_1_3d"
    return "pending_gt_3d"


def export_reconciliation_csv(db: Session) -> str:
    """Exporta el estado actual de reconciliacion como CSV."""
    data = get_reconciliation_list(db, limit=10000)

    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow([
        "observed_id", "driver_id", "nombre", "scout", "supervisor",
        "origen", "licencia", "telefono",
        "match_status", "match_confidence", "match_reason",
        "official_source_status", "review_status", "review_notes",
        "classification", "confidence_level", "in_official",
        "has_assignment", "has_paid_blocking", "has_cutoff_line",
        "aging", "fecha_afiliacion", "created_at",
    ])
    for item in data["items"]:
        writer.writerow([
            item["observed_id"], item["driver_id"] or "",
            item["reported_driver_name"] or "",
            item["reported_scout_name"] or "",
            item["reported_supervisor_name"] or "",
            item["reported_origin"] or "",
            item["reported_license"] or "",
            item["reported_phone"] or "",
            item["match_status"] or "",
            item["match_confidence"] or "",
            item["match_reason"] or "",
            item["official_source_status"] or "",
            item["review_status"] or "",
            item["review_notes"] or "",
            item["classification"] or "",
            item["confidence_level"] or "",
            str(item["in_official"]).lower(),
            str(item["has_active_assignment"]).lower(),
            str(item["has_paid_blocking"]).lower(),
            str(item["has_cutoff_line"]).lower(),
            item["aging"] or "",
            item["reported_affiliation_date"] or "",
            item["observed_created_at"] or "",
        ])
    return buf.getvalue()


def get_driver_timeline(db: Session, driver_id: str) -> Dict[str, Any]:
    """Linea de tiempo de atribucion para un driver especifico."""
    observed_records = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.matched_driver_id == driver_id
    ).order_by(ObservedAffiliation.created_at.asc()).all()

    cutoff_lines = db.query(CutoffDriverLine).filter(
        CutoffDriverLine.driver_id == driver_id
    ).order_by(CutoffDriverLine.created_at.desc()).limit(20).all()

    paid_records = db.query(PaidHistory).filter(
        PaidHistory.driver_id == driver_id
    ).order_by(PaidHistory.paid_at.desc()).limit(20).all()

    audit_trail = db.query(ReconciliationAudit).filter(
        ReconciliationAudit.driver_id == driver_id
    ).order_by(ReconciliationAudit.created_at.desc()).limit(50).all()

    first_trip = None
    trips_row = db.execute(text("""
        SELECT MIN(fecha_inicio_viaje)
        FROM trips_2026
        WHERE conductor_id = :did AND condicion = 'Completado'
    """), {"did": driver_id}).first()
    if trips_row and trips_row[0]:
        first_trip = str(trips_row[0])

    in_official = _check_official(db, driver_id)

    return {
        "driver_id": driver_id,
        "in_official_source": in_official,
        "first_trip_at": first_trip,
        "observed_history": [
            {
                "id": o.id,
                "observed_at": str(o.created_at) if o.created_at else None,
                "reported_scout": o.reported_scout_name,
                "match_confidence": o.match_confidence,
                "review_status": o.review_status,
                "official_source_status": o.official_source_status,
            }
            for o in observed_records
        ],
        "cutoff_lines": [
            {
                "id": cl.id,
                "cutoff_run_id": cl.cutoff_run_id,
                "scout_id": cl.scout_id,
                "attribution_source": cl.attribution_source,
                "payment_status": cl.payment_status,
                "calculated_amount": float(cl.calculated_amount) if cl.calculated_amount else None,
                "line_explanation": cl.line_explanation,
                "created_at": str(cl.created_at) if cl.created_at else None,
            }
            for cl in cutoff_lines
        ],
        "paid_history": [
            {
                "id": ph.id,
                "paid_at": str(ph.paid_at) if ph.paid_at else None,
                "amount_paid": float(ph.amount_paid) if ph.amount_paid else None,
                "import_source": ph.import_source,
                "blocks_future_payment": ph.blocks_future_payment,
            }
            for ph in paid_records
        ],
        "audit_trail": [
            {
                "id": a.id,
                "action": a.action,
                "actor": a.actor,
                "reason": a.reason,
                "reconciliation_status": a.reconciliation_status,
                "created_at": str(a.created_at) if a.created_at else None,
            }
            for a in audit_trail
        ],
    }


def refresh_reconciliation_view(db: Session):
    """Refresca la vista materializada de reconciliacion con registro de auditoria."""
    log = ReconciliationRefreshLog()
    db.add(log)
    db.flush()
    log_id = log.id

    start = time.time()
    try:
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY scout_liq_attribution_reconciliation"))
    except Exception:
        try:
            db.execute(text("REFRESH MATERIALIZED VIEW scout_liq_attribution_reconciliation"))
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            log = db.query(ReconciliationRefreshLog).filter(ReconciliationRefreshLog.id == log_id).first()
            if log:
                log.refresh_status = "error"
                log.refresh_error = str(e)[:500]
                log.refresh_duration_ms = elapsed_ms
            db.commit()
            _logger.error(f"Reconciliation MV refresh failed: {e}")
            raise

    elapsed_ms = int((time.time() - start) * 1000)
    row_count = db.execute(text("SELECT COUNT(*) FROM scout_liq_attribution_reconciliation")).scalar()

    log = db.query(ReconciliationRefreshLog).filter(ReconciliationRefreshLog.id == log_id).first()
    if log:
        log.refresh_status = "ok"
        log.refresh_duration_ms = elapsed_ms
        log.row_count = row_count
        log.last_refreshed_at = datetime.now()
    db.commit()

    return {"status": "ok", "duration_ms": elapsed_ms, "row_count": row_count}


def get_integrity_metrics(db: Session) -> Dict[str, Any]:
    """Metricas de integridad computacionales."""
    summary = get_reconciliation_summary(db)
    auto_detect = detect_observed_now_official(db)
    conflicts = detect_conflicts(db)

    total = summary["total_observed"]
    if total > 0:
        integrity = round((summary["total_validated"] / total) * 100, 1)
    else:
        integrity = 100.0

    return {
        "attribution_integrity_pct": integrity,
        "missing_attribution_rate": round(
            summary["operational_gaps"] / max(summary["total_source_drivers"], 1) * 100, 1
        ),
        "observed_only_count": summary["official_missing"],
        "official_only_count": summary["operational_gaps"],
        "active_conflicts": len(conflicts),
        "auto_detectable": len(auto_detect),
        "scouts_with_conflicts": summary["scouts_with_most_conflicts"],
        "aging": summary["aging"],
        "total_observed": total,
        "total_validated": summary["total_validated"],
        "total_rejected": summary["total_rejected"],
    }


def get_reconciliation_freshness(db: Session) -> Dict[str, Any]:
    """Estado de frescura de la vista materializada de reconciliacion."""
    log = db.query(ReconciliationRefreshLog).order_by(
        ReconciliationRefreshLog.id.desc()
    ).first()

    if not log or not log.last_refreshed_at:
        return {
            "last_refreshed_at": None,
            "age_minutes": None,
            "status": "never_refreshed",
            "last_error": None,
            "row_count": None,
            "refresh_duration_ms": None,
        }

    age = (datetime.now() - log.last_refreshed_at).total_seconds() / 60.0
    status = "fresh"
    if age > 60:
        status = "stale"
    if age > 1440:
        status = "stale_critical"
    if log.refresh_status == "error":
        status = "error"

    return {
        "last_refreshed_at": str(log.last_refreshed_at),
        "age_minutes": round(age, 1),
        "status": status,
        "last_error": log.refresh_error,
        "row_count": log.row_count,
        "refresh_duration_ms": log.refresh_duration_ms,
    }


def get_operational_gaps_diagnostic(db: Session) -> Dict[str, Any]:
    """Diagnostico segmentado de los operational_without_attribution gaps."""
    total_source = db.execute(
        text("SELECT COUNT(*) FROM module_ct_cabinet_drivers")
    ).scalar() or 0

    total_observed = db.query(ObservedAffiliation).count()
    official_found = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.official_source_status == "official_found"
    ).count()

    total_gaps = total_source - official_found if total_source > official_found else 0

    gaps_driver_ids = "(SELECT o.matched_driver_id FROM scout_liq_observed_affiliations o WHERE o.official_source_status = 'official_found' AND o.matched_driver_id IS NOT NULL)"

    breakdown = []

    with_assignment = db.execute(text(f"""
        SELECT COUNT(*)
        FROM module_ct_cabinet_drivers m
        INNER JOIN scout_liq_driver_assignments a ON a.driver_id = m.driver_id AND a.status = 'active'
        WHERE m.driver_id NOT IN {gaps_driver_ids}
    """)).scalar() or 0
    breakdown.append({
        "label": "drivers_asignados_gap",
        "count": with_assignment,
        "description": "Drivers con asignacion activa a scout pero sin atribucion oficial observada",
    })

    without_assignment = db.execute(text(f"""
        SELECT COUNT(*)
        FROM module_ct_cabinet_drivers m
        WHERE m.driver_id NOT IN {gaps_driver_ids}
          AND NOT EXISTS (
            SELECT 1 FROM scout_liq_driver_assignments a
            WHERE a.driver_id = m.driver_id AND a.status = 'active'
          )
    """)).scalar() or 0
    breakdown.append({
        "label": "drivers_sin_asignacion_gap",
        "count": without_assignment,
        "description": "Drivers sin asignacion activa y sin atribucion observada oficial",
    })

    by_origin = db.execute(text(f"""
        SELECT COALESCE(m.origen, 'sin_origen'), COUNT(*)
        FROM module_ct_cabinet_drivers m
        WHERE m.driver_id NOT IN {gaps_driver_ids}
        GROUP BY m.origen
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)).fetchall()
    for row in by_origin:
        breakdown.append({
            "label": f"origen_{row[0] or 'sin_origen'}",
            "count": row[1],
            "description": f"Gaps segmentados por origen: {row[0] or 'sin origen'}",
        })

    gap_rate = round((total_gaps / max(total_source, 1)) * 100, 1)

    return {
        "total_operational_gaps": total_gaps,
        "total_source_drivers": total_source,
        "gap_rate_pct": gap_rate,
        "note": "Este numero requiere diagnostico por ventana/origen antes de interpretarse como perdida real.",
        "breakdown": breakdown,
    }
