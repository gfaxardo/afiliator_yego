"""
FASE 0 — CROSS-REFERENCE: cabinet_drivers sin LCA vs module_ct_cabinet_leads
Enriquecimiento de lead_created_at desde tabla leads.
SOLO LECTURA.
"""
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
        except Exception as e:
            conn.rollback()
            return f'ERR: {e}'

T = 'module_ct_cabinet_drivers'
L = 'module_ct_cabinet_leads'

# ══════════════════════════════════════════════════════════
# 0. COLUMNAS DE module_ct_cabinet_leads
# ══════════════════════════════════════════════════════════
print('=' * 70)
print('0. COLUMNAS DE module_ct_cabinet_leads')
print('=' * 70)
cols = q(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{L}' ORDER BY ordinal_position", fetch='all')
if isinstance(cols, list):
    for r in cols:
        print(f"  {r[0]:30s} {r[1]}")

# Sample rows from leads
print('\n  Muestra (3 filas):')
sample = q(f"SELECT * FROM {L} LIMIT 3", fetch='all')
if isinstance(sample, list):
    col_names = [c[0] for c in cols]
    for i, row in enumerate(sample):
        print(f'\n  --- Row {i+1} ---')
        for j, val in enumerate(row):
            if j < len(col_names):
                v = str(val)[:60] if val is not None else 'NULL'
                print(f'    {col_names[j]:25s} = {v}')

# ══════════════════════════════════════════════════════════
# 1. UNIVERSE: cabinet drivers SIN lead_created_at
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('1. UNIVERSO: cabinet drivers SIN lead_created_at')
print('=' * 70)

base = q(f"""
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') AS with_hd,
           COUNT(*) FILTER (WHERE driver_phone IS NOT NULL AND driver_phone::text != '') AS with_phone,
           COUNT(*) FILTER (WHERE license IS NOT NULL AND license::text != '') AS with_license,
           COUNT(*) FILTER (WHERE driver_nombre IS NOT NULL AND driver_apellido IS NOT NULL
                            AND driver_nombre::text != '' AND driver_apellido::text != '') AS with_fullname,
           COUNT(*) FILTER (WHERE driver_placa IS NOT NULL AND driver_placa::text != '') AS with_plate
    FROM {T}
    WHERE origen = 'cabinet'
      AND (lead_created_at IS NULL OR lead_created_at::text = '')
""")
print(f"  Cabinet sin LCA total:       {base[0]}")
print(f"  Con hire_date:               {base[1]}")
print(f"  Con phone:                   {base[2]}")
print(f"  Con license:                 {base[3]}")
print(f"  Con nombre completo:         {base[4]}")
print(f"  Con placa:                   {base[5]}")

# ══════════════════════════════════════════════════════════
# 2. MATCH POR PHONE (driver_phone <-> park_phone)
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('2. MATCH POR PHONE: driver_phone = leads.park_phone')
print('=' * 70)

phone_match = q(f"""
    SELECT
        COUNT(DISTINCT cd.driver_id) AS matched_drivers,
        COUNT(DISTINCT cl.id) AS matched_leads
    FROM {T} cd
    JOIN {L} cl ON cd.driver_phone = cl.park_phone
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
      AND cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
""")
print(f"  Drivers matched:  {phone_match[0]}")
print(f"  Leads matched:    {phone_match[1]}")

# Sample
if phone_match[0] > 0:
    phone_sample = q(f"""
        SELECT cd.driver_id, cd.driver_phone, cd.driver_nombre || ' ' || cd.driver_apellido AS driver_name,
               cl.lead_created_at, cl.first_name || ' ' || cl.last_name AS lead_name,
               cl.status AS lead_status, cd.hire_date, cd.status
        FROM {T} cd
        JOIN {L} cl ON cd.driver_phone = cl.park_phone
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
          AND cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
        LIMIT 5
    """, fetch='all')
    if isinstance(phone_sample, list):
        print(f'  Muestra ({len(phone_sample)}):')
        for r in phone_sample:
            print(f'    phone={r[1][:14]}| driver={str(r[2])[:25]}| lca={r[3]}| lead_name={str(r[4])[:25]}| hd={r[5]}')

# Check if any phone has multiple leads (ambiguity)
phone_dup = q(f"""
    SELECT COUNT(*) AS phones_with_multiple_leads
    FROM (
        SELECT cl.park_phone, COUNT(*) AS cnt
        FROM {L} cl
        WHERE cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
        GROUP BY cl.park_phone
        HAVING COUNT(*) > 1
    ) dup
""", fetch='scalar')
print(f'  Phones with multiple leads: {phone_dup}')

# ══════════════════════════════════════════════════════════
# 3. MATCH POR NOMBRE (nombre + apellido <-> first_name + last_name)
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('3. MATCH POR NOMBRE COMPLETO')
print('=' * 70)

name_match = q(f"""
    SELECT
        COUNT(DISTINCT cd.driver_id) AS matched_drivers,
        COUNT(DISTINCT cl.id) AS matched_leads
    FROM {T} cd
    JOIN {L} cl
        ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
       AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_nombre IS NOT NULL AND cd.driver_nombre::text != ''
      AND cd.driver_apellido IS NOT NULL AND cd.driver_apellido::text != ''
""")
print(f"  Drivers matched:  {name_match[0]}")
print(f"  Leads matched:    {name_match[1]}")

if name_match[0] > 0:
    name_sample = q(f"""
        SELECT cd.driver_id, cd.driver_nombre || ' ' || cd.driver_apellido AS driver_name,
               cl.lead_created_at, cl.first_name || ' ' || cl.last_name AS lead_name,
               cd.hire_date, cd.status
        FROM {T} cd
        JOIN {L} cl
            ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
           AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND cd.driver_nombre IS NOT NULL AND cd.driver_nombre::text != ''
        LIMIT 5
    """, fetch='all')
    if isinstance(name_sample, list):
        print(f'  Muestra ({len(name_sample)}):')
        for r in name_sample:
            print(f'    driver={str(r[1])[:30]}| lca={r[2]}| lead_name={str(r[3])[:30]}| hd={r[4]}')

# ══════════════════════════════════════════════════════════
# 4. MATCH POR PLACA (driver_placa <-> asset_plate_number)
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('4. MATCH POR PLACA: driver_placa = asset_plate_number')
print('=' * 70)

plate_match = q(f"""
    SELECT
        COUNT(DISTINCT cd.driver_id) AS matched_drivers,
        COUNT(DISTINCT cl.id) AS matched_leads
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
      AND cl.asset_plate_number IS NOT NULL AND cl.asset_plate_number::text != ''
""")
print(f"  Drivers matched:  {plate_match[0]}")
print(f"  Leads matched:    {plate_match[1]}")

# ══════════════════════════════════════════════════════════
# 5. MATCH POR PHONE + NOMBRE (más seguro)
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('5. MATCH POR PHONE + NOMBRE (intersección)')
print('=' * 70)

phone_name_match = q(f"""
    SELECT
        COUNT(DISTINCT cd.driver_id) AS matched_drivers
    FROM {T} cd
    JOIN {L} cl
        ON cd.driver_phone = cl.park_phone
       AND LOWER(cd.driver_nombre) = LOWER(cl.first_name)
       AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
""")
print(f"  Drivers matched (phone+name):  {phone_name_match[0]}")

# ══════════════════════════════════════════════════════════
# 6. UNION DE TODOS LOS MATCHES (deduplicado)
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('6. MATCH TOTAL: UNION de phone + name + plate (dedup)')
print('=' * 70)

# First by phone
union_match = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id IN (
          -- Phone match
          SELECT cd2.driver_id
          FROM {T} cd2
          JOIN {L} cl ON cd2.driver_phone = cl.park_phone
          WHERE cd2.driver_phone IS NOT NULL AND cd2.driver_phone::text != ''
            AND cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
          UNION
          -- Name match
          SELECT cd3.driver_id
          FROM {T} cd3
          JOIN {L} cl2
            ON LOWER(cd3.driver_nombre) = LOWER(cl2.first_name)
           AND LOWER(cd3.driver_apellido) = LOWER(cl2.last_name)
          WHERE cd3.driver_nombre IS NOT NULL
            AND cd3.driver_apellido IS NOT NULL
            AND cd3.driver_nombre::text != ''
            AND cd3.driver_apellido::text != ''
          UNION
          -- Plate match
          SELECT cd4.driver_id
          FROM {T} cd4
          JOIN {L} cl3 ON cd4.driver_placa = cl3.asset_plate_number
          WHERE cd4.driver_placa IS NOT NULL AND cd4.driver_placa::text != ''
            AND cl3.asset_plate_number IS NOT NULL AND cl3.asset_plate_number::text != ''
      )
""", fetch='scalar')
print(f"  Drivers recuperables TOTAL:  {union_match}")

# ══════════════════════════════════════════════════════════
# 7. DESGLOSE POR LLAVE
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('7. DESGLOSE: cuántos matchean por cada llave (sin overlap)')
print('=' * 70)

# Exact count per key, without counting overlaps
phone_only = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_phone = cl.park_phone
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
      AND cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
""", fetch='scalar')

