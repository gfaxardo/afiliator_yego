"""
Health & Freshness Service para Liquidador de Calidad Scouts Yego.

Diagnostica:
- atraso de data
- estado de fuentes
- carga de scouts
- salud por cohorte
- cohortes incompletas
- cohortes maduras sin actividad
- problemas de cron/procesos
- gaps operativos

Solo SELECT. No modifica tablas fuente.
Todas las consultas son live, sin persistencia.
"""

import time as _time
import logging
import traceback
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError

from app.config import settings

_logger = logging.getLogger("scout_liq_health")

_HEALTH_FALLBACK_SOURCE = {
    "status": "UNKNOWN",
    "reason_text": "No se pudo evaluar la fuente operativa",
    "last_data_date": None,
    "data_lag_days": None,
    "data_lag_minutes": None,
    "data_lag_hours": None,
    "evaluated_at": None,
    "metrics": {},
}

_HEALTH_FALLBACK_SCOUTS = {
    "status": "UNKNOWN",
    "reason_text": "No se pudo evaluar la carga de scouts",
    "evaluated_at": None,
    "metrics": {
        "total_source_drivers": 0,
        "drivers_with_scout": 0,
        "drivers_without_scout": 0,
        "scout_coverage_pct": 0,
        "last_assignment_created_at": None,
        "assignment_lag_days": None,
        "assignment_lag_minutes": None,
        "assignment_lag_hours": None,
        "assignments_last_1d": 0,
        "assignments_last_3d": 0,
        "assignments_last_7d": 0,
    },
}

_HEALTH_FALLBACK_COHORTS = {
    "cohorts": [],
    "total_cohorts_visible": 0,
    "global_status": "UNKNOWN",
    "global_reason": "No se pudo evaluar la salud de cohortes",
    "warning_count": 0,
    "blocked_count": 0,
}

_HEALTH_FALLBACK_JOBS = {
    "jobs": [],
    "global_status": "UNKNOWN",
    "global_reason": "No se pudo evaluar la salud de jobs/procesos",
    "inferred_only": True,
    "note": "Error al consultar la infraestructura de jobs",
}

_HEALTH_FALLBACK_SUMMARY = {
    "global_status": "UNKNOWN",
    "evaluated_at": None,
    "sections": {
        "source": {"status": "UNKNOWN", "reason_text": "No disponible", "data_lag_days": None, "last_data_date": None},
        "scouts": {"status": "UNKNOWN", "reason_text": "No disponible", "coverage_pct": None},
        "cohorts": {"status": "UNKNOWN", "reason_text": "No disponible", "warning_count": 0, "blocked_count": 0},
        "jobs": {"status": "UNKNOWN", "reason_text": "No disponible"},
    },
    "alerts": [],
}

SOURCE_TABLE = settings.SOURCE_TABLE
STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '30000ms'"


def _iso_year_expr(col: str) -> str:
    return f"EXTRACT(ISOYEAR FROM {col}::date)::int"


def _iso_week_expr(col: str) -> str:
    return f"EXTRACT(WEEK FROM {col}::date)::int"


def _iso_label(iy_expr: str, iw_expr: str) -> str:
    return f"'S' || LPAD({iw_expr}::text, 2, '0') || '-' || {iy_expr}::text"


def _iso_week_dates(iso_year: int, iso_week: int) -> tuple:
    """Return (monday, sunday) for an ISO week number."""
    jan4 = date(iso_year, 1, 4)
    monday = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _cohort_maturity(cohort_to: date, maturity_days: int = 7) -> date:
    return cohort_to + timedelta(days=maturity_days)


def _status_from_lag(lag: Optional[int]) -> str:
    if lag is None:
        return "UNKNOWN"
    if lag <= 1:
        return "OK"
    if lag <= 3:
        return "WARNING"
    return "BLOCKED"


def _status_from_gap(gap_hours: Optional[float]) -> str:
    if gap_hours is None:
        return "UNKNOWN"
    if gap_hours <= 24:
        return "OK"
    if gap_hours <= 72:
        return "WARNING"
    return "BLOCKED"


# ═══════════════════════════════════════════════════════════════════════════
# 1. HEALTH DE FUENTE OPERATIVA
# ═══════════════════════════════════════════════════════════════════════════

