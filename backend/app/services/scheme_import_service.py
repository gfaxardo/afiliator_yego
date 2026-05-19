"""
Scheme Import Service - Fase 4.
Importa esquemas de pago historicos desde Excel y gestiona versionado.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.scout_liq import SchemeVersion, SchemeChangeLog


def parse_date_safe(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    try:
        ts = float(val)
        return datetime.fromtimestamp(ts).date()
    except (ValueError, TypeError):
        pass
    return None


def preview_scheme_import(db: Session, rows: List[dict], sheet: str = "") -> Dict[str, Any]:
    result = {
        "sheet": sheet,
        "total_rows": len(rows),
        "will_import": 0,
        "will_skip": 0,
        "errors": 0,
        "lines": [],
    }

    for i, row in enumerate(rows):
        line = _classify_scheme_row(row, sheet, i + 2)
        result["lines"].append(line)
        if line["status"] == "ready":
            result["will_import"] += 1
        elif line["status"] == "skip":
            result["will_skip"] += 1
        else:
            result["errors"] += 1

    return result


def _classify_scheme_row(row: dict, sheet: str, row_num: int) -> dict:
    base = {
        "source_sheet": sheet,
        "source_row": row_num,
        "status": "ready",
        "reason": None,
    }

    scheme_name = str(row.get("MODALIDAD", row.get("REGLA", row.get("SCHEME_NAME", "")))).strip()
    meta = str(row.get("META", row.get("UMBRAL_MIN_5_SOBRE_1", ""))).strip()
    monto = str(row.get("MONTO", row.get("TARIFA_UNITARIA", ""))).strip()
    orden = str(row.get("ORDEN", ""))
    inicio = str(row.get("INICIO VIGENCIA", row.get("FECHA_INICIO", row.get("DESDE", "")))).strip()
    fin = str(row.get("FIN VIGENCIA", row.get("FECHA_FIN", row.get("HASTA", "")))).strip()
    medio = str(row.get("MEDIO", row.get("MEDIO DE ADQUISICION", ""))).strip()
    activo = str(row.get("ACTIVO", row.get("ESTADO", ""))).strip().upper()
    obs = str(row.get("OBS", row.get("OBSERVACIONES", ""))).strip()

    base["scheme_name"] = scheme_name or "Sin nombre"
    base["medio"] = medio
    base["meta"] = meta
    base["monto"] = monto
    base["inicio"] = inicio
    base["fin"] = fin

    if not scheme_name:
        base["status"] = "error"
        base["reason"] = "sin nombre de esquema"
        return base

    if sheet.lower().startswith("esquema de pagos") or sheet.lower().startswith("mapeo_hitos"):
        scheme_type = "legacy_milestone"
    elif sheet.lower().startswith("esquema_calidad"):
        scheme_type = "quality_conversion"
    else:
        scheme_type = "legacy_milestone"

    valid_from = parse_date_safe(inicio)
    valid_to = parse_date_safe(fin)

    is_active = activo not in ("INACTIVO", "FALSE", "DESACTIVADO", "NO", "0")

    config = {
        "medio": medio,
        "meta": meta,
        "monto": monto,
        "orden": int(orden) if orden.isdigit() else None,
        "observaciones": obs,
    }

    base["scheme_type"] = scheme_type
    base["valid_from"] = str(valid_from) if valid_from else None
    base["valid_to"] = str(valid_to) if valid_to else None
    base["active"] = is_active
    base["config_json"] = json.dumps(config)

    # Check duplicate
    existing = db.query(SchemeVersion).filter(
        SchemeVersion.scheme_name == scheme_name,
        SchemeVersion.scheme_type == scheme_type,
        SchemeVersion.valid_from == valid_from,
        SchemeVersion.source_sheet == sheet,
        SchemeVersion.source_row == row_num,
    ).first()
    if existing:
        base["status"] = "skip"
        base["reason"] = f"ya existe (id={existing.id})"

    return base


def commit_scheme_import(db: Session, preview_result: Dict[str, Any],
                           created_by: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "sheet": preview_result.get("sheet"),
        "total_rows": preview_result.get("total_rows", 0),
        "created": 0,
        "skipped": 0,
        "errors": 0,
    }

    for line in preview_result.get("lines", []):
        if line.get("status") == "skip":
            result["skipped"] += 1
            continue
        if line.get("status") != "ready":
            result["errors"] += 1
            continue

        valid_from = parse_date_safe(line.get("inicio"))
        valid_to = parse_date_safe(line.get("fin"))

        sv = SchemeVersion(
            scheme_name=line.get("scheme_name", "Sin nombre"),
            scheme_type=line.get("scheme_type", "legacy_milestone"),
            origin=line.get("medio"),
            valid_from=valid_from,
            valid_to=valid_to,
            active=line.get("active", True),
            config_json=line.get("config_json"),
            source_sheet=line.get("source_sheet"),
            source_row=line.get("source_row"),
            created_by=created_by,
            change_reason="importado desde archivo historico",
        )
        db.add(sv)
        result["created"] += 1

    db.commit()
    return result


def get_scheme_versions(db: Session, scheme_type: Optional[str] = None,
                         active_only: Optional[bool] = None) -> List[dict]:
    q = db.query(SchemeVersion)
    if scheme_type:
        q = q.filter(SchemeVersion.scheme_type == scheme_type)
    if active_only is True:
        q = q.filter(SchemeVersion.active == True)
    rows = q.order_by(SchemeVersion.valid_from.desc().nullslast(), SchemeVersion.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "scheme_name": r.scheme_name,
            "scheme_type": r.scheme_type,
            "origin": r.origin,
            "scout_type": r.scout_type,
            "valid_from": str(r.valid_from) if r.valid_from else None,
            "valid_to": str(r.valid_to) if r.valid_to else None,
            "active": r.active,
            "config_json": r.config_json,
            "source_sheet": r.source_sheet,
            "source_row": r.source_row,
            "created_by": r.created_by,
            "created_at": str(r.created_at) if r.created_at else None,
            "change_reason": r.change_reason,
        }
        for r in rows
    ]


def get_scheme_change_log(db: Session, scheme_id: Optional[int] = None) -> List[dict]:
    q = db.query(SchemeChangeLog)
    if scheme_id:
        q = q.filter(SchemeChangeLog.scheme_id == scheme_id)
    rows = q.order_by(SchemeChangeLog.changed_at.desc()).all()

    return [
        {
            "id": r.id,
            "scheme_id": r.scheme_id,
            "old_config_json": r.old_config_json,
            "new_config_json": r.new_config_json,
            "changed_by": r.changed_by,
            "changed_at": str(r.changed_at) if r.changed_at else None,
            "reason": r.reason,
        }
        for r in rows
    ]
