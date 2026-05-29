"""FASE 0 - CROSS-REFERENCE v2: Detalle post-match + external_id check."""
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

T = 'module_ct_cabinet_drivers'
L = 'module_ct_cabinet_leads'

# 1. park_phone NULL rate in leads
print('Q1. park_phone NULL rate in leads:')
r = q(f'SELECT COUNT(*) FROM {L}', 'scalar')
r2 = q(f"SELECT COUNT(*) FROM {L} WHERE park_phone IS NOT NULL AND park_phone::text != ''", 'scalar')
print(f'  Total leads: {r}')
print(f'  Has park_phone: {r2} ({round(100*r2/max(r,1),1)}%)')

# 2. external_id in leads vs driver_id in cabinet_drivers
print('\nQ2. external_id match con driver_id:')
r = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_id = cl.external_id
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
""", 'scalar')
print(f'  Matched by external_id = driver_id: {r}')

# 3. lead_created_at NULL rate in leads
print('\nQ3. lead_created_at NULL rate in leads:')
r = q(f"SELECT COUNT(*) FROM {L} WHERE lead_created_at IS NULL", 'scalar')
print(f'  NULL in leads: {r}')

# 4. Full match detail: name+plate overlap
print('\nQ4. Overlap name vs plate match:')
overlap_name_plate = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl1 ON LOWER(cd.driver_nombre) = LOWER(cl1.first_name)
                AND LOWER(cd.driver_apellido) = LOWER(cl1.last_name)
    JOIN {L} cl2 ON cd.driver_placa = cl2.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_nombre IS NOT NULL
""", 'scalar')
print(f'  Drivers matched by BOTH name AND plate: {overlap_name_plate}')

# Pure plate match count (reconfirm)
plate_match = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
      AND cl.asset_plate_number IS NOT NULL AND cl.asset_plate_number::text != ''
""", 'scalar')
print(f'  Pure plate match: {plate_match}')

# Pure name match
name_match = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
               AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_nombre IS NOT NULL AND cd.driver_nombre::text != ''
""", 'scalar')
print(f'  Pure name match: {name_match}')

# Union dedup
union_total = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl ON LOWER(cd2.driver_nombre) = LOWER(cl.first_name)
                     AND LOWER(cd2.driver_apellido) = LOWER(cl.last_name)
          WHERE cd2.driver_nombre IS NOT NULL
          UNION
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl2 ON cd3.driver_placa = cl2.asset_plate_number
          WHERE cd3.driver_placa IS NOT NULL AND cd3.driver_placa::text != ''
            AND cl2.asset_plate_number IS NOT NULL AND cl2.asset_plate_number::text != ''
      )
""", 'scalar')
print(f'  UNION total (dedup): {union_total}')

# 5. Breakdown: exclusive contributions
print('\nQ5. Aporte exclusivo de cada llave:')
name_exclusive = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
               AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_nombre IS NOT NULL
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl2 ON cd2.driver_placa = cl2.asset_plate_number
          WHERE cd2.driver_placa IS NOT NULL AND cd2.driver_placa::text != ''
            AND cl2.asset_plate_number IS NOT NULL AND cl2.asset_plate_number::text != ''
      )
""", 'scalar')
print(f'  Solo NAME (no plate): {name_exclusive}')

plate_exclusive = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl2 ON LOWER(cd2.driver_nombre) = LOWER(cl2.first_name)
                     AND LOWER(cd2.driver_apellido) = LOWER(cl2.last_name)
      )
""", 'scalar')
print(f'  Solo PLATE (no name): {plate_exclusive}')

print(f'  Ambos (name + plate): {overlap_name_plate}')
print(f'  TOTAL unicos = {name_exclusive + plate_exclusive + overlap_name_plate}')

# 6. Why 1082 can't be matched: profile of unmatchable drivers
print('\nQ6. Perfil de los 1082 NO recuperables:')
unmatchable = q(f"""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER(WHERE hire_date IS NOT NULL AND hire_date::text != '') AS with_hd,
        MIN(hire_date::date) FILTER(WHERE hire_date IS NOT NULL AND hire_date::text != '') AS min_hd,
        MAX(hire_date::date) FILTER(WHERE hire_date IS NOT NULL AND hire_date::text != '') AS max_hd
    FROM {T} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl ON LOWER(cd2.driver_nombre) = LOWER(cl.first_name)
                     AND LOWER(cd2.driver_apellido) = LOWER(cl.last_name)
          WHERE cd2.driver_nombre IS NOT NULL
          UNION
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl2 ON cd3.driver_placa = cl2.asset_plate_number
          WHERE cd3.driver_placa IS NOT NULL AND cd3.driver_placa::text != ''
            AND cl2.asset_plate_number IS NOT NULL AND cl2.asset_plate_number::text != ''
      )
