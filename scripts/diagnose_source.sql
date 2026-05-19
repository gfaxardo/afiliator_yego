-- ============================================================================
-- DIAGNÓSTICO DE TABLA FUENTE: module_ct_cabinet_drivers
-- Fase 0 - Liquidador de Calidad Scouts Yego
-- Solo LECTURA. No modifica nada.
-- ============================================================================

-- 1. Columnas y tipos de datos
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_schema || '.' || table_name = 'public.module_ct_cabinet_drivers'
   OR table_name = 'module_ct_cabinet_drivers'
ORDER BY ordinal_position;

-- 2. Cantidad total de filas
SELECT COUNT(*) AS total_rows FROM module_ct_cabinet_drivers;

-- 3. Conteo de driver_id nulos
SELECT COUNT(*) AS null_driver_id FROM module_ct_cabinet_drivers WHERE driver_id IS NULL;

-- 4. Conteo de hire_date nulos
SELECT COUNT(*) AS null_hire_date FROM module_ct_cabinet_drivers WHERE hire_date IS NULL;

-- 5. Duplicados por driver_id
SELECT driver_id, COUNT(*) AS occurrences
FROM module_ct_cabinet_drivers
WHERE driver_id IS NOT NULL
GROUP BY driver_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC
LIMIT 20;

-- 6. Columnas posiblemente relacionadas a origin/cabinet/fleet
SELECT column_name, data_type
FROM information_schema.columns
WHERE (table_name = 'module_ct_cabinet_drivers')
  AND (column_name ILIKE '%origin%'
    OR column_name ILIKE '%cabinet%'
    OR column_name ILIKE '%fleet%'
    OR column_name ILIKE '%partner%')
ORDER BY ordinal_position;

-- 7. Columnas posiblemente relacionadas a trips_7d
SELECT column_name, data_type
FROM information_schema.columns
WHERE (table_name = 'module_ct_cabinet_drivers')
  AND (column_name ILIKE '%trip%7%'
    OR column_name ILIKE '%7%trip%'
    OR column_name ILIKE '%7d%'
    OR column_name ILIKE '%7_d%'
    OR column_name ILIKE '%week%'
    OR column_name ILIKE '%semana%')
ORDER BY ordinal_position;

-- 8. Columnas posiblemente relacionadas a trips_14d
SELECT column_name, data_type
FROM information_schema.columns
WHERE (table_name = 'module_ct_cabinet_drivers')
  AND (column_name ILIKE '%trip%14%'
    OR column_name ILIKE '%14%trip%'
    OR column_name ILIKE '%14d%'
    OR column_name ILIKE '%14_d%'
    OR column_name ILIKE '%biweek%'
    OR column_name ILIKE '%quincena%')
ORDER BY ordinal_position;

-- 9. Rango mínimo y máximo de hire_date
SELECT
    MIN(hire_date) AS min_hire_date,
    MAX(hire_date) AS max_hire_date
FROM module_ct_cabinet_drivers;

-- 10. Muestra de 5 filas para inspección visual
SELECT * FROM module_ct_cabinet_drivers LIMIT 5;

-- 11. Valores distintos en posibles columnas de origin
SELECT column_name
FROM information_schema.columns
WHERE (table_name = 'module_ct_cabinet_drivers')
  AND column_name ILIKE '%origin%'
ORDER BY ordinal_position;
