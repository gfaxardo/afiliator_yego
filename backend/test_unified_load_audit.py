"""
Tests para validar la regla: N filas de input = N filas en reporte de auditoria.

Prueba:
1. Input con 10 filas genera reporte con 10 filas.
2. Filas no_change aparecen en reporte.
3. Filas rechazadas aparecen en reporte.
4. Filas ignoradas (skipped_duplicate) aparecen en reporte.
5. Filas con driver_not_found aparecen en reporte.
6. Filas sin driver (validation_error) aparecen en reporte.
7. Resumen no se mezcla como filas falsas en el reporte principal.
8. El conteo del reporte coincide con el input.
"""
import sys
import os
import io
import csv
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.unified_load_service import (
    generate_full_audit_csv,
    generate_summary_csv,
)

pass_count = 0
fail_count = 0
errors = []


def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  OK  {label}")
    else:
        fail_count += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        errors.append(msg)


# ---- Test 1: 10 filas input -> 10 filas en reporte ----

preview_lines_10 = []
for i in range(10):
    preview_lines_10.append({
        "source_row": i + 2,
        "licencia": f"LIC{i:03d}",
        "scout": f"Scout {i}",
        "supervisor": f"Sup {i}",
        "pagado": "SI" if i < 5 else "NO",
        "monto_pagado": 100.0 if i < 5 else 0,
        "fecha_pago": "2024-01-01" if i < 5 else "",
        "fecha_atribucion": "2024-01-01",
        "tipo_evento": "new",
        "observacion": f"Obs {i}",
        "nombre_conductor": f"Driver {i}",
        "origen": "Lima",
        "tipo_scout": "cabinet",
        "motivo_pago": "",
        "cohorte_iso": "",
        "status": "ok",
        "errors": [],
        "warnings": [],
        "deduced_actions": ["assign_scout"],
        "driver_id_resolved": f"DRV{i:03d}",
        "scout_id_resolved": 100 + i,
    })

# Apply lines for 5 rows only (others not in apply_plan)
apply_lines_5 = []
for i in range(5):
    apply_lines_5.append({
        "source_row": i + 2,
        "action": "created_assignment" if i < 3 else "no_change",
        "status": "ok",
        "saved": True,
        "message": "Asignado" if i < 3 else "Sin cambios",
        "what_happened": ["Asignado a Scout"] if i < 3 else ["Sin cambios"],
        "licencia": f"LIC{i:03d}",
        "driver_id": f"DRV{i:03d}",
    })

csv_content = generate_full_audit_csv(preview_lines_10, apply_lines_5, "test.csv")
reader = csv.reader(io.StringIO(csv_content))
rows = list(reader)

# Row 0 is header, rows 1-10 are data
data_rows = [r for r in rows[1:] if r and any(c.strip() for c in r)]

check(
    "Test 1: 10 filas input = 10 filas en reporte",
    len(data_rows) == 10,
    f"Esperado 10, obtenido {len(data_rows)}"
)

# ---- Test 2: Filas no_change aparecen en reporte ----
action_index = rows[0].index("action") if "action" in rows[0] else 16
no_change_found = False
for r in data_rows:
    if len(r) > action_index and r[action_index] == "no_change":
        no_change_found = True
        break
check("Test 2: Filas no_change aparecen en reporte", no_change_found)

# ---- Test 3: Todas las columnas originales incluidas ----
header = rows[0]
original_cols = ["source_row", "licencia", "scout", "supervisor", "pagado", "monto_pagado",
                 "fecha_pago", "fecha_atribucion", "tipo_evento", "observacion",
                 "driver_id", "nombre_conductor", "origen",
                 "tipo_scout", "motivo_pago", "cohorte_iso"]
for col in original_cols:
    check(f"Test 3a: Columna '{col}' presente", col in header)

# ---- Test 4: Columnas de auditoria presentes ----
audit_cols = ["audit_status", "action", "saved", "applied", "rejected", "conflict",
              "ignored", "already_paid", "not_found", "error_code", "error_message",
              "what_happened", "rejection_reason"]
for col in audit_cols:
    check(f"Test 4a: Columna auditoria '{col}' presente", col in header)

# ---- Test 5: Sin resumen mezclado en data rows ----
for r in data_rows:
    first = r[0] if r else ""
    is_summary = first.strip().startswith("=== ") or first.strip() in (
        "metrica", "file_name", "processed_at", "total_rows", "applied"
    )
    check(f"Test 5: Fila {r[0] if r else '?'} no es resumen", not is_summary,
          f"Resumen encontrado en fila de datos: {first}")

