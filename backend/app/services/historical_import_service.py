"""
Historical Import Service - Fase 4.5.
Importa pagos historicos desde plantilla estandar o Excel original con trazabilidad completa.
"""

import hashlib
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    Scout, DriverAssignment, HistoricalImportBatch, HistoricalImportLine,
    PaidHistory, HistoricalAttribution,
)


# ── Estados explicitamente negativos que SI impiden pago historico ──
EXPLICITLY_NOT_PAID_STATES = frozenset({
    "NO PAGADO", "NO PAGABLE", "EXCLUIDO", "ANULADO",
    "RECHAZADO", "NO ELEGIBLE", "NO ALCANZADO", "CANCELADO",
})


def normalize_text(val: Optional[str]) -> str:
    if not val:
        return ""
    return str(val).strip().upper()


def is_explicitly_not_paid(status_raw: Optional[str]) -> bool:
    """Return True only if the payment status is explicitly negative (rejected/cancelled).

    For historical imports, amount_paid > 0 is the primary payment evidence.
    Only explicitly negative states should prevent payment recording/blocking.
    Ambiguous, empty, or modal states (PARTIME, DESTAJO, FULLTIME) do NOT block.
    """
    if not status_raw:
        return False
    normalized = " ".join(str(status_raw).strip().upper().split())
    return normalized in EXPLICITLY_NOT_PAID_STATES


def has_payment_evidence(amount_paid: Optional[float], status_raw: Optional[str]) -> bool:
    """Return True if there is evidence of a real historical payment.

    Evidence = amount_paid > 0 AND status is NOT explicitly negative.
    """
    if not amount_paid or amount_paid <= 0:
        return False
    return not is_explicitly_not_paid(status_raw)


