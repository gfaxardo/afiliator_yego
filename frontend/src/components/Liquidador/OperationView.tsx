import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  getOperationSummary, getOperationFilters, getAffiliations, getAffiliationDetail,
  type OperationSummary, type OperationFilters, type AffiliationRow, type AffiliationsResponse
} from '../../api/scoutLiq'

// ── ESTADO: que logro el driver (OPERATIONAL ONLY) ──

function deriveLifecycle(row: AffiliationRow): string {
  if (parseInt(row.trips_8_14_count || '0') >= 5) return 'converted_5v14d'
  if (row.converted_5v_7d === 1) return 'converted_5v7d'
  if (row.attribution_status === 'attribution_ready' || parseInt(row.trips_0_7_count || '0') > 0) return 'activated'
  if (row.driver_id) return 'no_trips'
  return 'no_driver_id'
}

const LIFECYCLE_LABELS: Record<string, string> = {
  no_driver_id: 'SIN ID',
  no_trips: 'SIN VIAJES',
  activated: 'ACTIVADO',
  converted_5v7d: '5V/7D',
  converted_5v14d: '5V/14D',
}

const LIFECYCLE_COLORS: Record<string, string> = {
  no_driver_id: 'bg-red-100 text-red-700 border-red-300',
  no_trips: 'bg-gray-100 text-gray-500 border-gray-300',
  activated: 'bg-green-100 text-green-700 border-green-300',
  converted_5v7d: 'bg-blue-100 text-blue-700 border-blue-400',
  converted_5v14d: 'bg-purple-100 text-purple-700 border-purple-300',
}

const LIFECYCLE_ROW_BORDER: Record<string, string> = {
  converted_5v7d: 'border-l-4 border-l-blue-400',
  converted_5v14d: 'border-l-4 border-l-purple-400',
  activated: 'border-l-4 border-l-green-400',
}

// ── PAGO: genera dinero? ──

const PAYMENT_LABELS: Record<string, string> = {
  payable: 'PAGABLE',
  paid: 'PAGADO',
  no_payable: 'NO PAGABLE',
  revisar: 'REVISAR',
}

const PAYMENT_COLORS: Record<string, string> = {
  payable: 'bg-emerald-100 text-emerald-700',
  paid: 'bg-teal-100 text-teal-700',
  no_payable: 'bg-gray-100 text-gray-600',
  revisar: 'bg-orange-100 text-orange-700',
}

function parseBlockingDisplay(bd: string): string | null {
  const b = bd.toLowerCase()
  if (b.includes('ya registrado') || b.includes('ya pagado') || b.includes('already_paid')) return 'Ya pagado antes'
  if (b.includes('minimo') || b.includes('mínimo') || b.includes('min_aff') || b.includes('min_act')) return 'Mínimo scout no alcanzado'
  if (b.includes('sin activacion') || b.includes('sin activación')) return 'Sin activación'
  if (b.includes('duplicado') || b.includes('duplicate')) return 'Duplicado'
  if (b.includes('sin scout') || b.includes('no_scout') || b.includes('falta scout')) return 'Sin scout'
  if (b.includes('sin driver') || b.includes('no_driver')) return 'Sin driver ID'
  if (b.includes('scout') && (b.includes('min') || b.includes('no alcan'))) return 'Mínimo scout no alcanzado'
  return null
}

