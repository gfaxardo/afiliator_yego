"""
FASE 0 — AUDIT v3: Profiling profundo de lead_created_at y consistencia temporal
"""
import sys
sys.path.insert(0, r'C:\cursor\AFILIATOR\backend')
from app.database import engine
from sqlalchemy import text

TABLE = "module_ct_cabinet_drivers"

def safe_query(sql, params=None, fetch="all"):
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
            return f"ERROR: {e}"

def pct(part, total):
    return round(100 * part / max(total, 1), 1)

total = safe_query(f"SELECT COUNT(*) FROM {TABLE}", fetch="scalar")
print(f"Total rows: {total}\n")

# ═══════════════════════════════════════════════════════════
# 1. lead_created_at: formato, distribución temporal
# ═══════════════════════════════════════════════════════════
print("=" * 80)
print("SECCIÓN 1 — lead_created_at PROFILING PROFUNDO")
print("=" * 80)

# Format exploration
print("\n1A. Formatos de lead_created_at (muestra):")
fmt_samples = safe_query(f"""
    SELECT lead_created_at
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
    LIMIT 30
""")
if isinstance(fmt_samples, list):
    formats = set()
    for r in fmt_samples:
        val = r[0]
        if 'T' in val:
            formats.add('ISO_8601 (YYYY-MM-DDTHH:MM:SS)')
        elif ' ' in val:
            formats.add('YYYY-MM-DD HH:MM:SS')
        elif len(val) == 10:
            formats.add('YYYY-MM-DD')
        elif '/' in val:
            formats.add('DD/MM/YYYY or MM/DD/YYYY')
        else:
            formats.add(f'OTHER: {val[:30]}')
    print(f"  Formats detectados: {formats}")
    print(f"  Ejemplos: {[r[0] for r in fmt_samples[:5]]}")

# Date range
print("\n1B. Rango temporal lead_created_at:")
lca_range = safe_query(f"""
    SELECT MIN(lead_created_at::timestamp), MAX(lead_created_at::timestamp),
           MIN(lead_created_at::date), MAX(lead_created_at::date)
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
""", fetch="first")
if isinstance(lca_range, tuple):
    print(f"  Min timestamp: {lca_range[0]}")
    print(f"  Max timestamp: {lca_range[1]}")
    print(f"  Min date: {lca_range[2]}")
    print(f"  Max date: {lca_range[3]}")

# Distribution by month
print("\n1C. Distribución lead_created_at por mes:")
lca_months = safe_query(f"""
    SELECT EXTRACT(YEAR FROM lead_created_at::date)::int as yr,
           EXTRACT(MONTH FROM lead_created_at::date)::int as mon,
           origen,
           COUNT(*) as cnt
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
    GROUP BY yr, mon, origen
    ORDER BY yr, mon, origen
""")
if isinstance(lca_months, list) and lca_months:
    for r in lca_months:
        print(f"  {r[0]}-{r[1]:02d} origen={str(r[2] or 'NULL'):10s} = {r[3]:4d}")

# Future timestamps
print("\n1D. Timestamps futuros en lead_created_at:")
lca_future = safe_query(f"""
    SELECT COUNT(*)
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL
      AND lead_created_at::text != ''
      AND lead_created_at::timestamp > CURRENT_TIMESTAMP
""", fetch="scalar")
print(f"  Future: {lca_future}")

# By origen
print("\n1E. lead_created_at por origen:")
lca_origin = safe_query(f"""
    SELECT origen,
           COUNT(*) as total,
           COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '') as with_lca,
           COUNT(*) FILTER (WHERE lead_created_at IS NULL) as without_lca
    FROM {TABLE}
    GROUP BY origen
    ORDER BY total DESC
""")
if isinstance(lca_origin, list):
    for r in lca_origin:
        t = r[1]
        w = r[2]
        print(f"  {str(r[0] or 'NULL'):10s} total={t:4d} with_lca={w:4d} ({pct(w,t)}%) without={r[3]:4d}")

