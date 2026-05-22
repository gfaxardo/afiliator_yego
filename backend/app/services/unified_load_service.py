"""
Unified Load Service — Plantilla unica plana por licencia.

El usuario sube CSV/XLSX con columnas simples:
  licencia, scout, supervisor, pagado, monto_pagado, fecha_pago, observacion
  (+ opcionales: driver_id, nombre_conductor, origen, tipo_scout, motivo_pago, cohorte_iso)

El sistema DEDUCE la accion desde los campos.
NO se usa action por fila.
NO se obliga al usuario a indicar assign/reassign/paid.
"""

import csv as _csv
import io
import re
import uuid
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.scout_liq import (
    Scout, DriverAssignment, PaidHistory,
    HistoricalAttribution, ManualOverride,
)

_preview_store: Dict[str, dict] = {}
_preview_store_lock = threading.Lock()
_PREVIEW_TTL_SECONDS = 3600

SOURCE_TABLE = settings.SOURCE_TABLE

COHORT_RE = re.compile(r"^\d{4}-W\d{2}$")

REQUIRED_COLS = [
    "licencia", "scout", "supervisor",
]

OPTIONAL_COLS = [
    "pagado", "monto_pagado", "fecha_pago", "observacion",
    "driver_id", "nombre_conductor", "origen",
    "tipo_scout", "motivo_pago", "cohorte_iso",
]

ALL_COLS = REQUIRED_COLS + OPTIONAL_COLS


def _normalize_header(h: str) -> str:
    h = h.strip().lower()
    h = h.replace(" ", "_").replace("-", "_")
    mapping = {
        "license": "licencia", "brevete": "licencia",
        "scout_name": "scout", "scout_nombre": "scout",
        "supervisor_name": "supervisor", "supervisor_nombre": "supervisor",
        "pagado": "pagado", "estado": "pagado", "estado_pago": "pagado",
        "pago": "pagado",
        "monto": "monto_pagado", "amount": "monto_pagado", "amount_paid": "monto_pagado",
        "monto_pagado": "monto_pagado",
        "fecha": "fecha_pago", "fecha_de_pago": "fecha_pago", "payment_date": "fecha_pago",
        "fecha_pago": "fecha_pago",
        "observacion": "observacion", "observaciones": "observacion",
        "notas": "observacion", "notes": "observacion",
        "driver_id": "driver_id", "conductor_id": "driver_id",
        "nombre": "nombre_conductor", "conductor": "nombre_conductor",
        "driver_name": "nombre_conductor", "nombre_conductor": "nombre_conductor",
        "origen": "origen", "origin": "origen",
        "tipo": "tipo_scout", "tipo_de_scout": "tipo_scout", "scout_type": "tipo_scout",
        "motivo": "motivo_pago", "motivo_de_pago": "motivo_pago",
        "payment_reason": "motivo_pago",
        "cohorte": "cohorte_iso", "cohort": "cohorte_iso",
        "cohorte_iso": "cohorte_iso", "iso_week": "cohorte_iso",
        "semana": "cohorte_iso",
    }
    return mapping.get(h, h)


