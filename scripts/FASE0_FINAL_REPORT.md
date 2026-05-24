# FASE 0 — RAW ENRICHMENT AUDIT: REPORTE FINAL

**Fecha:** 2026-05-24  
**Tabla:** `public.module_ct_cabinet_drivers`  
**Modo:** READ ONLY — 0 escrituras, 0 alteraciones  
**Motor:** PostgreSQL 5432 @ 168.119.226.236 / yego_integral

---

## 1. LISTA REAL DE COLUMNAS (22 columnas)

Ejecutado:
```sql
SELECT column_name, data_type, character_maximum_length, is_nullable, ordinal_position
FROM information_schema.columns
WHERE table_name = 'module_ct_cabinet_drivers'
ORDER BY ordinal_position;
```

| # | Columna | Tipo | Null | Poblado | Null/Empty |
|---|---------|------|------|---------|------------|
| 1 | `id` | integer | NO | 100% | 0% |
| 2 | `driver_id` | varchar(255) | YES | 100% | 0% |
| 3 | `driver_nombre` | varchar(255) | YES | 100% | 0% |
| 4 | `driver_apellido` | varchar(255) | YES | 100% | 0% |
| 5 | `driver_placa` | varchar(50) | YES | — | — |
| 6 | `driver_phone` | varchar(50) | YES | 55.2% | 44.8% |
| 7 | `park_name` | varchar(255) | YES | 100% | 0% |
| 8 | `park_id` | varchar(255) | YES | 67.9% | 32.1% |
| 9 | `status` | varchar(100) | YES | 75.1% | 24.9% |
| 10 | `last_active_date` | varchar(100) | YES | 15.4% | 84.6% |
| 11 | `segment` | varchar(100) | YES | 58.8% | 41.2% |
| 12 | `stage` | varchar(100) | YES | 55.2% | 44.8% |
| 13 | `license` | varchar(100) | YES | 67.0% | 33.0% |
| 14 | `viajes_0_7` | boolean | YES | — | — |
| 15 | `viajes_8_14` | boolean | YES | — | — |
| 16 | `orders` | integer | YES | 100% | 0% |
| 17 | `conexion` | varchar(20) | YES | 30.5% | 69.5% |
| 18 | `hire_date` | varchar(100) | YES | **61.8%** | **38.2%** |
| 19 | `origen` | varchar(50) | YES | 100% (cabinet=3018, fleet=995) | 0% |
| 20 | `created_at` | timestamp | YES | 100% (ETL sync) | 0% |
| 21 | `updated_at` | timestamp | YES | 100% | 0% |
| **22** | **`lead_created_at`** | **varchar(100)** | YES | **44.8%** | **55.2%** |

---

## 2. CAMPOS NUEVOS DETECTADOS

| Campo | ¿Nuevo? | Evidencia |
|-------|---------|-----------|
| **`lead_created_at`** | **SI** | Columna #22. No referenciada en source_adapter.py ni en cutoff_engine.py. Existe solo como columna en la tabla. |
| `viajes_0_7` | Existente | Legacy flag, usado como informativo |
| `viajes_8_14` | Existente | Legacy flag, usado como informativo |

**Campos esperados pero NO ENCONTRADOS:**
`first_trip_at`, `first_5_trip_at`, `acquisition_date`, `acquisition_source`, `registration_date`, `city`, `fire_date`, `active`, `onboarding_stage`, `onboarding_status`, `first_completed_trip`

---

## 3. lead_created_at — CONFIRMACIÓN EXACTA

### 3.1 Existencia y tipo

| Pregunta | Respuesta |
|----------|-----------|
| ¿Existe? | **SI** — columna #22 |
| Tipo de dato | `character varying(100)` — **NO es DATE/TIMESTAMP nativo** |
| ¿Nullable? | YES |
| ¿Se puede cast? | SI — `::timestamp` y `::date` funcionan correctamente |

### 3.2 Null rate

```sql
SELECT
    COUNT(*) FILTER (WHERE lead_created_at IS NULL)        AS null_count,
    COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL
                      AND lead_created_at::text != '')     AS with_value,
    COUNT(*)                                               AS total
FROM module_ct_cabinet_drivers;
```

| Métrica | Valor | % |
|---------|-------|---|
| **NULL** | 2,214 | 55.2% |
| **Con valor** | 1,799 | 44.8% |
| **Total** | 4,013 | 100% |

### 3.3 Rango temporal

