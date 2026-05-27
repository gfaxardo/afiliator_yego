"""
Operation Action Service — Fase 3

Persiste acciones operacionales sobre lineas de cutoff:
- approve: desbloquear linea para pago
- block: bloquear linea
- manual_review: enviar a revision manual
- mark_paid: marcar como pagada individualmente

Incluye:
- Operational locks (no doble pago, no approve critico sin override)
- Audit trail via OperationAudit
- Bulk operations
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import CutoffDriverLine, OperationAudit, PaidHistory

_logger = logging.getLogger("operation_action")

# ── Valid actions ────────────────────────────────────────────────────

VALID_ACTIONS = ["approve", "block", "manual_review", "mark_paid", "unblock"]

ACTION_LABELS: Dict[str, str] = {
    "approve": "Aprobado",
    "block": "Bloqueado",
    "manual_review": "En revision",
    "mark_paid": "Pagado",
    "unblock": "Desbloqueado",
}

# ── Operational locks ────────────────────────────────────────────────

def _check_operational_locks(line: CutoffDriverLine, action: str,
                             override_reason: Optional[str] = None) -> Optional[str]:
    """Return block reason if action is blocked, None if allowed."""
    if action == "mark_paid":
        if line.payment_status == "paid":
            return "Ya esta pagado. No se puede pagar dos veces."
        if line.already_paid:
            return "Ya tiene pago previo bloqueante."

    if action == "approve":
        if line.payment_status == "paid":
            return "Ya esta pagado. No se puede cambiar estado de linea pagada."
        is_critical = (
            line.anchor_confidence == "weak"
            or line.payment_anchor_status == "blocked_missing_official_anchor"
            or line.line_status == "blocked_invalid_hire_date"
            or line.line_status == "blocked_no_official_source"
        )
        if is_critical and not override_reason:
            return ("Linea critica requiere override_reason explicito. "
                    "Indica por que se debe aprobar a pesar del bloqueo.")

    if action == "block":
        if line.payment_status == "paid":
            return "No se puede bloquear una linea ya pagada."

    return None


# ── State transition ──────────────────────────────────────────────────

def _apply_action(line: CutoffDriverLine, action: str) -> Dict[str, Any]:
    """Apply state changes to line based on action. Returns {changes}."""
    changes = {"previous_line_status": line.line_status,
               "previous_payment_status": line.payment_status}

    if action == "approve":
        line.line_status = "payable"
        line.payment_status = "payable"
        line.blocked_reason = None
        line.anchor_payment_block_reason = None
        line.is_auto_payable_anchor = True
        line.payment_anchor_status = "approved_manual_override"
        line.payout_eligible_flag = True

    elif action == "block":
        line.line_status = "blocked"
        line.payment_status = "blocked"
        line.payout_eligible_flag = False
        line.is_auto_payable_anchor = False

    elif action == "unblock":
        line.line_status = "evaluating"
        line.payment_status = "blocked"
        line.blocked_reason = None
        line.payout_eligible_flag = False

    elif action == "manual_review":
        line.anchor_review_status = "pending_review"
        line.line_status = "evaluating"

    elif action == "mark_paid":
        line.line_status = "paid"
        line.payment_status = "paid"
        line.payout_eligible_flag = False

    changes["new_line_status"] = line.line_status
    changes["new_payment_status"] = line.payment_status
    return changes


# ── Audit trail ───────────────────────────────────────────────────────

def _create_audit(db: Session, line: CutoffDriverLine, action: str,
                  actor: Optional[str], reason: Optional[str], notes: Optional[str],
                  override_reason: Optional[str], changes: Dict[str, Any]):
    audit = OperationAudit(
        line_id=line.id,
        cutoff_run_id=line.cutoff_run_id,
        driver_id=line.driver_id,
        action=action,
        actor=actor,
        reason=reason,
        notes=notes,
        previous_line_status=changes["previous_line_status"],
        previous_payment_status=changes.get("previous_payment_status"),
        new_line_status=changes.get("new_line_status"),
        new_payment_status=changes.get("new_payment_status"),
        override_reason=override_reason,
        before_state=json.dumps({
            "line_status": changes["previous_line_status"],
            "payment_status": changes.get("previous_payment_status"),
            "blocked_reason": line.blocked_reason,
            "anchor_confidence": line.anchor_confidence,
        }),
        after_state=json.dumps({
            "line_status": changes.get("new_line_status"),
            "payment_status": changes.get("new_payment_status"),
            "blocked_reason": line.blocked_reason,
            "anchor_confidence": line.anchor_confidence,
        }),
    )
    db.add(audit)


# ── Single line action ────────────────────────────────────────────────

def perform_line_action(
    db: Session,
    line_id: int,
    action: str,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> Dict[str, Any]:
    if action not in VALID_ACTIONS:
        return {"status": "error", "message": f"Accion invalida: {action}"}

    line = db.query(CutoffDriverLine).filter(CutoffDriverLine.id == line_id).first()
    if not line:
        return {"status": "error", "message": f"Linea {line_id} no encontrada"}

    block_msg = _check_operational_locks(line, action, override_reason)
    if block_msg:
        return {"status": "blocked", "message": block_msg, "line_id": line_id}

    changes = _apply_action(line, action)
    _create_audit(db, line, action, actor, reason, notes, override_reason, changes)
    db.commit()

    return {
        "status": "ok",
        "line_id": line_id,
        "action": action,
        "driver_id": line.driver_id,
        "previous_status": changes["previous_line_status"],
        "new_status": changes["new_line_status"],
        "message": f"Linea {line_id}: {ACTION_LABELS.get(action, action)}",
    }


# ── Bulk line actions ─────────────────────────────────────────────────

def bulk_perform_line_action(
    db: Session,
    line_ids: List[int],
    action: str,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    override_reason: Optional[str] = None,
    max_bulk: int = 500,
) -> Dict[str, Any]:
    if action not in VALID_ACTIONS:
        return {"status": "error", "message": f"Accion invalida: {action}"}

    if len(line_ids) > max_bulk:
        return {"status": "error",
                "message": f"Maximo {max_bulk} lineas por operacion bulk. Recibido: {len(line_ids)}"}

    if not line_ids:
        return {"status": "error", "message": "No se proporcionaron line_ids"}

    lines = db.query(CutoffDriverLine).filter(
        CutoffDriverLine.id.in_(line_ids)
    ).all()

    applied = []
    skipped = []
    errors = []

    for line in lines:
        block_msg = _check_operational_locks(line, action, override_reason)
        if block_msg:
            skipped.append({
                "line_id": line.id,
                "driver_id": line.driver_id,
                "reason": block_msg,
            })
            continue

        try:
            changes = _apply_action(line, action)
            _create_audit(db, line, action, actor, reason, notes, override_reason, changes)
            applied.append({
                "line_id": line.id,
                "driver_id": line.driver_id,
                "previous_status": changes["previous_line_status"],
                "new_status": changes["new_line_status"],
            })
        except Exception as e:
            errors.append({"line_id": line.id, "error": str(e)})

    db.commit()

    return {
        "status": "ok",
        "action": action,
        "requested": len(line_ids),
        "applied": len(applied),
        "skipped": len(skipped),
        "errors": len(errors),
        "applied_details": applied[:50],
        "skipped_details": skipped[:50],
        "errors_details": errors[:20],
        "message": f"Bulk {action}: {len(applied)} aplicadas, {len(skipped)} omitidas, {len(errors)} errores",
    }


# ── Audit trail query ─────────────────────────────────────────────────

def get_line_audit_trail(db: Session, line_id: int) -> List[Dict[str, Any]]:
    audits = db.query(OperationAudit).filter(
        OperationAudit.line_id == line_id
    ).order_by(OperationAudit.created_at.desc()).all()

    return [
        {
            "id": a.id,
            "line_id": a.line_id,
            "action": a.action,
            "actor": a.actor,
            "reason": a.reason,
            "notes": a.notes,
            "previous_line_status": a.previous_line_status,
            "previous_payment_status": a.previous_payment_status,
            "new_line_status": a.new_line_status,
            "new_payment_status": a.new_payment_status,
            "override_reason": a.override_reason,
            "created_at": str(a.created_at) if a.created_at else None,
        }
        for a in audits
    ]


def get_cutoff_audit_summary(db: Session, cutoff_run_id: int) -> Dict[str, Any]:
    rows = db.execute(text(
        "SELECT action, COUNT(*) FROM scout_liq_operation_audit "
        "WHERE cutoff_run_id = :cid GROUP BY action ORDER BY COUNT(*) DESC"
    ), {"cid": cutoff_run_id}).fetchall()
    return {
        "cutoff_run_id": cutoff_run_id,
        "actions": [{"action": r[0], "count": r[1]} for r in rows],
        "total": sum(r[1] for r in rows),
    }
