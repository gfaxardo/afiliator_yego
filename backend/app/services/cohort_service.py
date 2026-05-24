"""
Cohort Service — Modelo temporal de cohortes ISO para Liquidador Scouts.

FASE 2A.1: Las cohortes usan acquisition_anchor_date por defecto.
hire_date_legacy sigue disponible como modo de comparacion QA.

La cohorte se define por la semana ISO de la fecha ancla.
date_basis = "acquisition_anchor" (default) | "hire_date_legacy"
"""
import time as _time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings

SOURCE_TABLE = settings.SOURCE_TABLE
STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '30000ms'"


def iso_week_dates(iso_year: int, iso_week: int) -> tuple:
    """Return (monday, sunday) for an ISO week number."""
    jan4 = date(iso_year, 1, 4)
    monday = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def cohort_maturity(cohort_to: date, maturity_days: int = 7) -> date:
    """Fecha en que la cohorte madura (cohort_to + maturity_days)."""
    return cohort_to + timedelta(days=maturity_days)


def _iso_year_expr(col: str) -> str:
    return f"EXTRACT(ISOYEAR FROM {col}::date)::int"


def _iso_week_expr(col: str) -> str:
    return f"EXTRACT(WEEK FROM {col}::date)::int"


def _resolve_anchors_batch(db: Session, date_basis: str) -> List[Dict[str, Any]]:
    """
    Resolve anchor dates for all drivers in module_ct_cabinet_drivers.
    Returns list of dicts with driver_id, origen, anchor_date, anchor fields.
    """
    if date_basis == "hire_date_legacy":
        rows = db.execute(text(f"""
            SELECT driver_id, origen, hire_date::date AS anchor_date,
                   'hire_date_legacy' AS anchor_source, 'strong' AS anchor_confidence,
                   'legacy' AS acquisition_type, false AS reactivation_flag,
                   NULL::text AS anchor_warning
            FROM {SOURCE_TABLE}
            WHERE hire_date IS NOT NULL AND hire_date::text != ''
        """)).fetchall()
        return [
            {
                "driver_id": r[0], "origen": r[1],
                "anchor_date": r[2], "anchor_source": r[3],
                "anchor_confidence": r[4], "acquisition_type": r[5],
                "reactivation_flag": r[6], "anchor_warning": r[7],
            }
            for r in rows if r[2] is not None
        ]

    # ── acquisition_anchor mode ──
    from app.services.acquisition_anchor_service import (
        resolve_acquisition_anchor, _batch_load_drivers, _batch_match_leads,
    )

    cols = ["driver_id", "driver_nombre", "driver_apellido", "driver_placa",
            "hire_date", "lead_created_at", "created_at", "origen"]
    rows = db.execute(text(f"""
        SELECT {', '.join(cols)}
        FROM {SOURCE_TABLE}
    """)).fetchall()

    all_driver_ids = [r[0] for r in rows]
    drivers_map = _batch_load_drivers(db, all_driver_ids)

    cabinet_without_lca = [
        {"driver_id": r[0], "driver_nombre": r[1], "driver_apellido": r[2],
         "driver_placa": r[3], "origen": r[7]}
        for r in rows if (r[7] or "").lower() == "cabinet" and not r[5]
    ]
    leads_map = _batch_match_leads(db, cabinet_without_lca)

    results = []
    for r in rows:
        row_dict = dict(zip(cols, r))
        anchor = resolve_acquisition_anchor(
            row_dict,
            drivers_data=drivers_map.get(row_dict["driver_id"]),
            leads_data=leads_map.get(row_dict["driver_id"]),
        )
        anchor_date_str = anchor.get("acquisition_anchor_date")
        anchor_date = None
        if anchor_date_str:
            try:
                anchor_date = datetime.strptime(anchor_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        results.append({
            "driver_id": row_dict["driver_id"],
            "origen": row_dict.get("origen", ""),
            "anchor_date": anchor_date,
            "anchor_source": anchor.get("anchor_source"),
            "anchor_confidence": anchor.get("anchor_confidence"),
            "acquisition_type": anchor.get("acquisition_type"),
            "reactivation_flag": anchor.get("reactivation_flag", False),
            "anchor_warning": anchor.get("anchor_warning"),
            "hire_date": row_dict.get("hire_date"),
        })
    return results


def get_iso_cohorts(
    db: Session,
    readiness_filter: Optional[str] = None,
    date_basis: str = "acquisition_anchor",
) -> List[Dict[str, Any]]:
    """
    Devuelve cohortes ISO detectadas desde la fuente.
    Agrupa por ISO week de acquisition_anchor_date (default) o hire_date (legacy).

    date_basis: "acquisition_anchor" | "hire_date_legacy"
    """
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))
    today = date.today()

    if date_basis == "hire_date_legacy":
        return _get_cohorts_legacy_sql(db, today, readiness_filter)

    # ── acquisition_anchor: Python-side anchor resolution + grouping ──
    anchors = _resolve_anchors_batch(db, date_basis)

    # Group by anchor ISO week
    cohort_groups: Dict[str, Dict[str, Any]] = {}
    for a in anchors:
        ad = a["anchor_date"]
        if ad is None:
            continue
        iso_year, iso_week, _ = ad.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        if key not in cohort_groups:
            monday, sunday = iso_week_dates(iso_year, iso_week)
            cohort_groups[key] = {
                "iso_year": iso_year,
                "iso_week": iso_week,
                "cohort_from": monday,
                "cohort_to": sunday,
                "total_drivers": 0,
                "drivers_with_scout": 0,
                "reactivations": 0,
                "strong_anchors": 0,
                "medium_anchors": 0,
                "weak_anchors": 0,
                "fleet_migration": 0,
                "cabinet_new": 0,
                "cabinet_reactivated": 0,
                "cabinet_unknown_no_lca": 0,
            }
        cg = cohort_groups[key]
        cg["total_drivers"] += 1
        if a["anchor_confidence"] == "strong":
            cg["strong_anchors"] += 1
        elif a["anchor_confidence"] == "medium":
            cg["medium_anchors"] += 1
        elif a["anchor_confidence"] == "weak":
            cg["weak_anchors"] += 1
        if a["acquisition_type"] == "fleet_migration":
            cg["fleet_migration"] += 1
        if a["acquisition_type"] in ("cabinet_new_same_day", "cabinet_delayed_conversion",
                                      "cabinet_recovered_lead", "cabinet_recovered_lead_delayed"):
            cg["cabinet_new"] += 1
        if a["reactivation_flag"]:
            cg["reactivations"] += 1
            cg["cabinet_reactivated"] += 1
        if a["acquisition_type"] == "cabinet_unknown_no_lca":
            cg["cabinet_unknown_no_lca"] += 1

    # Load cutoff runs
    cutoff_rows = db.execute(text(
        "SELECT id, cohort_iso_week, status, created_at, approved_at, paid_at "
        "FROM scout_liq_cutoff_runs WHERE cohort_iso_week IS NOT NULL ORDER BY created_at DESC"
    )).fetchall()
    cutoff_by_cohort: Dict[str, dict] = {}
    for cr in cutoff_rows:
        cw = cr[1]
        if cw and cw not in cutoff_by_cohort:
            cutoff_by_cohort[cw] = {
                "cutoff_run_id": cr[0], "cutoff_status": cr[2],
                "created_at": str(cr[3]) if cr[3] else None,
                "approved_at": str(cr[4]) if cr[4] else None,
                "paid_at": str(cr[5]) if cr[5] else None,
            }

    # Scout assignments
    scout_drivers = set()
    try:
        assigned = db.execute(text(
            "SELECT DISTINCT driver_id FROM scout_liq_driver_assignments WHERE status = 'active'"
        )).fetchall()
        scout_drivers = {r[0] for r in assigned}
    except Exception:
        pass

    for a in anchors:
        ad = a["anchor_date"]
        if ad is None:
            continue
        iso_year, iso_week, _ = ad.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        if key in cohort_groups and a["driver_id"] in scout_drivers:
            cohort_groups[key]["drivers_with_scout"] += 1

    result = []
    for key, meta in sorted(cohort_groups.items(), key=lambda x: (x[1]["iso_year"], x[1]["iso_week"]), reverse=True):
        maturity_days = 7
        maturity_at = cohort_maturity(meta["cohort_to"], maturity_days)
        cutoff = cutoff_by_cohort.get(key)
        cutoff_status = cutoff["cutoff_status"] if cutoff else None

        if cutoff_status == "paid":
            readiness = "paid"
        elif cutoff_status in ("calculated", "reviewed", "approved"):
            readiness = "locked"
        elif maturity_at > today:
            readiness = "open"
        else:
            readiness = "mature"

        if readiness_filter and readiness_filter != readiness:
            continue

        meta["drivers_without_scout"] = max(0, meta["total_drivers"] - meta.get("drivers_with_scout", 0))

        result.append({
            "cohort_iso_week": key,
            "cohort_label": f"S{meta['iso_week']:02d}-{meta['iso_year']}",
            "iso_year": meta["iso_year"],
            "iso_week": meta["iso_week"],
            "cohort_from": meta["cohort_from"].isoformat(),
            "cohort_to": meta["cohort_to"].isoformat(),
            "maturity_days": maturity_days,
            "maturity_completed_at": maturity_at.isoformat(),
            "is_mature": maturity_at <= today,
            "total_drivers": meta["total_drivers"],
            "drivers_with_scout": meta.get("drivers_with_scout", 0),
            "drivers_without_scout": meta.get("drivers_without_scout", 0),
            "activated": 0,
            "converted_5v7d": 0,
            "readiness_status": readiness,
            "cutoff_run_id": cutoff["cutoff_run_id"] if cutoff else None,
            "cutoff_status": cutoff_status,
            # ── Fase 2A.1: Anchor quality KPIs ──
            "date_basis": date_basis,
            "strong_anchors": meta["strong_anchors"],
            "medium_anchors": meta["medium_anchors"],
            "weak_anchors": meta["weak_anchors"],
            "reactivations": meta["reactivations"],
            "fleet_migration": meta["fleet_migration"],
            "cabinet_new": meta["cabinet_new"],
            "cabinet_reactivated": meta["cabinet_reactivated"],
            "cabinet_unknown_no_lca": meta["cabinet_unknown_no_lca"],
        })

    elapsed = round((_time.perf_counter() - t0) * 1000)
    return result