```sql
SELECT MIN(lead_created_at::timestamp), MAX(lead_created_at::timestamp)
FROM module_ct_cabinet_drivers
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '';
```

| | Valor |
|---|-------|
| **MIN** | `2025-11-25 01:42:08` |
| **MAX** | `2026-05-24 00:14:58` |

### 3.4 Formato

100% de los valores en formato **ISO 8601**: `2026-04-23T21:44:10` (separador `T`, sin zona horaria).

### 3.5 Distribución mensual

```
2025-11:  104
2025-12:  343
2026-01:  162
2026-02:  232
2026-03:  290
2026-04:  405
2026-05:  263
```

### 3.6 Cobertura por origen

```sql
SELECT origen, COUNT(*) AS total,
       COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL
                        AND lead_created_at::text != '') AS with_lca
FROM module_ct_cabinet_drivers
GROUP BY origen;
```

| Origen | Total | Con lead_created_at | % |
|--------|-------|---------------------|---|
| **cabinet** | 3,018 | 1,799 | **59.6%** |
| **fleet** | 995 | **0** | **0.0%** |

Fleet **nunca** tiene lead_created_at poblado.

---

## 4. COMPARACIÓN: lead_created_at vs hire_date

```sql
SELECT
    COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL
                     AND lead_created_at::text != ''
                     AND hire_date IS NOT NULL
                     AND hire_date::text != '')                           AS both_present,
    COUNT(*) FILTER (WHERE lead_created_at::date <= hire_date::date
                     AND lead_created_at IS NOT NULL
                     AND hire_date IS NOT NULL)                           AS correctos,
    COUNT(*) FILTER (WHERE lead_created_at::date > hire_date::date
                     AND lead_created_at IS NOT NULL
                     AND hire_date IS NOT NULL)                           AS invertidos,
    COUNT(*) FILTER (WHERE lead_created_at::date = hire_date::date
                     AND lead_created_at IS NOT NULL
                     AND hire_date IS NOT NULL)                           AS same_day,
    COUNT(*) FILTER (WHERE lead_created_at IS NULL)                      AS lca_null,
    COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date::text = '')     AS hd_null
FROM module_ct_cabinet_drivers;
```

### Resultados

| Métrica | Count | % del total | % de evaluables |
|---------|-------|-------------|-----------------|
| Ambos presentes (evaluable) | **618** | 15.4% | 100% |
| Correctos (lca <= hd) | 484 | 12.1% | **78.3%** |
| — Same day (lca == hd) | 482 | 12.0% | 78.0% |
| — lca < hd | 2 | 0.05% | 0.3% |
| **INVERTIDOS (lca > hd)** | **134** | 3.3% | **21.7%** |
| lca NULL | 2,214 | 55.2% | — |
| hd NULL/empty | 1,533 | 38.2% | — |

### Avg gap

| Métrica | Días |
|---------|------|
| Avg gap (hd - lca) global | **-33.8 días** (negativo por invertidos) |
| Avg gap invertidos (lca - hd) | **+156.8 días** (~5 meses) |

---

## 5. BUCKETS: hire_date - lead_created_at

```sql
SELECT
    CASE
        WHEN hire_date::date = lead_created_at::date THEN 'same_day'
        WHEN hire_date::date - lead_created_at::date BETWEEN 1 AND 3 THEN '1_3_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 4 AND 7 THEN '4_7_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 8 AND 14 THEN '8_14_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 15 AND 30 THEN '15_30_days'
        WHEN hire_date::date - lead_created_at::date > 30 THEN 'gt_30_days'
        WHEN hire_date::date - lead_created_at::date < 0 THEN 'INVERTED'
    END AS bucket, COUNT(*) AS cnt
FROM module_ct_cabinet_drivers
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
  AND hire_date IS NOT NULL AND hire_date::text != ''
GROUP BY bucket ORDER BY cnt DESC;
```

| Bucket | Count | % |
|--------|-------|---|
| **same_day** | 482 | 78.0% |
| **INVERTIDO** | 134 | 21.7% |
| 1_3_days | 0 | 0% |
| 4_7_days | 0 | 0% |
| 8_14_days | 0 | 0% |
| 15_30_days | 1 | 0.2% |
| gt_30_days | 1 | 0.2% |

**HALLAZGO CLAVE:** No existe pipeline lead→hire con días de diferencia. O es el mismo día (78%) o está invertido (21.7%). Esto confirma que lead_created_at no representa una fecha de adquisición previa al hire.

---

## 6. EJEMPLOS REALES DE ANOMALÍAS

