"""
Reconciliation Service — Contrasta sistema vs pagos reales (CSV/Sheets).

NO modifica fuentes. NO hardcodea reglas.
Exporta estado esperado del sistema y compara contra CSV subido.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.services.canonical_operation_service import (
    get_canonical_operation_snapshot,
    _parse_canonical_rule,
    _driver_meets_rule,
    _batch_trip_counts,
)
from app.services.cohort_service import iso_week_dates, cohort_maturity


SOURCE_TABLE = settings.SOURCE_TABLE


def _iso_week_of(date_val: date) -> str:
    iso = date_val.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def export_reconciliation_csv(
    db: Session,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    scheme_type: Optional[str] = None,
    pay_until_date: Optional[date] = None,
    only_matured: bool = False,
    limit: int = 10000,
) -> str:
    """
    Genera CSV de conciliacion con el estado esperado por el sistema.
    Cada fila = un driver con su expected_payment_status y expected_amount.
    """
    snapshot = get_canonical_operation_snapshot(
        db,
        hire_date_from=hire_date_from,
        hire_date_to=hire_date_to,
        scheme_type=scheme_type,
        limit=limit,
        offset=0,
    )

    items = snapshot.get("items", [])

    # ── Batch paid history and manual overrides ──
    driver_ids = [it["driver_id"] for it in items if it.get("driver_id")]
    paid_map = _batch_paid_history(db, driver_ids)
    override_map = _batch_manual_overrides(db, driver_ids)

    # ── Resolve scheme rules ──
    vol_min, vol_days = 1, 7
    qual_min, qual_days = 5, 7
    pays_on = "ACTIVATED_BASE"
    resolved_scheme_type = scheme_type or "cabinet"
    if scheme_type:
        try:
            from app.services.payment_scheme_resolver import resolve_payment_scheme_for_cohort
            latest = _get_latest_cohort(db)
            if latest:
                resolved = resolve_payment_scheme_for_cohort(db, latest, scheme_type)
                vol_min, vol_days = _parse_canonical_rule(resolved.get("volume_rule", "1V7D"))
                qual_min, qual_days = _parse_canonical_rule(resolved.get("quality_rule", "5V7D"))
                pays_on = resolved.get("pays_on_rule", "") or "ACTIVATED_BASE"
        except ValueError:
            pass

    # ── Build CSV ──
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([
        "driver_id", "driver_name", "license", "hire_date",
        "cohort_iso_week", "scheme_type",
        "scout_id", "scout_name", "attribution_status",
        "maturity_status",
        "trips_7d", "trips_14d", "trips_0_30",
        "counts_for_volume", "counts_for_quality", "counts_for_payment",
        "expected_payment_status", "expected_amount",
        "payment_origin", "paid_history_id", "manual_override_id",
        "reconciliation_status", "reconciliation_reason",
    ])

    today = date.today()

    for it in items:
        did = it.get("driver_id", "")
        driver_trips = {
            "trips_0_7": it.get("trips_7d", 0) or 0,
            "trips_8_14": (it.get("trips_14d", 0) or 0) - (it.get("trips_7d", 0) or 0),
            "trips_0_30": it.get("trips_0_30", 0) or 0,
        }

        meets_volume = _driver_meets_rule(driver_trips, vol_min, vol_days)
        meets_quality = _driver_meets_rule(driver_trips, qual_min, qual_days)

        # ── Maturity check ──
        hire_date_str = it.get("hire_date", "")
        maturity_status = "unknown"
        try:
            hd = datetime.strptime(str(hire_date_str).strip(), "%Y-%m-%d").date()
            iso_week = _iso_week_of(hd)
            iso_from, iso_to = iso_week_dates(iso_week)
            mature_at = iso_to
            if scheme_type == "fleet":
                mature_at = cohort_maturity(iso_to, 30)
            else:
                mature_at = cohort_maturity(iso_to, 7)
            maturity_status = "mature" if today >= mature_at else "open"
        except (ValueError, TypeError):
            iso_week = ""

        # ── Expected payment ──
        expected_status = it.get("payment_status", "not_payable")
        expected_amount = it.get("amount") or 0

        # ── Override / paid history info ──
        payments = paid_map.get(did, [])
        paid_history_id = payments[0]["id"] if payments else None
        overrides = override_map.get(did, [])
        manual_override_id = overrides[0]["id"] if overrides else None

        # ── Reconciliation status ──
        recon_status, recon_reason = _build_recon_status(
            expected_status, expected_amount, payments, overrides,
            maturity_status, meets_volume, meets_quality, pays_on
        )

        writer.writerow([
            did,
            it.get("driver_name", ""),
            it.get("license", ""),
            hire_date_str,
            iso_week,
            resolved_scheme_type,
            it.get("scout_id") or "",
            it.get("scout_name", ""),
            it.get("attribution_status", "unassigned"),
            maturity_status,
            it.get("trips_7d", 0),
            it.get("trips_14d", 0),
            it.get("trips_0_30", 0),
            str(meets_volume).lower(),
            str(meets_quality).lower(),
            str(it.get("counts_for_payment", False)).lower(),
            expected_status,
            f"{float(expected_amount):.2f}" if expected_amount else "0.00",
            it.get("payment_origin", "none"),
            paid_history_id or "",
            manual_override_id or "",
            recon_status,
            recon_reason,
        ])

    return buf.getvalue()


def _build_recon_status(
    expected_status: str,
    expected_amount: float,
    payments: List[dict],
    overrides: List[dict],
    maturity_status: str,
    meets_volume: bool,
    meets_quality: bool,
    pays_on: str,
) -> tuple:
    """
    Build reconciliation_status and reconciliation_reason for a driver.
    """
    if expected_status == "paid":
        if any(ov.get("override_type") == "force_pay" for ov in overrides):
            return ("manual_override", "Pago manual autorizado")
        if payments:
            latest = payments[0]
            if latest.get("import_source") == "historical_upload":
                return ("historical_paid", "Pagado historico registrado")
            if latest.get("import_source") == "cutoff_engine":
                return ("cutoff_paid", "Pagado por cutoff del sistema")
            return ("system_paid", "Pagado por el sistema")
        return ("expected_to_pay", "Esperado pagable pero sin registro de pago")
    elif expected_status == "payable":
        if maturity_status == "open":
            return ("pending_maturity", "Ventana aun no ha madurado")
        if payments:
            return ("already_paid", "Ya tiene registro de pago")
        return ("expected_to_pay", "Pagable pero no pagado aun")
    elif expected_status == "not_payable":
        if any(ov.get("override_type") == "force_exclude" for ov in overrides):
            return ("manual_exclude", "Excluido manualmente")
        if not meets_volume:
            return ("no_activation", "No cumple regla de volumen")
        return ("not_payable", "No pagable por regla")
    return ("unknown", "Estado desconocido")


def compare_upload(
    db: Session,
    csv_content: str,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    scheme_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compara CSV subido (pagos reales) contra el estado del sistema.
    El CSV debe tener columnas: driver_id, amount_paid, currency (opcional),
    y opcionalmente scout_name, payment_date, notes.

    Retorna resumen de conciliacion + fila por fila con diferencias.
    """
    # ── Parse uploaded CSV ──
    reader = csv.DictReader(io.StringIO(csv_content))
    upload_rows = list(reader)

    if not upload_rows:
        return {"error": "CSV vacio o sin columnas validas"}

    # ── Normalize headers ──
    header_map = _normalize_headers(list(upload_rows[0].keys()))
    normalized_rows = []
    for row in upload_rows:
        nr = {}
        for k, v in row.items():
            mapped = header_map.get(k.strip().lower(), k.strip().lower())
            nr[mapped] = (v or "").strip()
        normalized_rows.append(nr)

    # ── Get system state ──
    system_items = _get_system_state(db, hire_date_from, hire_date_to, scheme_type)

    # ── Compare ──
    total_rows = len(normalized_rows)
    matched_rows = 0
    unmatched_rows = 0
    amount_mismatch = 0
    already_paid_count = 0
    missing_in_system = 0
    missing_in_upload = 0
    details: List[dict] = []

    for row in normalized_rows:
        did = row.get("driver_id", row.get("license", ""))
        if not did:
            details.append({
                "driver_id": "",
                "driver_name": "",
                "status": "invalid_row",
                "reason": "Sin driver_id ni license",
                "system_amount": None, "upload_amount": _parse_amount(row.get("amount_paid", "0")),
                "system_scout": "", "upload_scout": row.get("scout_name", ""),
                "suggested_action": "Agregar driver_id o license",
            })
            unmatched_rows += 1
            continue

        upload_amount = _parse_amount(row.get("amount_paid", "0"))
        upload_scout = row.get("scout_name", "")

        sys = system_items.get(did)

        if not sys:
            details.append({
                "driver_id": did,
                "driver_name": row.get("driver_name", ""),
                "status": "missing_in_system",
                "reason": f"Driver {did} no encontrado en el sistema",
                "system_amount": None, "upload_amount": upload_amount,
                "system_scout": "", "upload_scout": upload_scout,
                "suggested_action": "Verificar driver_id en fuente",
            })
            missing_in_system += 1
            unmatched_rows += 1
            continue

        sys_amount = sys.get("expected_amount", 0) or 0
        sys_status = sys.get("expected_status", "not_payable")
        sys_scout = sys.get("scout_name", "")

        # ── Determine match type ──
        detail = {
            "driver_id": did,
            "driver_name": sys.get("driver_name", ""),
            "system_status": sys_status,
            "system_amount": sys_amount,
            "upload_amount": upload_amount,
            "system_scout": sys_scout,
            "upload_scout": upload_scout,
            "system_paid_history_id": sys.get("paid_history_id"),
            "system_manual_override_id": sys.get("manual_override_id"),
        }

        if sys.get("already_paid") and upload_amount > 0:
            detail["status"] = "already_paid"
            detail["reason"] = "Driver ya pagado en el sistema"
            detail["suggested_action"] = "Verificar si es duplicado"
            already_paid_count += 1
            matched_rows += 1
        elif abs(float(sys_amount) - float(upload_amount)) > 0.01:
            detail["status"] = "amount_mismatch"
            detail["reason"] = f"Sistema espera {sys_amount:.2f}, upload dice {upload_amount:.2f}"
            detail["suggested_action"] = "Revisar monto correcto"
            amount_mismatch += 1
            unmatched_rows += 1
        elif upload_scout and sys_scout and upload_scout.lower() != sys_scout.lower():
            detail["status"] = "scout_mismatch"
            detail["reason"] = f"Scout sistema: {sys_scout}, upload: {upload_scout}"
            detail["suggested_action"] = "Verificar asignacion de scout"
            unmatched_rows += 1
        elif sys_status == "paid" and upload_amount > 0:
            detail["status"] = "ok"
            detail["reason"] = "Sistema y upload coinciden"
            detail["suggested_action"] = None
            matched_rows += 1
        elif upload_amount > 0 and float(sys_amount or 0) == 0:
            detail["status"] = "unexpected_payment"
            detail["reason"] = "Upload pago registrado pero sistema no espera pago"
            detail["suggested_action"] = "Verificar si es pago manual valido"
            unmatched_rows += 1
        else:
            detail["status"] = "ok"
            detail["reason"] = "Coinciden"
            detail["suggested_action"] = None
            matched_rows += 1

        details.append(detail)

    # ── Detect missing in upload (system expects payment but not in upload) ──
    upload_dids = set()
    for row in normalized_rows:
        did = row.get("driver_id", row.get("license", ""))
        if did:
            upload_dids.add(did)

    for did, sys in system_items.items():
        if did not in upload_dids:
            exp_amount = sys.get("expected_amount", 0) or 0
            if float(exp_amount) > 0 or sys.get("expected_status") in ("payable", "paid"):
                missing_in_upload += 1
                details.append({
                    "driver_id": did,
                    "driver_name": sys.get("driver_name", ""),
                    "status": "missing_in_upload",
                    "reason": "Sistema espera pago pero no aparece en upload",
                    "system_amount": exp_amount,
                    "upload_amount": 0,
                    "system_scout": sys.get("scout_name", ""),
                    "upload_scout": "",
                    "suggested_action": "Verificar si falta cargar pago",
                })

    return {
        "total_rows": total_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "amount_mismatch": amount_mismatch,
        "already_paid": already_paid_count,
        "missing_in_system": missing_in_system,
        "missing_in_upload": missing_in_upload,
        "details": details,
        "suggested_actions": _build_suggested_actions(
            amount_mismatch, already_paid_count,
            missing_in_system, missing_in_upload
        ),
    }