name_only = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl
        ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
       AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_nombre IS NOT NULL AND cd.driver_nombre::text != ''
      AND cd.driver_apellido IS NOT NULL AND cd.driver_apellido::text != ''
""", fetch='scalar')

plate_only = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
      AND cl.asset_plate_number IS NOT NULL AND cl.asset_plate_number::text != ''
""", fetch='scalar')

phone_name_int = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl
        ON cd.driver_phone = cl.park_phone
       AND LOWER(cd.driver_nombre) = LOWER(cl.first_name)
       AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
""", fetch='scalar')

# Overlap between phone and name
phone_name_union = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl ON cd2.driver_phone = cl.park_phone
          WHERE cd2.driver_phone IS NOT NULL AND cd2.driver_phone::text != ''
          UNION
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl2
            ON LOWER(cd3.driver_nombre) = LOWER(cl2.first_name)
           AND LOWER(cd3.driver_apellido) = LOWER(cl2.last_name)
      )
""", fetch='scalar')

print(f"  Match por PHONE:              {phone_only}")
print(f"  Match por FULL NAME:          {name_only}")
print(f"  Match por PLATE:              {plate_only}")
print(f"  Match PHONE+NAME (intersect): {phone_name_int}")
print(f"  UNION phone+name (dedup):     {phone_name_union}")
print(f"  Overlap phone & name:         {phone_only + name_only - phone_name_union}")

