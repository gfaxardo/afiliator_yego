# OBSERVED AFFILIATION BRIDGE — Persistir driver_not_found como observado

## Fecha
2026-05-23

## Estado
IMPLEMENTADO — GO

## Problema
Cuando una fila de carga unificada no encontraba match en drivers ni en `module_ct_cabinet_drivers`, el sistema descartaba completamente la fila (solo quedaba en memoria y audit CSV). El trabajo reportado por el scout se perdía sin trazabilidad para reconciliación futura.

## Solución
Se implementó un puente automático: cuando `unified_apply()` detecta `driver_not_found` con evidencia mínima (licencia, nombre o teléfono + scout), crea un registro `ObservedAffiliation` con estado `unmatched` / `observed_pending_review`, conservando toda la metadata del CSV original.

## Qué se guarda

| Campo | Origen |
|-------|--------|
| `reported_license` | `licencia` del CSV |
| `reported_driver_name` | `nombre_conductor` del CSV |
| `reported_scout_name` | `scout` del CSV |
| `reported_supervisor_name` | `supervisor` del CSV |
| `reported_origin` | `origen` del CSV |
| `reported_affiliation_date` | `fecha_atribucion` (o `fecha_pago`, o today) |
| `match_status` | `unmatched` |
| `review_status` | `observed_pending_review` |
| `official_source_status` | `driver_not_found` |
| `review_notes` | `"Origen: carga unificada. {observacion}"` |
| `raw_payload` | JSON con `source`, `fecha_pago`, `fecha_atribucion`, `tipo_evento`, `monto_pagado`, `pagado`, `tipo_scout`, `motivo_pago`, `cohorte_iso` |

## Qué NO se guarda

- **No** `DriverAssignment` (sin driver_id validado)
- **No** `PaidHistory` (sin driver validado → no pagable)
- **No** `driver_id` fantasma
- **No** se toca `module_ct_cabinet_drivers`

## Cómo se reconcilia después

1. El registro queda en `scout_liq_observed_affiliations` con `match_status=unmatched`
2. `reprocess_unmatched_observed_affiliations()` puede re-ejecutar el matching si el driver aparece después en la tabla drivers
3. El `raw_payload` conserva todos los datos originales para auditoría forense

## Columnas nuevas en audit CSV

| Columna | Valor para observed | Valor para matched |
|---------|---------------------|---------------------|
| `observed_affiliation_created` | `true` | `false` |
| `observed_affiliation_id` | ID del registro | _(vacío)_ |
| `observed_affiliation_status` | `unmatched` | _(vacío)_ |
| `assignment_created` | `false` | `true`/`false` |
| `paid_history_created` | `false` | `true`/`false` |
| `eligible_for_cutoff` | `false` | `true` |
| `reconciliation_status` | `pending` | _(vacío)_ |
| `driver_operational_state` | `observed_only` | `matched` |
| `action` | `driver_not_found_observed_saved` | _(normal)_ |

## Nuevos contadores en apply/summary

- `observed_created`: observados nuevos creados
- `observed_existing`: duplicados encontrados en DB
- `rejected_no_evidence`: driver_not_found sin evidencia mínima (sin licencia/nombre/teléfono + scout)

## Deduplicación

- Clave: `(normalized_license, reported_affiliation_date, reported_scout_name)`
- Si ya existe un `ObservedAffiliation` con la misma clave: `action = driver_not_found_observed_existing`, no se duplica

## Archivos modificados

- `backend/app/services/unified_load_service.py` — lógica del puente en `unified_apply()`, nuevos campos en `generate_full_audit_csv()` y `generate_summary_csv()`
- `backend/app/schemas/scout_liq.py` — `UnifiedLoadApplyDetail` y `UnifiedLoadApplyResponse` extendidos
- `frontend/src/api/unifiedLoad.ts` — interfaces TypeScript actualizadas
- `frontend/src/components/Liquidador/CentroCargaView.tsx` — labels y colores para nuevas acciones

## Riesgos

- Los registros observados **no son pagables** hasta que un `driver_id` sea resuelto vía `reprocess_unmatched_observed_affiliations()` o reconciliación manual
- Si un scout reporta el mismo driver muchas veces en diferentes cargas, se crearán múltiples `ObservedAffiliation` (uno por fecha distinta)
- El `raw_payload` almacena el `monto_pagado` solo como metadata, nunca como pago validado

## Pendientes

- La UI de revisión de observados (`ObservedReviewQueue`) ya existe y puede usarse para revisar estos registros
- `reprocess_unmatched_observed_affiliations()` funciona sin cambios