def _get_cohorts_legacy_sql(db: Session, today: date, readiness_filter: Optional[str]) -> List[Dict[str, Any]]:
    """Legacy mode: cohorts by raw hire_date ISO week (SQL, no anchor resolution)."""
    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")

    cohort_sql = f"""
        SELECT {iy} AS iso_year, {iw} AS iso_week,
               COUNT(*) AS total_drivers,
               COUNT(DISTINCT src.driver_id) FILTER (
                   WHERE src.driver_id IN (
                       SELECT da.driver_id FROM scout_liq_driver_assignments da WHERE da.status = 'active'
                   )
               ) AS drivers_with_scout
        FROM {SOURCE_TABLE} src
        WHERE src.hire_date IS NOT NULL AND src.hire_date != ''
        GROUP BY {iy}, {iw}
        ORDER BY {iy} DESC, {iw} DESC
    """
    cohorts_raw = db.execute(text(cohort_sql)).fetchall()
    if not cohorts_raw:
        return []

    cohort_metrics: Dict[str, Dict[str, Any]] = {}
    for row in cohorts_raw:
        yr = int(row[0]); wk = int(row[1])
        key = f"{yr}-W{wk:02d}"
        monday, sunday = iso_week_dates(yr, wk)
        cohort_metrics[key] = {
            "iso_year": yr, "iso_week": wk,
            "cohort_from": monday, "cohort_to": sunday,
            "total_drivers": row[2] or 0,
            "drivers_with_scout": row[3] or 0,
            "drivers_without_scout": max(0, (row[2] or 0) - (row[3] or 0)),
            "activated": 0, "converted_5v7d": 0,
            "strong_anchors": 0, "medium_anchors": 0, "weak_anchors": 0,
            "reactivations": 0, "fleet_migration": 0,
            "cabinet_new": 0, "cabinet_reactivated": 0, "cabinet_unknown_no_lca": 0,
        }

    cutoff_rows = db.execute(text(
        "SELECT id, cohort_iso_week, status, created_at, approved_at, paid_at "
        "FROM scout_liq_cutoff_runs WHERE cohort_iso_week IS NOT NULL ORDER BY created_at DESC"
    )).fetchall()
    cutoff_by_cohort: Dict[str, dict] = {}
    for cr in cutoff_rows:
        cw = cr[1]
        if cw and cw not in cutoff_by_cohort:
            cutoff_by_cohort[cw] = {
                "cutoff_run_id": cr[0], "cutoff_status": cr[2],
                "created_at": str(cr[3]) if cr[3] else None,
                "approved_at": str(cr[4]) if cr[4] else None,
                "paid_at": str(cr[5]) if cr[5] else None,
            }

    result = []
    for key, meta in sorted(cohort_metrics.items(), key=lambda x: (x[1]["iso_year"], x[1]["iso_week"]), reverse=True):
        maturity_days = 7
        maturity_at = cohort_maturity(meta["cohort_to"], maturity_days)
        cutoff = cutoff_by_cohort.get(key)
        cutoff_status = cutoff["cutoff_status"] if cutoff else None
        if cutoff_status == "paid": readiness = "paid"
        elif cutoff_status in ("calculated", "reviewed", "approved"): readiness = "locked"
        elif maturity_at > today: readiness = "open"
        else: readiness = "mature"
        if readiness_filter and readiness_filter != readiness: continue
        result.append({
            "cohort_iso_week": key,
            "cohort_label": f"S{meta['iso_week']:02d}-{meta['iso_year']}",
            "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
            "cohort_from": meta["cohort_from"].isoformat(),
            "cohort_to": meta["cohort_to"].isoformat(),
            "maturity_days": maturity_days,
            "maturity_completed_at": maturity_at.isoformat(),
            "is_mature": maturity_at <= today,
            "total_drivers": meta["total_drivers"],
            "drivers_with_scout": meta.get("drivers_with_scout", 0),
            "drivers_without_scout": meta.get("drivers_without_scout", 0),
            "activated": 0, "converted_5v7d": 0,
            "readiness_status": readiness,
            "cutoff_run_id": cutoff["cutoff_run_id"] if cutoff else None,
            "cutoff_status": cutoff_status,
            "date_basis": "hire_date_legacy",
            "strong_anchors": 0, "medium_anchors": 0, "weak_anchors": 0,
            "reactivations": 0, "fleet_migration": 0,
            "cabinet_new": 0, "cabinet_reactivated": 0, "cabinet_unknown_no_lca": 0,
        })
    return result


