# PARITY AUDIT REPORT — Reporte Lado a Lado para Reemplazo de Sheets

## Propósito

Permitir al usuario migrar gradualmente desde un Sheets externo hacia AFILIATOR. Cada fila cargada genera un veredicto ejecutivo fila por fila que responde: ¿AFILIATOR ya refleja esto?, ¿lo aplicó?, ¿quedó parcial?, ¿está listo para corte?

## Formato Excel LATAM

El CSV usa:
- **Delimitador `;`** (punto y coma) para abrir correctamente en Excel LATAM.
- **Encoding UTF-8 con BOM** para compatibilidad con caracteres especiales.
- **Quoting correcto** para textos que contengan `;`, `,`, `|`, comillas o saltos de línea.

Para abrir en Excel: Archivo → Abrir → seleccionar el CSV. Excel LATAM reconoce automáticamente el punto y coma como separador de columnas.

## Columnas del reporte de paridad

Todas las columnas nuevas se añaden al final del CSV de auditoría completa, preservando las columnas legacy.

| Columna | Descripción | Posibles valores |
|---------|-------------|-----------------|
| `source_record_key` | Clave compuesta para identificar el registro | `licencia\|scout\|fecha` |
| `parity_status` | Veredicto principal | `full_applied`, `already_reflected`, `partial_applied`, `observed_pending`, `rejected_unusable`, `no_change`, `manual_review` |
| `parity_explanation` | Explicación en lenguaje natural | Texto descriptivo |
| `input_record_detected` | Si AFILIATOR leyó la fila | `true` / `false` |
| `driver_resolution_status` | Cómo se resolvió el driver | `matched_driver`, `unmatched_observed`, `not_found_no_evidence`, `duplicate_candidate`, `manual_review`, `unknown` |
| `assignment_status` | Estado de la atribución scout→driver | `created`, `already_exists`, `skipped_no_driver`, `blocked_duplicate`, `skipped_missing_scout`, `not_applicable` |
| `payment_history_status` | Estado del pago histórico | `created`, `already_exists`, `skipped_no_driver`, `skipped_invalid_amount`, `blocked_duplicate`, `not_applicable` |
| `needs_human_review` | Requiere revisión manual | `true` / `false` |
| `next_action` | Próximo paso recomendado | `ready_for_cutoff`, `wait_reconciliation`, `fix_license_or_phone`, `fix_scout`, `review_duplicate`, `no_action_needed`, `manual_review` |
| `blocking_reason` | Razón de bloqueo si hay | Texto descriptivo o vacío |
| `applied_entities` | Entidades creadas/actualizadas | Pipe-separated list: `driver_assignment\|payment_history\|observed_affiliation` |
| `skipped_entities` | Entidades omitidas | Pipe-separated list |
| `rejected_entities` | Entidades rechazadas por imposibles | Pipe-separated list. NUNCA incluye `observed_affiliation` si esta fue creada. |
| `system_confidence_level` | Confianza del sistema en el veredicto | `high`, `medium`, `low`, `none`, `unknown` |
| `operational_readiness` | ¿Está listo para operación/corte? | `ready_for_cutoff`, `pending_reconciliation`, `needs_fix`, `human_review`, `no_action_needed`, `not_eligible` |

## Diferencia clave: unmatched_observed vs not_found_no_evidence

- **`unmatched_observed`**: Driver no encontrado, pero el reporte del scout SÍ fue guardado como `ObservedAffiliation`. Hay evidencia suficiente (licencia + scout) para reconciliar después.
- **`not_found_no_evidence`**: Driver no encontrado Y NO hay evidencia mínima (sin licencia, nombre ni teléfono + scout). No se guardó nada útil.
- **Regla**: Si `observed_affiliation_created=true` → `driver_resolution_status` DEBE ser `unmatched_observed`.

## Regla de entidades (applied / skipped / rejected)