def _safe_source_health_impl(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    today = date.today()

    row = db.execute(text(f"""
        SELECT
            MAX(hire_date::date) AS max_hire_date,
            MIN(hire_date::date) AS min_hire_date,
            COUNT(*) AS total_drivers,
            COUNT(*) FILTER (
                WHERE hire_date::date >= :d1
            ) AS drivers_last_1d,
            COUNT(*) FILTER (
                WHERE hire_date::date >= :d3
            ) AS drivers_last_3d,
            COUNT(*) FILTER (
                WHERE hire_date::date >= :d7
            ) AS drivers_last_7d,
            MAX(updated_at::text) AS last_updated_at,
            MAX(created_at::text) AS last_created_at
        FROM {SOURCE_TABLE}
        WHERE hire_date IS NOT NULL AND hire_date != ''
    """), {
        "d1": (today - timedelta(days=1)).isoformat(),
        "d3": (today - timedelta(days=3)).isoformat(),
        "d7": (today - timedelta(days=7)).isoformat(),
    }).fetchone()

    if not row or not row[0]:
        return {
            "status": "BLOCKED",
            "reason_text": "No se detecto hire_date en la fuente. La tabla puede estar vacia.",
            "last_data_date": None,
            "evaluated_at": today.isoformat(),
            "metrics": {},
        }

    max_hd = row[0]
    lag_days = (today - max_hd).days if max_hd else None
    lag_minutes = lag_days * 1440 if lag_days is not None else None
    lag_hours = lag_days * 24 if lag_days is not None else None

    metrics = {
        "max_hire_date": str(max_hd) if max_hd else None,
        "min_hire_date": str(row[1]) if row[1] else None,
        "total_drivers": row[2] or 0,
        "drivers_last_1d": row[3] or 0,
        "drivers_last_3d": row[4] or 0,
        "drivers_last_7d": row[5] or 0,
        "last_updated_at": row[6],
        "last_created_at": row[7],
    }

    status = _status_from_lag(lag_days)

    reason_parts = []
    if lag_days is not None and lag_days > 1:
        reason_parts.append(f"Fuente atrasada {lag_days} dias")
    if metrics["drivers_last_1d"] == 0:
        reason_parts.append("Sin nuevos drivers en el ultimo dia")
    if metrics["drivers_last_7d"] == 0:
        reason_parts.append("Sin carga de drivers en la ultima semana")

    reason_text = "; ".join(reason_parts) if reason_parts else "Fuente operativa al dia"

    return {
        "status": status,
        "reason_text": reason_text,
        "last_data_date": str(max_hd),
        "data_lag_days": lag_days,
        "data_lag_minutes": lag_minutes,
        "data_lag_hours": lag_hours,
        "evaluated_at": today.isoformat(),
        "metrics": metrics,
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


def get_source_health(db: Session) -> Dict[str, Any]:
    try:
        return _safe_source_health_impl(db)
    except Exception as e:
        _logger.error(f"[get_source_health] {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_SOURCE)


# ═══════════════════════════════════════════════════════════════════════════
# 2. HEALTH DE SCOUTS / ASIGNACIONES
# ═══════════════════════════════════════════════════════════════════════════

def _safe_scout_assignment_health_impl(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    today = date.today()

    source_total = db.execute(text(
        f"SELECT COUNT(*) FROM {SOURCE_TABLE} WHERE hire_date IS NOT NULL AND hire_date != ''"
    )).scalar() or 0

    with_scout = db.execute(text(f"""
        SELECT COUNT(DISTINCT s.driver_id)
        FROM {SOURCE_TABLE} s
        INNER JOIN scout_liq_driver_assignments a
            ON s.driver_id = a.driver_id AND a.status = 'active'
        WHERE s.hire_date IS NOT NULL AND s.hire_date != ''
    """)).scalar() or 0

    without_scout = source_total - with_scout

    last_assignment = db.execute(text("""
        SELECT MAX(created_at) FROM scout_liq_driver_assignments
        WHERE status = 'active'
    """)).scalar()

    assignments_last_1d = db.execute(text(f"""
        SELECT COUNT(*) FROM scout_liq_driver_assignments
        WHERE status = 'active' AND created_at >= :d1
    """), {"d1": today - timedelta(days=1)}).scalar() or 0

    assignments_last_3d = db.execute(text(f"""
        SELECT COUNT(*) FROM scout_liq_driver_assignments
        WHERE status = 'active' AND created_at >= :d3
    """), {"d3": today - timedelta(days=3)}).scalar() or 0

    assignments_last_7d = db.execute(text(f"""
        SELECT COUNT(*) FROM scout_liq_driver_assignments
        WHERE status = 'active' AND created_at >= :d7
    """), {"d7": today - timedelta(days=7)}).scalar() or 0

    scout_coverage_pct = round((with_scout / source_total * 100), 1) if source_total > 0 else 0

    assignment_lag_days = None
    if last_assignment:
        if hasattr(last_assignment, 'date'):
            last_assignment_date = last_assignment.date()
        elif isinstance(last_assignment, date):
            last_assignment_date = last_assignment
        else:
            try:
                last_assignment_date = datetime.fromisoformat(str(last_assignment)).date()
            except (ValueError, TypeError):
                last_assignment_date = None
        if last_assignment_date:
            assignment_lag_days = (today - last_assignment_date).days

    issues = []
    if without_scout > 0:
        issues.append(f"{without_scout} drivers sin scout asignado")
    if scout_coverage_pct < 80:
        issues.append(f"Cobertura de scouts baja: {scout_coverage_pct}%")
    if assignments_last_7d == 0:
        issues.append("Sin asignaciones nuevas en la ultima semana")
    if assignment_lag_days is not None and assignment_lag_days > 7:
        issues.append(f"Ultima asignacion hace {assignment_lag_days} dias")

    if not issues:
        status = "OK"
        reason_text = "Scouts y asignaciones al dia"
    elif len(issues) <= 1:
        status = "WARNING"
        reason_text = issues[0]
    else:
        status = "BLOCKED"
        reason_text = "; ".join(issues)

    return {
        "status": status,
        "reason_text": reason_text,
        "evaluated_at": today.isoformat(),
        "metrics": {
            "total_source_drivers": source_total,
            "drivers_with_scout": with_scout,
            "drivers_without_scout": without_scout,
            "scout_coverage_pct": scout_coverage_pct,
            "last_assignment_created_at": str(last_assignment) if last_assignment else None,
            "assignment_lag_days": assignment_lag_days,
            "assignment_lag_minutes": assignment_lag_days * 1440 if assignment_lag_days is not None else None,
            "assignment_lag_hours": assignment_lag_days * 24 if assignment_lag_days is not None else None,
            "assignments_last_1d": assignments_last_1d,
            "assignments_last_3d": assignments_last_3d,
            "assignments_last_7d": assignments_last_7d,
        },
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


def get_scout_assignment_health(db: Session) -> Dict[str, Any]:
    try:
        return _safe_scout_assignment_health_impl(db)
    except Exception as e:
        _logger.error(f"[get_scout_assignment_health] {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_SCOUTS)


# ═══════════════════════════════════════════════════════════════════════════
# 3. HEALTH POR COHORTE
# ═══════════════════════════════════════════════════════════════════════════

def _safe_cohort_health_impl(
    db: Session,
    weeks_limit: int = 12,
    status_filter: Optional[str] = None,
    skip_trips: bool = False,
) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text("SET LOCAL statement_timeout = '60000ms'"))

    today = date.today()
    iy_expr = _iso_year_expr("s.hire_date")
    iw_expr = _iso_week_expr("s.hire_date")

    cohorts_sql = f"""
        WITH cohort_base AS (
            SELECT
                {iy_expr} AS iso_year,
                {iw_expr} AS iso_week,
                COUNT(*) AS total_drivers,
                COUNT(DISTINCT s.driver_id) FILTER (
                    WHERE s.driver_id IN (
                        SELECT a.driver_id FROM scout_liq_driver_assignments a
                        WHERE a.status = 'active'
                    )
                ) AS drivers_with_scout
            FROM {SOURCE_TABLE} s
            WHERE s.hire_date IS NOT NULL AND s.hire_date != ''
            GROUP BY {iy_expr}, {iw_expr}
            ORDER BY {iy_expr} DESC, {iw_expr} DESC
            LIMIT :weeks_limit
        )
        SELECT * FROM cohort_base ORDER BY iso_year ASC, iso_week ASC
    """
    raw_cohorts = db.execute(text(cohorts_sql), {"weeks_limit": weeks_limit}).fetchall()

    if not raw_cohorts:
        return {"cohorts": [], "total_cohorts_visible": 0, "global_status": "UNKNOWN", "global_reason": "No se detectaron cohortes en la fuente", "warning_count": 0, "blocked_count": 0}

    all_driver_ids = set()
    cohort_driver_map: Dict[str, List[str]] = {}
    cohort_meta: Dict[str, Dict] = {}

    for row in raw_cohorts:
        yr, wk = int(row[0]), int(row[1])
        key = f"{yr}-W{wk:02d}"
        monday, sunday = _iso_week_dates(yr, wk)
        maturity_at = _cohort_maturity(sunday, 7)
        is_mature = maturity_at <= today

        cohort_meta[key] = {
            "iso_year": yr,
            "iso_week": wk,
            "cohort_from": monday,
            "cohort_to": sunday,
            "maturity_at": maturity_at,
            "is_mature": is_mature,
            "total_drivers": row[2] or 0,
            "drivers_with_scout": row[3] or 0,
            "drivers_without_scout": max(0, (row[2] or 0) - (row[3] or 0)),
        }

    for key in cohort_meta:
        yr = cohort_meta[key]["iso_year"]
        wk = cohort_meta[key]["iso_week"]
        rows = db.execute(text(f"""
            SELECT driver_id FROM {SOURCE_TABLE}
            WHERE hire_date IS NOT NULL AND hire_date != ''
              AND EXTRACT(ISOYEAR FROM hire_date::date)::int = :yr
              AND EXTRACT(WEEK FROM hire_date::date)::int = :wk
        """), {"yr": yr, "wk": wk}).fetchall()
        dids = [r[0] for r in rows if r[0]]
        cohort_driver_map[key] = dids
        all_driver_ids.update(dids)

    if skip_trips:
        trip_map: Dict[str, Dict[str, int]] = {}
        paid_map: Dict[str, bool] = {}
    else:
        trip_map = _batch_trip_counts_health(db, list(all_driver_ids))
        paid_map = _batch_paid_history_health(db, list(all_driver_ids))

    cutoff_rows = db.execute(text(
        "SELECT cohort_iso_week, status, created_at, paid_at FROM scout_liq_cutoff_runs "
        "WHERE cohort_iso_week IS NOT NULL ORDER BY created_at DESC"
    )).fetchall()
    cutoff_by_cohort: Dict[str, dict] = {}
    for cr in cutoff_rows:
        cw = cr[0]
        if cw and cw not in cutoff_by_cohort:
            cutoff_by_cohort[cw] = {"status": cr[1], "created_at": str(cr[2]) if cr[2] else None,
                                     "paid_at": str(cr[3]) if cr[3] else None}

    cohorts = []
    for key in sorted(cohort_meta.keys(), reverse=True):
        meta = cohort_meta[key]
        dids = cohort_driver_map.get(key, [])
        cutoff = cutoff_by_cohort.get(key)

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

        unpaid = meta["total_drivers"] - paid_count

        flags = {
            "missing_scout_load_flag": meta["drivers_with_scout"] == 0 and meta["total_drivers"] > 0,
            "no_activity_flag": False if skip_trips else (activated_1_trip == 0 and meta["total_drivers"] > 0 and meta["is_mature"]),
            "missing_conversion_flag": False if skip_trips else (converted_5v7d == 0 and activated_1_trip > 0 and meta["is_mature"]),
            "stale_cohort_flag": meta["is_mature"] and not cutoff,
        }

        diagnostics = []
        if flags["missing_scout_load_flag"]:
            diagnostics.append("cohort_exists_without_scouts")
        if flags["no_activity_flag"]:
            diagnostics.append("cohort_matured_without_activity")
        if flags["missing_conversion_flag"]:
            diagnostics.append("cohort_has_activation_but_no_conversion")
        if flags["stale_cohort_flag"]:
            diagnostics.append("cohort_mature_without_cutoff")
        if skip_trips:
            diagnostics.append("trips_not_evaluated")

        reason_parts = []
        if meta["drivers_without_scout"] > 0:
            reason_parts.append(f"Existen {meta['drivers_without_scout']} drivers sin scout")
        if not skip_trips:
            if meta["is_mature"] and activated_1_trip == 0:
                reason_parts.append("Cohorte madura sin activaciones")
            if meta["is_mature"] and converted_5v7d == 0 and activated_1_trip > 0:
                reason_parts.append("Sin conversion a 5V7D a pesar de tener activaciones")
        if meta["is_mature"] and not cutoff:
            reason_parts.append("Cohorte madura sin cutoff creado")
        if meta["total_drivers"] == 0:
            reason_parts.append("Cohorte esperada vacia")

        if not reason_parts:
            reason_text = "Cohorte saludable"
            status = "OK"
        elif len(reason_parts) <= 1:
            reason_text = reason_parts[0]
            status = "WARNING"
        else:
            reason_text = "; ".join(reason_parts)
            status = "BLOCKED"

        cohort_entry = {
            "cohort_key": key,
            "cohort_label": f"S{meta['iso_week']:02d}-{meta['iso_year']}",
            "iso_year": meta["iso_year"],
            "iso_week": meta["iso_week"],
            "hire_date_from": meta["cohort_from"].isoformat(),
            "hire_date_to": meta["cohort_to"].isoformat(),
            "total_drivers": meta["total_drivers"],
            "with_scout": meta["drivers_with_scout"],
            "without_scout": meta["drivers_without_scout"],
            "activated_1_trip": activated_1_trip,
            "converted_5v7d": converted_5v7d,
            "converted_5v14d": converted_5v14d,
            "paid": paid_count,
            "unpaid": unpaid,
            "expected_7d_matured": meta["is_mature"],
            "expected_14d_matured": today >= _cohort_maturity(meta["cohort_to"], 14),
            "flags": flags,
            "diagnostics": diagnostics,
            "status": status,
            "reason_text": reason_text,
            "cutoff_status": cutoff["status"] if cutoff else None,
        }

        if status_filter is None or status_filter == status:
            cohorts.append(cohort_entry)

    warning_count = sum(1 for c in cohorts if c["status"] == "WARNING")
    blocked_count = sum(1 for c in cohorts if c["status"] == "BLOCKED")

    if blocked_count > 0:
        global_status = "BLOCKED"
        global_reason = f"{blocked_count} cohortes con problemas criticos"
    elif warning_count > 0:
        global_status = "WARNING"
        global_reason = f"{warning_count} cohortes con advertencias"
    else:
        global_status = "OK"
        global_reason = "Todas las cohortes saludables"

    return {
        "cohorts": cohorts,
        "total_cohorts_visible": len(cohorts),
        "global_status": global_status,
        "global_reason": global_reason,
        "warning_count": warning_count,
        "blocked_count": blocked_count,
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


def get_cohort_health(
    db: Session,
    weeks_limit: int = 12,
    status_filter: Optional[str] = None,
    skip_trips: bool = False,
) -> Dict[str, Any]:
    try:
        result = _safe_cohort_health_impl(db, weeks_limit, status_filter, skip_trips)
        _logger.info(f"[get_cohort_health] weeks={weeks_limit} skip_trips={skip_trips} status={result.get('global_status')} ms={result.get('_timing_ms')} cohorts={result.get('total_cohorts_visible')}")
        return result
    except Exception as e:
        _logger.error(f"[get_cohort_health] weeks_limit={weeks_limit} status_filter={status_filter}: {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_COHORTS)


# ═══════════════════════════════════════════════════════════════════════════
# 4. HEALTH DE SERVICIOS / JOBS
# ═══════════════════════════════════════════════════════════════════════════

def _safe_jobs_health_impl(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    today = date.today()

    jobs = []

    last_cutoff = None
    try:
        last_cutoff = db.execute(text(
            "SELECT MAX(created_at) FROM scout_liq_cutoff_runs"
        )).scalar()
    except Exception as e:
        _logger.warning(f"[get_jobs_health] scout_liq_cutoff_runs no accesible: {e}")

    if last_cutoff:
        last_cutoff_date = last_cutoff.date() if hasattr(last_cutoff, 'date') else datetime.fromisoformat(str(last_cutoff)).date()
        cutoff_gap_hours = (today - last_cutoff_date).days * 24
    else:
        last_cutoff_date = None
        cutoff_gap_hours = None

    last_paid = None
    try:
        last_paid = db.execute(text(
            "SELECT MAX(created_at) FROM scout_liq_paid_history"
        )).scalar()
    except Exception as e:
        _logger.warning(f"[get_jobs_health] scout_liq_paid_history no accesible: {e}")

    if last_paid:
        last_paid_date = last_paid.date() if hasattr(last_paid, 'date') else datetime.fromisoformat(str(last_paid)).date()
        paid_gap_hours = (today - last_paid_date).days * 24
    else:
        last_paid_date = None
        paid_gap_hours = None

    last_import = None
    try:
        last_import = db.execute(text(
            "SELECT MAX(created_at) FROM scout_liq_historical_import_batches"
        )).scalar()
    except Exception as e:
        _logger.warning(f"[get_jobs_health] scout_liq_historical_import_batches no accesible: {e}")

    last_source_update = None
    try:
        last_source_update = db.execute(text(
            f"SELECT MAX(updated_at::text), MAX(created_at::text) FROM {SOURCE_TABLE}"
        )).fetchone()
    except Exception as e:
        _logger.warning(f"[get_jobs_health] {SOURCE_TABLE} no accesible: {e}")

    last_scout_assignment = None
    try:
        last_scout_assignment = str(db.execute(text(
            "SELECT MAX(created_at) FROM scout_liq_driver_assignments"
        )).scalar())
    except Exception as e:
        _logger.warning(f"[get_jobs_health] scout_liq_driver_assignments no accesible: {e}")

    jobs.append({
        "job_name": "cutoff_engine",
        "type": "cutoff",
        "cron_detected": False,
        "last_run": str(last_cutoff) if last_cutoff else None,
        "gap_hours": cutoff_gap_hours,
        "status": _status_from_gap(cutoff_gap_hours) if cutoff_gap_hours is not None else "UNKNOWN",
        "notes": "Sin cron detectado. La ejecucion es manual via endpoint /cutoffs/from-cohort",
    })

    jobs.append({
        "job_name": "data_pipeline_feed",
        "type": "source_refresh",
        "cron_detected": False,
        "last_known_refresh": last_source_update[0] if last_source_update else None,
        "last_known_create": last_source_update[1] if last_source_update else None,
        "status": "UNKNOWN",
        "notes": "Sin cron de refresh detectado. La carga de data a module_ct_cabinet_drivers es externa al sistema.",
    })

    jobs.append({
        "job_name": "paid_history_writes",
        "type": "payment",
        "cron_detected": False,
        "last_run": str(last_paid) if last_paid else None,
        "gap_hours": paid_gap_hours,
        "status": _status_from_gap(paid_gap_hours) if paid_gap_hours is not None else "UNKNOWN",
        "notes": "Sin cron. Los pagos se registran via cutoff engine o import manual.",
    })

    jobs.append({
        "job_name": "historical_import",
        "type": "data_load",
        "cron_detected": False,
        "last_run": str(last_import) if last_import else None,
        "status": "OK" if last_import else "UNKNOWN",
        "notes": "Import manual via archivo. Sin cron automatico.",
    })

    jobs.append({
        "job_name": "scout_assignment_loader",
        "type": "data_load",
        "cron_detected": False,
        "last_run": last_scout_assignment,
        "status": "OK" if last_scout_assignment else "UNKNOWN",
        "notes": "Carga manual de scouts. Sin cron automatico.",
    })

    job_statuses = [j["status"] for j in jobs if j["status"] != "UNKNOWN"]
    if not job_statuses:
        global_status = "INFO"
        global_reason = "No hay jobs automaticos detectados. Todo es a demanda."
    elif "BLOCKED" in job_statuses:
        global_status = "BLOCKED"
        global_reason = "Al menos un job critico esta sin actividad reciente"
    elif "WARNING" in job_statuses:
        global_status = "WARNING"
        global_reason = "Algun job tiene gap de actividad"
    else:
        global_status = "OK"
        global_reason = "Jobs operativos con actividad reciente"

    return {
        "jobs": jobs,
        "global_status": global_status,
        "global_reason": global_reason,
        "inferred_only": True,
        "note": "No se detectaron crons automaticos. Diagnostico inferido de timestamps de tablas internas.",
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


def get_jobs_health(db: Session) -> Dict[str, Any]:
    try:
        return _safe_jobs_health_impl(db)
    except Exception as e:
        _logger.error(f"[get_jobs_health] {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_JOBS)


# ═══════════════════════════════════════════════════════════════════════════
# 5. SUMMARY AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════

def get_health_summary(db: Session) -> Dict[str, Any]:
    try:
        return _safe_health_summary_impl(db)
    except Exception as e:
        _logger.error(f"[get_health_summary] {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_SUMMARY)


def _safe_health_summary_impl(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()

    t_s = _time.perf_counter()
    source = get_source_health(db)
    source_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    scouts = get_scout_assignment_health(db)
    scouts_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    cohorts = get_cohort_health(db, weeks_limit=4, skip_trips=True)
    cohort_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    jobs = get_jobs_health(db)
    jobs_ms = round((_time.perf_counter() - t_s) * 1000)

    statuses = [source["status"], scouts["status"], cohorts["global_status"], jobs["global_status"]]
    if "BLOCKED" in statuses:
        global_status = "BLOCKED"
    elif "WARNING" in statuses:
        global_status = "WARNING"
    elif "INFO" in statuses:
        global_status = "INFO"
    else:
        global_status = "OK"

    alerts = []
    if source["status"] != "OK":
        alerts.append({
            "source": "source_health",
            "severity": source["status"],
            "message": source.get("reason_text", ""),
        })
    if scouts["status"] != "OK":
        alerts.append({
            "source": "scout_assignment",
            "severity": scouts["status"],
            "message": scouts.get("reason_text", ""),
        })
    for c in cohorts.get("cohorts", []) or []:
        if c["status"] != "OK":
            alerts.append({
                "source": f"cohort/{c['cohort_key']}",
                "severity": c["status"],
                "message": c.get("reason_text", ""),
            })

    result = {
        "global_status": global_status,
        "evaluated_at": date.today().isoformat(),
        "sections": {
            "source": {
                "status": source["status"],
                "reason_text": source.get("reason_text", ""),
                "data_lag_days": source.get("data_lag_days"),
                "last_data_date": source.get("last_data_date"),
            },
            "scouts": {
                "status": scouts["status"],
                "reason_text": scouts.get("reason_text", ""),
                "coverage_pct": (scouts.get("metrics") or {}).get("scout_coverage_pct"),
            },
            "cohorts": {
                "status": cohorts.get("global_status", "UNKNOWN"),
                "reason_text": cohorts.get("global_reason", ""),
                "warning_count": cohorts.get("warning_count", 0),
                "blocked_count": cohorts.get("blocked_count", 0),
            },
            "jobs": {
                "status": jobs.get("global_status", "UNKNOWN"),
                "reason_text": jobs.get("global_reason", ""),
            },
        },
        "alerts": alerts,
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
        "_timing_breakdown": {
            "source_ms": source_ms,
            "scouts_ms": scouts_ms,
            "cohorts_ms": cohort_ms,
            "jobs_ms": jobs_ms,
        },
    }
    _logger.info(f"[summary] total={result['_timing_ms']}ms source={source_ms}ms scouts={scouts_ms}ms cohorts={cohort_ms}ms jobs={jobs_ms}ms global={result['global_status']}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5B. HEALTH SUMMARY LITE — Sin cohorts pesadas, sin trips
# ═══════════════════════════════════════════════════════════════════════════

def get_health_summary_lite(db: Session) -> Dict[str, Any]:
    """Resumen ejecutivo rápido. NO consulta cohorts, NO escanea trips.
    Deriva salud de cohortes desde eventos abiertos y registry."""
    try:
        return _safe_health_summary_lite(db)
    except Exception as e:
        _logger.error(f"[get_health_summary_lite] {e}\n{traceback.format_exc()}")
        return dict(_HEALTH_FALLBACK_SUMMARY)


def _safe_health_summary_lite(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()

    t_s = _time.perf_counter()
    source = get_source_health(db)
    source_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    scouts = get_scout_assignment_health(db)
    scouts_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    jobs = get_jobs_health(db)
    jobs_ms = round((_time.perf_counter() - t_s) * 1000)

    t_s = _time.perf_counter()
    open_events = _get_open_event_counts(db)
    events_ms = round((_time.perf_counter() - t_s) * 1000)

    source_status = source.get("status", "UNKNOWN") if source else "UNKNOWN"
    scouts_status = scouts.get("status", "UNKNOWN") if scouts else "UNKNOWN"
    jobs_status = (jobs or {}).get("global_status", "UNKNOWN")

    blocked_events = open_events.get("blocked", 0)
    warning_events = open_events.get("warning", 0)
    if blocked_events > 0:
        cohort_status = "BLOCKED"
        cohort_reason = f"{blocked_events} eventos criticos activos"
    elif warning_events > 0:
        cohort_status = "WARNING"
        cohort_reason = f"{warning_events} eventos con advertencias activos"
    else:
        cohort_status = "OK"
        cohort_reason = "Sin eventos de salud activos"

    statuses = [source_status, scouts_status, cohort_status, jobs_status]
    if "BLOCKED" in statuses:
        global_status = "BLOCKED"
    elif "WARNING" in statuses:
        global_status = "WARNING"
    elif "INFO" in statuses:
        global_status = "INFO"
    else:
        global_status = "OK"

    alerts = []
    if source_status != "OK":
        alerts.append({
            "source": "source_health",
            "severity": source_status,
            "message": source.get("reason_text", ""),
        })
    if scouts_status != "OK":
        alerts.append({
            "source": "scout_assignment",
            "severity": scouts_status,
            "message": scouts.get("reason_text", ""),
        })
    if cohort_status != "OK":
        alerts.append({
            "source": "cohorts_via_events",
            "severity": cohort_status,
            "message": cohort_reason,
        })

    total_ms = round((_time.perf_counter() - t0) * 1000)
    _logger.info(f"[summary_lite] total={total_ms}ms source={source_ms}ms scouts={scouts_ms}ms jobs={jobs_ms}ms events={events_ms}ms global={global_status}")

    return {
        "global_status": global_status,
        "evaluated_at": date.today().isoformat(),
        "mode": "lite",
        "sections": {
            "source": {
                "status": source_status,
                "reason_text": source.get("reason_text", ""),
                "data_lag_days": source.get("data_lag_days"),
                "data_lag_minutes": source.get("data_lag_minutes"),
                "data_lag_hours": source.get("data_lag_hours"),
                "last_data_date": source.get("last_data_date"),
            },
            "scouts": {
                "status": scouts_status,
                "reason_text": scouts.get("reason_text", ""),
                "coverage_pct": (scouts.get("metrics") or {}).get("scout_coverage_pct"),
            },
            "cohorts": {
                "status": cohort_status,
                "reason_text": cohort_reason,
                "open_events_blocked": blocked_events,
                "open_events_warning": warning_events,
            },
            "jobs": {
                "status": jobs_status,
                "reason_text": (jobs or {}).get("global_reason", ""),
            },
        },
        "alerts": alerts,
        "_timing_ms": total_ms,
        "_timing_breakdown": {
            "source_ms": source_ms,
            "scouts_ms": scouts_ms,
            "jobs_ms": jobs_ms,
            "events_ms": events_ms,
        },
    }


def _get_open_event_counts(db: Session) -> Dict[str, int]:
    """Cuenta eventos abiertos por severidad. No toca trips."""
    try:
        db.execute(text(STATEMENT_TIMEOUT))
        rows = db.execute(text("""
            SELECT severity, COUNT(*) as cnt
            FROM scout_liq_health_events
            WHERE status = 'open'
            GROUP BY severity
        """)).fetchall()
        result: Dict[str, int] = {"blocked": 0, "warning": 0, "info": 0}
        for r in rows:
            sev = (r[0] or "").lower()
            if sev in result:
                result[sev] = r[1] or 0
        return result
    except Exception:
        return {"blocked": 0, "warning": 0, "info": 0}


# ═══════════════════════════════════════════════════════════════════════════
# BATCH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _batch_trip_counts_health(db: Session, driver_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text(STATEMENT_TIMEOUT))
    sql = f"""
        WITH driver_windows AS (
            SELECT
                driver_id,
                hire_date::date AS hire_date,
                hire_date::date + INTERVAL '7 days' AS d7,
                hire_date::date + INTERVAL '14 days' AS d14,
                hire_date::date + INTERVAL '30 days' AS d30
            FROM {SOURCE_TABLE}
            WHERE driver_id IN ({placeholders})
              AND hire_date IS NOT NULL AND hire_date != ''
        ),
        trips_all AS (
            SELECT conductor_id AS driver_id, fecha_inicio_viaje::date AS trip_date
            FROM trips_2026
            WHERE conductor_id IN ({placeholders}) AND condicion = 'Completado'
            UNION ALL
            SELECT t2025.conductor_id AS driver_id, t2025.fecha_inicio_viaje::date AS trip_date
            FROM trips_2025 t2025
            JOIN driver_windows dw ON t2025.conductor_id = dw.driver_id AND dw.d30 < '2026-01-01'::date
            WHERE t2025.conductor_id IN ({placeholders}) AND t2025.condicion = 'Completado'
        )
        SELECT
            dw.driver_id,
            COUNT(t.trip_date) FILTER (
                WHERE t.trip_date >= dw.hire_date AND t.trip_date < dw.d7
            )::int AS trips_0_7,
            COUNT(t.trip_date) FILTER (
                WHERE t.trip_date >= dw.d7 AND t.trip_date < dw.d14
            )::int AS trips_8_14,
            COUNT(t.trip_date) FILTER (
                WHERE t.trip_date >= dw.hire_date AND t.trip_date < dw.d30
            )::int AS trips_0_30
        FROM driver_windows dw
        LEFT JOIN trips_all t ON t.driver_id = dw.driver_id
            AND t.trip_date >= dw.hire_date AND t.trip_date < dw.d30
        GROUP BY dw.driver_id
    """
    rows = db.execute(text(sql), params).fetchall()
    return {r[0]: {"trips_0_7": r[1] or 0, "trips_8_14": r[2] or 0, "trips_0_30": r[3] or 0} for r in rows}


def _batch_paid_history_health(db: Session, driver_ids: List[str]) -> Dict[str, bool]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text(STATEMENT_TIMEOUT))
    rows = db.execute(text(f"""
        SELECT DISTINCT driver_id FROM scout_liq_paid_history
        WHERE driver_id IN ({placeholders}) AND blocks_future_payment = true
    """), params).fetchall()
    return {r[0]: True for r in rows}
