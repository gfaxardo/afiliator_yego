"""
Cohort Service — Modelo temporal de cohortes ISO para Liquidador Scouts.

La cohorte se define por la semana ISO del hire_date.
Madura cohort_to + maturity_days (default 7).
Solo es liquidable cuando CURRENT_DATE >= maturity_completed_at.
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


def get_iso_cohorts(
    db: Session,
    readiness_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve todas las cohortes ISO detectadas desde la fuente,
    con metadata temporal, conteos basicos, y readiness_status.

    NOTA: activated/converted_5v7d se computan on-demand en el cutoff engine
    (via trips_2025/trips_2026 con LATERAL). Esta vista es liviana: solo
    agrupa por ISO week del hire_date sin joins a trips.
    """
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    today = date.today()
    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")

    # ── 1. Cohort base: group by ISO week from source ──
    cohort_sql = f"""
        SELECT
            {iy} AS iso_year,
            {iw} AS iso_week,
            COUNT(*) AS total_drivers,
            COUNT(DISTINCT src.driver_id) FILTER (WHERE src.driver_id IS NOT NULL AND src.driver_id != '') AS with_driver_id,
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

    # ── 2. Build cohort_metrics dict (sin trip counts — pesados, on-demand) ──
    cohort_metrics: Dict[str, Dict[str, Any]] = {}
    for row in cohorts_raw:
        yr = int(row[0])
        wk = int(row[1])
        key = f"{yr}-W{wk:02d}"
        monday, sunday = iso_week_dates(yr, wk)
        cohort_metrics[key] = {
            "iso_year": yr,
            "iso_week": wk,
            "cohort_from": monday,
            "cohort_to": sunday,
            "total_drivers": row[2] or 0,
            "drivers_with_scout": row[3] or 0,
            "drivers_without_scout": max(0, (row[2] or 0) - (row[3] or 0)),
            "activated": 0,
            "converted_5v7d": 0,
        }

    # ── 3. Load existing cutoff runs indexed by cohort_iso_week ──
    cutoff_rows = db.execute(text(
        "SELECT id, cohort_iso_week, status, created_at, approved_at, paid_at "
        "FROM scout_liq_cutoff_runs WHERE cohort_iso_week IS NOT NULL ORDER BY created_at DESC"
    )).fetchall()
    cutoff_by_cohort: Dict[str, dict] = {}
    for cr in cutoff_rows:
        cw = cr[1]
        if cw and cw not in cutoff_by_cohort:
            cutoff_by_cohort[cw] = {
                "cutoff_run_id": cr[0],
                "cutoff_status": cr[2],
                "created_at": str(cr[3]) if cr[3] else None,
                "approved_at": str(cr[4]) if cr[4] else None,
                "paid_at": str(cr[5]) if cr[5] else None,
            }

    # ── 4. Assemble final list with readiness_status ──
    result = []
    for key, meta in sorted(cohort_metrics.items(), key=lambda x: (x[1]["iso_year"], x[1]["iso_week"]), reverse=True):
        cohort_from = meta["cohort_from"]
        cohort_to = meta["cohort_to"]
        maturity_days = 7
        maturity_at = cohort_maturity(cohort_to, maturity_days)

        cutoff = cutoff_by_cohort.get(key)
        cutoff_status = cutoff["cutoff_status"] if cutoff else None

        # Readiness:
        #   open   = no ha madurado (maturity_at > today)
        #   mature = maduró, sin cutoff o cutoff en draft
        #   locked = tiene cutoff en proceso (calculated/reviewed/approved)
        #   paid   = cutoff pagado
        if cutoff_status == "paid":
            readiness = "paid"
        elif cutoff_status in ("calculated", "reviewed", "approved"):
            readiness = "locked"
        elif maturity_at > today:
            readiness = "open"
        else:
            readiness = "mature"

        # Aplica filtro si se especificó
        if readiness_filter and readiness_filter != readiness:
            continue

        result.append({
            "cohort_iso_week": key,
            "cohort_label": f"S{meta['iso_week']:02d}-{meta['iso_year']}",
            "iso_year": meta["iso_year"],
            "iso_week": meta["iso_week"],
            "cohort_from": cohort_from.isoformat(),
            "cohort_to": cohort_to.isoformat(),
            "maturity_days": maturity_days,
            "maturity_completed_at": maturity_at.isoformat(),
            "is_mature": maturity_at <= today,
            "total_drivers": meta["total_drivers"],
            "drivers_with_scout": meta["drivers_with_scout"],
            "drivers_without_scout": meta["drivers_without_scout"],
            "activated": meta["activated"],
            "converted_5v7d": meta["converted_5v7d"],
            "readiness_status": readiness,
            "cutoff_run_id": cutoff["cutoff_run_id"] if cutoff else None,
            "cutoff_status": cutoff_status,
        })

    elapsed = round((_time.perf_counter() - t0) * 1000)
    return result


def get_cohort_diagnostic(db: Session) -> Dict[str, Any]:
    """
    Diagnóstico de cohortes: conteos por estado de madurez.
    """
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    today = date.today()
    cohorts = get_iso_cohorts(db)

    open_cohorts = [c for c in cohorts if c["readiness_status"] == "open"]
    mature_cohorts = [c for c in cohorts if c["readiness_status"] == "mature"]
    locked_cohorts = [c for c in cohorts if c["readiness_status"] == "locked"]
    paid_cohorts = [c for c in cohorts if c["readiness_status"] == "paid"]

    # Find the latest mature cohort that has no cutoff yet (candidate for liquidation)
    liquidable = [c for c in mature_cohorts if not c.get("cutoff_run_id")]

    return {
        "current_date": today.isoformat(),
        "total_cohorts": len(cohorts),
        "by_readiness": {
            "open": len(open_cohorts),
            "mature": len(mature_cohorts),
            "locked": len(locked_cohorts),
            "paid": len(paid_cohorts),
        },
        "liquidable_cohorts": [c["cohort_iso_week"] for c in liquidable],
        "latest_open": open_cohorts[0]["cohort_iso_week"] if open_cohorts else None,
        "latest_mature": mature_cohorts[0]["cohort_iso_week"] if mature_cohorts else None,
        "latest_mature_matures_on": mature_cohorts[0]["maturity_completed_at"] if mature_cohorts else None,
        "open_details": [
            {
                "cohort_iso_week": c["cohort_iso_week"],
                "maturity_completed_at": c["maturity_completed_at"],
                "days_until_mature": (datetime.strptime(c["maturity_completed_at"], "%Y-%m-%d").date() - today).days,
                "total_drivers": c["total_drivers"],
            }
            for c in open_cohorts[:5]
        ],
        "mature_details": [
            {
                "cohort_iso_week": c["cohort_iso_week"],
                "maturity_completed_at": c["maturity_completed_at"],
                "total_drivers": c["total_drivers"],
                "activated": c["activated"],
                "converted_5v7d": c["converted_5v7d"],
                "has_cutoff": c.get("cutoff_run_id") is not None,
            }
            for c in mature_cohorts[:5]
        ],
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }
