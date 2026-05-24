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
    ObservedAffiliation,
)
from app.services.normalization_service import normalize_license
from app.adapters.drivers_adapter import check_driver_in_official_source, get_driver_by_license

_preview_store: Dict[str, dict] = {}
_preview_store_lock = threading.Lock()
_PREVIEW_TTL_SECONDS = 3600

SOURCE_TABLE = settings.SOURCE_TABLE

COHORT_RE = re.compile(r"^\d{4}-W\d{2}$")

REQUIRED_COLS = [
    "licencia", "scout",
]

OPTIONAL_COLS = [
    "supervisor",
    "pagado", "monto_pagado", "fecha_pago",
    "fecha_atribucion", "tipo_evento", "observacion",
    "driver_id", "nombre_conductor", "origen",
    "tipo_scout", "motivo_pago", "cohorte_iso",
    "fecha_ancla_reportada", "reported_anchor_date",  # Fase 2A.2
]

ALL_COLS = REQUIRED_COLS + OPTIONAL_COLS


def _normalize_header(h: str) -> str:
    h = h.strip().lower()
    h = h.replace(" ", "_").replace("-", "_")
    mapping = {
        "license": "licencia", "brevete": "licencia",
        "numero_licencia": "licencia", "nro_licencia": "licencia",
        "driver_license": "licencia", "license_number": "licencia",
        "placa": "licencia",
        "scout_name": "scout", "scout_nombre": "scout",
        "nombre_scout": "scout", "scoutname": "scout",
        "supervisor_name": "supervisor", "supervisor_nombre": "supervisor",
        "nombre_supervisor": "supervisor", "supervisorname": "supervisor",
        "pagado": "pagado", "estado": "pagado", "estado_pago": "pagado",
        "pago": "pagado",
        "monto": "monto_pagado", "amount": "monto_pagado", "amount_paid": "monto_pagado",
        "monto_pagado": "monto_pagado",
        "fecha": "fecha_pago", "fecha_de_pago": "fecha_pago", "payment_date": "fecha_pago",
        "fecha_pago": "fecha_pago",
        "fecha_atribucion": "fecha_atribucion",
        "fecha_de_atribucion": "fecha_atribucion", "attribution_date": "fecha_atribucion",
        "fecha_captacion": "fecha_atribucion", "fecha_registro": "fecha_atribucion",
        "tipo_evento": "tipo_evento", "evento": "tipo_evento",
        "event_type": "tipo_evento", "tipo_de_evento": "tipo_evento",
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
        # Fase 2A.2: reported anchor date
        "fecha_ancla_reportada": "reported_anchor_date",
        "reported_anchor_date": "reported_anchor_date",
        "fecha_ancla": "reported_anchor_date",
        "anchor_date": "reported_anchor_date",
        "fecha_reporte": "reported_anchor_date",
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


def _detect_delimiter(first_lines: str) -> str:
    """Auto-detect CSV delimiter from first few lines for better accuracy."""
    candidates = [",", ";", "\t"]
    counts = {d: 0 for d in candidates}
    for d in candidates:
        counts[d] = first_lines.count(d)
    best = max(candidates, key=lambda d: counts.get(d, 0))
    if counts.get(best, 0) >= 2:
        return best
    return ","


def _is_suffixed_col(name: str) -> bool:
    """Check if column name looks like a duplicate suffix: licencia.1, scout.2, etc."""
    import re
    return bool(re.match(r'^.+\.\d+$', name.strip()))


def _strip_suffix(name: str) -> str:
    """Remove .1, .2 suffix from column name to get parent name."""
    import re
    return re.sub(r'\.\d+$', '', name.strip())


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
            if req == "fecha_atribucion" and nd in ("fechaatribucion", "attributiondate", "fechacaptacion", "fecharegistro"):
                suggestions[orig] = req
                break
            if req == "tipo_evento" and nd in ("tipoevento", "eventtype", "evento", "tipo"):
                # Don't override tipo_scout — only suggest if 'scout' not in nd
                if "scout" not in nd and "tipo_scout" not in nd:
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
    Handles: BOM, duplicate/suffixed columns (.1 .2), empty rows, delimiter detection.
    Returns (rows, errors, metadata).
    """
    errors = []
    raw_rows_count = 0
    empty_rows_skipped = 0
    ignored_cols: List[str] = []
    metadata: dict = {
        "delimiter_detected": ",",
        "columns_detected": [],
        "rows_detected": 0,
        "raw_rows_count": 0,
        "empty_rows_skipped": 0,
        "ignored_duplicate_columns": [],
        "structural_error": False,
        "expected_columns": REQUIRED_COLS,
        "suggested_mapping": {},
        "license_non_empty_count": 0,
        "scout_non_empty_count": 0,
    }

    try:
        # Strip BOM
        if content.startswith("\ufeff"):
            content = content[1:]

        lines = content.split("\n")
        all_lines = [l for l in lines if l.strip() or l.strip() == ""]
        # Re-add truly empty lines: we need ALL lines for raw count
        raw_rows_count = len([l for l in lines if l != "" or l.strip() == ""])

        data_lines = [l for l in lines if l.strip()]
        if len(data_lines) < 2:
            errors.append("CSV sin lineas de datos (necesita header + al menos 1 fila)")
            metadata["raw_rows_count"] = len(lines) - 1  # minus header
            return [], errors, metadata

        # Auto-detect delimiter from first lines (header + first few data lines)
        sample = "\n".join(data_lines[:min(6, len(data_lines))])
        delimiter = _detect_delimiter(sample)
        metadata["delimiter_detected"] = delimiter if delimiter != "," else ","
        global _validate_row_last_delimiter
        _validate_row_last_delimiter = delimiter

        # Parse headers using csv.reader for proper quote handling
        csv_reader = _csv.reader(io.StringIO(data_lines[0]), delimiter=delimiter)
        try:
            raw_headers = next(csv_reader)
        except StopIteration:
            raw_headers = data_lines[0].split(delimiter)
        raw_headers = [h.strip().lstrip('\ufeff').strip() for h in raw_headers]
        # Strip any remaining BOM from first header (double safety)
        if raw_headers and raw_headers[0].startswith("\ufeff"):
            raw_headers[0] = raw_headers[0][1:]

        # Detect and filter suffixed columns (licencia.1, scout.2, etc.)
        primary_headers = []
        primary_names = set()
        for h in raw_headers:
            if not h or h.lower().startswith("unnamed"):
                primary_headers.append(h)
                primary_names.add(h)
                continue
            if _is_suffixed_col(h):
                parent = _strip_suffix(h)
                parent_norm = _normalize_header(parent)
                if parent in primary_names or parent_norm in primary_names:
                    ignored_cols.append(h)
                    continue
                # Check if any existing primary already normalizes to same
                existing_norm = {_normalize_header(ph) for ph in primary_headers if ph}
                if parent_norm in existing_norm:
                    ignored_cols.append(h)
                    continue
            primary_headers.append(h)
            primary_names.add(h)

        metadata["columns_detected"] = primary_headers
        metadata["ignored_duplicate_columns"] = ignored_cols

        if ignored_cols:
            errors.append(
                f"El archivo contiene {len(ignored_cols)} columna(s) duplicada(s) "
                f"o bloques pegados a la derecha: {', '.join(ignored_cols[:5])}{'...' if len(ignored_cols) > 5 else ''}. "
                f"Se usara el primer bloque valido."
            )

        headers = {h: _normalize_header(h) for h in primary_headers if h}

        # Structural error: missing required columns
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
            metadata["raw_rows_count"] = len(data_lines) - 1
            return [], errors, metadata

        # Parse data rows — use csv.reader for proper quote handling, skip empty rows
        rows = []
        for i, line in enumerate(data_lines[1:]):
            try:
                vals = list(_csv.reader(io.StringIO(line), delimiter=delimiter))[0]
            except (IndexError, Exception):
                vals = line.split(delimiter)
            row = {}
            all_empty = True
            for j, val in enumerate(vals):
                if j < len(raw_headers):
                    # Skip ignored/suffixed columns
                    if raw_headers[j] in ignored_cols:
                        continue
                    mapped = headers.get(raw_headers[j], raw_headers[j])
                    v = (str(val) if val is not None else "").strip()
                    row[mapped] = v
                    if v:
                        all_empty = False

            row["_source_row"] = i + 2

            # Skip rows where all essential fields are empty
            has_license = bool(row.get("licencia", "").strip())
            has_scout = bool(row.get("scout", "").strip())
            if all_empty and not has_license and not has_scout:
                empty_rows_skipped += 1
                continue

            rows.append(row)

        # Count non-empty license and scout values
        lic_non_empty = sum(1 for r in rows if r.get("licencia", "").strip())
        scout_non_empty = sum(1 for r in rows if r.get("scout", "").strip())

        metadata["rows_detected"] = len(rows)
        metadata["raw_rows_count"] = len(data_lines) - 1
        metadata["empty_rows_skipped"] = empty_rows_skipped
        metadata["license_non_empty_count"] = lic_non_empty
        metadata["scout_non_empty_count"] = scout_non_empty

        # Diagnostic: dump first parsed row so user can verify
        if rows:
            r0 = rows[0]
            metadata["first_row_dump"] = {
                "source_row": r0.get("_source_row", 0),
                "licencia": r0.get("licencia", ""),
                "scout": r0.get("scout", ""),
                "supervisor": r0.get("supervisor", ""),
                "keys": sorted(k for k in r0.keys() if not k.startswith("_")),
            }

        return rows, errors, metadata
    except Exception as e:
        errors.append(f"Error al parsear CSV: {e}")
        return [], errors, metadata


def _parse_rows_from_xlsx(content: bytes) -> Tuple[List[dict], List[str]]:
    """Parse XLSX content into list of dicts. Uses first sheet. Filters .1 suffixed cols and empty rows."""
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

        # Filter .1/.2 suffixed duplicate columns
        primary_headers = []
        primary_names = set()
        ignored_cols = []
        for h in raw_headers:
            if not h or h.lower().startswith("unnamed"):
                primary_headers.append(h)
                primary_names.add(h)
                continue
            if _is_suffixed_col(h):
                parent = _strip_suffix(h)
                parent_norm = _normalize_header(parent)
                if parent in primary_names or parent_norm in primary_names:
                    ignored_cols.append(h)
                    continue
                existing_norm = {_normalize_header(ph) for ph in primary_headers if ph}
                if parent_norm in existing_norm:
                    ignored_cols.append(h)
                    continue
            primary_headers.append(h)
            primary_names.add(h)

        headers = {h: _normalize_header(h) for h in primary_headers if h}
        empty_skipped = 0

        rows = []
        for i, vals in enumerate(rows_iter):
            row = {}
            all_empty = True
            for j, val in enumerate(vals):
                if j < len(raw_headers):
                    if raw_headers[j] in ignored_cols:
                        continue
                    mapped = headers.get(raw_headers[j], raw_headers[j])
                    v = str(val).strip() if val is not None else ""
                    row[mapped] = v
                    if v:
                        all_empty = False
            row["_source_row"] = i + 2
            has_license = bool(row.get("licencia", "").strip())
            has_scout = bool(row.get("scout", "").strip())
            if all_empty and not has_license and not has_scout:
                empty_skipped += 1
                continue
            rows.append(row)

        if ignored_cols and not errors:
            errors.append(
                f"El archivo contiene {len(ignored_cols)} columna(s) duplicada(s) "
                f"o bloques pegados a la derecha. Se usara el primer bloque valido."
            )

        wb.close()
        return rows, errors
    except Exception as e:
        errors.append(f"Error al parsear XLSX: {e}")
        return [], errors


_validate_row_sample_dumped = False
_validate_row_last_delimiter = "?"

def _validate_row(row: dict) -> List[str]:
    global _validate_row_sample_dumped
    errors = []
    for col in REQUIRED_COLS:
        if col not in row or not row[col]:
            errors.append(f"Falta campo requerido: {col}")
    if errors and not _validate_row_sample_dumped:
        _validate_row_sample_dumped = True
        import json as _json
        try:
            sample = {k: v for k, v in row.items() if not k.startswith("_")}
            errors.append(f"[DIAG] Delimiter: {_validate_row_last_delimiter}")
            errors.append(f"[DIAG] First failing row keys: {sorted(sample.keys())[:20]}")
            errors.append(f"[DIAG] licencia={repr(sample.get('licencia'))} scout={repr(sample.get('scout'))} supervisor={repr(sample.get('supervisor'))}")
        except Exception:
            pass
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
    count_u1 = 0  # observed_no_official_source
    count_u2 = 0  # driver_found_not_official_source
    count_u3 = 0  # official_source_match
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
                "fecha_atribucion": row.get("fecha_atribucion", ""),
                "tipo_evento": row.get("tipo_evento", ""),
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
                "fecha_atribucion": row.get("fecha_atribucion", ""),
                "tipo_evento": row.get("tipo_evento", ""),
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
            line_errors.append("Licencia no encontrada en Fuente Oficial Operativa")

        # Operational source classification (U1/U2/U3)
        op_src = classify_operational_source(db, licencia, resolved_driver)
        op_universe = op_src["operational_source_universe"]
        if op_universe == "observed_no_official_source": count_u1 += 1
        elif op_universe == "driver_found_not_official_source": count_u2 += 1
        elif op_universe == "official_source_match": count_u3 += 1

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

        # Validation: missing fecha_atribucion on operational attribution rows
        fecha_atribucion = row.get("fecha_atribucion", "").strip()
        tipo_evento = row.get("tipo_evento", "").strip()
        input_driver_id = (row.get("driver_id") or "").strip()
        has_driver = bool(resolved_driver) or bool(input_driver_id) or bool(licencia)
        is_pure_financial = _parse_pagado(row.get("pagado", "")) and not bool(resolved_driver) and not bool(input_driver_id)
        if has_driver and not fecha_atribucion and not is_pure_financial:
            line_warnings.append("falta fecha_atribucion — atribucion operativa sin fecha de captacion")

        # Validation: missing supervisor → warning, NOT blocking
        supervisor_missing = not supervisor_name or not supervisor_name.strip()
        if supervisor_missing:
            line_warnings.append("Supervisor faltante; la fila se procesa pero requiere completar supervisor")

        if line_errors: error_rows += 1
        else: valid_rows += 1

        line_data = {"source_row": row.get("_source_row", i + 2), "licencia": licencia,
            "scout": scout_name, "supervisor": supervisor_name,
            "pagado": row.get("pagado", ""), "monto_pagado": monto,
            "fecha_pago": row.get("fecha_pago", ""),
            "fecha_atribucion": row.get("fecha_atribucion", ""),
            "tipo_evento": row.get("tipo_evento", ""),
            "observacion": row.get("observacion", ""),
            "nombre_conductor": row.get("nombre_conductor", ""),
            "origen": row.get("origen", ""),
            "tipo_scout": row.get("tipo_scout", ""),
            "motivo_pago": row.get("motivo_pago", ""),
            "operational_source_universe": op_universe,
            "source_confidence": op_src["source_confidence"],
            "payable_source_status": op_src["payable_source_status"],
            "source_warning": op_src["source_warning"],
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
                "fecha_atribucion": row.get("fecha_atribucion", ""),
                "tipo_evento": row.get("tipo_evento", ""),
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
        "count_u1_observed": count_u1,
        "count_u2_driver_not_official": count_u2,
        "count_u3_official": count_u3,
        "warnings": [],
        "lines": lines,
        "apply_plan": apply_plan,
        "parse_metadata": {},
    }


def _upsert_driver_assignment(db: Session, driver_id: str, scout_id: int,
                               applied_by: str, licencia: Optional[str],
                               origen: Optional[str], observacion: Optional[str],
                               source_row: Optional[int],
                               op_universe: Optional[str] = None,
                               op_confidence: Optional[str] = None,
                               op_payable: Optional[str] = None,
                               op_warning: Optional[str] = None,
                               op_matched_drivers: Optional[bool] = None,
                               op_matched_official: Optional[bool] = None,
                               op_origin_tag: Optional[str] = None,
                               reported_anchor_date: Optional[str] = None) -> str:
    """
    Idempotent assignment upsert.
    Returns action: 'created', 'reactivated', 'no_change', 'duplicate_existing'
    """
    # Fase 2A.2: Merge reported_anchor_date into notes as structured JSON
    effective_notes = observacion or None
    if reported_anchor_date:
        import json as _json
        anchor_note = _json.dumps({"reported_anchor_date": reported_anchor_date, "reported_anchor_source": "upload_csv"})
        effective_notes = (effective_notes or "") + (" | " if effective_notes else "") + anchor_note

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
        if op_universe: existing.operational_source_universe = op_universe
        if op_confidence: existing.source_confidence = op_confidence
        if op_payable: existing.payable_source_status = op_payable
        if op_warning: existing.source_warning = op_warning
        if op_matched_drivers is not None: existing.matched_in_drivers = op_matched_drivers
        if op_matched_official is not None: existing.matched_in_official_source = op_matched_official
        if op_origin_tag: existing.official_source_origin_tag = op_origin_tag
        return "reactivated"

    db.add(DriverAssignment(
        driver_id=driver_id, scout_id=scout_id,
        origin=origen or None, status="active",
        assigned_by=applied_by or "unified_load",
        license_raw=licencia or None,
        notes=observacion or None,
        source_file="unified_load.csv",
        source_row=source_row,
        operational_source_universe=op_universe,
        source_confidence=op_confidence,
        payable_source_status=op_payable,
        source_warning=op_warning,
        matched_in_drivers=op_matched_drivers,
        matched_in_official_source=op_matched_official,
        official_source_origin_tag=op_origin_tag,
    ))
    return "created"


def _enrich_detail_parity(d: dict) -> None:
    """Add parity fields to a detail dict in-place, computed from its existing fields."""
    action = d.get("action", "")
    assignment_created = d.get("assignment_created", False)
    payment_created = d.get("payment_created", False)
    observed_created = d.get("observed_affiliation_created", False)
    driver_id = d.get("driver_id")

    # Driver resolution
    if driver_id:
        driver_resolution = "matched_driver"
    elif observed_created:
        driver_resolution = "unmatched_observed"
    elif action in ("driver_not_found", "validation_error"):
        driver_resolution = "not_found_no_evidence"
    else:
        driver_resolution = "unknown"

    # Assignment
    if assignment_created:
        assignment_status = "created"
    elif action == "no_change":
        assignment_status = "already_exists"
    elif action in ("driver_not_found", "driver_not_found_observed_saved", "driver_not_found_observed_existing"):
        assignment_status = "skipped_no_driver"
    elif action in ("validation_error", "error"):
        assignment_status = "not_applicable"
    else:
        assignment_status = "not_applicable"

    # Payment
    if payment_created:
        payment_status = "created"
    elif action == "already_paid":
        payment_status = "already_exists"
    elif action in ("driver_not_found", "driver_not_found_observed_saved", "driver_not_found_observed_existing"):
        payment_status = "skipped_no_driver"
    elif action in ("validation_error", "error"):
        payment_status = "not_applicable"
    else:
        payment_status = "not_applicable"

    # Observed
    if observed_created:
        obs_status = "created"
    elif action == "driver_not_found_observed_existing":
        obs_status = "already_exists"
    elif driver_id:
        obs_status = "not_needed_driver_matched"
    elif action in ("driver_not_found",):
        obs_status = "skipped_no_evidence"
    else:
        obs_status = "not_applicable"

    # Parity status
    if assignment_created and driver_id:
        if payment_created:
            parity_status = "full_applied"
            parity_explanation = "Atribucion y pago aplicados correctamente en AFILIATOR."
        else:
            parity_status = "full_applied"
            parity_explanation = "Atribucion aplicada correctamente. El pago no era requerido."
        next_action = "ready_for_cutoff"
        confidence = "high"
        readiness = "ready_for_cutoff"
        applied = "driver_assignment"
        skipped = ""
        if payment_created:
            applied += " | payment_history"
    elif observed_created or action in ("driver_not_found_observed_saved", "driver_not_found_observed_existing"):
        parity_status = "observed_pending"
        parity_explanation = "Driver no encontrado en fuentes operativas; el reporte del scout fue guardado como observado y queda pendiente de reconciliacion."
        next_action = "wait_reconciliation"
        confidence = "medium"
        readiness = "pending_reconciliation"
        applied = "observed_affiliation"
        skipped = "driver_assignment | payment_history"
    elif action == "already_paid":
        parity_status = "already_reflected"
        parity_explanation = "El pago ya estaba registrado previamente."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "no_action_needed"
        applied = ""
        skipped = "payment_history"
    elif action == "no_change":
        parity_status = "already_reflected"
        parity_explanation = "El registro ya estaba reflejado en AFILIATOR; no se duplico."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "no_action_needed"
        applied = ""
        skipped = ""
    elif action in ("driver_not_found",):
        parity_status = "rejected_unusable"
        parity_explanation = "No hay evidencia minima suficiente para guardar ni atribuir el registro."
        next_action = "fix_license_or_phone"
        confidence = "none"
        readiness = "not_eligible"
        applied = ""
        skipped = ""
    elif action in ("validation_error",):
        parity_status = "rejected_unusable"
        parity_explanation = "El registro contiene errores de validacion y no pudo ser procesado."
        next_action = "fix_license_or_phone"
        confidence = "none"
        readiness = "not_eligible"
        applied = ""
        skipped = ""
    elif action in ("error",):
        parity_status = "rejected_unusable"
        parity_explanation = "Error durante la aplicacion."
        next_action = "manual_review"
        confidence = "none"
        readiness = "not_eligible"
        applied = ""
        skipped = ""
    else:
        parity_status = "unknown"
        parity_explanation = "Estado desconocido."
        next_action = "no_action_needed"
        confidence = "unknown"
        readiness = "not_eligible"
        applied = ""
        skipped = ""

    d["parity_status"] = parity_status
    d["parity_explanation"] = parity_explanation
    d["system_confidence_level"] = confidence
    d["operational_readiness"] = readiness
    d["next_action"] = next_action
    d["driver_resolution_status"] = driver_resolution
    d["assignment_status"] = assignment_status
    d["payment_history_status"] = payment_status
    d["observed_affiliation_status"] = obs_status
    d["applied_entities"] = applied
    d["skipped_entities"] = skipped
    d["rejected_entities"] = ""


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
    observed_created = 0
    observed_existing = 0
    rejected_no_evidence = 0
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

                scout_name = row.get("scout", "")
                licencia_val = row.get("licencia", "")
                driver_name = row.get("nombre_conductor", "")
                phone_val = row.get("telefono", "")

                has_min_evidence = bool(licencia_val or phone_val or driver_name) and bool(scout_name)

                if has_min_evidence:
                    norm_license = normalize_license(licencia_val) if licencia_val else ""
                    # Resolve scout for attribution date reference
                    fecha_attr_raw = row.get("fecha_atribucion", "")
                    fecha_pago_raw = row.get("fecha_pago", "")
                    afiliacion_date = _parse_date(fecha_attr_raw) or _parse_date(fecha_pago_raw) or date.today()

                    scout_id_resolved = _resolve_scout_cached(scout_cache, scout_name)
                    if scout_id_resolved or scout_name:
                        # Dedup: check existing ObservedAffiliation by license+date+scout
                        existing = None
                        if norm_license:
                            existing = db.query(ObservedAffiliation).filter(
                                ObservedAffiliation.normalized_license == norm_license,
                                ObservedAffiliation.reported_affiliation_date == afiliacion_date,
                                ObservedAffiliation.reported_scout_name == scout_name,
                            ).first()

                        if existing:
                            observed_existing += 1
                            sp.rollback()
                            details.append({
                                "source_row": source_row, "status": "observed_saved",
                                "action": "driver_not_found_observed_existing",
                                "saved": True,
                                "message": "Reporte del scout ya existe como observado",
                                "driver_id": None, "scout_id": scout_id_resolved,
                                "scout_name": scout_name,
                                "payment_created": False,
                                "assignment_created": False,
                                "observed_affiliation_created": False,
                                "observed_affiliation_id": existing.id,
                                "observed_affiliation_status": existing.match_status or "unmatched",
                                "eligible_for_cutoff": False,
                                "reconciliation_status": "pending",
                                "driver_operational_state": "observed_only",
                                "what_happened": ["Driver no encontrado", "Ya existe como observado"],
                            })
                        else:
                            oa = ObservedAffiliation(
                                source_file_id=None,
                                row_number=source_row,
                                reported_affiliation_date=afiliacion_date,
                                reported_origin=row.get("origen") or None,
                                reported_scout_name=scout_name,
                                reported_supervisor_name=row.get("supervisor") or None,
                                reported_driver_name=driver_name or None,
                                reported_license=licencia_val or None,
                                reported_phone=phone_val or None,
                                normalized_license=norm_license or None,
                                normalized_phone=None,
                                matched_driver_id=None,
                                match_status="unmatched",
                                match_confidence=None,
                                match_reason="Licencia no encontrada en fuente oficial",
                                official_source_status="driver_not_found",
                                review_status="observed_pending_review",
                                review_notes=f"Origen: carga unificada. {row.get('observacion') or ''}",
                                raw_payload={
                                    "source": "unified_load",
                                    "fecha_pago": fecha_pago_raw or None,
                                    "fecha_atribucion": fecha_attr_raw or None,
                                    "tipo_evento": row.get("tipo_evento") or None,
                                    "monto_pagado": str(row.get("monto_pagado", "")),
                                    "pagado": row.get("pagado") or None,
                                    "tipo_scout": row.get("tipo_scout") or None,
                                    "motivo_pago": row.get("motivo_pago") or None,
                                    "cohorte_iso": row.get("cohorte_iso") or None,
                                },
                            )
                            db.add(oa)
                            db.flush()
                            observed_created += 1
                            sp.commit()
                            details.append({
                                "source_row": source_row, "status": "observed_saved",
                                "action": "driver_not_found_observed_saved",
                                "saved": True,
                                "message": "Driver no encontrado; reporte del scout guardado como observado para reconciliacion futura",
                                "driver_id": None, "scout_id": scout_id_resolved,
                                "scout_name": scout_name,
                                "payment_created": False,
                                "assignment_created": False,
                                "observed_affiliation_created": True,
                                "observed_affiliation_id": oa.id,
                                "observed_affiliation_status": "unmatched",
                                "eligible_for_cutoff": False,
                                "reconciliation_status": "pending",
                                "driver_operational_state": "observed_only",
                                "what_happened": ["Driver no encontrado", "Guardado como afiliacion observada para reconciliacion"],
                            })
                    else:
                        rejected_no_evidence += 1
                        sp.rollback()
                        details.append({
                            "source_row": source_row, "status": "skipped",
                            "action": "driver_not_found", "saved": False,
                            "message": "Driver no encontrado; sin scout valido para guardar como observado",
                            "driver_id": None, "scout_id": None,
                        })
                else:
                    rejected_no_evidence += 1
                    sp.rollback()
                    details.append({
                        "source_row": source_row, "status": "skipped",
                        "action": "driver_not_found", "saved": False,
                        "message": "Driver no encontrado; sin evidencia minima (licencia/nombre/telefono + scout) para guardar como observado",
                        "driver_id": None, "scout_id": None,
                    })
                continue

            what_happened = []
            # Operational source classification for persistence
            op_src_apply = classify_operational_source(db, licencia, resolved_driver)
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
                        op_universe=op_src_apply.get("operational_source_universe"),
                        op_confidence=op_src_apply.get("source_confidence"),
                        op_payable=op_src_apply.get("payable_source_status"),
                        op_warning=op_src_apply.get("source_warning"),
                        op_matched_drivers=op_src_apply.get("matched_in_drivers"),
                        op_matched_official=op_src_apply.get("matched_in_official_source"),
                        op_origin_tag=op_src_apply.get("official_source_origin_tag"),
                        reported_anchor_date=row.get("reported_anchor_date") or None,
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
                        op_universe=op_src_apply.get("operational_source_universe"),
                        op_confidence=op_src_apply.get("source_confidence"),
                        op_payable=op_src_apply.get("payable_source_status"),
                        op_warning=op_src_apply.get("source_warning"),
                        op_matched_drivers=op_src_apply.get("matched_in_drivers"),
                        op_matched_official=op_src_apply.get("matched_in_official_source"),
                        op_origin_tag=op_src_apply.get("official_source_origin_tag"),
                        reported_anchor_date=row.get("reported_anchor_date") or None,
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
                "observed_affiliation_created": False,
                "observed_affiliation_id": None,
                "observed_affiliation_status": None,
                "eligible_for_cutoff": True,
                "reconciliation_status": None,
                "driver_operational_state": "matched",
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

    # Enrich all details with parity fields
    for d in details:
        _enrich_detail_parity(d)

    return {
        "applied": applied, "skipped": skipped, "errors": errors_count,
        "no_change": no_change_count, "conflicts": conflict_count,
        "already_paid": already_paid_count, "not_found": not_found_count,
        "observed_created": observed_created,
        "observed_existing": observed_existing,
        "rejected_no_evidence": rejected_no_evidence,
        "details": details,
    }


def _streaming_parity(assign_action: str, payment_created: bool, line_action: str,
                      what: list, resolved_driver: str) -> dict:
    """Parity for streaming apply rows (driver always resolved in plan)."""
    has_assignment = assign_action in ("created", "reactivated")
    has_payment = payment_created
    applied_ent = []
    skipped_ent = []

    if has_assignment:
        applied_ent.append("driver_assignment")
        if has_payment:
            applied_ent.append("payment_history")
            parity_status = "full_applied"
            parity_explanation = "Atribucion y pago aplicados correctamente en AFILIATOR."
            next_action = "ready_for_cutoff"
            confidence = "high"
            readiness = "ready_for_cutoff"
        else:
            parity_status = "full_applied"
            parity_explanation = "Atribucion aplicada correctamente. El pago no era requerido."
            next_action = "ready_for_cutoff"
            confidence = "high"
            readiness = "ready_for_cutoff"
    elif line_action == "already_paid":
        parity_status = "already_reflected"
        parity_explanation = "El pago ya estaba registrado previamente."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "no_action_needed"
        skipped_ent.append("payment_history")
    elif line_action == "no_change":
        parity_status = "already_reflected"
        parity_explanation = "El registro ya estaba reflejado en AFILIATOR; no se duplico."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "no_action_needed"
    elif line_action == "duplicate_existing":
        parity_status = "no_change"
        parity_explanation = "Registro duplicado; no requiere procesamiento."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "no_action_needed"
    elif line_action == "error":
        parity_status = "rejected_unusable"
        parity_explanation = "Error durante la aplicacion."
        next_action = "manual_review"
        confidence = "none"
        readiness = "not_eligible"
    else:
        parity_status = "full_applied" if has_assignment else "unknown"
        parity_explanation = "Procesado correctamente."
        next_action = "no_action_needed"
        confidence = "high"
        readiness = "ready_for_cutoff" if has_assignment else "no_action_needed"

    return {
        "parity_status": parity_status,
        "parity_explanation": parity_explanation,
        "system_confidence_level": confidence,
        "operational_readiness": readiness,
        "next_action": next_action,
        "driver_resolution_status": "matched_driver",
        "assignment_status": "created" if has_assignment else "already_exists" if assign_action == "no_change" else "not_applicable",
        "payment_history_status": "created" if has_payment else ("already_exists" if line_action == "already_paid" else "not_applicable"),
        "applied_entities": " | ".join(applied_ent) if applied_ent else "",
        "skipped_entities": " | ".join(skipped_ent) if skipped_ent else "",
        "rejected_entities": "",
        "observed_affiliation_status": "not_needed_driver_matched",
        "needs_human_review": "false",
        "blocking_reason": "",
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

            parity = _streaming_parity(assign_action, payment_created, line_action, what, resolved_driver)
            yield {
                "type": "line", "index": i, "total": total,
                "source_row": source_row,
                "licencia": entry.get("licencia", ""), "scout": scout_name,
                "action": line_action, "status": line_status,
                "saved": True, "message": " | ".join(what),
                "driver_id": resolved_driver,
                "what_happened": what, "applied": applied, "skipped": skipped,
                **parity,
            }

        except IntegrityError as e:
            sp.rollback()
            err_str = str(e).lower()
            if "unique" in err_str and "uq_driver_scout_active" in err_str:
                no_change_count += 1
                parity = _streaming_parity("no_change", False, "duplicate_existing", [], "")
                yield {
                    "type": "line", "index": i, "total": total,
                    "source_row": source_row,
                    "action": "duplicate_existing", "status": "ok",
                    "saved": False, "message": "Ya existia asignacion activa",
                    "applied": applied, "skipped": skipped,
                    **parity,
                }
            else:
                errors_count += 1
                parity = _streaming_parity("no_change", False, "error", [], "")
                yield {
                    "type": "line", "index": i, "total": total,
                    "source_row": source_row,
                    "action": "error", "status": "error",
                    "saved": False, "message": str(e),
                    "applied": applied, "skipped": skipped,
                    **parity,
                }
        except Exception as e:
            sp.rollback()
            errors_count += 1
            parity_e = _streaming_parity("no_change", False, "error", [], "")
            yield {
                "type": "line", "index": i, "total": total,
                "source_row": source_row,
                "action": "error", "status": "error",
                "saved": False, "message": str(e),
                "applied": applied, "skipped": skipped,
                **parity_e,
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
            "fecha_atribucion": line.get("fecha_atribucion", ""),
            "tipo_evento": line.get("tipo_evento", ""),
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
# OPERATIONAL SOURCE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_operational_source(
    db: Session,
    licencia: str,
    resolved_driver: str,
) -> dict:
    """
    Classify a driver into one of 3 operational universes:
    - U1 observed_no_official_source: no match anywhere
    - U2 driver_found_not_official_source: in drivers table, NOT in official source
    - U3 official_source_match: in module_ct_cabinet_drivers (official source)
    """
    if resolved_driver:
        # Driver resolved via license → driver_id in official source
        return {
            "operational_source_universe": "official_source_match",
            "source_confidence": "trusted",
            "payable_source_status": "payable_trusted",
            "source_warning": "",
            "matched_in_drivers": True,
            "matched_in_official_source": True,
            "official_source_origin_tag": "",  # filled later from source table
        }

    # Driver NOT in official source → check drivers table
    matched_in_drivers = False
    if licencia and licencia.strip():
        norm_lic = normalize_license(licencia)
        driver_info = get_driver_by_license(db, norm_lic)
        if driver_info:
            matched_in_drivers = True

    if matched_in_drivers:
        return {
            "operational_source_universe": "driver_found_not_official_source",
            "source_confidence": "warning",
            "payable_source_status": "payable_with_warning",
            "source_warning": "Driver encontrado en drivers pero no en Fuente Oficial Operativa. Revisar antes de aprobar.",
            "matched_in_drivers": True,
            "matched_in_official_source": False,
            "official_source_origin_tag": "",
        }

    return {
        "operational_source_universe": "observed_no_official_source",
        "source_confidence": "none",
        "payable_source_status": "not_payable_no_official_source",
        "source_warning": "Sin fuente oficial operativa.",
        "matched_in_drivers": False,
        "matched_in_official_source": False,
        "official_source_origin_tag": "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CACHE BUILDERS
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
        "monto_pagado", "fecha_pago", "fecha_atribucion", "tipo_evento",
        "status", "deduced_actions",
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
            line.get("fecha_atribucion", ""),
            line.get("tipo_evento", ""),
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
        "monto_pagado", "fecha_pago", "fecha_atribucion", "tipo_evento",
        "preview_status", "preview_actions",
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
            pl.get("fecha_atribucion", ""),
            pl.get("tipo_evento", ""),
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


def _compute_parity(pl: dict, apply: dict, audit_status: str, action: str,
                    not_found_flag: bool, rejected: bool, ignored_flag: bool,
                    has_assignment: bool, has_payment: bool,
                    ) -> dict:
    """
    Compute parity/equivalence report for a single row.
    Returns a dict with parity fields to append to audit CSV.
    """
    preview_status = pl.get("status", "")
    preview_actions = pl.get("deduced_actions", [])
    preview_errors = pl.get("errors", [])
    driver_resolved = pl.get("driver_id_resolved", "")
    licencia = pl.get("licencia", "")
    scout_name = pl.get("scout", "")
    supervisor_val = (pl.get("supervisor") or "").strip()
    supervisor_missing = not supervisor_val
    pagado_raw = pl.get("pagado", "")
    monto = pl.get("monto_pagado", 0)
    pagado = str(pagado_raw).strip().upper() in ("SI", "YES", "TRUE", "1")

    apply_action = apply.get("action", "")
    apply_saved = apply.get("saved", False)
    observed_created = apply.get("observed_affiliation_created", False)
    observed_id = apply.get("observed_affiliation_id")
    obs_status = apply.get("observed_affiliation_status", "")
    obs_existing = apply_action == "driver_not_found_observed_existing"
    assign_created = apply.get("assignment_created", False)
    payment_created = apply.get("payment_created", False)
    eligible_cutoff = apply.get("eligible_for_cutoff", False)
    driver_op_state = apply.get("driver_operational_state", "")
    reconciliation_st = apply.get("reconciliation_status", "")

    # Source record key
    source_record_key = f"{licencia}|{scout_name}|{pl.get('fecha_atribucion', '') or pl.get('fecha_pago', '')}"

    # Observed was saved (either created new or already existed)
    observed_saved = observed_created or obs_existing

    # Driver resolution status
    if driver_resolved:
        driver_resolution = "matched_driver"
    elif observed_saved:
        driver_resolution = "unmatched_observed"
    elif not_found_flag and (not licencia and not pl.get("nombre_conductor", "")):
        driver_resolution = "not_found_no_evidence"
    elif action == "skipped_duplicate" or preview_status == "skipped_duplicate":
        driver_resolution = "duplicate_candidate"
    elif audit_status == "conflict":
        driver_resolution = "manual_review"
    else:
        driver_resolution = "unknown"

    # Assignment status
    if assign_created and apply_action in ("created_assignment", "reactivated_assignment"):
        assignment_status = "created"
    elif apply_action in ("no_change", "duplicate_existing"):
        assignment_status = "already_exists"
    elif not_found_flag or apply_action == "driver_not_found":
        assignment_status = "skipped_no_driver"
    elif action == "skipped_duplicate" or preview_status == "skipped_duplicate":
        assignment_status = "blocked_duplicate"
    elif preview_status == "error" and "Falta campo requerido" in str(preview_errors):
        assignment_status = "skipped_missing_scout"
    else:
        assignment_status = "not_applicable"

    # Payment history status
    if payment_created and apply_action == "created_payment_history":
        payment_status = "created"
    elif apply_action == "already_paid":
        payment_status = "already_exists"
    elif not_found_flag or apply_action == "driver_not_found":
        payment_status = "skipped_no_driver"
    elif not pagado and not driver_resolved:
        payment_status = "skipped_no_driver"
    elif not pagado:
        payment_status = "not_applicable"
    elif pagado and monto <= 0 and driver_resolved:
        payment_status = "skipped_invalid_amount"
    elif preview_status == "skipped_duplicate":
        payment_status = "blocked_duplicate"
    else:
        payment_status = "not_applicable"

    # Observed affiliation status (parity-specific)
    if observed_created:
        parity_obs_status = "created"
    elif apply_action == "driver_not_found_observed_existing":
        parity_obs_status = "already_exists"
    elif driver_resolved:
        parity_obs_status = "not_needed_driver_matched"
    elif not_found_flag and not observed_saved:
        parity_obs_status = "skipped_no_evidence"
    else:
        parity_obs_status = "not_applicable"

    # ── PARITY STATUS ──
    parity_status = "unknown"
    parity_explanation = ""
    next_action = ""
    blocking_reason = ""
    needs_human_review = False
    applied_entities = []
    skipped_entities = []
    rejected_entities = []
    system_confidence = "unknown"
    operational_readiness = "not_eligible"

    if driver_resolved and not rejected and not ignored_flag:
        # Driver found
        if assignment_status == "created" and (payment_status == "created" or payment_status == "not_applicable"):
            parity_status = "full_applied"
            next_action = "ready_for_cutoff" if eligible_cutoff else "no_action_needed"
            system_confidence = "high"
            operational_readiness = "ready_for_cutoff" if eligible_cutoff else "no_action_needed"
            applied_entities = ["driver_assignment"]
            if payment_status == "created":
                applied_entities.append("payment_history")
                parity_explanation = "Atribucion y pago aplicados correctamente en AFILIATOR."
            else:
                parity_explanation = "Atribucion aplicada correctamente. El pago no era requerido (pagado=NO)."

        elif assignment_status == "already_exists" and (payment_status == "already_exists" or payment_status == "not_applicable"):
            parity_status = "already_reflected"
            parity_explanation = "El registro ya estaba reflejado en AFILIATOR; no se duplico."
            next_action = "no_action_needed"
            system_confidence = "high"
            operational_readiness = "no_action_needed"

        elif assignment_status == "created" and payment_status == "skipped_invalid_amount":
            parity_status = "partial_applied"
            parity_explanation = "Se aplico la atribucion, pero el pago quedo pendiente por monto invalido o faltante."
            next_action = "fix_license_or_phone"
            blocking_reason = "Monto de pago invalido o cero"
            system_confidence = "low"
            operational_readiness = "needs_fix"
            applied_entities = ["driver_assignment"]
            skipped_entities = ["payment_history"]

        elif assignment_status == "created" and payment_status == "already_exists":
            parity_status = "partial_applied"
            parity_explanation = "La atribucion se actualizo; el pago ya existia en el sistema."
            next_action = "no_action_needed"
            system_confidence = "low"
            operational_readiness = "needs_fix"
            applied_entities = ["driver_assignment"]

        elif assignment_status == "already_exists" and payment_status == "created":
            parity_status = "partial_applied"
            parity_explanation = "El pago fue creado; la atribucion ya existia previamente."
            next_action = "ready_for_cutoff" if eligible_cutoff else "no_action_needed"
            system_confidence = "low"
            operational_readiness = "needs_fix"
            applied_entities = ["payment_history"]

        elif audit_status == "conflict":
            parity_status = "manual_review"
            parity_explanation = "El registro presenta un conflicto de asignacion y requiere revision humana."
            next_action = "review_duplicate"
            needs_human_review = True
            system_confidence = "low"
            operational_readiness = "human_review"

        else:
            parity_status = "no_change"
            parity_explanation = "Sin cambios necesarios; el registro ya coincide con AFILIATOR."
            next_action = "no_action_needed"
            system_confidence = "high"
            operational_readiness = "no_action_needed"

    elif observed_saved:
        parity_status = "observed_pending"
        parity_explanation = "Driver no encontrado en fuentes operativas; el reporte del scout fue guardado como observado y queda pendiente de reconciliacion."
        next_action = "wait_reconciliation"
        system_confidence = "medium"
        operational_readiness = "pending_reconciliation"
        applied_entities = ["observed_affiliation"]
        skipped_entities = ["driver_assignment", "payment_history"]

    elif not_found_flag and preview_status == "error":
        parity_status = "rejected_unusable"
        parity_explanation = "No hay evidencia minima suficiente para guardar ni atribuir el registro."
        next_action = "fix_license_or_phone"
        blocking_reason = "; ".join(preview_errors) if preview_errors else "Sin licencia, nombre ni telefono suficientes"
        system_confidence = "none"
        operational_readiness = "not_eligible"
        rejected_entities = ["driver_assignment", "payment_history"]

    elif ignored_flag or preview_status == "skipped_duplicate":
        parity_status = "no_change"
        parity_explanation = "Registro duplicado en el archivo; no requiere procesamiento adicional."
        next_action = "no_action_needed"
        system_confidence = "high"
        operational_readiness = "no_action_needed"

    elif preview_status == "error":
        parity_status = "rejected_unusable"
        parity_explanation = "El registro contiene errores de validacion y no pudo ser procesado."
        next_action = "fix_license_or_phone"
        blocking_reason = "; ".join(preview_errors) if preview_errors else "Error desconocido"
        system_confidence = "none"
        operational_readiness = "not_eligible"
        rejected_entities = ["driver_assignment", "payment_history"]

    elif action == "no_change":
        parity_status = "already_reflected"
        parity_explanation = "El registro ya estaba reflejado en AFILIATOR."
        next_action = "no_action_needed"
        system_confidence = "high"
        operational_readiness = "no_action_needed"

    else:
        parity_status = "unknown"
        parity_explanation = "Estado desconocido; se requiere revision."
        next_action = "manual_review"
        needs_human_review = True
        system_confidence = "unknown"
        operational_readiness = "human_review"

    # Supervisor missing adjustment
    supervisor_status = "matched"
    supervisor_warning = ""
    if supervisor_missing:
        supervisor_status = "missing"
        supervisor_warning = "Supervisor faltante; el registro fue guardado pero requiere completar supervisor"
        if parity_status == "full_applied":
            parity_status = "partial_applied"
            parity_explanation = "Atribucion aplicada pero supervisor faltante; requiere completar dato organizacional."
            next_action = "fix_supervisor"
            system_confidence = "low"
            operational_readiness = "needs_fix"
        elif parity_status == "already_reflected" and driver_resolved:
            parity_status = "partial_applied"
            parity_explanation = "Registro reflejado pero supervisor faltante; completar dato organizacional."
            next_action = "fix_supervisor"
            system_confidence = "low"
            operational_readiness = "needs_fix"
        elif parity_status == "observed_pending":
            next_action = "fix_supervisor_and_wait_reconciliation"
            needs_human_review = True

    # Driver operational state
    if not driver_op_state:
        if driver_resolved:
            driver_op_state = "matched"
        elif observed_saved:
            driver_op_state = "observed_only"
        else:
            driver_op_state = "unmatched"

    return {
        "source_record_key": source_record_key,
        "parity_status": parity_status,
        "parity_explanation": parity_explanation,
        "input_record_detected": "true",
        "driver_resolution_status": driver_resolution,
        "driver_operational_state": driver_op_state,
        "assignment_status": assignment_status,
        "payment_history_status": payment_status,
        "observed_affiliation_status": parity_obs_status,
        "reconciliation_status": reconciliation_st or "",
        "eligible_for_cutoff": "true" if eligible_cutoff else "false",
        "needs_human_review": "true" if needs_human_review else "false",
        "next_action": next_action,
        "blocking_reason": blocking_reason,
        "applied_entities": " | ".join(applied_entities) if applied_entities else "",
        "skipped_entities": " | ".join(skipped_entities) if skipped_entities else "",
        "rejected_entities": " | ".join(rejected_entities) if rejected_entities else "",
        "system_confidence_level": system_confidence,
        "operational_readiness": operational_readiness,
        "supervisor_status": supervisor_status,
        "supervisor_warning": supervisor_warning,
        "attribution_saved_despite_supervisor_missing": "true" if (supervisor_missing and (applied_entities or observed_saved)) else "false",
        "operational_source_universe": pl.get("operational_source_universe", ""),
        "source_confidence": pl.get("source_confidence", ""),
        "payable_source_status": pl.get("payable_source_status", ""),
        "source_warning": pl.get("source_warning", ""),
        "matched_in_drivers": "true" if bool(pl.get("driver_id_resolved", "")) else "false",
        "matched_in_official_source": "true" if bool(pl.get("driver_id_resolved", "")) else "false",
    }


def generate_full_audit_csv(
    preview_lines: List[dict],
    apply_lines: List[dict],
    file_name: str = "",
    delimiter: str = ",",
) -> str:
    """
    Genera un CSV de auditoria COMPLETA con TODAS las filas del input original.
    Ninguna fila se omite. Incluye todas las columnas originales + columnas de auditoria.
    El resumen va en archivo separado (generate_summary_csv).
    Usa delimiter=';' para compatibilidad Excel LATAM.
    """
    apply_by_row: Dict[int, dict] = {}
    for al in apply_lines:
        sr = al.get("source_row") or al.get("row", 0)
        apply_by_row[int(sr) if sr else 0] = al

    buf = io.StringIO()
    w = _csv.writer(buf, delimiter=delimiter)

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
        "fecha_atribucion",
        "tipo_evento",
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
        # Observed bridge
        "observed_affiliation_created",
        "observed_affiliation_id",
        "observed_affiliation_status",
        "assignment_created",
        "paid_history_created",
        "eligible_for_cutoff",
        "reconciliation_status",
        "driver_operational_state",
        "assignment_id",
        "payment_id",
        "source_file",
        "import_batch_id",
        "processed_at",
        # Parity report (side-by-side with Sheets)
        "source_record_key",
        "parity_status",
        "parity_explanation",
        "input_record_detected",
        "driver_resolution_status",
        "assignment_status",
        "payment_history_status",
        "needs_human_review",
        "next_action",
        "blocking_reason",
        "applied_entities",
        "skipped_entities",
        "rejected_entities",
        "system_confidence_level",
        "operational_readiness",
        "supervisor_status",
        "supervisor_warning",
        "attribution_saved_despite_supervisor_missing",
        "operational_source_universe",
        "source_confidence",
        "payable_source_status",
        "source_warning",
        "matched_in_drivers",
        "matched_in_official_source",
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
        elif apply_action == "driver_not_found_observed_saved":
            audit_status = "observed"
            action = "driver_not_found_observed_saved"
            not_found_flag = True
            what_happened = "Driver no encontrado; reporte del scout guardado como observado para reconciliacion futura"
        elif apply_action == "driver_not_found_observed_existing":
            audit_status = "observed"
            action = "driver_not_found_observed_existing"
            not_found_flag = True
            what_happened = "Driver no encontrado; reporte ya existia como observado"
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

        has_assignment = apply.get("assignment_created", False) or action in ("no_change", "duplicate_existing", "already_paid")
        has_payment = apply.get("payment_created", False) or action in ("already_paid", "created_payment_history")
        parity = _compute_parity(
            pl, apply, audit_status, action,
            not_found_flag, rejected, ignored_flag,
            has_assignment, has_payment,
        )

        w.writerow([
            sr,
            pl.get("licencia", ""),
            pl.get("scout", ""),
            pl.get("supervisor", ""),
            pl.get("pagado", ""),
            pl.get("monto_pagado", ""),
            pl.get("fecha_pago", ""),
            pl.get("fecha_atribucion", ""),
            pl.get("tipo_evento", ""),
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
            # Observed bridge columns
            "true" if apply.get("observed_affiliation_created") else "false",
            str(apply.get("observed_affiliation_id") or ""),
            apply.get("observed_affiliation_status") or "",
            "true" if apply.get("assignment_created") else "false",
            "true" if apply.get("payment_created") else "false",
            "true" if apply.get("eligible_for_cutoff") else "false",
            apply.get("reconciliation_status") or "",
            apply.get("driver_operational_state") or "",
            "",
            "",
            file_name,
            "",
            datetime.now().isoformat(),
            # Parity columns — computed from preview + apply state
            parity.get("source_record_key", ""),
            parity.get("parity_status", ""),
            parity.get("parity_explanation", ""),
            parity.get("input_record_detected", "true"),
            parity.get("driver_resolution_status", ""),
            parity.get("assignment_status", ""),
            parity.get("payment_history_status", ""),
            parity.get("needs_human_review", "false"),
            parity.get("next_action", ""),
            parity.get("blocking_reason", ""),
            parity.get("applied_entities", ""),
            parity.get("skipped_entities", ""),
            parity.get("rejected_entities", ""),
            parity.get("system_confidence_level", ""),
            parity.get("operational_readiness", ""),
            parity.get("supervisor_status", ""),
            parity.get("supervisor_warning", ""),
            parity.get("attribution_saved_despite_supervisor_missing", "false"),
            parity.get("operational_source_universe", ""),
            parity.get("source_confidence", ""),
            parity.get("payable_source_status", ""),
            parity.get("source_warning", ""),
            parity.get("matched_in_drivers", "false"),
            parity.get("matched_in_official_source", "false"),
        ])

    return buf.getvalue()


def generate_summary_csv(
    preview_result: dict,
    apply_summary: dict,
    total_preview_rows: int,
    total_apply_rows: int,
    file_name: str = "",
    delimiter: str = ",",
) -> str:
    """Genera un CSV de resumen independiente."""
    buf = io.StringIO()
    w = _csv.writer(buf, delimiter=delimiter)
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
    w.writerow(["observed_created", apply_summary.get("observed_created", 0)])
    w.writerow(["observed_existing", apply_summary.get("observed_existing", 0)])
    w.writerow(["rejected_no_evidence", apply_summary.get("rejected_no_evidence", 0)])
    w.writerow(["full_applied", apply_summary.get("full_applied", 0)])
    w.writerow(["already_reflected", apply_summary.get("already_reflected", 0)])
    w.writerow(["partial_applied", apply_summary.get("partial_applied", 0)])
    w.writerow(["observed_pending", apply_summary.get("observed_pending", 0)])
    w.writerow(["rejected_unusable", apply_summary.get("rejected_unusable", 0)])
    w.writerow(["manual_review", apply_summary.get("manual_review", 0)])
    w.writerow(["commit_ok", str(apply_summary.get("commit_ok", True))])
    w.writerow(["commit_error", apply_summary.get("commit_error", "") or ""])
    return buf.getvalue()


def generate_parity_summary_csv(full_audit_csv_content: str, delimiter: str = ",") -> str:
    """Genera un resumen ejecutivo de paridad desde el CSV de auditoria completa."""
    import csv as _csv_reader
    buf = io.StringIO()
    reader = _csv_reader.reader(io.StringIO(full_audit_csv_content), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        return ""
    header = rows[0]
    data = rows[1:]
    try:
        ps_idx = header.index("parity_status")
    except ValueError:
        return ""

    parity_counts: dict = {}
    for r in data:
        if len(r) > ps_idx:
            ps = r[ps_idx].strip()
            parity_counts[ps] = parity_counts.get(ps, 0) + 1

    w = _csv.writer(buf, delimiter=delimiter)
    w.writerow(["parity_status", "count"])
    w.writerow(["full_applied", parity_counts.get("full_applied", 0)])
    w.writerow(["already_reflected", parity_counts.get("already_reflected", 0)])
    w.writerow(["partial_applied", parity_counts.get("partial_applied", 0)])
    w.writerow(["observed_pending", parity_counts.get("observed_pending", 0)])
    w.writerow(["rejected_unusable", parity_counts.get("rejected_unusable", 0)])
    w.writerow(["manual_review", parity_counts.get("manual_review", 0)])
    w.writerow(["no_change", parity_counts.get("no_change", 0)])
    w.writerow(["unknown", parity_counts.get("unknown", 0)])
    w.writerow(["total", sum(parity_counts.values())])
    return buf.getvalue()
