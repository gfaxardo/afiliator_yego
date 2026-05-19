"""
Diagnóstico de tabla fuente: module_ct_cabinet_drivers
Fase 0 - Liquidador de Calidad Scouts Yego
Solo LECTURA. No modifica nada.

Uso:
    python scripts/diagnose_source.py
    python scripts/diagnose_source.py --url postgresql://user:pass@host:5432/db
"""

import os
import sys
import json
import argparse
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 no instalado. Ejecuta: pip install psycopg2-binary")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env"))
except ImportError:
    pass


def get_connection(url: str = None):
    if url:
        return psycopg2.connect(url)

    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "yego_integral")
    db_user = os.getenv("DB_USER", "")
    db_password = os.getenv("DB_PASSWORD", "")

    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        client_encoding="UTF8",
    )


def diagnose(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    results = {}
    timestamp = datetime.now().isoformat()

    results["timestamp"] = timestamp
    results["source_table"] = "module_ct_cabinet_drivers"

    try:
        cur.execute("""
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'module_ct_cabinet_drivers'
            ORDER BY ordinal_position
        """)
        results["columns"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        results["columns"] = {"error": str(e)}

    try:
        cur.execute("SELECT COUNT(*) AS total FROM module_ct_cabinet_drivers")
        results["total_rows"] = cur.fetchone()["total"]
    except Exception as e:
        results["total_rows"] = f"ERROR: {e}"

    try:
        cur.execute(
            "SELECT COUNT(*) AS nulls FROM module_ct_cabinet_drivers WHERE driver_id IS NULL"
        )
        results["null_driver_id"] = cur.fetchone()["nulls"]
    except Exception as e:
        results["null_driver_id"] = f"ERROR: {e}"

    try:
        cur.execute(
            "SELECT COUNT(*) AS nulls FROM module_ct_cabinet_drivers WHERE hire_date IS NULL"
        )
        results["null_hire_date"] = cur.fetchone()["nulls"]
    except Exception as e:
        results["null_hire_date"] = f"ERROR: {e}"

    try:
        cur.execute("""
            SELECT driver_id, COUNT(*) AS occurrences
            FROM module_ct_cabinet_drivers
            WHERE driver_id IS NOT NULL
            GROUP BY driver_id
            HAVING COUNT(*) > 1
            ORDER BY occurrences DESC
            LIMIT 20
        """)
        results["duplicates_top20"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        results["duplicates_top20"] = f"ERROR: {e}"

    try:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'module_ct_cabinet_drivers'
              AND (column_name ILIKE '%origin%'
                OR column_name ILIKE '%cabinet%'
                OR column_name ILIKE '%fleet%'
                OR column_name ILIKE '%partner%')
            ORDER BY ordinal_position
        """)
        results["columns_origin_fleet"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        results["columns_origin_fleet"] = f"ERROR: {e}"

    try:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'module_ct_cabinet_drivers'
              AND (column_name ILIKE '%trip%7%'
                OR column_name ILIKE '%7%trip%'
                OR column_name ILIKE '%7d%'
                OR column_name ILIKE '%7_d%'
                OR column_name ILIKE '%week%'
                OR column_name ILIKE '%semana%')
            ORDER BY ordinal_position
        """)
        results["columns_trips_7d"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        results["columns_trips_7d"] = f"ERROR: {e}"

    try:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'module_ct_cabinet_drivers'
              AND (column_name ILIKE '%trip%14%'
                OR column_name ILIKE '%14%trip%'
                OR column_name ILIKE '%14d%'
                OR column_name ILIKE '%14_d%'
                OR column_name ILIKE '%biweek%'
                OR column_name ILIKE '%quincena%')
            ORDER BY ordinal_position
        """)
        results["columns_trips_14d"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        results["columns_trips_14d"] = f"ERROR: {e}"

    try:
        cur.execute("""
            SELECT MIN(hire_date) AS min_hire, MAX(hire_date) AS max_hire
            FROM module_ct_cabinet_drivers
        """)
        r = cur.fetchone()
        results["hire_date_range"] = {
            "min": str(r["min_hire"]) if r["min_hire"] else None,
            "max": str(r["max_hire"]) if r["max_hire"] else None,
        }
    except Exception as e:
        results["hire_date_range"] = f"ERROR: {e}"

    try:
        cur.execute("SELECT * FROM module_ct_cabinet_drivers LIMIT 3")
        rows = cur.fetchall()
        results["sample_rows"] = [
            {k: str(v) if hasattr(v, "isoformat") else v for k, v in r.items()}
            for r in rows
        ]
    except Exception as e:
        results["sample_rows"] = f"ERROR: {e}"

    cur.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico module_ct_cabinet_drivers")
    parser.add_argument("--url", help="URL de conexión PostgreSQL", default=None)
    args = parser.parse_args()

    try:
        conn = get_connection(args.url)
    except Exception as e:
        print(f"ERROR: No se pudo conectar a la base de datos: {e}")
        print("Asegúrate de configurar .env o pasar --url")
        sys.exit(1)

    try:
        results = diagnose(conn)
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "diagnose_output.json",
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        print(f"\n[OK] Resultados guardados en: {output_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