# ---- Test 6: Filas con error de validacion aparecen ----
preview_lines_with_errors = [
    {
        "source_row": 2, "licencia": "", "scout": "", "supervisor": "",
        "pagado": "", "monto_pagado": 0, "fecha_pago": "",
        "fecha_atribucion": "", "tipo_evento": "",
        "observacion": "",
        "nombre_conductor": "", "origen": "", "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
        "status": "error", "errors": ["Falta campo requerido: licencia"],
        "warnings": [], "deduced_actions": [],
        "driver_id_resolved": None, "scout_id_resolved": None,
    },
]
csv_error = generate_full_audit_csv(preview_lines_with_errors, [], "test_errors.csv")
error_rows = list(csv.reader(io.StringIO(csv_error)))[1:]  # skip header
check(
    "Test 6: Fila con validation_error aparece en reporte",
    len(error_rows) >= 1,
    f"Esperado 1, obtenido {len(error_rows)}"
)

# ---- Test 7: Filas con driver_not_found aparecen ----
preview_lines_not_found = [
    {
        "source_row": 2, "licencia": "LIC999", "scout": "Scout X", "supervisor": "Sup X",
        "pagado": "SI", "monto_pagado": 50, "fecha_pago": "",
        "fecha_atribucion": "", "tipo_evento": "",
        "observacion": "",
        "nombre_conductor": "", "origen": "", "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
        "status": "error", "errors": ["Licencia no encontrada en fuente"],
        "warnings": [], "deduced_actions": ["driver_not_found"],
        "driver_id_resolved": None, "scout_id_resolved": None,
    },
]
csv_nf = generate_full_audit_csv(preview_lines_not_found, [], "test_not_found.csv")
nf_rows = list(csv.reader(io.StringIO(csv_nf)))[1:]
check(
    "Test 7: Fila con driver_not_found aparece en reporte",
    len(nf_rows) >= 1,
    f"Esperado 1, obtenido {len(nf_rows)}"
)

# ---- Test 8: Filas skipped_duplicate aparecen ----
preview_lines_dup = [
    {
        "source_row": 2, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
        "pagado": "", "monto_pagado": 0, "fecha_pago": "",
        "fecha_atribucion": "", "tipo_evento": "",
        "observacion": "",
        "nombre_conductor": "", "origen": "", "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
        "status": "skipped_duplicate", "errors": [],
        "warnings": ["Driver duplicado en archivo. Fila ganadora: 5"],
        "deduced_actions": ["skipped_duplicate"],
        "driver_id_resolved": "DRV001", "scout_id_resolved": None,
        "duplicate_of_row": 5,
    },
]
csv_dup = generate_full_audit_csv(preview_lines_dup, [], "test_dup.csv")
dup_rows = list(csv.reader(io.StringIO(csv_dup)))[1:]
check(
    "Test 8: Fila skipped_duplicate aparece en reporte",
    len(dup_rows) >= 1,
    f"Esperado 1, obtenido {len(dup_rows)}"
)

# ---- Test 9: Summary CSV independiente funciona ----
summary_csv = generate_summary_csv(
    {"total_rows": 10, "valid_rows": 5, "error_rows": 2, "duplicate_rows": 3,
     "drivers_found": 5, "drivers_not_found": 2,
     "scouts_to_create": 0, "assignments_to_create": 3, "assignments_to_change": 1,
     "payments_to_create": 2, "already_paid": 1},
    {"applied": 3, "skipped": 2, "no_change": 2, "conflicts": 0, "errors": 1,
     "commit_ok": True, "commit_error": None},
    10, 5, "test.csv"
)
summary_rows = list(csv.reader(io.StringIO(summary_csv)))
check(
    "Test 9: Summary CSV tiene mas de 5 lineas",
    len(summary_rows) > 5,
    f"Obtenido {len(summary_rows)} lineas"
)

# ---- Test 10: BOM NOT embedded in raw CSV from function (added by router) ----
check(
    "Test 10: generate_full_audit_csv no contiene BOM (router lo agrega)",
    not csv_content.startswith("\ufeff")
)

# ---- Test 11: Cada source_row es unico en el reporte ----
source_rows = [r[0] for r in data_rows if r and r[0]]
unique_sr = len(set(source_rows))
check(
    "Test 11: source_row sin duplicados en reporte",
    unique_sr == len(data_rows),
    f"{unique_sr} unicos vs {len(data_rows)} total"
)

