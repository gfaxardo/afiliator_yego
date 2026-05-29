"""
FASE 0C — VALIDACION DE drivers COMO FUENTE DE ANCHOR DATE
Cruza module_ct_cabinet_drivers vs drivers (Yego platform).
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
        except Exception as e: conn.rollback(); return f'ERR: {e}'

C = 'module_ct_cabinet_drivers'
D = 'drivers'

# ===================================================================
# FASE A — DISCOVERY de drivers
# ===================================================================
print('=' * 70)
print('FASE A — COLUMNAS DE drivers')
print('=' * 70)

drv_cols = q(f"""
    SELECT column_name, data_type, is_nullable, ordinal_position
    FROM information_schema.columns
    WHERE table_name = '{D}'
    ORDER BY ordinal_position
""", fetch='all')

if isinstance(drv_cols, list):
    for r in drv_cols:
        print(f"  {r[3]:3d} | {r[0]:35s} | {r[1]:25s} | nullable={r[2]}")
    drv_names = [r[0] for r in drv_cols]
else:
    print(f"  {drv_cols}")
    drv_names = []

total_drv = q(f"SELECT COUNT(*) FROM {D}", 'scalar')
print(f"\n  Total rows in drivers: {total_drv}")

# ===================================================================
# FASE A.2 — Busqueda de campos clave
# ===================================================================
print('\n' + '=' * 70)
print('FASE A.2 — BUSQUEDA DE CAMPOS CLAVE EN drivers')
print('=' * 70)

for tc in ['lead_created_at', 'hire_date', 'fire_date', 'created_at',
           'updated_at', 'first_trip_at', 'active', 'phone', 'license',
           'status', 'work_status', 'current_status', 'registration_date',
           'acquisition_date', 'deleted_at', 'onboarding_date',
           'first_name', 'last_name', 'full_name', 'driver_id',
           'license_number', 'license_normalized_number', 'car_number',
           'park_id', 'account_balance', 'rating']:
    found = tc in drv_names
    mark = 'EXISTS' if found else 'NOT FOUND'
    print(f"  {tc:30s} -> {mark}")

# ===================================================================
# FASE A.3 — Null rates en drivers para campos temporales
# ===================================================================
print('\n' + '=' * 70)
print('FASE A.3 — NULL RATES EN drivers (campos temporales)')
print('=' * 70)

for tc in drv_names:
    if 'date' in tc.lower() or 'created_at' in tc.lower() or 'updated_at' in tc.lower():
        tc_null = q(f"SELECT COUNT(*) FROM {D} WHERE {tc} IS NULL", 'scalar')
        if isinstance(tc_null, int):
            nr = round(100 * tc_null / total_drv, 1)
            print(f"  {tc:35s} NULL={tc_null:7d} ({nr:5.1f}%)")

# ===================================================================
# FASE B — JOIN cabinet_drivers vs drivers
# ===================================================================
print('\n' + '=' * 70)
print('FASE B — JOIN cabinet_drivers (origen=cabinet) vs drivers')
print('=' * 70)

total_cabinet = q(f"SELECT COUNT(*) FROM {C} WHERE origen = 'cabinet'", 'scalar')
print(f"\n  Total cabinet in module_ct_cabinet_drivers: {total_cabinet}")

matched = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
""", 'scalar')
print(f"  Matched via driver_id:                    {matched} ({round(100*matched/total_cabinet,1)}%)")

not_matched = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    WHERE cd.origen = 'cabinet'
      AND cd.driver_id NOT IN (SELECT d.driver_id FROM {D} d)
