"""
CLI script: Health Refresh para Liquidador Scouts Yego.

Ejecuta el ciclo completo de health monitoring:
  - Snapshot de fuentes y procesos
  - Deteccion de eventos de salud
  - Resolucion de eventos recuperados
  - Calculo de health score

Uso:
  python scripts/scout_liq_health_refresh.py

Salida:
  Imprime resumen legible. Exit code 0 si OK, 1 si falla.

No depende del frontend ni del navegador.
No modifica fuentes operativas.
"""

import sys
import os
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import SessionLocal
from app.services.scout_liq_health_registry_service import (
    refresh_registry_snapshot,
    detect_health_events,
    resolve_recovered_events,
    compute_health_score_lite,
)


def main() -> int:
    t0 = time.perf_counter()
    db = SessionLocal()

    try:
        print("Health Refresh iniciado...")

        registry = refresh_registry_snapshot(db)
        events_detected = detect_health_events(db)
        events_resolved = resolve_recovered_events(db)
        score = compute_health_score_lite(db)

        new_events = events_detected.get("new_events", 0)
        if isinstance(new_events, list):
            new_events = len(new_events)

        resolved = events_resolved.get("resolved_count", 0)
        source_entry = next(
            (e for e in registry.get("entries", []) if e.get("source_name") == "module_ct_cabinet_drivers"),
            {},
        )
        lag_minutes = source_entry.get("lag_minutes")
        if lag_minutes is not None:
            lag_hours = round(lag_minutes / 60.0, 1)
            lag_days = round(lag_minutes / 1440.0, 1)
        else:
            lag_hours = None
            lag_days = None

        total_ms = round((time.perf_counter() - t0) * 1000)

        print()
        print("=" * 50)
        print("Health Refresh OK")
        print("=" * 50)
        print(f"  evaluated_at:    {score.get('evaluated_at', 'N/A')}")
        print(f"  global_status:   {score.get('status', 'N/A')}")
        print(f"  score:           {score.get('score', 'N/A')}")
        print(f"  events_open:     {events_detected.get('new_events', 0)}")
        print(f"  events_created:  {new_events}")
        print(f"  events_resolved: {resolved}")
        print(f"  source_status:   {source_entry.get('status', 'N/A')}")
        print(f"  source_lag_days:    {lag_days}")
        print(f"  source_lag_hours:   {lag_hours}")
        print(f"  source_lag_minutes: {lag_minutes}")
        print(f"  duration_ms:     {total_ms}")
        print("=" * 50)

        db.commit()
        db.close()
        return 0

    except Exception as e:
        db.rollback()
        db.close()
        total_ms = round((time.perf_counter() - t0) * 1000)
        tb = traceback.format_exc()
        print()
        print("=" * 50)
        print("Health Refresh FAILED")
        print("=" * 50)
        print(f"  error:        {e}")
        print(f"  duration_ms:  {total_ms}")
        print("=" * 50)
        print("Traceback:")
        print(tb)
        return 1


if __name__ == "__main__":
    sys.exit(main())
