"""Test structural error detection with suggested mappings."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.unified_load_service import (
    _parse_rows_from_csv, _suggest_column_mapping,
)

base = os.path.dirname(__file__)

def test_structural(name, csv_content, expected_structural, expected_suggestions=None):
    print(f"\n--- {name} ---")
    rows, errors, meta = _parse_rows_from_csv(csv_content)
    
    structural = meta.get("structural_error", False)
    print(f"  structural_error: {structural} (expected {expected_structural})")
    
    if structural:
        print(f"  expected_columns: {meta.get('expected_columns')}")
        print(f"  detected_columns: {meta.get('columns_detected')}")
        suggestions = meta.get("suggested_mapping", {})
        print(f"  suggested_mapping: {suggestions}")
        print(f"  rows parsed: {len(rows)} (should be 0)")
        
        if expected_suggestions:
            for det, exp in expected_suggestions.items():
                actual = suggestions.get(det)
                status = "[OK]" if actual == exp else f"[FAIL] expected {exp} got {actual}"
                print(f"    {status} {det} -> {actual}")
    
    assert structural == expected_structural, f"structural_error: {structural} != {expected_structural}"
    if structural:
        assert len(rows) == 0, "Should have 0 rows on structural error"
    
    print(f"  [OK]")
    return True

# Test 1: Correct columns - no structural error
print("=== STRUCTURAL ERROR DETECTION ===")
good = "licencia,scout,supervisor,pagado,monto_pagado,fecha_pago,observacion\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("Correcto", good, False)

# Test 2: Unknown columns that normalization can't map
bad_monto = "licencia,scout,supervisor,pagado,Precio,fecha_pago,observacion\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("Precio vs monto_pagado", bad_monto, True)  # "Precio" has no heuristic match

# Test 3: fecha vs fecha_pago (normalize handles "fecha" -> "fecha_pago")
# Use "Dia_de_pago" instead
bad_fecha = "licencia,scout,supervisor,pagado,monto_pagado,Dia_de_pago,observacion\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("Dia_de_pago vs fecha_pago", bad_fecha, True)

# Test 4: Multiple missing - completely wrong headers
bad_multi = "lic,scout,supervisor,estado,Precio,Dia_de_pago,notas\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("multiple unknown columns", bad_multi, True)

# Test 5: Mayusculas/minusculas
bad_case = "LICENCIA,SCOUT,SUPERVISOR,PAGADO,MONTO_PAGADO,FECHA_PAGO,OBSERVACION\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("uppercase headers", bad_case, False)  # Should normalize correctly!

# Test 6: Truly unrecognizable column name
bad_spaces = "licencia,scout,supervisor,pagado,Valor_total,fecha_pago,observacion\nQ1,S,J,SI,10,2026-01-01,ok"
test_structural("Valor_total unknown", bad_spaces, True)

# Test 7: Suggested mapping heuristic standalone
print("\n=== SUGGESTED MAPPING HEURISTIC ===")
sugg = _suggest_column_mapping(["monto", "fecha", "lic", "estado", "scout_name", "supervisor_name", "obs"])
print(f"  Input: ['monto', 'fecha', 'lic', 'estado', 'scout_name', 'supervisor_name', 'obs']")
print(f"  Suggestions: {sugg}")
assert sugg.get("monto") == "monto_pagado", f"monto -> {sugg.get('monto')}"
assert sugg.get("fecha") == "fecha_pago", f"fecha -> {sugg.get('fecha')}"
assert sugg.get("lic") == "licencia", f"lic -> {sugg.get('lic')}"
assert sugg.get("estado") == "pagado", f"estado -> {sugg.get('estado')}"
assert sugg.get("scout_name") == "scout", f"scout_name -> {sugg.get('scout_name')}"
assert sugg.get("obs") == "observacion", f"obs -> {sugg.get('obs')}"
print("  [OK] All heuristic suggestions correct")

# Test 8: Libro1.csv (semicolons, good columns)
print("\n=== Libro1.csv ===")
libro_path = os.path.join(base, "Libro1.csv")
if os.path.exists(libro_path):
    content = open(libro_path, encoding='utf-8-sig').read()
    rows, errors, meta = _parse_rows_from_csv(content)
    print(f"  structural_error: {meta.get('structural_error')}")
    print(f"  delimiter: {meta.get('delimiter_detected')}")
    print(f"  columns: {meta.get('columns_detected')}")
    print(f"  rows: {len(rows)}")
    assert not meta.get("structural_error"), "Libro1 should NOT have structural error"
    assert len(rows) == 4, f"Expected 4 rows, got {len(rows)}"
    print("  [OK] Libro1.csv parsed correctly")
else:
    print("  [SKIP] Libro1.csv not found")

print("\n[GO] All structural error tests passed")
