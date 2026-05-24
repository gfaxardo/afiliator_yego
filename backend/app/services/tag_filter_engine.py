"""
Tag Filter Engine — Fase 3A.0
Reusable tag definitions, search (q), and counter computation.
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Query

# ── Tag definitions ──
TAG_DEFS = {
    "REACTIVATED": {
        "label": "Reactivados",
        "color": "orange",
        "condition": lambda model: model.reactivation_flag == True,
    },
    "FLEET": {
        "label": "Fleet",
        "color": "blue",
        "condition": lambda model: model.acquisition_type == "fleet_migration",
    },
    "FALLBACK": {
        "label": "Fallback",
        "color": "yellow",
        "condition": lambda model: (
            model.anchor_confidence == "medium"
            and (model.anchor_source == None or "lead_created_at" not in (model.anchor_source or ""))
        ),
    },
    "WEAK": {
        "label": "Weak Anchor",
        "color": "red",
        "condition": lambda model: model.anchor_confidence == "weak",
    },
    "BLOCKED": {
        "label": "Bloqueados",
        "color": "red",
        "condition": lambda model: (
            (model.line_status != None and model.line_status.ilike("blocked%"))
            or (model.payment_anchor_status != None and model.payment_anchor_status.ilike("blocked%"))
            or model.payout_eligible_flag == False
        ),
    },
    "PAYABLE": {
        "label": "Pagables",
        "color": "green",
        "condition": lambda model: (
            model.payout_eligible_flag == True
            and model.is_auto_payable_anchor == True
        ),
    },
    "MANUAL_REVIEW": {
        "label": "Manual Review",
        "color": "yellow",
        "condition": lambda model: model.anchor_review_status.in_(
            ["pending_review", "requires_supervisor_review"]
        ),
    },
    "GAP_30": {
        "label": "Gap >30d",
        "color": "amber",
        "condition": lambda model: model.days_hire_vs_anchor != None
            and abs(model.days_hire_vs_anchor) > 30,
    },
    "NEW": {
        "label": "Nuevos",
        "color": "green",
        "condition": lambda model: (
            model.acquisition_type != None
            and "new" in (model.acquisition_type or "").lower()
        ),
    },
    "OFFICIAL_ANCHOR": {
        "label": "Anchor Oficial",
        "color": "green",
        "condition": lambda model: model.is_auto_payable_anchor == True,
    },
    "REPORTED_PENDING": {
        "label": "Reportado Pte",
        "color": "yellow",
        "condition": lambda model: model.payment_anchor_status == "reported_pending_validation",
    },
}

ALL_TAGS = list(TAG_DEFS.keys())


def apply_tag_filter(query: Query, model, tag: str) -> Query:
    """Apply a single tag filter to a SQLAlchemy query."""
    if tag not in TAG_DEFS:
        return query
    return query.filter(TAG_DEFS[tag]["condition"](model))


def apply_search(q_value: str, model, columns: List) -> callable:
    """Return a filter callable for text search across multiple columns.
    Usage: query.filter(apply_search('ABC', MyModel, [MyModel.driver_id, MyModel.license]))"""
    if not q_value or not q_value.strip():
        return lambda: True
    term = f"%{q_value.strip()}%"

    def _filter():
        from sqlalchemy import or_
        conditions = []
        for col in columns:
            conditions.append(col.ilike(term))
        return or_(*conditions) if conditions else True
    return _filter


def compute_tag_counts(query_base, model) -> Dict[str, int]:
    """Compute tag counts on a base query (before applying tag filters)."""
    counts = {}
    for tag_name, tag_def in TAG_DEFS.items():
        try:
            cnt = query_base.filter(tag_def["condition"](model)).count()
            if cnt > 0:
                counts[tag_name] = cnt
        except Exception:
            pass
    return counts


def resolve_tag_filters(tags_param: Optional[str]) -> List[str]:
    """Parse comma-separated tags string into list. Ignores invalid tags."""
    if not tags_param:
        return []
    requested = [t.strip().upper() for t in tags_param.split(",") if t.strip()]
    return [t for t in requested if t in TAG_DEFS]