# ---- Test 12: Already_paid flag correcto ----
preview_lines_ap = [
    {
        "source_row": 2, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
        "pagado": "SI", "monto_pagado": 100, "fecha_pago": "",
        "fecha_atribucion": "2024-01-01", "tipo_evento": "new",
        "observacion": "",
        "nombre_conductor": "", "origen": "", "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
        "status": "warning", "errors": [], "warnings": ["Ya pagado"],
        "deduced_actions": ["already_paid"],
        "driver_id_resolved": "DRV001", "scout_id_resolved": 1,
    },
]
csv_ap = generate_full_audit_csv(preview_lines_ap, [], "test_ap.csv")
ap_rows = list(csv.reader(io.StringIO(csv_ap)))
ap_header = ap_rows[0] if ap_rows else []
ap_data = [r for r in ap_rows[1:] if r and any(c.strip() for c in r)]
ap_col_index = ap_header.index("already_paid") if "already_paid" in ap_header else 22
already_paid_val = ap_data[0][ap_col_index] if len(ap_data) > 0 and len(ap_data[0]) > ap_col_index else ""
check(
    "Test 12: already_paid = true para fila ya pagada",
    already_paid_val == "true",
    f"Obtenido: {already_paid_val}"
)


# ═══════════════════════════════════════
# PARITY REPORT TESTS
# ═══════════════════════════════════════

from app.services.unified_load_service import _compute_parity

# Test 13: Parity statuses present
parity_cols = ["parity_status", "parity_explanation", "source_record_key",
               "driver_resolution_status", "assignment_status", "payment_history_status",
               "needs_human_review", "next_action", "blocking_reason",
               "applied_entities", "skipped_entities", "rejected_entities"]
for col in parity_cols:
    check(f"Test 13a: Parity columna '{col}' presente", col in header)

# Test 14: full_applied — driver found, assignment created
pl_full = {
    "source_row": 2, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
    "pagado": "SI", "monto_pagado": 100, "fecha_pago": "2024-01-01",
    "fecha_atribucion": "2024-01-01", "tipo_evento": "new",
    "observacion": "", "nombre_conductor": "Driver A", "origen": "cabinet",
    "tipo_scout": "destajo", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "DRV001", "scout_id_resolved": 1,
    "status": "ok", "errors": [], "warnings": [],
    "deduced_actions": ["assign_scout", "create_payment"],
}
apply_full = {
    "action": "created_assignment", "status": "ok", "saved": True,
    "assignment_created": True, "payment_created": True,
    "eligible_for_cutoff": True, "driver_operational_state": "matched",
}
parity = _compute_parity(pl_full, apply_full, "ok", "created_assignment",
                         False, False, False, True, True)
check("Test 14a: full_applied parity_status", parity["parity_status"] == "full_applied")
check("Test 14b: full_applied next_action", parity["next_action"] == "ready_for_cutoff")

# Test 15: observed_pending — driver_not_found with observed created
pl_obs = {
    "source_row": 3, "licencia": "LIC999", "scout": "Scout B", "supervisor": "Sup B",
    "pagado": "NO", "monto_pagado": 0, "fecha_pago": "",
    "fecha_atribucion": "", "tipo_evento": "",
    "observacion": "", "nombre_conductor": "Driver X", "origen": "fleet",
    "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "", "scout_id_resolved": None,
    "status": "error", "errors": ["Licencia no encontrada"],
    "warnings": [], "deduced_actions": ["driver_not_found"],
}
apply_obs = {
    "action": "driver_not_found_observed_saved", "status": "observed_saved",
    "saved": True, "observed_affiliation_created": True,
    "observed_affiliation_id": 327, "observed_affiliation_status": "unmatched",
    "assignment_created": False, "payment_created": False,
    "eligible_for_cutoff": False, "driver_operational_state": "observed_only",
}
parity = _compute_parity(pl_obs, apply_obs, "observed", "driver_not_found_observed_saved",
                         True, False, False, False, False)
check("Test 15a: observed_pending parity_status", parity["parity_status"] == "observed_pending")
check("Test 15b: observed_pending next_action", parity["next_action"] == "wait_reconciliation")
check("Test 15c: observed_pending applied_entities", "observed_affiliation" in parity["applied_entities"])

