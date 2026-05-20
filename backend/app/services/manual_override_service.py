"""
Manual Override Service — Acciones manuales auditables.

Tipos de override:
- assign_scout: asignar driver a scout
- reassign_scout: cambiar driver de scout
- force_exclude: excluir driver del pago automatico
- force_pay: crear pago manual fuera de regla
- send_review: enviar a revision manual
- resolve_review: resolver revision manual
"""

import json
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    ManualOverride,
    DriverAssignment,
    PaidHistory,
    Scout,
)


def _get_driver_source(db: Session, driver_id: str) -> Optional[dict]:
    row = db.execute(text(
        "SELECT driver_id, COALESCE(driver_nombre,''), COALESCE(driver_apellido,''), license, hire_date::text, origen "
        "FROM module_ct_cabinet_drivers WHERE driver_id = :did"
    ), {"did": driver_id}).fetchone()
    if not row:
        return None
    nombre = (row[1] or "").strip()
    apellido = (row[2] or "").strip()
    return {
        "driver_id": row[0],
        "driver_name": f"{apellido}, {nombre}" if apellido and nombre else (nombre or row[0]),
        "license": row[3],
        "hire_date": row[4],
        "origin": row[5],
    }


# ═══════════════════════════════════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════════════════════════════════

def create_manual_override(
    db: Session,
    driver_id: str,
    override_type: str,
    reason: str,
    cohort_iso_week: Optional[str] = None,
    scout_id: Optional[int] = None,
    scout_id_before: Optional[int] = None,
    amount: Optional[float] = None,
    currency: str = "PEN",
    notes: Optional[str] = None,
    created_by: Optional[str] = None,
    auto_approve: bool = True,
) -> Dict[str, Any]:
    if not driver_id:
        raise ValueError("driver_id requerido")
    if not reason.strip():
        raise ValueError("reason (motivo) requerido")
    if override_type not in ("assign_scout", "reassign_scout", "force_exclude", "force_pay", "send_review", "resolve_review"):
        raise ValueError(f"override_type invalido: {override_type}")

    # Validar driver existe en fuente
    src = _get_driver_source(db, driver_id)
    if not src:
        raise ValueError(f"Driver {driver_id} no encontrado en fuente")

    # force_pay validations
    if override_type == "force_pay":
        if not amount or amount <= 0:
            raise ValueError("force_pay requiere amount > 0")
        existing_paid = db.execute(text(
            "SELECT COUNT(*) FROM scout_liq_paid_history WHERE driver_id = :did AND blocks_future_payment = true"
        ), {"did": driver_id}).scalar()
        if existing_paid > 0:
            raise ValueError(
                f"Driver {driver_id} ya tiene un pago que bloquea pagos futuros ({existing_paid} registros). "
                f"No se puede crear force_pay sin force=true."
            )

    # assign / reassign validations
    if override_type in ("assign_scout", "reassign_scout"):
        if not scout_id:
            raise ValueError(f"{override_type} requiere scout_id destino")
        scout = db.query(Scout).filter(Scout.id == scout_id).first()
        if not scout:
            raise ValueError(f"Scout {scout_id} no encontrado")

    # reassign: need scout_id_before
    if override_type == "reassign_scout":
        current = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == driver_id,
            DriverAssignment.status == "active",
        ).first()
        if current:
            if not scout_id_before:
                scout_id_before = current.scout_id
        else:
            raise ValueError(f"Driver {driver_id} no tiene asignacion activa para reasignar")

    over = ManualOverride(
        driver_id=driver_id,
        cohort_iso_week=cohort_iso_week,
        scout_id_before=scout_id_before,
        scout_id_after=scout_id,
        override_type=override_type,
        amount=Decimal(str(amount)) if amount else None,
        currency=currency,
        reason=reason.strip(),
        notes=notes,
        created_by=created_by,
        status="pending",
    )
    db.add(over)
    db.commit()
    db.refresh(over)

    if auto_approve:
        over = _approve_and_apply(db, over, created_by)

    return _to_dict(over)


# ═══════════════════════════════════════════════════════════════════════════
# APPROVE
# ═══════════════════════════════════════════════════════════════════════════

def approve_manual_override(db: Session, override_id: int, approved_by: Optional[str] = None) -> Dict[str, Any]:
    over = db.query(ManualOverride).filter(ManualOverride.id == override_id).first()
    if not over:
        raise ValueError(f"Override {override_id} no encontrado")
    if over.status != "pending":
        raise ValueError(f"Override {override_id} en estado '{over.status}', no se puede aprobar")
    over = _approve_and_apply(db, over, approved_by)
    return _to_dict(over)


def _approve_and_apply(db: Session, over: ManualOverride, approved_by: Optional[str] = None) -> ManualOverride:
    over.status = "approved"
    over.approved_by = approved_by
    over.approved_at = datetime.now()
    db.commit()
    return _apply_override(db, over)


# ═══════════════════════════════════════════════════════════════════════════
# APPLY
# ═══════════════════════════════════════════════════════════════════════════

def apply_manual_override(db: Session, override_id: int) -> Dict[str, Any]:
    over = db.query(ManualOverride).filter(ManualOverride.id == override_id).first()
    if not over:
        raise ValueError(f"Override {override_id} no encontrado")
    if over.status not in ("approved",):
        raise ValueError(f"Override {override_id} en estado '{over.status}', debe estar approved")
    over = _apply_override(db, over)
    return _to_dict(over)


