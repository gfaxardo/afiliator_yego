"""
Normalization Service — Funciones puras para limpiar identificadores.

Normaliza licencias, telefonos y nombres para matching determinista
entre las atribuciones observadas y la tabla drivers.
"""

import re


def normalize_license(value: str) -> str:
    """Normaliza numero de licencia a formato estandar."""
    if not value:
        return ""
    v = str(value).strip().upper()
    v = re.sub(r'[^A-Z0-9]', '', v)
    return v


def normalize_phone(value: str) -> str:
    """Normaliza numero de telefono: solo digitos, sin codigo pais."""
    if not value:
        return ""
    v = str(value).strip()
    v = re.sub(r'[^0-9]', '', v)
    if v.startswith("51") and len(v) > 9:
        v = v[2:]
    if v.startswith("+51"):
        v = v[3:]
    if len(v) == 11 and v.startswith("51"):
        v = v[2:]
    return v


def normalize_name(value: str) -> str:
    """Normaliza nombre: mayusculas, sin acentos, sin espacios extras."""
    if not value:
        return ""
    v = str(value).strip().upper()
    v = re.sub(r'[^A-Z\s]', '', v)
    v = re.sub(r'\s+', ' ', v)
    return v
