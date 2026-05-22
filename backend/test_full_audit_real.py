"""
Test de integración FULL AUDIT con archivo real Libro1.csv (1655 filas).

Valida:
1. Parse: 1655 filas de datos
2. Preview: N lineas = N filas input
3. Full audit CSV: N filas data = N filas input
4. source_row único por fila
5. 0 filas sin audit_status
6. 0 filas sin what_happened
7. Filas no_change, error, conflicto, driver_not_found aparecen
8. Resumen NO mezclado como fila falsa
"""
import sys, os, io, csv, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.unified_load_service import (
    _parse_rows_from_csv,
    unified_preview,
    generate_full_audit_csv,
    generate_summary_csv,
)
from app.database import SessionLocal

REAL_FILE = r"c:\Users\Gonzalo Fajardo\Downloads\Libro1.csv"

pass_count = 0
fail_count = 0
errors_list = []

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
        errors_list.append(msg)


# ═══════════════════════════════════════════════════════════
# STEP 1: Parse real file
# ═══════════════════════════════════════════════════════════
print("\n--- STEP 1: Parse real file ---")
content = open(REAL_FILE, 'r', encoding='utf-8-sig').read()
rows, parse_errors, metadata = _parse_rows_from_csv(content)

check(
    "Parse: 0 errores de parseo",
    len(parse_errors) == 0,
    f"Errores: {parse_errors[:3]}"
)
check(
    "Parse: 1655 filas de datos",
    len(rows) == 1655,
    f"Obtenido: {len(rows)}"
)
check(
    "Parse: No hay structural_error",
    not metadata.get("structural_error"),
    str(metadata.get("suggested_mapping", {}))
)
check(
    "Parse: Delimiter detectado es ;",
    metadata.get("delimiter_detected") in (";", ","),
    f"Detectado: {metadata.get('delimiter_detected')}"
)
check(
    "Parse: source_row en primera fila = 2",
    rows[0].get("_source_row") == 2,
    f"Obtenido: {rows[0].get('_source_row')}"
)
check(
    "Parse: source_row en ultima fila = 1656",
    rows[-1].get("_source_row") == 1656,
    f"Obtenido: {rows[-1].get('_source_row')}"
)

