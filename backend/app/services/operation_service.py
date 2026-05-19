"""
Operation Service v2 — Grilla unificada de afiliaciones con filtros, semana ISO y alertas corregidas.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings

SOURCE_TABLE = settings.SOURCE_TABLE


def _iso_year_expr(col: str) -> str:
    return f"EXTRACT(ISOYEAR FROM {col}::date)::int"

def _iso_week_expr(col: str) -> str:
    return f"EXTRACT(WEEK FROM {col}::date)::int"

def _iso_start_expr(col: str) -> str:
    return f"date_trunc('week', {col}::date)::date"

def _iso_end_expr(col: str) -> str:
    return f"(date_trunc('week', {col}::date) + INTERVAL '6 days')::date"


def current_iso_week() -> tuple:
    """Return (iso_year, iso_week) for today."""
    today = date.today()
    return today.isocalendar()[0], today.isocalendar()[1]


def iso_week_dates(iso_year: int, iso_week: int) -> tuple:
    """Return (start_date, end_date) for an ISO week."""
    jan4 = date(iso_year, 1, 4)
    start = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=iso_week - 1)
    end = start + timedelta(days=6)
    return start, end


def _build_iso_label(iso_year_expr: str, iso_week_expr: str) -> str:
    return f"""
        CASE WHEN {iso_year_expr} IS NOT NULL AND {iso_week_expr} IS NOT NULL
        THEN 'S' || LPAD({iso_week_expr}::text, 2, '0') || '-' || {iso_year_expr}::text
        ELSE 'Sin fecha' END
    """


# ── Alert logic (CORRECTED) ──

def _build_alert_level() -> str:
    """Fixed: duplicates with paid_history_id are NOT critical."""
    return r"""
    CASE
        WHEN lil.attribution_status = 'attribution_rejected_missing_scout_and_driver' THEN 'critical'
        WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NULL THEN 'critical'
        WHEN lil.blocks_future_payment = true AND lil.driver_id_resolved IS NULL THEN 'critical'
        WHEN lil.payment_blocking_status = 'payment_blocking_manual_review_no_driver'
             OR lil.attribution_status = 'attribution_manual_review' THEN 'warning'
        WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NOT NULL THEN 'ok'
        WHEN lil.payment_financial_status = 'payment_financial_ready'
             AND lil.paid_history_id IS NULL THEN 'warning'
        WHEN lil.attribution_status = 'attribution_ready'
             AND lil.payment_blocking_status = 'payment_blocking_ready' THEN 'ok'
        WHEN lil.attribution_status = 'attribution_ready'
             AND lil.payment_financial_status = 'payment_financial_ready'
             AND lil.paid_history_id IS NOT NULL THEN 'ok'
        WHEN lil.payment_financial_status = 'payment_financial_not_applicable_no_amount'
             AND lil.attribution_status = 'attribution_ready' THEN 'ok'
        WHEN src.hire_date IS NULL AND lil.hire_date_raw IS NULL THEN 'warning'
        ELSE 'warning'
    END
    """


def _build_alert_codes() -> str:
    """Fixed codes — proper semantic naming."""
    return r"""
    ARRAY_REMOVE(ARRAY[
        CASE WHEN lil.driver_id_resolved IS NULL AND lil.driver_license_raw IS NOT NULL
        THEN 'missing_driver_id' END,
        CASE WHEN lil.scout_id_resolved IS NULL AND lil.scout_name_raw IS NOT NULL
        THEN 'missing_scout' END,
        CASE WHEN lil.blocks_future_payment = true AND lil.driver_id_resolved IS NULL
        THEN 'blocks_true_without_driver' END,
        CASE WHEN src.hire_date IS NULL AND lil.hire_date_raw IS NULL
        THEN 'missing_hire_date' END,
        CASE WHEN lil.supervisor_id_resolved IS NULL AND lil.supervisor_raw IS NOT NULL
        THEN 'missing_supervisor' END,
        CASE WHEN lil.attribution_status = 'attribution_manual_review'
        THEN 'manual_review' END,
        CASE WHEN lil.payment_blocking_status = 'payment_blocking_manual_review_no_driver'
        THEN 'financial_without_driver' END,
        CASE WHEN lil.payment_financial_status = 'payment_financial_ready'
             AND lil.paid_history_id IS NULL THEN 'payment_pending' END,
        CASE WHEN lil.amount_paid > 0 AND lil.paid_history_id IS NOT NULL
        THEN 'paid' END,
        CASE WHEN lil.payment_blocking_status = 'payment_blocking_ready'
             AND lil.paid_history_id IS NOT NULL THEN 'blocks_future_ok' END,
        CASE WHEN lil.attribution_status = 'attribution_ready'
             AND lil.driver_id_resolved IS NOT NULL AND lil.scout_id_resolved IS NOT NULL
        THEN 'attributed' END,
        CASE WHEN lil.final_status = 'rejected' THEN 'rejected' END,
        CASE WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NULL THEN 'duplicate_unresolved' END,
        CASE WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NOT NULL THEN 'already_registered' END,
        CASE WHEN lil.payment_blocking_status = 'payment_blocking_not_applicable_bad_status'
        THEN 'bad_status' END
    ], NULL)
    """


def _build_blocking_display() -> str:
    """Semantic blocking display label."""
    return r"""
    CASE
        WHEN lil.payment_blocking_status = 'payment_blocking_ready'
             AND lil.paid_history_id IS NOT NULL THEN 'Bloquea'
        WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NOT NULL THEN 'Ya registrado'
        WHEN lil.payment_blocking_status = 'payment_blocking_duplicate'
             AND lil.paid_history_id IS NULL THEN 'Duplicado'
        WHEN lil.payment_blocking_status = 'payment_blocking_manual_review_no_driver'
             AND lil.paid_history_id IS NOT NULL THEN 'No bloquea'
        WHEN lil.payment_blocking_status = 'payment_blocking_manual_review_no_driver'
             AND lil.paid_history_id IS NULL THEN 'Sin driver'
        WHEN lil.payment_blocking_status = 'payment_blocking_manual_review_no_scout'
        THEN 'Sin scout'
        WHEN lil.payment_financial_status = 'payment_financial_not_applicable_no_amount'
        THEN 'N/A'
        ELSE 'Pendiente'
    END
    """


# ── WHERE clause builder ──

def _build_where(params: dict, iso_year_expr: str = None, iso_week_expr: str = None) -> tuple:
    """Build WHERE clause and return (where_parts, params_dict)."""
    parts = ["lil.batch_id = :batch_id"]
    p = {"batch_id": params.get("batch_id", 20)}

    week_iso = params.get("week_iso")
    if week_iso and "-W" in str(week_iso) and iso_year_expr and iso_week_expr:
        try:
            py, pw = str(week_iso).split("-W")
            p["iso_year"] = int(py)
            p["iso_week"] = int(pw)
            parts.append(f"({iso_year_expr} = :iso_year AND {iso_week_expr} = :iso_week)")
        except (ValueError, IndexError):
            pass

    if params.get("hire_date_from"):
        p["hd_from"] = params["hire_date_from"]
        parts.append("src.hire_date::date >= :hd_from")
    if params.get("hire_date_to"):
        p["hd_to"] = params["hire_date_to"]
        parts.append("src.hire_date::date <= :hd_to")
    if params.get("scout_id"):
        p["scout_id"] = int(params["scout_id"])
        parts.append("lil.scout_id_resolved = :scout_id")
    if params.get("supervisor_id"):
        p["supervisor_id"] = int(params["supervisor_id"])
        parts.append("lil.supervisor_id_resolved = :supervisor_id")
    if params.get("origin"):
        p["origin"] = params["origin"]
        parts.append("LOWER(COALESCE(src.origen, lil.origin_raw)) = LOWER(:origin)")
    if params.get("only_manual_review"):
        parts.append("(lil.attribution_status = 'attribution_manual_review' OR lil.payment_blocking_status LIKE '%manual_review%')")
    if params.get("only_paid"):
        parts.append("lil.paid_history_id IS NOT NULL")
    if params.get("only_without_driver"):
        parts.append("lil.driver_id_resolved IS NULL")
    if params.get("only_without_scout"):
        parts.append("lil.scout_id_resolved IS NULL")
    if params.get("driver_id"):
        p["did"] = params["driver_id"]
        parts.append("lil.driver_id_resolved = :did")

    return parts, p


# ── Shared SELECT expressions ──

def _build_select_fields() -> str:
    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")
    istart = _iso_start_expr("src.hire_date")
    iend = _iso_end_expr("src.hire_date")
    label = _build_iso_label(iy, iw)

    return f"""
        lil.id AS row_id,
        'historical_import' AS source_type,
        lil.batch_id,
        lil.source_sheet,
        lil.source_row,
        {iy} AS iso_year,
        {iw} AS iso_week,
        {label} AS iso_week_label,
        TO_CHAR({istart}, 'DD Mon') AS iso_week_start,
        TO_CHAR({iend}, 'DD Mon') AS iso_week_end,
        {label} || ' \u00b7 ' || TO_CHAR({istart}, 'DD Mon') || '\u2013' || TO_CHAR({iend}, 'DD Mon') AS iso_week_label_full,
        COALESCE(src.hire_date::text, lil.hire_date_raw) AS hire_date,
        COALESCE(src.origen, lil.origin_raw) AS origin,
        lil.driver_id_resolved AS driver_id,
        lil.driver_license_raw,
        lil.driver_name_raw,
        CASE
            WHEN src.driver_apellido IS NOT NULL AND src.driver_nombre IS NOT NULL
            THEN src.driver_apellido || ', ' || src.driver_nombre
            WHEN src.driver_nombre IS NOT NULL THEN src.driver_nombre
            WHEN lil.driver_name_raw IS NOT NULL THEN lil.driver_name_raw
            ELSE 'Sin nombre'
        END AS driver_display_name,
        COALESCE(src.driver_apellido, '') AS driver_apellido,
        COALESCE(src.driver_nombre, '') AS driver_nombre,
        lil.scout_id_resolved AS scout_id,
        COALESCE(s.scout_name, lil.scout_name_raw) AS scout_name,
        lil.supervisor_id_resolved AS supervisor_id,
        lil.supervisor_raw AS supervisor_name,
        COALESCE(src.viajes_0_7, '0') AS trips_0_7_count,
        COALESCE(src.viajes_8_14, '0') AS trips_8_14_count,
        NULL::numeric AS trips_0_14_count,
        NULL::numeric AS converted_5v_7d,
        lil.attribution_status,
        lil.attribution_reason,
        CASE WHEN da.id IS NOT NULL THEN 'active' ELSE 'none' END AS assignment_status,
        lil.payment_financial_status,
        lil.payment_blocking_status,
        lil.blocks_future_payment,
        lil.paid_history_id,
        lil.amount_paid,
        lil.currency,
        ph.resolution_status,
        lil.final_status,
        {_build_blocking_display()} AS blocking_display,
        {_build_alert_level()} AS alert_level,
        {_build_alert_codes()} AS alert_codes
    """


# ═══════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════

def get_operation_filters(db: Session) -> Dict[str, Any]:
    """Return filter options + current/default week logic."""
    batch_id = 20
    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")
    cy, cw = current_iso_week()
    current_label = f"S{cw:02d}-{cy}"

    # Check if current week has data
    has_current = db.execute(text(f"""
        SELECT COUNT(*) FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        WHERE lil.batch_id = :bid AND {iy} = :cy AND {iw} = :cw
    """), {"bid": batch_id, "cy": cy, "cw": cw}).scalar()

    # Find latest week with data
    latest = db.execute(text(f"""
        SELECT {iy} AS y, {iw} AS w
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        WHERE lil.batch_id = :bid AND {iy} IS NOT NULL
        ORDER BY {iy} DESC, {iw} DESC LIMIT 1
    """), {"bid": batch_id}).fetchone()

    latest_label = None
    if latest:
        latest_label = f"S{latest[1]:02d}-{latest[0]}"

    # Default: current week if has data, else latest
    default_week = f"{cy}-W{cw:02d}" if has_current else (
        f"{latest[0]}-W{latest[1]:02d}" if latest else f"{cy}-W{cw:02d}"
    )

    # Weeks list
    weeks = db.execute(text(f"""
        SELECT DISTINCT {iy} AS y, {iw} AS w,
            'S' || LPAD({iw}::text, 2, '0') || '-' || {iy}::text AS label
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        WHERE lil.batch_id = :bid AND {iy} IS NOT NULL
        ORDER BY {iy} DESC, {iw} DESC
    """), {"bid": batch_id}).fetchall()

    scouts = db.execute(text("""
        SELECT DISTINCT s.id, s.scout_name
        FROM scout_liq_historical_import_lines lil
        JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
        WHERE lil.batch_id = :bid ORDER BY s.scout_name
    """), {"bid": batch_id}).fetchall()

    origins = db.execute(text(f"""
        SELECT DISTINCT COALESCE(src.origen, lil.origin_raw) AS origin
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        WHERE lil.batch_id = :bid AND COALESCE(src.origen, lil.origin_raw) IS NOT NULL
        ORDER BY origin
    """), {"bid": batch_id}).fetchall()

    return {
        "current_iso_week": f"{cy}-W{cw:02d}",
        "current_iso_week_label": current_label,
        "has_data_for_current_week": has_current > 0,
        "latest_iso_week_with_data": f"{latest[0]}-W{latest[1]:02d}" if latest else None,
        "latest_iso_week_with_data_label": latest_label,
        "default_week_iso": default_week,
        "weeks": [{"year": r[0], "week": r[1], "label": r[2]} for r in weeks],
        "scouts": [{"id": r[0], "name": r[1]} for r in scouts],
        "origins": [r[0] for r in origins],
        "alert_types": [
            {"value": "critical", "label": "Criticas"},
            {"value": "warning", "label": "Advertencias"},
            {"value": "ok", "label": "OK"},
        ],
    }


def get_operation_summary(db: Session, **filters) -> Dict[str, Any]:
    """Return KPIs, optionally filtered."""
    batch_id = filters.get("batch_id", 20)
    params_base = {"batch_id": batch_id, **filters}
    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")
    where_parts, p = _build_where(params_base, iy, iw)
    where = " AND ".join(where_parts)
    alert = _build_alert_level()

    def q(sql: str, extra_params: dict = None) -> Any:
        pp = {**p, **(extra_params or {})}
        return db.execute(text(sql), pp).scalar()

    total = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where}")

    with_driver = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.driver_id_resolved IS NOT NULL")

    with_scout = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.scout_id_resolved IS NOT NULL")

    manual_review = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.final_status = 'manual_review'")

    paid = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.paid_history_id IS NOT NULL")

    paid_amt = db.execute(text(f"""
        SELECT COALESCE(SUM(ph.amount_paid), 0)
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where}
    """), p).scalar()

    blocks_future = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.blocks_future_payment = true AND lil.paid_history_id IS NOT NULL")

    financial_only = q(f"SELECT COUNT(*) FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where} AND lil.paid_history_id IS NOT NULL AND lil.blocks_future_payment = false")

    critical = q(f"SELECT COUNT(*) FROM (SELECT {alert} AS al FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where}) sub WHERE sub.al = 'critical'")

    warning = q(f"SELECT COUNT(*) FROM (SELECT {alert} AS al FROM scout_liq_historical_import_lines lil LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved WHERE {where}) sub WHERE sub.al = 'warning'")

    # Weekly breakdown
    weeks_sql = f"""
        SELECT {iy} AS y, {iw} AS w,
            'S' || LPAD({iw}::text, 2, '0') || '-' || {iy}::text AS label,
            COUNT(*) AS total,
            COUNT(lil.driver_id_resolved) AS with_driver,
            COUNT(CASE WHEN lil.driver_id_resolved IS NULL THEN 1 END) AS without_driver,
            COUNT(lil.paid_history_id) AS paid_count,
            COALESCE(SUM(ph.amount_paid), 0) AS paid_amount,
            COUNT(CASE WHEN lil.blocks_future_payment = true AND lil.paid_history_id IS NOT NULL THEN 1 END) AS blocks_future,
            COUNT(CASE WHEN lil.final_status = 'manual_review' THEN 1 END) AS manual_review
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        WHERE {where}
        GROUP BY {iy}, {iw}
        ORDER BY {iy} DESC NULLS LAST, {iw} DESC NULLS LAST
    """
    weeks_rows = db.execute(text(weeks_sql), p).fetchall()

    # Scope metadata
    week_iso = filters.get("week_iso")
    scope_type = "selected_week" if week_iso else "all"
    scope_label = f"Semana {week_iso}" if week_iso else "Todas las semanas"

    cy, cw = current_iso_week()
    cur_label = f"S{cw:02d}-{cy}"

    # Latest week with data
    latest_w = db.execute(text(f"""
        SELECT {iy} AS y, {iw} AS w FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        WHERE lil.batch_id = :bid AND {iy} IS NOT NULL
        ORDER BY {iy} DESC, {iw} DESC LIMIT 1
    """), {"bid": batch_id}).fetchone()

    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "total_affiliations": total,
        "total_with_driver": with_driver or 0,
        "total_without_driver": (total or 0) - (with_driver or 0),
        "total_with_scout": with_scout or 0,
        "total_without_scout": (total or 0) - (with_scout or 0),
        "total_manual_review": manual_review or 0,
        "total_paid_history": paid or 0,
        "total_paid_amount": float(paid_amt or 0),
        "total_blocks_future": blocks_future or 0,
        "total_financial_only": financial_only or 0,
        "total_alerts_critical": critical or 0,
        "total_alerts_warning": warning or 0,
        "current_iso_week": f"{cy}-W{cw:02d}",
        "current_iso_week_label": cur_label,
        "latest_week_with_data": f"{latest_w[0]}-W{latest_w[1]:02d}" if latest_w else None,
        "latest_week_with_data_label": f"S{latest_w[1]:02d}-{latest_w[0]}" if latest_w else None,
        "by_iso_week": [
            {
                "iso_year": r[0], "iso_week": r[1], "label": r[2],
                "total": r[3], "with_driver": r[4], "without_driver": r[5],
                "paid_count": r[6], "paid_amount": float(r[7] or 0),
                "blocks_future": r[8], "manual_review": r[9],
            }
            for r in weeks_rows
        ],
    }


def get_affiliations(
    db: Session,
    week_iso: Optional[str] = None,
    hire_date_from: Optional[str] = None,
    hire_date_to: Optional[str] = None,
    scout_id: Optional[int] = None,
    supervisor_id: Optional[int] = None,
    origin: Optional[str] = None,
    alert_level: Optional[str] = None,
    only_manual_review: bool = False,
    only_paid: bool = False,
    only_without_driver: bool = False,
    only_without_scout: bool = False,
    driver_id_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    batch_id: int = 20,
) -> Dict[str, Any]:
    """Return unified affiliation grid."""

    iy = _iso_year_expr("src.hire_date")
    iw = _iso_week_expr("src.hire_date")

    params_base = {
        "batch_id": batch_id,
        "week_iso": week_iso,
        "hire_date_from": hire_date_from,
        "hire_date_to": hire_date_to,
        "scout_id": scout_id,
        "supervisor_id": supervisor_id,
        "origin": origin,
        "only_manual_review": only_manual_review,
        "only_paid": only_paid,
        "only_without_driver": only_without_driver,
        "only_without_scout": only_without_scout,
        "driver_id": driver_id_filter,
    }
    params_base = {k: v for k, v in params_base.items() if v}

    where_parts, p = _build_where(params_base, iy, iw)
    where = " AND ".join(where_parts)

    select_fields = _build_select_fields()
    alert_expr = _build_alert_level()

    # COUNT
    if alert_level:
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT {alert_expr} AS alert_level
                FROM scout_liq_historical_import_lines lil
                LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
                LEFT JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
                LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
                LEFT JOIN scout_liq_driver_assignments da ON da.driver_id = lil.driver_id_resolved AND da.status = 'active'
                WHERE {where}
            ) sub WHERE sub.alert_level = :alert_val
        """
        p["alert_val"] = alert_level
    else:
        count_sql = f"""
            SELECT COUNT(*) FROM scout_liq_historical_import_lines lil
            LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
            WHERE {where}
        """
    total = db.execute(text(count_sql), p).scalar()

    # SELECT
    base_sql = f"""
        SELECT {select_fields}
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
        LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        LEFT JOIN scout_liq_driver_assignments da ON da.driver_id = lil.driver_id_resolved AND da.status = 'active'
        WHERE {where}
        ORDER BY {iy} DESC NULLS LAST, {iw} DESC NULLS LAST,
            COALESCE(s.scout_name, lil.scout_name_raw) ASC,
            lil.driver_id_resolved ASC
    """

    if alert_level:
        select_sql = f"""
            SELECT * FROM ({base_sql}) sub
            WHERE sub.alert_level = :alert_val
            LIMIT :limit OFFSET :offset
        """
    else:
        select_sql = f"{base_sql} LIMIT :limit OFFSET :offset"

    p["limit"] = limit
    p["offset"] = offset

    rows = db.execute(text(select_sql), p).fetchall()

    items = []
    for row in rows:
        d = dict(row._mapping)
        if d.get("amount_paid"):
            d["amount_paid"] = float(d["amount_paid"])
        if d.get("converted_5v_7d"):
            d["converted_5v_7d"] = float(d["converted_5v_7d"])
        items.append(d)

    return {"total": total or 0, "limit": limit, "offset": offset, "items": items}