def _parse_amount(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).replace(",", "").replace("S/", "").replace("$", "").replace("s/", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_pagado(val: Any) -> bool:
    s = str(val).strip().upper() if val is not None else ""
    return s in ("SI", "SÍ", "YES", "TRUE", "1", "PAGADO", "OK", "S")


def _parse_date(val: Any) -> Optional[date]:
    if not val or str(val).strip() == "":
        return None
    s = str(val).strip()

    # Try standard formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
                "%Y/%m/%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Try ISO
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        pass

    # Try Excel serial date (days since 1899-12-30)
    try:
        n = float(s)
        if 1 <= n <= 100000:
            excel_epoch = date(1899, 12, 30)
            return excel_epoch + timedelta(days=int(n))
    except (ValueError, TypeError):
        pass

    return None


def _detect_delimiter(first_line: str) -> str:
    """Auto-detect CSV delimiter from first line."""
    candidates = [",", ";", "\t"]
    counts = {}
    for d in candidates:
        counts[d] = first_line.count(d)
    best = max(candidates, key=lambda d: counts.get(d, 0))
    if counts.get(best, 0) >= 1:
        return best
    return ","


def _suggest_column_mapping(detected: List[str]) -> Dict[str, str]:
    """
    Heuristically map detected column names to expected required columns.
    Returns {detected_col: expected_col} suggestions.
    """
    def _norm(s: str) -> str:
        return s.lower().replace(" ", "").replace("_", "").replace("-", "")

    suggestions: Dict[str, str] = {}
    norm_detected = {_norm(d): d for d in detected}

    for req in REQUIRED_COLS:
        req_norm = _norm(req)
        # Exact match after normalization
        if req_norm in norm_detected:
            suggestions[norm_detected[req_norm]] = req
            continue
        # Substring / fuzzy match
        for nd, orig in norm_detected.items():
            if orig in suggestions:
                continue
            if req_norm in nd or nd in req_norm:
                suggestions[orig] = req
                break
            # Common abbreviations
            if req == "licencia" and nd in ("lic", "brevete", "license", "placa"):
                suggestions[orig] = req
                break
            if req == "monto_pagado" and nd in ("monto", "amount", "pago", "amountpaid", "montopagado"):
                suggestions[orig] = req
                break
            if req == "fecha_pago" and nd in ("fecha", "date", "fechapago", "paymentdate", "fechadepago"):
                suggestions[orig] = req
                break
            if req == "pagado" and nd in ("estado", "status", "pagado", "pago"):
                suggestions[orig] = req
                break
            if req == "observacion" and nd in ("obs", "notas", "notes", "observaciones", "comentario", "comentarios"):
                suggestions[orig] = req
                break
            if req == "scout" and nd in ("scoutname", "scout_nombre", "nombrescout", "scoutnombre"):
                suggestions[orig] = req
                break
            if req == "supervisor" and nd in ("supervisorname", "supervisor_nombre", "nombresupervisor", "supervisor_nombre", "supername"):
                suggestions[orig] = req
                break

    return suggestions


def _parse_rows_from_csv(content: str) -> Tuple[List[dict], List[str], dict]:
    """
    Parse CSV content into list of dicts.
    Returns (rows, errors, metadata).
    If required columns are missing, returns structural_error metadata
    and NO rows (structural error takes precedence over row errors).
    """
    errors = []
    metadata: dict = {
        "delimiter_detected": ",",
        "columns_detected": [],
        "rows_detected": 0,
        "structural_error": False,
        "expected_columns": REQUIRED_COLS,
        "suggested_mapping": {},
    }

    try:
        # Strip BOM
        if content.startswith("\ufeff"):
            content = content[1:]

        lines = content.split("\n")
        data_lines = [l for l in lines if l.strip()]
        if len(data_lines) < 2:
            errors.append("CSV sin lineas de datos (necesita header + al menos 1 fila)")
            return [], errors, metadata

        # Auto-detect delimiter from first non-empty line
        delimiter = _detect_delimiter(data_lines[0])
        metadata["delimiter_detected"] = delimiter if delimiter != "," else ","

        # Parse headers
        raw_headers = [h.strip() for h in data_lines[0].split(delimiter)]
        # Strip any remaining BOM from first header
        if raw_headers and raw_headers[0].startswith("\ufeff"):
            raw_headers[0] = raw_headers[0][1:]
        metadata["columns_detected"] = raw_headers

        headers = {h: _normalize_header(h) for h in raw_headers}

        # ── Structural error: missing required columns ──
        normalized_found = set(headers.values())
        required_set = set(REQUIRED_COLS)
        missing_required = required_set - normalized_found

        if missing_required:
            suggestions = _suggest_column_mapping(raw_headers)
            metadata["structural_error"] = True
            metadata["suggested_mapping"] = suggestions
            errors.append(
                f"Faltan columnas requeridas: {', '.join(sorted(missing_required))}."
            )
            # Return NO rows — structural error takes precedence
            return [], errors, metadata

        # Parse data rows
        rows = []
        for i, line in enumerate(data_lines[1:]):
            vals = line.split(delimiter)
            row = {}
            for j, val in enumerate(vals):
                if j < len(raw_headers):
                    mapped = headers.get(raw_headers[j], raw_headers[j])
                    row[mapped] = (val or "").strip()
            row["_source_row"] = i + 2
            rows.append(row)

        metadata["rows_detected"] = len(rows)

        return rows, errors, metadata
    except Exception as e:
        errors.append(f"Error al parsear CSV: {e}")
        return [], errors, metadata


def _parse_rows_from_xlsx(content: bytes) -> Tuple[List[dict], List[str]]:
    """Parse XLSX content into list of dicts. Uses first sheet."""
    errors = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if not ws:
            errors.append("XLSX sin hoja activa")
            return [], errors

        rows_iter = ws.iter_rows(min_row=1, values_only=True)
        raw_headers = [str(c).strip() if c else "" for c in next(rows_iter, [])]
        headers = {h: _normalize_header(h) for h in raw_headers}

        rows = []
        for i, vals in enumerate(rows_iter):
            row = {}
            for j, val in enumerate(vals):
                if j < len(raw_headers):
                    mapped = headers.get(raw_headers[j], raw_headers[j])
                    row[mapped] = str(val).strip() if val is not None else ""
            row["_source_row"] = i + 2
            rows.append(row)

        wb.close()
        return rows, errors
    except Exception as e:
        errors.append(f"Error al parsear XLSX: {e}")
        return [], errors


def _validate_row(row: dict) -> List[str]:
    errors = []
    for col in REQUIRED_COLS:
        if col not in row or not row[col]:
            errors.append(f"Falta campo requerido: {col}")
    return errors


def unified_preview(
    db: Session,
    rows: List[dict],
) -> Dict[str, Any]:
    """
    Preview: analiza filas, detecta duplicados intra-batch,
    construye apply_plan deterministico. NO escribe en DB.
    """
    total_rows = len(rows)
    valid_rows = 0
    error_rows = 0
    duplicate_rows = 0
    drivers_found = 0
    drivers_not_found = 0
    scouts_to_create = 0
    supervisors_to_create = 0
    assignments_to_create = 0
    assignments_to_change = 0
    payments_to_create = 0
    already_paid = 0
    amount_mismatch = 0
    lines: List[dict] = []
    apply_plan: List[dict] = []

    scout_cache = _build_scout_cache(db)
    all_licenses = list(set(r.get("licencia", "") for r in rows if r.get("licencia")))
    all_driver_ids = list(set(r.get("driver_id", "") for r in rows if r.get("driver_id")))
    license_to_driver = _build_license_cache(db, all_licenses)
    existing_drivers = _build_driver_id_cache(db, all_driver_ids)
    active_assignments = _build_active_assignment_cache(db)
    blocking_paid = _build_blocking_paid_cache(db)

    # ── Pass 1: resolve all drivers first ──
    resolved_drivers: Dict[int, str] = {}  # row_index -> driver_id
    for i, row in enumerate(rows):
        did = row.get("driver_id", ""); lic = row.get("licencia", "")
        if did and did in existing_drivers: resolved_drivers[i] = did
        elif lic and lic in license_to_driver: resolved_drivers[i] = license_to_driver[lic]
        else: resolved_drivers[i] = ""

    # ── Pass 2: detect intra-batch duplicates ──
    # For each driver, keep only the LAST row index
    last_seen: Dict[str, int] = {}
    duplicate_indices: set = set()
    for i in range(len(rows)):
        drv = resolved_drivers.get(i, "")
        if drv: last_seen[drv] = i
    for i in range(len(rows)):
        drv = resolved_drivers.get(i, "")
        if drv and last_seen.get(drv, -1) != i:
            duplicate_indices.add(i)

    # ── Pass 3: process rows ──
    for i, row in enumerate(rows):
        row_errors = _validate_row(row)
        licencia = row.get("licencia", "")
        scout_name = row.get("scout", "")
        resolved_driver = resolved_drivers.get(i, "")

        if row_errors:
            error_rows += 1
            lines.append({"source_row": row.get("_source_row", i + 2), "licencia": licencia,
                "scout": scout_name, "supervisor": row.get("supervisor", ""),
                "pagado": row.get("pagado", ""), "monto_pagado": 0,
                "fecha_pago": row.get("fecha_pago", ""),
                "observacion": row.get("observacion", ""),
                "nombre_conductor": row.get("nombre_conductor", ""),
                "origen": row.get("origen", ""),
                "tipo_scout": row.get("tipo_scout", ""),
                "motivo_pago": row.get("motivo_pago", ""),
                "status": "error", "errors": row_errors, "warnings": [],
                "deduced_actions": [], "driver_id_resolved": None, "scout_id_resolved": None})
            continue

        # Intra-batch duplicate check
        if i in duplicate_indices:
            duplicate_rows += 1
            winner_idx = last_seen.get(resolved_driver, i)
            winner_row_nr = rows[winner_idx].get("_source_row", winner_idx + 2)
            lines.append({"source_row": row.get("_source_row", i + 2), "licencia": licencia,
                "scout": scout_name, "supervisor": row.get("supervisor", ""),
                "pagado": row.get("pagado", ""), "monto_pagado": 0,
                "fecha_pago": row.get("fecha_pago", ""),
                "observacion": row.get("observacion", ""),
                "nombre_conductor": row.get("nombre_conductor", ""),
                "origen": row.get("origen", ""),
                "tipo_scout": row.get("tipo_scout", ""),
                "motivo_pago": row.get("motivo_pago", ""),
                "status": "skipped_duplicate",
                "errors": [], "warnings": [f"Driver duplicado en archivo. Fila ganadora: {winner_row_nr}"],
                "deduced_actions": ["skipped_duplicate"],
                "driver_id_resolved": resolved_driver,
                "scout_id_resolved": None,
                "duplicate_of_row": winner_row_nr})
            continue

        line_warnings = []
        deduced_actions = []
        line_errors = []

        driver_found = bool(resolved_driver)
        if driver_found: drivers_found += 1
        else:
            drivers_not_found += 1
            line_errors.append("Licencia no encontrada en fuente")

        # Scout
        scout_id = _resolve_scout_cached(scout_cache, scout_name)
        supervisor_name = row.get("supervisor", "")
        if not scout_id:
            scouts_to_create += 1
            line_warnings.append(f"Scout '{scout_name}' no existe")
            deduced_actions.append("create_scout")

        # Supervisor
        sup_create = False
        if supervisor_name and scout_id:
            cs = _get_cached_supervisor(scout_cache, scout_id)
            if cs and cs.lower() != supervisor_name.lower(): sup_create = True
        elif supervisor_name and not scout_id: sup_create = True
        if sup_create:
            supervisors_to_create += 1
            line_warnings.append(f"Supervisor '{supervisor_name}' asignado a '{scout_name}'")

        # Assignment
        if driver_found:
            cur = active_assignments.get(resolved_driver)
            if cur and cur != scout_id:
                assignments_to_change += 1
                line_warnings.append(f"Reasignando de scout {cur} a '{scout_name}'")
                deduced_actions.append("reassign_scout")
            elif not cur:
                assignments_to_create += 1
                deduced_actions.append("assign_scout")

        # Payment
        pagado = _parse_pagado(row.get("pagado", "NO"))
        monto = _parse_amount(row.get("monto_pagado", "0"))
        if not driver_found:
            line_errors.append("Driver no encontrado — no se puede pagar")
            deduced_actions.append("driver_not_found")
        elif pagado and monto > 0:
            if resolved_driver in blocking_paid: already_paid += 1; line_warnings.append("Ya pagado"); deduced_actions.append("already_paid")
            else: payments_to_create += 1; deduced_actions.append("create_payment")
        else: deduced_actions.append("attribution_only")

        if line_errors: error_rows += 1
        else: valid_rows += 1

        line_data = {"source_row": row.get("_source_row", i + 2), "licencia": licencia,
            "scout": scout_name, "supervisor": supervisor_name,
            "pagado": row.get("pagado", ""), "monto_pagado": monto,
            "fecha_pago": row.get("fecha_pago", ""),
            "observacion": row.get("observacion", ""),
            "nombre_conductor": row.get("nombre_conductor", ""),
            "origen": row.get("origen", ""),
            "tipo_scout": row.get("tipo_scout", ""),
            "motivo_pago": row.get("motivo_pago", ""),
            "status": "error" if line_errors else ("warning" if line_warnings else "ok"),
            "errors": line_errors, "warnings": line_warnings,
            "deduced_actions": deduced_actions,
            "driver_id_resolved": resolved_driver, "scout_id_resolved": scout_id}
        lines.append(line_data)

        # Build apply_plan entry for valid rows
        if not line_errors and driver_found:
            plan_entry = {
                "source_row": row.get("_source_row", i + 2),
                "driver_id": resolved_driver,
                "licencia": licencia,
                "scout_name": scout_name,
                "scout_id": scout_id,
                "supervisor": supervisor_name,
                "create_scout": scout_id is None,
                "create_assignment": "assign_scout" in deduced_actions or "reassign_scout" in deduced_actions,
                "reassign_from": active_assignments.get(resolved_driver) if "reassign_scout" in deduced_actions else None,
                "create_payment": "create_payment" in deduced_actions,
                "amount": monto if "create_payment" in deduced_actions else 0,
                "fecha_pago": row.get("fecha_pago", ""),
                "observacion": row.get("observacion", ""),
                "origen": row.get("origen", ""),
                "tipo_scout": row.get("tipo_scout", ""),
                "motivo_pago": row.get("motivo_pago", ""),
                "nombre_conductor": row.get("nombre_conductor", ""),
            }
            apply_plan.append(plan_entry)

    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "error_rows": error_rows,
        "duplicate_rows": duplicate_rows,
        "drivers_found": drivers_found,
        "drivers_not_found": drivers_not_found,
        "scouts_to_create": scouts_to_create,
        "supervisors_to_create": supervisors_to_create,
        "assignments_to_create": assignments_to_create,
        "assignments_to_change": assignments_to_change,
        "payments_to_create": payments_to_create,
        "already_paid": already_paid,
        "amount_mismatch": amount_mismatch,
        "warnings": [],
        "lines": lines,
        "apply_plan": apply_plan,
        "parse_metadata": {},
    }