- `applied_entities`: entidades que EFECTIVAMENTE se crearon o actualizaron.
- `skipped_entities`: entidades que se omitieron intencionalmente por falta de condiciones (ej: pago no requerido porque pagado=NO, atribución no creada porque no hay driver).
- `rejected_entities`: SOLO entidades que fueron imposibles de crear por error duro (ej: sin licencia). NUNCA incluye `observed_affiliation` si esta fue creada.

## Significado de `system_confidence_level`

| Nivel | Cuándo aplica |
|-------|---------------|
| `high` | `full_applied`, `already_reflected`, `no_change` — el sistema está seguro del veredicto |
| `medium` | `observed_pending` — hay evidencia pero falta resolver el driver |
| `low` | `partial_applied`, `manual_review` — hay incertidumbre o aplicación incompleta |
| `none` | `rejected_unusable` — el registro no pudo procesarse |
| `unknown` | fallback, no debería ocurrir |

## Significado de `operational_readiness`

| Estado | Significado |
|--------|-------------|
| `ready_for_cutoff` | El registro está listo para entrar en un corte de liquidación |
| `pending_reconciliation` | Pendiente de que el driver sea encontrado en fuentes operativas |
| `needs_fix` | Requiere corrección (monto, fecha, licencia) |
| `human_review` | Requiere intervención humana por conflicto o ambigüedad |
| `no_action_needed` | Sin acción requerida |
| `not_eligible` | El registro no es elegible para corte

## Significado de cada `parity_status`

### `full_applied`
AFILIATOR aplicó completamente lo que correspondía. El driver fue encontrado, la atribución se creó, y si el pago era requerido (pagado=SI + monto>0), se creó.

**Filtro para "listo en AFILIATOR"**: `parity_status = full_applied OR already_reflected`

### `already_reflected`
El registro ya existía en AFILIATOR sin requerir cambios. La asignación ya estaba, el pago ya estaba.

### `partial_applied`
Se aplicó una parte (ej: asignación creada), pero otra quedó omitida (ej: pago con monto inválido). Requiere atención pero no bloquea la operación.

### `observed_pending`
No se encontró el driver, pero el reporte del scout quedó guardado como `ObservedAffiliation` para reconciliación futura. **No es pagable hasta que se resuelva el match.**

### `rejected_unusable`
La fila no tiene evidencia mínima (sin licencia, nombre ni teléfono + scout). Imposible de procesar.

### `no_change`
Fila duplicada en el archivo o sin cambios necesarios. No requiere procesamiento adicional.

### `manual_review`
Conflicto de asignación (mismo driver reclamado por múltiples scouts) o situación ambigua. Requiere intervención humana.

## Cómo usarlo para comparar contra Sheets

1. Cargar el archivo completo de operación en AFILIATOR (Carga Unificada)
2. Ejecutar preview → revisar advertencias
3. Ejecutar apply → los drivers encontrados se asignan, los no encontrados se guardan como observados
4. Descargar el CSV de auditoría completa
5. Abrir en Excel/Sheets y filtrar por `parity_status`:
   - `full_applied` + `already_reflected` + `no_change` = filas cubiertas
   - `observed_pending` = pendientes de reconciliación (driver no en BD)
   - `partial_applied` = requieren corrección menor
   - `rejected_unusable` = filas con datos insuficientes
6. El % de cobertura = (full_applied + already_reflected + no_change) / total × 100

## Cuándo AFILIATOR está listo para reemplazar Sheets

El Sheets puede considerarse reemplazable cuando:
- El % de filas con `parity_status IN (full_applied, already_reflected, no_change)` supera el umbral definido por el negocio
- Las filas `observed_pending` tienen un proceso de reconciliación definido
- Las filas `rejected_unusable` están documentadas como datos inválidos en el Sheets original

## Columnas legacy preservadas

Todas las columnas existentes se conservan sin cambios.
- `audit_status`, `action`, `saved`, `applied`, `rejected`, `ignored`, `already_paid`, `not_found`
- `error_code`, `error_message`, `what_happened`, `rejection_reason`
- Todas las columnas originales del input
- Todos los campos observed bridge

