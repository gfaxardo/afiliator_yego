"""
Diagnóstico de Acquisition Anchor — Fase 0B
Solo LECTURA. No modifica nada.
Ejecuta contra la DB real vía app.database.engine.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')

from app.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # A) Columnas module_ct_cabinet_drivers
        print("=== A) COLUMNAS module_ct_cabinet_drivers ===")
        rows = conn.execute(text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'module_ct_cabinet_drivers' ORDER BY ordinal_position"
        )).fetchall()
        for r in rows:
            print(f"  {r[0]:30s} {r[1]:15s} nullable={r[2]}")

        # A2) Columnas drivers
        print("\n=== A2) COLUMNAS drivers ===")
        try:
            rows = conn.execute(text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'drivers' ORDER BY ordinal_position"
            )).fetchall()
            for r in rows:
                print(f"  {r[0]:30s} {r[1]:15s} nullable={r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # B) Distribución por origen
        print("\n=== B) DISTRIBUCION POR ORIGEN ===")
        rows = conn.execute(text(
            "SELECT origen, COUNT(*) FROM module_ct_cabinet_drivers GROUP BY origen ORDER BY COUNT(*) DESC"
        )).fetchall()
        for r in rows:
            print(f"  origen={r[0] or 'NULL'}: {r[1]} drivers")

        # C) hire_date rango y nulos
        print("\n=== C) hire_date RANGO Y NULOS ===")
        r = conn.execute(text(
            "SELECT COUNT(*) as total, "
            "COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date = '') as nulls, "
            "MIN(hire_date) as min_hd, MAX(hire_date) as max_hd "
            "FROM module_ct_cabinet_drivers"
        )).first()
        print(f"  Total: {r[0]}, Nulos: {r[1]}, Min: {r[2]}, Max: {r[3]}")

        # Extra: distinct origen values including any 'flip'
        print("\n=== B2) VALORES DISTINTOS DE origen ===")
        rows = conn.execute(text(
            "SELECT DISTINCT origen FROM module_ct_cabinet_drivers ORDER BY origen"
        )).fetchall()
        for r in rows:
            print(f"  '{r[0]}'")

        # D) Reactivados: hire_date antiguo + asignación reciente
        print("\n=== D) REACTIVADOS: hire_date antiguo + asignacion reciente ===")
        rows = conn.execute(text("""
            SELECT src.origen,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE a.hire_date < CURRENT_DATE - INTERVAL '90 days') as old_hire,
                   COUNT(*) FILTER (WHERE a.hire_date IS NOT NULL AND a.assigned_at IS NOT NULL AND a.hire_date < a.assigned_at - INTERVAL '30 days') as hire_before_assign,
                   COUNT(*) FILTER (WHERE a.hire_date IS NOT NULL AND a.assigned_at IS NOT NULL AND a.hire_date > a.assigned_at) as hire_after_assign
            FROM scout_liq_driver_assignments a
            JOIN module_ct_cabinet_drivers src ON a.driver_id = src.driver_id
            WHERE a.status = 'active'
            GROUP BY src.origen
        """)).fetchall()
        for r in rows:
            print(f"  origen={r[0]}: total={r[1]}, old_hire={r[2]}, hire>30d_before_assign={r[3]}, hire_after_assign={r[4]}")

        # E) Actividad reciente vs hire_date antiguo
        print("\n=== E) ACTIVIDAD RECIENTE vs hire_date ANTIGUO ===")
        try:
            r = conn.execute(text("""
                SELECT COUNT(DISTINCT src.driver_id) as drivers_with_recent_trips,
                       COUNT(DISTINCT src.driver_id) FILTER (
                           WHERE src.hire_date IS NOT NULL AND src.hire_date != '' AND src.hire_date::date < '2026-01-01'
                       ) as old_hire_with_trips
                FROM module_ct_cabinet_drivers src
                WHERE EXISTS (
                    SELECT 1 FROM trips_2026 t
                    WHERE t.conductor_id = src.driver_id
                      AND t.fecha_inicio_viaje > '2026-05-01'
                      AND t.condicion = 'Completado'
                )
            """)).first()
            print(f"  Drivers con viajes en May 2026: {r[0]}")
            print(f"  ...con hire_date pre-2026: {r[1]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # F) Cohortes por hire_date
        print("\n=== F) COHORTES POR hire_date (ultimas 20) ===")
        try:
            rows = conn.execute(text("""
                SELECT EXTRACT(ISOYEAR FROM hire_date::date)::int as yr,
                       EXTRACT(WEEK FROM hire_date::date)::int as wk,
                       origen,
                       COUNT(*) as cnt
                FROM module_ct_cabinet_drivers
                WHERE hire_date IS NOT NULL AND hire_date != ''
                GROUP BY yr, wk, origen
                ORDER BY yr DESC, wk DESC
                LIMIT 20
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]}-W{r[1]:02d} origen={r[2]}: {r[3]} drivers")
        except Exception as e:
            print(f"  ERROR: {e}")

        # G) Asignaciones activas con estado de hire_date
        print("\n=== G) ASIGNACIONES ACTIVAS: hire_date status ===")
        rows = conn.execute(text("""
            SELECT src.origen,
                   COUNT(*) as total_assignments,
                   COUNT(*) FILTER (WHERE a.hire_date IS NOT NULL) as with_hire,
                   COUNT(*) FILTER (WHERE a.hire_date IS NULL) as without_hire,
                   COUNT(*) FILTER (WHERE a.source_hire_date_raw IS NOT NULL) as with_raw
            FROM scout_liq_driver_assignments a
            JOIN module_ct_cabinet_drivers src ON a.driver_id = src.driver_id
            WHERE a.status = 'active'
            GROUP BY src.origen
        """)).fetchall()
        for r in rows:
            print(f"  origen={r[0]}: total={r[1]}, with_hire={r[2]}, without_hire={r[3]}, with_raw={r[4]}")

        # H) Observed affiliations
        print("\n=== H) OBSERVED AFFILIATIONS ===")
        try:
            r = conn.execute(text("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE reported_affiliation_date IS NOT NULL) as with_date,
                       COUNT(*) FILTER (WHERE matched_driver_id IS NOT NULL) as matched,
                       COUNT(*) FILTER (WHERE review_status = 'observed_pending_review') as pending,
                       COUNT(*) FILTER (WHERE review_status = 'observed_validated') as validated,
                       COUNT(*) FILTER (WHERE review_status = 'observed_rejected') as rejected,
                       MIN(reported_affiliation_date) as min_date,
                       MAX(reported_affiliation_date) as max_date
                FROM scout_liq_observed_affiliations
            """)).first()
            print(f"  Total: {r[0]}, with_date: {r[1]}, matched: {r[2]}")
            print(f"  pending: {r[3]}, validated: {r[4]}, rejected: {r[5]}")
            print(f"  Date range: {r[6]} to {r[7]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # H2) Observed with different date vs assignment hire_date
        print("\n=== H2) OBSERVED date vs ASSIGNMENT hire_date (diff > 7d) ===")
        try:
            rows = conn.execute(text("""
                SELECT COUNT(*) as total_mismatch,
                       AVG((a.hire_date - oa.reported_affiliation_date)) as avg_diff_days,
                       MIN((a.hire_date - oa.reported_affiliation_date)) as min_diff,
                       MAX((a.hire_date - oa.reported_affiliation_date)) as max_diff
                FROM scout_liq_observed_affiliations oa
                JOIN scout_liq_driver_assignments a
                    ON oa.matched_driver_id = a.driver_id AND a.status = 'active'
                WHERE oa.matched_driver_id IS NOT NULL
                  AND oa.reported_affiliation_date IS NOT NULL
                  AND a.hire_date IS NOT NULL
                  AND ABS(a.hire_date - oa.reported_affiliation_date) > 7
            """)).first()
            print(f"  Mismatches (>7d diff): {r[0]}")
            print(f"  Avg diff days: {r[1]}, Min: {r[2]}, Max: {r[3]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # I) Tablas trips y summary_daily
        print("\n=== I) TABLAS trips Y summary_daily ===")
        for tbl in ['summary_daily', 'trips_2025', 'trips_2026']:
            try:
                r = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                print(f"  {tbl}: EXISTS ({r} rows)")
            except Exception as e:
                print(f"  {tbl}: NOT FOUND")

        # J) Gap hire_date vs assigned_at
        print("\n=== J) GAP hire_date vs assigned_at (dias) ===")
        try:
            rows = conn.execute(text("""
                SELECT
                    CASE
                        WHEN days_diff <= 0 THEN 'assigned_before_hire'
                        WHEN days_diff <= 7 THEN '0-7d'
                        WHEN days_diff <= 30 THEN '8-30d'
                        WHEN days_diff <= 90 THEN '31-90d'
                        ELSE '90d+'
                    END as gap_bucket,
                    src.origen,
                    COUNT(*) as cnt
                FROM (
                    SELECT a.driver_id, a.hire_date, a.assigned_at,
                           (a.assigned_at::date - a.hire_date) as days_diff
                    FROM scout_liq_driver_assignments a
                    WHERE a.status = 'active'
                      AND a.hire_date IS NOT NULL
                      AND a.assigned_at IS NOT NULL
                ) gaps
                JOIN module_ct_cabinet_drivers src ON gaps.driver_id = src.driver_id
                GROUP BY gap_bucket, src.origen
                ORDER BY gap_bucket, src.origen
            """)).fetchall()
            for r in rows:
                print(f"  gap={r[0]:25s} origen={r[1] or 'NULL'}: {r[2]} drivers")
        except Exception as e:
            print(f"  ERROR: {e}")

        # K) Cutoff runs
        print("\n=== K) CUTOFF RUNS ===")
        try:
            rows = conn.execute(text("""
                SELECT status, cutoff_mode, cohort_iso_week,
                       COUNT(*) as cnt,
                       MIN(hire_date_from) as min_from,
                       MAX(hire_date_to) as max_to
                FROM scout_liq_cutoff_runs
                GROUP BY status, cutoff_mode, cohort_iso_week
                ORDER BY status, cohort_iso_week
            """)).fetchall()
            for r in rows:
                print(f"  status={r[0]}, mode={r[1]}, cohort={r[2]}: cnt={r[3]}, from={r[4]}, to={r[5]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # L) Total unique drivers in assignments vs source
        print("\n=== L) COBERTURA: source vs assignments ===")
        try:
            r = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM module_ct_cabinet_drivers) as source_total,
                    (SELECT COUNT(DISTINCT driver_id) FROM scout_liq_driver_assignments WHERE status = 'active') as assigned_active,
                    (SELECT COUNT(DISTINCT driver_id) FROM scout_liq_cutoff_driver_lines) as in_cutoffs,
                    (SELECT COUNT(DISTINCT driver_id) FROM scout_liq_paid_history WHERE blocks_future_payment = true) as paid_blocking
            """)).first()
            print(f"  Source total: {r[0]}")
            print(f"  Assigned active: {r[1]}")
            print(f"  In cutoffs: {r[2]}")
            print(f"  Paid (blocking): {r[3]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # M) Most recent hire_dates per origen
        print("\n=== M) hire_date MAS RECIENTES POR ORIGEN ===")
        rows = conn.execute(text("""
            SELECT origen,
                   MAX(hire_date::date) as latest_hire,
                   COUNT(*) FILTER (WHERE hire_date::date >= '2026-05-01') as may_2026_count
            FROM module_ct_cabinet_drivers
            WHERE hire_date IS NOT NULL AND hire_date != ''
            GROUP BY origen
            ORDER BY latest_hire DESC
        """)).fetchall()
        for r in rows:
            print(f"  origen={r[0]}: latest={r[1]}, in_may_2026={r[2]}")

    print("\n=== DIAGNOSTICO COMPLETADO ===")


if __name__ == "__main__":
    run()
