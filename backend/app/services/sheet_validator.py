"""
Sheet Validator - Fase 4.6 fix.
Maps sheet names to import types and validates sheet-type routing.
"""

import time
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("scout_liq")

# Master sheet-to-type mapping
# format: sheet_name_pattern -> (import_type, allowed_endpoints)
SHEET_TYPE_MAP: Dict[str, Tuple[str, str]] = {
    "01_PAGOS_HISTORICOS": ("historical_payments", "historical-imports"),
    "02_SCOUTS": ("scouts_bulk", "scouts"),
    "03_ESQUEMAS": ("schemes", "schemes"),
    "04_PAGOS_MANUALES": ("manual_payments", "manual-payments"),
    "05_SUPERVISORES_BONOS": ("supervisor_bonus", "commissions-bonuses"),
    "06_ATRIBUCIONES_HISTORICAS": ("historical_attributions", "attributions"),
    "00_README": ("reference_only", None),
    "LISTAS": ("reference_only", None),
    "VALIDACIONES_IMPORT": ("reference_only", None),
    # Original Excel sheets
    "ESQUEMA DE PAGOS": ("schemes", "schemes"),
    "ESQUEMA_CALIDAD_CONVERSION": ("schemes", "schemes"),
    "MAPEO_HITOS": ("schemes", "schemes"),
    "ESQUEMA_SCOUTS": ("scouts_bulk", "scouts"),
    "PADRON_SCOUTS": ("scouts_bulk", "scouts"),
    "LIQUIDACION_DETALLE": ("historical_payments", "historical-imports"),
    "LIQUIDACION_RESUMEN": ("historical_payments", "historical-imports"),
    "LIQUIDACION_AUDITORIA": ("historical_attributions", "attributions"),
    "Registros-conductores": ("historical_payments", "historical-imports"),
    "dg-corte pagos manuales": ("historical_payments", "historical-imports"),
}


def classify_sheet(sheet_name: str) -> Tuple[str, Optional[str]]:
    """Returns (import_type, endpoint_group) for a sheet name."""
    name = sheet_name.strip() if sheet_name else ""
    if name in SHEET_TYPE_MAP:
        return SHEET_TYPE_MAP[name]
    return ("unknown", None)


def validate_sheet_for_endpoint(sheet_name: str, expected_endpoint: str) -> Tuple[bool, str, str]:
    """Validates a sheet against an expected endpoint group.
    Returns (is_valid, import_type, error_message).
    """
    import_type, endpoint_group = classify_sheet(sheet_name)

    if import_type == "unknown":
        return (False, import_type,
                f"Hoja '{sheet_name}' no reconocida. Las hojas validas para {expected_endpoint} son: "
                f"{', '.join(get_sheets_for_endpoint(expected_endpoint))}")

    if import_type == "reference_only":
        return (False, import_type,
                f"Hoja '{sheet_name}' es solo de referencia. No se puede importar.")

    if endpoint_group != expected_endpoint:
        valid_sheets = ", ".join(get_sheets_for_endpoint(expected_endpoint))
        return (False, import_type,
                f"Hoja '{sheet_name}' es de tipo '{import_type}'. "
                f"No se puede procesar como {expected_endpoint}. "
                f"Hojas validas: {valid_sheets}")

    return (True, import_type, "")


def get_sheets_for_endpoint(expected_endpoint: str) -> List[str]:
    """Returns sheet names valid for a given endpoint."""
    return [k for k, (_, ep) in SHEET_TYPE_MAP.items() if ep == expected_endpoint]


def get_sheet_type_label(import_type: str) -> str:
    labels = {
        "historical_payments": "Pagos historicos",
        "scouts_bulk": "Scouts masivo",
        "schemes": "Esquemas",
        "manual_payments": "Pagos manuales",
        "supervisor_bonus": "Supervisores y bonos",
        "historical_attributions": "Atribuciones historicas",
        "reference_only": "Solo referencia",
        "unknown": "Desconocido",
    }
    return labels.get(import_type, import_type)


# ── Structured logging ──

def log_preview_start(import_type: str, source_file: str, sheet_name: str, total_rows: int):
    logger.info(
        "[SCOUT_LIQ_IMPORT] preview_start import_type=%s file=%s sheet=%s rows=%s",
        import_type, source_file, sheet_name, total_rows,
    )


def log_preview_done(import_type: str, batch_id: Optional[int] = None,
                     total_rows: int = 0, ready: int = 0, review: int = 0,
                     rejected: int = 0, duplicate: int = 0,
                     amount_ready: float = 0, elapsed_ms: float = 0,
                     top_errors: Optional[Dict[str, int]] = None):
    errors_str = str(top_errors) if top_errors else "{}"
    logger.info(
        "[SCOUT_LIQ_IMPORT] preview_done import_type=%s batch_id=%s rows=%s ready=%s "
        "review=%s rejected=%s dup=%s amount_ready=%s elapsed_ms=%s top_errors=%s",
        import_type, batch_id, total_rows, ready, review, rejected, duplicate,
        amount_ready, elapsed_ms, errors_str,
    )


def log_preview_error(import_type: str, sheet_name: str, error: str):
    logger.error(
        "[SCOUT_LIQ_IMPORT] preview_error import_type=%s sheet=%s error=%s",
        import_type, sheet_name, error,
    )


def log_wrong_sheet(expected: str, received: str):
    logger.warning(
        "[SCOUT_LIQ_IMPORT] wrong_sheet_for_import expected=%s received=%s",
        expected, received,
    )


def log_commit_start(import_type: str, batch_id: int):
    logger.info(
        "[SCOUT_LIQ_IMPORT] commit_start import_type=%s batch_id=%s",
        import_type, batch_id,
    )


def log_commit_done(import_type: str, batch_id: int, result: dict, elapsed_ms: float):
    logger.info(
        "[SCOUT_LIQ_IMPORT] commit_done import_type=%s batch_id=%s result=%s elapsed_ms=%s",
        import_type, batch_id, str(result), elapsed_ms,
    )