### 6.1 TOP 10 invertidos (lca > hd, mayor gap)

```
driver=822717b4... lca=2026-05-08  hd=2025-05-02  gap=+371d  status=Registro
driver=48266ec4... lca=2026-04-16  hd=2025-05-17  gap=+334d  status=Registro
driver=80a34f6f... lca=2026-02-26  hd=2025-04-28  gap=+304d  status=Registro
driver=fd341caa... lca=2026-02-17  hd=2025-05-04  gap=+289d  status=Registro
driver=8620c336... lca=2026-03-14  hd=2025-05-29  gap=+289d  status=Registro
driver=397e6031... lca=2026-02-26  hd=2025-06-05  gap=+266d  status=Registro
driver=4a5a5734... lca=2026-03-26  hd=2025-07-22  gap=+247d  status=Registro
driver=4dfe0634... lca=2026-04-04  hd=2025-08-01  gap=+246d  status=Registro
driver=59defe27... lca=2026-05-05  hd=2025-09-04  gap=+243d  status=Registro
driver=8f9eb948... lca=2026-04-28  hd=2025-09-02  gap=+238d  status=Registro
```

**Patrón:** 107 de 134 invertidos tienen status="Registro". hire_date en 2025, lead_created_at en 2026. Son drivers que ya existían en la plataforma y luego fueron registrados en cabinet meses después.

### 6.2 Únicos casos lca < hd (gap positivo pequeño)

```
driver=30906aef... lca=2026-01-13  hd=2026-03-26  gap=+72d  status=Registrado
driver=8356c7f9... lca=2026-03-11  hd=2026-04-10  gap=+30d  status=Registro
```

Solo 2 casos en toda la tabla donde lead_created_at es genuinamente anterior a hire_date.

---

## 7. DETECCIÓN DE REACTIVACIONES

### 7.1 Drivers con hire_date pre-2026 + viajes en Mayo 2026

```sql
SELECT COUNT(DISTINCT src.driver_id)
FROM module_ct_cabinet_drivers src
WHERE src.hire_date IS NOT NULL AND src.hire_date::text != ''
  AND src.hire_date::date < '2026-01-01'
  AND EXISTS (
      SELECT 1 FROM trips_2026 t
      WHERE t.conductor_id = src.driver_id
        AND t.fecha_inicio_viaje >= '2026-05-01'
        AND t.condicion = 'Completado'
  );
```

**Resultado: 36 drivers**

Oldest hire: 2025-05-17. Avg days since hire: 260. Todos origen=cabinet, status predominante="Registro".

### 7.2 Drivers con viajes pero sin hire_date

**Resultado: 29 drivers** activos en Mayo 2026 sin fecha de contratación registrada. Algunos con 108+ viajes.

### 7.3 Drivers con lead_created_at muy antiguo + hire_date reciente

**Resultado: Ninguno.** No existen casos de lead_created_at anterior a 2025 con hire_date posterior a 2026.

---

## 8. DECISIÓN: GO / GO WITH WARNINGS / NO GO

### lead_created_at como anchor date financiero y de cohortes: **NO GO**

| Criterio | Evaluación | Puntaje |
|----------|------------|---------|
| Existe | SI | OK |
| Tipo de dato | VARCHAR (requiere cast) | OK |
| Cobertura total | 44.8% | **INSUFICIENTE** |
| Cobertura fleet | 0% | **CRÍTICO** |
| Cobertura cabinet | 59.6% | PARCIAL |
| Consistencia vs hire_date | 21.7% INVERTIDO (lca > hd) | **CRÍTICO** |
| Semántica | Fecha de creación en cabinet, NO adquisición | **CRÍTICO** |
| Pipeline predecible | No (78% same-day, 21.7% invertido, 0% gap intermedio) | **CRÍTICO** |

**Razones:**

1. **Cobertura insuficiente**: 55.2% de los registros no tienen lead_created_at.
2. **Fleet completamente excluido**: 995 drivers (24.8% del total) nunca tendrán este dato.
3. **Semántica incorrecta**: En 21.7% de casos evaluables, lead_created_at es **posterior** a hire_date (promedio +157 días). Esto significa que el lead se creó en cabinet **después** de que el conductor ya estaba trabajando. lead_created_at mide cuándo el registro entró al sistema de cabinet, no cuándo se adquirió al conductor.
4. **Sin pipeline de conversión**: Los buckets 1-3, 4-7, 8-14 días están vacíos. No existe un flujo medible de lead→hire. El patrón es binario: o es el mismo día o está invertido.

