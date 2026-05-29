"""FASE 0 - Final precision queries for report."""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

T = 'module_ct_cabinet_drivers'

def q(sql, fetch='first'):
    with engine.connect() as conn:
        try:
            r = conn.execute(text(sql))
            if fetch == 'scalar': val = r.scalar(); conn.commit(); return val
            elif fetch == 'first': row = r.first(); conn.commit(); return row
            else: rows = r.fetchall(); conn.commit(); return rows
        except Exception as e: conn.rollback(); return f'ERR: {e}'

print('=' * 70)
print('Q1. lead_created_at NULL vs NOT NULL exactos')
print('=' * 70)
null_lca = q(f"SELECT COUNT(*) FROM {T} WHERE lead_created_at IS NULL", 'scalar')
not_null_lca = q(f"SELECT COUNT(*) FROM {T} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''", 'scalar')
total = q(f"SELECT COUNT(*) FROM {T}", 'scalar')
print(f"  NULL:              {null_lca} ({round(100*null_lca/total,1)}%)")
print(f"  NOT NULL + value:  {not_null_lca} ({round(100*not_null_lca/total,1)}%)")
print(f"  TOTAL:             {total}")

print()
print('=' * 70)
print('Q2. lead_created_at MIN / MAX exactos')
print('=' * 70)
r = q(f"SELECT MIN(lead_created_at::timestamp), MAX(lead_created_at::timestamp) FROM {T} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''")
print(f"  MIN: {r[0]}")
print(f"  MAX: {r[1]}")

print()
print('=' * 70)
print('Q3. hire_date MIN / MAX exactos')
print('=' * 70)
r = q(f"SELECT MIN(hire_date::date), MAX(hire_date::date) FROM {T} WHERE hire_date IS NOT NULL AND hire_date::text != ''")
print(f"  MIN: {r[0]}")
print(f"  MAX: {r[1]}")

print()
print('=' * 70)
print('Q4. lead_created_at vs hire_date COMPARACION')
print('=' * 70)
r = q(f"""
SELECT
    COUNT(*) AS total_evaluable,
    COUNT(*) FILTER(WHERE lead_created_at::date <= hire_date::date) AS correctos,
    COUNT(*) FILTER(WHERE lead_created_at::date > hire_date::date) AS invertidos,
    COUNT(*) FILTER(WHERE lead_created_at::date = hire_date::date) AS same_day,
    COUNT(*) FILTER(WHERE lead_created_at::date < hire_date::date) AS lca_before_hd,
    COUNT(*) FILTER(WHERE lead_created_at IS NULL) AS lca_null,
    COUNT(*) FILTER(WHERE hire_date IS NULL OR hire_date::text = '') AS hd_null
FROM {T}
""")
bp = r[0]
correct = r[1]
inv = r[2]
same = r[3]
before = r[4]
lca_n = r[5]
hd_n = r[6]
print(f"  Ambos presentes (evaluable):  {bp}")
print(f"  Correctos (lca <= hd):        {correct} ({round(100*correct/bp,1)}%)")
print(f"  Invertidos (lca > hd):        {inv} ({round(100*inv/bp,1)}%)")
print(f"  - Same day (lca == hd):       {same}")
print(f"  - lca < hd:                   {before}")
print(f"  lca NULL:                     {lca_n}")
print(f"  hd NULL/empty:                {hd_n}")

# Avg gap
gap = q(f"SELECT ROUND(AVG(hire_date::date - lead_created_at::date)::numeric, 1) FROM {T} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '' AND hire_date IS NOT NULL AND hire_date::text != ''", 'scalar')
inv_gap = q(f"SELECT ROUND(AVG(lead_created_at::date - hire_date::date)::numeric, 1) FROM {T} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '' AND hire_date IS NOT NULL AND hire_date::text != '' AND lead_created_at::date > hire_date::date", 'scalar')
print(f"  Avg gap (hd - lca):            {gap} days")
print(f"  Avg gap inverted (lca - hd):   {inv_gap} days")

print()
print('=' * 70)
print('Q5. BUCKETS: hire_date - lead_created_at')
print('=' * 70)
buckets = q(f"""
SELECT
    CASE
        WHEN hire_date::date = lead_created_at::date THEN 'same_day'
        WHEN hire_date::date - lead_created_at::date BETWEEN 1 AND 3 THEN '1_3_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 4 AND 7 THEN '4_7_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 8 AND 14 THEN '8_14_days'
        WHEN hire_date::date - lead_created_at::date BETWEEN 15 AND 30 THEN '15_30_days'
        WHEN hire_date::date - lead_created_at::date > 30 THEN 'gt_30_days'
        WHEN hire_date::date - lead_created_at::date < 0 THEN 'INVERTED'
        ELSE 'other'
    END AS bucket, COUNT(*) AS cnt
FROM {T}
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
  AND hire_date IS NOT NULL AND hire_date::text != ''
GROUP BY bucket ORDER BY cnt DESC
""", fetch='all')
if isinstance(buckets, list):
    for row in buckets:
        print(f"  {row[0]:15s} = {row[1]}")

