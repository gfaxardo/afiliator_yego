"""FASE 0C v2 - Fix crash + remaining queries."""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

def q(sql, fetch='first'):
    with engine.connect() as conn:
        try:
            r = conn.execute(text(sql))
            if fetch == 'scalar': val = r.scalar(); conn.commit(); return val
            elif fetch == 'first': row = r.first(); conn.commit(); return row
            else: rows = r.fetchall(); conn.commit(); return rows
        except Exception as e: conn.rollback(); return f'ERR: {e}'

C = 'module_ct_cabinet_drivers'
D = 'drivers'

# ===================================================================
# 1. hire_date comparison: cabinet vs drivers
# ===================================================================
print('=' * 70)
print('1. hire_date comparison cabinet vs drivers (matched rows)')
print('=' * 70)

r = q(f"""
    SELECT
        COUNT(*) AS both_present,
        COUNT(*) FILTER(WHERE cd.hire_date::date = d.hire_date) AS equal,
        COUNT(*) FILTER(WHERE cd.hire_date::date != d.hire_date) AS different
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND cd.hire_date IS NOT NULL AND cd.hire_date::text != ''
      AND d.hire_date IS NOT NULL
""")
bp = r[0]; eq = r[1]; df = r[2]
print(f"  Both have hire_date: {bp}")
print(f"  Same date:           {eq} ({round(100*eq/bp,1)}%)" if bp else "  Same date: 0")
print(f"  Different date:      {df} ({round(100*df/bp,1)}%)" if bp else "  Different date: 0")

if df > 0:
    diffs = q(f"""
        SELECT cd.driver_id, cd.hire_date AS cab_hd, d.hire_date AS drv_hd,
               d.hire_date - cd.hire_date::date AS diff_days
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND cd.hire_date IS NOT NULL AND cd.hire_date::text != ''
          AND d.hire_date IS NOT NULL
          AND cd.hire_date::date != d.hire_date
        ORDER BY ABS(d.hire_date - cd.hire_date::date) DESC
        LIMIT 10
    """, fetch='all')
    if isinstance(diffs, list):
        print(f"\n  Top {len(diffs)} diferencias:")
        for r2 in diffs:
            print(f"    driver={r2[0][:16]}... cab={r2[1]} drv={r2[2]} diff={r2[3]}d")

# ===================================================================
# 2. Cabinet drivers WITH LCA: do they exist in drivers?
# ===================================================================
print('\n' + '=' * 70)
print('2. Cabinet drivers WITH LCA: existencia en drivers')
print('=' * 70)

lca_in_drv = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
""", 'scalar')
print(f"  Cabinet WITH LCA matched to drivers: {lca_in_drv}")

lca_not_in_drv = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
      AND cd.driver_id NOT IN (SELECT d.driver_id FROM {D} d)
""", 'scalar')
print(f"  Cabinet WITH LCA NOT in drivers:     {lca_not_in_drv}")

# ===================================================================
# 3. Fleet in drivers
# ===================================================================
print('\n' + '=' * 70)
print('3. Fleet vs drivers')
print('=' * 70)

fleet = q(f"""
    SELECT
        COUNT(*) AS total_matched,
        COUNT(*) FILTER(WHERE d.hire_date IS NOT NULL) AS drv_hd,
        COUNT(*) FILTER(WHERE cd.hire_date IS NOT NULL AND cd.hire_date::text != '') AS cab_hd,
        COUNT(*) FILTER(WHERE (cd.hire_date IS NULL OR cd.hire_date::text = '') AND d.hire_date IS NOT NULL) AS solo_drv_hd
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'fleet'
""")
ft = fleet[0]; fd = fleet[1]; fc = fleet[2]; fs = fleet[3]
print(f"  Fleet matched:         {ft}")
print(f"  drivers.hire_date:     {fd} ({round(100*fd/ft,1)}%)")
print(f"  cabinet.hire_date:     {fc} ({round(100*fc/ft,1)}%)")
print(f"  Solo drivers hd:       {fs} (recuperables)")

# Fleet NOT matched
fleet_not = q(f"""
    SELECT COUNT(*)
    FROM {C}
    WHERE origen = 'fleet'
      AND driver_id NOT IN (SELECT driver_id FROM {D})
""", 'scalar')
print(f"  Fleet NOT in drivers:  {fleet_not}")

# ===================================================================
# 4. drivers.hire_date range for matched cabinet
# ===================================================================
print('\n' + '=' * 70)
print('4. drivers.hire_date range for matched cabinet')
print('=' * 70)

r = q(f"""
    SELECT MIN(d.hire_date), MAX(d.hire_date)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet' AND d.hire_date IS NOT NULL
""")
print(f"  Range: [{r[0]}, {r[1]}]")

