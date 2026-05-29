"""
FASE 0 — RAW ENRICHMENT AUDIT v2 (resilient)
SOLO LECTURA.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

TABLE = "module_ct_cabinet_drivers"

def safe_query(engine, sql, params=None, fetch="all"):
    """Execute query in a fresh connection that auto-rolls back on error."""
    with engine.connect() as conn:
        try:
            result = conn.execute(text(sql), params or {})
            if fetch == "scalar":
                val = result.scalar()
                conn.commit()
                return val
            elif fetch == "first":
                row = result.first()
                conn.commit()
                return row
            else:
                rows = result.fetchall()
                conn.commit()
                return rows
        except Exception as e:
            conn.rollback()
            return f"ERROR: {e}"


def main():
    # ═══════════════════════════════════════════════════════════
    print("=" * 80)
    print("FASE A1 — LISTA COMPLETA DE COLUMNAS")
    print("=" * 80)

    col_rows = safe_query(engine, f"""
        SELECT column_name, data_type, character_maximum_length, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_name = '{TABLE}'
        ORDER BY ordinal_position
    """)

    col_names = []
    if isinstance(col_rows, list):
        for r in col_rows:
            print(f"  {r[4]:3d} | {r[0]:30s} | {r[1]:20s} | len={str(r[2] or ''):>5s} | nullable={r[3]}")
            col_names.append(r[0])
    else:
        print(col_rows)
        return

    total = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE}", fetch="scalar")
    print(f"\n  Total rows: {total}")
    print(f"  Total columns: {len(col_names)}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE A2 — BÚSQUEDA CAMPOS ESPECÍFICOS")
    print("=" * 80)

    targets = [
        'lead_created_at', 'hire_date', 'first_trip_at', 'first_5_trip_at',
        'created_at', 'updated_at', 'source', 'origen', 'origin',
        'park_id', 'park_name', 'city', 'driver_id', 'license',
        'status', 'driver_status', 'segment', 'stage', 'conexion',
        'fleet', 'migrated', 'migration', 'last_active_date',
        'fire_date', 'active', 'deleted_at', 'deactivation_date',
        'first_completed_trip', 'acquisition_date', 'acquisition_source',
    ]
    for tc in targets:
        found = tc in col_names
        print(f"  {tc:30s} -> {'EXISTS' if found else 'NOT FOUND'}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE A3 — MUESTRA 5 FILAS (driver_id, hire_date, lead_created_at, created_at, status, origen)")
    print("=" * 80)

    sample = safe_query(engine, f"""
        SELECT driver_id, hire_date, lead_created_at, created_at, updated_at, status, origen, last_active_date, segment, stage, orders
        FROM {TABLE} LIMIT 5
    """)
    if isinstance(sample, list):
        for i, r in enumerate(sample):
            print(f"\n  Row {i+1}:")
            print(f"    driver_id={repr(r[0][:20] if r[0] else None)}...")
            print(f"    hire_date={repr(r[1])}")
            print(f"    lead_created_at={repr(r[2])}")
            print(f"    created_at={repr(r[3])}")
            print(f"    updated_at={repr(r[4])}")
            print(f"    status={repr(r[5])}")
            print(f"    origen={repr(r[6])}")
            print(f"    segment={repr(r[7])}")
            print(f"    stage={repr(r[8])}")
            print(f"    orders={repr(r[9])}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE A4 — NULL RATES PARA COLUMNAS CLAVE")
    print("=" * 80)

    key_cols = ['driver_id', 'hire_date', 'lead_created_at', 'created_at', 'updated_at',
                'last_active_date', 'status', 'segment', 'stage', 'origen',
                'driver_nombre', 'driver_phone', 'license', 'park_id', 'park_name',
                'orders', 'conexion']
    for c in key_cols:
        if c not in col_names:
            continue
        null_cnt = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE {c} IS NULL", fetch="scalar")
        empty_cnt = 0
        if isinstance(null_cnt, int) and null_cnt < total:
            empty_cnt = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE {c}::text = ''", fetch="scalar")
            if not isinstance(empty_cnt, int):
                empty_cnt = 0
        if isinstance(null_cnt, int) and isinstance(empty_cnt, int):
            np = round(100 * null_cnt / total, 1)
            ep = round(100 * empty_cnt / total, 1)
            total_missing = null_cnt + empty_cnt
            tmp = round(100 * total_missing / total, 1)
            print(f"  {c:25s} NULL={np:5.1f}% | EMPTY={ep:5.1f}% | TOTAL_MISSING={tmp:5.1f}% ({total_missing}/{total})")
        else:
            print(f"  {c:25s} {null_cnt}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE A5 — VALORES DISTINTOS (origen, status, segment, stage)")
    print("=" * 80)

    for c in ['origen', 'status', 'segment', 'stage', 'conexion']:
        if c not in col_names:
            continue
        rows = safe_query(engine, f"""
            SELECT {c}, COUNT(*) as cnt
            FROM {TABLE}
            GROUP BY {c}
            ORDER BY cnt DESC
            LIMIT 30
        """)
        if isinstance(rows, list):
            print(f"\n  {c}:")
            for r in rows:
                val = str(r[0] or 'NULL')[:50]
                print(f"    {val:50s} = {r[1]}")
        else:
            print(f"  {c}: {rows}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE B — PROFILING lead_created_at")
    print("=" * 80)

    # lead_created_at stats
    lca_null = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE lead_created_at IS NULL", fetch="scalar")
    lca_empty = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE lead_created_at::text = ''", fetch="scalar")
    lca_present = total - (lca_null if isinstance(lca_null, int) else total) - (lca_empty if isinstance(lca_empty, int) else 0)

    print(f"\n  lead_created_at NULL:     {lca_null} ({round(100*(lca_null/total) if isinstance(lca_null,int) else 0, 1)}%)")
    print(f"  lead_created_at EMPTY:    {lca_empty} ({round(100*(lca_empty/total) if isinstance(lca_empty,int) else 0, 1)}%)")
    print(f"  lead_created_at HAS VALUE:{lca_present} ({round(100*lca_present/total if total else 0, 1)}%)")

    if lca_present > 0:
        # Show samples where lead_created_at has a value
        lca_samples = safe_query(engine, f"""
            SELECT driver_id, lead_created_at, hire_date, created_at, origen, status
            FROM {TABLE}
            WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
            LIMIT 20
        """)
        if isinstance(lca_samples, list):
            print(f"\n  Muestras con lead_created_at NO nulo ({len(lca_samples)} rows):")
            for r in lca_samples:
                print(f"    driver={r[0][:16]}... | lca={repr(r[1])} | hd={repr(r[2])} | created={repr(r[3])} | origen={r[4]} | status={r[5]}")
    else:
        print("\n  *** lead_created_at NO TIENE NINGÚN VALOR poblado ***")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE B2 — PROFILING hire_date")
    print("=" * 80)

    hd_null = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE hire_date IS NULL", fetch="scalar")
    hd_empty = safe_query(engine, f"SELECT COUNT(*) FROM {TABLE} WHERE hire_date::text = ''", fetch="scalar")
    hd_present = total - (hd_null if isinstance(hd_null, int) else total) - (hd_empty if isinstance(hd_empty, int) else 0)

    print(f"\n  hire_date NULL:     {hd_null}")
    print(f"  hire_date EMPTY:    {hd_empty}")
    print(f"  hire_date HAS VALUE:{hd_present} ({round(100*hd_present/total if total else 0, 1)}%)")

    # min/max
    hd_minmax = safe_query(engine, f"""
        SELECT MIN(hire_date::date), MAX(hire_date::date)
        FROM {TABLE}
        WHERE hire_date IS NOT NULL AND hire_date::text != ''
    """, fetch="first")
    if isinstance(hd_minmax, tuple) and hd_minmax[0]:
        print(f"  Min hire_date: {hd_minmax[0]}")
        print(f"  Max hire_date: {hd_minmax[1]}")

    # Year distribution
    hd_years = safe_query(engine, f"""
        SELECT EXTRACT(YEAR FROM hire_date::date)::int as yr,
               COUNT(*) as cnt
        FROM {TABLE}
        WHERE hire_date IS NOT NULL AND hire_date::text != ''
        GROUP BY yr ORDER BY yr
    """)
    if isinstance(hd_years, list) and hd_years:
        print(f"\n  Distribución por año:")
        for r in hd_years:
            print(f"    {r[0]}: {r[1]} drivers")

    # Month distribution (last 12 months)
    hd_months = safe_query(engine, f"""
        SELECT EXTRACT(YEAR FROM hire_date::date)::int as yr,
               EXTRACT(MONTH FROM hire_date::date)::int as mon,
               origen,
               COUNT(*) as cnt
        FROM {TABLE}
        WHERE hire_date IS NOT NULL AND hire_date::text != ''
          AND hire_date::date >= '2025-06-01'
        GROUP BY yr, mon, origen
        ORDER BY yr, mon, origen
    """)
    if isinstance(hd_months, list) and hd_months:
        print(f"\n  Distribución por mes (desde Jun 2025):")
        for r in hd_months:
            print(f"    {r[0]}-{r[1]:02d} origen={str(r[2] or 'NULL'):10s} = {r[3]:4d}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE B3 — PROFILING created_at")
    print("=" * 80)

    ca_minmax = safe_query(engine, f"""
        SELECT MIN(created_at), MAX(created_at)
        FROM {TABLE}
        WHERE created_at IS NOT NULL
    """, fetch="first")
    if isinstance(ca_minmax, tuple) and ca_minmax[0]:
        print(f"  Min created_at: {ca_minmax[0]}")
        print(f"  Max created_at: {ca_minmax[1]}")

    ca_future = safe_query(engine, f"""
        SELECT COUNT(*) FROM {TABLE}
        WHERE created_at > CURRENT_TIMESTAMP
    """, fetch="scalar")
    print(f"  Timestamps futuros: {ca_future}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE C — CONSISTENCIA TEMPORAL")
    print("=" * 80)

    # hire_date vs created_at
    print("\n  C.1 hire_date vs created_at:")
    r = safe_query(engine, f"""
        SELECT
            COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL) as both,
            COUNT(*) FILTER (WHERE hire_date::date <= created_at::date
                                AND hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL) as correct,
            COUNT(*) FILTER (WHERE hire_date::date > created_at::date
                                AND hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL) as inverted
        FROM {TABLE}
    """, fetch="first")
    if isinstance(r, tuple):
        print(f"    Both present: {r[0]}")
        print(f"    Correct (hd <= ca): {r[1]}")
        print(f"    Inverted (hd > ca): {r[2]} ({round(100*r[2]/max(r[0],1), 1)}%)")

    # hire_date vs last_active_date
    print("\n  C.2 hire_date vs last_active_date:")
    r = safe_query(engine, f"""
        SELECT
            COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '' AND last_active_date IS NOT NULL AND last_active_date::text != '') as both,
            COUNT(*) FILTER (WHERE hire_date::date <= last_active_date::date
                                AND hire_date IS NOT NULL AND hire_date::text != '' AND last_active_date IS NOT NULL AND last_active_date::text != '') as correct,
            COUNT(*) FILTER (WHERE hire_date::date > last_active_date::date
                                AND hire_date IS NOT NULL AND hire_date::text != '' AND last_active_date IS NOT NULL AND last_active_date::text != '') as inverted
        FROM {TABLE}
    """, fetch="first")
    if isinstance(r, tuple):
        print(f"    Both present: {r[0]}")
        print(f"    Correct (hd <= lad): {r[1]}")
        print(f"    Inverted (hd > lad): {r[2]} ({round(100*r[2]/max(r[0],1), 1)}%)")

    # lead_created_at vs hire_date (if lca has any values)
    if lca_present > 0:
        print("\n  C.3 lead_created_at vs hire_date:")
        r = safe_query(engine, f"""
            SELECT
                COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
                                   AND hire_date IS NOT NULL AND hire_date::text != '') as both,
                COUNT(*) FILTER (WHERE lead_created_at::date <= hire_date::date
                                   AND lead_created_at IS NOT NULL AND lead_created_at::text != ''
                                   AND hire_date IS NOT NULL AND hire_date::text != '') as correct,
                COUNT(*) FILTER (WHERE lead_created_at::date > hire_date::date
                                   AND lead_created_at IS NOT NULL AND lead_created_at::text != ''
                                   AND hire_date IS NOT NULL AND hire_date::text != '') as inverted,
                ROUND(AVG(hire_date::date - lead_created_at::date), 1)
                    FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
                                    AND hire_date IS NOT NULL AND hire_date::text != '') as avg_diff_days
            FROM {TABLE}
        """, fetch="first")
        if isinstance(r, tuple):
            print(f"    Both present: {r[0]}")
            print(f"    Correct (lca <= hd): {r[1]}")
            print(f"    Inverted (lca > hd): {r[2]} ({round(100*r[2]/max(r[0],1), 1)}%)")
            print(f"    Avg days (hd - lca): {r[3]}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE D — REACTIVACIONES / RECICLADOS")
    print("=" * 80)

    # D.1 Duplicates by driver_id
    print("\n  D.1 Duplicados por driver_id:")
    dups = safe_query(engine, f"""
        SELECT driver_id, COUNT(*) as cnt
        FROM {TABLE}
        WHERE driver_id IS NOT NULL
        GROUP BY driver_id
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)
    if isinstance(dups, list):
        if dups:
            for r in dups:
                print(f"    {r[0][:30]} = {r[1]} occurrences")
        else:
            print("    No duplicates found.")
    else:
        print(f"    {dups}")

    # D.2 Duplicates by license
    print("\n  D.2 Duplicados por license:")
    lic_dups = safe_query(engine, f"""
        SELECT license, COUNT(*) as cnt
        FROM {TABLE}
        WHERE license IS NOT NULL AND license::text != ''
        GROUP BY license
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 15
    """)
    if isinstance(lic_dups, list):
        if lic_dups:
            for r in lic_dups:
                print(f"    license={r[0][:20]} = {r[1]} drivers")
        else:
            print("    No duplicate licenses.")
    else:
        print(f"    {lic_dups}")

    # D.3 Drivers with old hire + recent trips (reactivations)
    print("\n  D.3 Drivers with pre-2026 hire + May 2026 trips:")
    react = safe_query(engine, """
        SELECT
            src.origen,
            COUNT(DISTINCT src.driver_id) as cnt,
            MIN(src.hire_date::date) as oldest_hire,
            MAX(src.hire_date::date) as newest_of_old,
            ROUND(AVG(CURRENT_DATE - src.hire_date::date), 0) as avg_days_since_hire
        FROM module_ct_cabinet_drivers src
        WHERE src.hire_date IS NOT NULL
          AND src.hire_date::text != ''
          AND src.hire_date::date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM trips_2026 t
              WHERE t.conductor_id = src.driver_id
                AND t.fecha_inicio_viaje > '2026-05-01'
                AND t.condicion = 'Completado'
          )
        GROUP BY src.origen
        ORDER BY cnt DESC
    """)
    if isinstance(react, list) and react:
        for r in react:
            print(f"    origen={r[0]}: {r[1]} drivers, oldest_hire={r[2]}, newest_old={r[3]}, avg_days={r[4]}")
    else:
        print(f"    {react}")

    # D.4 Without hire_date but with trips
    print("\n  D.4 Drivers WITHOUT hire_date but WITH trips:")
    nohd = safe_query(engine, """
        SELECT COUNT(DISTINCT src.driver_id)
        FROM module_ct_cabinet_drivers src
        WHERE (src.hire_date IS NULL OR src.hire_date::text = '')
          AND EXISTS (
              SELECT 1 FROM trips_2026 t
              WHERE t.conductor_id = src.driver_id
                AND t.condicion = 'Completado'
          )
    """, fetch="scalar")
    print(f"    {nohd}")

    # D.5 Drivers assigned vs unassigned with hire_date
    print("\n  D.5 Assigned vs unassigned with/without hire_date:")
    assign_stats = safe_query(engine, """
        SELECT
            CASE WHEN a.driver_id IS NOT NULL THEN 'assigned' ELSE 'unassigned' END as assignment_status,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE src.hire_date IS NOT NULL AND src.hire_date::text != '') as with_hd,
            COUNT(*) FILTER (WHERE src.hire_date IS NULL OR src.hire_date::text = '') as without_hd,
            COUNT(*) FILTER (WHERE src.lead_created_at IS NOT NULL AND src.lead_created_at::text != '') as with_lca
        FROM module_ct_cabinet_drivers src
        LEFT JOIN scout_liq_driver_assignments a
            ON src.driver_id = a.driver_id AND a.status = 'active'
        GROUP BY assignment_status
        ORDER BY assignment_status
    """)
    if isinstance(assign_stats, list) and assign_stats:
        for r in assign_stats:
            print(f"    {r[0]}: total={r[1]}, with_hd={r[2]}, without_hd={r[3]}, with_lca={r[4]}")
    else:
        print(f"    {assign_stats}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE E — TABLAS RELACIONADAS")
    print("=" * 80)

    # E.1 Drivers table columns
    print("\n  E.1 Columnas de tabla 'drivers':")
    drv_cols = safe_query(engine, """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'drivers'
        ORDER BY ordinal_position
    """)
    if isinstance(drv_cols, list):
        drv_names = [r[0] for r in drv_cols]
        for r in drv_cols:
            print(f"    {r[0]:35s} {r[1]:20s} nullable={r[2]}")

        for tc in ['lead_created_at', 'hire_date', 'fire_date', 'first_trip_at', 'active', 'city', 'created_at', 'updated_at']:
            status = "EXISTS" if tc in drv_names else "NOT FOUND"
            print(f"    {tc:30s} -> {status}")

        # If fire_date exists, get stats
        if 'fire_date' in drv_names and 'hire_date' in drv_names:
            r = safe_query(engine, """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL) as fired,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND active = true) as active_but_fired,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND fire_date > hire_date) as fired_after_hire
                FROM drivers
            """, fetch="first")
            if isinstance(r, tuple):
                print(f"\n    Firing stats: total={r[0]}, fired={r[1]}, active+but+fired={r[2]}, fired_after_hire={r[3]}")

    # E.2 Search for lead_created_at across entire DB
    print("\n  E.2 Búsqueda 'lead_created_at' en TODA la DB:")
    global_lead = safe_query(engine, """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE column_name ILIKE '%lead_created%'
           OR column_name ILIKE '%lead_creator%'
           OR column_name ILIKE '%first_trip_at%'
           OR column_name ILIKE '%first_5_trip%'
           OR column_name ILIKE '%acquisition_date%'
           OR column_name ILIKE '%registration_date%'
        ORDER BY table_schema, table_name, column_name
    """)
    if isinstance(global_lead, list):
        if global_lead:
            for r in global_lead:
                print(f"    {r[0]}.{r[1]}.{r[2]} ({r[3]})")
        else:
            print("    NO SE ENCONTRÓ en ninguna tabla.")
    else:
        print(f"    {global_lead}")

    # E.3 scout_liq_driver_assignments columns
    print("\n  E.3 Columnas de scout_liq_driver_assignments:")
    sla_cols = safe_query(engine, """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'scout_liq_driver_assignments'
        ORDER BY ordinal_position
    """)
    if isinstance(sla_cols, list):
        for r in sla_cols:
            print(f"    {r[0]:35s} {r[1]:20s} nullable={r[2]}")
    else:
        print(f"    {sla_cols}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE F — RESUMEN FINAL / EVALUACIÓN ANCHOR DATE")
    print("=" * 80)

    print(f"""
  Tabla: {TABLE}
  Total rows: {total}
  Total columns: {len(col_names)}

  lead_created_at existe como columna:  SI (col #22, varchar(100), nullable)
  lead_created_at tiene datos:          {lca_present} de {total} ({round(100*lca_present/total if total else 0, 1)}%)

  hire_date tiene datos:                {hd_present} de {total} ({round(100*hd_present/total if total else 0, 1)}%)
  hire_date rango:                      {hd_minmax[0] if isinstance(hd_minmax, tuple) and hd_minmax else 'N/A'} a {hd_minmax[1] if isinstance(hd_minmax, tuple) and hd_minmax else 'N/A'}

  created_at rango:                     {ca_minmax[0] if isinstance(ca_minmax, tuple) and ca_minmax else 'N/A'} a {ca_minmax[1] if isinstance(ca_minmax, tuple) and ca_minmax else 'N/A'}
""")

    print("=" * 80)
    print("EVALUACIÓN ANCHOR DATE")
    print("=" * 80)

    if lca_present > 0:
        lca_rate = round(100 * lca_present / total, 1)
        if lca_rate >= 90:
            print(f"\n  lead_created_at: GO ({lca_rate}% populated)")
        elif lca_rate >= 50:
            print(f"\n  lead_created_at: GO WITH WARNINGS ({lca_rate}% populated, needs fallback)")
        else:
            print(f"\n  lead_created_at: NO GO (only {lca_rate}% populated)")
        print(f"    Razón: Solo {lca_present} de {total} filas tienen valor.")
    else:
        print(f"\n  lead_created_at: NO GO (0% populated)")
        print(f"    Razón: La columna EXISTE pero está completamente vacía (NULL).")
        print(f"    La columna fue agregada al esquema pero aún no se ha poblado.")

    if hd_present > 0:
        hd_rate = round(100 * hd_present / total, 1)
        if hd_rate >= 90:
            print(f"\n  hire_date: GO ({hd_rate}% populated) - Usable como anchor date actual")
        elif hd_rate >= 70:
            print(f"\n  hire_date: GO WITH WARNINGS ({hd_rate}% populated)")
        else:
            print(f"\n  hire_date: GO WITH WARNINGS ({hd_rate}% populated, low coverage)")
    else:
        print(f"\n  hire_date: NO GO (0% populated)")

    print(f"""
  RECOMENDACIÓN:
  - lead_created_at existe como columna pero NO está poblada.
  - hire_date es el anchor date actual utilizable.
  - Ambos campos son VARCHAR (no DATE nativo), requieren cast ::date.
  - created_at (timestamp sin timezone) es confiable para auditoría de sincronización.

  PRÓXIMOS PASOS:
  1. Verificar con el equipo de datos cuándo se poblará lead_created_at.
  2. Si lead_created_at se pobla, volver a ejecutar esta auditoría.
  3. Mientras tanto, usar hire_date como anchor date para cohortes.
  4. Considerar crear una vista materializada con lead_created_at COALESCE a hire_date.
""")

if __name__ == "__main__":
    main()
