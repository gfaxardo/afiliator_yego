"""
Health Pipeline Service — Auditoria completa de frescura, derivados,
matching, cohortes, cutoff y jobs.

Distingue:
- fuente stale vs derivados stale
- matching gap vs workflow gap
- job gap

Proporciona recompute seguro de derivados.
"""
import time as _time
import json as _json
import logging
import traceback as _traceback
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError

from app.config import settings

_logger = logging.getLogger("scout_liq_health_pipeline")

SOURCE_TABLE = settings.SOURCE_TABLE
STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '45000ms'"
JOB_RUNS_TABLE = "scout_liq_job_runs"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _table_exists(db: Session, table_name: str) -> bool:
    try:
        row = db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :tbl)"
        ), {"tbl": table_name}).scalar()
        return bool(row)
    except Exception:
        return False


def _status_from_lag(lag_days: Optional[int]) -> str:
    if lag_days is None:
        return "UNKNOWN"
    if lag_days <= 1:
        return "ok"
    if lag_days <= 3:
        return "warning"
    return "blocked"


def _lag_from_date(target_date: Optional[date], reference: Optional[date] = None) -> Optional[int]:
    if target_date is None:
        return None
    ref = reference or date.today()
    return (ref - target_date).days


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE SUMMARY (estructurado completo)
# ═══════════════════════════════════════════════════════════════════════════

def get_pipeline_summary(db: Session) -> Dict[str, Any]:
    """Resumen completo pipeline con fuente, derivados, matching, cohortes, jobs."""
    try:
        return _safe_pipeline_summary(db)
    except Exception as e:
        _logger.error(f"[get_pipeline_summary] {e}\n{_traceback.format_exc()}")
        return _pipeline_fallback(str(e))