def get_cohort_diagnostic(db: Session, date_basis: str = "acquisition_anchor") -> Dict[str, Any]:
    """Diagnostico de cohortes con anchor KPIs."""
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))
    today = date.today()
    cohorts = get_iso_cohorts(db, date_basis=date_basis)

    open_cohorts = [c for c in cohorts if c["readiness_status"] == "open"]
    mature_cohorts = [c for c in cohorts if c["readiness_status"] == "mature"]
    locked_cohorts = [c for c in cohorts if c["readiness_status"] == "locked"]
    paid_cohorts = [c for c in cohorts if c["readiness_status"] == "paid"]
    liquidable = [c for c in mature_cohorts if not c.get("cutoff_run_id")]

    return {
        "current_date": today.isoformat(),
        "date_basis": date_basis,
        "total_cohorts": len(cohorts),
        "by_readiness": {
            "open": len(open_cohorts), "mature": len(mature_cohorts),
            "locked": len(locked_cohorts), "paid": len(paid_cohorts),
        },
        "liquidable_cohorts": [c["cohort_iso_week"] for c in liquidable],
        "latest_open": open_cohorts[0]["cohort_iso_week"] if open_cohorts else None,
        "latest_mature": mature_cohorts[0]["cohort_iso_week"] if mature_cohorts else None,
        "latest_mature_matures_on": mature_cohorts[0]["maturity_completed_at"] if mature_cohorts else None,
        "open_details": [
            {"cohort_iso_week": c["cohort_iso_week"],
             "maturity_completed_at": c["maturity_completed_at"],
             "days_until_mature": (datetime.strptime(c["maturity_completed_at"], "%Y-%m-%d").date() - today).days,
             "total_drivers": c["total_drivers"]}
            for c in open_cohorts[:5]
        ],
        "mature_details": [
            {"cohort_iso_week": c["cohort_iso_week"],
             "maturity_completed_at": c["maturity_completed_at"],
             "total_drivers": c["total_drivers"],
             "reactivations": c.get("reactivations", 0),
             "cabinet_new": c.get("cabinet_new", 0),
             "has_cutoff": c.get("cutoff_run_id") is not None}
            for c in mature_cohorts[:5]
        ],
        "anchor_quality": {
            "total_strong": sum(c.get("strong_anchors", 0) for c in cohorts),
            "total_medium": sum(c.get("medium_anchors", 0) for c in cohorts),
            "total_weak": sum(c.get("weak_anchors", 0) for c in cohorts),
            "total_reactivations": sum(c.get("reactivations", 0) for c in cohorts),
            "total_fleet": sum(c.get("fleet_migration", 0) for c in cohorts),
        },
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }
