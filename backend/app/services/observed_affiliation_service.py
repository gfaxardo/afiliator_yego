"""
Observed Affiliation Service — Flujo de Atribuciones Observadas.

Maneja el ciclo completo:
1. Normalizacion de licencia/telefono/nombre
2. Matching contra tabla drivers (fuente maestra de identidad)
3. Verificacion contra fuente oficial (module_ct_cabinet_drivers)
4. Preview y apply de cargas CSV/XLSX
5. Integracion con cutoff engine via lineas observadas
6. Bloqueo de duplicados
7. Export CSV/XLSX
"""

import csv as _csv
import io
import json
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import (
    ObservedAffiliation, CutoffDriverLine, PaidHistory, DriverAssignment,
)
from app.services.normalization_service import (
    normalize_license, normalize_phone, normalize_name,
)
from app.adapters.drivers_adapter import (
    get_driver_by_license,
    get_driver_by_phone,
    get_driver_by_id,
    check_driver_in_official_source,
)

REQUIRED_COLS_OBSERVED = [
    "fecha_afiliacion", "origen", "scout", "licencia", "telefono",
]

VALID_COLS_OBSERVED = [
    "fecha_afiliacion", "origen", "scout", "supervisor",
    "nombre_driver", "licencia", "telefono",
]


def _normalize_header(h: str) -> str:
    h = h.strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "fecha": "fecha_afiliacion",
        "fecha_afiliacion": "fecha_afiliacion",
        "date": "fecha_afiliacion",
        "fecha_contratacion": "fecha_afiliacion",
        "origen": "origen",
        "origin": "origen",
        "fuente": "origen",
        "scout": "scout",
        "scout_name": "scout",
        "nombre_scout": "scout",
        "supervisor": "supervisor",
        "supervisor_name": "supervisor",
        "nombre_supervisor": "supervisor",
        "nombre_driver": "nombre_driver",
        "driver_name": "nombre_driver",
        "nombre_conductor": "nombre_driver",
        "conductor": "nombre_driver",
        "licencia": "licencia",
        "license": "licencia",
        "brevete": "licencia",
        "telefono": "telefono",
        "phone": "telefono",
        "celular": "telefono",
        "mobile": "telefono",
    }
    return mapping.get(h, h)


def _match_driver(
    db: Session,
    license_val: str,
    phone_val: str,
    driver_name: str,
) -> Dict[str, Any]:
    """
    Busca driver_id en la tabla drivers por licencia y/o telefono.
    Retorna match_status, match_confidence, matched_driver_id, match_reason.
    """
    norm_license = normalize_license(license_val) if license_val else ""
    norm_phone = normalize_phone(phone_val) if phone_val else ""

    match_license = None
    match_phone_list = []

    if norm_license:
        match_license = get_driver_by_license(db, norm_license)

    if norm_phone:
        match_phone_list = get_driver_by_phone(db, norm_phone)

    license_did = match_license["driver_id"] if match_license else None
    phone_dids = [d["driver_id"] for d in match_phone_list] if match_phone_list else []

    if license_did and license_did in phone_dids:
        return {
            "matched_driver_id": license_did,
            "match_status": "matched",
            "match_confidence": "high",
            "match_reason": f"Licencia + telefono coinciden: driver_id={license_did}",
        }
    elif not license_did and not phone_dids:
        return {
            "matched_driver_id": None,
            "match_status": "unmatched",
            "match_confidence": None,
            "match_reason": "Sin coincidencias: licencia y telefono no encontrados en drivers",
        }
    elif license_did and not phone_dids:
        return {
            "matched_driver_id": license_did,
            "match_status": "matched",
            "match_confidence": "medium",
            "match_reason": f"Solo licencia coincide: driver_id={license_did}",
        }
    elif not license_did and len(phone_dids) == 1:
        return {
            "matched_driver_id": phone_dids[0],
            "match_status": "matched",
            "match_confidence": "medium",
            "match_reason": f"Solo telefono coincide: driver_id={phone_dids[0]}",
        }
    else:
        return {
            "matched_driver_id": None,
            "match_status": "manual_review",
            "match_confidence": None,
            "match_reason": f"Multiples coincidencias por telefono: {phone_dids}. Requiere revision manual.",
        }


def _check_official_source(db: Session, matched_driver_id: Optional[str]) -> str:
    """Verifica si driver_id existe en module_ct_cabinet_drivers."""
    if not matched_driver_id:
        return "official_unknown"
    found = check_driver_in_official_source(db, matched_driver_id)
    return "official_found" if found else "official_missing"


def preview_observed_affiliations(
    db: Session,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Preview de carga de atribuciones observadas.
    Para cada fila: normaliza, matchea, verifica fuente oficial.
    Retorna lineas con status y resumen.
    """
    preview_lines = []
    errors = []
    total = len(rows)

    for i, row in enumerate(rows):
        line_num = i + 2  # header = row 1
        fecha_str = (row.get("fecha_afiliacion") or "").strip()
        origen = (row.get("origen") or "").strip()
        scout = (row.get("scout") or "").strip()
        supervisor = (row.get("supervisor") or "").strip()
        driver_name = (row.get("nombre_driver") or "").strip()
        licencia = (row.get("licencia") or "").strip()
        telefono = (row.get("telefono") or "").strip()

        fecha_parsed = None
        if not fecha_str:
            errors.append({"row": line_num, "error": "fecha_afiliacion obligatoria"})
            fecha_parsed = None
        else:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    fecha_parsed = datetime.strptime(fecha_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not fecha_parsed:
                errors.append({"row": line_num, "error": f"Fecha invalida: {fecha_str}"})

        if not scout:
            errors.append({"row": line_num, "error": "scout obligatorio"})

        if not origen:
            errors.append({"row": line_num, "error": "origen obligatorio"})

        if not licencia and not telefono:
            errors.append({"row": line_num, "error": "licencia o telefono obligatorio"})

        norm_license = normalize_license(licencia)
        norm_phone = normalize_phone(telefono)

        match_result = _match_driver(db, licencia, telefono, driver_name)
        official_status = _check_official_source(db, match_result["matched_driver_id"])

        if errors and errors[-1]["row"] == line_num:
            review_status = "observed_error"
        elif match_result["match_status"] == "unmatched":
            review_status = "observed_pending_review"
        elif match_result["match_status"] == "manual_review":
            review_status = "observed_pending_review"
        else:
            review_status = "observed_pending_review"

        preview_lines.append({
            "row": line_num,
            "fecha_afiliacion": str(fecha_parsed) if fecha_parsed else fecha_str,
            "origen": origen,
            "scout": scout,
            "supervisor": supervisor,
            "nombre_driver": driver_name,
            "licencia": licencia,
            "telefono": telefono,
            "normalized_license": norm_license,
            "normalized_phone": norm_phone,
            "matched_driver_id": match_result["matched_driver_id"],
            "match_status": match_result["match_status"],
            "match_confidence": match_result["match_confidence"],
            "match_reason": match_result["match_reason"],
            "official_source_status": official_status,
            "review_status": review_status,
            "has_error": any(e["row"] == line_num for e in errors),
        })

    match_high = sum(1 for l in preview_lines if l["match_confidence"] == "high")
    match_medium = sum(1 for l in preview_lines if l["match_confidence"] == "medium")
    manual_review = sum(1 for l in preview_lines if l["match_status"] == "manual_review")
    unmatched = sum(1 for l in preview_lines if l["match_status"] == "unmatched")
    official_missing = sum(1 for l in preview_lines if l["official_source_status"] == "official_missing")
    error_count = sum(1 for l in preview_lines if l["has_error"])

    # Duplicate claim detection: same matched_driver_id OR same normalized_license
    # claimed by different scouts within the batch
    driver_scout_map: Dict[str, set] = {}
    license_scout_map: Dict[str, set] = {}
    for l in preview_lines:
        did = l.get("matched_driver_id")
        scout = l.get("scout")
        nlic = l.get("normalized_license", "")
        if did:
            driver_scout_map.setdefault(did, set()).add(scout)
        if nlic:
            license_scout_map.setdefault(nlic, set()).add(scout)

    duplicate_claims = 0
    conflicting_keys = set()
    for did, scouts in driver_scout_map.items():
        if len(scouts) > 1:
            conflicting_keys.add(did)
    for nlic, scouts in license_scout_map.items():
        if len(scouts) > 1:
            conflicting_keys.add(nlic)

    for l in preview_lines:
        did = l.get("matched_driver_id")
        nlic = l.get("normalized_license", "")
        if (did and did in conflicting_keys) or (nlic and nlic in conflicting_keys):
            if l.get("match_status") != "manual_review":
                l["match_status"] = "manual_review"
                l["match_confidence"] = None
                existing_reason = l.get("match_reason", "")
                if "duplicate_claim_same_driver_different_scout" not in existing_reason:
                    l["match_reason"] = (existing_reason + " | duplicate_claim_same_driver_different_scout").strip(" |")
                l["review_status"] = "manual_review"
                duplicate_claims += 1
                if l.get("match_confidence") == "medium":
                    match_medium -= 1
                manual_review += 1

    return {
        "total_rows": total,
        "lines": preview_lines,
        "errors": errors,
        "summary": {
            "total": total,
            "matched_high": match_high,
            "matched_medium": match_medium,
            "manual_review": manual_review,
            "unmatched": unmatched,
            "official_missing": official_missing,
            "errors": error_count,
            "valid": total - error_count,
            "duplicate_claims": duplicate_claims,
        },
    }


def apply_observed_affiliations(
    db: Session,
    rows: List[Dict[str, Any]],
    source_file_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aplica carga de atribuciones observadas.
    Guarda cada fila en scout_liq_observed_affiliations.
    Detecta duplicate claims: mismo driver_id reclamado por diferentes scouts.
    """
    saved_rows = []  # in-memory tracking for batch dedup
    saved = []
    errors = []
    duplicates = 0
    duplicate_claims = 0

    # Pre-scan for duplicate claims: same matched_driver_id or same normalized_license
    # with different scout within the batch
    row_matches = []
    for i, row in enumerate(rows):
        line_num = i + 2
        licencia = (row.get("licencia") or "").strip()
        telefono = (row.get("telefono") or "").strip()
        driver_name = (row.get("nombre_driver") or "").strip()
        match_result = _match_driver(db, licencia, telefono, driver_name)
        row_matches.append({
            "line_num": line_num,
            "scout": (row.get("scout") or "").strip(),
            "matched_driver_id": match_result["matched_driver_id"],
            "normalized_license": normalize_license(licencia),
        })

    # Find drivers claimed by multiple scouts (by driver_id OR license)
    driver_scout_map: Dict[str, set] = {}
    license_scout_map: Dict[str, set] = {}
    for rm in row_matches:
        did = rm["matched_driver_id"]
        nlic = rm["normalized_license"]
        if did:
            driver_scout_map.setdefault(did, set()).add(rm["scout"])
        if nlic:
            license_scout_map.setdefault(nlic, set()).add(rm["scout"])

    conflicting_drivers = {did for did, scouts in driver_scout_map.items() if len(scouts) > 1}
    conflicting_licenses = {nlic for nlic, scouts in license_scout_map.items() if len(scouts) > 1}

    for i, row in enumerate(rows):
        line_num = i + 2

        fecha_str = (row.get("fecha_afiliacion") or "").strip()
        origen = (row.get("origen") or "").strip()
        scout = (row.get("scout") or "").strip()
        supervisor = (row.get("supervisor") or "").strip()
        driver_name = (row.get("nombre_driver") or "").strip()
        licencia = (row.get("licencia") or "").strip()
        telefono = (row.get("telefono") or "").strip()

        fecha_parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                fecha_parsed = datetime.strptime(fecha_str, fmt).date()
                break
            except ValueError:
                continue

        if not fecha_parsed:
            errors.append({"row": line_num, "error": f"Fecha invalida: {fecha_str}"})
            continue

        match_result = _match_driver(db, licencia, telefono, driver_name)
        official_status = _check_official_source(db, match_result["matched_driver_id"])
        norm_license = normalize_license(licencia)
        norm_phone = normalize_phone(telefono)

        # Check in-memory batch duplicates first (same license + date + scout)
        already_in_batch = any(
            sr["norm_license"] == norm_license
            and sr["fecha"] == fecha_parsed
            and sr["scout"] == scout
            for sr in saved_rows
        )
        if already_in_batch:
            duplicates += 1
            continue

        existing = db.query(ObservedAffiliation).filter(
            ObservedAffiliation.normalized_license == norm_license,
            ObservedAffiliation.reported_affiliation_date == fecha_parsed,
            ObservedAffiliation.reported_scout_name == scout,
        ).first()

        if existing:
            duplicates += 1
            continue

        is_duplicate_claim = (
            (match_result["matched_driver_id"] and match_result["matched_driver_id"] in conflicting_drivers)
            or (norm_license and norm_license in conflicting_licenses)
        )

        if is_duplicate_claim:
            final_match_status = "manual_review"
            final_match_confidence = None
            final_match_reason = (match_result.get("match_reason", "") + " | duplicate_claim_same_driver_different_scout").strip(" |")
            final_review_status = "manual_review"
            duplicate_claims += 1
        else:
            final_match_status = match_result["match_status"]
            final_match_confidence = match_result["match_confidence"]
            final_match_reason = match_result["match_reason"]
            final_review_status = "observed_pending_review"

        oa = ObservedAffiliation(
            source_file_id=source_file_id,
            row_number=line_num,
            reported_affiliation_date=fecha_parsed,
            reported_origin=origen,
            reported_scout_name=scout,
            reported_supervisor_name=supervisor,
            reported_driver_name=driver_name,
            reported_license=licencia,
            reported_phone=telefono,
            normalized_license=norm_license,
            normalized_phone=norm_phone,
            matched_driver_id=match_result["matched_driver_id"],
            match_status=final_match_status,
            match_confidence=final_match_confidence,
            match_reason=final_match_reason,
            official_source_status=official_status,
            review_status=final_review_status,
            raw_payload=json.dumps(row, default=str),
        )
        db.add(oa)
        saved.append(oa)
        saved_rows.append({
            "norm_license": norm_license,
            "fecha": fecha_parsed,
            "scout": scout,
        })

    db.commit()

    return {
        "saved": len(saved),
        "duplicates": duplicates,
        "duplicate_claims": duplicate_claims,
        "errors": len(errors),
        "error_details": errors,
    }


def parse_observed_csv(file_content: bytes) -> List[Dict[str, Any]]:
    """Parsea archivo CSV de atribuciones observadas."""
    text_content = file_content.decode("utf-8-sig")
    reader = _csv.DictReader(io.StringIO(text_content))
    rows = []
    for row in reader:
        normalized = {}
        for k, v in row.items():
            key = _normalize_header(k)
            normalized[key] = v
        rows.append(normalized)
    return rows


def parse_observed_xlsx(file_content: bytes) -> List[Dict[str, Any]]:
    """Parsea archivo XLSX de atribuciones observadas."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
    ws = wb.active
    rows_raw = list(ws.iter_rows(values_only=True))
    if not rows_raw:
        return []
    headers = [_normalize_header(str(h or "")) for h in rows_raw[0]]
    rows = []
    for row_data in rows_raw[1:]:
        if all(v is None for v in row_data):
            continue
        normalized = {}
        for j, val in enumerate(row_data):
            if j < len(headers):
                normalized[headers[j]] = str(val) if val is not None else ""
        rows.append(normalized)
    return rows


def get_observed_for_cutoff(
    db: Session,
    window_from: Optional[date] = None,
    window_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Obtiene atribuciones observadas que deben incluirse en un corte.
    Filtra por review_status y ventana de fechas.
    """
    q = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.review_status.in_([
            "observed_pending_review",
            "observed_validated",
        ])
    )
    if window_from:
        q = q.filter(ObservedAffiliation.reported_affiliation_date >= window_from)
    if window_to:
        q = q.filter(ObservedAffiliation.reported_affiliation_date <= window_to)
    records = q.order_by(ObservedAffiliation.reported_affiliation_date).all()

    return [
        {
            "id": r.id,
            "reported_affiliation_date": str(r.reported_affiliation_date) if r.reported_affiliation_date else None,
            "reported_origin": r.reported_origin,
            "reported_scout_name": r.reported_scout_name,
            "reported_supervisor_name": r.reported_supervisor_name,
            "reported_driver_name": r.reported_driver_name,
            "reported_license": r.reported_license,
            "reported_phone": r.reported_phone,
            "matched_driver_id": r.matched_driver_id,
            "match_status": r.match_status,
            "match_confidence": r.match_confidence,
            "match_reason": r.match_reason,
            "official_source_status": r.official_source_status,
            "review_status": r.review_status,
            "review_notes": r.review_notes,
        }
        for r in records
    ]


def compute_observed_trip_counts(
    db: Session,
    driver_id: str,
    hire_date: date,
) -> Dict[str, int]:
    """
    Calcula viajes de un driver observado usando trips_2025/trips_2026.
    Los viajes se cuentan desde la fecha de afiliacion reportada.
    """
    result = {"trips_0_7_count": 0, "trips_8_14_count": 0, "trips_0_14_count": 0}
    if not driver_id or not hire_date:
        return result

    sql = text("""
        SELECT
            COALESCE(SUM(t.trips_0_7), 0)::int AS trips_0_7_count,
            COALESCE(SUM(t.trips_8_14), 0)::int AS trips_8_14_count
        FROM (SELECT :did AS driver_id, :hd AS hire_date) s
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= :hd
                      AND fecha_inicio_viaje < :hd + INTERVAL '7 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= :hd + INTERVAL '7 days'
                      AND fecha_inicio_viaje < :hd + INTERVAL '14 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2026
            WHERE conductor_id = :did
            UNION ALL
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= :hd
                      AND fecha_inicio_viaje < :hd + INTERVAL '7 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= :hd + INTERVAL '7 days'
                      AND fecha_inicio_viaje < :hd + INTERVAL '14 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2025
            WHERE conductor_id = :did
              AND :hd + INTERVAL '30 days' < '2026-01-01'::date
        ) t ON true
    """)

    try:
        row = db.execute(sql, {"did": driver_id, "hd": hire_date}).first()
        if row:
            t7 = row[0] or 0
            t14 = row[1] or 0
            result = {
                "trips_0_7_count": t7,
                "trips_8_14_count": t14,
                "trips_0_14_count": t7 + t14,
            }
    except Exception:
        pass

    return result


