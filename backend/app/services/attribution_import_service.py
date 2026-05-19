"""
Attribution Import Service - Fase 4.6.
Importa atribuciones historicas scout->conductor con o sin pago.
Crea/actualiza scout_liq_driver_assignments y guarda raw en historical_attributions.
"""

import json
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    Scout, DriverAssignment, HistoricalAttribution,
)
from app.services.historical_import_service import (
    resolve_scout, resolve_driver_id_via_license,
    parse_date_safe, parse_decimal_safe, normalize_text,
)


def _extract_field(row: dict, *keys: str) -> Optional[str]:
    for k in keys:
        val = row.get(k)
        if val:
            return str(val).strip()
    return None


def _classify_attribution_row(db: Session, row: dict, source_file: str,
                                sheet: str, row_num: int) -> dict:
    # Standard template columns
    scout_name_raw = _extract_field(row, "scout_name_raw", "SCOUT", "scout")
    driver_license_raw = _extract_field(row, "driver_license_raw", "LICENCIA", "licencia", "Brevete")
    driver_id_raw = _extract_field(row, "driver_id_resolved")
    driver_name_raw = _extract_field(row, "driver_name_raw", "NOMBRE DEL CONDUCTOR", "CONDUCTOR", "Nombre")
    supervisor_raw = _extract_field(row, "supervisor_name_raw", "SUPERVISOR", "supervisor")
    scout_type_raw = _extract_field(row, "scout_type_raw", "MODALIDAD", "MEDIO DE ADQUISICIÓN", "MEDIO")
    origin_raw = _extract_field(row, "origin_raw", "origin")
    cutoff_id = _extract_field(row, "cutoff_external_id", "CORTE_ID", "CORTE")
    hire_date_raw = _extract_field(row, "hire_date", "FECHA")
    assignment_date = _extract_field(row, "assignment_date", "FECHA_REGISTRO", "Fecha Registro")
    payment_status = _extract_field(row, "payment_status_raw", "ESTADO_LINEA", "ESTADO", "PAGADO_FLAG", "Estado")
    payment_amount = _extract_field(row, "payment_amount_raw", "TOTAL_PAGABLE", "TOTAL_PAGADO", "MONTO_COHORTE")
    payment_rule = _extract_field(row, "payment_rule_raw", "REGLA_PAGO", "MEDIO_EVALUADO")
    ok_1 = _extract_field(row, "ok_1_viaje_raw", "OK_1_VIAJE")
    ok_5 = _extract_field(row, "ok_5_viajes_raw", "OK_5_VIAJES")
    ok_25 = _extract_field(row, "ok_25_viajes_raw", "OK_25_VIAJES")
    ok_50 = _extract_field(row, "ok_50_viajes_raw", "OK_50_VIAJES")
    notes = _extract_field(row, "notes", "MOTIVO", "OBS")

    base = {
        "source_file": source_file,
        "source_sheet": sheet,
        "source_row": row_num,
        "cutoff_external_id": cutoff_id,
        "scout_name_raw": scout_name_raw,
        "supervisor_name_raw": supervisor_raw,
        "scout_type_raw": scout_type_raw,
        "origin_raw": origin_raw,
        "driver_license_raw": driver_license_raw,
        "driver_id_resolved": driver_id_raw,
        "driver_name_raw": driver_name_raw,
        "hire_date_raw": hire_date_raw,
        "assignment_date_raw": assignment_date,
        "payment_status_raw": payment_status,
        "payment_amount_raw": payment_amount,
        "payment_rule_raw": payment_rule,
        "import_status": "pending",
    }

    # Resolve scout
    scout_id = resolve_scout(db, scout_name_raw) if scout_name_raw else None
    base["scout_id_resolved"] = scout_id

    # Resolve supervisor
    sup_id = resolve_scout(db, supervisor_raw) if supervisor_raw else None
    base["supervisor_id_resolved"] = sup_id

    # Resolve driver
    did = driver_id_raw
    if not did and driver_license_raw:
        did = resolve_driver_id_via_license(db, driver_license_raw)
    base["driver_id_resolved"] = did

    # Parse payment amount
    amt = parse_decimal_safe(payment_amount)
    base["payment_amount"] = float(amt) if amt else None

    # Build operational flags
    flags = {}
    if ok_1: flags["ok_1_viaje"] = ok_1
    if ok_5: flags["ok_5_viajes"] = ok_5
    if ok_25: flags["ok_25_viajes"] = ok_25
    if ok_50: flags["ok_50_viajes"] = ok_50
    base["operational_flags_json"] = json.dumps(flags) if flags else None

    # Validation
    if not scout_name_raw:
        base["import_status"] = "rejected"
        base["import_reason"] = "sin scout_name_raw"
        return base
    if not driver_license_raw and not driver_name_raw and not driver_id_raw:
        base["import_status"] = "rejected"
        base["import_reason"] = "sin licencia ni nombre ni driver_id"
        return base

    # Manual review checks
    reasons = []
    if not scout_id:
        reasons.append("manual_review_no_scout_match")
    if not did:
        reasons.append("manual_review_no_driver_match")
    else:
        # Check assignment conflict
        existing = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == did,
            DriverAssignment.status == "active",
        ).first()
        if existing and existing.scout_id != scout_id:
            reasons.append("manual_review_assignment_conflict")

    if reasons:
        base["import_status"] = "manual_review"
        base["import_reason"] = "; ".join(reasons)
        return base

    # Check duplicate
    if did and scout_id:
        dup = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == did,
            DriverAssignment.scout_id == scout_id,
            DriverAssignment.status == "active",
        ).first()
        if dup:
            base["import_status"] = "duplicate"
            base["import_reason"] = f"ya existe assignment activo id={dup.id}"
            return dup

        # Check if there's a historical assignment already
        dup_hist = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == did,
            DriverAssignment.scout_id == scout_id,
            DriverAssignment.source_file == source_file,
            DriverAssignment.source_sheet == sheet,
            DriverAssignment.source_row == row_num,
        ).first()
        if dup_hist:
            base["import_status"] = "duplicate"
            base["import_reason"] = f"ya existe assignment historico id={dup_hist.id} (misma fuente)"
            return base

    # Check for duplicate in historical_attributions
    existing_attr = db.query(HistoricalAttribution).filter(
        HistoricalAttribution.source_file == source_file,
        HistoricalAttribution.source_sheet == sheet,
        HistoricalAttribution.source_row == row_num,
    ).first()
    if existing_attr:
        base["import_status"] = "duplicate"
        base["import_reason"] = f"ya existe atribucion historica id={existing_attr.id}"
        return base

    base["import_status"] = "ready_to_import"
    return base