def _apply_override(db: Session, over: ManualOverride) -> ManualOverride:
    ot = over.override_type
    did = over.driver_id

    if ot == "assign_scout":
        # Crear asignacion activa
        existing = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == did,
            DriverAssignment.status == "active",
        ).first()
        if existing:
            existing.status = "inactive"
        db.add(DriverAssignment(
            driver_id=did,
            scout_id=over.scout_id_after,
            status="active",
            origin="manual_override",
            notes=f"Manual override id={over.id}: {over.reason}",
        ))
        over.status = "applied"

    elif ot == "reassign_scout":
        # Cerrar anterior
        old = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == did,
            DriverAssignment.scout_id == over.scout_id_before,
            DriverAssignment.status == "active",
        ).first()
        if old:
            old.status = "inactive"
        db.add(DriverAssignment(
            driver_id=did,
            scout_id=over.scout_id_after,
            status="active",
            origin="manual_override",
            notes=f"Reasignado desde scout {over.scout_id_before}: {over.reason}",
        ))
        over.status = "applied"

    elif ot == "force_exclude":
        over.blocks_future_payment = True
        over.status = "applied"

    elif ot == "force_pay":
        # Crear paid_history manual
        cfg = json.loads(over.metadata_json) if over.metadata_json else {}
        ph = PaidHistory(
            scout_id=over.scout_id_after,
            driver_id=did,
            amount_paid=over.amount,
            currency=over.currency or "PEN",
            paid_at=datetime.now(),
            import_source="manual_override",
            payment_component="manual_override",
            payment_rule=cfg.get("payment_rule", "Manual override"),
            payment_scheme_name=cfg.get("scheme_name", "Manual"),
            status="paid",
            blocks_future_payment=True,
            reason=over.reason,
        )
        db.add(ph)
        db.flush()
        over.paid_history_id = ph.id
        over.blocks_future_payment = True
        over.status = "applied"

    elif ot == "send_review":
        over.status = "applied"

    elif ot == "resolve_review":
        over.status = "applied"

    db.commit()
    db.refresh(over)
    return over


# ═══════════════════════════════════════════════════════════════════════════
# REJECT
# ═══════════════════════════════════════════════════════════════════════════

def reject_manual_override(db: Session, override_id: int) -> Dict[str, Any]:
    over = db.query(ManualOverride).filter(ManualOverride.id == override_id).first()
    if not over:
        raise ValueError(f"Override {override_id} no encontrado")
    if over.status not in ("pending",):
        raise ValueError(f"Override {override_id} en estado '{over.status}', no se puede rechazar")
    over.status = "rejected"
    db.commit()
    return _to_dict(over)


# ═══════════════════════════════════════════════════════════════════════════
# LIST / GET
# ═══════════════════════════════════════════════════════════════════════════

def list_manual_overrides(
    db: Session,
    driver_id: Optional[str] = None,
    override_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    q = db.query(ManualOverride).order_by(ManualOverride.created_at.desc())
    if driver_id:
        q = q.filter(ManualOverride.driver_id == driver_id)
    if override_type:
        q = q.filter(ManualOverride.override_type == override_type)
    if status:
        q = q.filter(ManualOverride.status == status)
    items = q.limit(limit).offset(offset).all()
    return [_to_dict(o) for o in items]


def get_driver_overrides(db: Session, driver_id: str) -> List[Dict[str, Any]]:
    items = db.query(ManualOverride).filter(
        ManualOverride.driver_id == driver_id
    ).order_by(ManualOverride.created_at.desc()).all()
    return [_to_dict(o) for o in items]


def get_applied_overrides_for_drivers(db: Session, driver_ids: List[str]) -> Dict[str, List[Dict]]:
    """Batch: devuelve overrides aplicados por driver_id para canonical service."""
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": d for i, d in enumerate(driver_ids)}
    rows = db.execute(text(f"""
        SELECT id, driver_id, override_type, amount, currency, reason, status,
               blocks_future_payment, paid_history_id, scout_id_after, scout_id_before,
               created_at, created_by
        FROM scout_liq_manual_overrides
        WHERE driver_id IN ({placeholders}) AND status = 'applied'
        ORDER BY created_at DESC
    """), params).fetchall()
    result: Dict[str, List[Dict]] = {}
    for r in rows:
        did = r[1]
        if did not in result:
            result[did] = []
        result[did].append({
            "id": r[0],
            "override_type": r[2],
            "amount": float(r[3]) if r[3] else None,
            "currency": r[4],
            "reason": r[5],
            "status": r[6],
            "blocks_future_payment": r[7],
            "paid_history_id": r[8],
            "scout_id_after": r[9],
            "scout_id_before": r[10],
            "created_at": str(r[11]) if r[11] else None,
            "created_by": r[12],
        })
    return result


def _to_dict(o: ManualOverride) -> Dict[str, Any]:
    return {
        "id": o.id,
        "driver_id": o.driver_id,
        "cohort_iso_week": o.cohort_iso_week,
        "scout_id_before": o.scout_id_before,
        "scout_id_after": o.scout_id_after,
        "override_type": o.override_type,
        "amount": float(o.amount) if o.amount else None,
        "currency": o.currency,
        "reason": o.reason,
        "notes": o.notes,
        "created_by": o.created_by,
        "created_at": str(o.created_at) if o.created_at else None,
        "approved_by": o.approved_by,
        "approved_at": str(o.approved_at) if o.approved_at else None,
        "status": o.status,
        "blocks_future_payment": o.blocks_future_payment,
        "paid_history_id": o.paid_history_id,
    }
