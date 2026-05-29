"""
FASE 0 — FINAL: Queries that need explicit execution (fix FILTER syntax)
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

TABLE = "module_ct_cabinet_drivers"

def q(sql, params=None, fetch="all"):
    with engine.connect() as conn:
        try:
            result = conn.execute(text(sql), params or {})
            if fetch == "scalar":
                val = result.scalar()
                conn.commit()
                return val
            elif fetch == "first":
                row = result.first()
                conn.commit()
                return row
            else:
                rows = result.fetchall()
                conn.commit()
                return rows
        except Exception as e:
            conn.rollback()
            return f"ERR: {e}"

def pc(part, total):
    if not total: return "0"
    return f"{round(100*part/total,1)}%"

# ══════════════════════════════════════════════════════════
# 1. DATE RANGES
# ══════════════════════════════════════════════════════════
print("=" * 80)
print("1. DATE RANGES")
print("=" * 80)

print("\n1A. lead_created_at range (::timestamp):")
r = q(f"SELECT MIN(lead_created_at::timestamp), MAX(lead_created_at::timestamp) FROM {TABLE} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''", fetch="first")
print(f"  {r}")

print("\n1B. lead_created_at range (::date):")
r = q(f"SELECT MIN(lead_created_at::date), MAX(lead_created_at::date) FROM {TABLE} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''", fetch="first")
print(f"  {r}")

print("\n1C. hire_date range (::date):")
r = q(f"SELECT MIN(hire_date::date), MAX(hire_date::date) FROM {TABLE} WHERE hire_date IS NOT NULL AND hire_date::text != ''", fetch="first")
print(f"  {r}")

print("\n1D. created_at range:")
r = q(f"SELECT MIN(created_at), MAX(created_at) FROM {TABLE}", fetch="first")
print(f"  {r}")

print("\n1E. last_active_date range (::date):")
r = q(f"SELECT MIN(last_active_date::date), MAX(last_active_date::date) FROM {TABLE} WHERE last_active_date IS NOT NULL AND last_active_date::text != ''", fetch="first")
print(f"  {r}")

# ══════════════════════════════════════════════════════════
# 2. OVERLAP & CONSISTENCY (using CASE WHEN, not FILTER)
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("2. OVERLAP & CONSISTENCY")
print("=" * 80)

# Total and counts
t = q(f"SELECT COUNT(*) FROM {TABLE}", fetch="scalar")
lca = q(f"SELECT COUNT(*) FROM {TABLE} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''", fetch="scalar")
hd = q(f"SELECT COUNT(*) FROM {TABLE} WHERE hire_date IS NOT NULL AND hire_date::text != ''", fetch="scalar")
both = q(f"SELECT COUNT(*) FROM {TABLE} WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '' AND hire_date IS NOT NULL AND hire_date::text != ''", fetch="scalar")
either = q(f"SELECT COUNT(*) FROM {TABLE} WHERE (lead_created_at IS NOT NULL AND lead_created_at::text != '') OR (hire_date IS NOT NULL AND hire_date::text != '')", fetch="scalar")
neither = q(f"SELECT COUNT(*) FROM {TABLE} WHERE (lead_created_at IS NULL OR lead_created_at::text = '') AND (hire_date IS NULL OR hire_date::text = '')", fetch="scalar")

print(f"\n  Total:  {t}")
print(f"  LCA:    {lca} ({pc(lca,t)})")
print(f"  HD:     {hd} ({pc(hd,t)})")
print(f"  Both:   {both} ({pc(both,t)})")
print(f"  Either: {either} ({pc(either,t)})")
print(f"  Neither:{neither} ({pc(neither,t)})")

# 2A. hire_date vs created_at consistency
print("\n2A. hire_date vs created_at:")
r = q(f"""
    SELECT
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL THEN 1 ELSE 0 END) as both_present,
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL
                  AND hire_date::date <= created_at::date THEN 1 ELSE 0 END) as logical_order,
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != '' AND created_at IS NOT NULL
                  AND hire_date::date > created_at::date THEN 1 ELSE 0 END) as inverted
    FROM {TABLE}