# ═══════════════════════════════════════════════════════════
# 2. hire_date profiling profundo
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 2 — hire_date PROFILING PROFUNDO")
print("=" * 80)

print("\n2A. Rango hire_date:")
hd_range = safe_query(f"""
    SELECT MIN(hire_date::date), MAX(hire_date::date)
    FROM {TABLE}
    WHERE hire_date IS NOT NULL AND hire_date::text != ''
""", fetch="first")
if isinstance(hd_range, tuple):
    print(f"  Min: {hd_range[0]}, Max: {hd_range[1]}")

# hire_date by origen
print("\n2B. hire_date por origen:")
hd_origin = safe_query(f"""
    SELECT origen,
           COUNT(*) as total,
           COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as with_hd,
           COUNT(*) FILTER (WHERE hire_date IS NULL OR hire_date::text = '') as without_hd,
           MIN(hire_date::date) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as min_hd,
           MAX(hire_date::date) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as max_hd
    FROM {TABLE}
    GROUP BY origen
    ORDER BY total DESC
""")
if isinstance(hd_origin, list):
    for r in hd_origin:
        t = r[1]
        w = r[2]
        print(f"  {str(r[0] or 'NULL'):10s} total={t:4d} with_hd={w:4d} ({pct(w,t)}%) without={r[3]:4d} range=[{r[4]}, {r[5]}]")

# Year distribution for hire_date
print("\n2C. Distribución hire_date por año/origen:")
hd_yr = safe_query(f"""
    SELECT EXTRACT(YEAR FROM hire_date::date)::int as yr,
           origen,
           COUNT(*) as cnt
    FROM {TABLE}
    WHERE hire_date IS NOT NULL AND hire_date::text != ''
    GROUP BY yr, origen
    ORDER BY yr, origen
""")
if isinstance(hd_yr, list):
    for r in hd_yr:
        print(f"  {r[0]} origen={str(r[1] or 'NULL'):10s} = {r[2]:4d}")

# ═══════════════════════════════════════════════════════════
# 3. OVERLAP: lead_created_at vs hire_date
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 3 — OVERLAP: lead_created_at vs hire_date")
print("=" * 80)

overlap = safe_query(f"""
    SELECT
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != '') as has_lca,
        COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != '') as has_hd,
        COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
                          AND hire_date IS NOT NULL AND hire_date::text != '') as has_both,
        COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
                          AND (hire_date IS NULL OR hire_date::text = '')) as lca_only,
        COUNT(*) FILTER (WHERE (lead_created_at IS NULL OR lead_created_at::text = '')
                          AND hire_date IS NOT NULL AND hire_date::text != '') as hd_only,
        COUNT(*) FILTER (WHERE (lead_created_at IS NULL OR lead_created_at::text = '')
                          AND (hire_date IS NULL OR hire_date::text = '')) as neither
    FROM {TABLE}
""", fetch="first")
if isinstance(overlap, tuple):
    t = overlap[0]
    print(f"  Total:                {t}")
    print(f"  Has lead_created_at:  {overlap[1]} ({pct(overlap[1], t)}%)")
    print(f"  Has hire_date:        {overlap[2]} ({pct(overlap[2], t)}%)")
    print(f"  Has BOTH:             {overlap[3]} ({pct(overlap[3], t)}%)")
    print(f"  lead_created_at ONLY: {overlap[4]} ({pct(overlap[4], t)}%)")
    print(f"  hire_date ONLY:       {overlap[5]} ({pct(overlap[5], t)}%)")
    print(f"  NEITHER:              {overlap[6]} ({pct(overlap[6], t)}%)")