function derivePayment(row: AffiliationRow): { status: string; reason: string } {
  // 1. PAGADO — has a paid history record in this cut
  if (row.paid_history_id) return { status: 'paid', reason: '' }

  // 2. Sin driver ID operacional → NO PAGABLE
  if (!row.driver_id) return { status: 'no_payable', reason: 'Sin driver ID' }

  // 3. Sin activación (0 viajes, sin atribución) → NO PAGABLE
  if (parseInt(row.trips_0_7_count || '0') === 0 &&
      parseInt(row.trips_8_14_count || '0') === 0 &&
      row.attribution_status !== 'attribution_ready') {
    return { status: 'no_payable', reason: 'Sin activación' }
  }

  // 4. Manual review (cualquier campo) → REVISAR
  if (row.attribution_status === 'attribution_manual_review' ||
      row.payment_financial_status?.includes('manual_review') ||
      row.payment_blocking_status?.includes('manual_review')) {
    return { status: 'revisar', reason: 'Revisión manual' }
  }

  // 5. Parsear blocking_display ANTES que Sin monto (tiene prioridad)
  if (row.blocking_display && row.blocking_display !== 'N/A' &&
      row.blocking_display !== 'Pendiente' && row.blocking_display !== 'No bloquea') {
    const parsed = parseBlockingDisplay(row.blocking_display)
    if (parsed) return { status: 'no_payable', reason: parsed }
    if (row.blocking_display === 'Bloquea') return { status: 'no_payable', reason: 'Regla no alcanzada' }
    return { status: 'no_payable', reason: row.blocking_display }
  }

  // 5b. Blocking statuses not covered by blocking_display (backend maps them to 'Pendiente')
  const DIRECT_BLOCKING_MAP: Record<string, string> = {
    'payment_blocking_not_applicable_bad_status': 'Estado no elegible',
  }
  if (row.payment_blocking_status && DIRECT_BLOCKING_MAP[row.payment_blocking_status]) {
    return { status: 'no_payable', reason: DIRECT_BLOCKING_MAP[row.payment_blocking_status] }
  }

  // 6. Duplicado (payment_blocking sin manual_review)
  if (row.payment_blocking_status === 'payment_blocking_duplicate') {
    return { status: 'no_payable', reason: 'Duplicado' }
  }

  // 7. Sin monto (financial N/A) — solo si no hay causa mas especifica
  if (row.payment_financial_status === 'payment_financial_not_applicable_no_amount' ||
      row.payment_blocking_status === 'payment_blocking_not_applicable_no_amount') {
    return { status: 'no_payable', reason: 'Sin monto' }
  }

  // 8. PAGABLE — financial ready y sin bloqueo activo
  if (row.payment_financial_status === 'payment_financial_ready' &&
      (!row.payment_blocking_status || row.payment_blocking_status === 'payment_blocking_ready')) {
    return { status: 'payable', reason: '' }
  }

  // 9. Sin monto (fallback si no hay amount_paid ni causa especifica)
  if (!row.amount_paid && row.amount_paid !== 0) return { status: 'no_payable', reason: 'Sin monto' }

  // 10. Default
  return { status: 'no_payable', reason: 'Regla no alcanzada' }
}

// ── Progress Icons (operational flow only, no payment state in steps) ──