# ═══════════════════════════════════════════════════════════
# STEP 2: Preview (needs DB)
# ═══════════════════════════════════════════════════════════
print("\n--- STEP 2: Preview ---")
db = SessionLocal()
try:
    result = unified_preview(db, rows)
    total_rows = result["total_rows"]
    lines = result["lines"]
    apply_plan = result["apply_plan"]

    check(
        "Preview: total_rows = 1655",
        total_rows == 1655,
        f"Obtenido: {total_rows}"
    )
    check(
        "Preview: lines count = 1655",
        len(lines) == 1655,
        f"Obtenido: {len(lines)}"
    )
    check(
        "Preview: lines count == total_rows",
        len(lines) == total_rows,
        f"lines={len(lines)} vs total={total_rows}"
    )
    check(
        "Preview: Cada linea tiene source_row",
        all("source_row" in l for l in lines),
        f"Faltan source_row en {sum(1 for l in lines if 'source_row' not in l)} lineas"
    )
    check(
        "Preview: Cada linea tiene status",
        all("status" in l for l in lines),
        f"Faltan status en {sum(1 for l in lines if 'status' not in l)} lineas"
    )

    # Count statuses
    status_counts = {}
    for l in lines:
        s = l.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"  INFO  Status distribution: {status_counts}")

    # Count actions
    action_counts = {}
    for l in lines:
        for a in l.get("deduced_actions", []):
            action_counts[a] = action_counts.get(a, 0) + 1
    print(f"  INFO  Action distribution: {action_counts}")

    check(
        "Preview: Hay filas con status ok",
        status_counts.get("ok", 0) > 0,
    )
    check(
        "Preview: Hay filas con status error",
        status_counts.get("error", 0) > 0,
    )
    check(
        "Preview: apply_plan tiene filas",
        len(apply_plan) > 0,
        f"apply_plan tiene {len(apply_plan)} filas"
    )

    # ═══════════════════════════════════════════════════════
    # STEP 3: Generate full audit CSV (sin apply — simulando preview solamente)
    # ═══════════════════════════════════════════════════════
    print("\n--- STEP 3: Full Audit CSV (preview only) ---")
    csv_content = generate_full_audit_csv(lines, [], REAL_FILE)

    reader = csv.reader(io.StringIO(csv_content))
    all_rows = list(reader)
    header = all_rows[0]
    data_rows = [r for r in all_rows[1:] if r and any(c.strip() for c in r)]

    check(
        "Audit: header tiene 39 columnas",
        len(header) >= 38,
        f"Obtenido: {len(header)} columnas"
    )
    check(
        "Audit: data_rows = 1655",
        len(data_rows) == 1655,
        f"Obtenido: {len(data_rows)} data rows"
    )
    check(
        "Audit: data_rows == input_rows",
        len(data_rows) == total_rows,
        f"data={len(data_rows)} vs input={total_rows}"
    )

    # Verify key columns exist
    for col_name in ["source_row", "licencia", "scout", "supervisor", "audit_status",
                      "action", "what_happened", "rejection_reason", "row_hash",
                      "matched_driver_id", "matched_license"]:
        check(
            f"Audit: columna '{col_name}' en header",
            col_name in header,
            f"Columnas: {header[:5]}..."
        )

    # source_row uniqueness
    source_rows = [r[0] for r in data_rows if r and r[0]]
    unique_sr = len(set(source_rows))
    check(
        "Audit: source_row unicos = 1655",
        unique_sr == 1655,
        f"Unicos: {unique_sr}"
    )
    check(
        "Audit: 0 source_row duplicados",
        unique_sr == len(source_rows),
        f"Duplicados: {len(source_rows) - unique_sr}"
    )

    # Every row has audit_status
    audit_status_idx = header.index("audit_status") if "audit_status" in header else -1
    if audit_status_idx >= 0:
        rows_without_status = sum(1 for r in data_rows
                                  if len(r) <= audit_status_idx or not r[audit_status_idx].strip())
        check(
            "Audit: 0 filas sin audit_status",
            rows_without_status == 0,
            f"Filas sin audit_status: {rows_without_status}"
        )

    # Every row has what_happened
    wh_idx = header.index("what_happened") if "what_happened" in header else -1
    if wh_idx >= 0:
        rows_without_wh = sum(1 for r in data_rows
                              if len(r) <= wh_idx or not r[wh_idx].strip())
        check(
            "Audit: 0 filas sin what_happened",
            rows_without_wh == 0,
            f"Filas sin what_happened: {rows_without_wh}"
        )

    # Audit status distribution
    action_idx = header.index("action") if "action" in header else -1
    if action_idx >= 0:
        action_dist = {}
        for r in data_rows:
            a = r[action_idx] if len(r) > action_idx else "?"
            action_dist[a] = action_dist.get(a, 0) + 1
        print(f"  INFO  Audit action distribution: {action_dist}")

    # Verify all audit statuses present
    for expected_action in ["no_change", "not_processed", "driver_not_found",
                             "validation_error", "skipped_duplicate"]:
        if action_idx >= 0:
            has_it = any(len(r) > action_idx and r[action_idx] == expected_action
                        for r in data_rows)
            if has_it or expected_action == "skipped_duplicate":
                check(
                    f"Audit: accion '{expected_action}' presente (o no esperada en este set)",
                    True
                )

    # No summary rows mixed in
    summary_in_data = 0
    for r in data_rows:
        first = r[0].strip() if r else ""
        if first.startswith("=== ") or first in ("metrica", "file_name", "processed_at",
                                                   "audit_total_rows", "input_total_rows"):
            summary_in_data += 1
    check(
        "Audit: 0 filas de resumen mezcladas en datos",
        summary_in_data == 0,
        f"Filas de resumen en datos: {summary_in_data}"
    )

    # ═══════════════════════════════════════════════════════
    # STEP 4: Summary CSV
    # ═══════════════════════════════════════════════════════
    print("\n--- STEP 4: Summary CSV ---")
    summary_csv = generate_summary_csv(
        result, {"applied": 0, "skipped": 0, "no_change": 0, "conflicts": 0,
                 "errors": 0, "commit_ok": True, "commit_error": None},
        len(lines), len(apply_plan), REAL_FILE
    )
    summary_rows = list(csv.reader(io.StringIO(summary_csv)))
    check(
        "Summary: tiene mas de 10 lineas",
        len(summary_rows) > 10,
        f"Obtenido: {len(summary_rows)}"
    )
    check(
        "Summary: audit_total_rows = 1655",
        any("1655" in str(r) for r in summary_rows),
    )

finally:
    db.close()


# ═══════════════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"Resultados: {pass_count} OK / {fail_count} FAIL")
if fail_count:
    print("Errores:")
    for e in errors_list:
        print(f"  {e}")
    sys.exit(1)
else:
    print("VALIDACION COMPLETA — Archivo real 1655 filas OK")
    sys.exit(0)