""")
if isinstance(unmatchable, tuple):
    print(f'  Total no recuperables: {unmatchable[0]}')
    print(f'  Con hire_date: {unmatchable[1]} ({round(100*unmatchable[1]/unmatchable[0],1)}%)')
    print(f'  hd range: [{unmatchable[2]}, {unmatchable[3]}]')

# 7. Sample of plate matches (confirm quality)
print('\nQ7. Muestra PLATE match (5 rows):')
plate_sample = q(f"""
    SELECT cd.driver_id, cd.driver_placa, cd.driver_nombre || ' ' || cd.driver_apellido AS name,
           cl.lead_created_at, cl.asset_plate_number, cl.first_name || ' ' || cl.last_name AS lead_name,
           cd.hire_date
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
    LIMIT 5
""", fetch='all')
if isinstance(plate_sample, list):
    for row in plate_sample:
        print(f'  placa={str(row[1])[:10]}| driver={str(row[2])[:25]}| lca={row[3]}| lead_name={str(row[5])[:25]}| hd={row[6]}')

# 8. Leads without cabinet_drivers match (unused leads)
print('\nQ8. Leads sin match en cabinet_drivers:')
unused = q(f"""
    SELECT COUNT(*)
    FROM {L} cl
    WHERE cl.id NOT IN (
        SELECT DISTINCT cl2.id FROM {L} cl2
        JOIN {T} cd ON cd.driver_placa = cl2.asset_plate_number
        WHERE cd.origen = 'cabinet'
        UNION
        SELECT DISTINCT cl3.id FROM {L} cl3
        JOIN {T} cd2 ON LOWER(cd2.driver_nombre) = LOWER(cl3.first_name)
                    AND LOWER(cd2.driver_apellido) = LOWER(cl3.last_name)
        WHERE cd2.origen = 'cabinet'
    )
""", 'scalar')
print(f'  Leads without any cabinet_drivers match: {unused}')

# 9. drivers table cross-reference potential
print('\nQ9. drivers table: potential phone/license bridge:')
# Check if drivers table has phone that could match cabinet_drivers
bridge = q("""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM module_ct_cabinet_drivers cd
    JOIN drivers d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
""", 'scalar')
print(f'  Cabinet drivers matched to Yego drivers table: {bridge}')

# 10. Final summary numbers
print('\n' + '=' * 70)
print('RESUMEN FINAL DE ENRIQUECIMIENTO')
print('=' * 70)
total_cab = 3018
has_lca = 1799
missing = 1219
recovered_name = name_match
recovered_plate = plate_match
total_recovered = union_total
still_gone = 1082

print(f'''
  CABINET DRIVERS: {total_cab}

  Con LCA nativo:            {has_lca} ({round(100*has_lca/total_cab,1)}%)
  Sin LCA:                   {missing} ({round(100*missing/total_cab,1)}%)

  ENRIQUECIMIENTO DESDE module_ct_cabinet_leads:
  ├── Por PLACA:            +{recovered_plate} ({round(100*recovered_plate/missing,1)}% de missing)
  ├── Por NOMBRE:           +{recovered_name} ({round(100*recovered_name/missing,1)}% de missing)
  ├── Overlap name+plate:    -{overlap_name_plate}
  ├── Por PHONE:             +0 (park_phone es NULL en leads)
  ├── Por external_id:      +0 (no match con driver_id)
  └── TOTAL RECUPERADO:     {total_recovered} ({round(100*total_recovered/missing,1)}% de missing)

  POST-ENRIQUECIMIENTO:
  ├── Con LCA (nativo+recup):{has_lca+total_recovered} ({round(100*(has_lca+total_recovered)/total_cab,1)}%)
  └── SIN LCA definitivo:   {still_gone} ({round(100*still_gone/total_cab,1)}%)

  LLAVE MÁS EFECTIVA: asset_plate_number (131 de 906 leads útiles)
  LLAVE INÚTIL: park_phone (NULL en la mayoría de leads)
  LEADS NO UTILIZADOS: {unused} de 906

  CONCLUSIÓN:
  De los 1219 cabinet drivers sin lead_created_at, solo 137 (11.2%)
  pueden recuperarse desde module_ct_cabinet_leads. La tabla leads
  tiene solo 906 registros vs 3018 cabinet drivers, y las llaves de
  cruce (placa, nombre) tienen cobertura limitada.

  1082 cabinet drivers (35.9%) quedan SIN anchor comercial posible
  desde leads. Para ellos, hire_date sigue siendo el único anchor.

  PRÓXIMO PASO: cruzar con tabla drivers de Yego (154k registros)
  para ver si por driver_id se puede obtener hire_date adicional
  o alguna otra fecha de adquisición.
''')
