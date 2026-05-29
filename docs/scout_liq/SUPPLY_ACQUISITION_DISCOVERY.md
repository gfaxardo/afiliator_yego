# SUPPLY ACQUISITION DISCOVERY — Plantilla de Atribución

## Hallazgo
La plantilla histórica/manual de carga unificada (`plantilla_unificada.csv`) NO tiene `fecha_atribucion`. `fecha_pago` no debe usarse como cohorte operativa ni como anchor de adquisición.

## Fecha del hallazgo
2026-05-23

## Estado
CORREGIDO — GO. Las columnas `fecha_atribucion` y `tipo_evento` ya forman parte de la plantilla, el preview, el apply, los reportes de auditoría, el schema Pydantic, y la plantilla XLSX (06_ATRIBUCIONES_HISTORICAS).

## Corrección aplicada
- Añadidas columnas `fecha_atribucion` y `tipo_evento` a la plantilla unificada CSV (después de `fecha_pago`).
- Añadidas columnas `fecha_atribucion` y `tipo_evento` a la plantilla XLSX (hoja `06_ATRIBUCIONES_HISTORICAS`).
- `fecha_atribucion`: fecha real de captación/registro/reactivación del conductor por el scout.
- `tipo_evento`: `new`, `reactivated`, `migrated`, o `unknown` (default).
- Validación refinada en preview: solo se permite `fecha_atribucion` vacía en registros puramente financieros históricos (pagado=SI, sin driver_id resuelto ni input). Cualquier otra fila operativa con `fecha_atribucion` vacía recibe warning.
- Esquema Pydantic `UnifiedLoadPreviewLine` actualizado con todos los campos opcionales visibles.
- `fecha_pago` permanece como campo financiero, NO usado como anchor operativo.
- `cohorte_iso` permanece como referencia histórica, NO como anchor confiable.

## Columnas de la plantilla (nueva)
```
licencia, scout, supervisor, pagado, monto_pagado, fecha_pago,
fecha_atribucion, tipo_evento, observacion,
driver_id, nombre_conductor, origen, tipo_scout, motivo_pago, cohorte_iso
```

## Reglas de validación
1. Si `fecha_atribucion` está vacía y la fila es puramente financiera histórica (pagado=SI, sin driver_id resuelto ni input): permitido.
2. Si `fecha_atribucion` está vacía y la fila es operativa (con driver_id resuelto, input driver_id, o licencia): warning en preview "falta fecha_atribucion — atribucion operativa sin fecha de captacion".
3. `tipo_evento` vacío → default `unknown`.
4. `fecha_pago` NO se usa como cohorte operativa.
5. `cohorte_iso` es solo referencia de importación.

## Formato aceptado
- `fecha_atribucion`: DD/MM/YYYY o YYYY-MM-DD
- `tipo_evento`: `new`, `reactivated`, `migrated`, `unknown`

## Archivos modificados
- `backend/app/schemas/scout_liq.py` — `UnifiedLoadPreviewLine` extendido
- `backend/app/services/unified_load_service.py` — validación refinada
- `backend/scripts/generate_template.py` — hoja `06_ATRIBUCIONES_HISTORICAS` con nuevas columnas
- `backend/scripts/test_unified.csv` — columnas agregadas
- `backend/test_unified_load_audit.py` — tests actualizados
- `docs/scout_liq/SUPPLY_ACQUISITION_DISCOVERY.md` — este documento

## Riesgos pendientes
- El motor de corte (cutoff engine) aún no usa `fecha_atribucion` para liquidación operativa. Esto debe hacerse en una fase posterior (Acquisition Anchor).
- Los registros históricos sin `fecha_atribucion` NO deben recalcularse retroactivamente.
