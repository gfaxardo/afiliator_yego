"""
Acquisition Anchor Service — Fase 1 Semantic Layer.

Resuelve la fecha ancla de adquisición (acquisition_anchor_date) por conductor,
con trazabilidad completa de fuente, confianza y tipo de adquisición.

Reglas:
- CABINET: lead_created_at > cabinet_leads LCA > drivers.hire_date > cabinet.hire_date > created_at
- FLEET:  drivers.hire_date > cabinet.hire_date > created_at

SOLO LECTURA. No modifica tablas RAW.
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.services.lead_created_at_resolver import resolve_lead_created_at

_logger = logging.getLogger("acquisition_anchor")

CABINET_TABLE = settings.SOURCE_TABLE or "module_ct_cabinet_drivers"
DRIVERS_TABLE = "drivers"
LEADS_TABLE = "module_ct_cabinet_leads"


def _safe_date(value: Any) -> Optional[date]:
    """Cast a value to date safely."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value[:19] if len(value) >= 19 else value, fmt).date()
            except ValueError:
                continue
    return None


def resolve_acquisition_anchor(
    row: Dict[str, Any],
    drivers_data: Optional[Dict[str, Any]] = None,
    leads_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resuelve el acquisition_anchor_date para un conductor.

    Args:
        row: dict con columnas de module_ct_cabinet_drivers
        drivers_data: dict con columnas de drivers (por driver_id JOIN)
        leads_data: dict con columnas de module_ct_cabinet_leads (por placa/nombre)

    Returns:
        dict con todos los campos semánticos.
    """
    origen = (row.get("origen") or "").strip().lower()
    driver_id = row.get("driver_id")
    hire_date_raw = row.get("hire_date")
    created_at_raw = row.get("created_at")

    lca = resolve_lead_created_at(row)
    lead_created_at_raw = lca["lead_created_at_resolved"]

    cabinet_hire_date = _safe_date(hire_date_raw)
    cabinet_lead_created_at = _safe_date(lead_created_at_raw)
    cabinet_created_at = _safe_date(created_at_raw)

    drivers_hire_date = None
    if drivers_data:
        drivers_hire_date = _safe_date(drivers_data.get("hire_date"))

    leads_lead_created_at = None
    if leads_data:
        leads_lead_created_at = _safe_date(leads_data.get("lead_created_at"))

    anchor_date = None
    anchor_source = "none"
    anchor_confidence = "none"
    anchor_warning = None
    acquisition_type = "unknown"
    reactivation_flag = False
    days_hire_vs_anchor = None

    if origen == "fleet":
        anchor_date, anchor_source, anchor_confidence, anchor_warning, acquisition_type, reactivation_flag = (
            _resolve_fleet(cabinet_hire_date, cabinet_created_at, drivers_hire_date)
        )
    elif origen == "cabinet":
        anchor_date, anchor_source, anchor_confidence, anchor_warning, acquisition_type, reactivation_flag = (
            _resolve_cabinet(
                cabinet_lead_created_at, cabinet_hire_date, cabinet_created_at,
                drivers_hire_date, leads_lead_created_at,
            )
        )
    else:
        # Unknown origin — use best available
        candidates = [
            (cabinet_lead_created_at, "cabinet_drivers.lead_created_at", "strong"),
            (leads_lead_created_at, "cabinet_leads.lead_created_at", "medium"),
            (drivers_hire_date, "drivers.hire_date", "medium"),
            (cabinet_hire_date, "cabinet_drivers.hire_date", "medium"),
            (cabinet_created_at, "cabinet_drivers.created_at", "weak"),
        ]
        for dt, src, conf in candidates:
            if dt is not None:
                anchor_date = dt
                anchor_source = src
                anchor_confidence = conf
                if src.endswith("created_at"):
                    anchor_warning = "unknown origin; using ETL created_at fallback"
                break
        acquisition_type = "unknown_origin"

    # Compute days_hire_vs_anchor
    hire_for_gap = cabinet_hire_date or drivers_hire_date
    if anchor_date and hire_for_gap:
        days_hire_vs_anchor = (hire_for_gap - anchor_date).days

    return {
        "driver_id": driver_id,
        "origen": origen,
        "acquisition_anchor_date": str(anchor_date) if anchor_date else None,
        "anchor_source": anchor_source,
        "anchor_confidence": anchor_confidence,
        "acquisition_type": acquisition_type,
        "anchor_warning": anchor_warning,
        "reactivation_flag": reactivation_flag,
        "days_hire_vs_anchor": days_hire_vs_anchor,
        "cabinet_lead_created_at": str(cabinet_lead_created_at) if cabinet_lead_created_at else None,
        "cabinet_hire_date": str(cabinet_hire_date) if cabinet_hire_date else None,
        "drivers_hire_date": str(drivers_hire_date) if drivers_hire_date else None,
        "leads_lead_created_at": str(leads_lead_created_at) if leads_lead_created_at else None,
        "lead_created_at_resolved": lca["lead_created_at_resolved"],
        "lead_created_at_source": lca["lead_created_at_source"],
        "lead_created_at_status": lca["lead_created_at_status"],
        "lead_created_at_warning": lca["lead_created_at_warning"],
    }


def _resolve_fleet(
    cabinet_hd: Optional[date],
    cabinet_ca: Optional[date],
    drivers_hd: Optional[date],
) -> Tuple[Optional[date], str, str, Optional[str], str, bool]:
    """Resuelve anchor para fleet."""
    if drivers_hd is not None:
        return (drivers_hd, "drivers.hire_date", "strong", None, "fleet_migration", False)
    if cabinet_hd is not None:
        return (cabinet_hd, "cabinet_drivers.hire_date", "medium",
                "fleet without drivers.hire_date; using cabinet driver hire_date fallback",
                "fleet_migration", False)
    if cabinet_ca is not None:
        return (cabinet_ca, "cabinet_drivers.created_at", "weak",
                "fleet without hire_date; using ETL created_at fallback",
                "fleet_migration", False)
    return (None, "none", "none", "no date available for fleet driver", "unknown", False)


def _resolve_cabinet(
    lca: Optional[date],
    cabinet_hd: Optional[date],
    cabinet_ca: Optional[date],
    drivers_hd: Optional[date],
    leads_lca: Optional[date],
) -> Tuple[Optional[date], str, str, Optional[str], str, bool]:
    """Resuelve anchor para cabinet."""

    # Rule 1: cabinet_drivers.lead_created_at
    if lca is not None:
        atype = "cabinet_new_same_day"
        react = False
        if cabinet_hd is not None:
            if cabinet_hd > lca:
                atype = "cabinet_delayed_conversion"
            elif cabinet_hd < lca:
                atype = "cabinet_reactivated_existing_driver"
                react = True
        return (lca, "cabinet_drivers.lead_created_at", "strong", None, atype, react)

    # Rule 2: cabinet_leads.lead_created_at (pre-matched, single match only)
    if leads_lca is not None:
        atype = "cabinet_recovered_lead"
        react = False
        if cabinet_hd is not None:
            if cabinet_hd > leads_lca:
                atype = "cabinet_recovered_lead_delayed"
            elif cabinet_hd < leads_lca:
                atype = "cabinet_recovered_lead_reactivated"
                react = True
        return (leads_lca, "cabinet_leads.lead_created_at", "medium",
                "lead_created_at recovered from cabinet_leads", atype, react)

    # Rule 3: drivers.hire_date
    if drivers_hd is not None:
        return (drivers_hd, "drivers.hire_date", "medium",
                "missing lead_created_at; using operational hire_date fallback",
                "cabinet_unknown_no_lca", False)

    # Rule 4: cabinet_drivers.hire_date
    if cabinet_hd is not None:
        return (cabinet_hd, "cabinet_drivers.hire_date", "medium",
                "missing lead_created_at; using cabinet driver hire_date fallback",
                "cabinet_unknown_no_lca", False)

    # Rule 5: created_at (ETL fallback)
    if cabinet_ca is not None:
        return (cabinet_ca, "cabinet_drivers.created_at", "weak",
                "missing business anchor; using ETL created_at fallback",
                "cabinet_unknown_no_lca", False)

    return (None, "none", "none", "no date available", "unknown", False)


def resolve_payment_anchor_status(anchor_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive payment_anchor_status and is_auto_payable_anchor from anchor resolution.

    Rules:
    - official_strong: cabinet with lead_created_at from cabinet_drivers (official source)
    - official_medium: cabinet with lead_created_at recovered from cabinet_leads
    - reported_pending_validation: cabinet without official LCA but with reported_anchor_date
    - fallback_operational_only: cabinet without LCA, using hire_date/created_at
    - blocked_missing_official_anchor: cabinet without ANY anchor
    - fleet_official_hire_date: fleet with drivers.hire_date or cabinet.hire_date
    - fleet_fallback: fleet using created_at
    """
    origen = anchor_result.get("origen", "")
    source = anchor_result.get("anchor_source", "")
    confidence = anchor_result.get("anchor_confidence", "")
    reported = anchor_result.get("reported_anchor_date")

    status = "unknown"
    is_auto = False
    block_reason = None

    if origen == "fleet":
        if confidence in ("strong", "medium") and "hire_date" in source:
            status = "fleet_official_hire_date"
            is_auto = True
        elif "created_at" in source:
            status = "fleet_fallback"
            is_auto = False
            block_reason = "Fleet sin hire_date; usando ETL created_at como fallback."
        else:
            status = "fleet_fallback"
            is_auto = False
            block_reason = "Fleet sin anchor definido."
    elif origen == "cabinet":
        if source == "cabinet_drivers.lead_created_at":
            status = "official_strong"
            is_auto = True
        elif source == "cabinet_leads.lead_created_at":
            status = "official_medium"
            is_auto = True
        elif reported:
            status = "reported_pending_validation"
            is_auto = False
            block_reason = "Ancla reportada por scout/carga masiva; requiere validacion antes de pago."
        elif source in ("drivers.hire_date", "cabinet_drivers.hire_date",
                         "cabinet_drivers.created_at"):
            status = "fallback_operational_only"
            is_auto = False
            block_reason = "Cabinet sin lead_created_at oficial; requiere validacion antes de pago."
        elif source == "none":
            status = "blocked_missing_official_anchor"
            is_auto = False
            block_reason = "Sin fecha ancla disponible."
        else:
            status = "fallback_operational_only"
            is_auto = False
            block_reason = "Cabinet sin lead_created_at oficial."
    else:
        # Unknown origin
        if confidence in ("strong", "medium"):
            status = "official_medium"
            is_auto = True
        else:
            status = "fallback_operational_only"
            is_auto = False
            block_reason = "Origen desconocido; ancla no oficial."

    return {
        "payment_anchor_status": status,
        "is_auto_payable_anchor": is_auto,
        "anchor_payment_block_reason": block_reason,
    }


# ── Batch enrichment from drivers table ─────────────────────────

def _batch_load_drivers(db: Session, driver_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load drivers data for a batch of driver_ids."""
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    sql = f"""
        SELECT driver_id, hire_date, fire_date, active, phone,
               license_number, license_normalized_number
        FROM {DRIVERS_TABLE}
        WHERE driver_id IN ({placeholders})
    """
    try:
        rows = db.execute(text(sql), params).fetchall()
        return {
            r[0]: {
                "hire_date": r[1],
                "fire_date": r[2],
                "active": r[3],
                "phone": r[4],
                "license_number": r[5],
                "license_normalized_number": r[6],
            }
            for r in rows
        }
    except Exception as e:
        _logger.warning(f"Failed to batch load drivers: {e}")
        return {}


def _batch_match_leads(
    db: Session,
    cabinet_rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Match cabinet drivers without LCA to module_ct_cabinet_leads.
    Uses plate and name matching. Only returns unambiguous single matches.

    Returns: dict[driver_id] -> {lead_created_at, match_key}
    """
    if not cabinet_rows:
        return {}

    # Build sets for matching
    driver_ids = [r["driver_id"] for r in cabinet_rows]
    plates = [r.get("driver_placa", "") for r in cabinet_rows if r.get("driver_placa")]
    names_first = [r.get("driver_nombre", "") for r in cabinet_rows if r.get("driver_nombre")]
    names_last = [r.get("driver_apellido", "") for r in cabinet_rows if r.get("driver_apellido")]

    if not plates and not (names_first and names_last):
        return {}

    # Build SQL for plate match
    plate_conditions = []
    name_conditions = []
    params = {}

    for i, r in enumerate(cabinet_rows):
        did = r["driver_id"]
        placa = (r.get("driver_placa") or "").strip().upper()
        nombre = (r.get("driver_nombre") or "").strip().lower()
        apellido = (r.get("driver_apellido") or "").strip().lower()

        if placa:
            plate_conditions.append(f"(:placa_{i})")
            params[f"placa_{i}"] = placa
        if nombre and apellido:
            name_conditions.append(f"(:fn_{i}, :ln_{i})")
            params[f"fn_{i}"] = nombre
            params[f"ln_{i}"] = apellido

    result = {}

    # Plate match (higher confidence)
    if plate_conditions:
        plate_list = ", ".join(plate_conditions)
        plate_sql = f"""
            SELECT UPPER(cl.asset_plate_number) AS plate, cl.lead_created_at, cl.id
            FROM {LEADS_TABLE} cl
            WHERE UPPER(cl.asset_plate_number) IN ({plate_list})
              AND cl.lead_created_at IS NOT NULL
              AND cl.asset_plate_number IS NOT NULL
              AND cl.asset_plate_number != ''
        """
        try:
            plate_rows = db.execute(text(plate_sql), params).fetchall()
            # Group by plate — must be unique match
            plate_map: Dict[str, List[Tuple]] = {}
            for pr in plate_rows:
                plate = pr[0]
                if plate not in plate_map:
                    plate_map[plate] = []
                plate_map[plate].append((pr[1], pr[2], "plate"))

            # Assign to drivers (only if unique)
            plate_to_driver: Dict[str, str] = {}
            for r in cabinet_rows:
                placa = (r.get("driver_placa") or "").strip().upper()
                if placa in plate_map and len(plate_map[placa]) == 1:
                    plate_to_driver[placa] = r["driver_id"]

            for placa, matches in plate_map.items():
                if len(matches) == 1 and placa in plate_to_driver:
                    did = plate_to_driver[placa]
                    if did not in result:
                        result[did] = {
                            "lead_created_at": matches[0][0],
                            "match_key": "plate",
                            "lead_id": matches[0][1],
                        }
        except Exception as e:
            _logger.warning(f"Plate match failed: {e}")

    # Name match (fallback, also only unique)
    if name_conditions:
        name_list = ", ".join(name_conditions)
        name_sql = f"""
            SELECT LOWER(cl.first_name) AS fn, LOWER(cl.last_name) AS ln,
                   cl.lead_created_at, cl.id
            FROM {LEADS_TABLE} cl
            WHERE (LOWER(cl.first_name), LOWER(cl.last_name)) IN ({name_list})
              AND cl.lead_created_at IS NOT NULL
        """
        try:
            name_rows = db.execute(text(name_sql), params).fetchall()
            name_map: Dict[Tuple[str, str], List[Tuple]] = {}
            for nr in name_rows:
                key = (nr[0], nr[1])
                if key not in name_map:
                    name_map[key] = []
                name_map[key].append((nr[2], nr[3], "name"))

            for r in cabinet_rows:
                did = r["driver_id"]
                if did in result:
                    continue  # Already matched by plate
                nombre = (r.get("driver_nombre") or "").strip().lower()
                apellido = (r.get("driver_apellido") or "").strip().lower()
                key = (nombre, apellido)
                if key in name_map and len(name_map[key]) == 1:
                    result[did] = {
                        "lead_created_at": name_map[key][0][0],
                        "match_key": "name",
                        "lead_id": name_map[key][0][1],
                    }
        except Exception as e:
            _logger.warning(f"Name match failed: {e}")

    return result


# ── Summary / Reporting ──────────────────────────────────────────

def get_acquisition_anchor_summary(db: Session) -> Dict[str, Any]:
    """
    Computes full summary of acquisition anchor resolution
    across all drivers in module_ct_cabinet_drivers.
    """
    # Load all cabinet drivers
    all_rows = db.execute(text(f"""
        SELECT driver_id, driver_nombre, driver_apellido, driver_placa,
               driver_phone, hire_date, lead_created_at_cabinet, lead_created_at_fleet, created_at,
               origen, status, segment, stage, license
        FROM {CABINET_TABLE}
    """)).fetchall()

    columns = [
        "driver_id", "driver_nombre", "driver_apellido", "driver_placa",
        "driver_phone", "hire_date", "lead_created_at_cabinet", "lead_created_at_fleet", "created_at",
        "origen", "status", "segment", "stage", "license",
    ]
    rows = [dict(zip(columns, r)) for r in all_rows]

    cabinet_rows = [r for r in rows if (r.get("origen") or "").strip().lower() == "cabinet"]
    fleet_rows = [r for r in rows if (r.get("origen") or "").strip().lower() == "fleet"]
    other_rows = [r for r in rows if (r.get("origen") or "").strip().lower() not in ("cabinet", "fleet")]

    all_driver_ids = [r["driver_id"] for r in rows]
    drivers_map = _batch_load_drivers(db, all_driver_ids)

    cabinet_without_lca = [
        r for r in cabinet_rows
        if not resolve_lead_created_at(r).get("lead_created_at_resolved")
    ]
    leads_map = _batch_match_leads(db, cabinet_without_lca)

    # Resolve anchors
    results = []
    for r in rows:
        drv = drivers_map.get(r["driver_id"])
        lds = leads_map.get(r["driver_id"])
        anchor = resolve_acquisition_anchor(r, drv, lds)
        results.append(anchor)

    # Compute stats
    by_origin: Dict[str, int] = {}
    by_anchor_source: Dict[str, int] = {}
    by_anchor_confidence: Dict[str, int] = {}
    by_acquisition_type: Dict[str, int] = {}
    warnings: List[Dict[str, Any]] = []

    cabinet_missing_lca = 0
    cabinet_recovered_lca = 0
    fleet_without_hire_date = 0

    for r in results:
        origen = r["origen"]
        by_origin[origen] = by_origin.get(origen, 0) + 1
        by_anchor_source[r["anchor_source"]] = by_anchor_source.get(r["anchor_source"], 0) + 1
        by_anchor_confidence[r["anchor_confidence"]] = by_anchor_confidence.get(r["anchor_confidence"], 0) + 1
        by_acquisition_type[r["acquisition_type"]] = by_acquisition_type.get(r["acquisition_type"], 0) + 1

        if r["anchor_warning"]:
            warnings.append({
                "driver_id": r["driver_id"],
                "origen": r["origen"],
                "warning": r["anchor_warning"],
                "anchor_source": r["anchor_source"],
            })

        if origen == "cabinet":
            if r["anchor_source"] not in ("cabinet_drivers.lead_created_at", "cabinet_leads.lead_created_at"):
                cabinet_missing_lca += 1
            if r["anchor_source"] == "cabinet_leads.lead_created_at":
                cabinet_recovered_lca += 1

        if origen == "fleet" and r["anchor_source"] == "cabinet_drivers.created_at":
            fleet_without_hire_date += 1

    return {
        "total": len(results),
        "by_origin": [
            {"origen": k, "count": v}
            for k, v in sorted(by_origin.items(), key=lambda x: -x[1])
        ],
        "by_anchor_source": [
            {"anchor_source": k, "count": v}
            for k, v in sorted(by_anchor_source.items(), key=lambda x: -x[1])
        ],
        "by_anchor_confidence": [
            {"anchor_confidence": k, "count": v}
            for k, v in sorted(by_anchor_confidence.items(), key=lambda x: -x[1])
        ],
        "by_acquisition_type": [
            {"acquisition_type": k, "count": v}
            for k, v in sorted(by_acquisition_type.items(), key=lambda x: -x[1])
        ],
        "warnings": warnings[:100],  # Top 100 warnings
        "warning_count": len(warnings),
        "cabinet_missing_lca": cabinet_missing_lca,
        "cabinet_recovered_lca": cabinet_recovered_lca,
        "fleet_without_hire_date": fleet_without_hire_date,
        "reactivation_count": sum(1 for r in results if r["reactivation_flag"]),
    }


def get_acquisition_anchor_samples(
    db: Session,
    origen: Optional[str] = None,
    anchor_source: Optional[str] = None,
    acquisition_type: Optional[str] = None,
    anchor_confidence: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Returns sample rows resolved with anchor data, filterable.
    """
    # Load base data
    where = "1=1"
    if origen:
        where += f" AND origen = :origen"
    params: Dict[str, Any] = {}
    if origen:
        params["origen"] = origen

    all_rows = db.execute(text(f"""
        SELECT driver_id, driver_nombre, driver_apellido, driver_placa,
               driver_phone, hire_date, lead_created_at_cabinet, lead_created_at_fleet, created_at,
               origen, status, segment, stage, license
        FROM {CABINET_TABLE}
        WHERE {where}
        ORDER BY driver_id
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit + 200, "offset": offset}).fetchall()

    columns = [
        "driver_id", "driver_nombre", "driver_apellido", "driver_placa",
        "driver_phone", "hire_date", "lead_created_at_cabinet", "lead_created_at_fleet", "created_at",
        "origen", "status", "segment", "stage", "license",
    ]
    rows_list = [dict(zip(columns, r)) for r in all_rows]
    all_driver_ids = [r["driver_id"] for r in rows_list]
    drivers_map = _batch_load_drivers(db, all_driver_ids)

    cabinet_without_lca = [
        r for r in rows_list
        if (r.get("origen") or "").lower() == "cabinet"
        and not resolve_lead_created_at(r).get("lead_created_at_resolved")
    ]
    leads_map = _batch_match_leads(db, cabinet_without_lca)

    results = []
    for row in rows_list:
        drv = drivers_map.get(row["driver_id"])
        lds = leads_map.get(row["driver_id"])
        anchor = resolve_acquisition_anchor(row, drv, lds)

        # Apply filters
        if anchor_source and anchor["anchor_source"] != anchor_source:
            continue
        if acquisition_type and anchor["acquisition_type"] != acquisition_type:
            continue
        if anchor_confidence and anchor["anchor_confidence"] != anchor_confidence:
            continue

        results.append(anchor)
        if len(results) >= limit:
            break

    return {
        "total_matched_in_window": len(results),
        "limit": limit,
        "offset": offset,
        "filters": {
            "origen": origen,
            "anchor_source": anchor_source,
            "acquisition_type": acquisition_type,
            "anchor_confidence": anchor_confidence,
        },
        "samples": results,
    }