def get_affiliation_detail(db: Session, row_id: int) -> Dict[str, Any]:
    """Return full detail for a single affiliation."""
    row = db.execute(text(f"""
        SELECT
            lil.id AS row_id, lil.batch_id, lil.source_sheet, lil.source_row,
            lil.corte_id_raw, lil.fecha_corte_raw, lil.fecha_pago_raw, lil.estado_pago_raw,
            lil.scout_name_raw, lil.scout_id_resolved,
            lil.supervisor_raw, lil.supervisor_id_resolved, lil.scout_type_raw, lil.origin_raw,
            lil.driver_license_raw, lil.driver_id_resolved, lil.driver_name_raw, lil.hire_date_raw,
            lil.payment_scheme_raw, lil.payment_rule_raw, lil.milestone_raw, lil.trips_reported_raw,
            lil.amount_paid_raw, lil.amount_paid, lil.currency,
            lil.import_status, lil.import_reason,
            lil.attribution_status, lil.attribution_reason,
            lil.payment_status, lil.payment_reason,
            lil.payment_financial_status, lil.payment_financial_reason,
            lil.payment_blocking_status, lil.payment_blocking_reason,
            lil.blocks_future_payment, lil.final_status,
            lil.paid_history_id, lil.unique_hash,
            s.scout_name AS scout_resolved_name, s.scout_type AS scout_resolved_type, s.status AS scout_status,
            sup.scout_name AS supervisor_resolved_name,
            src.hire_date AS source_hire_date, src.license AS source_license,
            src.origen AS source_origin, src.driver_nombre, src.driver_apellido,
            src.viajes_0_7 AS trips_0_7_count, src.viajes_8_14 AS trips_8_14_count,
            ph.amount_paid AS ph_amount_paid,
            ph.blocks_future_payment AS ph_blocks_future,
            ph.resolution_status AS ph_resolution_status,
            ph.financial_record_status AS ph_financial_status,
            ph.unique_hash AS ph_unique_hash,
            ph.payment_rule AS ph_payment_rule,
            ph.status AS ph_status, ph.paid_at AS ph_paid_at,
            da.id AS assignment_id, da.status AS assignment_status,
            da.assigned_by AS assignment_assigned_by, da.source_file AS assignment_source_file,
            CASE WHEN src.driver_apellido IS NOT NULL AND src.driver_nombre IS NOT NULL
                THEN src.driver_apellido || ', ' || src.driver_nombre
                WHEN src.driver_nombre IS NOT NULL THEN src.driver_nombre
                WHEN lil.driver_name_raw IS NOT NULL THEN lil.driver_name_raw
                ELSE 'Sin nombre' END AS driver_display_name,
            {_build_blocking_display()} AS blocking_display,
            {_build_alert_level()} AS alert_level,
            {_build_alert_codes()} AS alert_codes
        FROM scout_liq_historical_import_lines lil
        LEFT JOIN {SOURCE_TABLE} src ON src.driver_id = lil.driver_id_resolved
        LEFT JOIN scout_liq_scouts s ON s.id = lil.scout_id_resolved
        LEFT JOIN scout_liq_scouts sup ON sup.id = lil.supervisor_id_resolved
        LEFT JOIN scout_liq_paid_history ph ON ph.id = lil.paid_history_id
        LEFT JOIN scout_liq_driver_assignments da ON da.driver_id = lil.driver_id_resolved AND da.status = 'active'
        WHERE lil.id = :row_id
    """), {"row_id": row_id}).fetchone()

    if not row:
        return {}

    d = dict(row._mapping)
    for k in ("amount_paid", "ph_amount_paid"):
        if d.get(k):
            d[k] = float(d[k])
    return d


def export_affiliations_csv(db: Session, filters: Dict[str, Any]) -> str:
    """Export as CSV respecting current filters."""
    result = get_affiliations(db, limit=10000, offset=0, **{k: v for k, v in filters.items() if v})
    items = result.get("items", [])
    if not items:
        return "Sin resultados"
    headers = [
        "row_id", "iso_week_label_full", "hire_date", "origin", "driver_id",
        "driver_display_name", "driver_license_raw", "scout_name", "supervisor_name",
        "trips_0_7_count", "trips_8_14_count",
        "attribution_status", "payment_financial_status", "blocking_display",
        "amount_paid", "final_status", "alert_level"
    ]
    lines = [",".join(headers)]
    for item in items:
        lines.append(",".join(str(item.get(h, "")) for h in headers))
    return "\r\n".join(lines)