""", fetch="first")
if isinstance(r, tuple):
    bp = r[0]
    lo = r[1]
    inv = r[2]
    print(f"  Both present:  {bp}")
    print(f"  Logical (hd <= ca): {lo} ({pc(lo,bp)})")
    print(f"  Inverted (hd > ca): {inv} ({pc(inv,bp)})")

# 2B. lead_created_at vs hire_date consistency
print("\n2B. lead_created_at vs hire_date (order):")
r = q(f"""
    SELECT
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND hire_date IS NOT NULL AND hire_date::text != '' THEN 1 ELSE 0 END) as both_present,
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND hire_date IS NOT NULL AND hire_date::text != ''
                  AND lead_created_at::date <= hire_date::date THEN 1 ELSE 0 END) as lca_before_hd,
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND hire_date IS NOT NULL AND hire_date::text != ''
                  AND lead_created_at::date > hire_date::date THEN 1 ELSE 0 END) as lca_after_hd,
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND hire_date IS NOT NULL AND hire_date::text != ''
                  AND lead_created_at::date = hire_date::date THEN 1 ELSE 0 END) as same_day
    FROM {TABLE}
""", fetch="first")
if isinstance(r, tuple):
    bp = r[0]
    before = r[1]
    after = r[2]
    same = r[3]
    print(f"  Both present:    {bp}")
    print(f"  lca <= hd:       {before} ({pc(before,bp)})")
    print(f"  lca > hd:        {after} ({pc(after,bp)})")
    print(f"  Same day:        {same} ({pc(same,bp)})")

# Average gap
gap = q(f"""
    SELECT ROUND(AVG(hire_date::date - lead_created_at::date)::numeric, 1),
           MIN(hire_date::date - lead_created_at::date),
           MAX(hire_date::date - lead_created_at::date)
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
""", fetch="first")
if isinstance(gap, tuple):
    print(f"  Avg gap (hd - lca): {gap[0]} days")
    print(f"  Min gap:            {gap[1]} days")
    print(f"  Max gap:            {gap[2]} days")

# 2C. lead_created_at vs created_at
print("\n2C. lead_created_at vs created_at:")
r = q(f"""
    SELECT
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND created_at IS NOT NULL THEN 1 ELSE 0 END) as both_present,
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND created_at IS NOT NULL
                  AND lead_created_at::date <= created_at::date THEN 1 ELSE 0 END) as lca_before_ca,
        SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != ''
                  AND created_at IS NOT NULL
                  AND lead_created_at::date > created_at::date THEN 1 ELSE 0 END) as lca_after_ca
    FROM {TABLE}
""", fetch="first")
if isinstance(r, tuple):
    bp = r[0]
    before = r[1]
    after = r[2]
    print(f"  Both present:       {bp}")
    print(f"  lca <= created_at:  {before} ({pc(before,bp)})")
    print(f"  lca > created_at:   {after} ({pc(after,bp)})")

# 2D. hire_date vs last_active_date
print("\n2D. hire_date vs last_active_date:")
r = q(f"""
    SELECT
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != ''
                  AND last_active_date IS NOT NULL AND last_active_date::text != '' THEN 1 ELSE 0 END) as both_present,
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != ''
                  AND last_active_date IS NOT NULL AND last_active_date::text != ''
                  AND hire_date::date <= last_active_date::date THEN 1 ELSE 0 END) as logical,
        SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != ''
                  AND last_active_date IS NOT NULL AND last_active_date::text != ''
                  AND hire_date::date > last_active_date::date THEN 1 ELSE 0 END) as inverted
    FROM {TABLE}
