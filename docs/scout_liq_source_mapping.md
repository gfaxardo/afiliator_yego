# Mapeo Real de Tabla Fuente: module_ct_cabinet_drivers

**Fecha diagnóstico**: 2026-05-16
**Schema**: `public`
**Filas totales**: 2227
**Regla**: SOLO LECTURA. No modificar, no alterar, no borrar.

---

## Columnas Reales (21 columnas)

| # | Columna | Tipo | Nullable | Uso en Liquidador |
|---|---------|------|----------|-------------------|
| 1 | `id` | integer | NO | PK interna (ignorar) |
| 2 | `driver_id` | varchar | YES | **PK de conductor** (0 nulos, sin duplicados) |
| 3 | `driver_nombre` | varchar | YES | Nombre del conductor |
| 4 | `driver_apellido` | varchar | YES | Apellido del conductor |
| 5 | `driver_placa` | varchar | YES | Placa del vehículo |
| 6 | `driver_phone` | varchar | YES | Teléfono |
| 7 | `park_name` | varchar | YES | Nombre del parque/flota |
| 8 | `park_id` | varchar | YES | ID de parque |
| 9 | `status` | varchar | YES | Estado (ej: "Registrado") |
| 10 | `last_active_date` | varchar | YES | Última fecha activa |
| 11 | `segment` | varchar | YES | Segmento (ej: "churn") |
| 12 | `stage` | varchar | YES | Stage (ej: "between_46_and_100") |
| 13 | `license` | varchar | YES | Número de licencia |
| 14 | `viajes_0_7` | boolean | YES | **¿Viajes en primeros 7 días?** (flag booleano) |
| 15 | `viajes_8_14` | boolean | YES | **¿Viajes entre día 8-14?** (flag booleano) |
| 16 | `orders` | integer | YES | **Total de órdenes/viajes acumulados** |
| 17 | `conexion` | varchar | YES | Hora de conexión |
| 18 | `hire_date` | varchar | YES | **Fecha de contratación** (⚠ VARCHAR, no DATE) |
| 19 | `origen` | varchar | YES | **Origen**: "cabinet" o "fleet" |
| 20 | `created_at` | timestamp | YES | Fecha creación registro |
| 21 | `updated_at` | timestamp | YES | Fecha actualización registro |

---

## Mapeo de Columnas para el Liquidador

| Concepto Liquidador | Columna Real | Tipo | Notas |
|---------------------|-------------|------|-------|
| **driver_id** | `driver_id` | VARCHAR | UUID 32 hex. Sin nulos. Sin duplicados. |
| **hire_date** | `hire_date` | VARCHAR | ⚠ Requiere CAST a DATE. 481 nulos (21.6%). Formato: `YYYY-MM-DD`. |
| **origin** | `origen` | VARCHAR | ⚠ Nombre en español. Valores: "cabinet", "fleet". |
| **trips_7d** | `viajes_0_7` | BOOLEAN | ⚠ Es flag booleano, NO conteo. True = hizo viajes en primeros 7 días. |
| **trips_14d** | `viajes_8_14` | BOOLEAN | ⚠ Es flag booleano, NO conteo. True = hizo viajes entre día 8-14. |
| **total_trips** | `orders` | INTEGER | Conteo total de órdenes/viajes del conductor. |
| **driver_name** | `driver_nombre` + `driver_apellido` | VARCHAR | Nombre compuesto |
| **fleet** | `park_name` + `park_id` | VARCHAR | Parque/flota de afiliación |
| **status** | `status` | VARCHAR | Estado del conductor |

---

## Columnas para Embudo Futuro

| Concepto | Disponible | Columna | Observación |
|----------|-----------|---------|-------------|
| 1 viaje | NO directo | — | No hay flag de "al menos 1 viaje". Usar `orders >= 1`. |
| 5 viajes / 7 días | NO directo | `viajes_0_7` (boolean) | Se necesita parsear si `orders >= 5` + `viajes_0_7 = True`. |
| 5 viajes / 14 días | NO directo | `viajes_8_14` (boolean) + `orders` | Usar `orders >= 5` para verificar. |
| 25 viajes | NO | — | No existe columna. |
| 50 viajes | NO | — | No existe columna. |

**Conclusión**: La tabla fuente tiene flags booleanos, no conteos de viajes. Para determinar "5 viajes en 7 días" se debe:
1. Verificar que `viajes_0_7 = True` (hizo al menos un viaje en los primeros 7 días)
2. Verificar que `orders >= 5` (tiene al menos 5 órdenes totales)
3. Alternativa: Usar solo `orders >= 5` si no se requiere el filtro temporal exacto.

---

## Riesgos de Datos

1. **hire_date es VARCHAR**: Debe castearse a DATE en todas las consultas. Si hay formatos inválidos, las consultas fallarán. Rango actual: `2025-04-28` a `2026-05-15` (formato consistente).

2. **481 hire_date nulos (21.6%)**: Conductores sin fecha de contratación no podrán participar en cortes por rango de fecha.

3. **viajes_0_7 / viajes_8_14 son booleanos, no conteos**: La lógica de "5 viajes en 7 días" requiere usar `orders` (conteo total). No se puede distinguir exactamente cuántos viajes fueron en los primeros 7 días vs. después.

4. **Sin duplicados en driver_id**: OK para atribución. Cada driver_id aparece una sola vez.

5. **Columna `origen` (español)**: Diferente del inglés `origin` esperado en el código. Mapear explícitamente.

6. **Tabla compartida en DB `yego_integral`**: Convive con Control Tower (137 migraciones). Nuestro proyecto usa tabla de versiones independiente `alembic_version_scout_liq`.

---

## Distribución de origen

| origen | count |
|--------|-------|
| cabinet | 1239 |
| fleet | 988 |

Fuente: diagnóstico real 2026-05-16.

---

## Recomendaciones para Fase 2

1. **Source Adapter**: Crear un módulo `app/adapters/source_adapter.py` que:
   - Lea `module_ct_cabinet_drivers` (solo SELECT)
   - Castee `hire_date` de VARCHAR a DATE con manejo de errores
   - Mapee `origen` → `origin` para el resto del sistema
   - Exponga `viajes_0_7` como `has_trips_week1` (boolean)
   - Exponga `orders` como `total_trips` (integer)

2. **Estrategia de conversión a 5 viajes / 7 días**:
   - Opción A: `viajes_0_7 = True` AND `orders >= 5`
   - Opción B: Solo `orders >= 5` (más simple, menos preciso)
   - Decidir con negocio cuál aplicar.

3. **Manejo de nulos en hire_date**: Conductores sin hire_date deben excluirse de cortes o asignarse a fecha default.
