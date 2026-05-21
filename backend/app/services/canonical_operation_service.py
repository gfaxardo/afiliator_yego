"""
Canonical Operation Service

Fuente master: module_ct_cabinet_drivers (read-only).
Viajes reales: trips_2025 / trips_2026 (condicion = 'Completado').
Scout attribution: scout_liq_driver_assignments (status = 'active').
Pago: cutoff engine + historical upload como overlay.

NO usa legacy flags (viajes_0_7 / viajes_8_14) para conteo.
NO modifica tablas fuente.
NO lee HistoricalImportLine como base operativa.
"""

import time as _time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import re as _re

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.services.manual_override_service import get_applied_overrides_for_drivers

SOURCE_TABLE = settings.SOURCE_TABLE
STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '15000ms'"


def _iso_year_expr(col: str) -> str:
    return f"EXTRACT(ISOYEAR FROM {col})::int"

def _iso_week_expr(col: str) -> str:
    return f"EXTRACT(WEEK FROM {col})::int"

def _build_iso_label(iy_expr: str, iw_expr: str) -> str:
    return f"'S' || LPAD({iw_expr}::text, 2, '0') || '-' || {iy_expr}::text"

def _compute_lifecycle(trips_0_7: int, trips_8_14: int) -> str:
    trips_0_14 = trips_0_7 + trips_8_14
    if trips_0_7 == 0 and trips_0_14 == 0:
        return "no_trip"
    if trips_0_7 >= 1 and trips_0_7 < 5:
        if trips_0_14 >= 5:
            return "converted_5v14d"
        return "activated"
    if trips_0_7 >= 5:
        return "converted_5v7d"
    if trips_0_14 >= 5:
        return "converted_5v14d"
    return "no_trip"


def _parse_canonical_rule(rule_str: str):
    if not rule_str:
        return (1, 7)
    m = _re.match(r'(\d+)V(\d+)D', str(rule_str).strip(), _re.IGNORECASE)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (1, 7)


def _driver_meets_rule(trips: dict, min_count: int, window_days: int) -> bool:
    if window_days <= 7:
        return (trips.get("trips_0_7", 0) or 0) >= min_count
    if window_days <= 14:
        t7 = trips.get("trips_0_7", 0) or 0
        t14 = trips.get("trips_8_14", 0) or 0
        return (t7 + t14) >= min_count
    if window_days <= 30:
        return (trips.get("trips_0_30", 0) or 0) >= min_count
    return (trips.get("trips_0_30", 0) or 0) >= min_count


def _get_latest_iso_week(db: Session) -> Optional[str]:
    try:
        db.execute(text(STATEMENT_TIMEOUT))
        row = db.execute(text(
            "SELECT MAX(EXTRACT(ISOYEAR FROM hire_date::date)) || '-W' || "
            "LPAD(MAX(EXTRACT(WEEK FROM hire_date::date))::text, 2, '0') "
            f"FROM {SOURCE_TABLE} WHERE hire_date IS NOT NULL AND hire_date != ''"
        )).scalar()
        return row
    except Exception:
        return None
    if trips_0_7 >= 1 and trips_0_7 < 5:
        if trips_0_14 >= 5:
            return "converted_5v14d"
        return "activated"
    if trips_0_7 >= 5:
        return "converted_5v7d"
    if trips_0_14 >= 5:
        return "converted_5v14d"
    return "no_trip"


def _ensure_date_window(
    hire_date_from: Optional[date],
    hire_date_to: Optional[date],
) -> Tuple[date, date]:
    """If no date filter provided, default to last 30 days."""
    if hire_date_from is not None and hire_date_to is not None:
        return hire_date_from, hire_date_to
    today = date.today()
    if hire_date_to is None:
        hire_date_to = today
    if hire_date_from is None:
        hire_date_from = hire_date_to - timedelta(days=30)
    return hire_date_from, hire_date_to


# ═══════════════════════════════════════════════════════════════════════════
# CANONICAL OPERATION SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════

