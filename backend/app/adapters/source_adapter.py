"""
Source Adapter para module_ct_cabinet_drivers.
Solo SELECT. No modifica la tabla fuente.

Fase 3: Los conteos reales de viajes se calculan en cutoff_engine via JOIN a trips_2025/trips_2026.
Los flags legacy viajes_0_7/viajes_8_14 son SOLO INFORMATIVOS.
"""

from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings


SOURCE_TABLE = settings.SOURCE_TABLE


def _parse_hire_date(value: Optional[str]) -> Optional[date]:
    if not value or not str(value).strip():
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _row_to_dict(row, col_names: List[str]) -> Dict[str, Any]:
    d = dict(zip(col_names, row))
    hire_raw = d.get("hire_date")
    hire_parsed = _parse_hire_date(hire_raw)
    trips_0_7 = d.get("trips_0_7_count")
    trips_8_14 = d.get("trips_8_14_count")
    has_counts = trips_0_7 is not None and trips_8_14 is not None
    return {
        "driver_id": d.get("driver_id"),
        "driver_nombre": d.get("driver_nombre"),
        "driver_apellido": d.get("driver_apellido"),
        "driver_placa": d.get("driver_placa"),
        "driver_phone": d.get("driver_phone"),
        "park_name": d.get("park_name"),
        "park_id": d.get("park_id"),
        "status": d.get("status"),
        "last_active_date": d.get("last_active_date"),
        "segment": d.get("segment"),
        "stage": d.get("stage"),
        "license": d.get("license"),
        "origin": d.get("origen"),
        "legacy_viajes_0_7_flag": d.get("viajes_0_7"),
        "legacy_viajes_8_14_flag": d.get("viajes_8_14"),
        "total_orders": d.get("orders"),
        "trips_0_7_count": trips_0_7,
        "trips_8_14_count": trips_8_14,
        "trips_0_14_count": (trips_0_7 or 0) + (trips_8_14 or 0) if has_counts else None,
        "conexion": d.get("conexion"),
        "hire_date_raw": hire_raw,
        "hire_date_parsed": str(hire_parsed) if hire_parsed else None,
        "source_status": (
            "invalid_hire_date" if (not hire_parsed and hire_raw)
            else "missing_hire_date" if not hire_raw
            else "ok"
        ),
        "source_quality_status": (
            "invalid_hire_date" if not hire_parsed
            else "missing_trip_counts" if not has_counts
            else "ok"
        ),
        "created_at": str(d.get("created_at")) if d.get("created_at") else None,
        "updated_at": str(d.get("updated_at")) if d.get("updated_at") else None,
    }


_COL_NAMES_CACHE = None


def _get_col_names(db: Session) -> List[str]:
    global _COL_NAMES_CACHE
    if _COL_NAMES_CACHE is None:
        rows = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :tbl ORDER BY ordinal_position"
            ),
            {"tbl": SOURCE_TABLE},
        ).fetchall()
        _COL_NAMES_CACHE = [r[0] for r in rows]
    return _COL_NAMES_CACHE


# ── Public adapter functions ──────────────────────────────────────────────

def get_source_drivers(
    db: Session,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    origin: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    col_names = _get_col_names(db)
    where_parts = ["1=1"]
    params = {}

    if hire_date_from:
        where_parts.append("hire_date::date >= :hd_from")
        params["hd_from"] = hire_date_from.isoformat()
    if hire_date_to:
        where_parts.append("hire_date::date <= :hd_to")
        params["hd_to"] = hire_date_to.isoformat()
    if origin:
        where_parts.append("LOWER(origen) = LOWER(:origin)")
        params["origin"] = origin

    where_clause = " AND ".join(where_parts)
    cols = ", ".join(col_names)

    count_sql = f"SELECT COUNT(*) FROM {SOURCE_TABLE} WHERE {where_clause}"
    total = db.execute(text(count_sql), params).scalar()

    select_sql = (
        f"SELECT {cols}, NULL::int AS trips_0_7_count, NULL::int AS trips_8_14_count "
        f"FROM {SOURCE_TABLE} "
        f"WHERE {where_clause} ORDER BY driver_id "
        f"LIMIT :limit OFFSET :offset"
    )
    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(text(select_sql), params).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "drivers": [_row_to_dict(r, col_names) for r in rows],
    }


def get_source_driver_by_id(db: Session, driver_id: str) -> Optional[Dict[str, Any]]:
    col_names = _get_col_names(db)
    cols = ", ".join(col_names)
    row = db.execute(
        text(f"SELECT {cols}, NULL::int AS trips_0_7_count, NULL::int AS trips_8_14_count "
             f"FROM {SOURCE_TABLE} WHERE driver_id = :did LIMIT 1"),
        {"did": driver_id},
    ).first()
    if not row:
        return None
    return _row_to_dict(row, col_names)


