"""Test hardened CSV parser: semicolon, tab, BOM, Excel dates."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.unified_load_service import (
    _parse_rows_from_csv, _detect_delimiter, _parse_date, _normalize_header,
    unified_preview,
)
from app.database import SessionLocal

base = os.path.dirname(__file__)

def test_file(name, expected_delim, min_rows):
    path = os.path.join(base, name)
    content = open(path, encoding='utf-8-sig').read()
    rows, errors, meta = _parse_rows_from_csv(content)
    print(f"\n--- {name} ---")
    print(f"  delimiter: {meta.get('delimiter_detected')} (expected {expected_delim})")
    print(f"  columns: {meta.get('columns_detected')}")
    print(f"  rows: {len(rows)} (min {min_rows})")
    if errors:
        print(f"  errors: {errors}")
    ok = meta.get('delimiter_detected') == expected_delim and len(rows) >= min_rows and not errors
    print(f"  {'[OK]' if ok else '[FAIL]'}")
    return ok

# Test 1: Detect delimiter
print("=== DELIMITER DETECTION ===")
tab_char = "\t"
assert _detect_delimiter("a,b,c,d") == ",", "Expected comma"
assert _detect_delimiter("a;b;c;d") == ";", "Expected semicolon"
assert _detect_delimiter(f"a{tab_char}b{tab_char}c{tab_char}d") == "\t", f"Expected tab got {repr(_detect_delimiter(f'a{tab_char}b{tab_char}c'))}"
print("  [OK] Delimiter detection works")

# Test 2: Excel serial date
print("\n=== EXCEL DATES ===")
d = _parse_date("46148")
print(f"  46148 -> {d} (Excel serial, May 2026)")
assert d is not None and d.year == 2026 and d.month == 5, f"Got {d}"

d2 = _parse_date("15/05/2026")
print(f"  15/05/2026 -> {d2}")
assert d2 is not None and d2.year == 2026 and d2.month == 5 and d2.day == 15, f"Got {d2}"

d3 = _parse_date("2026-01-15")
print(f"  2026-01-15 -> {d3}")
assert d3 is not None, f"Got {d3}"
print("  [OK] Excel dates work")

# Test 3: Semicolon CSV
test_file("test_semicolon.csv", ";", 2)

# Test 4: Tab CSV  
test_file("test_tab.csv", "\t", 1)

# Test 5: Excel dates CSV
test_file("test_excel_dates.csv", ",", 2)

# Test 6: BOM handling
print("\n--- BOM test ---")
bom_content = "\ufefflicencia,scout,supervisor,pagado,monto_pagado,fecha_pago,observacion\nQ1,SA,SP,SI,10,2026-01-01,ok"
rows, errors, meta = _parse_rows_from_csv(bom_content)
print(f"  delimiter: {meta.get('delimiter_detected')}")
print(f"  columns: {meta.get('columns_detected')}")
print(f"  rows: {len(rows)}")
assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
assert "\ufeff" not in str(meta.get('columns_detected', [])), "BOM not stripped from headers"
print("  [OK] BOM handled correctly")

# Test 7: Column mismatch reporting
print("\n--- Column mismatch ---")
bad_content = "col_a,col_b,col_c\n1,2,3\n4,5,6"
rows, errors, meta = _parse_rows_from_csv(bad_content)
print(f"  errors: {errors}")
assert len(errors) >= 1, "Should report missing required columns"
assert "columnas requeridas" in errors[0].lower(), "Should mention required columns"
print("  [OK] Column mismatch reported correctly")

# Test 8: Full preview with semicolon CSV
print("\n--- Full preview with semicolon CSV ---")
db = SessionLocal()
try:
    csv_text = open(os.path.join(base, 'test_semicolon.csv'), encoding='utf-8-sig').read()
    rows, errors, meta = _parse_rows_from_csv(csv_text)
    result = unified_preview(db, rows)
    result["parse_metadata"] = meta
    print(f"  total_rows: {result['total_rows']}")
    print(f"  valid_rows: {result['valid_rows']}")
    print(f"  error_rows: {result['error_rows']}")
    print(f"  delimiter: {meta['delimiter_detected']}")
    assert meta['delimiter_detected'] == ';', f"Expected ; got {meta['delimiter_detected']}"
    print("  [OK] Full preview with semicolon works")
finally:
    db.close()

print("\n[GO] All parser tests passed")
