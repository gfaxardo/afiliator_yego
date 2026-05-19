"""
Audit script: verifica conteos reales de viajes para drivers especificos.
Solo SELECT. No modifica tablas.
"""

import os, sys, json, argparse
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env"))

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def audit_driver(conn, driver_id):
    cur = conn.cursor()
    result = {"driver_id": driver_id}

    # Source driver data
    cur.execute("""
        SELECT driver_id, hire_date, origen, viajes_0_7, viajes_8_14, orders
        FROM module_ct_cabinet_drivers WHERE driver_id = %s
    """, (driver_id,))
    s = cur.fetchone()
    if not s:
        result["error"] = "driver not found in source"
        return result

    result["hire_date_raw"] = s[1]
    result["hire_date_parsed"] = s[1]
    result["origin"] = s[2]
    result["legacy_viajes_0_7_flag"] = s[3]
    result["legacy_viajes_8_14_flag"] = s[4]
    result["total_orders"] = s[5]

    # Corrected trip counts
    cur.execute("""
        SELECT s.driver_id, s.hire_date,
            COALESCE(SUM(t.trips_0_7), 0)::int AS trips_0_7_count,
            COALESCE(SUM(t.trips_8_14), 0)::int AS trips_8_14_count
        FROM module_ct_cabinet_drivers s
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '8 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '15 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2026 WHERE conductor_id = s.driver_id
            UNION ALL
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
                      AND condicion = 'Completado'
                ) AS trips_0_7,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '8 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '15 days'
                      AND condicion = 'Completado'
                ) AS trips_8_14
            FROM trips_2025 WHERE conductor_id = s.driver_id
        ) t ON true
        WHERE s.driver_id = %s
          AND s.hire_date IS NOT NULL AND s.hire_date != ''
        GROUP BY s.driver_id, s.hire_date
    """, (driver_id,))
    r = cur.fetchone()
    if r:
        result["trips_0_7_count"] = r[2]
        result["trips_8_14_count"] = r[3]
        result["trips_0_14_count"] = r[2] + r[3]

    # Canceled count for comparison (audit only)
    cur.execute("""
        SELECT s.driver_id,
            COALESCE(SUM(t.trips_0_7_canceled), 0)::int AS canceled_0_7,
            COALESCE(SUM(t.trips_8_14_canceled), 0)::int AS canceled_8_14
        FROM module_ct_cabinet_drivers s
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
                      AND condicion = 'Cancelado'
                ) AS trips_0_7_canceled,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '8 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '15 days'
                      AND condicion = 'Cancelado'
                ) AS trips_8_14_canceled
            FROM trips_2026 WHERE conductor_id = s.driver_id
            UNION ALL
            SELECT
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
                      AND condicion = 'Cancelado'
                ) AS trips_0_7_canceled,
                COUNT(*) FILTER (
                    WHERE fecha_inicio_viaje >= s.hire_date::date + INTERVAL '8 days'
                      AND fecha_inicio_viaje < s.hire_date::date + INTERVAL '15 days'
                      AND condicion = 'Cancelado'
                ) AS trips_8_14_canceled
            FROM trips_2025 WHERE conductor_id = s.driver_id
        ) t ON true
        WHERE s.driver_id = %s
        GROUP BY s.driver_id
    """, (driver_id,))
    r2 = cur.fetchone()
    if r2:
        result["canceled_0_7"] = r2[1]
        result["canceled_8_14"] = r2[2]

    # Sample completed trips in 0-7 window
    cur.execute("""
        SELECT t.id, t.fecha_inicio_viaje, t.condicion
        FROM trips_2026 t
        JOIN module_ct_cabinet_drivers s ON t.conductor_id = s.driver_id AND s.driver_id = %s
        WHERE t.fecha_inicio_viaje >= s.hire_date::date
          AND t.fecha_inicio_viaje < s.hire_date::date + INTERVAL '8 days'
          AND t.condicion = 'Completado'
        ORDER BY t.fecha_inicio_viaje LIMIT 5
    """, (driver_id,))
    result["sample_completed_0_7"] = [
        {"id": r[0], "date": str(r[1]), "status": r[2]} for r in cur.fetchall()
    ]

    cur.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("driver_id", nargs="?", default=None)
    args = parser.parse_args()

    conn = get_conn()

    if args.driver_id:
        result = audit_driver(conn, args.driver_id)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        # Audit both predefined drivers
        drivers = [
            "b4d763d0c64c439aa578993029527dd9",  # Driver A
            "ca915d577b0242b2ab5570924aab3804",  # Driver B
        ]
        for did in drivers:
            r = audit_driver(conn, did)
            label = "Driver A" if did == drivers[0] else "Driver B"
            print(f"\n=== {label} ===")
            print(f"  driver_id:       {r['driver_id'][:16]}...")
            print(f"  hire_date:       {r['hire_date_raw']}")
            print(f"  origin:          {r['origin']}")
            print(f"  legacy 0-7 flag: {r['legacy_viajes_0_7_flag']}")
            print(f"  legacy 8-14 flg: {r['legacy_viajes_8_14_flag']}")
            print(f"  total_orders:    {r['total_orders']}")
            print(f"  trips_0_7_count: {r['trips_0_7_count']}")
            print(f"  trips_8_14_ct:   {r['trips_8_14_count']}")
            print(f"  trips_0_14_ct:   {r['trips_0_14_count']}")
            print(f"  canceled_0_7:    {r.get('canceled_0_7')} (excluidos)")
            print(f"  canceled_8_14:   {r.get('canceled_8_14')} (excluidos)")
            print(f"  sample_completed_0_7: {len(r.get('sample_completed_0_7',[]))} trips")

    conn.close()


if __name__ == "__main__":
    main()