## Compatibilidad hacia atrás

- Las nuevas columnas se añaden al final del CSV
- Ninguna columna existente ha sido eliminada o renombrada
- Los consumidores actuales del CSV de auditoría no se ven afectados

## Panel de Paridad en Centro de Carga

### Fuente de verdad

El frontend consume los campos de paridad directamente desde el streaming del backend (`unified_apply_stream`). NO recalcula ni infiere paridad localmente (salvo fallback si los campos no están presentes).

Campos recibidos del backend en cada línea del streaming y en cada `detail` de `unified_apply()`:
- `parity_status`, `parity_explanation`
- `system_confidence_level`, `operational_readiness`
- `next_action`, `driver_resolution_status`
- `assignment_status`, `payment_history_status`
- `applied_entities`, `skipped_entities`, `rejected_entities`

Esto garantiza que UI, CSV de auditoría y response JSON de ambos endpoints (streaming y non-streaming) muestren la misma realidad operacional.

Después de ejecutar apply, el panel muestra:

### Tarjetas de resumen por estado
- **Aplicados**: `full_applied` — AFILIATOR aplicó todo
- **Ya reflejados**: `already_reflected` — ya existía
- **Observados pendientes**: `observed_pending` — driver no encontrado, guardado como observado
- **Parciales**: `partial_applied` — aplicado parcialmente
- **Revisión humana**: `manual_review` — requiere intervención
- **Rechazados**: `rejected_unusable` — sin evidencia mínima
- **Sin cambios**: `no_change` — duplicado o sin acción

### KPIs
- **Cobertura operativa**: % de filas con `full_applied` + `already_reflected` + `no_change`
- **Brecha de reconciliación**: % de filas con `observed_pending` + `manual_review` + `partial_applied`
- **Tasa de rechazo**: % de filas `rejected_unusable`

### Preparación operativa
Desplegable con conteos por `operational_readiness`:
- Listo para corte
- Pendiente reconciliación
- Necesita corrección
- Revisión humana
- Sin acción
- No elegible

### Tabla de resultados
Columnas en la tabla post-apply:
- `#` (source_row)
- Driver (licencia o driver_id)
- Scout
- Acción (etiqueta coloreada)
- **Paridad** (nueva — badge coloreado con parity_status)
- **Próx. paso** (nueva — operational_readiness)
- Guardado (SI/NO)

### Filtros
- Filtros por estado de paridad: botones con conteo por estado
- Filtros legacy por acción (desplegable)

### Cómo comparar contra Sheets
1. Cargar archivo → preview → apply
2. Leer KPI de cobertura operativa: indica % de filas ya cubiertas por AFILIATOR
3. Filtrar "Observados pendientes" para ver qué drivers faltan en fuentes operativas
4. Filtrar "Rechazados" para ver filas con datos insuficientes
5. Descargar CSV de auditoría completa para análisis detallado en Excel

## Supervisor ya no bloquea la fila completa

**Antes**: si faltaba `supervisor`, la fila entera era rechazada (`validation_error`). No se creaba `DriverAssignment` ni `ObservedAffiliation`.

**Ahora**: `supervisor` es opcional. Si falta:
- La fila se procesa normalmente (atribución u observación según corresponda)
- Se genera warning `"Supervisor faltante"` en preview
- `parity_status` se ajusta a `partial_applied` si todo lo demás fue aplicado
- `next_action = fix_supervisor`
- `supervisor_status = missing` en el audit CSV
- `attribution_saved_despite_supervisor_missing = true`

### Qué sí bloquea
- Falta de `licencia` (campo requerido)
- Falta de `scout` (campo requerido)
- Falta de evidencia mínima de driver (sin licencia, nombre ni teléfono)

### Nuevas columnas en audit CSV
- `supervisor_status`: `matched`, `missing`, `not_required`, `unknown`
- `supervisor_warning`: texto descriptivo si supervisor falta
- `attribution_saved_despite_supervisor_missing`: `true`/`false`