def check_double_payment_observed(
    db: Session,
    driver_id: str,
    cutoff_run_id: int,
) -> Dict[str, Any]:
    """
    Verifica duplicados antes de pagar un driver observado.
    - Si ya esta en PaidHistory con blocks_future_payment, bloquea.
    - Si ya esta en una linea oficial del mismo corte, prioriza oficial.
    """
    if not driver_id:
        return {"blocked": True, "reason": "blocked_no_driver_id", "explanation": "Sin driver_id resuelto"}

    existing_paid = db.execute(
        text("SELECT COUNT(*) FROM scout_liq_paid_history WHERE driver_id = :did AND blocks_future_payment = true"),
        {"did": driver_id},
    ).scalar()
    if existing_paid and existing_paid > 0:
        return {
            "blocked": True,
            "reason": "blocked_already_paid",
            "explanation": f"Driver {driver_id} ya tiene pago bloqueante en paid_history",
        }

    existing_official = db.query(CutoffDriverLine).filter(
        CutoffDriverLine.cutoff_run_id == cutoff_run_id,
        CutoffDriverLine.driver_id == driver_id,
        CutoffDriverLine.attribution_source == "official",
    ).first()
    if existing_official:
        return {
            "blocked": True,
            "reason": "duplicate_official",
            "explanation": f"Driver {driver_id} ya tiene linea oficial en este corte. Se prioriza la oficial.",
        }

    return {"blocked": False, "reason": None, "explanation": None}


