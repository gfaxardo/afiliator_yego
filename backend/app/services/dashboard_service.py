"""
Dashboard Service V1 — KPIs ejecutivos, ranking por scout, evolucion semanal, quality funnel, alerts.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings

SOURCE_TABLE = settings.SOURCE_TABLE


def _iso_year_week(col: str) -> tuple:
    return (
        f"EXTRACT(ISOYEAR FROM {col}::date)::int",
        f"EXTRACT(WEEK FROM {col}::date)::int",
    )


def _build_base_where(params: dict, iy_expr: str = None, iw_expr: str = None) -> tuple:
    parts = ["lil.batch_id = :batch_id"]
    p = {"batch_id": 20}

    if params.get("week_iso") and iy_expr:
        try:
            py, pw = str(params["week_iso"]).split("-W")
            p["iy"] = int(py)
            p["iw"] = int(pw)
            parts.append(f"({iy_expr} = :iy AND {iw_expr} = :iw)")
        except (ValueError, IndexError):
            pass

    for k, col in [("scout_id", "lil.scout_id_resolved"), ("supervisor_id", "lil.supervisor_id_resolved")]:
        if params.get(k):
            p[k] = int(params[k])
            parts.append(f"{col} = :{k}")

    if params.get("origin"):
        p["origin"] = params["origin"]
        parts.append("LOWER(COALESCE(src.origen, lil.origin_raw)) = LOWER(:origin)")

    if params.get("hire_date_from"):
        p["hd_from"] = params["hire_date_from"]
        parts.append("src.hire_date::date >= :hd_from")
    if params.get("hire_date_to"):
        p["hd_to"] = params["hire_date_to"]
        parts.append("src.hire_date::date <= :hd_to")

    return parts, p


def _base_from() -> str:
    return f"""
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
    """


def get_dashboard_overview(db: Session, **filters) -> Dict[str, Any]:
    iy, iw = _iso_year_week("src.hire_date")
    where_parts, p = _build_base_where(filters, iy, iw)
    where = " AND ".join(where_parts)
    base_from = _base_from()

    def q(sql_where_extra: str = "") -> Any:
        w = f"{where} {sql_where_extra}".strip()
        return db.execute(text(f"SELECT COUNT(*) {base_from} WHERE {w}"), p).scalar() or 0

    total = q()
    with_driver = q("AND lil.driver_id_resolved IS NOT NULL")
    with_scout = q("AND lil.scout_id_resolved IS NOT NULL")
    manual_review = q("AND lil.final_status = 'manual_review'")

    paid_count = q("AND lil.paid_history_id IS NOT NULL")
    paid_amt = db.execute(text(f"""
        SELECT COALESCE(SUM(ph.amount_paid), 0) {base_from}
        JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where}
    """), p).scalar() or 0

    blocking_count = db.execute(text(f"""
        SELECT COUNT(*) {base_from}
        JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where} AND ph.blocks_future_payment = true
    """), p).scalar() or 0
    blocking_amt = db.execute(text(f"""
        SELECT COALESCE(SUM(ph.amount_paid), 0) {base_from}
        JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where} AND ph.blocks_future_payment = true
    """), p).scalar() or 0

    financial_only_count = q("AND lil.paid_history_id IS NOT NULL AND lil.blocks_future_payment = false")
    financial_only_amt = db.execute(text(f"""
        SELECT COALESCE(SUM(ph.amount_paid), 0) {base_from}
        JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where} AND ph.blocks_future_payment = false
    """), p).scalar() or 0

    blocks_bad = q("AND lil.blocks_future_payment = true AND lil.driver_id_resolved IS NULL")
    dup_hashes = db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT ph.unique_hash {base_from}
            JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
            WHERE {where} AND lil.paid_history_id IS NOT NULL AND ph.unique_hash IS NOT NULL
            GROUP BY ph.unique_hash HAVING COUNT(*) > 1
        ) sub
    """), p).scalar() or 0

    active_scouts = db.execute(text(f"""
        SELECT COUNT(DISTINCT lil.scout_id_resolved) {base_from} WHERE {where} AND lil.scout_id_resolved IS NOT NULL
    """), p).scalar() or 0

    scouts_with_payments = db.execute(text(f"""
        SELECT COUNT(DISTINCT lil.scout_id_resolved) {base_from} WHERE {where} AND lil.paid_history_id IS NOT NULL
    """), p).scalar() or 0

    scouts_with_review = db.execute(text(f"""
        SELECT COUNT(DISTINCT lil.scout_id_resolved) {base_from} WHERE {where} AND lil.final_status = 'manual_review'
    """), p).scalar() or 0

    has_cutoff = db.execute(text("SELECT COUNT(*) FROM scout_liq_cutoff_runs")).scalar() or 0

    week_iso = filters.get("week_iso")
    scope_label = f"Semana {week_iso}" if week_iso else "Todas las semanas"

    return {
        "scope_label": scope_label,
        "total_affiliations": total,
        "total_with_driver": with_driver,
        "total_without_driver": total - with_driver,
        "total_with_scout": with_scout,
        "total_without_scout": total - with_scout,
        "total_manual_review": manual_review,
        "paid_history_count": paid_count,
        "paid_history_amount": float(paid_amt),
        "blocking_count": blocking_count,
        "blocking_amount": float(blocking_amt),
        "financial_only_count": financial_only_count,
        "financial_only_amount": float(financial_only_amt),
        "blocks_true_without_driver_count": blocks_bad,
        "duplicate_hash_count": dup_hashes,
        "active_scouts": active_scouts,
        "scouts_with_payments": scouts_with_payments,
        "scouts_with_manual_review": scouts_with_review,
        "pending_cutoff_warning": has_cutoff == 0,
    }