""", fetch="first")
if isinstance(r, tuple):
    bp = r[0]
    lo = r[1]
    inv = r[2]
    print(f"  Both present:       {bp}")
    print(f"  Logical (hd<=lad):  {lo} ({pc(lo,bp)})")
    print(f"  Inverted:           {inv} ({pc(inv,bp)})")

# ══════════════════════════════════════════════════════════
# 3. GAP BUCKETS (hd - lca)
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("3. GAP BUCKETS: hire_date - lead_created_at")
print("=" * 80)

buckets = q(f"""
    SELECT
        CASE
            WHEN hire_date::date - lead_created_at::date < 0 THEN 'inverted'
            WHEN hire_date::date - lead_created_at::date = 0 THEN 'same_day'
            WHEN hire_date::date - lead_created_at::date BETWEEN 1 AND 3 THEN '1_3_days'
            WHEN hire_date::date - lead_created_at::date BETWEEN 4 AND 7 THEN '4_7_days'
            WHEN hire_date::date - lead_created_at::date BETWEEN 8 AND 14 THEN '8_14_days'
            WHEN hire_date::date - lead_created_at::date BETWEEN 15 AND 30 THEN '15_30_days'
            ELSE 'gt_30_days'
        END as bucket,
        COUNT(*) as cnt
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
    GROUP BY bucket
    ORDER BY cnt DESC
""")
if isinstance(buckets, list):
    for r in buckets:
        print(f"  {r[0]:20s} = {r[1]:4d} ({pc(r[1], both)})")

# ══════════════════════════════════════════════════════════
# 4. DETAILED INVERTED ANALYSIS
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4. INVERTED lca > hd: Análisis detallado")
print("=" * 80)

inv_count = q(f"""
    SELECT COUNT(*)
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND lead_created_at::date > hire_date::date
""", fetch="scalar")
print(f"\n  Total inverted: {inv_count} ({pc(inv_count, both)})")

# Inverted by bucket
inv_buckets = q(f"""
    SELECT
        CASE
            WHEN lead_created_at::date - hire_date::date <= 30 THEN '<=30d'
            WHEN lead_created_at::date - hire_date::date <= 90 THEN '31-90d'
            WHEN lead_created_at::date - hire_date::date <= 180 THEN '91-180d'
            WHEN lead_created_at::date - hire_date::date <= 365 THEN '181-365d'
            ELSE '>365d'
        END as inv_bucket,
        COUNT(*) as cnt
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND lead_created_at::date > hire_date::date
    GROUP BY inv_bucket
    ORDER BY MIN(lead_created_at::date - hire_date::date)
""")
if isinstance(inv_buckets, list):
    print(f"\n  Magnitud de inversión (lca AFTER hd):")
    for r in inv_buckets:
        print(f"    {r[0]:15s} = {r[1]:4d}")

# Inverted by origen/status
inv_detail = q(f"""
    SELECT origen, status,
           COUNT(*) as cnt,
           ROUND(AVG(lead_created_at::date - hire_date::date)) as avg_inv_days
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND lead_created_at::date > hire_date::date
    GROUP BY origen, status
    ORDER BY cnt DESC
    LIMIT 15
""")
if isinstance(inv_detail, list):
    print(f"\n  Inverted por origen/status:")
    for r in inv_detail:
        print(f"    origen={r[0]}, status={str(r[1] or 'NULL'):35s} cnt={r[2]:3d} avg_inv={r[3]}d")

# ══════════════════════════════════════════════════════════
# 5. module_ct_cabinet_leads DETAIL
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5. module_ct_cabinet_leads DETAIL")
print("=" * 80)

# Columns
cl_cols = q("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'module_ct_cabinet_leads'
    ORDER BY ordinal_position
""")
if isinstance(cl_cols, list):
    print(f"\n  Columns ({len(cl_cols)}):")
    for r in cl_cols:
        print(f"    {r[0]:35s} {r[1]}")

# overlap analysis
print("\n  Overlap with cabinet_drivers:")
overlap = q("""
    SELECT
        (SELECT COUNT(*) FROM module_ct_cabinet_leads) as leads_total,
        (SELECT COUNT(*) FROM module_ct_cabinet_leads WHERE driver_id IS NOT NULL) as leads_with_driver,
        (SELECT COUNT(DISTINCT cl.driver_id) FROM module_ct_cabinet_leads cl
         JOIN module_ct_cabinet_drivers cd ON cl.driver_id = cd.driver_id) as overlap,
        (SELECT COUNT(DISTINCT cd.driver_id) FROM module_ct_cabinet_drivers cd
         WHERE cd.lead_created_at IS NULL
           AND cd.driver_id IN (SELECT driver_id FROM module_ct_cabinet_leads WHERE lead_created_at IS NOT NULL)) as drivers_missing_lca_but_available_in_leads
""", fetch="first")
if isinstance(overlap, tuple):
    print(f"  Total leads:                    {overlap[0]}")
    print(f"  Leads with driver_id:           {overlap[1]}")
    print(f"  Overlap (in both tables):       {overlap[2]}")
    print(f"  Drivers missing lca BUT available in leads: {overlap[3]}")