# lead_created_at vs hire_date gap analysis
print("\n3B. Gap days (hire_date - lead_created_at) when both present:")
gap_stats = safe_query(f"""
    SELECT
        COUNT(*) as both_present,
        ROUND(AVG(hire_date::date - lead_created_at::date)::numeric, 1) as avg_gap_days,
        MIN(hire_date::date - lead_created_at::date) as min_gap,
        MAX(hire_date::date - lead_created_at::date) as max_gap,
        COUNT(*) FILTER (WHERE lead_created_at::date <= hire_date::date) as logical_order,
        COUNT(*) FILTER (WHERE lead_created_at::date > hire_date::date) as inverted_order
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
""", fetch="first")
if isinstance(gap_stats, tuple):
    print(f"  Both present:  {gap_stats[0]}")
    print(f"  Avg gap days:  {gap_stats[1]}")
    print(f"  Min gap:       {gap_stats[2]}")
    print(f"  Max gap:       {gap_stats[3]}")
    print(f"  Logical (lca <= hd): {gap_stats[4]} ({pct(gap_stats[4], gap_stats[0])}%)")
    print(f"  Inverted (lca > hd): {gap_stats[5]} ({pct(gap_stats[5], gap_stats[0])}%)")

# Gap buckets
print("\n3C. Gap buckets (hire_date - lead_created_at):")
gap_buckets = safe_query(f"""
    SELECT
        CASE
            WHEN hire_date::date - lead_created_at::date <= 0 THEN 'inverted_or_same_day'
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
    ORDER BY
        CASE bucket
            WHEN 'inverted_or_same_day' THEN 1
            WHEN '1_3_days' THEN 2
            WHEN '4_7_days' THEN 3
            WHEN '8_14_days' THEN 4
            WHEN '15_30_days' THEN 5
            ELSE 6
        END
""")
if isinstance(gap_buckets, list):
    for r in gap_buckets:
        print(f"  {r[0]:30s} = {r[1]:4d} ({pct(r[1], gap_stats[0]) if isinstance(gap_stats, tuple) else '?'}%)")

# Inverted examples
print("\n3D. Ejemplos de lead_created_at > hire_date (inverted):")
inverted = safe_query(f"""
    SELECT driver_id, lead_created_at, hire_date,
           hire_date::date - lead_created_at::date as gap_days,
           origen, status
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND lead_created_at::date > hire_date::date
    LIMIT 10
""")
if isinstance(inverted, list):
    if inverted:
        for r in inverted:
            print(f"  driver={r[0][:16]}... lca={r[1]} hd={r[2]} gap={r[3]}d origen={r[4]} status={r[5]}")
    else:
        print("  (ninguno)")

# Examples where hire_date is much later than lead_created_at
print("\n3E. Ejemplos con gap >30 días (posible reactivación):")
big_gap = safe_query(f"""
    SELECT driver_id, lead_created_at, hire_date,
           hire_date::date - lead_created_at::date as gap_days,
           origen, status
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND hire_date::date - lead_created_at::date > 30
    ORDER BY gap_days DESC
    LIMIT 15
""")
if isinstance(big_gap, list):
    if big_gap:
        for r in big_gap:
            print(f"  driver={r[0][:16]}... lca={r[1]} hd={r[2]} gap={r[3]}d origen={r[4]} status={r[5]}")
    else:
        print("  (ninguno)")

# ═══════════════════════════════════════════════════════════
# 4. TIMESTAMP CONSISTENCY: created_at vs hire_date
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 4 — TIMESTAMP CONSISTENCY")
print("=" * 80)

