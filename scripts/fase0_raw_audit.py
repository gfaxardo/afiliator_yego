"""
FASE 0 — RAW ENRICHMENT AUDIT & ACQUISITION DATE VALIDATION
Auditoría completa de module_ct_cabinet_drivers
SOLO LECTURA. NO modifica, NO altera, NO migra.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # ═══════════════════════════════════════════════════════════════
        # FASE A — DISCOVERY REAL
        # ═══════════════════════════════════════════════════════════════
        print("=" * 80)
        print("FASE A — DISCOVERY REAL: COLUMNAS DE module_ct_cabinet_drivers")
        print("=" * 80)

        columns = conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_name = 'module_ct_cabinet_drivers'
            ORDER BY ordinal_position
        """)).fetchall()

        print(f"\n{'#':>3s} | {'COLUMN':35s} | {'TYPE':20s} | {'LEN':>5s} | NULLABLE")
        print("-" * 95)
        col_names = []
        for r in columns:
            print(f"{r[4]:3d} | {r[0]:35s} | {r[1]:20s} | {str(r[2] or ''):>5s} | {r[3]}")
            col_names.append(r[0])

        print(f"\nTotal columns: {len(columns)}")

        # Quick count
        total = conn.execute(text("SELECT COUNT(*) FROM module_ct_cabinet_drivers")).scalar()
        print(f"Total rows: {total}")

        # ═══════════════════════════════════════════════════════════════
        # FASE A.2 — Búsqueda de columnas específicas
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE A.2 — BÚSQUEDA DE COLUMNAS ESPECÍFICAS")
        print("=" * 80)

        target_cols = [
            'lead_created_at', 'hire_date', 'first_trip_at', 'first_5_trip_at',
            'created_at', 'updated_at', 'source', 'origen', 'origin',
            'park_id', 'park_name', 'city', 'driver_id', 'license',
            'status', 'driver_status', 'segment', 'stage', 'conexion',
            'fleet', 'migrated', 'migration', 'last_active_date',
            'driver_nombre', 'driver_apellido', 'driver_placa', 'driver_phone',
            'viajes_0_7', 'viajes_8_14', 'orders', 'fire_date', 'active',
            'blocked', 'blocked_reason', 'source_created_at', 'source_updated_at',
            'acquisition_date', 'acquisition_source', 'registration_date',
            'first_order_date', 'first_completed_trip', 'deleted',
            'deleted_at', 'deactivation_date', 'reactivation_date',
            'onboarding_stage', 'onboarding_status',
        ]
        for tc in target_cols:
            found = tc.lower() in [c.lower() for c in col_names]
            status = "EXISTS" if found else "NOT FOUND"
            print(f"  {tc:30s} -> {status}")

        # ═══════════════════════════════════════════════════════════════
        # FASE A.3 — Muestra real de 5 filas
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE A.3 — MUESTRA DE 5 FILAS COMPLETAS")
        print("=" * 80)

        sample = conn.execute(text(f"SELECT * FROM module_ct_cabinet_drivers LIMIT 5")).fetchall()
        for i, row in enumerate(sample):
            print(f"\n--- Row {i+1} ---")
            for j, val in enumerate(row):
                if j < len(col_names):
                    print(f"  {col_names[j]:30s} = {repr(val)}")

        # ═══════════════════════════════════════════════════════════════
        # FASE A.4 — Null rates for all columns
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE A.4 — NULL RATE POR COLUMNA")
        print("=" * 80)

        for c in col_names:
            try:
                null_count = conn.execute(text(
                    f"SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE {c} IS NULL"
                )).scalar()
                null_pct = round(100 * null_count / total, 2) if total > 0 else 0
                # Also check for empty strings if text/varchar
                if null_pct < 100:
                    try:
                        empty_count = conn.execute(text(
                            f"SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE {c} = ''"
                        )).scalar()
                        empty_pct = round(100 * empty_count / total, 2)
                        print(f"  {c:35s} NULL={null_pct:.1f}% EMPTY={empty_pct:.1f}%")
                    except Exception:
                        print(f"  {c:35s} NULL={null_pct:.1f}%")
                else:
                    print(f"  {c:35s} NULL={null_pct:.1f}%  <-- COMPLETAMENTE NULO")
            except Exception as e:
                print(f"  {c:35s} ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE A.5 — Valores distintos por columna clave
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE A.5 — VALORES DISTINTOS POR COLUMNA CLAVE")
        print("=" * 80)

        key_cols_to_check = ['origen', 'origin', 'status', 'segment', 'stage',
                             'conexion', 'source', 'park_name', 'park_id',
                             'driver_status', 'onboarding_stage', 'onboarding_status']

        for kc in key_cols_to_check:
            if kc in col_names:
                try:
                    rows = conn.execute(text(
                        f"SELECT {kc}, COUNT(*) as cnt FROM module_ct_cabinet_drivers "
                        f"GROUP BY {kc} ORDER BY cnt DESC LIMIT 30"
                    )).fetchall()
                    print(f"\n  {kc}:")
                    for r in rows:
                        val = r[0] if r[0] is not None else 'NULL'
                        print(f"    {str(val)[:50]:50s} = {r[1]}")
                except Exception as e:
                    print(f"  {kc}: ERROR {e}")

        # ═══════════════════════════════════════════════════════════════
        # If lead_created_at exists, do detailed profiling
        # ═══════════════════════════════════════════════════════════════
        if 'lead_created_at' in col_names:
            run_lead_created_at_profiling(conn, total, col_names)
        else:
            print("\n" + "=" * 80)
            print("lead_created_at NO EXISTE en module_ct_cabinet_drivers")
            print("=" * 80)
            # Check ALL schemas for this column
            all_tables_with_lead = conn.execute(text("""
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE column_name ILIKE '%lead_created%'
                   OR column_name ILIKE '%lead_creation%'
                   OR column_name ILIKE '%acquisition_date%'
                   OR column_name ILIKE '%first_trip_at%'
                   OR column_name ILIKE '%first_5_trip%'
                   OR column_name ILIKE '%registration_date%'
                ORDER BY table_schema, table_name
            """)).fetchall()
            print(f"\nColumnas similares en TODA la DB:")
            if all_tables_with_lead:
                for r in all_tables_with_lead:
                    print(f"  {r[0]}.{r[1]}.{r[2]} ({r[3]})")
            else:
                print("  NINGUNA encontrada en toda la base de datos.")

        # ═══════════════════════════════════════════════════════════════
        # FASE B — PROFILING DE CAMPOS TEMPORALES
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE B — PROFILING DE CAMPOS TEMPORALES")
        print("=" * 80)

        timestamp_cols = ['hire_date', 'created_at', 'updated_at', 'last_active_date',
                          'lead_created_at', 'first_trip_at', 'first_5_trip_at',
                          'fire_date', 'deleted_at', 'deactivation_date',
                          'source_created_at', 'source_updated_at',
                          'first_order_date', 'registration_date']

        timestamp_found = [c for c in timestamp_cols if c in col_names]
        print(f"\nTimestamps encontrados: {timestamp_found}")

        for tc in timestamp_found:
            print(f"\n--- {tc} ---")
            try:
                # null rate
                null_count = conn.execute(text(
                    f"SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE {tc} IS NULL OR {tc}::text = ''"
                )).scalar()
                null_pct = round(100 * null_count / total, 2) if total > 0 else 0
                print(f"  Null/Empty rate: {null_pct}% ({null_count}/{total})")

                # min/max (try date cast)
                try:
                    r = conn.execute(text(
                        f"SELECT MIN({tc}::timestamp), MAX({tc}::timestamp) FROM module_ct_cabinet_drivers WHERE {tc} IS NOT NULL AND {tc}::text != ''"
                    )).first()
                    print(f"  Min: {r[0]}, Max: {r[1]}")
                except Exception:
                    try:
                        r = conn.execute(text(
                            f"SELECT MIN({tc}::date), MAX({tc}::date) FROM module_ct_cabinet_drivers WHERE {tc} IS NOT NULL AND {tc}::text != ''"
                        )).first()
                        print(f"  Min (date): {r[0]}, Max (date): {r[1]}")
                    except Exception as e2:
                        print(f"  Cannot cast to date: {e2}")

                # future timestamps
                try:
                    future = conn.execute(text(
                        f"SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE {tc}::timestamp > CURRENT_TIMESTAMP"
                    )).scalar()
                    print(f"  Future timestamps: {future}")
                except Exception:
                    pass

                # year distribution (for date types)
                try:
                    rows = conn.execute(text(f"""
                        SELECT EXTRACT(YEAR FROM {tc}::date)::int as yr,
                               COUNT(*) as cnt
                        FROM module_ct_cabinet_drivers
                        WHERE {tc} IS NOT NULL AND {tc}::text != ''
                        GROUP BY yr ORDER BY yr
                    """)).fetchall()
                    if rows:
                        print(f"  Distribution by year:")
                        for r in rows:
                            print(f"    {r[0]}: {r[1]} drivers")
                except Exception:
                    pass

            except Exception as e:
                print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE C — CONSISTENCIA TEMPORAL
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE C — CONSISTENCIA TEMPORAL")
        print("=" * 80)

        # C.1 hire_date vs created_at
        if 'hire_date' in col_names and 'created_at' in col_names:
            print("\nC.1 hire_date vs created_at:")
            try:
                r = conn.execute(text("""
                    SELECT
                        COUNT(*) as total_with_both,
                        COUNT(*) FILTER (WHERE hire_date::date <= created_at::date) as correct,
                        COUNT(*) FILTER (WHERE hire_date::date > created_at::date) as inverted,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE hire_date::date > created_at::date) / NULLIF(COUNT(*), 0), 2) as pct_inverted
                    FROM module_ct_cabinet_drivers
                    WHERE hire_date IS NOT NULL AND hire_date::text != ''
                      AND created_at IS NOT NULL
                """)).first()
                print(f"  Both non-null: {r[0]}")
                print(f"  Correct (hire <= created): {r[1]}")
                print(f"  Inverted (hire > created): {r[2]} ({r[3]}%)")
            except Exception as e:
                print(f"  ERROR: {e}")

        # C.2 hire_date vs last_active_date
        if 'hire_date' in col_names and 'last_active_date' in col_names:
            print("\nC.2 hire_date vs last_active_date:")
            try:
                r = conn.execute(text("""
                    SELECT
                        COUNT(*) as total_with_both,
                        COUNT(*) FILTER (WHERE hire_date::date <= last_active_date::date) as correct,
                        COUNT(*) FILTER (WHERE hire_date::date > last_active_date::date) as inverted,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE hire_date::date > last_active_date::date) / NULLIF(COUNT(*), 0), 2) as pct_inverted
                    FROM module_ct_cabinet_drivers
                    WHERE hire_date IS NOT NULL AND hire_date::text != ''
                      AND last_active_date IS NOT NULL AND last_active_date::text != ''
                """)).first()
                print(f"  Both non-null: {r[0]}")
                print(f"  Correct (hire <= last_active): {r[1]}")
                print(f"  Inverted (hire > last_active): {r[2]} ({r[3]}%)")
            except Exception as e:
                print(f"  ERROR: {e}")

        # C.3 hire_date vs updated_at
        if 'hire_date' in col_names and 'updated_at' in col_names:
            print("\nC.3 hire_date vs updated_at:")
            try:
                r = conn.execute(text("""
                    SELECT
                        COUNT(*) as total_with_both,
                        COUNT(*) FILTER (WHERE hire_date::date <= updated_at::date) as correct,
                        COUNT(*) FILTER (WHERE hire_date::date > updated_at::date) as inverted,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE hire_date::date > updated_at::date) / NULLIF(COUNT(*), 0), 2) as pct_inverted
                    FROM module_ct_cabinet_drivers
                    WHERE hire_date IS NOT NULL AND hire_date::text != ''
                      AND updated_at IS NOT NULL
                """)).first()
                print(f"  Both non-null: {r[0]}")
                print(f"  Correct (hire <= updated): {r[1]}")
                print(f"  Inverted (hire > updated): {r[2]} ({r[3]}%)")
            except Exception as e:
                print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE D — DETECCIÓN DE REACTIVACIONES / RECICLADOS
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE D — DETECCIÓN DE REACTIVACIONES / RECICLADOS")
        print("=" * 80)

        # D.1 Duplicates by driver_id
        print("\nD.1 Duplicados por driver_id:")
        try:
            dups = conn.execute(text("""
                SELECT driver_id, COUNT(*) as cnt
                FROM module_ct_cabinet_drivers
                WHERE driver_id IS NOT NULL
                GROUP BY driver_id
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
                LIMIT 20
            """)).fetchall()
            if dups:
                print(f"  Found {len(dups)}+ drivers with duplicates:")
                for r in dups:
                    print(f"    {r[0][:30]} = {r[1]} occurrences")
            else:
                print("  No duplicates found.")
        except Exception as e:
            print(f"  ERROR: {e}")

        # D.2 Possible duplicates by license
        if 'license' in col_names:
            print("\nD.2 Posibles duplicados por license:")
            try:
                dups = conn.execute(text("""
                    SELECT license, COUNT(*) as cnt, ARRAY_AGG(driver_id) as driver_ids
                    FROM module_ct_cabinet_drivers
                    WHERE license IS NOT NULL AND license != ''
                    GROUP BY license
                    HAVING COUNT(*) > 1
                    ORDER BY cnt DESC
                    LIMIT 15
                """)).fetchall()
                if dups:
                    print(f"  Found {len(dups)}+ licenses with multiple drivers:")
                    for r in dups:
                        print(f"    license={r[0][:20]}: {r[1]} drivers")
                else:
                    print("  No duplicate licenses found.")
            except Exception as e:
                print(f"  ERROR (may not support ARRAY_AGG): {e}")

        # D.3 Possible duplicates by phone
        if 'driver_phone' in col_names:
            print("\nD.3 Posibles duplicados por driver_phone:")
            try:
                dups = conn.execute(text("""
                    SELECT driver_phone, COUNT(*) as cnt
                    FROM module_ct_cabinet_drivers
                    WHERE driver_phone IS NOT NULL AND driver_phone != ''
                    GROUP BY driver_phone
                    HAVING COUNT(*) > 1
                    ORDER BY cnt DESC
                    LIMIT 15
                """)).fetchall()
                if dups:
                    print(f"  Found {len(dups)}+ phones with multiple drivers:")
                    for r in dups:
                        print(f"    phone={r[0][:20]}: {r[1]} drivers")
                else:
                    print("  No duplicate phones found.")
            except Exception as e:
                print(f"  ERROR: {e}")

        # D.4 Drivers with old hire_date but recent activity (reactivation candidates)
        if 'hire_date' in col_names:
            print("\nD.4 Drivers with old hire_date + May 2026 trips (reactivation candidates):")
            try:
                r = conn.execute(text("""
                    SELECT
                        COUNT(DISTINCT src.driver_id) as total,
                        COUNT(DISTINCT src.driver_id) FILTER (WHERE src.hire_date::date < '2026-01-01') as pre_2026_hire,
                        COUNT(DISTINCT src.driver_id) FILTER (WHERE src.hire_date::date < '2025-01-01') as pre_2025_hire
                    FROM module_ct_cabinet_drivers src
                    WHERE EXISTS (
                        SELECT 1 FROM trips_2026 t
                        WHERE t.conductor_id = src.driver_id
                          AND t.fecha_inicio_viaje > '2026-05-01'
                          AND t.condicion = 'Completado'
                    )
                      AND src.hire_date IS NOT NULL AND src.hire_date::text != ''
                """)).first()
                print(f"  Total drivers with May 2026 trips: {r[0]}")
                print(f"  Pre-2026 hire (reactivation?): {r[1]}")
                print(f"  Pre-2025 hire (deep reactivation?): {r[2]}")
            except Exception as e:
                print(f"  ERROR: {e}")

        # D.5 Fleet vs Cabinet distribution
        if 'origen' in col_names:
            print("\nD.5 Fleet vs Cabinet distribution:")
            try:
                rows = conn.execute(text("""
                    SELECT origen,
                           COUNT(*) as total,
                           COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date::text = '') as null_hire,
                           MIN(hire_date::date) as min_hd,
                           MAX(hire_date::date) as max_hd,
                           COUNT(*) FILTER (WHERE last_active_date IS NOT NULL AND last_active_date::text != '') as with_last_active
                    FROM module_ct_cabinet_drivers
                    GROUP BY origen
                    ORDER BY total DESC
                """)).fetchall()
                for r in rows:
                    print(f"  origen={r[0]}: total={r[1]}, null_hire={r[2]}, hd_range=[{r[3]}, {r[4]}], with_last_active={r[5]}")
            except Exception as e:
                print(f"  ERROR: {e}")

        # D.6 Drivers without hire_date but with trips
        print("\nD.6 Drivers WITHOUT hire_date but WITH trips:")
        try:
            r = conn.execute(text("""
                SELECT COUNT(DISTINCT src.driver_id)
                FROM module_ct_cabinet_drivers src
                WHERE (src.hire_date IS NULL OR src.hire_date::text = '')
                  AND EXISTS (
                      SELECT 1 FROM trips_2026 t
                      WHERE t.conductor_id = src.driver_id
                        AND t.condicion = 'Completado'
                  )
            """)).scalar()
            print(f"  Drivers with trips but no hire_date: {r}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE E — CHECK DRIVERS TABLE FOR lead_created_at and fire_date
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE E — EXPLORACIÓN DE TABLAS RELACIONADAS")
        print("=" * 80)

        # Check drivers table
        try:
            driver_cols = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'drivers'
                ORDER BY ordinal_position
            """)).fetchall()
            print("\nE.1 Columnas de la tabla 'drivers':")
            for r in driver_cols:
                print(f"  {r[0]:35s} {r[1]:20s} nullable={r[2]}")

            # Count
            drv_count = conn.execute(text("SELECT COUNT(*) FROM drivers")).scalar()
            print(f"\n  Total drivers rows: {drv_count}")

            # Check for lead_created_at, fire_date, hire_date etc
            driver_col_names = [r[0] for r in driver_cols]
            for tc in ['lead_created_at', 'hire_date', 'fire_date', 'first_trip_at', 'active',
                        'created_at', 'updated_at', 'city', 'license']:
                status = "EXISTS" if tc in driver_col_names else "NOT FOUND"
                print(f"  {tc:25s} -> {status}")

            # If fire_date exists, check reactivation patterns
            if 'fire_date' in driver_col_names and 'hire_date' in driver_col_names:
                r = conn.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE fire_date IS NOT NULL) as fired,
                        COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND active = true) as active_but_fired,
                        COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND fire_date > hire_date) as fired_after_hire
                    FROM drivers
                """)).first()
                print(f"\n  Firing stats: total={r[0]}, fired={r[1]}, active+but+fired={r[2]}, fired_after_hire={r[3]}")

        except Exception as e:
            print(f"  ERROR accessing drivers table: {e}")

        # Check all tables for lead_created_at
        print("\nE.2 Búsqueda de lead_created_at en TODAS las tablas:")
        all_lead = conn.execute(text("""
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE column_name ILIKE '%lead_creator%'
               OR column_name ILIKE '%lead_created%'
               OR column_name ILIKE '%lead_date%'
               OR column_name ILIKE '%acquisition%'
               OR column_name ILIKE '%first_trip%'
               OR column_name ILIKE '%first_5_trip%'
               OR column_name ILIKE '%first_completed%'
               OR column_name ILIKE '%first_order%'
            ORDER BY table_schema, table_name, column_name
        """)).fetchall()
        if all_lead:
            for r in all_lead:
                print(f"  {r[0]}.{r[1]}.{r[2]} ({r[3]})")
        else:
            print("  NO se encontró lead_created_at ni campos relacionados en ninguna tabla.")

        # Check scout_liq_driver_assignments for any stored timestamps
        print("\nE.3 Columnas de scout_liq_driver_assignments:")
        try:
            rows = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'scout_liq_driver_assignments'
                ORDER BY ordinal_position
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]:35s} {r[1]:20s} nullable={r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE F — DISTRIBUCIÓN hire_date POR BUCKETS
        # ═══════════════════════════════════════════════════════════════
        if 'hire_date' in col_names:
            print("\n" + "=" * 80)
            print("FASE F — DISTRIBUCIÓN hire_date POR MESES")
            print("=" * 80)
            try:
                rows = conn.execute(text("""
                    SELECT EXTRACT(YEAR FROM hire_date::date)::int as yr,
                           EXTRACT(MONTH FROM hire_date::date)::int as mon,
                           origen,
                           COUNT(*) as cnt
                    FROM module_ct_cabinet_drivers
                    WHERE hire_date IS NOT NULL AND hire_date::text != ''
                    GROUP BY yr, mon, origen
                    ORDER BY yr DESC, mon DESC
                    LIMIT 40
                """)).fetchall()
                for r in rows:
                    print(f"  {r[0]}-{r[1]:02d} origen={r[2] or 'NULL':10s} = {r[3]} drivers")
            except Exception as e:
                print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════
        # FASE G — ESTADO REAL DEL SISTEMA (resumen para anchor date)
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("FASE G — RESUMEN DE HALLAZGOS PARA ANCHOR DATE")
        print("=" * 80)

        has_lead = 'lead_created_at' in col_names
        has_hire = 'hire_date' in col_names
        hire_null_rate = 0

        if has_hire:
            hire_null = conn.execute(text(
                "SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE hire_date IS NULL OR hire_date::text = ''"
            )).scalar()
            hire_null_rate = round(100 * hire_null / total, 2) if total > 0 else 0

        has_created_at = 'created_at' in col_names
        has_updated_at = 'updated_at' in col_names
        has_last_active = 'last_active_date' in col_names
        has_origen = 'origen' in col_names

        print(f"\n  lead_created_at exists:     {has_lead}")
        print(f"  hire_date exists:           {has_hire} (null/empty: {hire_null_rate}%)")
        print(f"  created_at exists:          {has_created_at}")
        print(f"  updated_at exists:          {has_updated_at}")
        print(f"  last_active_date exists:    {has_last_active}")
        print(f"  origen exists:              {has_origen}")

        print(f"\n  Total rows in table:        {total}")
        print(f"  Total columns in table:     {len(columns)}")

        # ═══════════════════════════════════════════════════════════════
        # Final: Assessment
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 80)
        print("EVALUACIÓN ANCHOR DATE")
        print("=" * 80)

        if has_lead:
            print("\n  lead_created_at: GO (existe, requiere profiling detallado)")
        elif has_hire:
            print(f"\n  lead_created_at: NO GO (no existe)")
            print(f"  hire_date: GO WITH WARNINGS (existe con {hire_null_rate}% null/empty)")
            print(f"\n  RECOMENDACIÓN PRELIMINAR:")
            print(f"    Usar hire_date como anchor date actual.")
            print(f"    lead_created_at NO existe en esta tabla.")
            print(f"    Si la tabla fue enriquecida, verificar si los datos")
            print(f"    se encuentran en otra tabla o si aún no han sido cargados.")
        else:
            print("\n  NO GO: ni lead_created_at ni hire_date están disponibles.")

    print("\n" + "=" * 80)
    print("AUDITORÍA COMPLETADA.")
    print("=" * 80)