# ══════════════════════════════════════════════════════════
# 6. FLEET DEEP DIVE
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("6. FLEET DEEP DIVE")
print("=" * 80)

print("\n6A. Fleet stats:")
fleet = q(f"""
    SELECT
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as with_hd,
        COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date::text = '') as without_hd,
        COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '') as with_lca,
        COUNT(*) FILTER (WHERE park_name = 'ADQUISICI�N LINKTREE 20.11') as linktree_outliers,
        MIN(hire_date::date) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as min_hd,
        MAX(hire_date::date) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as max_hd
    FROM {TABLE}
    WHERE origen = 'fleet'
""", fetch="first")
if isinstance(fleet, tuple):
    print(f"  Total fleet:              {fleet[0]}")
    print(f"  With hire_date:           {fleet[1]} ({pc(fleet[1], fleet[0])})")
    print(f"  Without hire_date:        {fleet[2]}")
    print(f"  With lead_created_at:     {fleet[3]} (0 = always NULL)")
    print(f"  Linktree outliers:        {fleet[4]}")
    print(f"  hire_date range:          [{fleet[5]}, {fleet[6]}]")

# Fleet park_name distribution
print("\n6B. Fleet park_name distribution:")
fleet_parks = q(f"""
    SELECT park_name, COUNT(*) as cnt
    FROM {TABLE}
    WHERE origen = 'fleet'
    GROUP BY park_name
    ORDER BY cnt DESC
    LIMIT 15
""")
if isinstance(fleet_parks, list):
    for r in fleet_parks:
        print(f"  {str(r[0] or 'NULL')[:50]:50s} = {r[1]}")

# ══════════════════════════════════════════════════════════
# 7. STATUS & SEGMENT CROSS-ANALYSIS
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("7. STATUS X SEGMENT X ORIGEN")
print("=" * 80)

ss = q(f"""
    SELECT origen, status, segment, COUNT(*) as cnt
    FROM {TABLE}
    GROUP BY origen, status, segment
    ORDER BY cnt DESC
    LIMIT 20
""")
if isinstance(ss, list):
    for r in ss:
        print(f"  origen={str(r[0] or 'NULL'):10s} status={str(r[1] or 'NULL'):35s} segment={str(r[2] or 'NULL'):15s} = {r[3]}")

# ══════════════════════════════════════════════════════════
# 8. ALL ANCHOR DATES COMPARISON PER ORIGEN
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("8. ALL ANCHOR DATES COVERAGE PER ORIGEN")
print("=" * 80)

anchor = q(f"""
    SELECT origen,
           COUNT(*) as total,
           SUM(CASE WHEN lead_created_at IS NOT NULL AND lead_created_at::text != '' THEN 1 ELSE 0 END) as has_lca,
           SUM(CASE WHEN hire_date IS NOT NULL AND hire_date::text != '' THEN 1 ELSE 0 END) as has_hd,
           SUM(CASE WHEN (lead_created_at IS NOT NULL AND lead_created_at::text != '')
                      OR (hire_date IS NOT NULL AND hire_date::text != '') THEN 1 ELSE 0 END) as has_either,
           MIN(COALESCE(lead_created_at::date, hire_date::date)) as min_anchor,
           MAX(COALESCE(lead_created_at::date, hire_date::date)) as max_anchor
    FROM {TABLE}
    GROUP BY origen
""")
if isinstance(anchor, list):
    for r in anchor:
        print(f"\n  origen={r[0]}:")
        print(f"    total={r[1]}, has_lca={r[2]} ({pc(r[2],r[1])}), has_hd={r[3]} ({pc(r[3],r[1])}), has_either={r[4]} ({pc(r[4],r[1])})")
        print(f"    anchor range: [{r[5]}, {r[6]}]")

# ══════════════════════════════════════════════════════════
# 9. FINAL METRICS FOR REPORT
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("9. FINAL QUALITY METRICS")
print("=" * 80)