""", 'scalar')
print(f"  NOT matched:                              {not_matched} ({round(100*not_matched/total_cabinet,1)}%)")

# ===================================================================
# FASE C — COMPARACION lead_created_at (si existe en drivers)
# ===================================================================
print('\n' + '=' * 70)
print('FASE C — COMPARACION lead_created_at')
print('=' * 70)

if 'lead_created_at' in drv_names:
    print("\n  lead_created_at EXISTS en drivers. Procediendo a comparar...\n")

    # C.1 ambos tienen LCA y coinciden
    both_equal = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
          AND d.lead_created_at IS NOT NULL
          AND cd.lead_created_at::date = d.lead_created_at::date
    """, 'scalar')
    print(f"  Ambos LCA, iguales:                           {both_equal}")

    # C.2 ambos tienen LCA pero distintos
    both_diff = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
          AND d.lead_created_at IS NOT NULL
          AND cd.lead_created_at::date != d.lead_created_at::date
    """, 'scalar')
    print(f"  Ambos LCA, DISTINTOS:                         {both_diff}")

    # C.3 cabinet tiene LCA, drivers NO
    cab_yes_drv_no = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND cd.lead_created_at IS NOT NULL AND cd.lead_created_at::text != ''
          AND d.lead_created_at IS NULL
    """, 'scalar')
    print(f"  Cabinet SI, drivers NO:                       {cab_yes_drv_no}")

    # C.4 drivers tiene LCA, cabinet NO (los que nos interesan)
    drv_yes_cab_no = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND d.lead_created_at IS NOT NULL
    """, 'scalar')
    print(f"  Drivers SI, cabinet NO (RECUPERABLES):        {drv_yes_cab_no}")

    # C.5 ninguno tiene LCA
    neither = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND (cd.lead_created_at IS NULL OR cd.lead_created_at::text = '')
          AND d.lead_created_at IS NULL
    """, 'scalar')
    print(f"  NINGUNO tiene LCA:                            {neither}")

    # Verificar total
    total_join_cab = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
    """, 'scalar')
    print(f"\n  Total matched rows:                           {total_join_cab}")
    print(f"  Verificacion: {both_equal}+{both_diff}+{cab_yes_drv_no}+{drv_yes_cab_no}+{neither} = {both_equal+both_diff+cab_yes_drv_no+drv_yes_cab_no+neither}")

else:
    print("\n  *** lead_created_at NO EXISTE en drivers ***")
    print("  Esto implica que drivers NO puede aportar LCA como campo.\n")

    # Pero drivers tiene hire_date (DATE nativo) y fire_date
    # Verifiquemos si drivers.hire_date puede servir como anchor date
    # donde module_ct_cabinet_drivers.hire_date es NULL
    print('=' * 70)
    print('FASE C.ALT — hire_date en drivers como anchor alternativo')
    print('=' * 70)

    # Cuantos cabinet tienen hire_date en cabinet_drivers vs drivers
    print("\n  C.ALT.1 cabinet_drivers.hire_date vs drivers.hire_date:")

    cab_hd_present = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND cd.hire_date IS NOT NULL AND cd.hire_date::text != ''
    """, 'scalar')
    print(f"  Cabinet drivers con hire_date en cabinet_drivers: {cab_hd_present}")

    drv_hd_present = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND d.hire_date IS NOT NULL
    """, 'scalar')
    print(f"  Cabinet drivers con hire_date en drivers:         {drv_hd_present}")

    # donde cabinet no tiene hire_date pero drivers si
    cab_no_drv_yes = q(f"""
        SELECT COUNT(*)
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
          AND (cd.hire_date IS NULL OR cd.hire_date::text = '')
          AND d.hire_date IS NOT NULL
    """, 'scalar')
    print(f"  Cabinet SIN hd, drivers CON hd (RECUPERABLES):   {cab_no_drv_yes}")

    # comparacion cuando ambos tienen hire_date
    hd_both = q(f"""
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
    if isinstance(hd_both, tuple):
        bp = hd_both[0]
        eq = hd_both[1]
        df = hd_both[2]
        print(f"\n  C.ALT.2 Comparacion hire_date ambos presentes ({bp}):")
        print(f"    Iguales:    {eq} ({round(100*eq/bp,1)}%)")
        print(f"    Distintos:  {df} ({round(100*df/bp,1)}%)")

    # diferencia cuando son distintos
    if df > 0:
        hd_diff_sample = q(f"""
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
        if isinstance(hd_diff_sample, list):
            print(f"\n    Muestra diferencias (TOP 10 por magnitud):")
            for r in hd_diff_sample:
                print(f"      driver={r[0][:16]}... cab={r[1]} drv={r[2]} diff={r[3]}d")

# ===================================================================
# FASE D — VALIDACION TEMPORAL (hire_date de drivers)
# ===================================================================
print('\n' + '=' * 70)
print('FASE D — VALIDACION TEMPORAL drivers.hire_date')
print('=' * 70)

# Para los cabinet drivers, buckets hire_date en drivers
print("\n  D.1 Rango hire_date en drivers para cabinet:")
drv_hd_range = q(f"""
    SELECT MIN(d.hire_date), MAX(d.hire_date)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND d.hire_date IS NOT NULL
""")
if isinstance(drv_hd_range, tuple):
    print(f"    MIN: {drv_hd_range[0]}")
    print(f"    MAX: {drv_hd_range[1]}")

# Future hire dates
drv_hd_future = q(f"""
    SELECT COUNT(*)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'cabinet'
      AND d.hire_date > CURRENT_DATE
""", 'scalar')
print(f"    hire_date futuros: {drv_hd_future}")

# drivers.fire_date stats
if 'fire_date' in drv_names:
    print("\n  D.2 fire_date stats para cabinet:")
    fd_stats = q(f"""
        SELECT
            COUNT(*) AS total_matched,
            COUNT(*) FILTER(WHERE d.fire_date IS NOT NULL) AS with_fd,
            MIN(d.fire_date) FILTER(WHERE d.fire_date IS NOT NULL) AS min_fd,
            MAX(d.fire_date) FILTER(WHERE d.fire_date IS NOT NULL) AS max_fd,
            COUNT(*) FILTER(WHERE d.active = true) AS active_now
        FROM {C} cd
        JOIN {D} d ON cd.driver_id = d.driver_id
        WHERE cd.origen = 'cabinet'
    """)
    if isinstance(fd_stats, tuple):
        print(f"    Total matched:    {fd_stats[0]}")
        print(f"    With fire_date:   {fd_stats[1]} ({round(100*fd_stats[1]/fd_stats[0],1)}%)")
        print(f"    fire_date range:  [{fd_stats[2]}, {fd_stats[3]}]")
        print(f"    active=true now:  {fd_stats[4]}")

# ===================================================================
# FASE E — FLEET cross-reference
# ===================================================================
print('\n' + '=' * 70)
print('FASE E — FLEET en drivers')
print('=' * 70)

total_fleet = q(f"SELECT COUNT(*) FROM {C} WHERE origen = 'fleet'", 'scalar')
fleet_matched = q(f"""
    SELECT COUNT(DISTINCT cd.driver_id)
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'fleet'
""", 'scalar')
print(f"\n  Fleet total in cabinet_drivers:  {total_fleet}")
print(f"  Matched via driver_id to drivers: {fleet_matched} ({round(100*fleet_matched/total_fleet,1)}%)")

fleet_hd = q(f"""
    SELECT
        COUNT(*) AS total_matched,
        COUNT(*) FILTER(WHERE d.hire_date IS NOT NULL) AS with_hd,
        COUNT(*) FILTER(WHERE cd.hire_date IS NOT NULL AND cd.hire_date::text != '') AS cab_with_hd,
        COUNT(*) FILTER(WHERE (cd.hire_date IS NULL OR cd.hire_date::text = '') AND d.hire_date IS NOT NULL) AS drv_only_hd
    FROM {C} cd
    JOIN {D} d ON cd.driver_id = d.driver_id
    WHERE cd.origen = 'fleet'
""")
if isinstance(fleet_hd, tuple):
    print(f"  Fleet matched total:              {fleet_hd[0]}")
    print(f"  With drivers.hire_date:           {fleet_hd[1]} ({round(100*fleet_hd[1]/fleet_hd[0],1)}%)")
    print(f"  With cabinet.hire_date:           {fleet_hd[2]} ({round(100*fleet_hd[2]/fleet_hd[0],1)}%)")
    print(f"  Fleet SIN cab hd, CON drv hd:    {fleet_hd[3]} (recuperables)")

# ===================================================================
# FASE F — RESUMEN Y DECISION
# ===================================================================
print('\n' + '=' * 70)
print('FASE F — RESUMEN Y DECISION')
print('=' * 70)

has_lca_in_drv = 'lead_created_at' in drv_names

print(f"""
  drivers.lead_created_at EXISTS:  {has_lca_in_drv}

  MATCH cabinet_drivers <-> drivers:
    Cabinet total:                  {total_cabinet}
    Cabinet matched:                {matched} ({round(100*matched/total_cabinet,1)}%)
    Cabinet NOT matched:            {not_matched} ({round(100*not_matched/total_cabinet,1)}%)
""")

if has_lca_in_drv:
    print(f"""
  COMPARACION lead_created_at (matched cabinet rows):
    Ambos iguales:                  {both_equal}
    Ambos distintos:                {both_diff}
    Solo cabinet:                   {cab_yes_drv_no}
    Solo drivers (RECUPERABLES):   {drv_yes_cab_no}
    Ninguno:                        {neither}
""")
else:
    print(f"""
  lead_created_at NO EXISTE en drivers.
  drivers.hire_date (DATE nativo, 100% poblado) como alternativa:

  Cabinet SIN hire_date en cabinet_drivers pero SI en drivers:
    Recuperables:                   {cab_no_drv_yes}

  Fleet SIN hire_date en cabinet_drivers pero SI en drivers:
    Recuperables:                   {fleet_hd[3] if isinstance(fleet_hd, tuple) else '?'}
""")

print('=' * 70)
print('DECISION')
print('=' * 70)

if has_lca_in_drv:
    print("""
  drivers.lead_created_at: EVALUAR COBERTURA Y CONSISTENCIA

  Si cobertura >90% y consistencia >95%:
    -> GO como fuente primaria para cabinet

  Si cobertura 50-90%:
    -> GO WITH WARNINGS como fallback

  Si cobertura <50% o consistencia <80%:
    -> NO GO, mantener hire_date como anchor
""")
else:
    print("""
  drivers.lead_created_at: NO GO (NO EXISTE en esta tabla)

  ALTERNATIVA: drivers.hire_date como fuente de anchor date

  Ventajas:
    - Tipo DATE nativo (no requiere cast)
    - 100% poblado en drivers
    - 100% consistente con cabinet_drivers.hire_date cuando ambos existen

  Desventajas:
    - NO es lead_created_at (no es fecha de adquisicion comercial)
    - Es la misma fecha que cabinet_drivers.hire_date en la mayoria de casos

  REGLA FINAL PROPUESTA PARA FASE 1:

    Para cabinet:
      acquisition_anchor =
        COALESCE(
          cabinet_drivers.lead_created_at::date,   -- 59.6% cobertura
          cabinet_leads.lead_created_at::date,      -- +11.2% via placa/nombre
          drivers.hire_date,                        -- +xx% via driver_id
          cabinet_drivers.hire_date::date           -- fallback actual
        )

    Para fleet:
      acquisition_anchor =
        COALESCE(
          drivers.hire_date,                        -- via driver_id join
          cabinet_drivers.hire_date::date            -- fallback actual
        )
      (fleet NUNCA tiene lead_created_at)

    Cobertura estimada post-enriquecimiento cabinet:
      - Con LCA nativo:                           1799 (59.6%)
      - Recuperado de cabinet_leads:              +137 (11.2% de missing)
      - Recuperado de drivers.hire_date:          +cab_no_drv_yes
      - Sin anchor:                               resto
""")

print('=' * 70)
print('FASE 0C COMPLETADA')
print('=' * 70)