def preview_attributions(db: Session, rows: List[dict], source_file: str,
                          sheet: str = "") -> Dict[str, Any]:
    result = {
        "source_file": source_file,
        "sheet": sheet,
        "total_rows": len(rows),
        "ready_to_import": 0,
        "manual_review": 0,
        "conflicts": 0,
        "duplicates": 0,
        "rejected": 0,
        "lines": [],
    }

    for i, row in enumerate(rows):
        line = _classify_attribution_row(db, row, source_file, sheet, i + 2)
        result["lines"].append(line)

        status = line.get("import_status", "pending")
        if status == "ready_to_import":
            result["ready_to_import"] += 1
        elif status == "manual_review":
            result["manual_review"] += 1
            if "conflict" in (line.get("import_reason") or ""):
                result["conflicts"] += 1
        elif status == "rejected":
            result["rejected"] += 1
        elif status == "duplicate":
            result["duplicates"] += 1

    return result


def commit_attributions(db: Session, batch_id: int,
                          preview_lines: List[dict]) -> Dict[str, Any]:
    result = {
        "batch_id": batch_id,
        "assignments_created": 0,
        "assignments_updated": 0,
        "historical_attributions_created": 0,
        "manual_review": 0,
        "conflicts": 0,
        "duplicates": 0,
        "rejected": 0,
    }

    for line_data in preview_lines:
        status = line_data.get("import_status", "pending")

        # Save historical attribution for every row
        attr = _save_historical_attribution(db, batch_id, line_data, status)
        if attr:
            result["historical_attributions_created"] += 1

        if status == "manual_review":
            result["manual_review"] += 1
            if "conflict" in (line_data.get("import_reason") or ""):
                result["conflicts"] += 1
            continue
        elif status == "rejected":
            result["rejected"] += 1
            continue
        elif status == "duplicate":
            result["duplicates"] += 1
            continue

        # ready_to_import: create/update DriverAssignment
        scout_id = line_data.get("scout_id_resolved")
        driver_id = line_data.get("driver_id_resolved")
        if not scout_id or not driver_id:
            continue

        source_file = line_data.get("source_file", "")
        source_sheet = line_data.get("source_sheet", "")
        source_row = line_data.get("source_row")
        origin = line_data.get("origin_raw")
        license_raw = line_data.get("driver_license_raw")
        hire_date_raw = line_data.get("hire_date_raw")

        hire_date = parse_date_safe(hire_date_raw)

        # Check if historical assignment from same source exists
        existing_hist = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == driver_id,
            DriverAssignment.scout_id == scout_id,
            DriverAssignment.source_file == source_file,
            DriverAssignment.source_sheet == source_sheet,
            DriverAssignment.source_row == source_row,
        ).first()

        if existing_hist:
            existing_hist.origin = origin or existing_hist.origin
            existing_hist.license_raw = license_raw or existing_hist.license_raw
            existing_hist.source_hire_date_raw = hire_date_raw or existing_hist.source_hire_date_raw
            existing_hist.hire_date = hire_date or existing_hist.hire_date
            existing_hist.notes = f"Actualizado por reimport (batch {batch_id})"
            result["assignments_updated"] += 1
            continue

        # Check active assignment
        existing = db.query(DriverAssignment).filter(
            DriverAssignment.driver_id == driver_id,
            DriverAssignment.status == "active",
        ).first()

        if existing:
            if existing.scout_id != scout_id:
                result["conflicts"] += 1
                line_data["import_reason"] = (line_data.get("import_reason") or "") + "; conflict_on_commit"
                continue
            existing.origin = origin or existing.origin
            existing.license_raw = license_raw or existing.license_raw
            existing.source_hire_date_raw = hire_date_raw or existing.source_hire_date_raw
            existing.hire_date = hire_date or existing.hire_date
            existing.source_file = source_file or existing.source_file
            existing.source_sheet = source_sheet or existing.source_sheet
            existing.source_row = source_row or existing.source_row
            existing.assigned_by = "historical_upload"
            result["assignments_updated"] += 1
            if attr:
                attr.linked_assignment_id = existing.id
            continue

        # Create new assignment
        assignment = DriverAssignment(
            driver_id=driver_id,
            scout_id=scout_id,
            origin=origin,
            hire_date=hire_date,
            status="active",
            source_hire_date_raw=hire_date_raw,
            source_origin=origin,
            assigned_by="historical_upload",
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=source_row,
            import_batch_id=batch_id,
            license_raw=license_raw,
            notes=f"Importado de {source_file} / {source_sheet} row {source_row}",
        )
        db.add(assignment)
        db.flush()
        result["assignments_created"] += 1
        if attr:
            attr.linked_assignment_id = assignment.id

    db.commit()
    return result