def _upsert_driver_assignment(db: Session, driver_id: str, scout_id: int,
                               applied_by: str, licencia: Optional[str],
                               origen: Optional[str], observacion: Optional[str],
                               source_row: Optional[int]) -> str:
    """
    Idempotent assignment upsert.
    Returns action: 'created', 'reactivated', 'no_change', 'duplicate_existing'
    """
    existing = db.query(DriverAssignment).filter(
        DriverAssignment.driver_id == driver_id,
        DriverAssignment.scout_id == scout_id,
    ).first()

    if existing:
        if existing.status == "active":
            return "no_change"
        existing.status = "active"
        existing.updated_at = datetime.now()
        existing.assigned_by = applied_by or "unified_load"
        existing.source_file = "unified_load.csv"
        if source_row: existing.source_row = source_row
        if licencia: existing.license_raw = licencia
        if origen: existing.origin = origen
        if observacion: existing.notes = observacion
        return "reactivated"

    db.add(DriverAssignment(
        driver_id=driver_id, scout_id=scout_id,
        origin=origen or None, status="active",
        assigned_by=applied_by or "unified_load",
        license_raw=licencia or None,
        notes=observacion or None,
        source_file="unified_load.csv",
        source_row=source_row,
    ))
    return "created"


def unified_apply(
    db: Session,
    rows: List[dict],
    applied_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply idempotente: usa savepoints por fila, upsert, captura UniqueViolation."""
    applied = 0
    skipped = 0
    errors_count = 0
    no_change_count = 0
    conflict_count = 0
    already_paid_count = 0
    not_found_count = 0
    details: List[dict] = []

    scout_cache = _build_scout_cache(db)
    all_licenses = list(set(r.get("licencia", "") for r in rows if r.get("licencia")))
    license_to_driver = _build_license_cache(db, all_licenses)
    all_driver_ids = list(set(r.get("driver_id", "") for r in rows if r.get("driver_id")))
    existing_drivers = _build_driver_id_cache(db, all_driver_ids)
    active_assignments = _build_active_assignment_cache(db)
    blocking_paid = _build_blocking_paid_cache(db)

    seen: set = set()
    deduped = []
    for row in reversed(rows):
        did = row.get("driver_id", ""); lic = row.get("licencia", "")
        key = did if (did and did in existing_drivers) else (license_to_driver.get(lic) if (lic and lic in license_to_driver) else (lic or did or str(row.get("_source_row", ""))))
        if key and key not in seen:
            seen.add(key); deduped.append(row)
    deduped.reverse()
    if deduped: rows = deduped

    any_applied = False

    for i, row in enumerate(rows):
        if "_source_row" not in row:
            row["_source_row"] = i + 2
        source_row = row.get("_source_row", i + 2)

        row_errors = _validate_row(row)
        if row_errors:
            skipped += 1
            details.append({
                "source_row": source_row, "status": "skipped",
                "action": "validation_error", "saved": False,
                "message": "; ".join(row_errors),
            })
            continue

        sp = db.begin_nested()
        try:
            driver_id = row.get("driver_id", "")
            licencia = row.get("licencia", "")
            if driver_id and driver_id in existing_drivers:
                resolved_driver = driver_id
            elif licencia and licencia in license_to_driver:
                resolved_driver = license_to_driver[licencia]
            else:
                resolved_driver = None
            if not resolved_driver:
                not_found_count += 1
                sp.rollback()
                details.append({
                    "source_row": source_row, "status": "skipped",
                    "action": "driver_not_found", "saved": False,
                    "message": "Driver no encontrado",
                    "driver_id": None, "scout_id": None,
                })
                continue

            what_happened = []
            scout_name = row.get("scout", "")
            scout_id = _resolve_scout_cached(scout_cache, scout_name)
            if not scout_id:
                scout = Scout(scout_name=scout_name, scout_type=row.get("tipo_scout") or None,
                              supervisor_name_raw=row.get("supervisor") or None,
                              status="active", imported_from="unified_load")
                db.add(scout); db.flush()
                scout_id = scout.id
                scout_cache[scout_name.lower()] = (scout_id, row.get("supervisor") or "")
                what_happened.append(f"Scout '{scout_name}' creado")

            assign_action = "no_change"
            if scout_id:
                current = active_assignments.get(resolved_driver)
                if current and current != scout_id:
                    old = db.query(DriverAssignment).filter(
                        DriverAssignment.driver_id == resolved_driver,
                        DriverAssignment.scout_id == current,
                        DriverAssignment.status == "active").first()
                    if old:
                        old.status = "inactive"; old.updated_at = datetime.now()
                    what_happened.append(f"Reasignado de scout {current}")
                    assign_action = _upsert_driver_assignment(
                        db, resolved_driver, scout_id,
                        applied_by=applied_by or "unified_load",
                        licencia=licencia or None,
                        origen=row.get("origen") or None,
                        observacion=row.get("observacion") or None,
                        source_row=source_row,
                    )
                    if assign_action in ("created", "reactivated"):
                        what_happened.append(f"Asignado a '{scout_name}'")
                        active_assignments[resolved_driver] = scout_id
                    elif assign_action == "no_change":
                        what_happened.append(f"Ya asignado a '{scout_name}'")
                elif not current:
                    assign_action = _upsert_driver_assignment(
                        db, resolved_driver, scout_id,
                        applied_by=applied_by or "unified_load",
                        licencia=licencia or None,
                        origen=row.get("origen") or None,
                        observacion=row.get("observacion") or None,
                        source_row=source_row,
                    )
                    if assign_action in ("created", "reactivated"):
                        what_happened.append(f"Asignado a '{scout_name}'")
                        active_assignments[resolved_driver] = scout_id
                    elif assign_action == "no_change":
                        what_happened.append(f"Ya asignado a '{scout_name}'")
                else:
                    what_happened.append(f"Ya asignado a '{scout_name}'")

            pagado = _parse_pagado(row.get("pagado", "NO"))
            monto = _parse_amount(row.get("monto_pagado", "0"))
            payment_created = False
            if pagado and monto > 0:
                if resolved_driver in blocking_paid:
                    already_paid_count += 1
                    what_happened.append("Ya pagado")
                else:
                    db.add(PaidHistory(scout_id=scout_id, driver_id=resolved_driver,
                        amount_paid=monto, currency="PEN",
                        paid_at=_parse_date(row.get("fecha_pago", "")) or date.today(),
                        import_source="unified_load", payment_component="unified_load",
                        driver_license_raw=licencia or None, scout_name_raw=scout_name,
                        reason=row.get("motivo_pago") or row.get("observacion") or None,
                        status="paid", blocks_future_payment=True,
                        source_file="unified_load.csv", source_row=source_row))
                    what_happened.append(f"Pago S/{monto:.0f}")
                    payment_created = True

            if not what_happened:
                what_happened.append("Sin cambios")

            sp.commit()
            any_applied = True
            applied += 1

            line_action = "no_change"
            line_status = "ok"
            if assign_action == "created":
                line_action = "created_assignment"
            elif assign_action == "reactivated":
                line_action = "reactivated_assignment"
            elif payment_created:
                line_action = "created_payment_history"
            elif pagado and resolved_driver in blocking_paid:
                line_action = "already_paid"
                line_status = "warning"
            elif assign_action == "no_change":
                line_action = "no_change"

            details.append({
                "source_row": source_row, "status": line_status,
                "action": line_action, "saved": True,
                "message": " | ".join(what_happened),
                "driver_id": resolved_driver, "scout_id": scout_id,
                "scout_name": scout_name,
                "payment_created": payment_created,
                "assignment_created": assign_action in ("created", "reactivated"),
                "what_happened": what_happened,
            })

        except IntegrityError as e:
            sp.rollback()
            err_str = str(e).lower()
            if "unique" in err_str and "uq_driver_scout_active" in err_str:
                no_change_count += 1
                details.append({
                    "source_row": source_row, "status": "ok",
                    "action": "duplicate_existing", "saved": False,
                    "message": "Ya existia asignacion activa",
                    "driver_id": resolved_driver if 'resolved_driver' in dir() else None,
                    "scout_id": scout_id if 'scout_id' in dir() else None,
                })
            else:
                errors_count += 1
                details.append({
                    "source_row": source_row, "status": "error",
                    "action": "error", "saved": False,
                    "message": str(e),
                })
        except Exception as e:
            sp.rollback()
            errors_count += 1
            details.append({
                "source_row": source_row, "status": "error",
                "action": "error", "saved": False,
                "message": str(e),
            })

    if any_applied:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return {
                "applied": 0, "skipped": len(rows), "errors": 1,
                "details": [{"source_row": 0, "status": "fatal_error",
                             "action": "error", "saved": False, "message": str(e)}],
            }

    return {
        "applied": applied, "skipped": skipped, "errors": errors_count,
        "no_change": no_change_count, "conflicts": conflict_count,
        "already_paid": already_paid_count, "not_found": not_found_count,
        "details": details,
    }


def unified_apply_stream(db: Session, plan: List[dict], applied_by: Optional[str] = None):
    """
    Generator idempotente: ejecuta apply_plan con savepoint por fila,
    upsert de asignaciones, captura de UniqueViolation.
    """
    applied = 0; skipped = 0; errors_count = 0; total = len(plan)
    no_change_count = 0; conflict_count = 0; already_paid_count = 0
    not_found_count = 0
    scout_cache = _build_scout_cache(db)
    active_assignments = _build_active_assignment_cache(db)
    blocking_paid = _build_blocking_paid_cache(db)

    commit_ok = True
    commit_error = None

    for i, entry in enumerate(plan):
        source_row = entry.get("source_row", 0)
        sp = db.begin_nested()
        try:
            resolved_driver = entry["driver_id"]
            scout_name = entry["scout_name"]
            scout_id = entry.get("scout_id")
            what = []

            if entry.get("create_scout") or not scout_id:
                s = Scout(scout_name=scout_name, scout_type=entry.get("tipo_scout") or None,
                          supervisor_name_raw=entry.get("supervisor") or None,
                          status="active", imported_from="unified_load")
                db.add(s); db.flush(); scout_id = s.id
                scout_cache[scout_name.lower()] = (scout_id, entry.get("supervisor") or "")
                what.append(f"Scout '{scout_name}' creado")

            assign_action = "no_change"
            if entry.get("create_assignment") and scout_id:
                cur = active_assignments.get(resolved_driver)
                reassign_from = entry.get("reassign_from")
                if cur and cur != scout_id:
                    old = db.query(DriverAssignment).filter(
                        DriverAssignment.driver_id == resolved_driver,
                        DriverAssignment.scout_id == cur,
                        DriverAssignment.status == "active").first()
                    if old:
                        old.status = "inactive"; old.updated_at = datetime.now()
                    what.append(f"Reasignado de scout {cur}")
                if cur != scout_id:
                    assign_action = _upsert_driver_assignment(
                        db, resolved_driver, scout_id,
                        applied_by=applied_by or "unified_load",
                        licencia=entry.get("licencia") or None,
                        origen=entry.get("origen") or None,
                        observacion=entry.get("observacion") or None,
                        source_row=source_row,
                    )
                    if assign_action in ("created", "reactivated"):
                        what.append(f"Asignado a '{scout_name}'")
                        active_assignments[resolved_driver] = scout_id
                    elif assign_action == "no_change":
                        what.append(f"Ya asignado a '{scout_name}'")
                else:
                    what.append(f"Ya asignado a '{scout_name}'")

            payment_created = False
            if entry.get("create_payment") and entry.get("amount", 0) > 0:
                if resolved_driver in blocking_paid:
                    already_paid_count += 1
                    what.append("Ya pagado")
                else:
                    db.add(PaidHistory(scout_id=scout_id, driver_id=resolved_driver,
                        amount_paid=entry["amount"], currency="PEN",
                        paid_at=_parse_date(entry.get("fecha_pago", "")) or date.today(),
                        import_source="unified_load", payment_component="unified_load",
                        driver_license_raw=entry.get("licencia") or None,
                        scout_name_raw=scout_name,
                        reason=entry.get("motivo_pago") or entry.get("observacion") or None,
                        status="paid", blocks_future_payment=True,
                        source_file="unified_load.csv", source_row=source_row))
                    what.append(f"Pago S/{entry['amount']:.0f}")
                    payment_created = True

            if not what:
                what.append("Sin cambios")

            sp.commit()
            applied += 1

            line_action = "no_change"
            line_status = "ok"
            if assign_action == "created":
                line_action = "created_assignment"
            elif assign_action == "reactivated":
                line_action = "reactivated_assignment"
            elif payment_created:
                line_action = "created_payment_history"
            elif entry.get("create_payment") and resolved_driver in blocking_paid:
                line_action = "already_paid"
                line_status = "warning"

            yield {
                "type": "line", "index": i, "total": total,
                "source_row": source_row,
                "licencia": entry.get("licencia", ""), "scout": scout_name,
                "action": line_action, "status": line_status,
                "saved": True, "message": " | ".join(what),
                "driver_id": resolved_driver,
                "what_happened": what, "applied": applied, "skipped": skipped,
            }

        except IntegrityError as e:
            sp.rollback()
            err_str = str(e).lower()
            if "unique" in err_str and "uq_driver_scout_active" in err_str:
                no_change_count += 1
                yield {
                    "type": "line", "index": i, "total": total,
                    "source_row": source_row,
                    "action": "duplicate_existing", "status": "ok",
                    "saved": False, "message": "Ya existia asignacion activa",
                    "applied": applied, "skipped": skipped,
                }
            else:
                errors_count += 1
                yield {
                    "type": "line", "index": i, "total": total,
                    "source_row": source_row,
                    "action": "error", "status": "error",
                    "saved": False, "message": str(e),
                    "applied": applied, "skipped": skipped,
                }
        except Exception as e:
            sp.rollback()
            errors_count += 1
            yield {
                "type": "line", "index": i, "total": total,
                "source_row": source_row,
                "action": "error", "status": "error",
                "saved": False, "message": str(e),
                "applied": applied, "skipped": skipped,
            }

    if applied > 0:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            commit_ok = False
            commit_error = str(e)

    yield {
        "type": "summary",
        "applied": applied, "skipped": skipped,
        "errors": errors_count,
        "no_change": no_change_count,
        "conflicts": conflict_count,
        "already_paid": already_paid_count,
        "not_found": not_found_count,
        "commit_ok": commit_ok, "commit_error": commit_error,
        "done": True,
    }


def unified_preview_stream(db: Session, rows: List[dict]):
    """
    Generator: ejecuta unified_preview internamente y
    hace yield de cada linea + summary final.
    """
    result = unified_preview(db, rows)
    total = result["total_rows"]

    for i, line in enumerate(result["lines"]):
        yield {
            "type": "line",
            "index": i, "total": total,
            "source_row": line.get("source_row", i + 2),
            "licencia": line.get("licencia", ""),
            "scout": line.get("scout", ""),
            "supervisor": line.get("supervisor", ""),
            "pagado": line.get("pagado", ""),
            "monto_pagado": line.get("monto_pagado", ""),
            "fecha_pago": line.get("fecha_pago", ""),
            "observacion": line.get("observacion", ""),
            "nombre_conductor": line.get("nombre_conductor", ""),
            "origen": line.get("origen", ""),
            "tipo_scout": line.get("tipo_scout", ""),
            "motivo_pago": line.get("motivo_pago", ""),
            "status": line.get("status", "ok"),
            "errors": line.get("errors", []),
            "warnings": line.get("warnings", []),
            "deduced_actions": line.get("deduced_actions", []),
            "driver_id_resolved": line.get("driver_id_resolved"),
            "scout_id_resolved": line.get("scout_id_resolved"),
            "duplicate_of_row": line.get("duplicate_of_row"),
            "valid_rows": result["valid_rows"],
            "error_rows": result["error_rows"],
        }

    yield {
        "type": "summary",
        "total_rows": result["total_rows"],
        "valid_rows": result["valid_rows"],
        "error_rows": result["error_rows"],
        "duplicate_rows": result["duplicate_rows"],
        "drivers_found": result["drivers_found"],
        "drivers_not_found": result["drivers_not_found"],
        "scouts_to_create": result["scouts_to_create"],
        "supervisors_to_create": result["supervisors_to_create"],
        "assignments_to_create": result["assignments_to_create"],
        "assignments_to_change": result["assignments_to_change"],
        "payments_to_create": result["payments_to_create"],
        "already_paid": result["already_paid"],
        "amount_mismatch": 0,
        "apply_plan": result["apply_plan"],
        "done": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CACHE BUILDERS (reused from historical_import_service patterns)
# ═══════════════════════════════════════════════════════════════════════════

def _build_scout_cache(db: Session) -> Dict[str, tuple]:
    """Returns {normalized_name: (scout_id, supervisor_name_raw)}"""
    scouts = db.query(Scout).filter(Scout.status == "active").all()
    cache = {}
    for s in scouts:
        name = (s.scout_name or "").strip().lower()
        if name:
            cache[name] = (s.id, s.supervisor_name_raw or "")
    return cache


def _resolve_scout_cached(cache: Dict[str, tuple], name_raw: Optional[str]) -> Optional[int]:
    if not name_raw:
        return None
    name = name_raw.strip().lower()
    if name in cache:
        return cache[name][0]
    for cname, (cid, _) in cache.items():
        if name in cname or cname in name:
            return cid
    return None


def _get_cached_supervisor(cache: Dict[str, tuple], scout_id: Optional[int]) -> str:
    """Get supervisor name for a scout_id from cache."""
    if not scout_id:
        return ""
    for (_name, (sid, sup)) in cache.items():
        if sid == scout_id:
            return sup or ""
    return ""


def _build_license_cache(db: Session, licenses: List[str]) -> Dict[str, str]:
    if not licenses:
        return {}
    placeholders = ", ".join(f":lic{i}" for i in range(len(licenses)))
    params = {f"lic{i}": lic for i, lic in enumerate(licenses)}
    rows = db.execute(text(
        f"SELECT license, driver_id FROM {SOURCE_TABLE} "
        f"WHERE license IN ({placeholders}) AND license IS NOT NULL AND license != ''"
    ), params).fetchall()
    return {r[0]: r[1] for r in rows if r[0] and r[1]}


def _build_driver_id_cache(db: Session, driver_ids: List[str]) -> set:
    if not driver_ids:
        return set()
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    rows = db.execute(text(
        f"SELECT driver_id FROM {SOURCE_TABLE} WHERE driver_id IN ({placeholders})"
    ), params).fetchall()
    return {r[0] for r in rows}


def _build_active_assignment_cache(db: Session) -> Dict[str, int]:
    assignments = db.query(DriverAssignment).filter(
        DriverAssignment.status == "active"
    ).all()
    return {a.driver_id: a.scout_id for a in assignments if a.driver_id}


def _build_blocking_paid_cache(db: Session) -> set:
    rows = db.execute(text(
        "SELECT driver_id FROM scout_liq_paid_history "
        "WHERE blocks_future_payment = true AND status = 'paid'"
    )).fetchall()
    return {r[0] for r in rows if r[0]}


def _store_preview(data: dict) -> str:
    preview_id = uuid.uuid4().hex[:12]
    with _preview_store_lock:
        _preview_store[preview_id] = {
            "data": data,
            "created_at": datetime.now(),
        }
    return preview_id


def _get_preview(preview_id: str) -> Optional[dict]:
    with _preview_store_lock:
        entry = _preview_store.get(preview_id)
        if not entry:
            return None
        age = (datetime.now() - entry["created_at"]).total_seconds()
        if age > _PREVIEW_TTL_SECONDS:
            del _preview_store[preview_id]
            return None
        return entry["data"]


def generate_preview_audit_csv(db: Session, rows: List[dict]) -> str:
    result = unified_preview(db, rows)
    preview_id = _store_preview(result)

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([
        "source_row", "licencia", "scout", "supervisor", "pagado",
        "monto_pagado", "fecha_pago", "status", "deduced_actions",
        "errors", "warnings", "driver_id_resolved", "scout_id_resolved",
        "preview_id",
    ])
    for line in result.get("lines", []):
        w.writerow([
            line.get("source_row", ""),
            line.get("licencia", ""),
            line.get("scout", ""),
            line.get("supervisor", ""),
            line.get("pagado", ""),
            line.get("monto_pagado", ""),
            line.get("fecha_pago", ""),
            line.get("status", ""),
            " | ".join(line.get("deduced_actions", [])),
            "; ".join(line.get("errors", [])),
            "; ".join(line.get("warnings", [])),
            line.get("driver_id_resolved", ""),
            line.get("scout_id_resolved", ""),
            preview_id,
        ])

    # Append summary rows
    w.writerow([])
    w.writerow(["=== RESUMEN ==="])
    w.writerow(["total_rows", result.get("total_rows", 0)])
    w.writerow(["valid_rows", result.get("valid_rows", 0)])
    w.writerow(["error_rows", result.get("error_rows", 0)])
    w.writerow(["duplicate_rows", result.get("duplicate_rows", 0)])
    w.writerow(["drivers_found", result.get("drivers_found", 0)])
    w.writerow(["drivers_not_found", result.get("drivers_not_found", 0)])
    w.writerow(["scouts_to_create", result.get("scouts_to_create", 0)])
    w.writerow(["assignments_to_create", result.get("assignments_to_create", 0)])
    w.writerow(["assignments_to_change", result.get("assignments_to_change", 0)])
    w.writerow(["payments_to_create", result.get("payments_to_create", 0)])
    w.writerow(["already_paid", result.get("already_paid", 0)])
    w.writerow(["preview_id", preview_id])

    return buf.getvalue()


def generate_apply_audit_csv(preview_lines: List[dict], apply_lines: List[dict]) -> str:
    apply_by_row: Dict[int, dict] = {}
    for al in apply_lines:
        sr = al.get("source_row", 0)
        apply_by_row[sr] = al

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([
        "source_row", "licencia", "scout", "supervisor", "pagado",
        "monto_pagado", "fecha_pago", "preview_status", "preview_actions",
        "apply_action", "apply_status", "apply_saved", "apply_message",
        "what_happened", "driver_id_resolved",
    ])

    for pl in preview_lines:
        sr = pl.get("source_row", "")
        apply = apply_by_row.get(sr, {})
        w.writerow([
            sr,
            pl.get("licencia", ""),
            pl.get("scout", ""),
            pl.get("supervisor", ""),
            pl.get("pagado", ""),
            pl.get("monto_pagado", ""),
            pl.get("fecha_pago", ""),
            pl.get("status", ""),
            " | ".join(pl.get("deduced_actions", [])),
            apply.get("action", ""),
            apply.get("status", ""),
            apply.get("saved", ""),
            apply.get("message", ""),
            " | ".join(apply.get("what_happened", [])),
            pl.get("driver_id_resolved", ""),
        ])

    return buf.getvalue()


def generate_full_audit_csv(
    preview_lines: List[dict],
    apply_lines: List[dict],
    file_name: str = "",
) -> str:
    """
    Genera un CSV de auditoria COMPLETA con TODAS las filas del input original.
    Ninguna fila se omite. Incluye todas las columnas originales + columnas de auditoria.
    El resumen va en archivo separado (generate_summary_csv).
    """
    apply_by_row: Dict[int, dict] = {}
    for al in apply_lines:
        sr = al.get("source_row") or al.get("row", 0)
        apply_by_row[int(sr) if sr else 0] = al

    buf = io.StringIO()
    w = _csv.writer(buf)

    # BOM para compatibilidad Excel
    w.writerow([
        # Originales
        "source_row",
        "licencia",
        "scout",
        "supervisor",
        "pagado",
        "monto_pagado",
        "fecha_pago",
        "observacion",
        "driver_id",
        "nombre_conductor",
        "origen",
        "tipo_scout",
        "motivo_pago",
        "cohorte_iso",
        # Auditoria
        "row_hash",
        "audit_status",
        "action",
        "saved",
        "applied",
        "rejected",
        "conflict",
        "ignored",
        "already_paid",
        "not_found",
        "error_code",
        "error_message",
        "what_happened",
        "rejection_reason",
        "existing_scout_id",
        "existing_scout_name",
        "matched_driver_id",
        "matched_driver_name",
        "matched_license",
        "matched_phone",
        "assignment_id",
        "payment_id",
        "source_file",
        "import_batch_id",
        "processed_at",
    ])

    for pl in preview_lines:
        sr = pl.get("source_row", "")
        apply = apply_by_row.get(int(sr) if sr else 0, {})

        preview_status = pl.get("status", "")
        preview_actions = pl.get("deduced_actions", [])
        preview_errors = pl.get("errors", [])
        preview_warnings = pl.get("warnings", [])

        apply_action = apply.get("action", "")
        apply_status = apply.get("status", "")
        apply_saved = apply.get("saved", False)
        apply_message = apply.get("message", "")
        apply_what = apply.get("what_happened", [])

        audit_status = "ok"
        action = apply_action or "not_processed"
        rejected = False
        conflict_flag = False
        ignored_flag = False
        already_paid_flag = False
        not_found_flag = False
        error_code = ""
        error_message = ""
        rejection_reason = ""
        what_happened = " | ".join(apply_what) if apply_what else ""

        if preview_status == "error" and "driver_not_found" in preview_actions:
            audit_status = "rejected"
            action = "driver_not_found"
            not_found_flag = True
            if not rejection_reason:
                rejection_reason = "; ".join(preview_errors)
        elif preview_status == "error":
            audit_status = "rejected"
            action = "validation_error"
            rejected = True
            rejection_reason = "; ".join(preview_errors)
            error_message = rejection_reason
        elif preview_status == "skipped_duplicate":
            audit_status = "ignored"
            action = "skipped_duplicate"
            ignored_flag = True
            if not rejection_reason:
                rejection_reason = "; ".join(preview_warnings)
        elif preview_status == "warning" and "already_paid" in preview_actions:
            audit_status = "ok"
            action = "already_paid"
            already_paid_flag = True
            what_happened = "Pago ya registrado — fila omitida"
        elif not apply:
            audit_status = "ignored"
            action = preview_actions[0] if preview_actions else "not_processed"
            ignored_flag = True
            if not rejection_reason:
                rejection_reason = "; ".join(preview_warnings + preview_errors) or "Fila no procesada"
        elif apply_action == "duplicate_existing":
            audit_status = "ok"
            action = "no_change"
            what_happened = "Ya existia asignacion activa"
        elif apply_action in ("error",):
            audit_status = "rejected"
            action = "error"
            rejected = True
            rejection_reason = apply_message
            error_message = apply_message
        elif apply_action in ("driver_not_found", "scout_not_found"):
            audit_status = "rejected"
            not_found_flag = True
            rejection_reason = apply_message
        elif apply_action == "already_paid":
            already_paid_flag = True
        elif apply_action == "conflict_existing_active_scout":
            audit_status = "conflict"
            conflict_flag = True
            rejection_reason = apply_message

        if not what_happened:
            if action == "not_processed":
                what_happened = "Fila no procesada"
            elif action == "no_change":
                what_happened = "Sin cambios"
            elif action == "already_paid":
                what_happened = "Pago ya registrado"
            elif not_found_flag:
                what_happened = "Driver no encontrado"
            elif ignored_flag:
                what_happened = "Fila ignorada: " + rejection_reason
            elif rejected:
                what_happened = "Fila rechazada: " + rejection_reason

        is_applied = apply_saved and audit_status == "ok" and action not in (
            "not_processed", "no_change", "skipped_duplicate"
        )

        row_hash_raw = f"{pl.get('licencia','')}|{pl.get('scout','')}|{pl.get('supervisor','')}|{pl.get('monto_pagado','')}"
        row_hash = ""
        try:
            import hashlib
            row_hash = hashlib.md5(row_hash_raw.encode()).hexdigest()[:12]
        except Exception:
            pass

        w.writerow([
            sr,
            pl.get("licencia", ""),
            pl.get("scout", ""),
            pl.get("supervisor", ""),
            pl.get("pagado", ""),
            pl.get("monto_pagado", ""),
            pl.get("fecha_pago", ""),
            pl.get("observacion", ""),
            pl.get("driver_id_resolved", ""),
            pl.get("nombre_conductor", ""),
            pl.get("origen", ""),
            pl.get("tipo_scout", ""),
            pl.get("motivo_pago", ""),
            pl.get("cohorte_iso", ""),
            row_hash,
            audit_status,
            action,
            "true" if apply_saved else "false",
            "true" if is_applied else "false",
            "true" if rejected else "false",
            "true" if conflict_flag else "false",
            "true" if ignored_flag else "false",
            "true" if already_paid_flag else "false",
            "true" if not_found_flag else "false",
            error_code,
            error_message,
            what_happened,
            rejection_reason,
            pl.get("scout_id_resolved", ""),
            pl.get("scout", ""),
            pl.get("driver_id_resolved", ""),
            pl.get("nombre_conductor", ""),
            pl.get("licencia", ""),
            "",
            "",
            "",
            file_name,
            "",
            datetime.now().isoformat(),
        ])

    return buf.getvalue()


def generate_summary_csv(
    preview_result: dict,
    apply_summary: dict,
    total_preview_rows: int,
    total_apply_rows: int,
    file_name: str = "",
) -> str:
    """Genera un CSV de resumen independiente."""
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["metrica", "valor"])
    w.writerow(["file_name", file_name])
    w.writerow(["processed_at", datetime.now().isoformat()])
    w.writerow(["audit_total_rows", total_preview_rows])
    w.writerow(["input_total_rows", total_preview_rows])
    w.writerow(["apply_total_rows", total_apply_rows])
    w.writerow(["total_rows", preview_result.get("total_rows", 0)])
    w.writerow(["valid_rows", preview_result.get("valid_rows", 0)])
    w.writerow(["error_rows", preview_result.get("error_rows", 0)])
    w.writerow(["duplicate_rows", preview_result.get("duplicate_rows", 0)])
    w.writerow(["drivers_found", preview_result.get("drivers_found", 0)])
    w.writerow(["drivers_not_found", preview_result.get("drivers_not_found", 0)])
    w.writerow(["scouts_to_create", preview_result.get("scouts_to_create", 0)])
    w.writerow(["assignments_to_create", preview_result.get("assignments_to_create", 0)])
    w.writerow(["assignments_to_change", preview_result.get("assignments_to_change", 0)])
    w.writerow(["payments_to_create", preview_result.get("payments_to_create", 0)])
    w.writerow(["already_paid", preview_result.get("already_paid", 0)])
    w.writerow(["applied", apply_summary.get("applied", 0)])
    w.writerow(["skipped", apply_summary.get("skipped", 0)])
    w.writerow(["no_change", apply_summary.get("no_change", 0)])
    w.writerow(["conflicts", apply_summary.get("conflicts", 0)])
    w.writerow(["errors", apply_summary.get("errors", 0)])
    w.writerow(["commit_ok", str(apply_summary.get("commit_ok", True))])
    w.writerow(["commit_error", apply_summary.get("commit_error", "") or ""])
    return buf.getvalue()