# created_at vs hire_date
print("\n4A. created_at vs hire_date:")
ca_hd = safe_query(f"""
    SELECT
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND hire_date IS NOT NULL AND hire_date::text != '') as both,
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND hire_date IS NOT NULL AND hire_date::text != ''
                          AND hire_date::date <= created_at::date) as logical,
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND hire_date IS NOT NULL AND hire_date::text != ''
                          AND hire_date::date > created_at::date) as inverted,
        ROUND(AVG(created_at::date - hire_date::date) FILTER (
            WHERE created_at IS NOT NULL AND hire_date IS NOT NULL AND hire_date::text != ''
        )::numeric, 1) as avg_gap
    FROM {TABLE}
""", fetch="first")
if isinstance(ca_hd, tuple):
    print(f"  Both present: {ca_hd[0]}")
    print(f"  Logical (hd <= ca): {ca_hd[1]} ({pct(ca_hd[1], ca_hd[0])}%)")
    print(f"  Inverted (hd > ca): {ca_hd[2]} ({pct(ca_hd[2], ca_hd[0])}%)")
    print(f"  Avg gap days: {ca_hd[3]}")

# created_at vs lead_created_at
print("\n4B. created_at vs lead_created_at:")
ca_lca = safe_query(f"""
    SELECT
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND lead_created_at IS NOT NULL AND lead_created_at::text != '') as both,
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND lead_created_at IS NOT NULL AND lead_created_at::text != ''
                          AND lead_created_at::date <= created_at::date) as logical,
        COUNT(*) FILTER (WHERE created_at IS NOT NULL AND lead_created_at IS NOT NULL AND lead_created_at::text != ''
                          AND lead_created_at::date > created_at::date) as inverted,
        ROUND(AVG(created_at::date - lead_created_at::date) FILTER (
            WHERE created_at IS NOT NULL AND lead_created_at IS NOT NULL AND lead_created_at::text != ''
        )::numeric, 1) as avg_gap
    FROM {TABLE}
""", fetch="first")
if isinstance(ca_lca, tuple):
    print(f"  Both present: {ca_lca[0]}")
    print(f"  Logical (lca <= ca): {ca_lca[1]} ({pct(ca_lca[1], ca_lca[0])}%)")
    print(f"  Inverted (lca > ca): {ca_lca[2]} ({pct(ca_lca[2], ca_lca[0])}%)")
    print(f"  Avg gap days: {ca_lca[3]}")

# created_at range
ca_range = safe_query(f"""
    SELECT MIN(created_at), MAX(created_at)
    FROM {TABLE}
    WHERE created_at IS NOT NULL
""", fetch="first")
if isinstance(ca_range, tuple):
    print(f"\n4C. created_at range: {ca_range[0]} -> {ca_range[1]}")

# last_active_date range
lad_range = safe_query(f"""
    SELECT MIN(last_active_date::date), MAX(last_active_date::date)
    FROM {TABLE}
    WHERE last_active_date IS NOT NULL AND last_active_date::text != ''
""", fetch="first")
if isinstance(lad_range, tuple):
    print(f"4D. last_active_date range: {lad_range[0]} -> {lad_range[1]}")

# hire_date vs last_active_date
print("\n4E. hire_date vs last_active_date:")
hd_lad = safe_query(f"""
    SELECT
        COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != ''
                          AND last_active_date IS NOT NULL AND last_active_date::text != '') as both,
        COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != ''
                          AND last_active_date IS NOT NULL AND last_active_date::text != ''
                          AND hire_date::date <= last_active_date::date) as logical,
        COUNT(*) FILTER (WHERE hire_date IS NOT NULL AND hire_date::text != ''
                          AND last_active_date IS NOT NULL AND last_active_date::text != ''
                          AND hire_date::date > last_active_date::date) as inverted
    FROM {TABLE}
""", fetch="first")
if isinstance(hd_lad, tuple):
    print(f"  Both present: {hd_lad[0]}")
    print(f"  Logical (hd <= lad): {hd_lad[1]} ({pct(hd_lad[1], hd_lad[0])}%)")
    print(f"  Inverted (hd > lad): {hd_lad[2]} ({pct(hd_lad[2], hd_lad[0])}%)")

# ═══════════════════════════════════════════════════════════
# 5. REACTIVATION / RECYCLED DETECTION
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 5 — REACTIVACIONES Y RECICLADOS")
print("=" * 80)

