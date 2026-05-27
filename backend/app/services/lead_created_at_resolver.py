"""
Lead Created At Resolver

Pure helper that resolves a single lead_created_at date and metadata
from the real DB columns lead_created_at_cabinet / lead_created_at_fleet.

Nota: module_ct_cabinet_drivers no tiene columna lead_created_at singular.
Las columnas reales son:
  - lead_created_at_cabinet (varchar, ISO 8601)
  - lead_created_at_fleet   (varchar, ISO 8601)

Ambas son varchar, por lo que cualquier uso como fecha requiere cast seguro.
"""

from datetime import date, datetime
from typing import Any, Dict, Optional


def _safe_parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.date()
        except ValueError:
            continue
    return None


def resolve_lead_created_at(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resuelve el lead_created_at desde las columnas reales de la BD.

    Args:
        row: dict con al menos origen, lead_created_at_cabinet, lead_created_at_fleet.

    Returns:
        dict con:
          - lead_created_at_resolved: str | None (ISO date)
          - lead_created_at_source: str
          - lead_created_at_status: str
          - lead_created_at_warning: str | None
    """
    origen = (row.get("origen") or "").strip().lower()
    lca_cabinet = row.get("lead_created_at_cabinet")
    lca_fleet = row.get("lead_created_at_fleet")

    cab_date = _safe_parse_date(lca_cabinet)
    fleet_date = _safe_parse_date(lca_fleet)

    resolved: Optional[date] = None
    source = "none"
    status = "missing"
    warning: Optional[str] = None

    # ── Both dates present (edge case) ──
    if cab_date is not None and fleet_date is not None:
        warning = "both_dates_present"
        if origen == "cabinet":
            resolved = cab_date
            source = "lead_created_at_cabinet"
            status = "resolved_by_origen"
        elif origen == "fleet":
            resolved = fleet_date
            source = "lead_created_at_fleet"
            status = "resolved_by_origen"
        else:
            resolved = cab_date
            source = "lead_created_at_cabinet"
            status = "resolved_by_available_date"
            if not warning:
                warning = "origin_unclear"
    # ── Cabinet origen ──
    elif origen == "cabinet":
        if cab_date is not None:
            resolved = cab_date
            source = "lead_created_at_cabinet"
            status = "resolved_by_origen"
        else:
            status = "missing"
            warning = "lead_created_at_missing"
    # ── Fleet origen ──
    elif origen == "fleet":
        if fleet_date is not None:
            resolved = fleet_date
            source = "lead_created_at_fleet"
            status = "resolved_by_origen"
        else:
            status = "missing"
            warning = "lead_created_at_missing"
    # ── Unknown/null origen ──
    else:
        if cab_date is not None:
            resolved = cab_date
            source = "lead_created_at_cabinet"
            status = "resolved_by_available_date"
            warning = "origin_unclear"
        elif fleet_date is not None:
            resolved = fleet_date
            source = "lead_created_at_fleet"
            status = "resolved_by_available_date"
            warning = "origin_unclear"
        else:
            status = "missing"
            warning = "lead_created_at_missing"

    # ── Invalid date detection ──
    if status == "missing":
        has_cabinet_value = lca_cabinet is not None and str(lca_cabinet).strip()
        has_fleet_value = lca_fleet is not None and str(lca_fleet).strip()
        if has_cabinet_value or has_fleet_value:
            status = "invalid_date"
            warning = "lead_created_at_invalid_format"

    return {
        "lead_created_at_resolved": str(resolved) if resolved else None,
        "lead_created_at_source": source,
        "lead_created_at_status": status,
        "lead_created_at_warning": warning,
    }