def get_canonical_operation_snapshot(
    db: Session,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    origin: Optional[str] = None,
    scout_id: Optional[int] = None,
    attribution_status: Optional[str] = None,
    payment_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    scheme_type: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = _time.perf_counter()

    # Enforce date window
    hd_from, hd_to = _ensure_date_window(hire_date_from, hire_date_to)

    # Set timeout
    db.execute(text(STATEMENT_TIMEOUT))

    # ── WHERE clause ──
    where_parts = [
        "src.hire_date IS NOT NULL",
        "src.hire_date != ''",
        "src.hire_date::date >= :hd_from",
        "src.hire_date::date <= :hd_to",
    ]
    params: Dict[str, Any] = {
        "hd_from": hd_from.isoformat(),
        "hd_to": hd_to.isoformat(),
    }

    if origin:
        where_parts.append("LOWER(src.origen) = LOWER(:origin)")
        params["origin"] = origin
    if scout_id is not None:
        where_parts.append("src.driver_id IN (SELECT da.driver_id FROM scout_liq_driver_assignments da WHERE da.scout_id = :scout_filter AND da.status = 'active')")
        params["scout_filter"] = int(scout_id)
    if attribution_status == "unassigned":
        where_parts.append("src.driver_id NOT IN (SELECT da.driver_id FROM scout_liq_driver_assignments da WHERE da.status = 'active')")

    where_clause = " AND ".join(where_parts)

    t1 = _time.perf_counter()

    # ── 1. Base drivers (LIMIT applied HERE, before lateral joins) ──
    iy_expr = _iso_year_expr("src.hire_date::date")
    iw_expr = _iso_week_expr("src.hire_date::date")
    iso_label = _build_iso_label(iy_expr, iw_expr)

    count_sql = f"SELECT COUNT(*) FROM {SOURCE_TABLE} src WHERE {where_clause}"
    total = db.execute(text(count_sql), params).scalar() or 0

    base_sql = f"""
        SELECT
            src.driver_id,
            COALESCE(src.driver_nombre, '') AS driver_nombre,
            COALESCE(src.driver_apellido, '') AS driver_apellido,
            src.license,
            src.hire_date::text AS hire_date_raw,
            src.hire_date::date AS hire_date,
            {iy_expr} AS iso_year,
            {iw_expr} AS iso_week,
            {iso_label} AS iso_week_label,
            COALESCE(src.origen, '') AS origin,
            ''::text AS country,
            src.viajes_0_7 AS legacy_viajes_0_7,
            src.viajes_8_14 AS legacy_viajes_8_14,
            src.orders AS total_orders,
            src.status AS source_driver_status,
            COALESCE(src.updated_at::text, src.created_at::text, '') AS source_updated_at
        FROM {SOURCE_TABLE} src
        WHERE {where_clause}
        ORDER BY src.hire_date::date DESC, src.driver_id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    base_rows = db.execute(text(base_sql), params).fetchall()
    t2 = _time.perf_counter()

    if not base_rows:
        return {
            "total": total, "limit": limit, "offset": offset, "items": [],
            "freshness": _freshness_snapshot(db),
            "_timing_ms": {
                "base_query": round((t2 - t1) * 1000),
                "total": round((_time.perf_counter() - t0) * 1000),
            },
        }

    driver_ids = [r[0] for r in base_rows if r[0]]

    # ── 2. Batch compute trips (only for visible drivers) ──
    trip_map = _batch_trip_counts(db, driver_ids)
    t3 = _time.perf_counter()

    # ── 3. Scout assignments ──
    scout_map = _batch_scout_assignments(db, driver_ids)

    # ── 4. Paid history overlay ──
    paid_map = _batch_paid_history(db, driver_ids)

    # ── 4b. Manual overrides ──
    override_map = get_applied_overrides_for_drivers(db, driver_ids)
    t4 = _time.perf_counter()

    # ── 5. Freshness ──
    freshness = _freshness_snapshot(db)

    # ── 6. Assemble items (first pass: identity + trips, no payment decision) ──
    items = []
    for row in base_rows:
        dd = dict(row._mapping)
        did = dd["driver_id"]

        scout_info = scout_map.get(did, {})
        trips = trip_map.get(did, {"trips_0_7": 0, "trips_8_14": 0, "trips_0_30": 0})

        trips_7d = trips.get("trips_0_7", 0) or 0
        trips_8_14 = trips.get("trips_8_14", 0) or 0
        trips_14d = trips_7d + trips_8_14
        trips_0_30 = trips.get("trips_0_30", 0) or 0
        activated = trips_7d >= 1
        conv_7d = trips_7d >= 5
        conv_14d = trips_14d >= 5
        lifecycle = _compute_lifecycle(trips_7d, trips_8_14)

        attr_status = scout_info.get("attribution_status", "unassigned")
        scout_name = scout_info.get("scout_name", "")
        scout_id_resolved = scout_info.get("scout_id")
        supervisor_name = scout_info.get("supervisor_name", "")

        driver_name = ""
        apellido = (dd.get("driver_apellido") or "").strip()
        nombre = (dd.get("driver_nombre") or "").strip()
        if apellido and nombre:
            driver_name = f"{apellido}, {nombre}"
        elif nombre:
            driver_name = nombre

        items.append({
            "driver_id": did,
            "driver_name": driver_name,
            "license": dd.get("license"),
            "hire_date": str(dd.get("hire_date")) if dd.get("hire_date") else dd.get("hire_date_raw"),
            "iso_week": f"{dd.get('iso_year')}-W{dd.get('iso_week'):02d}" if dd.get("iso_year") and dd.get("iso_week") else None,
            "iso_week_label": dd.get("iso_week_label"),
            "origin": dd.get("origin"),
            "city": "",
            "country": dd.get("country"),
            "scout_id": scout_id_resolved,
            "scout_name": scout_name,
            "supervisor_name": supervisor_name,
            "attribution_status": attr_status,
            "trips_7d": trips_7d,
            "trips_14d": trips_14d,
            "trips_0_30": trips_0_30,
            "activated_flag": activated,
            "converted_5v7d": conv_7d,
            "converted_5v14d": conv_14d,
            "driver_lifecycle_status": lifecycle,
            "legacy_viajes_0_7": dd.get("legacy_viajes_0_7"),
            "legacy_viajes_8_14": dd.get("legacy_viajes_8_14"),
            "total_orders": dd.get("total_orders"),
            "source_driver_status": dd.get("source_driver_status"),
            "source_updated_at": dd.get("source_updated_at"),
            # Payment placeholders
            "payment_status": "not_payable",
            "payment_origin": "none",
            "payment_rule_label": "",
            "payment_evidence_label": "",
            "payment_trace_status": "ok",
            "payment_trace_warning": None,
            "payment_basis_label": "",
            "amount": None,
            "paid_history_id": None,
            "reason": "ok",
            # Explanation fields
            "counts_as_activated_base": False,
            "counts_as_quality_5v7d": False,
            "counts_for_payment": False,
            "scout_activated_base": 0,
            "scout_quality_5v7d": 0,
            "scout_conversion_rate_5v7d": 0.0,
            "scout_tier_amount": 0.0,
            "scout_tier_threshold": 0.0,
            "payment_formula_label": "",
        })

    # ── 7. Compute scout group metrics + payment decision (second pass) ──

    # ── Resolve multi-scheme rules if scheme_type provided ──
    resolved_scheme = None
    if scheme_type:
        from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort
        latest_week = _get_latest_iso_week(db)
        if latest_week:
            try:
                resolved_scheme = resolve_payment_scheme_for_cohort(db, latest_week, scheme_type)
            except ValueError:
                resolved_scheme = None

    if resolved_scheme:
        vol_min, vol_days = _parse_canonical_rule(resolved_scheme.get("volume_rule", "1V7D"))
        qual_min, qual_days = _parse_canonical_rule(resolved_scheme.get("quality_rule", "5V7D"))
        pays_on_rule = resolved_scheme.get("pays_on_rule", "") or "ACTIVATED_BASE"
        payout_formula_type = resolved_scheme.get("payout_formula_type", "ACTIVATED_X_TIER")
        min_volume = resolved_scheme.get("min_volume_count", resolved_scheme.get("min_activated", 8))
        tiers_list = [
            {"min_conversion_rate": t["min_conversion_rate"], "payment_per_converted_driver": t["payout_amount"], "currency": resolved_scheme.get("currency", "PEN")}
            for t in resolved_scheme.get("tiers", [])
        ]
    else:
        vol_min, vol_days = 1, 7
        qual_min, qual_days = 5, 7
        pays_on_rule = "ACTIVATED_BASE"
        payout_formula_type = "ACTIVATED_X_TIER"
        min_volume = 8
        tiers_list = []

    # Group by scout
    scout_groups: Dict[int, Dict[str, Any]] = {}
    for it in items:
        sid = it["scout_id"] or 0
        if sid not in scout_groups:
            scout_groups[sid] = {"activated_count": 0, "quality_5v7d_count": 0, "items": []}
        if it["activated_flag"]:
            scout_groups[sid]["activated_count"] += 1
        if it["converted_5v7d"]:
            scout_groups[sid]["quality_5v7d_count"] += 1
        scout_groups[sid]["items"].append(it)

    if not resolved_scheme:
        # Legacy scheme path (when no scheme_type provided)
        schemes = db.execute(text(
            "SELECT id, scheme_name, origin, min_affiliations FROM scout_liq_conversion_schemes WHERE active = true"
        )).fetchall()
        tiers_rows = db.execute(text(
            "SELECT scheme_id, min_conversion_rate, payment_per_converted_driver, currency FROM scout_liq_conversion_tiers WHERE active = true ORDER BY scheme_id, min_conversion_rate"
        )).fetchall()

        scheme_tiers: Dict[int, list] = {}
        for trow in tiers_rows:
            sid = trow[0]
            if sid not in scheme_tiers:
                scheme_tiers[sid] = []
            scheme_tiers[sid].append({
                "min_conversion_rate": float(trow[1]),
                "payment_per_converted_driver": float(trow[2]),
                "currency": trow[3],
            })

        scheme_map: Dict[int, dict] = {}
        for srow in schemes:
            scheme_map[srow[0]] = {
                "id": srow[0], "scheme_name": srow[1], "origin": srow[2], "min_affiliations": srow[3] or 0,
            }

        default_scheme = scheme_map.get(1, {"id": 1, "scheme_name": "Default", "origin": None, "min_affiliations": 8})
        default_tiers = scheme_tiers.get(1, [{"min_conversion_rate": 0.10, "payment_per_converted_driver": 10.0, "currency": "PEN"}])

    # Apply payment rules per scout group
    for sid, group in scout_groups.items():
        if sid == 0:
            for it in group["items"]:
                it["payment_status"] = "not_payable"
                it["reason"] = "no_scout"
                it["payment_trace_status"] = "blocked_unassigned"
                it["payment_trace_warning"] = "Sin scout asignado"
                it["payment_basis_label"] = "no_scout"
            continue

        for it in group["items"]:
            overrides = override_map.get(it["driver_id"], [])
            for ov in overrides:
                if ov["override_type"] == "force_exclude":
                    it["payment_status"] = "not_payable"
                    it["reason"] = "manual_exclude"
                    it["payment_trace_status"] = "blocked_manual_exclude"
                    it["payment_trace_warning"] = "Excluido manualmente"
                    it["payment_basis_label"] = "manual_exclude"
                elif ov["override_type"] == "force_pay":
                    it["payment_status"] = "paid"
                    it["reason"] = "manual_force_pay"
                    it["payment_origin"] = "manual_override"
                    it["amount"] = ov["amount"]
                    it["paid_history_id"] = ov.get("paid_history_id")
                    it["payment_rule_label"] = "Pago manual autorizado"
                    it["payment_evidence_label"] = "manual_override"
                    it["payment_trace_status"] = "paid_manual_override"
                    it["payment_trace_warning"] = "Pago manual autorizado — no salio de la regla automatica"
                    it["payment_basis_label"] = "manual_force_pay"

            payments_list = paid_map.get(it["driver_id"], [])
            if payments_list:
                latest = payments_list[0]
                if latest.get("blocks_future_payment", True):
                    it["payment_status"] = "paid"
                    it["reason"] = "already_paid"
                    it["payment_origin"] = latest.get("import_source", "historical_upload")
                    it["amount"] = float(latest["amount_paid"]) if latest.get("amount_paid") else None
                    it["paid_history_id"] = latest.get("id")
                    it["payment_rule_label"] = latest.get("payment_rule") or ""
                    it["payment_evidence_label"] = "paid_" + (latest.get("import_source") or "historical")
                    it["payment_trace_status"] = "paid_confirmed"

        # Compute scout metrics (excluding already-paid drivers from base)
        tripmap_lookup = trip_map
        non_paid_volume = [
            it for it in group["items"]
            if _driver_meets_rule(tripmap_lookup.get(it["driver_id"], {}), vol_min, vol_days)
            and it["payment_status"] != "paid"
        ]
        non_paid_quality = [
            it for it in group["items"]
            if _driver_meets_rule(tripmap_lookup.get(it["driver_id"], {}), qual_min, qual_days)
            and it["payment_status"] != "paid"
        ]

        activated_base = len(non_paid_volume)
        quality_5v7d = len(non_paid_quality)
        conversion_rate = (quality_5v7d / activated_base) if activated_base > 0 else 0.0

        if resolved_scheme:
            tiers = tiers_list
            min_aff = min_volume
        else:
            scheme = default_scheme
            tiers = default_tiers
            for sch in scheme_map.values():
                if sch.get("origin") and any(it["origin"] == sch["origin"] for it in group["items"] if it["origin"]):
                    scheme = sch
                    tiers = scheme_tiers.get(sch["id"], default_tiers)
                    break
            min_aff = scheme["min_affiliations"]

        min_met = activated_base >= min_aff

        tier_reached = None
        tier_amount = 0.0
        tier_threshold = 0.0
        for t in sorted(tiers, key=lambda x: x["min_conversion_rate"]):
            if conversion_rate >= t["min_conversion_rate"]:
                tier_reached = t
                tier_amount = t["payment_per_converted_driver"]
                tier_threshold = t["min_conversion_rate"]

        pay_label = "calidad" if pays_on_rule == "QUALITY_HIT" else "activados"
        pay_count = quality_5v7d if pays_on_rule == "QUALITY_HIT" else activated_base

        for it in group["items"]:
            driver_meets_vol = _driver_meets_rule(tripmap_lookup.get(it["driver_id"], {}), vol_min, vol_days)
            driver_meets_qual = _driver_meets_rule(tripmap_lookup.get(it["driver_id"], {}), qual_min, qual_days)
            it["counts_as_activated_base"] = driver_meets_vol
            it["counts_as_quality_5v7d"] = driver_meets_qual
            it["scout_activated_base"] = activated_base
            it["scout_quality_5v7d"] = quality_5v7d
            it["scout_conversion_rate_5v7d"] = round(conversion_rate, 4)
            it["scout_tier_amount"] = tier_amount
            it["scout_tier_threshold"] = tier_threshold

            if it["payment_status"] == "paid":
                it["counts_for_payment"] = False
                continue

            driver_payable = driver_meets_qual if pays_on_rule == "QUALITY_HIT" else driver_meets_vol

            if not driver_payable:
                it["payment_status"] = "not_payable"
                it["reason"] = "no_activation"
                it["payment_trace_status"] = "no_activation"
                it["payment_basis_label"] = "below_threshold"
                it["counts_for_payment"] = False
                continue

            if not min_met:
                it["payment_status"] = "not_payable"
                it["reason"] = "min_activated_not_reached"
                it["payment_trace_status"] = "blocked_min_activated"
                it["payment_trace_warning"] = f"Minimo {min_aff} volumen requerido, scout tiene {activated_base}"
                it["payment_basis_label"] = "scout_below_min"
                it["payment_formula_label"] = f"scout_volume={activated_base} < min={min_aff}"
                it["counts_for_payment"] = False
                continue

            if tier_reached is None:
                it["payment_status"] = "not_payable"
                it["reason"] = "tier_not_reached"
                it["payment_trace_status"] = "blocked_no_tier"
                it["payment_trace_warning"] = f"Conversion {conversion_rate:.2%} no alcanza ningun tier"
                it["payment_basis_label"] = "tier_not_reached"
                it["payment_formula_label"] = f"conversion={conversion_rate:.2%} < min_tier={tiers[0]['min_conversion_rate'] if tiers else 0}"
                it["counts_for_payment"] = False
                continue

            it["payment_status"] = "payable"
            it["reason"] = "ok"
            it["payment_origin"] = "cutoff"
            it["amount"] = tier_amount
            it["payment_rule_label"] = f"Scout alcanza tier {tier_threshold:.0%} -> S/{tier_amount:.0f}"
            it["payment_evidence_label"] = "scout_tier_reached"
            it["payment_trace_status"] = "payable_scout_tier"
            it["payment_basis_label"] = pay_label
            it["payment_formula_label"] = f"tier={tier_amount} x {pay_label}={pay_count} = S/{pay_count * tier_amount:.0f}"
            it["counts_for_payment"] = True

    t4a = _time.perf_counter()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
        "freshness": freshness,
        "_timing_ms": {
            "base_query": round((t2 - t1) * 1000),
            "trips_query": round((t3 - t2) * 1000),
            "scout_paid_query": round((t4 - t3) * 1000),
            "payment_logic": round((t4a - t4) * 1000),
            "total": round((t4a - t0) * 1000),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# DIAGNOSTICO LIVIANO (sin calcular trips)
# ═══════════════════════════════════════════════════════════════════════════

def get_operation_diagnostic(
    db: Session,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    hd_from, hd_to = _ensure_date_window(hire_date_from, hire_date_to)

    params: Dict[str, Any] = {
        "hd_from": hd_from.isoformat(),
        "hd_to": hd_to.isoformat(),
    }

    where_parts = [
        "src.hire_date IS NOT NULL",
        "src.hire_date != ''",
        "src.hire_date::date >= :hd_from",
        "src.hire_date::date <= :hd_to",
    ]
    if origin:
        where_parts.append("LOWER(src.origen) = LOWER(:origin)")
        params["origin"] = origin
    where_clause = " AND ".join(where_parts)

    # Base counts
    base = db.execute(text(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE driver_id IS NULL OR driver_id = '') AS null_invalid
        FROM {SOURCE_TABLE} src WHERE {where_clause}
    """), params).fetchone()
    total_source = base[0] or 0
    null_invalid = base[1] or 0

    # Scout counts
    with_scout = db.execute(text(f"""
        SELECT COUNT(DISTINCT src.driver_id)
        FROM {SOURCE_TABLE} src
        INNER JOIN scout_liq_driver_assignments da ON src.driver_id = da.driver_id AND da.status = 'active'
        WHERE {where_clause}
    """), params).scalar() or 0

    without_scout = db.execute(text(f"""
        SELECT COUNT(DISTINCT src.driver_id)
        FROM {SOURCE_TABLE} src
        LEFT JOIN scout_liq_driver_assignments da ON src.driver_id = da.driver_id AND da.status = 'active'
        WHERE {where_clause} AND da.id IS NULL
    """), params).scalar() or 0

    conflicts = db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT da.driver_id FROM scout_liq_driver_assignments da
            JOIN {SOURCE_TABLE} src ON src.driver_id = da.driver_id
            WHERE da.status = 'active' AND {where_clause}
            GROUP BY da.driver_id HAVING COUNT(*) > 1
        ) sub
    """), params).scalar() or 0

    # Freshness (global, no filter)
    frow = db.execute(text(f"""
        SELECT
            MAX(hire_date::date) AS mhd,
            CURRENT_DATE - MAX(hire_date::date) AS lag_days,
            MAX(updated_at::text) AS mup,
            MAX(created_at::text) AS mcr
        FROM {SOURCE_TABLE}
    """)).fetchone()

    max_hd = str(frow[0]) if frow and frow[0] else None
    lag = frow[1] if frow else None
    fs_status = "ok" if lag is not None and lag <= 7 else ("warning" if lag is not None and lag <= 14 else "stale")

    # Paid counts
    paid_total = db.execute(text(f"""
        SELECT COUNT(DISTINCT ph.driver_id)
        FROM scout_liq_paid_history ph
        JOIN {SOURCE_TABLE} src ON src.driver_id = ph.driver_id
        WHERE {where_clause} AND ph.blocks_future_payment = true
    """), params).scalar() or 0

    paid_cutoff = db.execute(text(f"""
        SELECT COUNT(DISTINCT ph.driver_id)
        FROM scout_liq_paid_history ph
        JOIN {SOURCE_TABLE} src ON src.driver_id = ph.driver_id
        WHERE {where_clause} AND ph.import_source = 'cutoff_engine' AND ph.blocks_future_payment = true
    """), params).scalar() or 0

    paid_hist = db.execute(text(f"""
        SELECT COUNT(DISTINCT ph.driver_id)
        FROM scout_liq_paid_history ph
        JOIN {SOURCE_TABLE} src ON src.driver_id = ph.driver_id
        WHERE {where_clause} AND ph.import_source != 'cutoff_engine' AND ph.blocks_future_payment = true
    """), params).scalar() or 0

    elapsed = round((_time.perf_counter() - t0) * 1000)

    return {
        "source_table": SOURCE_TABLE,
        "filters_applied": {"hire_date_from": str(hd_from), "hire_date_to": str(hd_to), "origin": origin},
        "base_counts": {
            "total_source_drivers": total_source,
            "drivers_with_scout": with_scout,
            "drivers_without_scout": without_scout,
            "null_invalid_driver_id": null_invalid,
        },
        "trip_metrics": {"activated_1plus_7d": 0, "converted_5v7d": 0, "converted_5v14d": 0,
                         "_note": "trip_metrics skipped in lightweight diagnostic. Use /operation/canonical"},
        "payment_metrics": {
            "paid_history_total": paid_total,
            "paid_cutoff_engine": paid_cutoff,
            "paid_historical_upload": paid_hist,
            "not_payable_with_activation": 0,
            "_note": "not_payable skipped. Use /operation/canonical",
        },
        "freshness": {
            "source_max_hire_date": max_hd,
            "source_max_updated_at": frow[2] if frow else None,
            "source_max_created_at": frow[3] if frow else None,
            "data_lag_days": lag,
            "freshness_status": fs_status,
        },
        "attribution_quality": {"assignment_conflicts": conflicts},
        "_timing_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BATCH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _batch_scout_assignments(db: Session, driver_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text(STATEMENT_TIMEOUT))
    rows = db.execute(text(f"""
        SELECT
            da.driver_id, da.scout_id,
            s.scout_name, s.scout_type, s.country, s.city,
            sup.scout_name AS supervisor_name,
            CASE WHEN conflict.cnt > 1 THEN 'conflict' ELSE 'assigned' END AS attribution_status
        FROM scout_liq_driver_assignments da
        JOIN scout_liq_scouts s ON s.id = da.scout_id AND da.status = 'active'
        LEFT JOIN scout_liq_scouts sup ON sup.id = s.supervisor_id
        LEFT JOIN (
            SELECT driver_id, COUNT(*) AS cnt FROM scout_liq_driver_assignments
            WHERE status = 'active' AND driver_id IN ({placeholders})
            GROUP BY driver_id
        ) conflict ON conflict.driver_id = da.driver_id
        WHERE da.driver_id IN ({placeholders}) AND da.status = 'active'
    """), params).fetchall()
    result = {}
    for r in rows:
        did = r[0]
        if did not in result:
            result[did] = {
                "driver_id": did, "scout_id": r[1], "scout_name": r[2],
                "scout_type": r[3], "country": r[4], "city": r[5],
                "supervisor_name": r[6], "attribution_status": r[7],
            }
    for did in driver_ids:
        if did and did not in result:
            result[did] = {"driver_id": did, "scout_id": None, "scout_name": None, "attribution_status": "unassigned"}
    return result


def _batch_trip_counts(db: Session, driver_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text(STATEMENT_TIMEOUT))
    sql = f"""
        SELECT s.driver_id,
            COALESCE(SUM(t.trips_0_7), 0)::int AS trips_0_7_count,
            COALESCE(SUM(t.trips_8_14), 0)::int AS trips_8_14_count,
            COALESCE(SUM(t.trips_0_30), 0)::int AS trips_0_30_count
        FROM {SOURCE_TABLE} s
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
                ) AS trips_8_14,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '30 days'
                      AND condicion = 'Completado'
                ) AS trips_0_30
            FROM trips_2026 WHERE conductor_id = s.driver_id
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
                ) AS trips_8_14,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '30 days'
                      AND condicion = 'Completado'
                ) AS trips_0_30
            FROM trips_2025 WHERE conductor_id = s.driver_id
              AND s.hire_date::date + INTERVAL '30 days' < '2026-01-01'::date
        ) t ON true
        WHERE s.driver_id IN ({placeholders}) AND s.hire_date IS NOT NULL AND s.hire_date != ''
        GROUP BY s.driver_id
    """
    rows = db.execute(text(sql), params).fetchall()
    return {r[0]: {"trips_0_7": r[1] or 0, "trips_8_14": r[2] or 0, "trips_0_30": r[3] or 0} for r in rows}


def _batch_paid_history(db: Session, driver_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    db.execute(text(STATEMENT_TIMEOUT))
    rows = db.execute(text(f"""
        SELECT ph.id, ph.driver_id, ph.scout_id, ph.amount_paid, ph.currency,
               ph.paid_at, ph.import_source, ph.payment_rule, ph.payment_component,
               ph.payment_scheme_name, ph.cutoff_window_from, ph.cutoff_window_to,
               ph.blocks_future_payment, ph.status, ph.reason
        FROM scout_liq_paid_history ph
        WHERE ph.driver_id IN ({placeholders})
        ORDER BY ph.paid_at DESC
    """), params).fetchall()
    result: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        did = r[1]
        if did not in result:
            result[did] = []
        result[did].append({
            "id": r[0], "driver_id": did, "scout_id": r[2],
            "amount_paid": float(r[3]) if r[3] else None,
            "currency": r[4], "paid_at": str(r[5]) if r[5] else None,
            "import_source": r[6], "payment_rule": r[7],
            "payment_component": r[8], "payment_scheme_name": r[9],
            "cutoff_window_from": str(r[10]) if r[10] else None,
            "cutoff_window_to": str(r[11]) if r[11] else None,
            "blocks_future_payment": r[12], "status": r[13], "reason": r[14],
        })
    return result


def _freshness_snapshot(db: Session) -> Dict[str, Any]:
    db.execute(text(STATEMENT_TIMEOUT))
    row = db.execute(text(f"""
        SELECT
            MAX(hire_date::date) AS source_max_hire_date,
            CURRENT_DATE - MAX(hire_date::date) AS data_lag_days,
            MAX(updated_at::text) AS source_max_updated_at,
            MAX(created_at::text) AS source_max_created_at,
            COUNT(*) AS total_source_rows,
            COUNT(*) FILTER (WHERE driver_id IS NULL OR driver_id = '') AS null_invalid_driver_id_count,
            COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') AS null_hire_date_count
        FROM {SOURCE_TABLE}
    """)).fetchone()
    if not row:
        return {"freshness_status": "unavailable"}
    lag = row[1]
    if lag is not None:
        fs_status = "ok" if lag <= 7 else ("warning" if lag <= 14 else "stale")
    else:
        fs_status = "unknown"
    return {
        "source_max_hire_date": str(row[0]) if row[0] else None,
        "data_lag_days": lag,
        "source_max_updated_at": row[2],
        "source_max_created_at": row[3],
        "total_source_rows": row[4],
        "null_invalid_driver_id_count": row[5],
        "null_hire_date_count": row[6],
        "freshness_status": fs_status,
    }