def export_observed_affiliations_csv(db: Session) -> str:
    """Exporta todas las atribuciones observadas como CSV."""
    records = db.query(ObservedAffiliation).order_by(
        ObservedAffiliation.reported_affiliation_date.desc()
    ).all()

    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow([
        "id", "fecha_afiliacion", "origen", "scout", "supervisor",
        "nombre_driver", "licencia", "telefono",
        "licencia_normalizada", "telefono_normalizado",
        "matched_driver_id", "match_status", "match_confidence",
        "match_reason", "official_source_status", "review_status",
        "review_notes", "created_at",
    ])
    for r in records:
        writer.writerow([
            r.id,
            str(r.reported_affiliation_date) if r.reported_affiliation_date else "",
            r.reported_origin or "",
            r.reported_scout_name or "",
            r.reported_supervisor_name or "",
            r.reported_driver_name or "",
            r.reported_license or "",
            r.reported_phone or "",
            r.normalized_license or "",
            r.normalized_phone or "",
            r.matched_driver_id or "",
            r.match_status or "",
            r.match_confidence or "",
            r.match_reason or "",
            r.official_source_status or "",
            r.review_status or "",
            r.review_notes or "",
            str(r.created_at) if r.created_at else "",
        ])
    return buf.getvalue()


def list_observed_affiliations(
    db: Session,
    review_status: Optional[str] = None,
    match_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Lista atribuciones observadas con filtros."""
    q = db.query(ObservedAffiliation)
    if review_status:
        q = q.filter(ObservedAffiliation.review_status == review_status)
    if match_status:
        q = q.filter(ObservedAffiliation.match_status == match_status)

    total = q.count()
    records = q.order_by(
        ObservedAffiliation.reported_affiliation_date.desc()
    ).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "reported_affiliation_date": str(r.reported_affiliation_date) if r.reported_affiliation_date else None,
                "reported_origin": r.reported_origin,
                "reported_scout_name": r.reported_scout_name,
                "reported_supervisor_name": r.reported_supervisor_name,
                "reported_driver_name": r.reported_driver_name,
                "reported_license": r.reported_license,
                "reported_phone": r.reported_phone,
                "matched_driver_id": r.matched_driver_id,
                "match_status": r.match_status,
                "match_confidence": r.match_confidence,
                "match_reason": r.match_reason,
                "official_source_status": r.official_source_status,
                "review_status": r.review_status,
                "review_notes": r.review_notes,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in records
        ],
    }


def update_observed_review(
    db: Session,
    observed_id: int,
    review_status: str,
    review_notes: Optional[str] = None,
) -> Optional[Dict]:
    """Actualiza el estado de revision de una atribucion observada."""
    oa = db.query(ObservedAffiliation).filter(ObservedAffiliation.id == observed_id).first()
    if not oa:
        return None
    oa.review_status = review_status
    if review_notes:
        oa.review_notes = review_notes
    oa.updated_at = datetime.now()
    db.commit()
    return {
        "id": oa.id,
        "review_status": oa.review_status,
        "review_notes": oa.review_notes,
        "updated_at": str(oa.updated_at),
    }


def reprocess_unmatched_observed_affiliations(
    db: Session,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Reintenta match para observed_affiliations sin driver_id.
    Util cuando un conductor aparece en drivers posteriormente.

    Solo procesa registros con matched_driver_id IS NULL
    y review_status IN ('observed_pending_review', 'manual_review').

    Para cada registro:
    - Reintenta _match_driver con licencia/telefono originales
    - Si match unico: actualiza matched_driver_id, match_status, confidence, etc.
    - Si multiples matches: deja en manual_review con razon multiple_candidates
    - Si sin match: deja como esta
    - Crea audit trail en ReconciliationAudit por cada cambio
    """
    import json as _json
    from app.models.scout_liq import ReconciliationAudit

    candidates = db.query(ObservedAffiliation).filter(
        ObservedAffiliation.matched_driver_id.is_(None),
        ObservedAffiliation.review_status.in_([
            "observed_pending_review",
            "manual_review",
        ]),
    ).order_by(ObservedAffiliation.id.asc()).limit(limit).all()

    updated = 0
    skipped = 0
    manual_review_set = 0
    errors_info = []

    for oa in candidates:
        if not oa.reported_license and not oa.reported_phone:
            skipped += 1
            continue

        before_state = {
            "matched_driver_id": oa.matched_driver_id,
            "match_status": oa.match_status,
            "match_confidence": oa.match_confidence,
            "match_reason": oa.match_reason,
            "official_source_status": oa.official_source_status,
            "review_status": oa.review_status,
        }

        match_result = _match_driver(
            db,
            oa.reported_license or "",
            oa.reported_phone or "",
            oa.reported_driver_name or "",
        )

        if match_result["matched_driver_id"] is None:
            skipped += 1
            continue

        if match_result["match_status"] == "manual_review":
            oa.matched_driver_id = match_result["matched_driver_id"]
            oa.match_status = "manual_review"
            oa.match_confidence = None
            oa.match_reason = (match_result.get("match_reason", "") or "multiple_candidates_in_drivers")
            oa.review_status = "manual_review"
            manual_review_set += 1
        else:
            oa.matched_driver_id = match_result["matched_driver_id"]
            oa.match_status = match_result["match_status"]
            oa.match_confidence = match_result["match_confidence"]
            oa.match_reason = match_result["match_reason"]
            official_status = _check_official_source(db, match_result["matched_driver_id"])
            oa.official_source_status = official_status
            if oa.review_status not in ("manual_review",):
                oa.review_status = "observed_pending_review"
            updated += 1

        oa.updated_at = datetime.now()

        after_state = {
            "matched_driver_id": oa.matched_driver_id,
            "match_status": oa.match_status,
            "match_confidence": oa.match_confidence,
            "match_reason": oa.match_reason,
            "official_source_status": oa.official_source_status,
            "review_status": oa.review_status,
        }

        audit = ReconciliationAudit(
            driver_id=oa.matched_driver_id or "unknown",
            observed_affiliation_id=oa.id,
            action="reprocess_unmatched",
            before_state=_json.dumps(before_state),
            after_state=_json.dumps(after_state),
            actor="system_operator",
            reason=f"Reprocess unmatched: new match found for driver_id={oa.matched_driver_id}",
            reconciliation_status="done",
        )
        db.add(audit)

    db.commit()

    return {
        "total_candidates": len(candidates),
        "updated": updated,
        "manual_review_set": manual_review_set,
        "skipped": skipped,
        "errors": errors_info,
    }
