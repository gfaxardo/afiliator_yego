# Data Contract de Calidad — Liquidador Scouts Yego

**Fecha**: 2026-05-16
**Fase**: 3
**Estado**: `ok` — Conteos reales disponibles vía JOIN

---

## 1. Fuentes de Conteo de Viajes

| Fuente | Filas | Índices relevantes | Uso |
|--------|-------|-------------------|-----|
| `trips_2025` | 48M | `idx_trips_2025_fecha` (fecha_inicio_viaje) | Conductores con hire_date en 2025 |
| `trips_2026` | 16M | `ix_trips_2026_conductor_fecha` (conductor_id, fecha) | Conductores con hire_date en 2026 |
| `trips_all` | x̄ | Vista/partición | Referencia, no usar directamente |
| `trips_unified` | x̄ | Vista unificada | Referencia |

---

## 2. Método de Cálculo de Conteos (CORREGIDO)

Los campos `trips_0_7_count`, `trips_8_14_count`, `trips_0_14_count` se calculan así:

```sql
-- Ventana 0-7 días: desde hire_date (inclusive) hasta hire_date+8d (exclusivo)
-- Ventana 8-14 días: desde hire_date+8d (inclusive) hasta hire_date+15d (exclusivo)
-- Solo viajes completados: condicion = 'Completado'

WITH driver_trips AS (
    SELECT conductor_id, fecha_inicio_viaje, condicion FROM trips_2026
    UNION ALL
    SELECT conductor_id, fecha_inicio_viaje, condicion FROM trips_2025
)
SELECT
    s.driver_id,
    COUNT(dt.conductor_id) FILTER (
        WHERE dt.fecha_inicio_viaje >= s.hire_date::date 
              AND dt.fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
              AND dt.condicion = 'Completado'
    ) AS trips_0_7_count,
    COUNT(dt.conductor_id) FILTER (
        WHERE dt.fecha_inicio_viaje >= s.hire_date::date + INTERVAL '8 days'
              AND dt.fecha_inicio_viaje < s.hire_date::date + INTERVAL '15 days'
              AND dt.condicion = 'Completado'
    ) AS trips_8_14_count
FROM module_ct_cabinet_drivers s
LEFT JOIN driver_trips dt ON s.driver_id = dt.conductor_id
WHERE s.hire_date IS NOT NULL AND s.hire_date != ''
GROUP BY s.driver_id
```

**Reglas de ventana:**
- Inicio inclusivo (`>=`), fin exclusivo (`<`)
- NO usar `BETWEEN` (causa solapamiento con timestamps)
- Solo `condicion = 'Completado'` (excluye Cancelado, Conduciendo, etc.)

**Optimización**: Para cutoffs con rango acotado, solo se consulta `trips_2026` que tiene índice `conductor_fecha`.

---

## 3. Contrato de Campos por Driver

| Campo | Origen | Tipo | Nota |
|-------|--------|------|------|
| driver_id | module_ct_cabinet_drivers | VARCHAR | PK |
| hire_date_raw | module_ct_cabinet_drivers | VARCHAR | Original |
| hire_date_parsed | Casteado | DATE | NULL si inválido |
| origin | module_ct_cabinet_drivers.origen | VARCHAR | cabinet/fleet |
| **trips_0_7_count** | Cálculo JOIN trips_* | INTEGER | Viajes en [hire, hire+6d] |
| **trips_8_14_count** | Cálculo JOIN trips_* | INTEGER | Viajes en [hire+7d, hire+13d] |
| **trips_0_14_count** | trips_0_7 + trips_8_14 | INTEGER | Derivado |
| total_orders | module_ct_cabinet_drivers.orders | INTEGER | Total acumulado (referencia) |
| legacy_viajes_0_7_flag | module_ct_cabinet_drivers.viajes_0_7 | BOOLEAN | **SOLO INFORMATIVO — NO USAR PARA PAGO** |
| legacy_viajes_8_14_flag | module_ct_cabinet_drivers.viajes_8_14 | BOOLEAN | **SOLO INFORMATIVO — NO USAR PARA PAGO** |
| source_quality_status | Cálculo | VARCHAR | ok / missing_trip_counts / invalid_hire_date |

---

## 4. Reglas de Calidad para Pago

1. **trips_0_7_count y trips_8_14_count DEBEN ser no-nulos** para que un driver sea elegible para pago.
2. Si `hire_date_parsed IS NULL`, el driver se excluye con status `invalid_hire_date`.
3. Si `trips_0_7_count IS NULL`, el driver se excluye con status `missing_trip_counts`.
4. Los flags `legacy_viajes_0_7_flag` y `legacy_viajes_8_14_flag` **NUNCA** se usan para calcular pago.
5. `total_orders` se usa solo como referencia, no como sustituto de conteos de ventana.

---

## 5. Métricas de Embudo Configurables

| Métrica | Cálculo | Campo |
|---------|---------|-------|
| 1+ viajes 0-7d | trips_0_7_count >= 1 | drivers_1plus_0_7 |
| 5+ viajes 0-7d | trips_0_7_count >= 5 | drivers_5plus_0_7 |
| 1+ viajes 8-14d | trips_8_14_count >= 1 | drivers_1plus_8_14 |
| 5+ viajes 0-14d | trips_0_14_count >= 5 | drivers_5plus_0_14 |

---

## 6. Bloqueos de Aprobación

Un cutoff NO puede ser aprobado si:
- `quality_data_contract_status != 'ok'`
- La métrica de conversión principal tiene `trips_0_7_count IS NULL` para algún driver elegible
- Hay drivers con `source_quality_status = 'missing_trip_counts'` incluidos en el cálculo

---

## 7. Impacto en la UI

- La pantalla de Liquidador muestra conteos reales (números), no flags.
- Si faltan conteos, se muestra alerta y se bloquean los botones Aprobar/Pagar.
- El detalle por driver muestra `trips_0_7_count`, `trips_8_14_count`, `trips_0_14_count`.
