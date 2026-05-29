"""
Fase 0 — Impact Queries: Detailed temporal analysis for taxonomy and confidence matrix.
Only SELECT. No modifications.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text


def run():
    with engine.connect() as conn:
        # ═══════════════════════════════════════════════════════════════════
        # IQ-1: Cabinet con hire_date antiguo y presencia en cabinet reciente
        # (creados en fuente post-hire_date original)
        # ═══════════════════════════════════════════════════════════════════
        print("=== IQ-1: CABINET hire_date antiguo vs created_at reciente ===")
        try:
            rows = conn.execute(text("""
                SELECT
                    CASE
                        WHEN gap_days <= 0 THEN 'created_before_hire'
                        WHEN gap_days <= 30 THEN '1-30d'
                        WHEN gap_days <= 90 THEN '31-90d'
                        WHEN gap_days <= 180 THEN '91-180d'
                        ELSE '180d+'
                    END AS gap_bucket,
                    COUNT(*) AS cnt,
                    ROUND(AVG(gap_days)) AS avg_gap_days
                FROM (
                    SELECT driver_id,
                           hire_date::date AS hd,
                           created_at::date AS ca,
                           (created_at::date - hire_date::date) AS gap_days
                    FROM module_ct_cabinet_drivers
                    WHERE origen = 'cabinet'
                      AND hire_date IS NOT NULL AND hire_date != ''
                      AND created_at IS NOT NULL
                ) sub
                GROUP BY gap_bucket
                ORDER BY MIN(gap_days)
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]:25s} = {r[1]:5d} drivers, avg_gap={r[2]}d")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-2: Cabinet con hire_date antiguo Y actividad May 2026 (reactivated)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-2: CABINET reactivated (hd < 2026 + May 2026 trips) ===")
        try:
            rows = conn.execute(text("""
                WITH active_may AS (
                    SELECT conductor_id, COUNT(*) AS trip_cnt,
                           MIN(fecha_inicio_viaje) AS first_trip,
                           MAX(fecha_inicio_viaje) AS last_trip
                    FROM trips_2026
                    WHERE fecha_inicio_viaje >= '2026-05-01'
                      AND condicion = 'Completado'
                    GROUP BY conductor_id
                )
                SELECT src.origen,
                       COUNT(*) AS driver_count,
                       ROUND(AVG(trip_cnt)) AS avg_trips,
                       MIN(src.hire_date::date) AS earliest_hd,
                       MAX(src.hire_date::date) AS latest_hd,
                       ROUND(AVG(EXTRACT(DAY FROM am.first_trip - src.hire_date::date))) AS avg_days_hd_to_first_trip
                FROM module_ct_cabinet_drivers src
                JOIN active_may am ON src.driver_id = am.conductor_id
                WHERE src.hire_date IS NOT NULL AND src.hire_date != ''
                  AND src.hire_date::date < '2026-01-01'
                GROUP BY src.origen
            """)).fetchall()
            for r in rows:
                print(f"  origen={r[0]}: {r[1]} drivers, avg_trips={r[2]}, hd_range={r[3]} to {r[4]}, avg_hd_to_first={r[5]}d")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-3: Fleet/Flip — hire_date vs assigned_at vs trips
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-3: FLEET drivers — hire_date vs assignment gap ===")
        try:
            rows = conn.execute(text("""
                SELECT
                    a.driver_id,
                    src.hire_date,
                    src.created_at AS src_created,
                    a.assigned_at,
                    (a.assigned_at::date - src.hire_date::date) AS days_hd_to_assign,
                    src.status,
                    src.segment,
                    CASE WHEN a.driver_id IS NOT NULL THEN 'assigned' ELSE 'unassigned' END AS assign_status
                FROM module_ct_cabinet_drivers src
                LEFT JOIN scout_liq_driver_assignments a
                    ON src.driver_id = a.driver_id AND a.status = 'active'
                WHERE src.origen = 'fleet'
                  AND src.hire_date IS NOT NULL AND src.hire_date != ''
                ORDER BY src.hire_date::date ASC
                LIMIT 15
            """)).fetchall()
            for r in rows:
                print(f"  {r[0][:12]}... hd={r[1]}, src_created={r[2]}, assigned={r[3]}, gap={r[4]}d, status={r[5]}, segment={r[6]}, {r[7]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # Fleet aggregate
        print("\n  --- Fleet aggregate ---")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE a.driver_id IS NOT NULL) AS assigned,
                    AVG((a.assigned_at::date - src.hire_date::date)) AS avg_gap_assign_hd,
                    MIN((a.assigned_at::date - src.hire_date::date)) AS min_gap,
                    MAX((a.assigned_at::date - src.hire_date::date)) AS max_gap
                FROM module_ct_cabinet_drivers src
                LEFT JOIN scout_liq_driver_assignments a
                    ON src.driver_id = a.driver_id AND a.status = 'active'
                WHERE src.origen = 'fleet'
                  AND src.hire_date IS NOT NULL AND src.hire_date != ''
                  AND a.driver_id IS NOT NULL
            """)).first()
            print(f"    Fleet assigned: {r[0]}, avg_gap={r[2]}d, min={r[3]}d, max={r[4]}d")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-4: Drivers perdidos por cohortes (hire_date-based cohort exclusion)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-4: DRIVERS PERDIDOS por cohortes hire_date ===")
        try:
            # Drivers that would be excluded if we only consider hire_date >= 2026-W01
            r = conn.execute(text("""
                SELECT
                    'pre_2026_hire' AS category,
                    COUNT(*) AS cnt
                FROM module_ct_cabinet_drivers
                WHERE hire_date IS NOT NULL AND hire_date != ''
                  AND hire_date::date < '2026-01-01'
                UNION ALL
                SELECT
                    'null_hire_date' AS category,
                    COUNT(*) AS cnt
                FROM module_ct_cabinet_drivers
                WHERE hire_date IS NULL OR hire_date = ''
                UNION ALL
                SELECT
                    'valid_2026_hire' AS category,
                    COUNT(*) AS cnt
                FROM module_ct_cabinet_drivers
                WHERE hire_date IS NOT NULL AND hire_date != ''
                  AND hire_date::date >= '2026-01-01'
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]}: {r[1]} drivers")
        except Exception as e:
            print(f"  ERROR: {e}")

        # Drivers with trips in 2026 but hire_date pre-2026 (lost from 2026 cohorts)
        print("\n  --- With recent trips ---")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(DISTINCT src.driver_id) AS lost_active_drivers,
                    COUNT(DISTINCT src.driver_id) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM scout_liq_driver_assignments a
                            WHERE a.driver_id = src.driver_id AND a.status = 'active'
                        )
                    ) AS lost_and_assigned,
                    COUNT(DISTINCT src.driver_id) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM trips_2026 t
                            WHERE t.conductor_id = src.driver_id
                              AND t.fecha_inicio_viaje >= '2026-05-01'
                              AND t.condicion = 'Completado'
                        )
                    ) AS lost_and_active_trips
                FROM module_ct_cabinet_drivers src
                WHERE src.hire_date IS NOT NULL
                  AND src.hire_date != ''
                  AND src.hire_date::date < '2026-01-01'
            """)).first()
            print(f"    Lost active drivers (hd < 2026): {r[0]}")
            print(f"    ...and assigned: {r[1]}")
            print(f"    ...with May 2026 trips: {r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-5: Distribución de diferencias hire_date vs created_at (source)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-5: DISTRIBUCIÓN hire_date vs created_at gap ===")
        for origen_val in ['cabinet', 'fleet']:
            try:
                rows = conn.execute(text(f"""
                    SELECT
                        CASE
                            WHEN gap_days <= 0 THEN 'created_before_or_same'
                            WHEN gap_days <= 1 THEN '1d'
                            WHEN gap_days <= 3 THEN '2-3d'
                            WHEN gap_days <= 7 THEN '4-7d'
                            WHEN gap_days <= 30 THEN '8-30d'
                            WHEN gap_days <= 90 THEN '31-90d'
                            ELSE '90d+'
                        END AS gap_bucket,
                        COUNT(*) AS cnt
                    FROM (
                        SELECT (created_at::date - hire_date::date) AS gap_days
                        FROM module_ct_cabinet_drivers
                        WHERE origen = '{origen_val}'
                          AND hire_date IS NOT NULL AND hire_date != ''
                          AND created_at IS NOT NULL
                    ) sub
                    GROUP BY gap_bucket
                    ORDER BY MIN(gap_days)
                """)).fetchall()
                print(f"  --- {origen_val} ---")
                for r in rows:
                    print(f"    {r[0]:25s} = {r[1]:5d}")
            except Exception as e:
                print(f"  ERROR ({origen_val}): {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-6: Taxonomy counts
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-6: TAXONOMY COUNTS (candidate_new / reactivated / migrated / unknown) ===")
        try:
            rows = conn.execute(text("""
                SELECT
                    origen,
                    COUNT(*) AS total_drivers,
                    -- new: hire_date >= 2026-01-01
                    COUNT(*) FILTER (
                        WHERE hire_date IS NOT NULL AND hire_date != ''
                          AND hire_date::date >= '2026-01-01'
                    ) AS candidate_new,
                    -- reactivated: hire_date < 2026-01-01
                    COUNT(*) FILTER (
                        WHERE hire_date IS NOT NULL AND hire_date != ''
                          AND hire_date::date < '2026-01-01'
                    ) AS candidate_reactivated,
                    -- migrated: fleet drivers (regardless of hire_date)
                    -- (fleet is separate category)
                    COUNT(*) FILTER (
                        WHERE hire_date IS NOT NULL AND hire_date != ''
                    ) AS has_hire_date,
                    -- unknown: no hire_date
                    COUNT(*) FILTER (
                        WHERE hire_date IS NULL OR hire_date = ''
                    ) AS candidate_unknown,
                    -- with trips May 2026
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM trips_2026 t
                            WHERE t.conductor_id = driver_id
                              AND t.fecha_inicio_viaje >= '2026-05-01'
                              AND t.condicion = 'Completado'
                        )
                    ) AS active_may_2026,
                    -- assigned active
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM scout_liq_driver_assignments a
                            WHERE a.driver_id = driver_id AND a.status = 'active'
                        )
                    ) AS assigned_active
                FROM module_ct_cabinet_drivers
                GROUP BY origen
                ORDER BY origen
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]}:")
                print(f"    total={r[1]}, candidate_new={r[2]}, candidate_reactivated={r[3]}")
                print(f"    has_hire_date={r[4]}, candidate_unknown={r[5]}")
                print(f"    active_may2026={r[6]}, assigned_active={r[7]}")

            # Total taxonomy
            r2 = conn.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE hire_date IS NOT NULL AND hire_date != ''
                          AND hire_date::date >= '2026-01-01'
                    ) AS candidate_new,
                    COUNT(*) FILTER (
                        WHERE hire_date IS NOT NULL AND hire_date != ''
                          AND hire_date::date < '2026-01-01'
                    ) AS candidate_reactivated,
                    COUNT(*) FILTER (
                        WHERE hire_date IS NULL OR hire_date = ''
                    ) AS candidate_unknown
                FROM module_ct_cabinet_drivers
            """)).first()
            print(f"  TOTAL: total={r2[0]}, new={r2[1]}, reactivated={r2[2]}, unknown={r2[3]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-7: Drivers sin fecha fuente confiable (double-check)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-7: DRIVERS SIN FECHA FUENTE CONFIABLE (breakdown) ===")
        try:
            # Cabinet sin hire_date: ¿tienen created_at? ¿tienen actividad?
            r = conn.execute(text("""
                SELECT
                    COUNT(*) AS total_no_hd,
                    COUNT(*) FILTER (WHERE created_at IS NOT NULL) AS has_created_at,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM trips_2026 t
                            WHERE t.conductor_id = driver_id
                              AND t.fecha_inicio_viaje >= '2026-05-01'
                              AND t.condicion = 'Completado'
                        )
                    ) AS active_may,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM scout_liq_driver_assignments a
                            WHERE a.driver_id = driver_id AND a.status = 'active'
                        )
                    ) AS assigned,
                    MIN(created_at) AS earliest_created,
                    MAX(created_at) AS latest_created
                FROM module_ct_cabinet_drivers
                WHERE origen = 'cabinet'
                  AND (hire_date IS NULL OR hire_date = '')
            """)).first()
            print(f"  CABINET sin hire_date: {r[0]}")
            print(f"    has_created_at={r[1]}, active_may={r[2]}, assigned={r[3]}")
            print(f"    created_at range: {r[4]} to {r[5]}")

            r = conn.execute(text("""
                SELECT
                    COUNT(*) AS total_no_hd,
                    COUNT(*) FILTER (WHERE created_at IS NOT NULL) AS has_created_at,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM trips_2026 t
                            WHERE t.conductor_id = driver_id
                              AND t.fecha_inicio_viaje >= '2026-05-01'
                              AND t.condicion = 'Completado'
                        )
                    ) AS active_may,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM scout_liq_driver_assignments a
                            WHERE a.driver_id = driver_id AND a.status = 'active'
                        )
                    ) AS assigned,
                    MIN(created_at) AS earliest_created,
                    MAX(created_at) AS latest_created
                FROM module_ct_cabinet_drivers
                WHERE origen = 'fleet'
                  AND (hire_date IS NULL OR hire_date = '')
            """)).first()
            print(f"  FLEET sin hire_date: {r[0]}")
            print(f"    has_created_at={r[1]}, active_may={r[2]}, assigned={r[3]}")
            print(f"    created_at range: {r[4]} to {r[5]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-8: assigned_at timestamp analysis (batch detection)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-8: assigned_at BATCH ANALYSIS ===")
        try:
            rows = conn.execute(text("""
                SELECT assigned_at, COUNT(*) AS cnt
                FROM scout_liq_driver_assignments
                WHERE status = 'active'
                  AND assigned_at IS NOT NULL
                GROUP BY assigned_at
                ORDER BY cnt DESC
                LIMIT 10
            """)).fetchall()
            for r in rows:
                print(f"  assigned_at={r[0]}: {r[1]} drivers")
        except Exception as e:
            print(f"  ERROR: {e}")

        # assigned_at distribution
        print("\n  --- assigned_at vs created_at gap (assignments) ---")
        try:
            rows = conn.execute(text("""
                SELECT
                    CASE
                        WHEN gap_seconds <= 0 THEN 'same_or_negative'
                        WHEN gap_seconds <= 1 THEN '<=1s'
                        WHEN gap_seconds <= 60 THEN '2-60s'
                        WHEN gap_seconds <= 3600 THEN '1m-1h'
                        ELSE '1h+'
                    END AS gap,
                    COUNT(*) AS cnt
                FROM (
                    SELECT EXTRACT(EPOCH FROM (assigned_at - created_at)) AS gap_seconds
                    FROM scout_liq_driver_assignments
                    WHERE status = 'active'
                      AND assigned_at IS NOT NULL
                      AND created_at IS NOT NULL
                ) sub
                GROUP BY gap
                ORDER BY MIN(gap_seconds)
            """)).fetchall()
            for r in rows:
                print(f"    {r[0]:15s} = {r[1]} drivers")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-9: drivers.fire_date cross with module_ct
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-9: drivers.fire_date CROSS module_ct ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) AS total_fired,
                    COUNT(*) FILTER (WHERE EXISTS (
                        SELECT 1 FROM module_ct_cabinet_drivers c WHERE c.driver_id = d.driver_id
                    )) AS in_module_ct,
                    COUNT(*) FILTER (WHERE EXISTS (
                        SELECT 1 FROM trips_2026 t WHERE t.conductor_id = d.driver_id
                          AND t.fecha_inicio_viaje >= '2026-05-01' AND t.condicion = 'Completado'
                    )) AS active_may_2026,
                    COUNT(*) FILTER (WHERE EXISTS (
                        SELECT 1 FROM scout_liq_driver_assignments a WHERE a.driver_id = d.driver_id AND a.status = 'active'
                    )) AS assigned_active
                FROM drivers d
                WHERE d.fire_date IS NOT NULL
            """)).first()
            print(f"  Total fired drivers: {r[0]}")
            print(f"    In module_ct: {r[1]}")
            print(f"    Active May 2026: {r[2]}")
            print(f"    Assigned active: {r[3]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # IQ-10: summary_daily — min/max date per driver (first/last activity)
        # ═══════════════════════════════════════════════════════════════════
        print("\n=== IQ-10: summary_daily FIRST/LAST activity per driver ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(DISTINCT driver_id) AS unique_drivers,
                    MIN(first_date) AS earliest_first_activity,
                    MAX(last_date) AS latest_last_activity
                FROM (
                    SELECT driver_id,
                           MIN(date_file) AS first_date,
                           MAX(date_file) AS max_date,
                           MAX(date_file) AS last_date
                    FROM summary_daily
                    WHERE driver_id IS NOT NULL
                    GROUP BY driver_id
                ) sub
            """)).first()
            print(f"  Unique drivers with summary_daily: {r[0]}")
            print(f"  Activity range: {r[1]} to {r[2]}")

            # Overlap with module_ct
            r = conn.execute(text("""
                SELECT
                    COUNT(DISTINCT sd.driver_id) AS in_summary,
                    COUNT(DISTINCT sd.driver_id) FILTER (
                        WHERE EXISTS (SELECT 1 FROM module_ct_cabinet_drivers c WHERE c.driver_id = sd.driver_id)
                    ) AS in_both
                FROM summary_daily sd
                WHERE sd.driver_id IS NOT NULL
            """)).first()
            print(f"  Drivers in summary_daily: {r[0]}, overlap with module_ct: {r[1]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n=== IMPACT QUERIES COMPLETADO ===")


if __name__ == "__main__":
    run()