def _safe_pipeline_summary(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    today = date.today()
    yesterday = today - timedelta(days=1)

    # ── 1. Fuente operativa ──
    source_info = _evaluate_source(db, today)

    # ── 2. Ultimo recompute de derivados ──
    derived_info = _evaluate_derived(db, today)

    # ── 3. Matching/Asignacion ──
    matching_info = _evaluate_matching(db, today)

    # ── 4. Cohortes ──
    cohorts_info = _evaluate_cohorts_pipeline(db, today)

    # ── 5. Jobs ──
    jobs_info = _evaluate_jobs_pipeline(db, today)

    # ── 6. Alertas ──
    alerts = _build_pipeline_alerts(source_info, derived_info, matching_info, cohorts_info, jobs_info)

    # ── 7. Operational Readiness ──
    readiness = _compute_operational_readiness(source_info, matching_info, cohorts_info, jobs_info)

    # ── 8. Status global ──
    statuses = [
        source_info.get("status", "ok"),
        derived_info.get("status", "ok"),
        matching_info.get("status", "ok"),
        cohorts_info.get("global_status", "ok"),
        jobs_info.get("status", "ok"),
    ]
    if "blocked" in statuses:
        overall = "blocked"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "ok"

    duration = round((_time.perf_counter() - t0) * 1000)

    return {
        "evaluated_at": today.isoformat(),
        "overall_status": overall,
        "closed_day_expected": yesterday.isoformat(),
        "source_operational": source_info,
        "derived_pipeline": derived_info,
        "matching": matching_info,
        "cohorts": cohorts_info.get("cohorts", []),
        "cohorts_summary": {
            "global_status": cohorts_info.get("global_status", "ok"),
            "warning_count": cohorts_info.get("warning_count", 0),
            "blocked_count": cohorts_info.get("blocked_count", 0),
            "total_cohorts": cohorts_info.get("total_cohorts_visible", 0),
        },
        "jobs": jobs_info,
        "alerts": alerts,
        "operational_readiness": readiness,
        "_timing_ms": duration,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. FUENTE OPERATIVA
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_source(db: Session, today: date) -> Dict[str, Any]:
    db.execute(text("SET LOCAL statement_timeout = '30000ms'"))
    yesterday = today - timedelta(days=1)

    cols_row = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :tbl ORDER BY ordinal_position"
    ), {"tbl": SOURCE_TABLE}).fetchall()
    col_names = {r[0] for r in cols_row}

    has_lead_cabinet = "lead_created_at_cabinet" in col_names
    has_lead_fleet = "lead_created_at_fleet" in col_names
    has_hire_date = "hire_date" in col_names
    has_updated_at = "updated_at" in col_names

    if not has_hire_date:
        return {"status": "blocked", "max_hire_date": None, "max_anchor_date": None,
                "anchor_date_source": "none",
                "lag_days": None, "rows_last_1d": 0, "rows_last_3d": 0, "rows_last_7d": 0,
                "total_rows": 0, "message": "Columna hire_date no existe en la fuente",
                "recommended_action": "Verificar tabla fuente y columnas esperadas",
                "column_issues": ["hire_date_missing"]}

    params = {
        "d1": yesterday.isoformat(),
        "d3": (today - timedelta(days=3)).isoformat(),
        "d7": (today - timedelta(days=7)).isoformat(),
    }

    where_clause = "WHERE hire_date IS NOT NULL AND hire_date::text != ''"

    # Query 1: hire_date stats
    hire_sql = f"""
        SELECT MAX(hire_date::date) AS max_hire_date,
               COUNT(*) AS total_rows,
               COUNT(*) FILTER (WHERE hire_date::date >= :d1) AS rows_last_1d,
               COUNT(*) FILTER (WHERE hire_date::date >= :d3) AS rows_last_3d,
               COUNT(*) FILTER (WHERE hire_date::date >= :d7) AS rows_last_7d
        FROM {SOURCE_TABLE} {where_clause}
    """
    try:
        hire_row = db.execute(text(hire_sql), params).mappings().fetchone()
    except Exception as e:
        _logger.warning(f"[_evaluate_source] Hire query error: {e}")
        return {"status": "blocked", "message": f"Error al consultar fuente: {e}",
                "recommended_action": "Revisar acceso a tabla fuente"}

    if not hire_row or hire_row["max_hire_date"] is None:
        return {"status": "blocked", "max_hire_date": None, "max_anchor_date": None,
                "anchor_date_source": "hire_date",
                "lag_days": None, "rows_last_1d": 0, "rows_last_3d": 0, "rows_last_7d": 0,
                "total_rows": 0, "message": "Tabla fuente vacia o sin hire_date valido",
                "recommended_action": "Ejecutar ETL de carga de module_ct_cabinet_drivers"}

    max_hd = hire_row["max_hire_date"]
    total_rows = hire_row["total_rows"] or 0
    rows_1d = hire_row["rows_last_1d"] or 0
    rows_3d = hire_row["rows_last_3d"] or 0
    rows_7d = hire_row["rows_last_7d"] or 0

    lag_days = _lag_from_date(max_hd, today) if max_hd else None
    status = _status_from_lag(lag_days)

    # Query 2: anchor date stats (separate queries for safety)
    max_lca_cabinet = None
    max_lca_fleet = None
    anchor_warnings = []
    anchor_date_source = "hire_date"
    max_anchor_date = str(max_hd) if max_hd else None

    if has_lead_cabinet:
        try:
            cab_row = db.execute(text(f"""
                SELECT MAX(lead_created_at_cabinet::date) AS max_cab
                FROM {SOURCE_TABLE}
                WHERE lead_created_at_cabinet IS NOT NULL AND lead_created_at_cabinet::text != ''
            """)).mappings().fetchone()
            if cab_row and cab_row["max_cab"]:
                max_lca_cabinet = cab_row["max_cab"]
        except Exception:
            pass

    if has_lead_fleet:
        try:
            fleet_row = db.execute(text(f"""
                SELECT MAX(lead_created_at_fleet::date) AS max_fleet
                FROM {SOURCE_TABLE}
                WHERE lead_created_at_fleet IS NOT NULL AND lead_created_at_fleet::text != ''
            """)).mappings().fetchone()
            if fleet_row and fleet_row["max_fleet"]:
                max_lca_fleet = fleet_row["max_fleet"]
        except Exception:
            pass

    # Determine anchor date
    if max_lca_cabinet or max_lca_fleet:
        candidates = []
        if max_lca_cabinet:
            candidates.append(max_lca_cabinet)
        if max_lca_fleet:
            candidates.append(max_lca_fleet)
        max_anchor_date = str(max(candidates))
        anchor_date_source = "lead_created_at"
    else:
        max_anchor_date = str(max_hd) if max_hd else None
        anchor_date_source = "hire_date_fallback"
        anchor_warnings.append("No se detecto lead_created_at; usando hire_date como ancla")

    # Query 3: lead_created_at activity
    cabinet_leads_1d = 0
    fleet_leads_1d = 0
    if has_lead_cabinet:
        try:
            cab_1d = db.execute(text(f"""
                SELECT COUNT(*) FROM {SOURCE_TABLE}
                WHERE lead_created_at_cabinet::date >= :d1
                  AND (origen IS NULL OR origen = '' OR LOWER(origen) = 'cabinet')
            """), {"d1": yesterday.isoformat()}).scalar()
            cabinet_leads_1d = cab_1d or 0
        except Exception:
            pass
    if has_lead_fleet:
        try:
            fleet_1d = db.execute(text(f"""
                SELECT COUNT(*) FROM {SOURCE_TABLE}
                WHERE lead_created_at_fleet::date >= :d1 AND LOWER(origen) = 'fleet'
            """), {"d1": yesterday.isoformat()}).scalar()
            fleet_leads_1d = fleet_1d or 0
        except Exception:
            pass

    # Query 4: last source update
    last_source_update = None
    if has_updated_at:
        try:
            upd_row = db.execute(text(f"""
                SELECT MAX(updated_at::text) AS last_upd FROM {SOURCE_TABLE}
            """)).mappings().fetchone()
            if upd_row:
                last_source_update = str(upd_row["last_upd"]) if upd_row["last_upd"] else None
        except Exception:
            pass

    message_parts = []
    if lag_days is not None and lag_days > 1:
        message_parts.append(f"Fuente atrasada {lag_days} dias. Ultima hire_date: {max_hd}")
    if rows_1d == 0:
        message_parts.append("Sin nuevos drivers en el ultimo dia")
    if rows_3d == 0:
        message_parts.append("Sin carga en los ultimos 3 dias")

    if not message_parts:
        message = "Fuente operativa al dia"
        recommended = None
    else:
        message = "; ".join(message_parts)
        if lag_days and lag_days > 1:
            recommended = "Revisar cronjob/ETL de carga de module_ct_cabinet_drivers"
        else:
            recommended = "Monitorear carga de fuente operativa"

    result = {
        "status": status,
        "max_hire_date": str(max_hd) if max_hd else None,
        "max_anchor_date": max_anchor_date,
        "anchor_date_source": anchor_date_source,
        "lag_days": lag_days,
        "rows_last_1d": rows_1d,
        "rows_last_3d": rows_3d,
        "rows_last_7d": rows_7d,
        "total_rows": total_rows,
        "message": message,
        "recommended_action": recommended,
    }

    if anchor_warnings:
        result["anchor_warnings"] = anchor_warnings
    if max_lca_cabinet is not None:
        result["max_lead_created_at_cabinet"] = str(max_lca_cabinet)
    if max_lca_fleet is not None:
        result["max_lead_created_at_fleet"] = str(max_lca_fleet)
    result["cabinet_leads_last_1d"] = cabinet_leads_1d
    result["fleet_leads_last_1d"] = fleet_leads_1d
    if last_source_update:
        result["last_source_update"] = last_source_update

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. DERIVADOS / RECOMPUTE TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_derived(db: Session, today: date) -> Dict[str, Any]:
    db.execute(text(STATEMENT_TIMEOUT))

    last_recompute = None
    if _table_exists(db, JOB_RUNS_TABLE):
        row = db.execute(text(
            "SELECT MAX(finished_at), MAX(started_at) FROM scout_liq_job_runs "
            "WHERE job_type = 'health_recompute' AND status = 'success'"
        )).fetchone()
        if row and row[0]:
            last_recompute = str(row[0])

    # Check if health events are stale relative to source
    source_max_date = None
    try:
        src = db.execute(text(
            f"SELECT MAX(hire_date::date) FROM {SOURCE_TABLE} WHERE hire_date IS NOT NULL AND hire_date::text != ''"
        )).scalar()
        if src:
            source_max_date = src
    except Exception:
        pass

    stale_deps = []
    recompute_lag = None

    if last_recompute:
        try:
            rec_date = datetime.fromisoformat(last_recompute).date()
            recompute_lag = _lag_from_date(rec_date, today)
        except (ValueError, TypeError):
            pass

    # Check cohort/cutoff freshness
    try:
        last_cohort_eval = db.execute(text(
            "SELECT MAX(detected_at) FROM scout_liq_health_events"
        )).scalar()
        if last_cohort_eval:
            if hasattr(last_cohort_eval, 'date'):
                eval_date = last_cohort_eval.date()
            elif isinstance(last_cohort_eval, datetime):
                eval_date = last_cohort_eval.date()
            else:
                eval_date = datetime.fromisoformat(str(last_cohort_eval)).date()
            # If source has newer data than last evaluation
            if source_max_date and eval_date < source_max_date:
                stale_deps.append("health_events_detection_stale")
    except Exception:
        pass

    # Check if registry snapshot is stale
    try:
        last_registry = db.execute(text(
            "SELECT MAX(last_refresh_at) FROM scout_liq_refresh_registry"
        )).scalar()
        if last_registry and source_max_date:
            if hasattr(last_registry, 'date'):
                reg_date = last_registry.date()
            elif isinstance(last_registry, datetime):
                reg_date = last_registry.date()
            else:
                reg_date = datetime.fromisoformat(str(last_registry)).date()
            if reg_date < source_max_date:
                stale_deps.append("registry_snapshot_stale")
    except Exception:
        stale_deps.append("registry_table_unavailable")

    if stale_deps:
        status = "warning"
        message = f"Derivados posiblemente stale: {', '.join(stale_deps)}"
        recommended = "Ejecutar recompute de derivados (POST /health/recompute-derived)"
    elif recompute_lag is not None and recompute_lag > 1:
        status = "warning"
        message = f"Ultimo recompute hace {recompute_lag} dias"
        recommended = "Ejecutar recompute de derivados"
    else:
        status = "ok"
        message = "Derivados al dia"
        recommended = None

    return {
        "status": status,
        "last_recomputed_at": last_recompute,
        "recompute_lag_days": recompute_lag,
        "stale_dependencies": stale_deps,
        "message": message,
        "recommended_action": recommended,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. MATCHING / ASIGNACIONES
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_matching(db: Session, today: date) -> Dict[str, Any]:
    db.execute(text("SET LOCAL statement_timeout = '30000ms'"))

    total = db.execute(text(
        f"SELECT COUNT(*) FROM {SOURCE_TABLE} WHERE hire_date IS NOT NULL AND hire_date::text != ''"
    )).scalar() or 0

    assigned = db.execute(text(f"""
        SELECT COUNT(DISTINCT s.driver_id)
        FROM {SOURCE_TABLE} s
        INNER JOIN scout_liq_driver_assignments a
            ON s.driver_id = a.driver_id AND a.status = 'active'
        WHERE s.hire_date IS NOT NULL AND s.hire_date::text != ''
    """)).scalar() or 0

    unassigned = total - assigned
    coverage = round((assigned / total * 100), 1) if total > 0 else 0

    # Sample unassigned drivers
    sample = []
    if unassigned > 0:
        sample_rows = db.execute(text(f"""
            SELECT s.driver_id, s.hire_date::text, s.origen,
                   s.lead_created_at_cabinet, s.lead_created_at_fleet
            FROM {SOURCE_TABLE} s
            WHERE s.hire_date IS NOT NULL AND s.hire_date::text != ''
              AND s.driver_id NOT IN (
                  SELECT a.driver_id FROM scout_liq_driver_assignments a WHERE a.status = 'active'
              )
            ORDER BY s.hire_date::date DESC
            LIMIT 20
        """)).fetchall()
        sample = [
            {
                "driver_id": r[0],
                "hire_date": r[1],
                "origen": r[2],
                "lead_created_at_cabinet": str(r[3]) if r[3] else None,
                "lead_created_at_fleet": str(r[4]) if r[4] else None,
                "reason": "Sin scout asignado en scout_liq_driver_assignments",
            }
            for r in sample_rows
        ]

    if coverage < 20:
        status = "blocked"
    elif coverage < 80:
        status = "warning"
    else:
        status = "ok"

    parts = []
    if unassigned > 0:
        parts.append(f"{unassigned} drivers sin scout ({coverage}% cobertura)")
    if status == "ok":
        message = "Asignaciones al dia"
        recommended = None
    else:
        message = "; ".join(parts)
        recommended = "Cargar scouts faltantes via carga masiva o manual"

    return {
        "status": status,
        "unmatched_count": unassigned,
        "total_source_drivers": total,
        "assigned_count": assigned,
        "assignment_coverage_pct": coverage,
        "unassigned_sample": sample,
        "message": message,
        "recommended_action": recommended,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. COHORTES (version pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_cohorts_pipeline(
    db: Session, today: date, weeks_limit: int = 8,
) -> Dict[str, Any]:
    db.execute(text("SET LOCAL statement_timeout = '60000ms'"))

    iy_expr = "EXTRACT(ISOYEAR FROM s.hire_date::date)::int"
    iw_expr = "EXTRACT(WEEK FROM s.hire_date::date)::int"

    raw = db.execute(text(f"""
        WITH cohort_base AS (
            SELECT {iy_expr} AS iso_year, {iw_expr} AS iso_week,
                   COUNT(*) AS total_drivers,
                   COUNT(DISTINCT s.driver_id) FILTER (
                       WHERE s.driver_id IN (
                           SELECT a.driver_id FROM scout_liq_driver_assignments a
                           WHERE a.status = 'active'
                       )
                   ) AS drivers_with_scout
            FROM {SOURCE_TABLE} s
            WHERE s.hire_date IS NOT NULL AND s.hire_date::text != ''
            GROUP BY {iy_expr}, {iw_expr}
            ORDER BY {iy_expr} DESC, {iw_expr} DESC
            LIMIT :weeks_limit
        )
        SELECT * FROM cohort_base ORDER BY iso_year ASC, iso_week ASC
    """), {"weeks_limit": weeks_limit}).fetchall()

    if not raw:
        return {"cohorts": [], "total_cohorts_visible": 0,
                "global_status": "ok", "warning_count": 0, "blocked_count": 0}

    # Build cutoff lookup
    cutoff_rows = db.execute(text(
        "SELECT cohort_iso_week, status FROM scout_liq_cutoff_runs "
        "WHERE cohort_iso_week IS NOT NULL ORDER BY created_at DESC"
    )).fetchall()
    cutoff_by_cohort: Dict[str, dict] = {}
    for cr in cutoff_rows:
        cw = cr[0]
        if cw and cw not in cutoff_by_cohort:
            cutoff_by_cohort[cw] = {"exists": True, "status": cr[1]}

    # Batch trip counts
    all_dids = set()
    cohort_dids: Dict[str, list] = {}
    for row in raw:
        yr, wk = int(row[0]), int(row[1])
        key = f"{yr}-W{wk:02d}"
        dr = db.execute(text(f"""
            SELECT driver_id FROM {SOURCE_TABLE}
            WHERE hire_date IS NOT NULL AND hire_date::text != ''
              AND EXTRACT(ISOYEAR FROM hire_date::date)::int = :yr
              AND EXTRACT(WEEK FROM hire_date::date)::int = :wk
        """), {"yr": yr, "wk": wk}).fetchall()
        dids = [r[0] for r in dr if r[0]]
        cohort_dids[key] = dids
        all_dids.update(dids)

    trip_map = _batch_trip_counts(db, list(all_dids))
    paid_map = _batch_paid_status(db, list(all_dids))

    cohorts = []
    for row in raw:
        yr = int(row[0])
        wk = int(row[1])
        key = f"{yr}-W{wk:02d}"
        monday, sunday = _iso_week_dates(yr, wk)
        maturity_7d = sunday + timedelta(days=7)
        maturity_14d = sunday + timedelta(days=14)
        is_7d_mature = maturity_7d <= today
        is_14d_mature = maturity_14d <= today

        total = row[2] or 0
        assigned_count = row[3] or 0
        unassigned = max(0, total - assigned_count)

        dids = cohort_dids.get(key, [])
        activated_1_trip = 0
        converted_5v7d = 0
        converted_5v14d = 0
        paid_count = 0

        for did in dids:
            trips = trip_map.get(did, {})
            t7 = trips.get("trips_0_7", 0) or 0
            t8_14 = trips.get("trips_8_14", 0) or 0
            t14_total = t7 + t8_14
            if t7 >= 1:
                activated_1_trip += 1
            if t7 >= 5:
                converted_5v7d += 1
            if t14_total >= 5:
                converted_5v14d += 1
            if paid_map.get(did):
                paid_count += 1

        cutoff = cutoff_by_cohort.get(key)
        cutoff_exists = cutoff is not None
        cutoff_status = cutoff["status"] if cutoff else None

        # Determine status and reasons
        reasons = []
        status = "ok"

        if unassigned > 0:
            reasons.append(f"existen drivers sin scout ({unassigned})")
        if is_7d_mature and activated_1_trip == 0:
            reasons.append("cohorte madura sin activaciones")
        if is_7d_mature and converted_5v7d == 0 and activated_1_trip > 0:
            reasons.append("sin conversion 5V7D a pesar de tener activaciones")
        if is_7d_mature and not cutoff_exists:
            reasons.append("cohorte madura sin cutoff creado")
        if total == 0:
            reasons.append("cohorte vacia")

        if reasons:
            if "cohorte madura sin cutoff creado" in reasons or "cohorte madura sin activaciones" in reasons:
                status = "blocked"
            else:
                status = "warning"

        label = f"S{wk:02d}-{yr}"
        active_count = activated_1_trip - converted_5v7d

        cohorts.append({
            "cohort": label,
            "cohort_key": key,
            "range": f"{monday.isoformat()} → {sunday.isoformat()}",
            "total": total,
            "assigned": assigned_count,
            "unassigned": unassigned,
            "active": active_count,
            "converted_5v_7d": converted_5v7d,
            "converted_5v_14d": converted_5v14d,
            "paid": paid_count,
            "is_7d_mature": is_7d_mature,
            "is_14d_mature": is_14d_mature,
            "cutoff_exists": cutoff_exists,
            "cutoff_status": cutoff_status,
            "status": status,
            "reasons": reasons,
        })

    warning_count = sum(1 for c in cohorts if c["status"] == "warning")
    blocked_count = sum(1 for c in cohorts if c["status"] == "blocked")

    if blocked_count > 0:
        global_status = "blocked"
    elif warning_count > 0:
        global_status = "warning"
    else:
        global_status = "ok"

    return {
        "cohorts": cohorts,
        "total_cohorts_visible": len(cohorts),
        "global_status": global_status,
        "warning_count": warning_count,
        "blocked_count": blocked_count,
    }


def _iso_week_dates(iso_year: int, iso_week: int) -> tuple:
    jan4 = date(iso_year, 1, 4)
    monday = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _batch_trip_counts(db: Session, driver_ids: list) -> Dict[str, Dict[str, int]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text("SET LOCAL statement_timeout = '60000ms'"))
    sql = f"""
        WITH driver_windows AS (
            SELECT driver_id, hire_date::date AS hire_date,
                   hire_date::date + INTERVAL '7 days' AS d7,
                   hire_date::date + INTERVAL '14 days' AS d14
            FROM {SOURCE_TABLE}
            WHERE driver_id IN ({placeholders})
              AND hire_date IS NOT NULL AND hire_date::text != ''
        ),
        trips_all AS (
            SELECT conductor_id AS driver_id, fecha_inicio_viaje::date AS trip_date
            FROM trips_2026
            WHERE conductor_id IN ({placeholders}) AND condicion = 'Completado'
            UNION ALL
            SELECT t2025.conductor_id, t2025.fecha_inicio_viaje::date
            FROM trips_2025 t2025
            JOIN driver_windows dw ON t2025.conductor_id = dw.driver_id AND dw.d14 < '2026-01-01'::date
            WHERE t2025.conductor_id IN ({placeholders}) AND t2025.condicion = 'Completado'
        )
        SELECT dw.driver_id,
               COUNT(t.trip_date) FILTER (WHERE t.trip_date >= dw.hire_date AND t.trip_date < dw.d7)::int AS trips_0_7,
               COUNT(t.trip_date) FILTER (WHERE t.trip_date >= dw.d7 AND t.trip_date < dw.d14)::int AS trips_8_14
        FROM driver_windows dw
        LEFT JOIN trips_all t ON t.driver_id = dw.driver_id
            AND t.trip_date >= dw.hire_date AND t.trip_date < dw.d14
        GROUP BY dw.driver_id
    """
    rows = db.execute(text(sql), params).fetchall()
    return {r[0]: {"trips_0_7": r[1] or 0, "trips_8_14": r[2] or 0} for r in rows}


def _batch_paid_status(db: Session, driver_ids: list) -> Dict[str, bool]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text("SET LOCAL statement_timeout = '30000ms'"))
    rows = db.execute(text(f"""
        SELECT DISTINCT driver_id FROM scout_liq_paid_history
        WHERE driver_id IN ({placeholders}) AND blocks_future_payment = true
    """), params).fetchall()
    return {r[0]: True for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
# 5. JOBS / PROCESOS
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_jobs_pipeline(db: Session, today: date) -> Dict[str, Any]:
    db.execute(text(STATEMENT_TIMEOUT))

    last_successful = []
    failed_runs = []
    missing_jobs = []

    # Check if job_runs table exists
    if _table_exists(db, JOB_RUNS_TABLE):
        success_rows = db.execute(text(
            "SELECT DISTINCT ON (job_name) job_name, status, started_at, finished_at, duration_ms "
            "FROM scout_liq_job_runs WHERE status = 'success' ORDER BY job_name, started_at DESC"
        )).fetchall()
        for r in success_rows:
            last_successful.append({
                "job_name": r[0],
                "status": r[1],
                "finished_at": str(r[3]) if r[3] else str(r[2]),
                "duration_ms": r[4],
            })

        failed_rows = db.execute(text(
            "SELECT job_name, error_message, started_at "
            "FROM scout_liq_job_runs WHERE status = 'failed' "
            "AND started_at >= :since ORDER BY started_at DESC LIMIT 10"
        ), {"since": (today - timedelta(days=7)).isoformat()}).fetchall()
        for r in failed_rows:
            failed_runs.append({
                "job_name": r[0],
                "error_message": r[1],
                "started_at": str(r[2]),
            })

    # Infer from table timestamps (fallback)
    cutoff_last = None
    try:
        cutoff_last = db.execute(text(
            "SELECT MAX(created_at) FROM scout_liq_cutoff_runs"
        )).scalar()
    except Exception:
        pass

    has_recompute = any(
        "health_recompute" in (s.get("job_name", "") or "")
        for s in last_successful
    )

    if not has_recompute:
        missing_jobs.append({
            "job_name": "health_recompute",
            "description": "Nunca se ha ejecutado recompute de derivados de salud",
            "recommended_action": "Ejecutar POST /scout-liq/health/recompute-derived",
        })

    if cutoff_last is None:
        missing_jobs.append({
            "job_name": "cutoff_engine",
            "description": "Sin registros de ejecucion de cutoff",
            "recommended_action": "Crear cutoff para cohortes maduras",
        })

    is_ok = len(failed_runs) == 0 and len(missing_jobs) == 0

    return {
        "status": "ok" if is_ok else "warning",
        "last_successful_runs": last_successful,
        "failed_runs": failed_runs,
        "missing_jobs": missing_jobs,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. ALERTAS
# ═══════════════════════════════════════════════════════════════════════════

def _build_pipeline_alerts(
    source: Dict, derived: Dict, matching: Dict,
    cohorts_info: Dict, jobs: Dict,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    alerts = []
    ref = today or date.today()
    yesterday = (ref - timedelta(days=1)).isoformat()

    # Source alerts
    if source.get("status") != "ok":
        lag_days = source.get("lag_days")
        alerts.append({
            "code": "source_health",
            "severity": source.get("status", "blocked"),
            "category": "source_stale",
            "message": source.get("message", ""),
            "root_cause_candidate": _root_cause_source(source),
            "impact": (
                "Cohortes, conversiones y cortes usaran fechas desactualizadas. "
                "No se pueden liquidar cohortes nuevas hasta que la fuente este al dia."
            ),
            "recommended_action": source.get("recommended_action", ""),
            "is_blocking": True,
            "owner": "TI / ETL externo",
            "evidence": {
                "expected_closed_day": yesterday,
                "max_detected_hire_date": source.get("max_hire_date"),
                "max_anchor_date": source.get("max_anchor_date"),
                "lag_days": lag_days,
                "rows_last_1d": source.get("rows_last_1d", 0),
                "rows_last_3d": source.get("rows_last_3d", 0),
                "rows_last_7d": source.get("rows_last_7d", 0),
                "total_rows": source.get("total_rows", 0),
            },
        })

    # Derived alerts
    if derived.get("status") != "ok":
        alerts.append({
            "code": "derived_stale",
            "severity": derived.get("status", "warning"),
            "category": "derived_stale",
            "message": derived.get("message", ""),
            "root_cause_candidate": "Derivados no recalculados despues de actualizacion de fuente",
            "impact": "El health dashboard puede mostrar datos viejos que no reflejan el estado real.",
            "recommended_action": derived.get("recommended_action", "Ejecutar recompute de derivados"),
            "is_blocking": source.get("status") == "ok",
            "owner": "TI / Automatizar cron",
            "evidence": {
                "last_recomputed_at": derived.get("last_recomputed_at"),
                "recompute_lag_days": derived.get("recompute_lag_days"),
                "stale_dependencies": derived.get("stale_dependencies", []),
            },
        })

    # Matching alerts
    if matching.get("status") != "ok":
        coverage = matching.get("assignment_coverage_pct", 0)
        unassigned = matching.get("unmatched_count", 0)
        alerts.append({
            "code": "scout_assignment",
            "severity": matching.get("status", "warning"),
            "category": "matching_gap",
            "message": matching.get("message", ""),
            "root_cause_candidate": "Drivers en fuente sin scout asignado en el sistema",
            "impact": (
                f"{unassigned} drivers no seran liquidados en ningun cutoff hasta que tengan scout. "
                f"Esto reduce el alcance de liquidacion al {coverage}% de la base."
            ),
            "recommended_action": matching.get("recommended_action", "Cargar scouts faltantes"),
            "is_blocking": coverage < 20,
            "owner": "Operaciones",
            "evidence": {
                "total_source_drivers": matching.get("total_source_drivers", 0),
                "assigned_count": matching.get("assigned_count", 0),
                "unassigned_count": unassigned,
                "coverage_pct": coverage,
                "sample_available": len(matching.get("unassigned_sample", [])) > 0,
            },
        })

    # Cohort alerts
    for c in cohorts_info.get("cohorts", []):
        if c.get("status") != "ok":
            cohort = c.get("cohort", "")
            reasons = c.get("reasons", [])
            has_workflow_gap = any("sin cutoff creado" in r for r in reasons)
            has_matching_gap = any("sin scout" in r for r in reasons)
            has_no_activity = any("sin activaciones" in r for r in reasons)

            # Clasificar categoria
            if has_workflow_gap:
                category = "workflow_gap"
            elif has_no_activity:
                category = "cutoff_gap"
            elif has_matching_gap:
                category = "matching_gap"
            else:
                category = "unknown"

            # Determinar severidad y bloqueo
            is_blocking = c.get("status") == "blocked"

            if has_workflow_gap:
                root_cause = (
                    f"La cohorte {cohort} alcanzo madurez 7D pero no se ha creado un cutoff para liquidarla."
                )
                action = f"Crear cutoff para cohorte {cohort} desde la UI de Liquidaciones (Centro Operativo > Liquidaciones)."
            elif has_matching_gap:
                root_cause = f"Drivers en la cohorte {cohort} sin scout asignado."
                action = f"Asignar scouts a los {c.get('unassigned', 0)} drivers sin scout en esta cohorte."
            elif has_no_activity:
                root_cause = f"Cohorte {cohort} madura pero sin viajes registrados en ventana."
                action = "Verificar si los drivers de esta cohorte tienen viajes en el sistema."
            else:
                root_cause = "Problema no especifico detectado en la cohorte."
                action = "Revisar detalle de la cohorte en el dashboard."

            alerts.append({
                "code": f"cohort/{cohort}",
                "severity": c.get("status", "warning"),
                "category": category,
                "message": f"Cohorte {cohort}: {'; '.join(reasons)}",
                "root_cause_candidate": root_cause,
                "impact": (
                    f"{c.get('total', 0)} drivers en esta cohorte, "
                    f"{c.get('converted_5v_7d', 0)} califican para pago 5V7D. "
                    f"{'No se puede liquidar hasta crear cutoff.' if is_blocking else 'Requiere atencion operativa.'}"
                ),
                "recommended_action": action,
                "is_blocking": is_blocking,
                "owner": "Operaciones" if has_workflow_gap else "Operaciones",
                "evidence": {
                    "cohort": cohort,
                    "range": c.get("range", ""),
                    "total_drivers": c.get("total", 0),
                    "assigned": c.get("assigned", 0),
                    "unassigned": c.get("unassigned", 0),
                    "converted_5v_7d": c.get("converted_5v_7d", 0),
                    "converted_5v_14d": c.get("converted_5v_14d", 0),
                    "is_7d_mature": c.get("is_7d_mature", False),
                    "is_14d_mature": c.get("is_14d_mature", False),
                    "cutoff_exists": c.get("cutoff_exists", False),
                    "cutoff_status": c.get("cutoff_status"),
                },
            })

    # Job alerts
    for fj in jobs.get("missing_jobs", []):
        alerts.append({
            "code": "missing_job",
            "severity": "warning",
            "category": "missing_job",
            "message": f"Job no ejecutado: {fj.get('job_name', '')}",
            "root_cause_candidate": fj.get("description", ""),
            "impact": "Sin ejecucion automatica, los derivados de salud se desactualizan y las alertas no se regeneran.",
            "recommended_action": fj.get("recommended_action", ""),
            "is_blocking": False,
            "owner": "TI / Deploy",
            "evidence": {"job_name": fj.get("job_name"), "description": fj.get("description")},
        })
    for fj in jobs.get("failed_runs", []):
        alerts.append({
            "code": "failed_job",
            "severity": "blocked",
            "category": "missing_job",
            "message": f"Job fallido: {fj.get('job_name', '')} — {fj.get('error_message', '')}",
            "root_cause_candidate": "Error en ejecucion de job",
            "impact": "Los derivados de salud no se estan actualizando. Alertas pueden ser stale.",
            "recommended_action": "Revisar logs y corregir causa del error",
            "is_blocking": True,
            "owner": "TI",
            "evidence": {
                "job_name": fj.get("job_name"),
                "error_message": fj.get("error_message"),
                "started_at": fj.get("started_at"),
            },
        })

    return alerts


def _root_cause_source(source: Dict) -> str:
    lag = source.get("lag_days")
    if lag is not None and lag > 1:
        return "Fuente operativa module_ct_cabinet_drivers sin datos al dia. Revisar cronjob/ETL de carga."
    if source.get("total_rows", 0) == 0:
        return "Tabla fuente vacia. ETL no esta cargando datos."
    return "Posible gap en pipeline ETL de carga de fuente operativa."


# ═══════════════════════════════════════════════════════════════════════════
# RECOMPUTE DERIVED (endpoint POST)
# ═══════════════════════════════════════════════════════════════════════════

def recompute_derived(db: Session, triggered_by: str = "manual") -> Dict[str, Any]:
    """Recalcula todos los derivados del pipeline de salud.
    Registra ejecucion en job_runs si la tabla existe."""
    started_at = datetime.utcnow()
    steps: List[Dict[str, Any]] = []
    job_id = None

    try:
        # ── Registrar inicio del job ──
        if _table_exists(db, JOB_RUNS_TABLE):
            result = db.execute(text(f"""
                INSERT INTO scout_liq_job_runs
                    (job_name, job_type, status, started_at, triggered_by)
                VALUES ('health_recompute', 'health_recompute', 'running', :now, :by)
                RETURNING id
            """), {"now": started_at, "by": triggered_by})
            job_id = result.scalar()
            db.commit()

        all_ok = True
        final_status = "success"

        # ── Step 1: Source freshness ──
        try:
            src = _evaluate_source(db, date.today())
            steps.append({
                "name": "source_freshness",
                "status": "ok",
                "rows_checked": src.get("total_rows", 0),
                "lag_days": src.get("lag_days"),
                "message": src.get("message", ""),
            })
        except Exception as e:
            steps.append({"name": "source_freshness", "status": "failed", "message": str(e)})
            all_ok = False

        # ── Step 2: Scout assignment coverage ──
        try:
            matching = _evaluate_matching(db, date.today())
            steps.append({
                "name": "scout_assignment_coverage",
                "status": "ok",
                "total": matching.get("total_source_drivers", 0),
                "assigned": matching.get("assigned_count", 0),
                "coverage_pct": matching.get("assignment_coverage_pct", 0),
                "message": matching.get("message", ""),
            })
        except Exception as e:
            steps.append({"name": "scout_assignment_coverage", "status": "failed", "message": str(e)})
            all_ok = False

        # ── Step 3: Cohort readiness ──
        try:
            cohorts = _evaluate_cohorts_pipeline(db, date.today(), weeks_limit=8)
            steps.append({
                "name": "cohort_readiness",
                "status": "ok",
                "cohorts_evaluated": cohorts.get("total_cohorts_visible", 0),
                "warning_count": cohorts.get("warning_count", 0),
                "blocked_count": cohorts.get("blocked_count", 0),
                "message": f"{cohorts.get('blocked_count', 0)} bloqueadas, {cohorts.get('warning_count', 0)} con warning",
            })
        except Exception as e:
            steps.append({"name": "cohort_readiness", "status": "failed", "message": str(e)})
            all_ok = False

        # ── Step 4: Health events refresh ──
        try:
            from app.services.scout_liq_health_registry_service import (
                refresh_registry_snapshot,
                detect_health_events,
                resolve_recovered_events,
            )
            registry = refresh_registry_snapshot(db)
            events_detected = detect_health_events(db)
            events_resolved = resolve_recovered_events(db)
            steps.append({
                "name": "health_events_refresh",
                "status": "ok",
                "registry_entries": registry.get("total", 0),
                "new_events": events_detected.get("new_events", 0),
                "resolved_events": events_resolved.get("resolved_count", 0),
            })
        except Exception as e:
            steps.append({"name": "health_events_refresh", "status": "failed", "message": str(e)})
            all_ok = False

        # ── Step 5: Unmatched drivers detail ──
        try:
            unmatched_detail = _evaluate_matching(db, date.today())
            steps.append({
                "name": "unmatched_detail",
                "status": "ok",
                "unmatched_count": unmatched_detail.get("unmatched_count", 0),
                "sample_size": len(unmatched_detail.get("unassigned_sample", [])),
            })
        except Exception as e:
            steps.append({"name": "unmatched_detail", "status": "failed", "message": str(e)})
            all_ok = False

        if all_ok:
            final_status = "success"
        else:
            final_status = "partial_failure"

    except Exception as e:
        final_status = "failed"
        _logger.error(f"[recompute_derived] Fatal error: {e}\n{_traceback.format_exc()}")
        steps.append({"name": "recompute_derived", "status": "failed", "message": str(e)})
        all_ok = False

    finished_at = datetime.utcnow()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # ── Registrar fin del job ──
    if job_id and _table_exists(db, JOB_RUNS_TABLE):
        try:
            db.execute(text(f"""
                UPDATE scout_liq_job_runs SET
                    status = :st, finished_at = :fin, duration_ms = :dur,
                    steps_executed = :se, steps_succeeded = :ss,
                    steps_failed = :sf,
                    details_json = :dj,
                    error_message = :err
                WHERE id = :jid
            """), {
                "st": final_status,
                "fin": finished_at,
                "dur": duration_ms,
                "se": len(steps),
                "ss": sum(1 for s in steps if s.get("status") == "ok"),
                "sf": sum(1 for s in steps if s.get("status") == "failed"),
                "dj": _json.dumps(steps, default=str),
                "err": None if all_ok else "; ".join(
                    s.get("message", "") for s in steps if s.get("status") == "failed"
                ),
                "jid": job_id,
            })
            db.commit()
        except Exception as e:
            _logger.error(f"[recompute_derived] Error updating job run: {e}")

    # ── Obtener pipeline summary fresco ──
    fresh_summary = get_pipeline_summary(db)

    return {
        "status": final_status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": duration_ms,
        "steps": steps,
        "alerts": fresh_summary.get("alerts", []),
        "health_summary": {
            "overall_status": fresh_summary.get("overall_status"),
            "source_status": fresh_summary.get("source_operational", {}).get("status"),
            "matching_status": fresh_summary.get("matching", {}).get("status"),
            "cohorts_status": fresh_summary.get("cohorts_summary", {}).get("global_status"),
        },
    }


def _pipeline_fallback(error: str) -> Dict[str, Any]:
    return {
        "evaluated_at": date.today().isoformat(),
        "overall_status": "unknown",
        "closed_day_expected": None,
        "source_operational": {"status": "unknown", "message": f"Error: {error}"},
        "derived_pipeline": {"status": "unknown"},
        "matching": {"status": "unknown"},
        "cohorts": [],
        "cohorts_summary": {"global_status": "unknown"},
        "jobs": {"status": "unknown"},
        "alerts": [],
        "error": str(error),
    }


# ═══════════════════════════════════════════════════════════════════════════
# OPERATIONAL READINESS
# ═══════════════════════════════════════════════════════════════════════════

def _compute_operational_readiness(
    source: Dict, matching: Dict, cohorts_info: Dict, jobs: Dict,
) -> Dict[str, Any]:
    source_ok = source.get("status") == "ok"
    matching_ok = matching.get("status") == "ok"
    has_unassigned = matching.get("unmatched_count", 0) > 0
    coverage = matching.get("assignment_coverage_pct", 0)

    blocking_domains = []
    next_actions = []

    if not source_ok:
        blocking_domains.append("source")
        next_actions.append({
            "owner": "TI / ETL externo",
            "action": "Actualizar fuente operativa module_ct_cabinet_drivers hasta dia cerrado anterior",
            "blocking": True,
            "detail": f"Fuente atrasada {source.get('lag_days', '?')} dias. Ultima fecha: {source.get('max_hire_date', '?')}",
        })

    if has_unassigned:
        pct_str = f"{coverage}%"
        if coverage < 80:
            blocking_domains.append("assignment")
        next_actions.append({
            "owner": "Operaciones",
            "action": f"Asignar scouts a {matching.get('unmatched_count', 0)} drivers pendientes",
            "blocking": coverage < 80,
            "detail": f"Cobertura actual: {pct_str}. Cargar via Centro Operativo > Asignar Scout o carga masiva.",
        })

    for c in cohorts_info.get("cohorts", []):
        if c.get("status") == "blocked":
            reasons = c.get("reasons", [])
            if any("sin cutoff" in r for r in reasons):
                if "cutoff_workflow" not in blocking_domains:
                    blocking_domains.append("cutoff_workflow")
                next_actions.append({
                    "owner": "Operaciones / Liquidacion",
                    "action": f"Crear cutoff para cohorte {c.get('cohort', '?')}",
                    "blocking": True,
                    "detail": f"{c.get('total', 0)} drivers, {c.get('converted_5v_7d', 0)} convertidos 5V7D. Ir a Liquidaciones > Crear corte.",
                })

    seen = set()
    unique_actions = []
    for na in next_actions:
        key = na["action"][:80]
        if key not in seen:
            seen.add(key)
            unique_actions.append(na)

    can_create_cutoff = "source" not in blocking_domains
    can_calculate_preview = True
    can_approve_payments = len(blocking_domains) == 0
    can_assign_scouts = True

    return {
        "can_create_cutoff": can_create_cutoff,
        "can_calculate_preview": can_calculate_preview,
        "can_approve_payments": can_approve_payments,
        "can_assign_scouts": can_assign_scouts,
        "blocking_domains": blocking_domains,
        "next_actions": unique_actions,
    }


def get_operational_readiness(db: Session) -> Dict[str, Any]:
    """Obtiene readiness operativo sin recalcular todo el pipeline.
    Solo evalua source + matching + cohorts minimo."""
    today = date.today()
    source_info = _evaluate_source(db, today)
    matching_info = _evaluate_matching(db, today)
    cohorts_info = _evaluate_cohorts_pipeline(db, today, weeks_limit=8)
    jobs_info = _evaluate_jobs_pipeline(db, today)
    return _compute_operational_readiness(source_info, matching_info, cohorts_info, jobs_info)


# ═══════════════════════════════════════════════════════════════════════════
# CSV EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

def export_unassigned_drivers_csv(db: Session) -> str:
    """Exporta CSV con BOM UTF-8 de drivers sin scout."""
    import csv, io
    output = io.StringIO()
    output.write('\ufeff')  # BOM
    writer = csv.writer(output)

    writer.writerow([
        "driver_id", "anchor_date", "anchor_date_source", "hire_date",
        "origin_tag", "trips_7d", "trips_14d", "reason", "suggested_action",
    ])

    detail = get_unassigned_drivers_detail(db, limit=5000, offset=0)
    for d in detail.get("items", []):
        writer.writerow([
            d.get("driver_id", ""),
            d.get("lead_created_at_cabinet") or d.get("lead_created_at_fleet") or d.get("hire_date", ""),
            "lead_created_at" if (d.get("lead_created_at_cabinet") or d.get("lead_created_at_fleet")) else "hire_date_fallback",
            d.get("hire_date", ""),
            d.get("origen", ""),
            "",  # trips_7d — not computed here (needs trips DB join)
            "",  # trips_14d
            "Sin scout asignado en scout_liq_driver_assignments",
            d.get("suggested_action", "Asignar scout via carga masiva o UI"),
        ])

    return output.getvalue()


def export_blocked_cohorts_csv(db: Session) -> str:
    """Exporta CSV con BOM UTF-8 de cohortes bloqueadas."""
    import csv, io
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow([
        "cohort", "date_from", "date_to", "mature_7d", "mature_14d",
        "cutoff_exists", "total_drivers", "assigned", "unassigned",
        "blocking_reason", "suggested_action",
    ])

    detail = get_blocked_cohorts_detail(db)
    for c in detail.get("cohorts", []):
        blocking = "; ".join(c.get("reasons", []))
        writer.writerow([
            c.get("cohort", ""),
            c.get("range", "").split(" → ")[0] if " → " in c.get("range", "") else c.get("range", ""),
            c.get("range", "").split(" → ")[1] if " → " in c.get("range", "") else "",
            "SI" if c.get("is_7d_mature") else "NO",
            "SI" if c.get("is_14d_mature") else "NO",
            "SI" if c.get("cutoff_exists") else "NO",
            c.get("total_drivers", 0),
            c.get("assigned", 0),
            c.get("unassigned", 0),
            blocking,
            c.get("suggested_action", ""),
        ])

    return output.getvalue()


def export_alerts_csv(db: Session) -> str:
    """Exporta CSV con BOM UTF-8 de alertas activas."""
    import csv, io
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow([
        "code", "severity", "category", "owner", "message",
        "impact", "recommended_action", "is_blocking",
    ])

    detail = get_alerts_detail(db)
    for a in detail.get("alerts", []):
        writer.writerow([
            a.get("code", ""),
            a.get("severity", ""),
            a.get("category", ""),
            a.get("owner", ""),
            a.get("message", ""),
            a.get("impact", ""),
            a.get("recommended_action", ""),
            "SI" if a.get("is_blocking") else "NO",
        ])

    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# DETAILED ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

def get_alerts_detail(db: Session) -> Dict[str, Any]:
    """Retorna todas las alertas con evidencia, clasificacion y accion detallada."""
    summary = get_pipeline_summary(db)
    alerts = summary.get("alerts", [])

    # Enriquecer cada alerta con SQL-evidence si aplica
    for a in alerts:
        code = a.get("code", "")
        if code == "source_health":
            # Ya tiene evidence del pipeline
            pass
        elif code.startswith("cohort/"):
            cohort_name = code.replace("cohort/", "")
            # Buscar cohort en los datos del pipeline
            for c in summary.get("cohorts", []):
                if c.get("cohort") == cohort_name:
                    a["evidence"] = a.get("evidence", {})
                    break

    return {
        "evaluated_at": summary.get("evaluated_at"),
        "overall_status": summary.get("overall_status"),
        "total_alerts": len(alerts),
        "blocking_count": sum(1 for a in alerts if a.get("is_blocking")),
        "alerts": alerts,
        "summary_by_category": _summarize_by_category(alerts),
        "summary_by_owner": _summarize_by_owner(alerts),
    }


def _summarize_by_category(alerts: List[Dict]) -> Dict[str, Any]:
    cats: Dict[str, Dict] = {}
    for a in alerts:
        cat = a.get("category", "unknown")
        if cat not in cats:
            cats[cat] = {"count": 0, "blocking": 0, "sample_codes": []}
        cats[cat]["count"] += 1
        if a.get("is_blocking"):
            cats[cat]["blocking"] += 1
        if len(cats[cat]["sample_codes"]) < 3:
            cats[cat]["sample_codes"].append(a.get("code", ""))
    return cats


def _summarize_by_owner(alerts: List[Dict]) -> Dict[str, Any]:
    owners: Dict[str, Dict] = {}
    for a in alerts:
        owner = a.get("owner", "Desconocido")
        if owner not in owners:
            owners[owner] = {"count": 0, "blocking": 0}
        owners[owner]["count"] += 1
        if a.get("is_blocking"):
            owners[owner]["blocking"] += 1
    return owners


def get_unassigned_drivers_detail(
    db: Session, limit: int = 50, offset: int = 0,
) -> Dict[str, Any]:
    """Retorna detalle de drivers sin scout en fuente operativa."""
    db.execute(text("SET LOCAL statement_timeout = '30000ms'"))

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM {SOURCE_TABLE} s
        WHERE s.hire_date IS NOT NULL AND s.hire_date::text != ''
          AND s.driver_id NOT IN (
              SELECT a.driver_id FROM scout_liq_driver_assignments a WHERE a.status = 'active'
          )
    """)).scalar() or 0

    rows = db.execute(text(f"""
        SELECT s.driver_id,
               s.hire_date::text,
               s.lead_created_at_cabinet,
               s.lead_created_at_fleet,
               s.origen,
               s.license,
               s.status,
               s.created_at::text,
               s.updated_at::text
        FROM {SOURCE_TABLE} s
        WHERE s.hire_date IS NOT NULL AND s.hire_date::text != ''
          AND s.driver_id NOT IN (
              SELECT a.driver_id FROM scout_liq_driver_assignments a WHERE a.status = 'active'
          )
        ORDER BY s.hire_date::date DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).fetchall()

    items = []
    for r in rows:
        items.append({
            "driver_id": r[0],
            "hire_date": r[1],
            "lead_created_at_cabinet": str(r[2]) if r[2] else None,
            "lead_created_at_fleet": str(r[3]) if r[3] else None,
            "origen": r[4],
            "license": r[5],
            "source_status": r[6],
            "created_at": str(r[7]) if r[7] else None,
            "updated_at": str(r[8]) if r[8] else None,
            "suggested_action": (
                "Asignar scout via carga masiva o UI de Centro Operativo > Asignar Scout"
            ),
        })

    return {
        "total_unassigned": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "items": items,
    }


def get_blocked_cohorts_detail(db: Session) -> Dict[str, Any]:
    """Retorna detalle de cohortes bloqueadas (maduras sin cutoff)."""
    summary = get_pipeline_summary(db)

    blocked_cohorts = []
    for c in summary.get("cohorts", []):
        reasons = c.get("reasons", [])
        has_cutoff_gap = any("sin cutoff creado" in r for r in reasons)
        has_matching_gap = any("sin scout" in r for r in reasons)

        # Incluir todas las que no estan OK, pero clasificar problema
        if c.get("status") in ("blocked", "warning"):
            blocked_cohorts.append({
                "cohort": c.get("cohort"),
                "cohort_key": c.get("cohort_key"),
                "range": c.get("range"),
                "is_7d_mature": c.get("is_7d_mature", False),
                "is_14d_mature": c.get("is_14d_mature", False),
                "cutoff_exists": c.get("cutoff_exists", False),
                "cutoff_status": c.get("cutoff_status"),
                "total_drivers": c.get("total", 0),
                "assigned": c.get("assigned", 0),
                "unassigned": c.get("unassigned", 0),
                "active": c.get("active", 0),
                "converted_5v_7d": c.get("converted_5v_7d", 0),
                "converted_5v_14d": c.get("converted_5v_14d", 0),
                "paid": c.get("paid", 0),
                "status": c.get("status"),
                "reasons": reasons,
                "main_problem": (
                    "workflow_gap_sin_cutoff" if has_cutoff_gap else
                    "matching_gap_sin_scout" if has_matching_gap else
                    "unknown"
                ),
                "suggested_action": (
                    f"Crear cutoff para cohorte {c.get('cohort')} desde Liquidaciones"
                    if has_cutoff_gap else
                    f"Asignar scouts a los {c.get('unassigned', 0)} drivers sin scout"
                    if has_matching_gap else
                    "Revisar detalle de cohorte"
                ),
                "owner": "Operaciones",
                "is_blocking": c.get("status") == "blocked",
            })

    return {
        "total_blocked_or_warning": len(blocked_cohorts),
        "blocking_count": sum(1 for c in blocked_cohorts if c.get("is_blocking")),
        "warning_count": sum(1 for c in blocked_cohorts if not c.get("is_blocking")),
        "cohorts": blocked_cohorts,
    }