def _get_system_state(
    db: Session,
    hire_date_from: Optional[date] = None,
    hire_date_to: Optional[date] = None,
    scheme_type: Optional[str] = None,
) -> Dict[str, dict]:
    """Get compact system state indexed by driver_id."""
    snapshot = get_canonical_operation_snapshot(
        db,
        hire_date_from=hire_date_from,
        hire_date_to=hire_date_to,
        scheme_type=scheme_type,
        limit=10000,
        offset=0,
    )

    items = snapshot.get("items", [])
    driver_ids = [it["driver_id"] for it in items if it.get("driver_id")]
    paid_map = _batch_paid_history(db, driver_ids)
    override_map = _batch_manual_overrides(db, driver_ids)

    result = {}
    for it in items:
        did = it["driver_id"]
        if not did:
            continue
        payments = paid_map.get(did, [])
        overrides = override_map.get(did, [])

        result[did] = {
            "driver_id": did,
            "driver_name": it.get("driver_name", ""),
            "scout_name": it.get("scout_name", ""),
            "scout_id": it.get("scout_id"),
            "expected_status": it.get("payment_status", "not_payable"),
            "expected_amount": it.get("amount") or 0,
            "already_paid": bool(payments),
            "has_manual_override": bool(overrides),
            "paid_history_id": payments[0]["id"] if payments else None,
            "manual_override_id": overrides[0]["id"] if overrides else None,
        }

    return result


