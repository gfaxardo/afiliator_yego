"""
Diagnóstico de Acquisition Anchor — Fase 0B - Ronda 2
Queries específicas para entender datos reales y gaps.
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # N1: Why are assignment hire_dates NULL?
        print("=== N1) ASIGNACIONES: valores reales de hire_date y source_hire_date_raw ===")
        rows = conn.execute(text("""
            SELECT a.driver_id, a.hire_date, a.source_hire_date_raw, a.source_origin,
                   a.assigned_at, a.created_at, a.status, a.origin,
                   src.hire_date as source_hd, src.origen
            FROM scout_liq_driver_assignments a
            JOIN module_ct_cabinet_drivers src ON a.driver_id = src.driver_id
            WHERE a.status = 'active'
            LIMIT 10
        """)).fetchall()
        for r in rows:
            print(f"  driver={r[0][:12]}... a.hire={r[1]}, a.raw={r[2]}, a.origin={r[4] or r[7]}, src.hd={r[8]}, src.origen={r[9]}, assigned={r[3]}")

        # N2: summary_daily columns
        print("\n=== N2) COLUMNAS summary_daily ===")
        try:
            rows = conn.execute(text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'summary_daily' ORDER BY ordinal_position"
            )).fetchall()
            for r in rows:
                print(f"  {r[0]:30s} {r[1]:15s}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N3: summary_daily sample
        print("\n=== N3) summary_daily SAMPLE ===")
        try:
            rows = conn.execute(text(
                "SELECT * FROM summary_daily LIMIT 3"
            )).fetchall()
            keys = rows[0]._fields if rows and hasattr(rows[0], '_fields') else []
            for r in rows:
                print(f"  {dict(r._mapping) if hasattr(r, '_mapping') else r}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N4: Drivers with hire_date from source who are assigned
        print("\n=== N4) DRIVERS ASIGNADOS: source hire_date vs assignment ===")
        r = conn.execute(text("""
            SELECT
                COUNT(*) as total_assigned,
                COUNT(*) FILTER (WHERE src.hire_date IS NOT NULL AND src.hire_date != '') as src_has_hd,
                COUNT(*) FILTER (WHERE a.hire_date IS NOT NULL) as a_has_hd,
                COUNT(*) FILTER (WHERE a.source_hire_date_raw IS NOT NULL) as a_has_raw,
                MIN(src.hire_date::date) as min_src_hd,
                MAX(src.hire_date::date) as max_src_hd
            FROM scout_liq_driver_assignments a
            JOIN module_ct_cabinet_drivers src ON a.driver_id = src.driver_id
            WHERE a.status = 'active'
        """)).first()
        print(f"  Total assigned: {r[0]}")
        print(f"  Source has hire_date: {r[1]}")
        print(f"  Assignment has hire_date: {r[2]}")
        print(f"  Assignment has source_raw: {r[3]}")
        print(f"  Source hire_date range: {r[4]} to {r[5]}")

        # N5: Pre-2026 drivers with recent trips - DETAIL
        print("\n=== N5) PRE-2026 DRIVERS CON VIAJES RECIENTES (muestra) ===")
        try:
            rows = conn.execute(text("""
                SELECT src.driver_id, src.hire_date, src.origen,
                       MIN(t.fecha_inicio_viaje) as first_trip_2026,
                       MAX(t.fecha_inicio_viaje) as last_trip_2026,
                       COUNT(*) as trip_count,
                       CASE WHEN a.driver_id IS NOT NULL THEN 'assigned' ELSE 'unassigned' END as status
                FROM module_ct_cabinet_drivers src
                JOIN trips_2026 t ON src.driver_id = t.conductor_id
                LEFT JOIN scout_liq_driver_assignments a
                    ON src.driver_id = a.driver_id AND a.status = 'active'
                WHERE src.hire_date IS NOT NULL
                  AND src.hire_date != ''
                  AND src.hire_date::date < '2026-01-01'
                  AND t.condicion = 'Completado'
                  AND t.fecha_inicio_viaje > '2026-05-01'
                GROUP BY src.driver_id, src.hire_date, src.origen, a.driver_id
                ORDER BY src.hire_date::date ASC
                LIMIT 15
            """)).fetchall()
            for r in rows:
                print(f"  {r[0][:12]}... hd={r[1]}, origen={r[2]}, first_trip={r[3]}, last={r[4]}, trips={r[5]}, {r[6]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N6: All distinct assignment statuses and origins
        print("\n=== N6) ASIGNACIONES: todos los estados y origenes ===")
        rows = conn.execute(text("""
            SELECT a.status, a.source_origin, a.origin, COUNT(*) as cnt
            FROM scout_liq_driver_assignments a
            GROUP BY a.status, a.source_origin, a.origin
            ORDER BY cnt DESC
        """)).fetchall()
        for r in rows:
            print(f"  status={r[0]}, src_origin={r[1]}, origin={r[2]}: {r[3]}")

        # N7: Fleet drivers: hire_date range and last_active
        print("\n=== N7) FLEET DRIVERS: hire_date y last_active ===")
        rows = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date != '') as with_hd,
                COUNT(*) FILTER (WHERE last_active_date IS NOT NULL AND last_active_date != '') as with_last_active,
                MIN(hire_date::date) as min_hd,
                MAX(hire_date::date) as max_hd,
                MIN(last_active_date) as min_last,
                MAX(last_active_date) as max_last
            FROM module_ct_cabinet_drivers
            WHERE origen = 'fleet'
        """)).first()
        print(f"  Total fleet: {r[0]}")
        print(f"  With hire_date: {r[1]}")
        print(f"  With last_active_date: {r[2]}")
        print(f"  hire_date range: {r[3]} to {r[4]}")
        print(f"  last_active range: {r[5]} to {r[6]}")

        # N8: Distribution of hire_date by year/month
        print("\n=== N8) hire_date POR MES (cabinet vs fleet) ===")
        rows = conn.execute(text("""
            SELECT
                origen,
                EXTRACT(YEAR FROM hire_date::date)::int as yr,
                EXTRACT(MONTH FROM hire_date::date)::int as mon,
                COUNT(*) as cnt
            FROM module_ct_cabinet_drivers
            WHERE hire_date IS NOT NULL AND hire_date != ''
            GROUP BY origen, yr, mon
            ORDER BY yr, mon, origen
        """)).fetchall()
        for r in rows:
            print(f"  {r[0]}: {r[1]}-{r[2]:02d} = {r[3]} drivers")

        # N9: Check if any driver has multiple active assignments
        print("\n=== N9) DRIVERS CON MULTIPLES ASIGNACIONES ACTIVAS ===")
        rows = conn.execute(text("""
            SELECT driver_id, COUNT(*) as assignment_count,
                   STRING_AGG(CAST(scout_id AS VARCHAR), ', ') as scout_ids,
                   STRING_AGG(source_origin, ', ') as origins
            FROM scout_liq_driver_assignments
            WHERE status = 'active'
            GROUP BY driver_id
            HAVING COUNT(*) > 1
        """)).fetchall()
        for r in rows:
            print(f"  driver={r[0]}: {r[1]} assignments, scouts={r[2]}, origins={r[3]}")
        if not rows:
            print("  (ninguno)")

        # N10: Drivers with fire_date in drivers table (potentially reactivated)
        print("\n=== N10) DRIVERS CON fire_date (posibles reactivados) ===")
        try:
            r = conn.execute(text("""
                SELECT
                    COUNT(*) as total_drivers,
                    COUNT(*) FILTER (WHERE fire_date IS NOT NULL) as with_fire_date,
                    COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND fire_date IS NOT NULL AND fire_date > hire_date) as fired_after_hired,
                    COUNT(*) FILTER (WHERE active = true) as currently_active,
                    COUNT(*) FILTER (WHERE active = true AND fire_date IS NOT NULL) as active_with_fire_date
                FROM drivers
            """)).first()
            print(f"  Total drivers: {r[0]}")
            print(f"  With fire_date: {r[1]}")
            print(f"  Fired after hired: {r[2]}")
            print(f"  Currently active: {r[3]}")
            print(f"  Active with fire_date: {r[4]} (anomaly?)")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N11: last_active_date sample from cabinet drivers
        print("\n=== N11) last_active_date VALORES (cabinet, muestra) ===")
        rows = conn.execute(text("""
            SELECT driver_id, hire_date, last_active_date, status, segment, stage, created_at
            FROM module_ct_cabinet_drivers
            WHERE origen = 'cabinet'
              AND hire_date IS NOT NULL AND hire_date != ''
              AND last_active_date IS NOT NULL AND last_active_date != ''
            LIMIT 10
        """)).fetchall()
        for r in rows:
            print(f"  {r[0][:12]}... hd={r[1]}, last_active={r[2]}, status={r[3]}, segment={r[4]}, stage={r[5]}, created={r[6]}")

        # N12: Total counts from drivers vs module_ct_cabinet_drivers overlap
        print("\n=== N12) OVERLAP: drivers vs module_ct_cabinet_drivers ===")
        try:
            r = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM drivers) as drivers_total,
                    (SELECT COUNT(*) FROM module_ct_cabinet_drivers) as cabinet_total,
                    (SELECT COUNT(DISTINCT d.driver_id) FROM drivers d
                     JOIN module_ct_cabinet_drivers c ON d.driver_id = c.driver_id) as overlap
            """)).first()
            print(f"  drivers table: {r[0]}")
            print(f"  module_ct_cabinet_drivers: {r[1]}")
            print(f"  Overlap (in both): {r[2]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # N13: Paid history details
        print("\n=== N13) PAID HISTORY: distribución por import_source ===")
        try:
            rows = conn.execute(text("""
                SELECT import_source, COUNT(*) as cnt,
                       SUM(amount_paid) as total_amount,
                       MIN(paid_at) as first_paid,
                       MAX(paid_at) as last_paid
                FROM scout_liq_paid_history
                WHERE blocks_future_payment = true
                GROUP BY import_source
                ORDER BY cnt DESC
            """)).fetchall()
            for r in rows:
                print(f"  source={r[0]}: cnt={r[1]}, total=S/{r[2]}, from={r[3]}, to={r[4]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n=== DIAGNOSTICO RONDA 2 COMPLETADO ===")

if __name__ == "__main__":
    run()