# ══════════════════════════════════════════════════════════
# 8. CALIDAD DEL MATCH: ¿hay ambigüedad?
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('8. CALIDAD: ambigüedad en matches')
print('=' * 70)

# Phone: one driver matched to multiple leads
phone_amb = q(f"""
    SELECT COUNT(*) AS drivers_with_multi_leads
    FROM (
        SELECT cd.driver_id, COUNT(DISTINCT cl.id) AS lead_count
        FROM {T} cd
        JOIN {L} cl ON cd.driver_phone = cl.park_phone
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
        GROUP BY cd.driver_id
        HAVING COUNT(DISTINCT cl.id) > 1
    ) sub
""", fetch='scalar')
print(f"  Drivers con >1 lead por phone:   {phone_amb}")

name_amb = q(f"""
    SELECT COUNT(*) AS drivers_with_multi_leads
    FROM (
        SELECT cd.driver_id, COUNT(DISTINCT cl.id) AS lead_count
        FROM {T} cd
        JOIN {L} cl
            ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
           AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
        GROUP BY cd.driver_id
        HAVING COUNT(DISTINCT cl.id) > 1
    ) sub
""", fetch='scalar')
print(f"  Drivers con >1 lead por name:    {name_amb}")

# One lead matched to multiple drivers (ambiguity)
lead_to_multi = q(f"""
    SELECT COUNT(*) AS leads_with_multi_drivers
    FROM (
        SELECT cl.id, COUNT(DISTINCT cd.driver_id) AS driver_count
        FROM {T} cd
        JOIN {L} cl ON cd.driver_phone = cl.park_phone
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
        GROUP BY cl.id
        HAVING COUNT(DISTINCT cd.driver_id) > 1
    ) sub
""", fetch='scalar')
print(f"  Leads con >1 driver (por phone): {lead_to_multi}")

# ══════════════════════════════════════════════════════════
# 9. RESULTADO FINAL: cuántos quedan sin anchor comercial
# ══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('9. RESULTADO FINAL')
print('=' * 70)

total_cabinet = q(f"SELECT COUNT(*) FROM {T} WHERE origen = 'cabinet'", fetch='scalar')
has_lca_already = q(f"SELECT COUNT(*) FROM {T} WHERE origen = 'cabinet' AND lead_created_at IS NOT NULL AND lead_created_at::text != ''", fetch='scalar')
missing_lca = total_cabinet - has_lca_already
recoverable = union_match if isinstance(union_match, int) else 0
still_missing = missing_lca - recoverable

print(f"")
print(f"  Cabinet drivers TOTAL:                {total_cabinet}")
print(f"  Ya tienen LCA:                        {has_lca_already} ({round(100*has_lca_already/total_cabinet,1)}%)")
print(f"  Sin LCA (missing):                    {missing_lca} ({round(100*missing_lca/total_cabinet,1)}%)")
print(f"  ---")
print(f"  Recuperables desde leads:             {recoverable} ({round(100*recoverable/missing_lca,1)}% de missing)")
print(f"  Definitivamente SIN anchor comercial: {still_missing} ({round(100*still_missing/total_cabinet,1)}% del total cabinet)")
print(f"")