def run_lead_created_at_profiling(conn, total, col_names):
    """Detailed profiling if lead_created_at exists."""
    print("\n" + "=" * 80)
    print("PROFILING DETALLADO: lead_created_at")
    print("=" * 80)

    # null rate
    null_count = conn.execute(text(
        "SELECT COUNT(*) FROM module_ct_cabinet_drivers WHERE lead_created_at IS NULL"
    )).scalar()
    null_pct = round(100 * null_count / total, 2) if total > 0 else 0
    print(f"  Null rate: {null_pct}% ({null_count}/{total})")

    # min/max
    try:
        r = conn.execute(text("""
            SELECT MIN(lead_created_at::timestamp), MAX(lead_created_at::timestamp)
            FROM module_ct_cabinet_drivers
            WHERE lead_created_at IS NOT NULL
        """)).first()
        print(f"  Min: {r[0]}, Max: {r[1]}")
    except Exception as e:
        print(f"  Cannot get min/max: {e}")

    # Distribution by year
    try:
        rows = conn.execute(text("""
            SELECT EXTRACT(YEAR FROM lead_created_at::date)::int as yr,
                   COUNT(*) as cnt
            FROM module_ct_cabinet_drivers
            WHERE lead_created_at IS NOT NULL
            GROUP BY yr ORDER BY yr
        """)).fetchall()
        print(f"  Distribution by year:")
        for r in rows:
            print(f"    {r[0]}: {r[1]} drivers")
    except Exception as e:
        print(f"  Year distribution error: {e}")

    # lead_created_at vs hire_date
    if 'hire_date' in col_names:
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) as both_present,
                    COUNT(*) FILTER (WHERE lead_created_at::date <= hire_date::date) as correct,
                    COUNT(*) FILTER (WHERE lead_created_at::date > hire_date::date) as inverted,
                    ROUND(AVG(EXTRACT(DAY FROM hire_date::date - lead_created_at::date)), 1) as avg_days_gap
                FROM module_ct_cabinet_drivers
                WHERE lead_created_at IS NOT NULL
                  AND hire_date IS NOT NULL AND hire_date::text != ''
            """)).first()
            print(f"\n  lead_created_at vs hire_date:")
            print(f"    Both present: {r[0]}")
            print(f"    Correct (lead <= hire): {r[1]}")
            print(f"    Inverted (lead > hire): {r[2]}")
            print(f"    Avg days gap: {r[3]}")
        except Exception as e:
            print(f"  lead vs hire comparison error: {e}")


if __name__ == "__main__":
    run()
