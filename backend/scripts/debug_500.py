"""Reproduce 500 with full file and capture traceback."""
import traceback, sys, time
sys.path.insert(0, "C:\\cursor\\AFILIATOR\\backend")
from app.database import SessionLocal
from app.services.historical_import_service import preview_historical_import
import openpyxl, io

FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"

wb = openpyxl.load_workbook(FILE, read_only=True)
ws = wb["01_PAGOS_HISTORICOS"]
rows_iter = ws.iter_rows(values_only=True)
headers = [str(h).strip() if h else "" for h in next(rows_iter, [])]
rows = []
for r in rows_iter:
    d = {}
    for j, cell in enumerate(r):
        key = headers[j] if j < len(headers) else f"col_{j}"
        val = str(cell).strip() if cell is not None else ""
        if val:
            d[key] = val
    if any(d.values()):
        rows.append(d)
wb.close()

print(f"Rows extracted: {len(rows)}")

db = SessionLocal()
try:
    t0 = time.time()
    result = preview_historical_import(db, rows, "prueba1.xlsx", "01_PAGOS_HISTORICOS")
    elapsed = time.time() - t0
    print(f"Preview OK in {elapsed:.1f}s")
    print(f"Rows: {result['total_rows']} ready={result['ready_to_import']} review={result['manual_review']} rejected={result['rejected']}")
    a = result.get('attribution', {})
    p = result.get('payment', {})
    print(f"Attr: total={a.get('total')} ready={a.get('ready')} review={a.get('manual_review')}")
    print(f"Pay: total={p.get('total')} ready={p.get('ready')} na={p.get('not_applicable')} review={p.get('manual_review')} amount={p.get('amount_ready')}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
finally:
    db.close()