function ProgressIcons({ row }: { row: AffiliationRow }) {
  const hasId = !!row.driver_id
  const has1Trip = parseInt(row.trips_0_7_count || '0') > 0
  const conv7 = row.converted_5v_7d === 1
  const conv14 = parseInt(row.trips_8_14_count || '0') >= 5
  const payable = row.payment_financial_status === 'payment_financial_ready' &&
    (!row.payment_blocking_status || row.payment_blocking_status === 'payment_blocking_ready')
  const paid = !!row.paid_history_id
  const noPayable = !paid && !payable && !!(
    row.payment_blocking_status && row.payment_blocking_status !== 'payment_blocking_ready'
  )

  const steps = [
    { key: 'id', icon: 'ID', label: 'Driver ID', active: hasId },
    { key: '1v', icon: '1', label: '1+ viaje (7d)', active: has1Trip },
    { key: '5v7d', icon: '7', label: '5 viajes 7d', active: conv7 },
    { key: '5v14d', icon: '14', label: '5 viajes 14d', active: conv14 },
    { key: 'pay', icon: '$', label: 'Pagable', active: payable && !paid },
    { key: 'done', icon: '\u2713', label: paid ? 'Pagado' : 'Pendiente', active: paid },
  ]

  return (
    <div className="flex items-center gap-1">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1">
          <span
            className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold border ${
              s.active
                ? 'bg-green-500 text-white border-green-500'
                : (s.key === 'done' && noPayable)
                  ? 'bg-gray-200 text-gray-400 border-gray-300'
                  : 'bg-white text-gray-300 border-gray-200'
            }`}
            title={s.label}
          >
            {s.icon}
          </span>
          {i < steps.length - 1 && (
            <span className={`w-4 h-0.5 rounded ${s.active ? 'bg-green-400' : 'bg-gray-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Badges ──

function LifecycleBadge({ status }: { status: string }) {
  const color = LIFECYCLE_COLORS[status] || 'bg-gray-100 text-gray-500 border-gray-300'
  const label = LIFECYCLE_LABELS[status] || status
  return (
    <span className={`px-2.5 py-1 rounded text-xs font-bold border whitespace-nowrap ${color}`}>
      {label}
    </span>
  )
}

function PaymentBadge({ status }: { status: string }) {
  const color = PAYMENT_COLORS[status] || 'bg-gray-100 text-gray-500'
  const label = PAYMENT_LABELS[status] || status
  return (
    <span className={`px-2.5 py-1 rounded text-xs font-bold whitespace-nowrap ${color}`}>
      {label}
    </span>
  )
}

// ── KPI Card ──

function KpiCard({ label, value, color = 'text-gray-700', highlight, muted }: {
  label: string; value: string | number; color?: string; highlight?: boolean; muted?: boolean
}) {
  return (
    <div className={`rounded border px-3 py-1.5 text-center ${highlight ? 'border-blue-300 bg-blue-50/50' : 'border-gray-200 bg-white'} ${muted ? 'opacity-50' : ''}`}>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-[11px] text-gray-400 uppercase tracking-wider leading-tight">{label}</div>
    </div>
  )
}

// ── Motivo renderer ──

const MOTIVO_COLORS: Record<string, string> = {
  'Sin driver ID': 'text-red-600 font-medium',
  'Sin activación': 'text-red-600 font-medium',
  'Duplicado': 'text-red-600 font-medium',
  'Sin scout': 'text-red-600 font-medium',
  'Revisión manual': 'text-orange-600 font-medium',
  'Mínimo scout no alcanzado': 'text-orange-600 font-medium',
  'Ya pagado antes': 'text-teal-600 font-medium',
  'Estado no elegible': 'text-red-600 font-medium',
  'Sin monto': 'text-gray-500',
  'Regla no alcanzada': 'text-gray-500',
}

// ── Main Component ──

export default function OperationView() {
  const [summary, setSummary] = useState<OperationSummary | null>(null)
  const [filters, setFilters] = useState<OperationFilters | null>(null)
  const [data, setData] = useState<AffiliationsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [kpiLoading, setKpiLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [weekIso, setWeekIso] = useState('')
  const [scoutId, setScoutId] = useState('')
  const [origin, setOrigin] = useState('')
  const [alertLevel, setAlertLevel] = useState('')
  const [onlyManualReview, setOnlyManualReview] = useState(false)
  const [onlyWithoutDriver, setOnlyWithoutDriver] = useState(false)
  const [onlyPaid, setOnlyPaid] = useState(false)
  const [lifecycleFilter, setLifecycleFilter] = useState('')
  const [paymentFilter, setPaymentFilter] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const f = await getOperationFilters()
        setFilters(f)
        setWeekIso(f.default_week_iso || '')
      } catch (e: any) {
        setError('Error al cargar filtros')
      }
    })()
  }, [])

  const loadSummary = useCallback(async () => {
    setKpiLoading(true)
    try {
      const p: Record<string, any> = {}
      if (weekIso) p.week_iso = weekIso
      if (scoutId) p.scout_id = scoutId
      if (origin) p.origin = origin
      if (onlyManualReview) p.only_manual_review = true
      if (onlyPaid) p.only_paid = true
      if (onlyWithoutDriver) p.only_without_driver = true
      if (lifecycleFilter) p.lifecycle = lifecycleFilter
      if (paymentFilter) p.payment_status = paymentFilter
      setSummary(await getOperationSummary(Object.keys(p).length ? p : undefined as any))
    } catch { /* ignore */ }
    finally { setKpiLoading(false) }
  }, [weekIso, scoutId, origin, onlyManualReview, onlyPaid, onlyWithoutDriver, lifecycleFilter, paymentFilter])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, any> = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
      if (weekIso) params.week_iso = weekIso
      if (scoutId) params.scout_id = scoutId
      if (origin) params.origin = origin
      if (alertLevel) params.alert_level = alertLevel
      if (onlyManualReview) params.only_manual_review = true
      if (onlyWithoutDriver) params.only_without_driver = true
      if (onlyPaid) params.only_paid = true
      if (lifecycleFilter) params.lifecycle = lifecycleFilter
      if (paymentFilter) params.payment_status = paymentFilter
      const d = await getAffiliations(params)
      setData(d)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Error')
    } finally {
      setLoading(false)
    }
  }, [weekIso, scoutId, origin, alertLevel, onlyManualReview, onlyWithoutDriver, onlyPaid, lifecycleFilter, paymentFilter, page])

  useEffect(() => { loadData(); loadSummary() }, [loadData, loadSummary])

  const sortedItems = useMemo(() => {
    if (!data) return []
    const items = [...data.items]
    items.sort((a, b) => {
      const w = (b.iso_week_label || '').localeCompare(a.iso_week_label || '')
      if (w !== 0) return w
      const h = (b.hire_date || '').localeCompare(a.hire_date || '')
      return h
    })
    return items
  }, [data])

  const displayItems = useMemo(() => {
    let items = sortedItems
    if (lifecycleFilter) items = items.filter(row => deriveLifecycle(row) === lifecycleFilter)
    if (paymentFilter) items = items.filter(row => derivePayment(row).status === paymentFilter)
    return items
  }, [sortedItems, lifecycleFilter, paymentFilter])

  async function openDetail(rowId: number) {
    setSelectedId(rowId)
    setDetailLoading(true)
    try { setDetail(await getAffiliationDetail(rowId)) }
    catch { setDetail(null) }
    finally { setDetailLoading(false) }
  }

  function clearFilters() {
    setWeekIso(filters?.default_week_iso || '')
    setScoutId(''); setOrigin(''); setAlertLevel('')
    setOnlyManualReview(false); setOnlyWithoutDriver(false); setOnlyPaid(false)
    setLifecycleFilter(''); setPaymentFilter('')
    setPage(0)
  }

  function applyPreset(preset: string) {
    setWeekIso(filters?.default_week_iso || '')
    setScoutId(''); setOrigin(''); setAlertLevel('')
    setOnlyManualReview(false); setOnlyWithoutDriver(false); setOnlyPaid(false)
    setLifecycleFilter(''); setPaymentFilter('')

    switch (preset) {
      case 'no_driver_id': setOnlyWithoutDriver(true); break
      case 'no_trips': setLifecycleFilter('no_trips'); break
      case 'activated': setLifecycleFilter('activated'); break
      case 'converted_5v7d': setLifecycleFilter('converted_5v7d'); break
      case 'converted_5v14d': setLifecycleFilter('converted_5v14d'); break
      case 'payable': setPaymentFilter('payable'); break
      case 'paid': setOnlyPaid(true); break
      case 'no_payable': setPaymentFilter('no_payable'); break
      case 'revisar': setPaymentFilter('revisar'); break
      case 'manual_review': setOnlyManualReview(true); break
    }
    setPage(0)
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const noDataCurrentWeek = filters && !filters.has_data_for_current_week && weekIso === filters.current_iso_week && data && data.total === 0
  const activePreset =
    (onlyManualReview && 'manual_review') ||
    (onlyWithoutDriver && 'no_driver_id') ||
    (onlyPaid && 'paid') ||
    (lifecycleFilter || '') ||
    (paymentFilter || '')

  return (
    <div className="flex flex-col h-full" style={{ minHeight: 'calc(100vh - 140px)' }}>
      <div className="space-y-2 flex-shrink-0">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-800">Operacion de Afiliaciones</h2>
            {summary && (
              <p className="text-xs text-gray-400 mt-0.5">
                {summary.scope_type === 'selected_week'
                  ? `Resumen de ${summary.scope_label}`
                  : 'Resumen de todas las semanas'}
                {data ? ` \u00b7 ${data.total} registros` : ''}
              </p>
            )}
          </div>
          {filters && !filters.has_data_for_current_week && (
            <button
              onClick={() => { setWeekIso(filters.latest_iso_week_with_data || weekIso); setPage(0) }}
              className="text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-3 py-1 rounded border border-blue-200"
            >
              Ver ultima semana con data: {filters.latest_iso_week_with_data_label}
            </button>
          )}
        </div>

        {/* KPIs — Primary row: funnel ejecutivo */}
        {summary && (
          <div className="grid grid-cols-7 gap-1.5">
            <KpiCard label="Afiliados" value={summary.total_affiliations} />
            <KpiCard label="Activados" value={((summary as any).total_activated ?? summary.total_with_driver)} color="text-green-600" />
            <KpiCard label="5V / 7D" value={((summary as any).total_5v7d ?? (summary as any).total_converted_5v7d ?? '—')} color="text-blue-600" highlight />
            <KpiCard label="Conversion" value={((summary as any).total_converted_5v7d && summary.total_affiliations ? Math.round((summary as any).total_converted_5v7d / summary.total_affiliations * 100) + '%' : '—')} color="text-blue-500" />
            <KpiCard label="Pagables" value={((summary as any).total_payable ?? '—')} color="text-emerald-600" />
            <KpiCard label="Pagados" value={summary.total_paid_history} color="text-teal-600" />
            <KpiCard label="Monto" value={`S/ ${summary.total_paid_amount.toLocaleString()}`} color="text-gray-700" />
          </div>
        )}

        {/* KPIs — Secondary row */}
        {summary && (
          <div className="grid grid-cols-4 gap-1.5">
            <KpiCard label="Sin driver" value={summary.total_without_driver} color="text-yellow-600" muted />
            <KpiCard label="Bloqueos" value={summary.total_blocks_future} color="text-purple-600" muted />
            <KpiCard label="Manual review" value={summary.total_manual_review} color="text-orange-600" muted />
            <KpiCard label="Criticas" value={summary.total_alerts_critical} color={summary.total_alerts_critical > 0 ? 'text-red-600' : 'text-green-600'} muted />
          </div>
        )}

        {/* Empty state */}
        {noDataCurrentWeek && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2 text-sm text-yellow-700 flex items-center justify-between">
            <span>No hay afiliaciones en la semana actual ({filters?.current_iso_week_label}).</span>
            <button
              onClick={() => { setWeekIso(filters?.latest_iso_week_with_data || ''); setPage(0) }}
              className="text-blue-600 hover:text-blue-800 font-medium underline text-xs"
            >
              Ir a {filters?.latest_iso_week_with_data_label}
            </button>
          </div>
        )}

        {/* Presets — Modos operacionales */}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-xs text-gray-400 uppercase tracking-wider mr-1">Modo:</span>
          {[
            { key: 'no_driver_id', label: 'Sin ID', color: 'border-red-300 text-red-600 hover:bg-red-50' },
            { key: 'no_trips', label: 'Sin viajes', color: 'border-gray-300 text-gray-500 hover:bg-gray-50' },
            { key: 'activated', label: 'Activados', color: 'border-green-300 text-green-600 hover:bg-green-50' },
            { key: 'converted_5v7d', label: '5V / 7D', color: 'border-blue-300 text-blue-700 hover:bg-blue-50' },
            { key: 'converted_5v14d', label: '5V / 14D', color: 'border-purple-300 text-purple-600 hover:bg-purple-50' },
            { key: 'payable', label: 'Pagables', color: 'border-emerald-300 text-emerald-700 hover:bg-emerald-50' },
            { key: 'paid', label: 'Pagados', color: 'border-teal-300 text-teal-700 hover:bg-teal-50' },
            { key: 'no_payable', label: 'No pagables', color: 'border-gray-300 text-gray-600 hover:bg-gray-50' },
            { key: 'revisar', label: 'Revisar', color: 'border-orange-300 text-orange-600 hover:bg-orange-50' },
            { key: 'manual_review', label: 'Manual review', color: 'border-yellow-300 text-yellow-600 hover:bg-yellow-50' },
          ].map(p => (
            <button
              key={p.key}
              onClick={() => applyPreset(p.key)}
              className={`px-2.5 py-1 text-xs font-semibold border rounded-full transition-all ${
                activePreset === p.key
                  ? `${p.color} bg-opacity-15 shadow-sm`
                  : `bg-white ${p.color}`
              }`}
            >
              {p.label}
            </button>
          ))}
          {activePreset && (
            <button onClick={clearFilters} className="text-xs text-blue-600 hover:text-blue-800 ml-2 underline">
              Limpiar modo
            </button>
          )}
        </div>

        {/* Filters row */}
        {filters && (
          <div className="flex flex-wrap gap-2 items-center bg-white rounded-lg border border-gray-200 px-3 py-1.5">
            <select value={weekIso} onChange={(e) => { setWeekIso(e.target.value); setPage(0) }}
              className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
              <option value="">Todas las semanas</option>
              {filters.weeks.map((w) => (
                <option key={w.label} value={`${w.year}-W${String(w.week).padStart(2, '0')}`}>{w.label}</option>
              ))}
            </select>

            <select value={scoutId} onChange={(e) => { setScoutId(e.target.value); setPage(0) }}
              className="border border-gray-200 rounded px-2 py-1 text-xs bg-white max-w-[180px]">
              <option value="">Todos los scouts</option>
              {filters.scouts.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>

            <select value={origin} onChange={(e) => { setOrigin(e.target.value); setPage(0) }}
              className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
              <option value="">Todos los origenes</option>
              {filters.origins.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>

            <select value={alertLevel} onChange={(e) => { setAlertLevel(e.target.value); setPage(0) }}
              className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
              <option value="">Todas las alertas</option>
              {filters.alert_types.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>

            <button onClick={clearFilters} className="text-xs text-blue-600 hover:text-blue-800 ml-auto">
              Limpiar filtros
            </button>
          </div>
        )}

        {/* Error */}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-2 text-sm">{error}</div>}
      </div>

      {/* Grid */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden flex-1 mt-2 min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">Cargando...</div>
        ) : data && data.items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">Sin resultados para los filtros actuales</div>
        ) : data ? (
          <div className="flex flex-col h-full">
            <div className="overflow-x-auto flex-1">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    <th className="px-3 py-2 whitespace-nowrap">Semana ISO</th>
                    <th className="px-3 py-2 whitespace-nowrap">Hire Date</th>
                    <th className="px-3 py-2">Driver</th>
                    <th className="px-3 py-2">Origen</th>
                    <th className="px-3 py-2">Scout</th>
                    <th className="px-3 py-2 whitespace-nowrap">Progreso</th>
                    <th className="px-3 py-2 text-center whitespace-nowrap">Viajes 7D</th>
                    <th className="px-3 py-2 text-center whitespace-nowrap">Viajes 14D</th>
                    <th className="px-3 py-2">Estado</th>
                    <th className="px-3 py-2">Pago</th>
                    <th className="px-3 py-2">Motivo</th>
                    <th className="px-3 py-2 text-right whitespace-nowrap">Monto</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {displayItems.map((row: AffiliationRow) => {
                    const lifecycle = deriveLifecycle(row)
                    const payment = derivePayment(row)
                    const rowBorder = LIFECYCLE_ROW_BORDER[lifecycle] || ''
                    const motivoColor = MOTIVO_COLORS[payment.reason] || 'text-gray-500'
                    const trip7d = parseInt(row.trips_0_7_count || '0')
                    const trip14d = parseInt(row.trips_8_14_count || '0')
                    return (
                      <tr key={row.row_id} onClick={() => openDetail(row.row_id)}
                        className={`hover:bg-blue-50/40 cursor-pointer transition-colors ${rowBorder}`}>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <div className="font-mono text-xs font-semibold text-gray-700">{row.iso_week_label}</div>
                          {row.iso_week_start && <div className="text-[11px] text-gray-400">{row.iso_week_start} — {row.iso_week_end}</div>}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap font-mono text-xs text-gray-600">
                          {row.hire_date ? row.hire_date.slice(0, 10) : '-'}
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <div className="font-medium text-gray-800 truncate text-xs" title={row.driver_display_name}>
                            {row.driver_display_name || '-'}
                          </div>
                          <div className="text-[11px] text-gray-400 truncate font-mono" title={row.driver_id || ''}>
                            {row.driver_id ? row.driver_id.slice(0, 14) : '-'}
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-600">{row.origin || '-'}</td>
                        <td className="px-3 py-2 max-w-[140px] truncate text-xs" title={row.scout_name || ''}>
                          {row.scout_name || '-'}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <ProgressIcons row={row} />
                        </td>
                        <td className={`px-3 py-2 text-center font-mono text-sm font-bold ${
                          trip7d >= 5 ? 'text-blue-700 bg-blue-50 rounded' : 'text-gray-500'
                        }`}>
                          {row.trips_0_7_count || '0'}
                        </td>
                        <td className={`px-3 py-2 text-center font-mono text-sm ${
                          trip14d >= 5 ? 'text-purple-700 font-bold' : 'text-gray-500'
                        }`}>
                          {row.trips_8_14_count || '0'}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <LifecycleBadge status={lifecycle} />
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <PaymentBadge status={payment.status} />
                        </td>
                        <td className={`px-3 py-2 text-xs max-w-[160px] truncate ${motivoColor}`} title={payment.reason || ''}>
                          {payment.reason || '\u2014'}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-sm whitespace-nowrap">
                          {row.amount_paid
                            ? <span className={`font-bold ${payment.status === 'paid' ? 'text-teal-700' : payment.status === 'payable' ? 'text-emerald-700' : 'text-gray-700'}`}>S/ {row.amount_paid.toFixed(0)}</span>
                            : <span className="text-gray-300">-</span>
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs flex-shrink-0">
                <span className="text-gray-400">Pag {page + 1} de {totalPages} ({data.total} registros)</span>
                <div className="flex gap-1.5">
                  <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                    className="px-3 py-1 border border-gray-200 rounded text-xs disabled:opacity-30 hover:bg-gray-100">Anterior</button>
                  <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                    className="px-3 py-1 border border-gray-200 rounded text-xs disabled:opacity-30 hover:bg-gray-100">Siguiente</button>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {/* Detail Drawer */}
      {selectedId && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/20" onClick={() => setSelectedId(null)} />
          <div className="relative w-[520px] bg-white shadow-xl border-l border-gray-200 overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-2.5 flex items-center justify-between z-10">
              <h3 className="font-semibold text-gray-800 text-sm">Detalle #{selectedId}</h3>
              <button onClick={() => setSelectedId(null)} className="text-gray-400 hover:text-gray-600 text-lg">&times;</button>
            </div>
            <div className="p-4 space-y-3">
              {detailLoading ? <div className="text-center text-gray-400 py-8 text-sm">Cargando...</div> : detail ? (
                <>
                  <Section title="Afiliacion">
                    <F label="Row" value={detail.row_id} />
                    <F label="Batch" value={detail.batch_id} />
                    <F label="Sheet / Row" value={`${detail.source_sheet || '-'} / ${detail.source_row || '-'}`} />
                    <F label="ISO Week" value={detail.iso_week_label_full || '-'} />
                    <F label="Hire Date" value={detail.hire_date || detail.source_hire_date || '-'} />
                    <F label="Origen" value={detail.origin_raw || detail.source_origin || '-'} />
                  </Section>
                  <Section title="Driver">
                    <F label="Nombre" value={detail.driver_display_name || 'Sin nombre'} bold />
                    <F label="Driver ID" value={detail.driver_id_resolved || 'No resuelto'} mono />
                    <F label="Licencia" value={detail.driver_license_raw || '-'} mono />
                    <F label="Nombre raw" value={detail.driver_name_raw || '-'} />
                  </Section>
                  <Section title="Scout">
                    <F label="Scout (raw)" value={detail.scout_name_raw || '-'} />
                    <F label="Scout (resuelto)" value={detail.scout_resolved_name || 'No resuelto'} />
                    <F label="Supervisor" value={detail.supervisor_raw || '-'} />
                    <F label="Sup. resuelto" value={detail.supervisor_resolved_name || '-'} />
                  </Section>
                  <Section title="Pago">
                    <F label="Monto" value={detail.amount_paid ? `S/ ${detail.amount_paid}` : '-'} bold />
                    <F label="Regla" value={detail.payment_rule_raw || '-'} />
                    <F label="Estado raw" value={detail.estado_pago_raw || '-'} />
                    <F label="Esquema" value={detail.payment_scheme_raw || '-'} />
                    <F label="Hito" value={detail.milestone_raw || '-'} />
                  </Section>
                  <Section title="Paid History">
                    <F label="PH ID" value={detail.paid_history_id || 'No creado'} />
                    <F label="PH Amount" value={detail.ph_amount_paid ? `S/ ${detail.ph_amount_paid}` : '-'} />
                    <F label="Blocks Future" value={detail.ph_blocks_future === true ? 'Si' : detail.ph_blocks_future === false ? 'No' : '-'} />
                    <F label="Resolution" value={detail.ph_resolution_status || '-'} />
                    <F label="Hash" value={detail.ph_unique_hash ? detail.ph_unique_hash.slice(0, 16) + '...' : '-'} mono />
                  </Section>
                  <Section title="Clasificacion">
                    <F label="Atribucion" value={detail.attribution_status || '-'} />
                    <F label="Attr. Reason" value={detail.attribution_reason || '-'} />
                    <F label="Pago Financiero" value={detail.payment_financial_status || '-'} />
                    <F label="Pago Blocking" value={detail.payment_blocking_status || '-'} />
                    <F label="Blocking Display" value={detail.blocking_display || '-'} />
                    <F label="Blocks Future" value={detail.blocks_future_payment === true ? 'Si' : detail.blocks_future_payment === false ? 'No' : '-'} />
                    <F label="Final Status" value={detail.final_status || '-'} />
                  </Section>
                  <Section title="Alertas">
                    <F label="Alert Level" value={detail.alert_level || '-'} />
                    <F label="Alert Codes" value={detail.alert_codes ? detail.alert_codes.join(', ') : '-'} />
                  </Section>
                </>
              ) : <div className="text-center text-gray-400 py-8 text-sm">Sin datos</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-3 py-1 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
      <div className="divide-y divide-gray-100">{children}</div>
    </div>
  )
}

function F({ label, value, mono, bold }: { label: string; value: string | number | null | undefined; mono?: boolean; bold?: boolean }) {
  return (
    <div className="flex items-center px-3 py-1 text-xs">
      <span className="text-gray-400 w-32 shrink-0">{label}</span>
      <span className={`text-gray-700 truncate ${mono ? 'font-mono' : ''} ${bold ? 'font-medium' : ''}`}>
        {value !== null && value !== undefined ? String(value) : '-'}
      </span>
    </div>
  )
}