def _save_historical_attribution(db: Session, batch_id: int,
                                   line_data: dict, status: str) -> Optional[HistoricalAttribution]:
    attr = HistoricalAttribution(
        import_batch_id=batch_id,
        source_file=line_data.get("source_file"),
        source_sheet=line_data.get("source_sheet"),
        source_row=line_data.get("source_row"),
        cutoff_external_id=line_data.get("cutoff_external_id"),
        scout_id_resolved=line_data.get("scout_id_resolved"),
        scout_name_raw=line_data.get("scout_name_raw"),
        supervisor_id_resolved=line_data.get("supervisor_id_resolved"),
        supervisor_name_raw=line_data.get("supervisor_name_raw"),
        scout_type_raw=line_data.get("scout_type_raw"),
        origin_raw=line_data.get("origin_raw"),
        driver_license_raw=line_data.get("driver_license_raw"),
        driver_id_resolved=line_data.get("driver_id_resolved"),
        driver_name_raw=line_data.get("driver_name_raw"),
        hire_date_raw=line_data.get("hire_date_raw"),
        assignment_date_raw=line_data.get("assignment_date_raw"),
        payment_status_raw=line_data.get("payment_status_raw"),
        payment_amount_raw=line_data.get("payment_amount_raw"),
        payment_amount=Decimal(str(line_data.get("payment_amount", 0))) if line_data.get("payment_amount") else None,
        payment_rule_raw=line_data.get("payment_rule_raw"),
        operational_flags_json=line_data.get("operational_flags_json"),
        import_status=status,
        import_reason=line_data.get("import_reason"),
    )
    db.add(attr)
    return attr