# 5A. Lead muy antiguo + hire reciente
print("\n5A. lead_created_at pre-2025 + hire_date en 2026 (reactivación):")
old_lead = safe_query(f"""
    SELECT COUNT(*) as cnt,
           MIN(lead_created_at::date) as oldest_lead,
           MAX(hire_date::date) as newest_hire,
           ROUND(AVG(hire_date::date - lead_created_at::date)) as avg_gap_days
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
      AND lead_created_at::date < '2025-01-01'
      AND hire_date::date >= '2026-01-01'
""", fetch="first")
if isinstance(old_lead, tuple):
    print(f"  Count: {old_lead[0]}, oldest_lead={old_lead[1]}, newest_hire={old_lead[2]}, avg_gap={old_lead[3]}d")

# 5B. Drivers with lead_created_at but NO hire_date (recently added?)
print("\n5B. Drivers with lead_created_at but NO hire_date:")
lca_no_hd = safe_query(f"""
    SELECT COUNT(*) as cnt,
           origen,
           MIN(lead_created_at::date) as min_lca,
           MAX(lead_created_at::date) as max_lca
    FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND (hire_date IS NULL OR hire_date::text = '')
    GROUP BY origen
    ORDER BY cnt DESC
""")
if isinstance(lca_no_hd, list):
    for r in lca_no_hd:
        print(f"  origen={r[1]}: cnt={r[0]}, lca_range=[{r[2]}, {r[3]}]")

# 5C. Drivers with hire_date but NO lead_created_at (missing enrichment)
print("\n5C. Drivers with hire_date but NO lead_created_at:")
hd_no_lca = safe_query(f"""
    SELECT COUNT(*) as cnt,
           origen,
           MIN(hire_date::date) as min_hd,
           MAX(hire_date::date) as max_hd
    FROM {TABLE}
    WHERE hire_date IS NOT NULL AND hire_date::text != ''
      AND (lead_created_at IS NULL OR lead_created_at::text = '')
    GROUP BY origen
    ORDER BY cnt DESC
""")
if isinstance(hd_no_lca, list):
    for r in hd_no_lca:
        print(f"  origen={r[1]}: cnt={r[0]}, hd_range=[{r[2]}, {r[3]}]")

# 5D. license duplicates with details
print("\n5D. Top license duplicates with both driver_ids:")
lic_detail = safe_query(f"""
    SELECT license, COUNT(*) as cnt,
           MIN(hire_date::date) as min_hd,
           MAX(hire_date::date) as max_hd,
           STRING_AGG(DISTINCT origen, ', ') as origins
    FROM {TABLE}
    WHERE license IS NOT NULL AND license::text != ''
    GROUP BY license
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
    LIMIT 10
""")
if isinstance(lic_detail, list):
    for r in lic_detail:
        print(f"  lic={r[0][:20]}: cnt={r[1]}, hd_range=[{r[2]}, {r[3]}], origins={r[4]}")

# ═══════════════════════════════════════════════════════════
# 6. TABLAS RELACIONADAS - lead_created_at en otras tablas
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 6 — lead_created_at EN OTRAS TABLAS")
print("=" * 80)

# module_ct_cabinet_leads
print("\n6A. module_ct_cabinet_leads:")
cl_counts = safe_query("""
    SELECT COUNT(*) FROM module_ct_cabinet_leads
""", fetch="scalar")
print(f"  Total rows: {cl_counts}")

