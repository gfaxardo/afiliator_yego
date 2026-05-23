"""
Drivers Adapter — Acceso SOLO LECTURA a la tabla drivers.

La tabla drivers sirve como fuente maestra de identidad para resolver
driver_id por licencia o telefono, especialmente para conductores que
NO aparecen en module_ct_cabinet_drivers pero SI existen en drivers.

Columnas reales de drivers (confirmado via information_schema):
- driver_id (varchar, NOT NULL)
- first_name, last_name, full_name
- phone
- license_number, license_normalized_number
- hire_date, work_status, active
- park_id, car_id, car_number, etc.
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

DRIVERS_TABLE = "drivers"


def get_driver_by_license(db: Session, normalized_license: str) -> Optional[Dict]:
    """Busca driver por numero de licencia normalizada."""
    if not normalized_license:
        return None
    row = db.execute(text(
        f"SELECT driver_id, full_name, phone, license_number, license_normalized_number "
        f"FROM {DRIVERS_TABLE} "
        f"WHERE license_normalized_number = :lic "
        f"   OR license_number = :lic2 "
        f"LIMIT 1"
    ), {"lic": normalized_license, "lic2": normalized_license}).first()
    if not row:
        return None
    return {
        "driver_id": row[0],
        "full_name": row[1],
        "phone": row[2],
        "license_number": row[3],
        "license_normalized_number": row[4],
    }


def get_driver_by_phone(db: Session, normalized_phone: str) -> List[Dict]:
    """Busca drivers por numero de telefono normalizado. Puede retornar multiples."""
    if not normalized_phone or len(normalized_phone) < 7:
        return []
    rows = db.execute(text(
        f"SELECT driver_id, full_name, phone, license_number, license_normalized_number "
        f"FROM {DRIVERS_TABLE} "
        f"WHERE phone IS NOT NULL "
        f"  AND REGEXP_REPLACE(phone, '[^0-9]', '', 'g') = :phone "
        f"LIMIT 10"
    ), {"phone": normalized_phone}).fetchall()
    return [
        {
            "driver_id": row[0],
            "full_name": row[1],
            "phone": row[2],
            "license_number": row[3],
            "license_normalized_number": row[4],
        }
        for row in rows
    ]


def get_driver_by_id(db: Session, driver_id: str) -> Optional[Dict]:
    """Obtiene driver por driver_id."""
    if not driver_id:
        return None
    row = db.execute(text(
        f"SELECT driver_id, full_name, phone, license_number, license_normalized_number "
        f"FROM {DRIVERS_TABLE} WHERE driver_id = :did LIMIT 1"
    ), {"did": driver_id}).first()
    if not row:
        return None
    return {
        "driver_id": row[0],
        "full_name": row[1],
        "phone": row[2],
        "license_number": row[3],
        "license_normalized_number": row[4],
    }


def check_driver_in_official_source(db: Session, driver_id: str) -> bool:
    """Verifica si un driver_id existe en module_ct_cabinet_drivers (fuente oficial)."""
    if not driver_id:
        return False
    row = db.execute(text(
        "SELECT 1 FROM module_ct_cabinet_drivers WHERE driver_id = :did LIMIT 1"
    ), {"did": driver_id}).scalar()
    return row is not None