def get_attributions(db: Session, filters: Dict[str, Any] = None,
                      limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    q = db.query(HistoricalAttribution)
    f = filters or {}

    if f.get("scout_id"):
        q = q.filter(HistoricalAttribution.scout_id_resolved == int(f["scout_id"]))
    if f.get("driver_id"):
        q = q.filter(HistoricalAttribution.driver_id_resolved == f["driver_id"])
    if f.get("license"):
        q = q.filter(HistoricalAttribution.driver_license_raw.ilike(f"%{f['license']}%"))
    if f.get("source_file"):
        q = q.filter(HistoricalAttribution.source_file == f["source_file"])
    if f.get("source_sheet"):
        q = q.filter(HistoricalAttribution.source_sheet == f["source_sheet"])
    if f.get("import_status"):
        q = q.filter(HistoricalAttribution.import_status == f["import_status"])
    if f.get("origin_raw"):
        q = q.filter(HistoricalAttribution.origin_raw == f["origin_raw"])
    if f.get("cutoff_external_id"):
        q = q.filter(HistoricalAttribution.cutoff_external_id == f["cutoff_external_id"])

    total = q.count()
    rows = q.order_by(HistoricalAttribution.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "import_batch_id": r.import_batch_id,
                "source_file": r.source_file,
                "source_sheet": r.source_sheet,
                "source_row": r.source_row,
                "cutoff_external_id": r.cutoff_external_id,
                "scout_id_resolved": r.scout_id_resolved,
                "scout_name_raw": r.scout_name_raw,
                "supervisor_id_resolved": r.supervisor_id_resolved,
                "driver_license_raw": r.driver_license_raw,
                "driver_id_resolved": r.driver_id_resolved,
                "driver_name_raw": r.driver_name_raw,
                "origin_raw": r.origin_raw,
                "payment_status_raw": r.payment_status_raw,
                "payment_amount": float(r.payment_amount) if r.payment_amount else None,
                "payment_rule_raw": r.payment_rule_raw,
                "import_status": r.import_status,
                "import_reason": r.import_reason,
                "linked_assignment_id": r.linked_assignment_id,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ],
    }


def get_attribution_batch_errors_csv(db: Session, batch_id: int) -> str:
    lines = db.query(HistoricalAttribution).filter(
        HistoricalAttribution.import_batch_id == batch_id,
        HistoricalAttribution.import_status.in_(["rejected", "manual_review", "duplicate"]),
    ).all()

    csv_lines = ["source_sheet,source_row,scout_name_raw,driver_license_raw,driver_id_resolved,payment_status_raw,import_status,import_reason"]
    for l in lines:
        csv_lines.append(
            f"{l.source_sheet or ''},{l.source_row or ''},{l.scout_name_raw or ''},"
            f"{l.driver_license_raw or ''},{l.driver_id_resolved or ''},"
            f"{l.payment_status_raw or ''},{l.import_status},{l.import_reason or ''}"
        )
    return "\r\n".join(csv_lines)