def get_dashboard_by_scout(db: Session, **filters) -> List[Dict[str, Any]]:
    iy, iw = _iso_year_week("src.hire_date")
    where_parts, p = _build_base_where(filters, iy, iw)
    where = " AND ".join(where_parts)

    rows = db.execute(text(f"""
        SELECT
            s.id AS scout_id,
            COALESCE(s.scout_name, lil.scout_name_raw) AS scout_name,
            lil.supervisor_raw AS supervisor_name,
            COUNT(*) AS affiliations_total,
            COUNT(lil.driver_id_resolved) AS with_driver,
            COUNT(*) - COUNT(lil.driver_id_resolved) AS without_driver,
            COUNT(CASE WHEN lil.final_status = 'manual_review' THEN 1 END) AS manual_review,
            COUNT(lil.paid_history_id) AS paid_history_count,
            COALESCE(SUM(ph.amount_paid), 0) AS paid_history_amount,
            COUNT(CASE WHEN ph.blocks_future_payment = true THEN 1 END) AS blocking_count,
            COUNT(CASE WHEN ph.id IS NOT NULL AND ph.blocks_future_payment = false THEN 1 END) AS financial_only_count,
            CASE WHEN COUNT(lil.paid_history_id) > 0
                THEN COALESCE(SUM(ph.amount_paid), 0) / COUNT(lil.paid_history_id)
                ELSE 0 END AS avg_amount_per_paid_driver,
            CASE WHEN COUNT(lil.final_status) = COUNT(CASE WHEN lil.blocks_future_payment = true AND lil.paid_history_id IS NOT NULL THEN 1 END)
                AND COUNT(lil.paid_history_id) > 0 THEN 'ok'
                WHEN COUNT(CASE WHEN lil.final_status = 'manual_review' THEN 1 END) > COUNT(*) / 2 THEN 'warning'
                WHEN COUNT(lil.paid_history_id) = 0 THEN 'ok'
                ELSE 'ok' END AS alert_level
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
        LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where}
        GROUP BY s.id, s.scout_name, lil.scout_name_raw, lil.supervisor_raw
        ORDER BY paid_history_amount DESC, affiliations_total DESC
        LIMIT 100
    """), p).fetchall()

    return [
        {
            "scout_id": r[0], "scout_name": r[1], "supervisor_name": r[2],
            "affiliations_total": r[3], "with_driver": r[4], "without_driver": r[5],
            "manual_review": r[6], "paid_history_count": r[7],
            "paid_history_amount": float(r[8] or 0), "blocking_count": r[9],
            "financial_only_count": r[10],
            "avg_amount_per_paid_driver": float(r[11] or 0),
            "alert_level": r[12],
        }
        for r in rows
    ]