def parse_date_safe(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal_safe(val: Optional[str]) -> Optional[Decimal]:
    if not val:
        return None
    try:
        return Decimal(str(val).strip().replace(",", "").replace("S/", "").replace("$", "").replace(" ", ""))
    except Exception:
        return None


def build_hash(batch_id: int, source_sheet: str, source_row: int,
               corte_id: Optional[str], licencia: Optional[str], scout: Optional[str],
               amount: Optional[str], rule: Optional[str]) -> str:
    raw = f"{batch_id}|{source_sheet}|{source_row}|{corte_id or ''}|{licencia or ''}|{scout or ''}|{amount or ''}|{rule or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def build_scout_cache(db: Session) -> Dict[str, int]:
    """Pre-load all scouts into a name->id lookup cache."""
    scouts = db.query(Scout).all()
    cache: Dict[str, int] = {}
    for s in scouts:
        name = normalize_text(s.scout_name)
        if name:
            cache[name] = s.id
    return cache


def resolve_scout_cached(cache: Dict[str, int], name_raw: Optional[str]) -> Optional[int]:
    if not name_raw:
        return None
    name = normalize_text(str(name_raw))
    # Exact match
    if name in cache:
        return cache[name]
    # Partial match
    for cached_name, sid in cache.items():
        if name in cached_name or cached_name in name:
            return sid
    return None


def build_license_cache(db: Session, licenses: List[str]) -> Dict[str, str]:
    """Batch-resolve license -> driver_id from source table."""
    if not licenses:
        return {}
    placeholders = ", ".join(f":lic{i}" for i in range(len(licenses)))
    params = {f"lic{i}": lic for i, lic in enumerate(licenses)}
    rows = db.execute(
        text(f"SELECT license, driver_id FROM module_ct_cabinet_drivers WHERE license IN ({placeholders})"),
        params,
    ).fetchall()
    return {r[0]: r[1] for r in rows if r[0] and r[1]}


def build_driver_id_cache(db: Session, driver_ids: List[str]) -> set:
    """Batch-check which driver_ids exist in source table."""
    if not driver_ids:
        return set()
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    rows = db.execute(
        text(f"SELECT driver_id FROM module_ct_cabinet_drivers WHERE driver_id IN ({placeholders})"),
        params,
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def resolve_scout(db: Session, name_raw: Optional[str]) -> Optional[int]:
    if not name_raw:
        return None
    name = str(name_raw).strip()
    s = db.query(Scout).filter(Scout.scout_name.ilike(name)).first()
    if s:
        return s.id
    s = db.query(Scout).filter(Scout.scout_name.ilike(f"%{name}%")).first()
    return s.id if s else None


def resolve_driver_id_via_license(db: Session, license_raw: Optional[str]) -> Optional[str]:
    if not license_raw:
        return None
    lic = str(license_raw).strip()
    row = db.execute(
        text("SELECT driver_id FROM module_ct_cabinet_drivers WHERE license = :lic LIMIT 1"),
        {"lic": lic},
    ).first()
    return row[0] if row else None


def resolve_driver_id_direct(db: Session, driver_id: Optional[str]) -> Optional[str]:
    if not driver_id:
        return None
    row = db.execute(
        text("SELECT driver_id FROM module_ct_cabinet_drivers WHERE driver_id = :did LIMIT 1"),
        {"did": str(driver_id).strip()},
    ).first()
    return row[0] if row else None


def _extract_field(row: dict, *keys: str) -> Optional[str]:
    for k in keys:
        val = row.get(k)
        if val:
            return str(val).strip()
    return None


def _classify_historical_row(db: Session, row: dict, source_file: str,
                              sheet: str, row_num: int,
                              scout_cache: Dict[str, int] = None,
                              license_cache: Dict[str, str] = None,
                              driver_id_set: Set[str] = None,
                              batch_id: int = 0) -> dict:
    """Detect if standard template or original Excel by checking column names."""
    is_standard = any(k in row for k in ("estado_pago", "scout_name_raw", "driver_license_raw", "amount_paid"))

    if is_standard:
        return _classify_standard_row(db, row, source_file, sheet, row_num,
                                       scout_cache, license_cache, driver_id_set, batch_id)
    else:
        return _classify_original_row(db, row, source_file, sheet, row_num,
                                       scout_cache, license_cache, driver_id_set, batch_id)


def _classify_standard_row(db: Session, row: dict, source_file: str,
                            sheet: str, row_num: int,
                            scout_cache: Dict[str, int] = None,
                            license_cache: Dict[str, str] = None,
                            driver_id_set: Set[str] = None,
                            batch_id: int = 0) -> dict:
    scout_name_raw = _extract_field(row, "scout_name_raw", "scout_name")
    driver_license_raw = _extract_field(row, "driver_license_raw")
    driver_id_resolved = _extract_field(row, "driver_id_resolved")
    driver_name_raw = _extract_field(row, "driver_name_raw")
    supervisor_raw = _extract_field(row, "supervisor_name_raw")
    estado_pago = normalize_text(_extract_field(row, "estado_pago", "estado", "ESTADO_LINEA") or "")
    amount_raw = _extract_field(row, "amount_paid", "amount", "MONTO") or "0"
    payment_rule = _extract_field(row, "payment_rule", "TIPO_PAGO", "MEDIO_EVALUADO")
    payment_scheme_name = _extract_field(row, "payment_scheme_name", "REGLA_PAGO")
    payment_scheme_type = _extract_field(row, "payment_scheme_type")
    payment_component = _extract_field(row, "payment_component") or "scout_driver_payment"
    milestone = _extract_field(row, "milestone", "HITO")
    cutoff_external_id = _extract_field(row, "cutoff_external_id", "CORTE_ID", "CORTE")
    fecha_pago_raw = _extract_field(row, "fecha_pago", "FECHA_PAGO")
    currency = _extract_field(row, "currency") or "PEN"
    notes = _extract_field(row, "notes", "OBS")
    external_payment_id = _extract_field(row, "external_payment_id")
    source_file_row = _extract_field(row, "source_file") or source_file
    source_sheet_row = _extract_field(row, "source_sheet") or sheet
    source_row_raw = _extract_field(row, "source_row")
    trips_0_7 = _extract_field(row, "trips_0_7_count_reported")
    trips_8_14 = _extract_field(row, "trips_8_14_count_reported")

    base = {
        "source_sheet": source_sheet_row,
        "source_row": int(source_row_raw) if source_row_raw and source_row_raw.isdigit() else row_num,
        "scout_name_raw": scout_name_raw,
        "driver_license_raw": driver_license_raw,
        "driver_name_raw": driver_name_raw,
        "driver_id_resolved": driver_id_resolved,
        "supervisor_raw": supervisor_raw,
        "corte_id_raw": cutoff_external_id,
        "fecha_pago_raw": fecha_pago_raw,
        "payment_rule_raw": payment_rule,
        "payment_scheme_raw": payment_scheme_name,
        "payment_scheme_type_raw": payment_scheme_type,
        "milestone_raw": milestone,
        "amount_paid_raw": amount_raw,
        "estado_pago_raw": estado_pago,
        "currency": currency,
        "payment_component": payment_component,
        "notes": notes,
        "import_status": "pending",
    }

    # Resolve scout (use cache if available)
    if scout_cache is not None:
        scout_id = resolve_scout_cached(scout_cache, scout_name_raw) if scout_name_raw else None
    else:
        scout_id = resolve_scout(db, scout_name_raw) if scout_name_raw else None
    base["scout_id_resolved"] = scout_id

    # Resolve driver: prefer driver_id_resolved from row, then license resolution (use cache)
    did = driver_id_resolved
    if did:
        if driver_id_set is not None:
            base["driver_id_resolved"] = did if did in driver_id_set else None
        else:
            base["driver_id_resolved"] = resolve_driver_id_direct(db, did)
    elif driver_license_raw:
        if license_cache is not None:
            base["driver_id_resolved"] = license_cache.get(driver_license_raw.strip())
        else:
            base["driver_id_resolved"] = resolve_driver_id_via_license(db, driver_license_raw)

    # Resolve supervisor (use cache)
    if scout_cache is not None:
        sup = resolve_scout_cached(scout_cache, supervisor_raw) if supervisor_raw else None
    else:
        sup = resolve_scout(db, supervisor_raw) if supervisor_raw else None
    base["supervisor_id_resolved"] = sup

    # Parse amount
    amt = parse_decimal_safe(amount_raw)
    base["amount_paid"] = float(amt) if amt else None

    has_amount = amt is not None and float(amt) > 0
    has_payment = has_payment_evidence(float(amt) if amt else 0, estado_pago)

    # ── CAPA A: Attribution classification ──
    attr_status = None
    attr_reason = None

    has_scout_data = bool(scout_name_raw)
    has_driver_data = bool(driver_license_raw or driver_id_resolved)

    if not has_scout_data and not has_driver_data:
        attr_status = "attribution_rejected_missing_scout_and_driver"
        attr_reason = "sin scout ni licencia/driver"
    else:
        attr_reasons = []
        if not scout_id:
            attr_reasons.append("manual_review_no_scout_match")
        if not base["driver_id_resolved"]:
            attr_reasons.append("manual_review_no_driver_match")

        if attr_reasons:
            attr_status = "attribution_manual_review"
            attr_reason = "; ".join(attr_reasons)
        else:
            attr_status = "attribution_ready"
            attr_reason = None

    base["attribution_status"] = attr_status
    base["attribution_reason"] = attr_reason

    # ── CAPA B: Payment Financial (records money paid historically, even without driver_id) ──
    fin_s = None
    fin_r = None

    if not has_amount:
        fin_s = "payment_financial_not_applicable_no_amount"
        fin_r = "monto = 0"
    elif not scout_id and not scout_name_raw:
        fin_s = "payment_financial_manual_review_no_scout"
        fin_r = "sin scout"
    else:
        fin_s = "payment_financial_ready"
        fin_r = None

    base["payment_financial_status"] = fin_s
    base["payment_financial_reason"] = fin_r

    # ── CAPA C: Payment Blocking (only blocks future when driver_id resolved) ──
    blk_s = None
    blk_r = None
    blocks = False

    if not has_amount:
        blk_s = "payment_blocking_not_applicable_no_amount"
        blk_r = "monto = 0"
    elif is_explicitly_not_paid(estado_pago):
        blk_s = "payment_blocking_not_applicable_bad_status"
        blk_r = f"estado explícitamente negativo: {estado_pago}"
    elif not scout_id:
        blk_s = "payment_blocking_manual_review_no_scout"
        blk_r = "scout no resuelto"
    elif not base["driver_id_resolved"]:
        blk_s = "payment_blocking_manual_review_no_driver"
        blk_r = "driver no resuelto"
    else:
        # Check duplicate for blocking
        hash_val = build_hash(
            0, source_sheet_row or sheet, base["source_row"],
            cutoff_external_id, driver_license_raw, scout_name_raw,
            str(amt), payment_rule or "",
        )
        base["unique_hash"] = hash_val

        existing_ph = db.query(PaidHistory).filter(PaidHistory.unique_hash == hash_val).first()
        if existing_ph:
            blk_s = "payment_blocking_duplicate"
            blk_r = f"duplicate_hash: paid_history_id={existing_ph.id}"
        else:
            dup2 = db.query(PaidHistory).filter(
                PaidHistory.driver_id == base["driver_id_resolved"],
                PaidHistory.amount_paid == amt,
                PaidHistory.status == "paid",
                PaidHistory.blocks_future_payment == True,
            ).first()
            if dup2:
                blk_s = "payment_blocking_duplicate"
                blk_r = f"duplicate_driver_amount: paid_history_id={dup2.id}"
            else:
                blk_s = "payment_blocking_ready"
                blk_r = None
                blocks = True

    base["payment_blocking_status"] = blk_s
    base["payment_blocking_reason"] = blk_r
    base["blocks_future_payment"] = blocks

    # Legacy compat
    base["payment_status"] = blk_s or fin_s
    base["payment_reason"] = blk_r or fin_r

    # ── Final composite status ──
    if attr_status == "attribution_rejected_missing_scout_and_driver":
        base["final_status"] = "rejected"
    elif attr_status == "attribution_ready":
        if blk_s == "payment_blocking_ready":
            base["final_status"] = "attribution_and_blocking_ready"
        elif fin_s == "payment_financial_ready":
            base["final_status"] = "attribution_and_financial_ready"
        else:
            base["final_status"] = "attribution_only_ready"
    elif attr_status == "attribution_manual_review":
        base["final_status"] = "manual_review"
    else:
        base["final_status"] = fin_s or "unknown"

    base["import_status"] = base["final_status"]
    base["import_reason"] = (attr_reason or "") + (" | " + (fin_r or blk_r) if (fin_r or blk_r) else "")
    return base


def _classify_original_row(db: Session, row: dict, source_file: str,
                            sheet: str, row_num: int,
                            scout_cache: Dict[str, int] = None,
                            license_cache: Dict[str, str] = None,
                            driver_id_set: Set[str] = None,
                            batch_id: int = 0) -> dict:
    """Legacy support for original Excel column names (Data Gerencia y Scouts.xlsx)."""
    base = {
        "source_sheet": sheet,
        "source_row": row_num,
        "scout_name_raw": _extract_field(row, "SCOUT", "scout") or None,
        "driver_license_raw": _extract_field(row, "LICENCIA", "licencia", "Brevete") or None,
        "driver_name_raw": _extract_field(row, "NOMBRE DEL CONDUCTOR", "Nombre", "CONDUCTOR") or None,
        "supervisor_raw": _extract_field(row, "SUPERVISOR", "supervisor") or None,
        "corte_id_raw": _extract_field(row, "CORTE", "CORTE_ID", "corte_id") or None,
        "fecha_pago_raw": _extract_field(row, "FECHA", "FECHA_PAGO", "fecha") or None,
        "payment_rule_raw": _extract_field(row, "REGLA_PAGO", "TIPO_PAGO", "MEDIO", "MODALIDAD") or None,
        "milestone_raw": _extract_field(row, "HITO", "hito", "REGLA") or None,
        "amount_paid_raw": _extract_field(row, "TOTAL_PAGABLE", "TOTAL_PAGADO", "MONTO", "Total de Bono") or None,
        "estado_pago_raw": _extract_field(row, "ESTADO", "ESTADO_LINEA", "PAGADO_FLAG") or None,
        "import_status": "pending",
    }

    scout_name = base["scout_name_raw"]
    if scout_cache is not None:
        base["scout_id_resolved"] = resolve_scout_cached(scout_cache, scout_name) if scout_name else None
    else:
        base["scout_id_resolved"] = resolve_scout(db, scout_name) if scout_name else None

    lic = base["driver_license_raw"]
    if license_cache is not None and lic:
        base["driver_id_resolved"] = license_cache.get(lic.strip())
    else:
        base["driver_id_resolved"] = resolve_driver_id_via_license(db, lic) if lic else None

    sup = base["supervisor_raw"]
    if scout_cache is not None:
        base["supervisor_id_resolved"] = resolve_scout_cached(scout_cache, sup) if sup else None
    else:
        base["supervisor_id_resolved"] = resolve_scout(db, sup) if sup else None

    amt_raw = base["amount_paid_raw"]
    amt = parse_decimal_safe(amt_raw)
    base["amount_paid"] = float(amt) if amt else None

    estado = normalize_text(base.get("estado_pago_raw") or "")

    if not base["driver_license_raw"] and not base["driver_name_raw"]:
        base["import_status"] = "rejected"
        base["import_reason"] = "sin licencia ni nombre de conductor"
        return base

    if amt is None or float(amt) <= 0:
        base["import_status"] = "rejected"
        base["import_reason"] = "monto cero o invalido"
        return base

    if is_explicitly_not_paid(estado):
        base["import_status"] = "rejected"
        base["import_reason"] = f"estado explícitamente negativo: {estado}"
        return base

    if not base["scout_id_resolved"]:
        base["import_status"] = "manual_review"
        base["import_reason"] = "scout no resuelto"
        return base

    if lic and not base["driver_id_resolved"]:
        base["import_status"] = "manual_review"
        base["import_reason"] = "licencia no resuelve driver_id"
        return base

    hash_val = build_hash(
        batch_id, sheet, row_num,
        base["corte_id_raw"] or "", normalize_text(lic), normalize_text(scout_name or ""),
        str(amt), base["payment_rule_raw"] or "",
    )
    base["unique_hash"] = hash_val

    existing = db.query(PaidHistory).filter(PaidHistory.unique_hash == hash_val).first()
    if existing:
        base["import_status"] = "duplicate"
        base["import_reason"] = f"ya existe en paid_history id={existing.id}"
        return base

    if base["driver_id_resolved"]:
        dup = db.query(PaidHistory).filter(
            PaidHistory.driver_id == base["driver_id_resolved"],
            PaidHistory.milestone == base["milestone_raw"],
            PaidHistory.amount_paid == amt,
        ).first()
        if dup:
            base["import_status"] = "duplicate"
            base["import_reason"] = f"duplicado logico id={dup.id}"
            return base

    base["import_status"] = "ready_to_import"
    return base


def preview_historical_import(db: Session, rows: List[dict], source_file: str,
                               sheet: str = "") -> Dict[str, Any]:
    result = {
        "source_file": source_file,
        "sheet": sheet,
        "total_rows": len(rows),
        # Legacy (kept for backward compat)
        "ready_to_import": 0,
        "rejected": 0,
        "manual_review": 0,
        "duplicate": 0,
        "amount_ready": Decimal("0"),
        "amount_rejected": Decimal("0"),
        "amount_manual_review": Decimal("0"),
        "errors_by_type": {},
        # Dual-layer metrics
        "attribution": {
            "total": 0,
            "ready": 0,
            "manual_review": 0,
            "conflicts": 0,
            "duplicates": 0,
            "rejected": 0,
        },
        "payment": {
            "total": 0,
            "ready": 0,
            "not_applicable": 0,
            "manual_review": 0,
            "duplicates": 0,
            "rejected": 0,
            "amount_ready": Decimal("0"),
            "amount_manual_review": Decimal("0"),
        },
        # Financial layer
        "payment_financial": {
            "ready": 0,
            "not_applicable": 0,
            "manual_review": 0,
            "amount_ready": Decimal("0"),
        },
        # Blocking layer
        "payment_blocking": {
            "ready": 0,
            "manual_review": 0,
            "duplicates": 0,
            "amount_ready": Decimal("0"),
        },
        "lines": [],
    }

    scout_cache = build_scout_cache(db)

    all_licenses = set()
    all_driver_ids = set()
    for row in rows:
        lic = _extract_field(row, "driver_license_raw", "LICENCIA", "licencia", "Brevete")
        if lic:
            all_licenses.add(lic.strip())
        did = _extract_field(row, "driver_id_resolved")
        if did:
            all_driver_ids.add(did.strip())

    license_cache = build_license_cache(db, list(all_licenses)) if all_licenses else {}
    driver_id_set = build_driver_id_cache(db, list(all_driver_ids)) if all_driver_ids else set()

    for i, row in enumerate(rows):
        line_result = _classify_historical_row(
            db, row, source_file, sheet, i + 2,
            scout_cache=scout_cache,
            license_cache=license_cache,
            driver_id_set=driver_id_set,
        )
        result["lines"].append(line_result)

        attr_s = line_result.get("attribution_status", "")
        fin_s = line_result.get("payment_financial_status", "")
        blk_s = line_result.get("payment_blocking_status", "")
        final_s = line_result.get("final_status", "")
        amt = line_result.get("amount_paid") or 0
        amt_d = Decimal(str(amt)) if amt else Decimal("0")
        reason = line_result.get("attribution_reason") or line_result.get("payment_financial_reason") or "unknown"

        # Attribution metrics
        if attr_s and attr_s != "attribution_rejected_missing_scout_and_driver":
            result["attribution"]["total"] += 1
            if attr_s == "attribution_ready":
                result["attribution"]["ready"] += 1
            elif attr_s == "attribution_manual_review":
                result["attribution"]["manual_review"] += 1

        # Financial payment metrics
        if fin_s:
            if fin_s == "payment_financial_ready":
                result["payment_financial"]["ready"] += 1
                result["payment_financial"]["amount_ready"] += amt_d
            elif "not_applicable" in fin_s:
                result["payment_financial"]["not_applicable"] += 1
            elif "manual_review" in fin_s:
                result["payment_financial"]["manual_review"] += 1
            elif "duplicate" in fin_s:
                result["payment"]["duplicates"] += 1

        # Blocking payment metrics
        if blk_s:
            if blk_s == "payment_blocking_ready":
                result["payment_blocking"]["ready"] += 1
                result["payment_blocking"]["amount_ready"] += amt_d
                result["payment"]["ready"] += 1
                result["payment"]["amount_ready"] += amt_d
            elif "manual_review" in blk_s:
                result["payment_blocking"]["manual_review"] += 1
            elif "duplicate" in blk_s:
                result["payment_blocking"]["duplicates"] += 1

        # Legacy mapping
        if final_s == "attribution_and_payment_ready":
            result["ready_to_import"] += 1
            result["amount_ready"] += amt_d
        elif final_s == "rejected":
            result["rejected"] += 1
            result["amount_rejected"] += amt_d
        elif final_s == "manual_review":
            result["manual_review"] += 1
            result["amount_manual_review"] += amt_d

        if final_s not in ("attribution_and_payment_ready", "attribution_only_ready"):
            result["errors_by_type"][reason] = result["errors_by_type"].get(reason, 0) + 1

    return result


def commit_historical_import(db: Session, batch_id: int,
                               preview_result: Dict[str, Any]) -> Dict[str, Any]:
    batch = db.query(HistoricalImportBatch).filter(HistoricalImportBatch.id == batch_id).first()
    if not batch:
        raise ValueError(f"Batch {batch_id} no encontrado")

    result = {
        "batch_id": batch_id,
        "status": "completed",
        # Legacy
        "imported": 0, "rejected": 0, "manual_review": 0, "duplicate": 0, "amount_imported": 0,
        # Dual-layer
        "attributions_created": 0,
        "assignments_created": 0,
        "assignments_updated": 0,
        "paid_history_created": 0,
        "attributions_saved": 0,
        "manual_review_saved": 0,
        "conflicts": 0,
    }
    total_amount = Decimal("0")

    for line_data in preview_result.get("lines", []):
        attr_s = line_data.get("attribution_status", "")
        pay_s = line_data.get("payment_status", "")
        final_s = line_data.get("final_status", "")
        amt = line_data.get("amount_paid") or 0
        amt_d = Decimal(str(amt)) if amt else Decimal("0")

        # Save attribution for rows that have scout+driver data
        attr_obj = None
        assn_obj = None
        if attr_s and attr_s != "attribution_rejected_missing_scout_and_driver":
            attr_obj = _save_attribution_from_line(db, batch_id, line_data, attr_s, attr_s)
            if attr_obj:
                result["attributions_saved"] += 1

            # Create assignment if attribution ready + scout+driver resolved + no conflict
            if attr_s == "attribution_ready":
                scout_id = line_data.get("scout_id_resolved")
                did = line_data.get("driver_id_resolved")
                if scout_id and did:
                    source_file = line_data.get("source_file") or batch.source_file or ""
                    source_sheet = line_data.get("source_sheet", "")
                    source_row = line_data.get("source_row")

                    existing = db.query(DriverAssignment).filter(
                        DriverAssignment.driver_id == did,
                        DriverAssignment.status == "active",
                    ).first()

                    if existing and existing.scout_id != scout_id:
                        result["conflicts"] += 1
                    elif not existing:
                        assn = DriverAssignment(
                            driver_id=did, scout_id=scout_id,
                            origin=line_data.get("origin_raw"),
                            status="active",
                            source_hire_date_raw=line_data.get("hire_date_raw"),
                            source_origin=line_data.get("origin_raw"),
                            assigned_by="historical_upload",
                            source_file=source_file,
                            source_sheet=source_sheet,
                            source_row=source_row,
                            import_batch_id=batch_id,
                            license_raw=line_data.get("driver_license_raw"),
                            notes=f"Importado de {source_file} / {source_sheet} row {source_row}",
                        )
                        db.add(assn)
                        db.flush()
                        assn_obj = assn
                        result["assignments_created"] += 1
                    else:
                        existing.source_file = source_file or existing.source_file
                        existing.source_sheet = source_sheet or existing.source_sheet
                        existing.source_row = source_row or existing.source_row
                        existing.assigned_by = "historical_upload"
                        assn_obj = existing
                        result["assignments_updated"] += 1

        # Create paid_history: financial AND blocking
        ph_obj = None
        fin_s = line_data.get("payment_financial_status", "")
        blk_s = line_data.get("payment_blocking_status", "")
        has_driver = bool(line_data.get("driver_id_resolved"))

        if fin_s == "payment_financial_ready" and amt_d > 0:
            paid_at = parse_date_safe(line_data.get("fecha_pago_raw"))
            ph = PaidHistory(
                cutoff_run_id=None,
                scout_id=line_data.get("scout_id_resolved"),
                driver_id=line_data.get("driver_id_resolved") if has_driver else None,
                driver_license_raw=line_data.get("driver_license_raw"),
                scout_name_raw=line_data.get("scout_name_raw"),
                supervisor_id=line_data.get("supervisor_id_resolved"),
                payment_scheme_name=line_data.get("payment_scheme_raw"),
                payment_scheme_type=line_data.get("payment_scheme_type_raw"),
                payment_rule=line_data.get("payment_rule_raw"),
                amount_paid=amt_d,
                currency=line_data.get("currency") or "PEN",
                paid_at=paid_at or datetime.now(),
                payment_reference=line_data.get("corte_id_raw"),
                import_source="historical_upload",
                import_batch_id=batch_id,
                source_file=batch.source_file or line_data.get("source_file"),
                source_sheet=line_data.get("source_sheet"),
                source_row=line_data.get("source_row"),
                milestone=line_data.get("milestone_raw"),
                cutoff_external_id=line_data.get("corte_id_raw"),
                payment_component=line_data.get("payment_component") or "scout_driver_payment",
                unique_hash=line_data.get("unique_hash"),
                paid_by=batch.uploaded_by or "historical_import",
                reason=line_data.get("notes"),
                status="paid",
                resolution_status="resolved" if has_driver else "unresolved_driver",
                blocks_future_payment=bool(has_driver and blk_s == "payment_blocking_ready"),
                financial_record_status="recorded",
                original_payment_status_raw=line_data.get("estado_pago_raw"),
            )
            db.add(ph)
            db.flush()
            ph_obj = ph
            result["paid_history_created"] += 1
            result["imported"] += 1
            total_amount += amt_d
            result["amount_imported"] = float(total_amount)

        # Save import line with dual-layer fields
        db_line = HistoricalImportLine(
            batch_id=batch_id,
            source_sheet=line_data.get("source_sheet"),
            source_row=line_data.get("source_row"),
            corte_id_raw=line_data.get("corte_id_raw"),
            scout_name_raw=line_data.get("scout_name_raw"),
            scout_id_resolved=line_data.get("scout_id_resolved"),
            driver_license_raw=line_data.get("driver_license_raw"),
            driver_id_resolved=line_data.get("driver_id_resolved"),
            driver_name_raw=line_data.get("driver_name_raw"),
            amount_paid_raw=line_data.get("amount_paid_raw"),
            amount_paid=amt_d if amt_d > 0 else None,
            import_status=final_s,
            import_reason=(line_data.get("attribution_reason") or "") + " | " + (line_data.get("payment_reason") or ""),
            attribution_status=attr_s,
            attribution_reason=line_data.get("attribution_reason"),
            payment_status=pay_s,
            payment_reason=line_data.get("payment_reason"),
            final_status=final_s,
            attribution_id=attr_obj.id if attr_obj else None,
            assignment_id=assn_obj.id if assn_obj else None,
            paid_history_id=ph_obj.id if ph_obj else None,
            unique_hash=line_data.get("unique_hash"),
            payment_rule_raw=line_data.get("payment_rule_raw"),
            milestone_raw=line_data.get("milestone_raw"),
            supervisor_id_resolved=line_data.get("supervisor_id_resolved"),
            fecha_pago_raw=line_data.get("fecha_pago_raw"),
        )
        db.add(db_line)

        # Counters
        if final_s == "rejected":
            result["rejected"] += 1
        elif final_s == "manual_review":
            result["manual_review"] += 1
            result["manual_review_saved"] += 1
        elif "duplicate" in (pay_s or ""):
            result["duplicate"] += 1

    batch.status = "completed"
    batch.imported_count = result["imported"]
    batch.rejected_count = result["rejected"]
    batch.manual_review_count = result["manual_review"]
    batch.duplicate_count = result["duplicate"]
    batch.amount_imported = total_amount
    db.commit()

    return result


def _save_attribution_from_line(db: Session, batch_id: int, line_data: dict,
                                  import_status: str, reason: str) -> Optional[HistoricalAttribution]:
    attr = HistoricalAttribution(
        import_batch_id=batch_id,
        source_file=line_data.get("source_file"),
        source_sheet=line_data.get("source_sheet"),
        source_row=line_data.get("source_row"),
        cutoff_external_id=line_data.get("corte_id_raw"),
        scout_id_resolved=line_data.get("scout_id_resolved"),
        scout_name_raw=line_data.get("scout_name_raw"),
        supervisor_id_resolved=line_data.get("supervisor_id_resolved"),
        supervisor_name_raw=line_data.get("supervisor_raw"),
        scout_type_raw=line_data.get("scout_type_raw"),
        origin_raw=line_data.get("origin_raw"),
        driver_license_raw=line_data.get("driver_license_raw"),
        driver_id_resolved=line_data.get("driver_id_resolved"),
        driver_name_raw=line_data.get("driver_name_raw"),
        hire_date_raw=line_data.get("hire_date_raw"),
        assignment_date_raw=line_data.get("fecha_pago_raw"),
        payment_status_raw=line_data.get("estado_pago_raw"),
        payment_amount_raw=line_data.get("amount_paid_raw"),
        payment_amount=Decimal(str(line_data.get("amount_paid", 0))) if line_data.get("amount_paid") else None,
        payment_rule_raw=line_data.get("payment_rule_raw"),
        import_status=import_status,
        import_reason=reason,
    )
    db.add(attr)
    return attr


def get_batch_errors_csv(db: Session, batch_id: int) -> str:
    lines = db.query(HistoricalImportLine).filter(
        HistoricalImportLine.batch_id == batch_id,
        HistoricalImportLine.import_status.in_(["rejected", "manual_review", "duplicate"]),
    ).all()

    csv_lines = ["source_sheet,source_row,scout_name_raw,driver_license_raw,driver_id_resolved,amount_paid,import_status,import_reason"]
    for l in lines:
        csv_lines.append(
            f"{l.source_sheet or ''},{l.source_row or ''},{l.scout_name_raw or ''},"
            f"{l.driver_license_raw or ''},{l.driver_id_resolved or ''},{l.amount_paid or 0},"
            f"{l.import_status},{l.import_reason or ''}"
        )
    return "\r\n".join(csv_lines)