def _batch_paid_history(db: Session, driver_ids: List[str]) -> Dict[str, List[dict]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    rows = db.execute(text(f"""
        SELECT id, driver_id, scout_id, amount_paid, currency, paid_at,
               import_source, payment_rule, payment_scheme_name, blocks_future_payment, status
        FROM scout_liq_paid_history
        WHERE driver_id IN ({placeholders})
        ORDER BY paid_at DESC
    """), params).fetchall()

    result: Dict[str, List[dict]] = {}
    for r in rows:
        did = r[1]
        if did not in result:
            result[did] = []
        result[did].append({
            "id": r[0], "driver_id": did, "scout_id": r[2],
            "amount_paid": float(r[3]) if r[3] else None,
            "currency": r[4], "paid_at": str(r[5]) if r[5] else None,
            "import_source": r[6], "payment_rule": r[7],
            "payment_scheme_name": r[8],
            "blocks_future_payment": r[9], "status": r[10],
        })
    return result


def _batch_manual_overrides(db: Session, driver_ids: List[str]) -> Dict[str, List[dict]]:
    if not driver_ids:
        return {}
    placeholders = ", ".join(f":did{i}" for i in range(len(driver_ids)))
    params = {f"did{i}": did for i, did in enumerate(driver_ids)}
    rows = db.execute(text(f"""
        SELECT id, driver_id, override_type, amount, reason, status, blocks_future_payment, paid_history_id
        FROM scout_liq_manual_overrides
        WHERE driver_id IN ({placeholders}) AND status = 'applied'
        ORDER BY created_at DESC
    """), params).fetchall()

    result: Dict[str, List[dict]] = {}
    for r in rows:
        did = r[1]
        if did not in result:
            result[did] = []
        result[did].append({
            "id": r[0], "driver_id": did, "override_type": r[2],
            "amount": float(r[3]) if r[3] else None,
            "reason": r[4], "status": r[5],
            "blocks_future_payment": r[6], "paid_history_id": r[7],
        })
    return result


def _get_latest_cohort(db: Session) -> Optional[str]:
    try:
        row = db.execute(text(
            "SELECT MAX(EXTRACT(ISOYEAR FROM hire_date::date)) || '-W' || "
            "LPAD(MAX(EXTRACT(WEEK FROM hire_date::date))::text, 2, '0') "
            f"FROM {SOURCE_TABLE} WHERE hire_date IS NOT NULL AND hire_date != ''"
        )).scalar()
        return row
    except Exception:
        return None


def _normalize_headers(headers: List[str]) -> Dict[str, str]:
    known = {
        "driver_id": "driver_id",
        "driver id": "driver_id",
        "conductor_id": "driver_id",
        "license": "license",
        "licencia": "license",
        "amount_paid": "amount_paid",
        "amount": "amount_paid",
        "monto": "amount_paid",
        "pago": "amount_paid",
        "scout_name": "scout_name",
        "scout": "scout_name",
        "payment_date": "payment_date",
        "fecha_pago": "payment_date",
        "notes": "notes",
        "notas": "notes",
        "currency": "currency",
        "moneda": "currency",
    }
    result = {}
    for h in headers:
        result[h] = known.get(h, h)
    return result


def _parse_amount(val: str) -> float:
    try:
        return float(str(val).replace(",", "").replace("S/", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _build_suggested_actions(
    amount_mismatch: int,
    already_paid: int,
    missing_in_system: int,
    missing_in_upload: int,
) -> List[str]:
    actions = []
    if amount_mismatch > 0:
        actions.append(f"Corregir {amount_mismatch} montos con diferencia")
    if already_paid > 0:
        actions.append(f"Revisar {already_paid} pagos ya registrados (posible duplicado)")
    if missing_in_system > 0:
        actions.append(f"Investigar {missing_in_system} drivers no encontrados en el sistema")
    if missing_in_upload > 0:
        actions.append(f"Cargar {missing_in_upload} pagos que el sistema espera")
    if not actions:
        actions.append("Sin acciones pendientes — sistema y upload coinciden")
    return actions