# Test 16: already_reflected — assignment already exists
pl_ref = {
    "source_row": 4, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
    "pagado": "NO", "monto_pagado": 0, "fecha_pago": "",
    "fecha_atribucion": "", "tipo_evento": "",
    "observacion": "", "nombre_conductor": "Driver A", "origen": "cabinet",
    "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "DRV001", "scout_id_resolved": 1,
    "status": "ok", "errors": [], "warnings": [],
    "deduced_actions": [],
}
apply_ref = {
    "action": "no_change", "status": "ok", "saved": True,
    "assignment_created": False, "payment_created": False,
    "eligible_for_cutoff": True, "driver_operational_state": "matched",
}
parity = _compute_parity(pl_ref, apply_ref, "ok", "no_change",
                         False, False, False, False, False)
check("Test 16a: already_reflected parity_status", parity["parity_status"] == "already_reflected")

# Test 17: rejected_unusable — no evidence
pl_rej = {
    "source_row": 5, "licencia": "", "scout": "Scout C", "supervisor": "Sup C",
    "pagado": "", "monto_pagado": 0, "fecha_pago": "",
    "fecha_atribucion": "", "tipo_evento": "",
    "observacion": "", "nombre_conductor": "", "origen": "",
    "tipo_scout": "", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "", "scout_id_resolved": None,
    "status": "error", "errors": ["Falta campo requerido: licencia"],
    "warnings": [], "deduced_actions": [],
}
apply_rej = {
    "action": "validation_error", "status": "skipped", "saved": False,
    "assignment_created": False, "payment_created": False,
}
parity = _compute_parity(pl_rej, apply_rej, "rejected", "validation_error",
                         False, True, False, False, False)
check("Test 17a: rejected_unusable parity_status", parity["parity_status"] == "rejected_unusable")
check("Test 17b: rejected_unusable next_action", parity["next_action"] == "fix_license_or_phone")

# Test 18: partial_applied — assignment created, payment skipped (invalid amount)
pl_part = {
    "source_row": 6, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
    "pagado": "SI", "monto_pagado": 0, "fecha_pago": "",
    "fecha_atribucion": "2024-01-01", "tipo_evento": "new",
    "observacion": "", "nombre_conductor": "Driver A", "origen": "cabinet",
    "tipo_scout": "destajo", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "DRV001", "scout_id_resolved": 1,
    "status": "ok", "errors": [], "warnings": [],
    "deduced_actions": ["assign_scout", "attribution_only"],
}
apply_part = {
    "action": "created_assignment", "status": "ok", "saved": True,
    "assignment_created": True, "payment_created": False,
    "eligible_for_cutoff": True, "driver_operational_state": "matched",
}
parity = _compute_parity(pl_part, apply_part, "ok", "created_assignment",
                         False, False, False, True, False)
check("Test 18a: partial_applied parity_status", parity["parity_status"] == "partial_applied")

# Test 19: pagado=NO with assignment created should NOT be partial
pl_attr = {
    "source_row": 7, "licencia": "LIC001", "scout": "Scout A", "supervisor": "Sup A",
    "pagado": "NO", "monto_pagado": 0, "fecha_pago": "",
    "fecha_atribucion": "2024-01-01", "tipo_evento": "new",
    "observacion": "", "nombre_conductor": "Driver A", "origen": "cabinet",
    "tipo_scout": "destajo", "motivo_pago": "", "cohorte_iso": "",
    "driver_id_resolved": "DRV001", "scout_id_resolved": 1,
    "status": "ok", "errors": [], "warnings": [],
    "deduced_actions": ["assign_scout", "attribution_only"],
}
apply_attr = {
    "action": "created_assignment", "status": "ok", "saved": True,
    "assignment_created": True, "payment_created": False,
    "eligible_for_cutoff": True, "driver_operational_state": "matched",
}
parity_attr = _compute_parity(pl_attr, apply_attr, "ok", "created_assignment",
                              False, False, False, True, False)
check("Test 19a: pagado=NO con assignment = full_applied (no partial)",
      parity_attr["parity_status"] == "full_applied",
      f"Got {parity_attr['parity_status']}, explanation: {parity_attr['parity_explanation']}")

# Test 20: verify parity columns exist in header (backward compat)
legacy_cols = ["audit_status", "action", "saved", "applied", "rejected",
               "ignored", "already_paid", "not_found"]
for col in legacy_cols:
    check(f"Test 20: Legacy columna '{col}' conservada", col in header)


# ═══════════════════════════════════════
print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    print("Errores:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("TODOS LOS TESTS PASARON")
    sys.exit(0)
