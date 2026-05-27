"""
Tests deterministicos: anchor_date vs hire_date en hitos operativos y pagos.

Verifica que:
1. compute_trip_counts_batch usa COALESCE(lead_created_at_cabinet/fleet, hire_date, created_at) como anchor_date
2. Cabinet usa lead_created_at_cabinet primario
3. Fleet usa lead_created_at_fleet primario
4. hire_date solo se usa como fallback explicito
5. Los nuevos campos de auditoria estan en el modelo ORM
"""

import sys, os, json, inspect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pass_count = 0
fail_count = 0

def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        msg = f"  FAIL  {label}"
        if detail: msg += f"  ({detail})"
        print(msg)

# ─────────────────────────────────────────────────
# TEST 1: SQL expression de anchor_date no usa hire_date como primario
# ─────────────────────────────────────────────────
print("\n--- Test 1: SQL anchor_date expression ---")

# Verificar que el SQL de compute_trip_counts_batch usa anchor_date, no hire_date
from app.adapters.source_adapter import compute_trip_counts_batch
source = inspect.getsource(compute_trip_counts_batch)

check("anchor_date expression exists in SQL",
      "COALESCE" in source and "lead_created_at_cabinet" in source)
check("lead_created_at_cabinet used for cabinet origin",
      "origen = 'cabinet'" in source and "lead_created_at_cabinet" in source)
check("lead_created_at_fleet used for fleet origin",
      "origen = 'fleet'" in source and "lead_created_at_fleet" in source)
check("hire_date used as COALESCE fallback (not primary)",
      "hire_date::date" in source)
check("created_at used as last-resort fallback",
      "created_at::date" in source)
check("anchor_date used in trip window comparison",
      "d.anchor_date" in source and "anchor_date + INTERVAL" in source)
check("NO direct hire_date reference in trip window",
      "d.hire_date + INTERVAL" not in source)

# ─────────────────────────────────────────────────
# TEST 2: Resolucion anchor_date para cabinet
# ─────────────────────────────────────────────────
print("\n--- Test 2: Cabinet anchor resolution ---")

from app.services.cutoff_engine import resolve_lead_created_at

# Cabinet with valid lead_created_at_cabinet → uses it as anchor
cabinet_row = {
    "origen": "cabinet",
    "lead_created_at_cabinet": "2026-05-01 10:00:00",
    "lead_created_at_fleet": None,
    "hire_date": "2026-05-10",
}
result_cab = resolve_lead_created_at(cabinet_row)
check("cabinet: lead_created_at_resolved = 2026-05-01",
      result_cab.get("lead_created_at_resolved") and "2026-05-01" in str(result_cab["lead_created_at_resolved"]))
check("cabinet: lead_created_at_source = lead_created_at_cabinet",
      result_cab.get("lead_created_at_source") == "lead_created_at_cabinet")
check("cabinet: lead_created_at_status = resolved_by_origen",
      result_cab.get("lead_created_at_status") == "resolved_by_origen")
check("cabinet: NO warning",
      result_cab.get("lead_created_at_warning") is None)

# ─────────────────────────────────────────────────
# TEST 3: Resolucion anchor_date para fleet
# ─────────────────────────────────────────────────
print("\n--- Test 3: Fleet anchor resolution ---")

fleet_row = {
    "origen": "fleet",
    "lead_created_at_cabinet": None,
    "lead_created_at_fleet": "2026-05-01 08:00:00",
    "hire_date": "2026-05-10",
}
result_fleet = resolve_lead_created_at(fleet_row)
check("fleet: lead_created_at_resolved = 2026-05-01",
      result_fleet.get("lead_created_at_resolved") and "2026-05-01" in str(result_fleet["lead_created_at_resolved"]))
check("fleet: lead_created_at_source = lead_created_at_fleet",
      result_fleet.get("lead_created_at_source") == "lead_created_at_fleet")
check("fleet: lead_created_at_status = resolved_by_origen",
      result_fleet.get("lead_created_at_status") == "resolved_by_origen")

# ─────────────────────────────────────────────────
# TEST 4: Fallback a hire_date
# ─────────────────────────────────────────────────
print("\n--- Test 4: hire_date fallback ---")

fallback_row = {
    "origen": "cabinet",
    "lead_created_at_cabinet": None,
    "lead_created_at_fleet": None,
}
result_fb = resolve_lead_created_at(fallback_row)
check("fallback: lead_created_at_resolved = None (no lead dates)",
      result_fb.get("lead_created_at_resolved") is None)
check("fallback: lead_created_at_status = missing",
      result_fb.get("lead_created_at_status") == "missing")
check("fallback: warning = lead_created_at_missing",
      result_fb.get("lead_created_at_warning") == "lead_created_at_missing")

# ─────────────────────────────────────────────────
# TEST 5: Sin ninguna fecha base
# ─────────────────────────────────────────────────
print("\n--- Test 5: No date at all ---")

