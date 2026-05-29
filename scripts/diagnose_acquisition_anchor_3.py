"""
Diagnóstico de Acquisition Anchor — Fase 0B - Ronda 3
Queries que fallaron + queries adicionales críticas.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # N7b: Fleet drivers hire_date (fixed)
        print("=== N7b) FLEET DRIVERS: hire_date y last_active ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '') as with_hd,
                    COUNT(*) FILTER (WHERE last_active_date IS NOT NULL AND last_active_date != '') as with_la
                FROM module_ct_cabinet_drivers
                WHERE origen = 'fleet'
            """)).first()
            print(f"  Total fleet: {r[0]}, with_hd: {r[1]}, with_last_active: {r[2]}")
            r2 = conn.execute(text("""
                SELECT MIN(hire_date::date) as min_hd, MAX(hire_date::date) as max_hd
                FROM module_ct_cabinet_drivers
                WHERE origen = 'fleet' AND hire_date IS NOT NULL AND hire_date != ''
            """)).first()
            print(f"  hire_date range: {r2[0]} to {r2[1]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N7c: Cabinet drivers hire_date
        print("\n=== N7c) CABINET DRIVERS: hire_date ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '') as with_hd,
                    COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') as null_hd
                FROM module_ct_cabinet_drivers
                WHERE origen = 'cabinet'
            """)).first()
            print(f"  Total cabinet: {r[0]}, with_hd: {r[1]}, null_hd: {r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N10b: drivers table stats (simplified)
        print("\n=== N10b) DRIVERS TABLE: fire_date y actividad ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE hire_date IS NOT NULL) as with_hd,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL) as with_fd,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND hire_date IS NOT NULL) as both,
                    COUNT(*) FILTER (WHERE active = true) as active_now
                FROM drivers
            """)).first()
            print(f"  Total: {r[0]}, with_hire_date: {r[1]}, with_fire_date: {r[2]}")
            print(f"  Both hire+fire: {r[3]}, active_now: {r[4]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N10c: drivers that might be reactivated (fire_date + hire_date)
        print("\n=== N10c) DRIVERS: possible reactivation patterns ===")
        try:
            rows = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND active = true) as active_but_fired,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND fire_date > hire_date) as fired_after_hired,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND fire_date < CURRENT_DATE - INTERVAL '30 days') as fired_30d_ago,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL AND fire_date < CURRENT_DATE - INTERVAL '90 days') as fired_90d_ago,
                    MIN(hire_date) as min_hd,
                    MAX(hire_date) as max_hd,
                    MIN(fire_date) as min_fd,
                    MAX(fire_date) as max_fd
                FROM drivers
            """)).first()
            print(f"  Total: {r[0]}, active_but_fired: {r[1]}")
            print(f"  Fired after hired: {r[2]}")
            print(f"  Fired >30d ago: {r[3]}, >90d ago: {r[4]}")
            print(f"  hire_date: {r[5]} to {r[6]}")
            print(f"  fire_date: {r[7]} to {r[8]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N14: Taxonomía estimada (new vs reactivated vs migrated vs unknown)
        print("\n=== N14) TAXONOMIA ESTIMADA ===")
        # cabinet drivers
        r = conn.execute(text("""
            SELECT
                COUNT(*) as total_cabinet,
                COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '' AND hire_date::date >= '2026-04-01') as likely_new_2026q2,
                COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '' AND hire_date::date < '2026-01-01') as likely_pre_2026,
                COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') as unknown_date
            FROM module_ct_cabinet_drivers
            WHERE origen = 'cabinet'
        """)).first()
        print(f"  CABINET: total={r[0]}, likely_new(Q2_2026)={r[1]}, likely_pre_2026={r[2]}, unknown={r[3]}")

        r = conn.execute(text("""
            SELECT
                COUNT(*) as total_fleet,
                COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '' AND hire_date::date >= '2026-04-01') as recent_hd,
                COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '' AND hire_date::date < '2026-01-01') as pre_2026,
                COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') as unknown
            FROM module_ct_cabinet_drivers
            WHERE origen = 'fleet'
        """)).first()
        print(f"  FLEET: total={r[0]}, recent_hd={r[1]}, pre_2026={r[2]}, unknown={r[3]}")

        # N15: Reactivation candidates: drivers with hire_date in 2025 but active in May 2026
        print("\n=== N15) REACTIVATION CANDIDATES: pre-2026 hire + May 2026 trips ===")
        try:
            r = conn.execute(text("""
                SELECT
                    src.origen,
                    COUNT(DISTINCT src.driver_id) as cnt,
                    AVG(EXTRACT(DAY FROM CURRENT_DATE - src.hire_date::date)) as avg_days_since_hire,
                    MIN(EXTRACT(DAY FROM CURRENT_DATE - src.hire_date::date)) as min_days,
                    MAX(EXTRACT(DAY FROM CURRENT_DATE - src.hire_date::date)) as max_days
                FROM module_ct_cabinet_drivers src
                WHERE src.hire_date IS NOT NULL
                  AND src.hire_date != ''
                  AND src.hire_date::date < '2026-01-01'
                  AND EXISTS (
                      SELECT 1 FROM trips_2026 t
                      WHERE t.conductor_id = src.driver_id
                        AND t.fecha_inicio_viaje > '2026-05-01'
                        AND t.condicion = 'Completado'
                  )
                GROUP BY src.origen
            """)).first()
            print(f"  origen={r[0]}: {r[1]} drivers, avg {r[2]:.0f} days since hire, range {r[3]:.0f}-{r[4]:.0f}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N16: Cohort displacement impact
        print("\n=== N16) COHORT DISPLACEMENT: pre-2026 hire in 2026 cohorts ===")
        try:
            r = conn.execute(text("""
                SELECT COUNT(DISTINCT driver_id) as drivers_in_wrong_cohort
                FROM module_ct_cabinet_drivers
                WHERE hire_date IS NOT NULL
                  AND hire_date != ''
                  AND hire_date::date < '2026-01-01'
                  AND driver_id IN (
                      SELECT DISTINCT a.driver_id
                      FROM scout_liq_driver_assignments a
                      WHERE a.status = 'active'
                  )
            """)).first()
            print(f"  Assigned drivers with pre-2026 hire_date: {r[0]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N16b: Which pre-2026 assigned drivers have the biggest gap
        print("\n=== N16b) WORST cohort displacement (pre-2026 hire + active assignment) ===")
        try:
            rows = conn.execute(text("""
                SELECT a.driver_id, src.hire_date, src.origen,
                       EXTRACT(DAY FROM CURRENT_DATE - src.hire_date::date)::int as days_since_hire,
                       EXTRACT(YEAR FROM src.hire_date::date)::int as hire_year,
                       EXTRACT(WEEK FROM src.hire_date::date)::int as hire_week
                FROM scout_liq_driver_assignments a
                JOIN module_ct_cabinet_drivers src ON a.driver_id = src.driver_id
                WHERE a.status = 'active'
                  AND src.hire_date IS NOT NULL
                  AND src.hire_date != ''
                  AND src.hire_date::date < '2026-01-01'
                ORDER BY src.hire_date::date ASC
            """)).fetchall()
            print(f"  Found {len(rows)} assigned drivers with pre-2026 hire:")
            for r in rows:
                print(f"    {r[0][:12]}... hd={r[1]}, origen={r[2]}, days_gap={r[3]}, cohort={r[4]}-W{r[5]:02d}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N17: summary_daily drivers vs cabinet drivers
        print("\n=== N17) summary_daily: driver coverage ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(DISTINCT driver_id) as unique_drivers,
                    MIN(date_file) as earliest,
                    MAX(date_file) as latest
                FROM summary_daily
            """)).first()
            print(f"  Unique drivers in summary_daily: {r[0]}, range: {r[1]} to {r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N18: Total distinct drivers in trips_2026
        print("\n=== N18) trips_2026: unique conductors ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(DISTINCT conductor_id) as unique_conductors,
                    MIN(fecha_inicio_viaje) as first_trip,
                    MAX(fecha_inicio_viaje) as last_trip
                FROM trips_2026
                WHERE condicion = 'Completado'
            """)).first()
            print(f"  Unique conductors in trips_2026: {r[0]}")
            print(f"  Range: {r[1]} to {r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N19: Drivers with no assignment but recent trips (operational gap)
        print("\n=== N19) OPERATIONAL GAP: drivers con viajes pero sin asignacion ===")
        try:
            r = conn.execute(text("""
                SELECT COUNT(DISTINCT src.driver_id) as unassigned_with_trips
                FROM module_ct_cabinet_drivers src
                WHERE src.driver_id NOT IN (
                    SELECT a.driver_id FROM scout_liq_driver_assignments a WHERE a.status = 'active'
                )
                AND EXISTS (
                    SELECT 1 FROM trips_2026 t
                    WHERE t.conductor_id = src.driver_id
                      AND t.fecha_inicio_viaje > '2026-05-01'
                      AND t.condicion = 'Completado'
                )
            """)).first()
            print(f"  Unassigned drivers with May 2026 trips: {r[0]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n=== DIAGNOSTICO RONDA 3 COMPLETADO ===")


if __name__ == "__main__":
    run()