# Coverage after enrichment
after_enrich = has_lca_already + recoverable
print(f"  COBERTURA POST-ENRIQUECIMIENTO:")
print(f"  Con LCA (nativo + recuperado):        {after_enrich} ({round(100*after_enrich/total_cabinet,1)}%)")
print(f"  Sin LCA definitivo:                   {still_missing} ({round(100*still_missing/total_cabinet,1)}%)")
print(f"")

# ══════════════════════════════════════════════════════════
# 10. DESGLOSE FINAL POR LLAVE (quién aporta qué)
# ══════════════════════════════════════════════════════════
print('=' * 70)
print('10. APORTE POR LLAVE AL ENRIQUECIMIENTO')
print('=' * 70)

phone_contrib = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_phone = cl.park_phone
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_phone IS NOT NULL AND cd.driver_phone::text != ''
      AND cl.park_phone IS NOT NULL AND cl.park_phone::text != ''
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl2 ON LOWER(cd2.driver_nombre) = LOWER(cl2.first_name)
                       AND LOWER(cd2.driver_apellido) = LOWER(cl2.last_name)
          WHERE cd2.origen = 'cabinet'
            AND (cd2.lead_created_at IS NULL OR cd2.lead_created_at::text = '')
      )
      AND cd.driver_id NOT IN (
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl3 ON cd3.driver_placa = cl3.asset_plate_number
          WHERE cd3.origen = 'cabinet'
            AND (cd3.lead_created_at IS NULL OR cd3.lead_created_at::text = '')
            AND cd3.driver_placa IS NOT NULL AND cd3.driver_placa::text != ''
      )
""", fetch='scalar')

name_only_contrib = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON LOWER(cd.driver_nombre) = LOWER(cl.first_name)
               AND LOWER(cd.driver_apellido) = LOWER(cl.last_name)
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl2 ON cd2.driver_phone = cl2.park_phone
          WHERE cd2.origen = 'cabinet'
            AND (cd2.lead_created_at IS NULL OR cd2.lead_created_at::text = '')
            AND cd2.driver_phone IS NOT NULL AND cd2.driver_phone::text != ''
      )
      AND cd.driver_id NOT IN (
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl3 ON cd3.driver_placa = cl3.asset_plate_number
          WHERE cd3.origen = 'cabinet'
            AND (cd3.lead_created_at IS NULL OR cd3.lead_created_at::text = '')
            AND cd3.driver_placa IS NOT NULL AND cd3.driver_placa::text != ''
      )
""", fetch='scalar')

plate_only_contrib = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {T} cd
    JOIN {L} cl ON cd.driver_placa = cl.asset_plate_number
    WHERE cd.origen = 'cabinet'
      AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
      AND cd.driver_placa IS NOT NULL AND cd.driver_placa::text != ''
      AND cd.driver_id NOT IN (
          SELECT cd2.driver_id FROM {T} cd2
          JOIN {L} cl2 ON cd2.driver_phone = cl2.park_phone
          WHERE cd2.origen = 'cabinet'
            AND (cd2.lead_created_at IS NULL OR cd2.lead_created_at::text = '')
            AND cd2.driver_phone IS NOT NULL AND cd2.driver_phone::text != ''
      )
      AND cd.driver_id NOT IN (
          SELECT cd3.driver_id FROM {T} cd3
          JOIN {L} cl3 ON LOWER(cd3.driver_nombre) = LOWER(cl3.first_name)
                       AND LOWER(cd3.driver_apellido) = LOWER(cl3.last_name)
          WHERE cd3.origen = 'cabinet'
            AND (cd3.lead_created_at IS NULL OR cd3.lead_created_at::text = '')
      )
""", fetch='scalar')

overlap_phone_name = phone_only + name_only - phone_name_union
# The overlap between all three is complicated. Let me just present what we have.

print(f"")
print(f"  Llave               | Total match | Exclusivos | Confianza")
print(f"  ---------------------|-------------|------------|----------")
print(f"  PHONE                | {phone_only:11d} | {phone_contrib if isinstance(phone_contrib,int) else '?':10s} | ALTA (unicidad OK)")
print(f"  FULL NAME            | {name_only:11d} | {name_only_contrib if isinstance(name_only_contrib,int) else '?':10s} | MEDIA (homónimos)")
print(f"  PLATE                | {plate_only:11d} | {plate_only_contrib if isinstance(plate_only_contrib,int) else '?':10s} | MEDIA (cambio placa)")
print(f"  PHONE + NAME (inter) | {phone_name_int:11d} | —         | MUY ALTA")
print(f"")

print('=' * 70)
print('CROSS-REFERENCE COMPLETADO')
print('=' * 70)
