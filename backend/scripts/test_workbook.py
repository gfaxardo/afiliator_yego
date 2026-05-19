import requests, json, time
FILE = r"C:\Users\Gonzalo Fajardo\Downloads\Plantilla_AFILIATOR_Carga_Historica_Esquemas_Manual PRUEBA 1.xlsx"
t0 = time.time()
with open(FILE, "rb") as f:
    r = requests.post("http://localhost:8000/scout-liq/workbook-import/preview",
        files={"file": ("p.xlsx", f, "application/octet-stream")}, timeout=300)
elapsed = time.time() - t0
data = r.json()
g = data.get("global", {})
s = data.get("scouts", {})
sup = data.get("supervisors", {})
p = data.get("payments", {})
pay = p.get("payment", {})
attr = p.get("attribution", {})
print(f"Status: {r.status_code} ({elapsed:.1f}s)")
print(f"Hojas: {len(data.get('detected_sheets',[]))} detectadas, {len(data.get('ignored_sheets',[]))} ignoradas")
print(f"Scouts: total={s.get('total_rows')} create={s.get('will_create')} update={s.get('will_update')}")
print(f"Supervisores: detectados={sup.get('total_detected')} ready={sup.get('ready_to_link')} needs_create={sup.get('needs_create')} conflicts={sup.get('conflicts')}")
print(f"Links scout-supervisor: {len(sup.get('scout_supervisor_links',[]))}")
print(f"Atribuciones (06): ready={data.get('attributions',{}).get('ready')} review={data.get('attributions',{}).get('manual_review')}")
print(f"Pagos: ready={pay.get('ready')} not_applicable={pay.get('not_applicable')} review={pay.get('manual_review')} monto=S/ {pay.get('amount_ready')}")
print(f"Attr desde pagos: ready={attr.get('ready')} review={attr.get('manual_review')}")
print(f"\nGLOBAL: scouts={g.get('scouts_ready')} supers={g.get('supervisors_detected')} attr_ready={g.get('attribution_ready')} pay_ready={g.get('payment_ready')} pay_na={g.get('payment_not_applicable')} monto=S/ {g.get('amount_ready')} time={g.get('elapsed_ms')}ms")
cands = sup.get("candidates", [])[:5]
if cands:
    print("\nTop supervisores:")
    for c in cands:
        print(f"  {c.get('supervisor_name')} freq={c.get('frequency_total')} top_scouts={c.get('top_scouts')[:3]} sources={c.get('sources')} status={c.get('status')}")