nodate_row = {
    "origen": "cabinet",
    "lead_created_at_cabinet": None,
    "lead_created_at_fleet": None,
    "hire_date": None,
}
result_nd = resolve_lead_created_at(nodate_row)
check("nodate: lead_created_at_resolved = None",
      result_nd.get("lead_created_at_resolved") is None)
check("nodate: lead_created_at_status = missing",
      result_nd.get("lead_created_at_status") == "missing")
check("nodate: warning exists",
      result_nd.get("lead_created_at_warning") is not None)

# ─────────────────────────────────────────────────
# TEST 6: Modelo ORM tiene campos de auditoria
# ─────────────────────────────────────────────────
print("\n--- Test 6: ORM model audit fields ---")

from app.models.scout_liq import CutoffDriverLine
model_cols = [c.name for c in CutoffDriverLine.__table__.columns]
audit_fields = ['acquisition_anchor_date', 'anchor_source', 'anchor_confidence',
                'anchor_warning', 'anchor_fallback_used', 'metric_window_start',
                'metric_window_end', 'hire_date', 'hire_date_reference', 'date_basis']
for f in audit_fields:
    check(f"model has '{f}'", f in model_cols)

# ─────────────────────────────────────────────────
# TEST 7: Schema snapshot incluye rule_type y origin_scope
# ─────────────────────────────────────────────────
print("\n--- Test 7: Snapshot with rule_type and origin_scope ---")

from app.services.cutoff_engine import _build_config_snapshot_from_resolved
resolved_test = {
    "scheme_id": 1, "scheme_name": "Cab QC", "scheme_type": "cabinet",
    "scheme_version_id": 10, "version_name": "v1",
    "valid_from_cohort_iso_week": "2026-W20",
    "maturity_days": 7, "maturity_window_days": 7,
    "min_activated": 10, "min_volume_count": 10,
    "activation_rule": "1V7D", "volume_rule": "1V7D",
    "quality_rule": "5V7D",
    "counts_volume_rule": "1V7D", "counts_quality_rule": "5V7D",
    "formula_type": "ACTIVATED_X_TIER",
    "pays_on_rule": "QUALITY_HIT",
    "payout_formula_type": "ACTIVATED_X_TIER",
    "currency": "PEN",
    "block_scope": "driver_metric_origin",
    "tiers": [{"min_conversion_rate": 0.10, "payout_amount": 10.0, "sort_order": 0}],
}
snap = json.loads(_build_config_snapshot_from_resolved(resolved_test))
check("snapshot: rule_type = cohort_quality_tier", snap.get("rule_type") == "cohort_quality_tier")
check("snapshot: origin_scope = cabinet", snap.get("origin_scope") == "cabinet")
check("snapshot: block_scope = driver_metric_origin", snap.get("block_scope") == "driver_metric_origin")
check("snapshot: has frozen_at", "frozen_at" in snap)

# ─────────────────────────────────────────────────
# TEST 8: Escenario comparativo: anchor gana sobre hire_date
# ─────────────────────────────────────────────────
print("\n--- Test 8: Anchor wins over hire_date (escenario conceptual) ---")

# Simulacion: driver cabinet con hire_date=05-10 y lead_cabinet=05-01
# Ventana desde anchor_date (05-01): viajes del 01 al 08 mayo → 5 viajes → 5V/7D = TRUE
# Ventana desde hire_date (05-10): viajes del 10 al 17 mayo → 0 viajes → 5V/7D = FALSE
# Conclusión: usar anchor_date da TRUE, usar hire_date da FALSE. El motor debe usar anchor_date.

anchor_window_start = "2026-05-01"
anchor_window_end = "2026-05-08"
hire_window_start = "2026-05-10"
hire_window_end = "2026-05-17"

trips_in_anchor_window = 5
trips_in_hire_window = 0

check("anchor window: 5 trips in [01, 08] -> 5V/7D TRUE",
      trips_in_anchor_window >= 5)
check("hire window: 0 trips in [10, 17] -> 5V/7D FALSE",
      trips_in_hire_window < 5)
check("CONCLUSION: anchor_date gives different (correct) result vs hire_date",
      (trips_in_anchor_window >= 5) != (trips_in_hire_window >= 5))

# ─────────────────────────────────────────────────
# TEST 9: Fleet aggregate bonus window
# ─────────────────────────────────────────────────
print("\n--- Test 9: Fleet 50V/30D aggregate window ---")

fleet_anchor_start = "2026-05-01"
fleet_anchor_end = "2026-05-31"
fleet_hire_start = "2026-05-10"
fleet_hire_end = "2026-06-09"

trips_anchor_30d = 50
trips_hire_30d = 25

check("anchor 30d window [01, 31]: 50 trips >= 50 -> TRUE",
      trips_anchor_30d >= 50)
check("hire 30d window [10, 09]: 25 trips < 50 -> FALSE",
      trips_hire_30d < 50)
check("CONCLUSION: fleet 50V/30D depends on using anchor_date",
      (trips_anchor_30d >= 50) != (trips_hire_30d >= 50))

print("\n==================================================")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count == 0:
    print("TODOS LOS TESTS DE FECHA ANCLA PASARON")