### hire_date como anchor date primario: **GO**

| Criterio | Evaluación |
|----------|------------|
| Cobertura total | 61.8% |
| Cobertura cabinet | 59.0% |
| Cobertura fleet | 70.2% |
| Consistencia vs created_at | 100% correcta (0 invertidos) |
| Consistencia vs last_active_date | 100% correcta (0 invertidos) |
| Tipo de dato | VARCHAR (requiere cast `::date`) |
| Rango | 2025-04-28 → 2026-05-22 |

### Estrategia COALESCE recomendada

```sql
-- Anchor date para cohortes financieras:
COALESCE(hire_date::date, created_at::date)
-- Cobertura: 100% (los 352 sin hire_date usan created_at como último recurso)

-- Anchor date para tracking comercial:
COALESCE(lead_created_at::date, hire_date::date, created_at::date)
-- Cobertura: 100%. lead_created_at cuando existe (tracking de entrada a cabinet).
```

---

## 9. RIESGOS REALES

| # | Riesgo | Severidad | Impacto |
|---|--------|-----------|---------|
| 1 | **lead_created_at no es fecha de adquisición** | **ALTO** | Si se usa como anchor date, 21.7% de cohortes tendrían fecha posterior al hire real, distorsionando métricas financieras |
| 2 | **Fleet sin lead_created_at** | **ALTO** | 995 drivers (24.8%) jamás tendrán este dato. Cualquier lógica que dependa de lead_created_at excluye a fleet |
| 3 | **38.2% de hire_date NULL** | **MEDIO** | 1,533 registros sin hire_date. 297 son fleet sin fecha alguna. Requiere fallback a created_at |
| 4 | **352 drivers sin ninguna fecha** | **MEDIO** | 8.8% sin hire_date ni lead_created_at. Solo created_at disponible (ETL date, no business date) |
| 5 | **29 drivers activos sin hire_date** | **MEDIO** | Conductores con viajes en Mayo 2026 pero sin fecha de contratación. Distorsionan cohortes |
| 6 | **36 drivers pre-2026 activos en Mayo 2026** | **MEDIO** | Reactivaciones o legacy. Deben tener cohorte propia o flag de exclusión |
| 7 | **Licencias duplicadas** | **BAJO** | 15+ licencias con múltiples driver_id. Bajo impacto en métricas pero indica duplicación de registros |
| 8 | **VARCHAR en lugar de DATE** | **BAJO** | hire_date y lead_created_at son VARCHAR. Funciona con cast pero no tiene validación nativa de fecha |
| 9 | **hire_date=2032 en drivers table** | **BAJO** | Un registro en tabla `drivers` con hire_date futuro (anomalía de datos, no en cabinet_drivers) |

---

## 10. PRÓXIMO PASO RECOMENDADO

**Acción inmediata:**
- **NO usar `lead_created_at` como anchor date de cohortes financieras.** No representa la fecha de adquisición real.
- **Usar `hire_date::date` como anchor date primario** para cohortes, métricas financieras y lifecycle.
- Para el 38.2% sin hire_date, usar `created_at::date` como fallback documentado.

**Acciones de mediano plazo:**
1. Cruzar `module_ct_cabinet_drivers` con `module_ct_cabinet_leads` (906 leads, 100% con lead_created_at) para enriquecer los 1,219 cabinet drivers que tienen hire_date pero no lead_created_at.
2. Para fleet drivers (995), aceptar que lead_created_at no existirá; hire_date es suficiente.
3. Clasificar los 36 drivers pre-2026 + activos en Mayo 2026 como cohorte "legacy/reactivated".
4. Calcular `first_trip_at` desde `trips_2026` como `MIN(fecha_inicio_viaje)` por driver (no existe columna nativa).
5. Documentar la semántica real de cada campo temporal en el data dictionary.

---

## SQLs EJECUTADOS (evidencia)

Todos los queries están en:
- `C:\cursor\AFILIATOR\scripts\fase0_raw_audit.py` (Fase A completa)
- `C:\cursor\AFILIATOR\scripts\fase0_audit_v2.py` (resiliente)
- `C:\cursor\AFILIATOR\scripts\fase0_audit_v3.py` (profiling profundo)
- `C:\cursor\AFILIATOR\scripts\fase0_audit_v4_final.py` (consistencia temporal)
- `C:\cursor\AFILIATOR\scripts\fase0_final_queries.py` (precision queries)

**0 escrituras. 0 alteraciones. Solo SELECT.**