def get_unassigned_source_drivers(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    col_names = _get_col_names(db)
    cols = ", ".join(f"s.{c}" for c in col_names)
    where_clause = (
        "s.driver_id NOT IN ("
        "  SELECT a.driver_id FROM scout_liq_driver_assignments a "
        "  WHERE a.status = 'active'"
        ") "
    )
    count_sql = f"SELECT COUNT(*) FROM {SOURCE_TABLE} s WHERE {where_clause}"
    total = db.execute(text(count_sql)).scalar()

    select_sql = (
        f"SELECT {cols}, NULL::int AS trips_0_7_count, NULL::int AS trips_8_14_count "
        f"FROM {SOURCE_TABLE} s "
        f"WHERE {where_clause} ORDER BY s.driver_id "
        f"LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(text(select_sql), {"limit": limit, "offset": offset}).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "drivers": [_row_to_dict(r, col_names) for r in rows],
    }


def get_source_diagnostic_summary(db: Session) -> Dict[str, Any]:
    sql = (
        f"SELECT "
        f"  COUNT(*) AS total_rows, "
        f"  COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '') AS with_hire_date, "
        f"  COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') AS without_hire_date, "
        f"  COUNT(*) FILTER (WHERE viajes_0_7 = true) AS legacy_with_trips_0_7, "
        f"  COUNT(*) FILTER (WHERE viajes_0_7 = false) AS legacy_without_trips_0_7, "
        f"  COUNT(*) FILTER (WHERE viajes_8_14 = true) AS legacy_with_trips_8_14, "
        f"  COUNT(*) FILTER (WHERE viajes_8_14 = false) AS legacy_without_trips_8_14 "
        f"FROM {SOURCE_TABLE}"
    )
    row = db.execute(text(sql)).first()
    cols = [
        "total_rows", "with_hire_date", "without_hire_date",
        "legacy_with_trips_0_7", "legacy_without_trips_0_7",
        "legacy_with_trips_8_14", "legacy_without_trips_8_14",
    ]
    summary = dict(zip(cols, row))
    origen_rows = db.execute(
        text(f"SELECT origen, COUNT(*) FROM {SOURCE_TABLE} WHERE origen IS NOT NULL GROUP BY origen ORDER BY COUNT(*) DESC")
    ).fetchall()
    summary["by_origin"] = [{"origin": r[0], "count": r[1]} for r in origen_rows]
    assigned_count = db.execute(
        text("SELECT COUNT(DISTINCT driver_id) FROM scout_liq_driver_assignments WHERE status = 'active'")
    ).scalar()
    summary["assigned_drivers"] = assigned_count or 0
    summary["unassigned_drivers"] = summary["total_rows"] - summary["assigned_drivers"]
    return summary


def get_quality_data_contract_status(db: Session) -> Dict[str, Any]:
    can_compute = True
    errors = []
    has_2025 = False
    has_2026 = False
    try:
        db.execute(text("SELECT 1 FROM trips_2026 LIMIT 1"))
        has_2026 = True
    except Exception:
        pass
    try:
        db.execute(text("SELECT 1 FROM trips_2025 LIMIT 1"))
        has_2025 = True
    except Exception:
        pass
    if not has_2026 and not has_2025:
        can_compute = False
        errors.append("Tablas trips_2025/trips_2026 no accesibles")

    sample = None
    if can_compute:
        try:
            row = db.execute(text(
                "SELECT s.driver_id, s.hire_date, COUNT(t.conductor_id) AS cnt "
                "FROM module_ct_cabinet_drivers s "
                "LEFT JOIN trips_2026 t ON s.driver_id = t.conductor_id "
                "AND t.fecha_inicio_viaje >= s.hire_date::date "
                "AND t.fecha_inicio_viaje < s.hire_date::date + INTERVAL '7 days' "
                "AND t.condicion = 'Completado' "
                "WHERE s.hire_date IS NOT NULL AND s.hire_date != '' "
                "GROUP BY s.driver_id, s.hire_date LIMIT 1"
            )).first()
            if row:
                sample = {"driver_id": row[0], "hire_date": str(row[1]) if row[1] else None, "trips_0_7_count": row[2]}
        except Exception as e:
            errors.append(f"Sample failed: {e}")

    return {
        "status": "ok" if can_compute and not errors else "unavailable",
        "can_compute_trip_counts": can_compute,
        "trip_sources": {"trips_2025": has_2025, "trips_2026": has_2026},
        "uses_legacy_booleans_for_payment": False,
        "sample_driver_trip_count": sample,
        "errors": errors,
        "fields": {
            "trips_0_7_count": "computed via JOIN trips_2025/trips_2026",
            "trips_8_14_count": "computed via JOIN trips_2025/trips_2026",
            "trips_0_14_count": "trips_0_7_count + trips_8_14_count",
            "legacy_viajes_0_7_flag": "INFORMATIVE ONLY - DO NOT USE FOR PAYMENT",
            "legacy_viajes_8_14_flag": "INFORMATIVE ONLY - DO NOT USE FOR PAYMENT",
        },
    }


def compute_trip_counts_batch(
    db: Session,
    driver_ids: List[str],
) -> Dict[str, Dict[str, int]]:
    """Compute trips_0_7_count and trips_8_14_count for a batch of drivers."""
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    # Determine which trip tables each driver needs:
    # - If hire_date + 14d reaches into 2025, query trips_2025
    # - Always query trips_2026 (has conductor_fecha index, fast)
    need_2025 = ", ".join(
        f":did{i}" for i in range(len(driver_ids))
    ) + " AND s.hire_date::date + INTERVAL '14 days' < '2026-01-01'::date"

    sql = f"""
        SELECT s.driver_id,
            COALESCE(SUM(t.trips_0_7), 0)::int AS trips_0_7_count,
            COALESCE(SUM(t.trips_8_14), 0)::int AS trips_8_14_count
        FROM module_ct_cabinet_drivers s
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '7 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '7 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '14 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2026
            WHERE conductor_id = s.driver_id
            UNION ALL
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '7 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '7 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '14 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2025
            WHERE conductor_id = s.driver_id
              AND s.hire_date::date + INTERVAL '14 days' < '2026-01-01'::date
        ) t ON true
        WHERE s.driver_id IN ({placeholders})
          AND s.hire_date IS NOT NULL AND s.hire_date != ''
        GROUP BY s.driver_id
    """
    rows = db.execute(text(sql), params).fetchall()
    return {r[0]: {"trips_0_7_count": r[1] or 0, "trips_8_14_count": r[2] or 0} for r in rows}