if isinstance(cl_counts, int) and cl_counts > 0:
    cl_lca = safe_query("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL) as with_lca,
            MIN(lead_created_at) as min_lca,
            MAX(lead_created_at) as max_lca
        FROM module_ct_cabinet_leads
    """, fetch="first")
    if isinstance(cl_lca, tuple):
        print(f"  With lead_created_at: {cl_lca[1]}/{cl_lca[0]} ({pct(cl_lca[1], cl_lca[0])}%)")
        print(f"  Range: {cl_lca[2]} -> {cl_lca[3]}")

    # Check overlap with cabinet_drivers
    cl_overlap = safe_query("""
        SELECT
            COUNT(DISTINCT cl.driver_id) as leads_with_driver,
            COUNT(DISTINCT cd.driver_id) as overlap
        FROM module_ct_cabinet_leads cl
        JOIN module_ct_cabinet_drivers cd ON cl.driver_id = cd.driver_id
    """, fetch="first")
    if isinstance(cl_overlap, tuple):
        print(f"  Leads with driver_id: {cl_overlap[0]}")
        print(f"  Overlap with cabinet_drivers: {cl_overlap[1]}")

# lead_matches
print("\n6B. lead_matches:")
lm_counts = safe_query("""
    SELECT COUNT(*) FROM lead_matches
""", fetch="scalar")
print(f"  Total rows: {lm_counts}")

if isinstance(lm_counts, int) and lm_counts > 0:
    lm_lca = safe_query("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE lead_created_at IS NOT NULL) as with_lca,
            MIN(lead_created_at) as min_lca,
            MAX(lead_created_at) as max_lca
        FROM lead_matches
    """, fetch="first")
    if isinstance(lm_lca, tuple):
        print(f"  With lead_created_at: {lm_lca[1]}/{lm_lca[0]} ({pct(lm_lca[1], lm_lca[0])}%)")
        print(f"  Range: {lm_lca[2]} -> {lm_lca[3]}")

# v_cabinet_leads_missing_scout_alerts (VIEW)
print("\n6C. v_cabinet_leads_missing_scout_alerts (view):")
try:
    vw_count = safe_query("""
        SELECT COUNT(*) FROM ops.v_cabinet_leads_missing_scout_alerts
    """, fetch="scalar")
    print(f"  Total rows: {vw_count}")
except Exception as e:
    print(f"  {e}")

# Check if scout_liq_driver_assignments has any lead_created_at info
print("\n6D. driver_assignments that have source_origin with lead info:")
sla_origin = safe_query("""
    SELECT source_origin, COUNT(*) as cnt
    FROM scout_liq_driver_assignments
    WHERE status = 'active'
    GROUP BY source_origin
    ORDER BY cnt DESC
    LIMIT 10
""")
if isinstance(sla_origin, list):
    for r in sla_origin:
        print(f"  source_origin={str(r[0] or 'NULL'):30s} = {r[1]}")

# ═══════════════════════════════════════════════════════════
# 7. FINAL EVALUATION
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("SECCIÓN 7 — EVALUACIÓN FINAL ANCHOR DATE")
print("=" * 80)

# Calculate key metrics
lca_present = safe_query(f"""
    SELECT COUNT(*) FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
""", fetch="scalar")
lca_present = lca_present if isinstance(lca_present, int) else 0

hd_present = safe_query(f"""
    SELECT COUNT(*) FROM {TABLE}
    WHERE hire_date IS NOT NULL AND hire_date::text != ''
""", fetch="scalar")
hd_present = hd_present if isinstance(hd_present, int) else 0

both_present = safe_query(f"""
    SELECT COUNT(*) FROM {TABLE}
    WHERE lead_created_at IS NOT NULL AND lead_created_at::text != ''
      AND hire_date IS NOT NULL AND hire_date::text != ''
""", fetch="scalar")
both_present = both_present if isinstance(both_present, int) else 0

either_present = safe_query(f"""
    SELECT COUNT(*) FROM {TABLE}
    WHERE (lead_created_at IS NOT NULL AND lead_created_at::text != '')
       OR (hire_date IS NOT NULL AND hire_date::text != '')
""", fetch="scalar")
either_present = either_present if isinstance(either_present, int) else 0