lca_rate = round(100 * lca / t, 1)
hd_rate = round(100 * hd / t, 1)
either_rate = round(100 * either / t, 1)
neither_rate = round(100 * neither / t, 1)
both_rate = round(100 * both / t, 1)

print(f"""
  CALIDAD DE CAMPOS TEMPORALES:

  Campo              | Poblado   | Null/Empty | Formato
  -------------------|-----------|------------|------------------
  lead_created_at    | {lca_rate}%      | {round(100-lca_rate,1)}%       | ISO 8601 (T sep)
  hire_date          | {hd_rate}%      | {round(100-hd_rate,1)}%       | YYYY-MM-DD
  created_at         | 100%      | 0%         | timestamp tz
  updated_at         | 100%      | 0%         | timestamp tz
  last_active_date   | ~15%      | ~85%       | YYYY-MM-DD (mixed)

  CONSISTENCIA TEMPORAL:

  Relación            | Correcto   | Invertido  | Nota
  --------------------|------------|------------|---------------------------
  hd <= created_at    | ?          | ?          | (from query 2A)
  lca <= hd           | ?          | ?          | (from query 2B - mayormente invertido!)
  hd <= last_active   | ?          | ?          | (from query 2D)

  COBERTURA:

  Ambos campos (lca+hd):     {both_rate}%
  Al menos uno:              {either_rate}%
  Ninguno:                   {neither_rate}%

  DISTRIBUCIÓN POR ORIGEN:

  Origen    | Total | lead_created_at | hire_date    | Ambos | Ninguno
  ----------|-------|-----------------|--------------|-------|----------
""")

# Breakdown
for orig in ['cabinet', 'fleet']:
    oc = q(f"SELECT COUNT(*) FROM {TABLE} WHERE origen = '{orig}'", fetch="scalar")
    ol = q(f"SELECT COUNT(*) FROM {TABLE} WHERE origen = '{orig}' AND lead_created_at IS NOT NULL AND lead_created_at::text != ''", fetch="scalar")
    oh = q(f"SELECT COUNT(*) FROM {TABLE} WHERE origen = '{orig}' AND hire_date IS NOT NULL AND hire_date::text != ''", fetch="scalar")
    ob = q(f"SELECT COUNT(*) FROM {TABLE} WHERE origen = '{orig}' AND lead_created_at IS NOT NULL AND lead_created_at::text != '' AND hire_date IS NOT NULL AND hire_date::text != ''", fetch="scalar")
    onone = q(f"SELECT COUNT(*) FROM {TABLE} WHERE origen = '{orig}' AND (lead_created_at IS NULL OR lead_created_at::text = '') AND (hire_date IS NULL OR hire_date::text = '')", fetch="scalar")
    print(f"  {orig:10s} | {oc:5d} | {pc(ol,oc):14s} ({ol}) | {pc(oh,oc):12s} ({oh}) | {pc(ob,oc):8s} ({ob}) | {pc(onone,oc):7s} ({onone})")

print("""
  HALLAZGO CRÍTICO:
  lead_created_at NO es la fecha de adquisición real.
  En la mayoría de los casos, lead_created_at > hire_date.
  Esto sugiere que lead_created_at es la fecha en que el registro
  fue creado en el sistema de cabinet/scouting, no la fecha de
  adquisición/contratación del conductor.

  SEMÁNTICA INFERIDA:
  - lead_created_at: fecha de creación del lead en sistema cabinet (NO adquisición)
  - hire_date: fecha de contratación/registro en la plataforma Yego
  - created_at: fecha de sincronización ETL a esta tabla
  - updated_at: última actualización del registro en esta tabla

  RECOMENDACIÓN FINAL:
  - lead_created_at: NO GO como anchor date de adquisición (semántica invertida)
  - hire_date: GO como anchor date primario para cohortes y métricas
  - Para drivers sin hire_date: investigar fuente alternativa o usar created_at como proxy
  - Considerar COALESCE(hire_date::date, created_at::date) para máxima cobertura
""")

print("=" * 80)
print("AUDITORÍA COMPLETADA - FASE 0")
print("=" * 80)
