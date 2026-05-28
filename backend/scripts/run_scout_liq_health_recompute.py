"""
Script seguro para cron/systemd: ejecuta recompute completo de health pipeline.

Uso:
    cd backend
    python scripts/run_scout_liq_health_recompute.py

Exit codes:
    0 = success o warning (ejecucion ok aunque salud no este OK)
    1 = failed (error durante ejecucion)

No imprime credenciales. Solo resumen operativo.
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.scout_liq_health_pipeline import recompute_derived


def main() -> int:
    db = SessionLocal()
    try:
        t0 = time.perf_counter()
        started = datetime.utcnow().isoformat()
        result = recompute_derived(db, triggered_by="system")

        status = result.get("status", "unknown")
        duration_ms = result.get("duration_ms", 0)
        alerts_count = len(result.get("alerts", []))
        hs = result.get("health_summary", {})

        # Solo imprimir resumen seguro
        print(f"[{started}] recompute status={status} duration={duration_ms}ms alerts={alerts_count}")
        print(f"  overall={hs.get('overall_status', '?')} "
              f"source={hs.get('source_status', '?')} "
              f"matching={hs.get('matching_status', '?')} "
              f"cohorts={hs.get('cohorts_status', '?')}")

        for step in result.get("steps", []):
            print(f"  step [{step.get('status', '?')}] {step.get('name', '?')}: {step.get('message', '')}")

        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        print(f"  total_wall_ms={elapsed_ms}")

        if status == "failed":
            return 1
        return 0
    except Exception as e:
        print(f"[ERROR] recompute failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