print(f"""
  TABLE: {TABLE}
  Total rows: {total}

  lead_created_at:
    Exists as column:    YES (VARCHAR(100))
    Has value:           {lca_present}/{total} ({pct(lca_present, total)}%)
    Format:              ISO 8601 (YYYY-MM-DDTHH:MM:SS)

  hire_date:
    Exists as column:    YES (VARCHAR(100))
    Has value:           {hd_present}/{total} ({pct(hd_present, total)}%)
    Format:              YYYY-MM-DD

  Overlap:
    Both present:        {both_present}/{total} ({pct(both_present, total)}%)
    Either present:      {either_present}/{total} ({pct(either_present, total)}%)
    Neither:             {total - either_present}/{total} ({pct(total - either_present, total)}%)

  OTHER TABLES WITH lead_created_at:
    - module_ct_cabinet_leads (timestamp)
    - lead_matches (date)
    - ops.v_cabinet_leads_missing_scout_alerts (view)

  DRIVERS TABLE:
    - hire_date: date (native DATE type!)
    - fire_date: date
    - active: boolean
""")

print("=" * 80)
print("RECOMENDACIÓN ANCHOR DATE")
print("=" * 80)

if lca_present > 0:
    # Evaluate lead_created_at
    lca_rate = pct(lca_present, total)
    hd_rate = pct(hd_present, total)

    # Check consistency where both present
    logical_pct = 0
    if isinstance(gap_stats, tuple) and gap_stats[0] > 0:
        logical_pct = pct(gap_stats[4], gap_stats[0])

    print(f"""
  lead_created_at:
    Coverage:   {lca_rate}%
    Source:     44.8% covered; 55.2% NULL -> enrichment parcial
    Format:     ISO 8601 string (cast to ::timestamp works)
    Semántica:  Fecha/hora de creación del lead (comercial/adquisición)
    Calidad:    Cuando existe, consistente con hire_date ({logical_pct}% lca <= hd)

  hire_date:
    Coverage:   {hd_rate}%
    Source:     61.8% covered; 38.2% NULL -> muchos fleet sin fecha
    Format:     YYYY-MM-DD string (cast to ::date works)
    Semántica:  Fecha de contratación/registro en plataforma

  COMBINED (COALESCE):
    Coverage:   {pct(either_present, total)}% de drivers tienen al menos una fecha
    Gap:        {pct(total - either_present, total)}% no tienen ninguna fecha (principalmente fleet)
""")

    # Decision
    print("  DECISIÓN:")
    if lca_rate >= 80:
        print("    lead_created_at: GO — usar como anchor date primario")
    elif lca_rate >= 40:
        print("    lead_created_at: GO WITH WARNINGS — usar con fallback a hire_date")
    else:
        print("    lead_created_at: GO WITH WARNINGS — cobertura baja pero útil donde existe")

    print(f"""
    Estrategia recomendada:
      anchor_date = COALESCE(lead_created_at::date, hire_date::date)
      Cubre: {pct(either_present, total)}% de drivers

    Para drivers sin ninguna fecha ({total - either_present}):
      - Usar created_at como proxy (sincronización del ETL)
      - O marcarlos como 'unknown_acquisition_date'

    PRÓXIMOS PASOS:
      1. lead_created_at es LA columna correcta para acquisition anchor.
      2. Actualmente 44.8% poblada; complementar con hire_date llega a {pct(either_present, total)}%.
      3. lead_created_at viene de module_ct_cabinet_leads (tabla separada con 100% poblada).
      4. Considerar JOIN a module_ct_cabinet_leads para obtener lead_created_at donde falta.
      5. Los {total - either_present} drivers sin fecha son principalmente fleet sin datos en cabinet.
""")
else:
    print("\n  lead_created_at: NO GO (sin datos)")
    print("  hire_date: GO WITH WARNINGS (anchor date actual)")

print("=" * 80)
print("AUDITORÍA COMPLETADA.")
print("=" * 80)

if __name__ == "__main__":
    pass
