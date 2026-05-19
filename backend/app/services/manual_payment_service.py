"""
Manual Payment Service - Fase 4.
Gestiona pagos manuales, comisiones de supervisor, y bonos.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    Scout, ManualPayment, PaidHistory,
    SupervisorCommission, ScoutBonus, CutoffRun, CutoffScoutSummary,
)


def create_manual_payment_preview(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    scout = db.query(Scout).filter(Scout.id == data["scout_id"]).first()
    if not scout:
        raise ValueError(f"Scout {data['scout_id']} no encontrado")

    preview = {
        "scout_id": scout.id,
        "scout_name": scout.scout_name,
        "driver_id": data.get("driver_id"),
        "driver_license_raw": data.get("driver_license_raw"),
        "payment_rule": data.get("payment_rule"),
        "amount": data.get("amount"),
        "currency": data.get("currency", "PEN"),
        "reason": data.get("reason"),
        "payment_component": data.get("payment_component", "manual_adjustment"),
        "valid": True,
        "errors": [],
    }

    if not preview["amount"] or float(preview["amount"]) <= 0:
        preview["valid"] = False
        preview["errors"].append("monto debe ser mayor a 0")

    if not preview["reason"]:
        preview["valid"] = False
        preview["errors"].append("motivo es obligatorio")

    if not preview["driver_id"] and not preview["driver_license_raw"]:
        preview["valid"] = False
        preview["errors"].append("se requiere driver_id o licencia")

    return preview


def approve_manual_payment(db: Session, manual_payment_id: int,
                            approved_by: Optional[str] = None,
                            payment_reference: Optional[str] = None) -> Dict[str, Any]:
    mp = db.query(ManualPayment).filter(ManualPayment.id == manual_payment_id).first()
    if not mp:
        raise ValueError(f"Pago manual {manual_payment_id} no encontrado")
    if mp.status != "draft":
        raise ValueError(f"No se puede aprobar pago en estado '{mp.status}'")

    mp.status = "approved"
    mp.approved_by = approved_by
    mp.approved_at = datetime.now()
    db.commit()

    return {
        "id": mp.id,
        "status": "approved",
        "approved_by": approved_by,
    }


def mark_manual_payment_paid(db: Session, manual_payment_id: int,
                               paid_by: Optional[str] = None) -> Dict[str, Any]:
    mp = db.query(ManualPayment).filter(ManualPayment.id == manual_payment_id).first()
    if not mp:
        raise ValueError(f"Pago manual {manual_payment_id} no encontrado")
    if mp.status != "approved":
        raise ValueError(f"No se puede marcar como pagado en estado '{mp.status}'")

    ph = PaidHistory(
        cutoff_run_id=mp.cutoff_run_id,
        scout_id=mp.scout_id,
        driver_id=mp.driver_id,
        driver_license_raw=mp.driver_license_raw,
        supervisor_id=mp.supervisor_id,
        payment_scheme_id=mp.payment_scheme_id,
        payment_rule=mp.payment_rule,
        amount_paid=mp.amount,
        currency=mp.currency,
        payment_component="manual_adjustment",
        import_source="manual_payment",
        reason=mp.reason,
        paid_at=datetime.now(),
        paid_by=paid_by or mp.created_by,
        status="paid",
    )
    db.add(ph)
    db.flush()

    mp.status = "paid"
    mp.paid_history_id = ph.id
    db.commit()

    return {
        "id": mp.id,
        "status": "paid",
        "paid_history_id": ph.id,
    }


def list_manual_payments(db: Session, scout_id: Optional[int] = None,
                          status: Optional[str] = None) -> List[dict]:
    q = db.query(ManualPayment)
    if scout_id:
        q = q.filter(ManualPayment.scout_id == scout_id)
    if status:
        q = q.filter(ManualPayment.status == status)
    rows = q.order_by(ManualPayment.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "scout_id": r.scout_id,
            "supervisor_id": r.supervisor_id,
            "driver_id": r.driver_id,
            "driver_license_raw": r.driver_license_raw,
            "payment_rule": r.payment_rule,
            "amount": float(r.amount) if r.amount else 0,
            "currency": r.currency,
            "reason": r.reason,
            "status": r.status,
            "approved_by": r.approved_by,
            "approved_at": str(r.approved_at) if r.approved_at else None,
            "paid_history_id": r.paid_history_id,
            "created_by": r.created_by,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]


# --- Supervisor Commission ---

def calculate_supervisor_commission(db: Session, cutoff_run_id: int,
                                      commission_rate: float = 0.10) -> List[dict]:
    run = db.query(CutoffRun).filter(CutoffRun.id == cutoff_run_id).first()
    if not run:
        raise ValueError(f"Cutoff {cutoff_run_id} no encontrado")

    summaries = db.query(CutoffScoutSummary, Scout).join(
        Scout, CutoffScoutSummary.scout_id == Scout.id
    ).filter(
        CutoffScoutSummary.cutoff_run_id == cutoff_run_id,
        CutoffScoutSummary.status == "paid",
    ).all()

    supervisor_totals: Dict[int, Dict] = {}

    for summary, scout in summaries:
        sup_id = scout.supervisor_id
        if not sup_id:
            continue
        if sup_id not in supervisor_totals:
            supervisor_totals[sup_id] = {
                "supervisor_id": sup_id,
                "base_amount": Decimal("0"),
                "commission_rate": Decimal(str(commission_rate)),
                "scouts": [],
            }
        amt = summary.amount_calculated or Decimal("0")
        supervisor_totals[sup_id]["base_amount"] += amt
        supervisor_totals[sup_id]["scouts"].append({
            "scout_id": scout.id,
            "scout_name": scout.scout_name,
            "amount": float(amt),
        })

    result = []
    for sup_id, data in supervisor_totals.items():
        commission_amount = data["base_amount"] * data["commission_rate"]
        commission = SupervisorCommission(
            cutoff_run_id=cutoff_run_id,
            supervisor_id=sup_id,
            base_amount=data["base_amount"],
            commission_rate=data["commission_rate"],
            commission_amount=commission_amount,
            status="pending",
        )
        db.add(commission)
        result.append({
            "supervisor_id": sup_id,
            "base_amount": float(data["base_amount"]),
            "commission_rate": float(data["commission_rate"]),
            "commission_amount": float(commission_amount),
            "scouts": data["scouts"],
        })

    db.commit()
    return result


def list_commissions(db: Session, cutoff_run_id: Optional[int] = None) -> List[dict]:
    q = db.query(SupervisorCommission)
    if cutoff_run_id:
        q = q.filter(SupervisorCommission.cutoff_run_id == cutoff_run_id)
    rows = q.order_by(SupervisorCommission.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "cutoff_run_id": r.cutoff_run_id,
            "supervisor_id": r.supervisor_id,
            "base_amount": float(r.base_amount) if r.base_amount else 0,
            "commission_rate": float(r.commission_rate) if r.commission_rate else 0,
            "commission_amount": float(r.commission_amount) if r.commission_amount else 0,
            "status": r.status,
            "paid_history_id": r.paid_history_id,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]


def mark_commission_paid(db: Session, commission_id: int) -> Dict[str, Any]:
    comm = db.query(SupervisorCommission).filter(SupervisorCommission.id == commission_id).first()
    if not comm:
        raise ValueError(f"Comision {commission_id} no encontrada")

    ph = PaidHistory(
        cutoff_run_id=comm.cutoff_run_id,
        scout_id=None,
        supervisor_id=comm.supervisor_id,
        amount_paid=comm.commission_amount,
        currency="PEN",
        payment_component="supervisor_commission",
        import_source="cutoff_engine",
        reason=f"Comision supervisor {comm.commission_rate * 100}% sobre base {comm.base_amount}",
        paid_at=datetime.now(),
        status="paid",
    )
    db.add(ph)
    db.flush()

    comm.status = "paid"
    comm.paid_history_id = ph.id
    db.commit()

    return {"id": commission_id, "status": "paid", "paid_history_id": ph.id}


# --- Scout Bonuses ---

def create_bonus(db: Session, data: Dict[str, Any]) -> dict:
    scout = db.query(Scout).filter(Scout.id == data["scout_id"]).first()
    if not scout:
        raise ValueError(f"Scout {data['scout_id']} no encontrado")

    bonus = ScoutBonus(
        cutoff_run_id=data.get("cutoff_run_id"),
        scout_id=data["scout_id"],
        bonus_type=data.get("bonus_type", "best_scout"),
        amount=Decimal(str(data["amount"])),
        currency=data.get("currency", "PEN"),
        reason=data["reason"],
        status="draft",
        created_by=data.get("created_by"),
    )
    db.add(bonus)
    db.commit()
    db.refresh(bonus)

    return {
        "id": bonus.id,
        "scout_id": bonus.scout_id,
        "bonus_type": bonus.bonus_type,
        "amount": float(bonus.amount),
        "currency": bonus.currency,
        "reason": bonus.reason,
        "status": bonus.status,
        "created_by": bonus.created_by,
    }


def approve_bonus(db: Session, bonus_id: int, approved_by: Optional[str] = None) -> Dict[str, Any]:
    bonus = db.query(ScoutBonus).filter(ScoutBonus.id == bonus_id).first()
    if not bonus:
        raise ValueError(f"Bono {bonus_id} no encontrado")
    if bonus.status != "draft":
        raise ValueError(f"No se puede aprobar bono en estado '{bonus.status}'")

    bonus.status = "approved"
    bonus.approved_by = approved_by
    bonus.approved_at = datetime.now()
    db.commit()
    return {"id": bonus.id, "status": "approved"}


def mark_bonus_paid(db: Session, bonus_id: int) -> Dict[str, Any]:
    bonus = db.query(ScoutBonus).filter(ScoutBonus.id == bonus_id).first()
    if not bonus:
        raise ValueError(f"Bono {bonus_id} no encontrado")
    if bonus.status != "approved":
        raise ValueError(f"No se puede pagar bono en estado '{bonus.status}'")

    ph = PaidHistory(
        cutoff_run_id=bonus.cutoff_run_id,
        scout_id=bonus.scout_id,
        amount_paid=bonus.amount,
        currency=bonus.currency,
        payment_component="scout_bonus",
        import_source="cutoff_engine",
        reason=bonus.reason,
        paid_at=datetime.now(),
        paid_by=bonus.approved_by,
        status="paid",
    )
    db.add(ph)
    db.flush()

    bonus.status = "paid"
    bonus.paid_history_id = ph.id
    db.commit()

    return {"id": bonus.id, "status": "paid", "paid_history_id": ph.id}


def list_bonuses(db: Session, cutoff_run_id: Optional[int] = None,
                  scout_id: Optional[int] = None) -> List[dict]:
    q = db.query(ScoutBonus)
    if cutoff_run_id:
        q = q.filter(ScoutBonus.cutoff_run_id == cutoff_run_id)
    if scout_id:
        q = q.filter(ScoutBonus.scout_id == scout_id)
    rows = q.order_by(ScoutBonus.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "cutoff_run_id": r.cutoff_run_id,
            "scout_id": r.scout_id,
            "bonus_type": r.bonus_type,
            "amount": float(r.amount) if r.amount else 0,
            "currency": r.currency,
            "reason": r.reason,
            "status": r.status,
            "approved_by": r.approved_by,
            "approved_at": str(r.approved_at) if r.approved_at else None,
            "paid_history_id": r.paid_history_id,
            "created_by": r.created_by,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]