def get_dashboard_by_week(db: Session, **filters) -> List[Dict[str, Any]]:
    iy, iw = _iso_year_week("src.hire_date")
    where_parts, p = _build_base_where(filters, iy, iw)
    where = " AND ".join(where_parts)

    rows = db.execute(text(f"""
        SELECT
            {iy} AS iso_year,
            {iw} AS iso_week,
            'S' || LPAD({iw}::text, 2, '0') || '-' || {iy}::text AS label,
            COUNT(*) AS total,
            COUNT(lil.paid_history_id) AS paid_count,
            COALESCE(SUM(ph.amount_paid), 0) AS paid_amount,
            COUNT(CASE WHEN ph.blocks_future_payment = true THEN 1 END) AS blocking_count,
            COUNT(CASE WHEN ph.id IS NOT NULL AND ph.blocks_future_payment = false THEN 1 END) AS financial_only_count,
            COUNT(CASE WHEN lil.final_status = 'manual_review' THEN 1 END) AS manual_review,
            COUNT(lil.driver_id_resolved) AS with_driver,
            COUNT(*) - COUNT(lil.driver_id_resolved) AS without_driver
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where} AND {iy} IS NOT NULL
        GROUP BY {iy}, {iw}
        ORDER BY {iy} DESC, {iw} DESC
    """), p).fetchall()

    return [
        {
            "iso_year": r[0], "iso_week": r[1], "label": r[2],
            "total": r[3], "paid_count": r[4], "paid_amount": float(r[5] or 0),
            "blocking_count": r[6], "financial_only_count": r[7],
            "manual_review": r[8], "with_driver": r[9], "without_driver": r[10],
        }
        for r in rows
    ]


def get_dashboard_quality_funnel(db: Session, **filters) -> Dict[str, Any]:
    has_cutoff = db.execute(text("SELECT COUNT(*) FROM scout_liq_cutoff_runs")).scalar() or 0
    if not has_cutoff:
        return {"status": "pending_cutoff", "message": "Aun no hay corte calculado. Crea un corte para ver el embudo de calidad."}

    # Get latest approved/reviewed cutoff
    cutoff = db.execute(text("""
        SELECT id FROM scout_liq_cutoff_runs
        WHERE status IN ('reviewed', 'approved', 'paid')
        ORDER BY id DESC LIMIT 1
    """)).fetchone()

    if not cutoff:
        return {"status": "pending_cutoff", "message": "No hay corte revisado o aprobado aun."}

    cutoff_id = cutoff[0]
    totals = db.execute(text("""
        SELECT
            SUM(total_affiliations) AS total,
            SUM(drivers_1plus_0_7) AS d1_0_7,
            SUM(drivers_5plus_0_7) AS d5_0_7,
            SUM(drivers_1plus_8_14) AS d1_8_14,
            SUM(drivers_5plus_0_14) AS d5_0_14,
            SUM(converted_5trips_7d) AS conv_5v7d,
            AVG(conversion_rate) AS avg_rate
        FROM scout_liq_cutoff_scout_summary WHERE cutoff_run_id = :cid
    """), {"cid": cutoff_id}).fetchone()

    return {
        "status": "ok",
        "cutoff_run_id": cutoff_id,
        "total_affiliations": totals[0] or 0,
        "drivers_1plus_0_7": totals[1] or 0,
        "drivers_5plus_0_7": totals[2] or 0,
        "drivers_1plus_8_14": totals[3] or 0,
        "drivers_5plus_0_14": totals[4] or 0,
        "conversion_5v_7d": totals[5] or 0,
        "avg_conversion_rate": float(totals[6] or 0),
    }


def get_dashboard_alerts(db: Session, **filters) -> Dict[str, Any]:
    iy, iw = _iso_year_week("src.hire_date")
    where_parts, p = _build_base_where(filters, iy, iw)
    where = " AND ".join(where_parts)
    base_from = _base_from()

    def q(extra: str = "") -> int:
        return db.execute(text(f"SELECT COUNT(*) {base_from} WHERE {where} {extra}".strip()), p).scalar() or 0

    return {
        "manual_review_count": q("AND lil.final_status = 'manual_review'"),
        "without_driver_count": q("AND lil.driver_id_resolved IS NULL"),
        "without_scout_count": q("AND lil.scout_id_resolved IS NULL AND lil.scout_name_raw IS NOT NULL"),
        "financial_only_count": q("AND lil.paid_history_id IS NOT NULL AND lil.blocks_future_payment = false"),
        "blocks_true_without_driver_count": q("AND lil.blocks_future_payment = true AND lil.driver_id_resolved IS NULL"),
        "duplicate_hash_count": db.execute(text(f"""
            SELECT COUNT(*) FROM (
                SELECT ph.unique_hash {base_from}
                JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
                WHERE {where} AND lil.paid_history_id IS NOT NULL AND ph.unique_hash IS NOT NULL
                GROUP BY ph.unique_hash HAVING COUNT(*) > 1
            ) sub
        """), p).scalar() or 0,
        "supervisor_missing_count": q("AND lil.supervisor_id_resolved IS NULL AND lil.supervisor_raw IS NOT NULL"),
        "cutoff_pending": db.execute(text("SELECT COUNT(*) FROM scout_liq_cutoff_runs")).scalar() == 0,
    }