print()
print('=' * 70)
print('Q6. ANOMALIAS: lead_created_at > hire_date (TOP 10)')
print('=' * 70)
anomalies = q(f"""
SELECT driver_id, lead_created_at, hire_date,
       lead_created_at::date - hire_date::date AS gap_days,
       origen, status
FROM {T}
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
  AND hire_date IS NOT NULL AND hire_date::text != ''
  AND lead_created_at::date > hire_date::date
ORDER BY (lead_created_at::date - hire_date::date) DESC
LIMIT 10
""", fetch='all')
if isinstance(anomalies, list):
    for row in anomalies:
        print(f"  driver={row[0][:20]}... lca={row[1]} hd={row[2]} gap={row[3]}d origen={row[4]} status={row[5]}")

print()
print('=' * 70)
print('Q7. ANOMALIAS: lead_created_at BEFORE hire_date > 0 days (TOP 5)')
print('=' * 70)
before_samples = q(f"""
SELECT driver_id, lead_created_at, hire_date,
       hire_date::date - lead_created_at::date AS gap_days,
       origen, status
FROM {T}
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
  AND hire_date IS NOT NULL AND hire_date::text != ''
  AND hire_date::date - lead_created_at::date > 0
ORDER BY (hire_date::date - lead_created_at::date) DESC
LIMIT 5
""", fetch='all')
if isinstance(before_samples, list):
    for row in before_samples:
        print(f"  driver={row[0][:20]}... lca={row[1]} hd={row[2]} gap={row[3]}d origen={row[4]} status={row[5]}")
else:
    print(f"  {before_samples}")

print()
print('=' * 70)
print('Q8. REACTIVACIONES: lca antiguo + hd reciente (pre-2025 lca, post-2026 hd)')
print('=' * 70)
react = q(f"""
SELECT driver_id, lead_created_at, hire_date,
       hire_date::date - lead_created_at::date AS gap_days,
       origen, status
FROM {T}
WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
  AND hire_date IS NOT NULL AND hire_date::text != ''
  AND lead_created_at::date < '2025-01-01'
  AND hire_date::date >= '2026-01-01'
ORDER BY gap_days DESC
LIMIT 10
""", fetch='all')
if isinstance(react, list):
    if react:
        for row in react:
            print(f"  driver={row[0][:20]}... lca={row[1]} hd={row[2]} gap={row[3]}d origen={row[4]} status={row[5]}")
    else:
        print("  Ninguno encontrado.")
else:
    print(f"  {react}")

print()
print('=' * 70)
print('Q9. lead_created_at coverage por origen')
print('=' * 70)
cov = q(f"""
SELECT origen,
       COUNT(*) AS total,
       COUNT(*) FILTER(WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '') AS with_lca,
       COUNT(*) FILTER(WHERE hire_date IS NOT NULL AND hire_date::text != '') AS with_hd
FROM {T}
GROUP BY origen ORDER BY total DESC
""", fetch='all')
if isinstance(cov, list):
    for row in cov:
        t2 = row[1]; wl = row[2]; wh = row[3]
        print(f"  {row[0]:10s} total={t2} lca={wl} ({round(100*wl/max(t2,1),1)}%) hd={wh} ({round(100*wh/max(t2,1),1)}%)")

print()
print('=' * 70)
print('Q10. Drivers con viajes en Mayo 2026 sin hire_date')
print('=' * 70)
nohd = q("""
SELECT COUNT(DISTINCT src.driver_id)
FROM module_ct_cabinet_drivers src
WHERE (src.hire_date IS NULL OR src.hire_date::text = '')
  AND EXISTS (
      SELECT 1 FROM trips_2026 t
      WHERE t.conductor_id = src.driver_id
        AND t.fecha_inicio_viaje >= '2026-05-01'
        AND t.condicion = 'Completado'
  )
""", 'scalar')
print(f"  {nohd} drivers")

print()
print('=' * 70)
print('Q11. Drivers con hire_date pre-2026 + viajes Mayo 2026')
print('=' * 70)
pre2026 = q("""
SELECT COUNT(DISTINCT src.driver_id)
FROM module_ct_cabinet_drivers src
WHERE src.hire_date IS NOT NULL AND src.hire_date::text != ''
  AND src.hire_date::date < '2026-01-01'
  AND EXISTS (
      SELECT 1 FROM trips_2026 t
      WHERE t.conductor_id = src.driver_id
        AND t.fecha_inicio_viaje >= '2026-05-01'
        AND t.condicion = 'Completado'
  )
""", 'scalar')
print(f"  {pre2026} drivers (posibles reactivados)")

print()
print('=' * 70)
print('Q12. Fleet park_name distribution con hire_date NULL')
print('=' * 70)
fleet_null_hd = q(f"""
SELECT park_name, COUNT(*) AS cnt
FROM {T}
WHERE origen = 'fleet' AND (hire_date IS NULL OR hire_date::text = '')
GROUP BY park_name ORDER BY cnt DESC
""", fetch='all')
if isinstance(fleet_null_hd, list):
    for row in fleet_null_hd:
        pn = str(row[0] or 'NULL')[:40]
        print(f"  {pn:40s} = {row[1]}")

print()
print('=' * 70)
print('REPORTE COMPLETO')