# Future dates
r = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet' AND d.hire_date > CURRENT_DATE
""", 'scalar')
print(f"  Future hire_date: {r}")

# drivers.fire_date stats for matched cabinet
print('\n  fire_date stats for matched cabinet:')
r = q(f"""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER(WHERE d.fire_date IS NOT NULL) AS fired,
        MIN(d.fire_date) FILTER(WHERE d.fire_date IS NOT NULL) AS min_fd,
        MAX(d.fire_date) FILTER(WHERE d.fire_date IS NOT NULL) AS max_fd,
        COUNT(*) FILTER(WHERE d.active = true) AS active_now
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
""")
print(f"    Total matched:  {r[0]}")
print(f"    Fired (has fd): {r[1]} ({round(100*r[1]/r[0],1)}%)")
print(f"    fire_date:      [{r[2]}, {r[3]}]")
print(f"    active=true:    {r[4]}")

# ===================================================================
# 5. Estructural: overlap analysis
# ===================================================================
print('\n' + '=' * 70)
print('5. ANALISIS ESTRUCTURAL: quien es quien')
print('=' * 70)

tot_cab = q(f"SELECT COUNT(*) FROM {C} WHERE origen = 'cabinet'", 'scalar')
tot_has_lca = q(f"SELECT COUNT(*) FROM {C} WHERE origen = 'cabinet' AND lead_created_at IS NOT NULL AND lead_created_at::text != ''", 'scalar')
tot_missing_lca = tot_cab - tot_has_lca
match_drv = q(f"SELECT COUNT(DISTINCT cd.driver_id) FROM {C} cd JOIN {D} d ON cd.driver_id = d.driver_id WHERE cd.origen = 'cabinet'", 'scalar')

# Of those matched to drivers, how many have LCA?
match_with_lca = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
""", 'scalar')

match_without_lca = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
""", 'scalar')

not_match_with_lca = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
      AND cd.driver_id NOT IN (SELECT d.driver_id FROM {D} d)
""", 'scalar')

not_match_without_lca = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id NOT IN (SELECT d.driver_id FROM {D} d)
""", 'scalar')

print(f"""
  CABINET DRIVERS: {tot_cab} total

                       | En drivers | NO en drivers | TOTAL
  ---------------------|------------|---------------|------
  CON LCA              | {match_with_lca:10d} | {not_match_with_lca:13d} | {tot_has_lca}
  SIN LCA              | {match_without_lca:10d} | {not_match_without_lca:13d} | {tot_missing_lca}
  TOTAL                | {match_drv:10d} | {tot_cab - match_drv:13d} | {tot_cab}
""")

# ===================================================================
# 6. How many cabinet drivers get hire_date enriched from drivers
# ===================================================================
print('=' * 70)
print('6. ENRIQUECIMIENTO hire_date DESDE drivers')
print('=' * 70)

cab_sin_hd = q(f"SELECT COUNT(*) FROM {C} WHERE origen = 'cabinet' AND (hire_date IS NULL OR hire_date::text = '')", 'scalar')
print(f"\n  Cabinet SIN hire_date total: {cab_sin_hd}")

# De esos, cuantos estan en drivers y tienen hire_date alli
cab_sin_hd_drv_yes = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND (cd.hire_date IS NULL OR cd.hire_date::text = '')
      AND d.hire_date IS NOT NULL
""", 'scalar')
print(f"  Cabinet sin hd PERO recuperable desde drivers: {cab_sin_hd_drv_yes}")

cab_sin_hd_drv_no = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.hire_date IS NULL OR cd.hire_date::text = '')
      AND cd.driver_id NOT IN (SELECT d.driver_id FROM {D} d)
""", 'scalar')
print(f"  Cabinet sin hd NI en drivers (sin solucion):  {cab_sin_hd_drv_no}")

# ===================================================================
# 7. Final rule summary
# ===================================================================
print('\n' + '=' * 70)
print('7. REGLA FINAL DE ANCHOR DATE PARA FASE 1')
print('=' * 70)

# Cabinets with some anchor
cab_with_anchor = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND (
          (cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != '')
          OR (cd.hire_date IS NOT NULL AND cd.hire_date::text != '')
          OR cd.driver_id IN (SELECT d.driver_id FROM {D} d WHERE d.hire_date IS NOT NULL)
      )
""", 'scalar')

cab_no_anchor = tot_cab - cab_with_anchor

print(f"""
  PROPUESTA anchor_date para cabinet:

    acquisition_anchor_date =
      COALESCE(
        cabinet_drivers.lead_created_at::date,    -- 1799 drv (59.6%)
        cabinet_leads.lead_created_at::date,       -- +137 drv (11.2% de missing, via placa/nombre)
        drivers.hire_date                          -- +{cab_sin_hd_drv_yes} drv via driver_id
      )

  Cobertura esperada:
    Con lead_created_at (nativo):                 1799 (59.6%)
    + cabinet_leads (placa/nombre):               +137 -> 1936 (64.1%)
    + drivers.hire_date (donde LCA falta):        +{cab_sin_hd_drv_yes} -> {1936 + cab_sin_hd_drv_yes} ({round(100*(1936+cab_sin_hd_drv_yes)/tot_cab,1)}%)
    Sin anchor (solo created_at ETL):             {cab_no_anchor} ({round(100*cab_no_anchor/tot_cab,1)}%)

  NOTAS:
    - drivers NO tiene lead_created_at. Su hire_date es DATE nativo, 100% poblado.
    - Solo 1219/3018 (40.4%) cabinet drivers existen en tabla drivers.
    - Los 1799 drivers CON LCA NO estan en tabla drivers (fuente cabinet_leads).
    - La tabla cabinet_drivers es un UNION de dos origenes:
      1799 de cabinet_leads (tienen LCA, no estan en drivers)
      1219 de drivers (NO tienen LCA, SI estan en drivers)
    - drivers.fire_date esta 96.1% NULL (no util para reactivacion masiva).
    - drivers.active = false para todos los cabinet (no es indicador confiable).

  REGLA FINAL:
    anchor_date = COALESCE(lead_created_at::date, hire_date::date, created_at::date)
    Donde hire_date se enriquece con drivers.hire_date via JOIN cuando es NULL en cabinet.

    lead_created_at sigue siendo NO GO como unico anchor por semantica invertida
    (21.7% de casos lca > hd). Pero funciona como fecha comercial complementaria.
""")

print('=' * 70)
print('FASE 0C COMPLETADA')
print('=' * 70)
