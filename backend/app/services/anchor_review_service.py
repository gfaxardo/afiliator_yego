"""
Anchor Review Service — Fase 2B.
Workflow operacional para revision manual de acquisition anchors.

Provee:
- Review queue (filtrable)
- Approve / Reject / Needs Supervisor / Ignore
- Audit trail automatico
- Refresh integration (fallback -> official)
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import CutoffDriverLine, AnchorReviewAudit

_logger = logging.getLogger("anchor_review")

VALID_ACTIONS = ["approve", "reject", "needs_supervisor", "ignore", "resolved_by_refresh"]

REVIEW_STATUS_MAP = {
    "approve": "approved_manual_override",
    "reject": "rejected_manual_override",
    "needs_supervisor": "requires_supervisor_review",
    "ignore": "ignored_low_priority",
    "resolved_by_refresh": "resolved_by_official_refresh",
}

REVIEW_STATUS_DEFAULTS = {
    "blocked_missing_official_anchor": "pending_review",
    "reported_pending_validation": "pending_review",
    "fallback_operational_only": "pending_review",
    "fleet_fallback": "pending_review",
}


def _line_to_review_dict(l: CutoffDriverLine) -> Dict[str, Any]:
    return {
        "line_id": l.id,
        "driver_id": l.driver_id,
        "cutoff_run_id": l.cutoff_run_id,
        "scout_id": l.scout_id,
        "origin": l.origin,
        "acquisition_anchor_date": str(l.acquisition_anchor_date) if l.acquisition_anchor_date else None,
        "hire_date_reference": str(l.hire_date_reference) if l.hire_date_reference else None,
        "days_hire_vs_anchor": l.days_hire_vs_anchor,
        "payment_anchor_status": l.payment_anchor_status,
        "acquisition_type": l.acquisition_type,
        "anchor_confidence": l.anchor_confidence,
        "anchor_source": l.anchor_source,
        "anchor_warning": l.anchor_warning,
        "reactivation_flag": l.reactivation_flag,
        "payout_eligible_flag": l.payout_eligible_flag,
        "line_status": l.line_status,
        "payment_status": l.payment_status,
        "blocked_reason": l.blocked_reason,
        "anchor_review_status": l.anchor_review_status or "pending_review",
        "anchor_reviewed_by": l.anchor_reviewed_by,
        "anchor_reviewed_at": str(l.anchor_reviewed_at) if l.anchor_reviewed_at else None,
        "anchor_review_reason": l.anchor_review_reason,
        "is_auto_payable_anchor": l.is_auto_payable_anchor,
        "trips_0_7_count": l.trips_0_7_count,
        "trips_0_14_count": l.trips_0_14_count,
    }


def get_anchor_review_queue(
    db: Session,
    status_filter: Optional[str] = None,
    anchor_status_filter: Optional[str] = None,
    cutoff_run_id: Optional[int] = None,
    origin: Optional[str] = None,
    scout_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    tags: Optional[str] = None,
) -> Dict[str, Any]:
    """Get drivers que requieren revision de anchor. Soporta search (q) y tags."""
    from app.services.tag_filter_engine import (
        apply_tag_filter, apply_search, compute_tag_counts, resolve_tag_filters,
    )

    model = CutoffDriverLine
    q_obj = db.query(model)

    # Base filters (always applied)
    review_conditions = []
    if anchor_status_filter:
        q_obj = q_obj.filter(model.payment_anchor_status == anchor_status_filter)
    elif status_filter == "reactivated":
        q_obj = q_obj.filter(model.reactivation_flag == True)
    elif status_filter == "weak":
        q_obj = q_obj.filter(model.anchor_confidence == "weak")
    elif status_filter == "fallback":
        q_obj = q_obj.filter(model.anchor_confidence == "medium")
        q_obj = q_obj.filter(model.acquisition_type != "fleet_migration")
    elif status_filter == "gap":
        from sqlalchemy import func
        q_obj = q_obj.filter(func.abs(model.days_hire_vs_anchor) > 30)
    elif status_filter == "blocked":
        q_obj = q_obj.filter(model.payment_anchor_status == "blocked_missing_official_anchor")
    elif status_filter == "manual_override":
        q_obj = q_obj.filter(model.anchor_review_status == "approved_manual_override")
    else:
        q_obj = q_obj.filter(model.payment_anchor_status.in_([
            "blocked_missing_official_anchor", "reported_pending_validation",
            "fallback_operational_only",
        ]))
        q_obj = q_obj.filter(model.anchor_review_status.in_(
            ["pending_review", "requires_supervisor_review", None]))

    if cutoff_run_id:
        q_obj = q_obj.filter(model.cutoff_run_id == cutoff_run_id)
    if origin:
        q_obj = q_obj.filter(model.origin == origin)
    if scout_id:
        q_obj = q_obj.filter(model.scout_id == scout_id)

    # ── Text search (q) ──
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        from sqlalchemy import or_
        q_obj = q_obj.filter(or_(
            model.driver_id.ilike(search_term),
            model.origin.ilike(search_term),
            model.anchor_source.ilike(search_term),
            model.acquisition_type.ilike(search_term),
            model.payment_anchor_status.ilike(search_term),
        ))

    # ── Tag counts (before applying tag filters) ──
    tag_counts = compute_tag_counts(q_obj, model)

    # ── Tag filters ──
    tag_list = resolve_tag_filters(tags)
    for tag in tag_list:
        q_obj = apply_tag_filter(q_obj, model, tag)

    total = q_obj.count()
    lines = q_obj.order_by(
        model.payment_anchor_status,
        model.acquisition_anchor_date.desc(),
    ).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_line_to_review_dict(l) for l in lines],
        "tag_counts": tag_counts,
        "active_filters": {
            "q": q,
            "tags": tag_list,
        },
    }


def perform_anchor_review(
    db: Session,
    line_id: int,
    action: str,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    reviewed_anchor_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a review action on a driver line. Returns updated line + audit trail."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Valid: {VALID_ACTIONS}")

    line = db.query(CutoffDriverLine).filter(CutoffDriverLine.id == line_id).first()
    if not line:
        raise ValueError(f"Line {line_id} not found")

    # Cannot mutate approved/paid cutoffs (Fase 2A.2 Rule 10)
    if line.payment_status in ("paid",):
        raise ValueError(f"Cannot review line {line_id}: cutoff is already paid")

    # Capture before state
    before_state = json.dumps({
        "anchor_review_status": line.anchor_review_status,
        "payment_anchor_status": line.payment_anchor_status,
        "is_auto_payable_anchor": line.is_auto_payable_anchor,
        "line_status": line.line_status,
        "payout_eligible_flag": line.payout_eligible_flag,
        "blocked_reason": line.blocked_reason,
        "acquisition_anchor_date": str(line.acquisition_anchor_date) if line.acquisition_anchor_date else None,
    })

    # Apply action
    now = datetime.now()
    line.anchor_review_status = REVIEW_STATUS_MAP.get(action, "pending_review")
    line.anchor_reviewed_by = actor
    line.anchor_reviewed_at = now
    line.anchor_review_reason = reason

    if action == "approve":
        # Manual approve: enable payout if previously blocked
        if line.payment_anchor_status == "fallback_operational_only":
            line.is_auto_payable_anchor = True
            line.payment_anchor_status = "approved_manual_override"
            if line.blocked_reason and "sin lead_created_at" in (line.blocked_reason or "").lower():
                line.line_status = "evaluating"
                line.blocked_reason = None
                line.anchor_payment_block_reason = None
        elif line.payment_anchor_status == "blocked_missing_official_anchor":
            line.is_auto_payable_anchor = True
            line.payment_anchor_status = "approved_manual_override"
            line.blocked_reason = None
            line.anchor_payment_block_reason = None
        elif line.payment_anchor_status == "reported_pending_validation":
            line.is_auto_payable_anchor = True
            line.payment_anchor_status = "approved_manual_override"

        if reviewed_anchor_date:
            from datetime import date as dt_date
            line.acquisition_anchor_date = datetime.strptime(reviewed_anchor_date, "%Y-%m-%d").date()

    elif action == "reject":
        line.is_auto_payable_anchor = False
        if not line.blocked_reason:
            line.blocked_reason = "Rechazado en revision manual de anchor"
        if not line.anchor_payment_block_reason:
            line.anchor_payment_block_reason = "Rechazado en revision manual de anchor"
        line.payout_eligible_flag = False

    elif action == "resolved_by_refresh":
        # Refresh detected official LCA became available
        line.is_auto_payable_anchor = True
        line.payment_anchor_status = "official_strong"
        if line.blocked_reason and "sin lead_created_at" in (line.blocked_reason or "").lower():
            line.blocked_reason = None
            line.anchor_payment_block_reason = None

    # Capture after state
    after_state = json.dumps({
        "anchor_review_status": line.anchor_review_status,
        "payment_anchor_status": line.payment_anchor_status,
        "is_auto_payable_anchor": line.is_auto_payable_anchor,
        "line_status": line.line_status,
        "payout_eligible_flag": line.payout_eligible_flag,
        "blocked_reason": line.blocked_reason,
        "acquisition_anchor_date": str(line.acquisition_anchor_date) if line.acquisition_anchor_date else None,
    })

    # Persist audit trail
    audit = AnchorReviewAudit(
        line_id=line_id,
        action=action,
        actor=actor,
        reason=reason,
        notes=notes,
        reviewed_anchor_date=(
            datetime.strptime(reviewed_anchor_date, "%Y-%m-%d").date()
            if reviewed_anchor_date else None
        ),
        before_state=before_state,
        after_state=after_state,
    )
    db.add(audit)
    db.flush()

    return {
        "line_id": line_id,
        "action": action,
        "anchor_review_status": line.anchor_review_status,
        "audit_id": audit.id,
        "line": _line_to_review_dict(line),
    }


def get_review_audit_trail(db: Session, line_id: int) -> List[Dict[str, Any]]:
    """Get audit trail for a specific line."""
    audits = db.query(AnchorReviewAudit).filter(
        AnchorReviewAudit.line_id == line_id
    ).order_by(AnchorReviewAudit.created_at.desc()).all()

    return [
        {
            "id": a.id,
            "line_id": a.line_id,
            "action": a.action,
            "actor": a.actor,
            "reason": a.reason,
            "notes": a.notes,
            "reviewed_anchor_date": str(a.reviewed_anchor_date) if a.reviewed_anchor_date else None,
            "before_state": json.loads(a.before_state) if a.before_state else None,
            "after_state": json.loads(a.after_state) if a.after_state else None,
            "created_at": str(a.created_at) if a.created_at else None,
        }
        for a in audits
    ]


def get_review_queue_summary(db: Session) -> Dict[str, Any]:
    """Summary KPIs for the review queue."""
    q = db.query(CutoffDriverLine)

    total = q.count()
    pending = q.filter(CutoffDriverLine.anchor_review_status.in_(
        ["pending_review", None])).count()
    blocked = q.filter(CutoffDriverLine.payment_anchor_status == "blocked_missing_official_anchor").count()
    supervisor = q.filter(CutoffDriverLine.anchor_review_status == "requires_supervisor_review").count()
    approved = q.filter(CutoffDriverLine.anchor_review_status == "approved_manual_override").count()
    rejected = q.filter(CutoffDriverLine.anchor_review_status == "rejected_manual_override").count()
    resolved_refresh = q.filter(CutoffDriverLine.anchor_review_status == "resolved_by_official_refresh").count()
    weak = q.filter(CutoffDriverLine.anchor_confidence == "weak").count()
    reactivated = q.filter(CutoffDriverLine.reactivation_flag == True).count()

    return {
        "total_lines": total,
        "pending_review": pending,
        "blocked_anchor": blocked,
        "supervisor_review": supervisor,
        "approved_manual": approved,
        "rejected": rejected,
        "resolved_by_refresh": resolved_refresh,
        "weak_anchors": weak,
        "reactivated_pending": reactivated,
    }


def bulk_perform_anchor_review(
    db: Session,
    line_ids: List[int],
    action: str,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a review action on multiple lines. Max 500 lines."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}")
    if len(line_ids) > 500:
        raise ValueError(f"Max 500 lines per bulk operation, got {len(line_ids)}")
    if not reason:
        raise ValueError("Reason is required for bulk operations")

    applied = []
    skipped = []
    errors = []

    for line_id in line_ids:
        try:
            result = perform_anchor_review(
                db, line_id=line_id, action=action,
                actor=actor, reason=reason, notes=notes,
            )
            applied.append({"line_id": line_id, "audit_id": result["audit_id"]})
        except ValueError as e:
            skipped.append({"line_id": line_id, "reason": str(e)})
        except Exception as e:
            errors.append({"line_id": line_id, "error": str(e)})

    db.flush()

    return {
        "action": action,
        "requested": len(line_ids),
        "applied": len(applied),
        "skipped": len(skipped),
        "errors": len(errors),
        "applied_details": applied[:50],
        "skipped_details": skipped[:50],
        "error_details": errors[:50],
    }
