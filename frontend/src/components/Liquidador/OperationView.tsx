import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  getCanonicalOperation, getOperationDiagnostic,
  type CanonicalDriver, type CanonicalSnapshotResponse,
  type CanonicalFreshness, type OperationDiagnosticResponse,
  resolvePaymentScheme, type ResolvedScheme,
} from '../../api/scoutLiq'

// ── LIFECYCLE desde datos canonicos ──

const LIFECYCLE_LABELS: Record<string, string> = {
  no_driver_id: 'SIN ID',
  no_trips: 'SIN VIAJES',
  sin_scout: 'SIN SCOUT',
  activated: 'ACTIVADO',
  converted_5v7d: '5V/7D',
  converted_5v14d: '5V/14D',
}

const LIFECYCLE_COLORS: Record<string, string> = {
  no_driver_id: 'bg-red-100 text-red-700 border-red-300',
  no_trips: 'bg-gray-100 text-gray-500 border-gray-300',
  sin_scout: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  activated: 'bg-green-100 text-green-700 border-green-300',
  converted_5v7d: 'bg-blue-100 text-blue-700 border-blue-400',
  converted_5v14d: 'bg-purple-100 text-purple-700 border-purple-300',
}

const LIFECYCLE_ROW_BORDER: Record<string, string> = {
  sin_scout: 'border-l-4 border-l-yellow-400',
  converted_5v7d: 'border-l-4 border-l-blue-400',
  converted_5v14d: 'border-l-4 border-l-purple-400',
  activated: 'border-l-4 border-l-green-400',
}

// ── TRACE STATUS translations ──

const RULE_LABELS: Record<string, string> = {
  '1V7D': '1 viaje en 7 días',
  '5V7D': '5 viajes en 7 días',
  '50V30D': '50 viajes en 30 días',
}

const FORMULA_LABELS: Record<string, string> = {
  'ACTIVATED_X_TIER': 'Activados × Tier',
  'QUALITY_X_FIXED': 'Calidad × Fijo',
}

const TRACE_STATUS_LABELS: Record<string, string> = {
  blocked_unassigned: 'Sin scout asignado',
  no_activation: 'Sin activación',
  blocked_min_activated: 'Mínimo de activados no alcanzado',
  blocked_no_tier: 'No alcanzó tier',
  payable_scout_tier: 'Pagable: scout alcanzó tier',
  paid_confirmed: 'Ya pagado',
  ok: 'OK',
}

const TRACE_STATUS_COLORS: Record<string, string> = {
  blocked_unassigned: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  no_activation: 'bg-red-100 text-red-700 border-red-200',
  blocked_min_activated: 'bg-orange-100 text-orange-700 border-orange-200',
  blocked_no_tier: 'bg-orange-100 text-orange-700 border-orange-200',
  payable_scout_tier: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  paid_confirmed: 'bg-teal-100 text-teal-700 border-teal-200',
  ok: 'bg-gray-100 text-gray-600 border-gray-200',
}

const REASON_LABELS: Record<string, string> = {
  no_scout: 'Sin scout',
  no_activation: 'Sin activación',
  already_paid: 'Ya pagado',
  min_activated_not_reached: 'Mínimo de activados no alcanzado',
  tier_not_reached: 'No alcanzó tier',
  manual_review: 'Revisión manual',
  ok: 'Pagable',
}

// ── Compact badges ──

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span className={`inline-flex items-center justify-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${
      value ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-50 text-gray-300 border-gray-200'
    }`}>
      {value ? 'Sí' : 'No'}
    </span>
  )
}

function TraceStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-gray-300 text-[10px]">—</span>
  const label = TRACE_STATUS_LABELS[status] || status
  const color = TRACE_STATUS_COLORS[status] || 'bg-gray-100 text-gray-500 border-gray-200'
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border whitespace-nowrap ${color}`}>
      {label}
    </span>
  )
}

function buildEvidence(row: CanonicalDriver): string {
  if (row.payment_status === 'paid') {
    return `Ya pagado (${row.payment_origin || 'histórico'})`
  }
  if (row.scout_id == null || row.attribution_status === 'unassigned') {
    return 'Sin scout asignado'
  }
  if (!row.activated_flag) {
    return 'Sin activación (0 viajes 7D)'
  }
  const base = row.scout_activated_base
  const quality = row.scout_quality_5v7d
  const rate = (row.scout_conversion_rate_5v7d * 100).toFixed(0)
  const amount = row.scout_tier_amount
  if (amount > 0) {
    return `Scout ${quality}/${base} = ${rate}% \u2192 S/${amount.toFixed(0)}`
  }
  if (row.reason === 'min_activated_not_reached') {
    return `Scout ${quality}/${base} = ${rate}% — mínimo no alcanzado (base: ${base})`
  }
  return `Scout ${quality}/${base} = ${rate}% — sin tier`
}

function buildRegla(row: CanonicalDriver): string {
  if (row.scout_tier_amount > 0) {
    return `Tier S/${row.scout_tier_amount.toFixed(0)}`
  }
  return '—'
}

function deriveLifecycle(row: CanonicalDriver): string {
  if (row.attribution_status === 'unassigned') return 'sin_scout'
  if (row.converted_5v14d) return 'converted_5v14d'
  if (row.converted_5v7d) return 'converted_5v7d'
  if (row.activated_flag) return 'activated'
  if (row.driver_id) return 'no_trips'
  return 'no_driver_id'
}

// ── PAGO desde datos canonicos ──

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

const PAYMENT_ORIGIN_LABELS: Record<string, string> = {
  cutoff: 'Corte',
  historical_upload: 'Historico',
  manual: 'Manual',
  none: 'Ninguno',
}

function derivePayment(row: CanonicalDriver): { status: string; reason: string; originLabel: string } {
  const origin = row.payment_origin || 'none'
  const originLabel = PAYMENT_ORIGIN_LABELS[origin] || origin

  if (row.payment_status === 'paid') {
    return { status: 'paid', reason: row.reason === 'already_paid' ? 'Ya pagado' : originLabel, originLabel }
  }
  if (row.payment_status === 'payable') {
    return { status: 'payable', reason: 'Pagable: activó y scout alcanzó tier', originLabel }
  }
  const translated = REASON_LABELS[row.reason] || row.reason
  if (row.reason === 'no_scout') return { status: 'no_payable', reason: translated, originLabel }
  if (row.reason === 'no_activation') return { status: 'no_payable', reason: translated, originLabel }
  if (row.reason === 'min_activated_not_reached') return { status: 'no_payable', reason: translated, originLabel }
  if (row.reason === 'tier_not_reached') return { status: 'no_payable', reason: translated, originLabel }
  if (row.reason === 'manual_review') return { status: 'revisar', reason: translated, originLabel }
  return { status: 'no_payable', reason: translated || 'Sin regla', originLabel }
}

// ── Progress Icons ──

function ProgressIcons({ row }: { row: CanonicalDriver }) {
  const hasId = !!row.driver_id
  const has1Trip = row.activated_flag
  const conv7 = row.converted_5v7d
  const conv14 = row.converted_5v14d
  const isPaid = row.payment_status === 'paid'
  const isPayable = row.payment_status === 'payable'

  const steps = [
    { key: 'id', icon: 'ID', label: 'Driver ID', active: hasId },
    { key: '1v', icon: '1', label: '1+ viaje (7d)', active: has1Trip },
    { key: '5v7d', icon: '7', label: '5 viajes 7d', active: conv7 },
    { key: '5v14d', icon: '14', label: '5 viajes 14d', active: conv14 },
    { key: 'pay', icon: '$', label: 'Pagable', active: isPayable && !isPaid },
    { key: 'done', icon: '\u2713', label: isPaid ? 'Pagado' : 'Pendiente', active: isPaid },
  ]

  return (
    <div className="flex items-center gap-1">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1">
          <span
            className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold border ${
              s.active
                ? 'bg-green-500 text-white border-green-500'
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

function PaymentBadge({ status, originLabel }: { status: string; originLabel?: string }) {
  const color = PAYMENT_COLORS[status] || 'bg-gray-100 text-gray-500'
  const label = PAYMENT_LABELS[status] || status
  return (
    <div className="flex flex-col gap-0.5">
      <span className={`px-2.5 py-0.5 rounded text-xs font-bold whitespace-nowrap ${color}`}>
        {label}
      </span>
      {originLabel && originLabel !== 'Ninguno' && (
        <span className="text-[10px] text-gray-400 leading-tight">{originLabel}</span>
      )}
    </div>
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

// ── Frescura Banner ──

function FreshnessBanner({ freshness }: { freshness: CanonicalFreshness | null }) {
  if (!freshness) return null
  const statusColor =
    freshness.freshness_status === 'ok' ? 'bg-green-50 border-green-200 text-green-700' :
    freshness.freshness_status === 'warning' ? 'bg-yellow-50 border-yellow-200 text-yellow-700' :
    'bg-red-50 border-red-200 text-red-700'
  return (
    <div className={`rounded border px-3 py-1.5 text-xs flex items-center gap-3 ${statusColor}`}>
      <span className="font-semibold">Fuente: module_ct_cabinet_drivers</span>
      <span>·</span>
      <span>Ultimo hire_date: {freshness.source_max_hire_date || '—'}</span>
      <span>·</span>
      <span>Atraso: {freshness.data_lag_days != null ? `${freshness.data_lag_days} dias` : '—'}</span>
      <span>·</span>
      <span className="uppercase font-bold">{freshness.freshness_status}</span>
    </div>
  )
}

// ── Motivo renderer ──

const MOTIVO_COLORS: Record<string, string> = {
  'Sin scout': 'text-yellow-600 font-medium',
  'Sin activación': 'text-red-600 font-medium',
  'Ya pagado': 'text-teal-600 font-medium',
  'Mínimo de activados no alcanzado': 'text-orange-600 font-medium',
  'No alcanzó tier': 'text-amber-600 font-medium',
  'Revisión manual': 'text-orange-600 font-medium',
  'Historico': 'text-teal-600 font-medium',
  'Corte': 'text-blue-600 font-medium',
  'Pagable: activó y scout alcanzó tier': 'text-emerald-600 font-medium',
}

// ── Main Component ──

export default function OperationView() {
  const [data, setData] = useState<CanonicalSnapshotResponse | null>(null)
  const [diagnostic, setDiagnostic] = useState<OperationDiagnosticResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [origin, setOrigin] = useState('')
  const [lifecycleFilter, setLifecycleFilter] = useState('')
  const [paymentFilter, setPaymentFilter] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  const [selectedRow, setSelectedRow] = useState<CanonicalDriver | null>(null)
  const [resolvedScheme, setResolvedScheme] = useState<ResolvedScheme | null>(null)

  // Resolve scheme when driver is selected
  useEffect(() => {
    if (!selectedRow?.iso_week_label) { setResolvedScheme(null); return }
    const cohort = selectedRow.iso_week || ''
    if (!cohort) { setResolvedScheme(null); return }
    // Try cabinet first, fallback to fleet
    resolvePaymentScheme(cohort, 'cabinet').then(setResolvedScheme).catch(() => {
      resolvePaymentScheme(cohort, 'fleet').then(setResolvedScheme).catch(() => setResolvedScheme(null))
    })
  }, [selectedRow])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, any> = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
      if (origin) params.origin = origin
      if (lifecycleFilter) {
        if (lifecycleFilter === 'sin_scout') params.attribution_status = 'unassigned'
        else if (lifecycleFilter === 'payable') params.payment_status = 'payable'
        else if (lifecycleFilter === 'paid') params.payment_status = 'paid'
        else if (lifecycleFilter === 'no_payable') params.payment_status = 'not_payable'
      }
      if (paymentFilter) {
        if (paymentFilter === 'paid') params.payment_status = 'paid'
        else if (paymentFilter === 'payable') params.payment_status = 'payable'
        else if (paymentFilter === 'no_payable') params.payment_status = 'not_payable'
      }
      const [d, diag] = await Promise.all([
        getCanonicalOperation(params),
        getOperationDiagnostic(),
      ])
      setData(d)
      setDiagnostic(diag)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Error')
    } finally {
      setLoading(false)
    }
  }, [origin, lifecycleFilter, paymentFilter, page])

  useEffect(() => { loadData() }, [loadData])

  const displayItems = useMemo(() => {
    if (!data) return []
    let items = [...data.items]
    if (lifecycleFilter && lifecycleFilter !== 'sin_scout' && lifecycleFilter !== 'payable' && lifecycleFilter !== 'paid' && lifecycleFilter !== 'no_payable') {
      items = items.filter(row => deriveLifecycle(row) === lifecycleFilter)
    }
    if (paymentFilter && lifecycleFilter !== 'payable' && lifecycleFilter !== 'paid' && lifecycleFilter !== 'no_payable') {
      items = items.filter(row => derivePayment(row).status === paymentFilter)
    }
    return items
  }, [data, lifecycleFilter, paymentFilter])

  // Compute summary KPIs from diagnostic + snapshot
  const kpis = useMemo(() => ({
    total: data?.total ?? 0,
    withScout: diagnostic?.base_counts.drivers_with_scout ?? 0,
    withoutScout: diagnostic?.base_counts.drivers_without_scout ?? 0,
    activated: diagnostic?.trip_metrics.activated_1plus_7d ?? 0,
    converted5v7d: diagnostic?.trip_metrics.converted_5v7d ?? 0,
    converted5v14d: diagnostic?.trip_metrics.converted_5v14d ?? 0,
    paidTotal: diagnostic?.payment_metrics.paid_history_total ?? 0,
    paidCutoff: diagnostic?.payment_metrics.paid_cutoff_engine ?? 0,
    paidHistorical: diagnostic?.payment_metrics.paid_historical_upload ?? 0,
    notPayable: diagnostic?.payment_metrics.not_payable_with_activation ?? 0,
  }), [data, diagnostic])

  function clearFilters() {
    setOrigin('')
    setLifecycleFilter('')
    setPaymentFilter('')
    setPage(0)
  }

  function applyPreset(preset: string) {
    setOrigin('')
    setPaymentFilter('')

    switch (preset) {
      case 'sin_scout':
      case 'no_trips':
      case 'activated':
      case 'converted_5v7d':
      case 'converted_5v14d':
        setLifecycleFilter(preset)
        break
      case 'payable':
      case 'paid':
      case 'no_payable':
      case 'revisar':
        setPaymentFilter(preset)
        setLifecycleFilter('')
        break
    }
    setPage(0)
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const activePreset = lifecycleFilter || paymentFilter || ''

  // Origins from data
  const origins = useMemo(() => {
    if (!diagnostic) return []
    const seen = new Set<string>()
    data?.items?.forEach(r => { if (r.origin) seen.add(r.origin) })
    return Array.from(seen).sort()
  }, [data])

  return (
    <div className="flex flex-col h-full" style={{ minHeight: 'calc(100vh - 140px)' }}>
      <div className="space-y-2 flex-shrink-0">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-800">Operacion de Afiliaciones</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Fuente: module_ct_cabinet_drivers
              {data ? ` \u00b7 ${data.total} registros` : ''}
            </p>
          </div>
        </div>

        {/* Freshness */}
        <FreshnessBanner freshness={data?.freshness ?? null} />

        {/* KPIs — Primary row */}
        <div className="grid grid-cols-8 gap-1.5">
          <KpiCard label="Total" value={kpis.total} />
          <KpiCard label="Con scout" value={kpis.withScout} color="text-green-600" />
          <KpiCard label="Sin scout" value={kpis.withoutScout} color="text-yellow-600" highlight />
          <KpiCard label="Activados" value={kpis.activated} color="text-green-600" />
          <KpiCard label="5V / 7D" value={kpis.converted5v7d} color="text-blue-600" highlight />
          <KpiCard label="5V / 14D" value={kpis.converted5v14d} color="text-purple-600" />
          <KpiCard label="Pagados" value={kpis.paidTotal} color="text-teal-600" />
          <KpiCard label="No pagables" value={kpis.notPayable} color="text-gray-500" muted />
        </div>

        {/* KPIs — Secondary row */}
        <div className="grid grid-cols-4 gap-1.5">
          <KpiCard label="Pago corte" value={kpis.paidCutoff} color="text-blue-500" muted />
          <KpiCard label="Pago historico" value={kpis.paidHistorical} color="text-teal-500" muted />
          <KpiCard label="Conflictos" value={diagnostic?.attribution_quality.assignment_conflicts ?? 0}
            color={(diagnostic?.attribution_quality.assignment_conflicts ?? 0) > 0 ? 'text-red-600' : 'text-green-600'} muted />
          <KpiCard label="Data lag" value={data?.freshness.data_lag_days != null ? `${data.freshness.data_lag_days}d` : '—'} color="text-gray-500" muted />
        </div>

        {/* Presets */}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-xs text-gray-400 uppercase tracking-wider mr-1">Modo:</span>
          {[
            { key: 'sin_scout', label: 'Sin scout', color: 'border-yellow-300 text-yellow-600 hover:bg-yellow-50' },
            { key: 'no_trips', label: 'Sin viajes', color: 'border-gray-300 text-gray-500 hover:bg-gray-50' },
            { key: 'activated', label: 'Activados', color: 'border-green-300 text-green-600 hover:bg-green-50' },
            { key: 'converted_5v7d', label: '5V / 7D', color: 'border-blue-300 text-blue-700 hover:bg-blue-50' },
            { key: 'converted_5v14d', label: '5V / 14D', color: 'border-purple-300 text-purple-600 hover:bg-purple-50' },
            { key: 'payable', label: 'Pagables', color: 'border-emerald-300 text-emerald-700 hover:bg-emerald-50' },
            { key: 'paid', label: 'Pagados', color: 'border-teal-300 text-teal-700 hover:bg-teal-50' },
            { key: 'no_payable', label: 'No pagables', color: 'border-gray-300 text-gray-600 hover:bg-gray-50' },
            { key: 'revisar', label: 'Revisar', color: 'border-orange-300 text-orange-600 hover:bg-orange-50' },
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
        <div className="flex flex-wrap gap-2 items-center bg-white rounded-lg border border-gray-200 px-3 py-1.5">
          <select value={origin} onChange={(e) => { setOrigin(e.target.value); setPage(0) }}
            className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
            <option value="">Todos los origenes</option>
            {origins.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <button onClick={clearFilters} className="text-xs text-blue-600 hover:text-blue-800 ml-auto">
            Limpiar filtros
          </button>
        </div>

        {/* Error */}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-2 text-sm">{error}</div>}
      </div>

      {/* Grid */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden flex-1 mt-2 min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">Cargando...</div>
        ) : data && displayItems.length === 0 ? (
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
                    <th className="px-2 py-2 text-center whitespace-nowrap">Base</th>
                    <th className="px-2 py-2 text-center whitespace-nowrap">Calidad</th>
                    <th className="px-2 py-2">Regla</th>
                    <th className="px-2 py-2">Evidencia</th>
                    <th className="px-3 py-2">Pago</th>
                    <th className="px-3 py-2">Motivo</th>
                    <th className="px-3 py-2 text-right whitespace-nowrap">Monto</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {displayItems.map((row: CanonicalDriver) => {
                    const lifecycle = deriveLifecycle(row)
                    const payment = derivePayment(row)
                    const rowBorder = LIFECYCLE_ROW_BORDER[lifecycle] || ''
                    const motivoColor = MOTIVO_COLORS[payment.reason] || 'text-gray-500'
                    return (
                      <tr key={row.driver_id} onClick={() => setSelectedRow(row)}
                        className={`hover:bg-blue-50/40 cursor-pointer transition-colors ${rowBorder}`}>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <div className="font-mono text-xs font-semibold text-gray-700">{row.iso_week_label || '-'}</div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap font-mono text-xs text-gray-600">
                          {row.hire_date ? row.hire_date.slice(0, 10) : '-'}
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <div className="font-medium text-gray-800 truncate text-xs" title={row.driver_name}>
                            {row.driver_name || '-'}
                          </div>
                          <div className="text-[11px] text-gray-400 truncate font-mono" title={row.driver_id || ''}>
                            {row.driver_id ? row.driver_id.slice(0, 14) : '-'}
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-600">{row.origin || '-'}</td>
                        <td className="px-3 py-2 max-w-[140px] truncate text-xs" title={row.scout_name || ''}>
                          {row.scout_name || (row.attribution_status === 'unassigned' ? 'Sin scout' : '-')}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <ProgressIcons row={row} />
                        </td>
                        <td className={`px-3 py-2 text-center font-mono text-sm font-bold ${
                          row.trips_7d >= 5 ? 'text-blue-700 bg-blue-50 rounded' : 'text-gray-500'
                        }`}>
                          {row.trips_7d}
                        </td>
                        <td className={`px-3 py-2 text-center font-mono text-sm ${
                          (row.trips_14d - row.trips_7d) >= 5 ? 'text-purple-700 font-bold' : 'text-gray-500'
                        }`}>
                          {row.trips_14d - row.trips_7d}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <LifecycleBadge status={lifecycle} />
                        </td>
                        <td className="px-2 py-2 text-center">
                          <BoolBadge value={row.counts_as_activated_base} />
                        </td>
                        <td className="px-2 py-2 text-center">
                          <BoolBadge value={row.counts_as_quality_5v7d} />
                        </td>
                        <td className="px-2 py-2 text-xs text-gray-600 max-w-[100px] truncate" title={buildRegla(row)}>
                          {buildRegla(row)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-gray-500 max-w-[160px] truncate" title={buildEvidence(row)}>
                          {buildEvidence(row)}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <PaymentBadge status={payment.status} originLabel={payment.originLabel} />
                        </td>
                        <td className={`px-3 py-2 text-xs max-w-[160px] truncate ${motivoColor}`} title={payment.reason || ''}>
                          {payment.reason || '\u2014'}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-sm whitespace-nowrap">
                          {row.amount
                            ? <span className={`font-bold ${row.payment_status === 'paid' ? 'text-teal-700' : 'text-emerald-700'}`}>S/ {row.amount.toFixed(0)}</span>
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
      {selectedRow && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/20" onClick={() => setSelectedRow(null)} />
          <div className="relative w-[520px] bg-white shadow-xl border-l border-gray-200 overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-2.5 flex items-center justify-between z-10">
              <h3 className="font-semibold text-gray-800 text-sm">Detalle Driver</h3>
              <button onClick={() => setSelectedRow(null)} className="text-gray-400 hover:text-gray-600 text-lg">&times;</button>
            </div>
            <div className="p-4 space-y-3">
              <Section title="Identidad">
                <F label="Driver ID" value={selectedRow.driver_id} mono />
                <F label="Nombre" value={selectedRow.driver_name} bold />
                <F label="Licencia" value={selectedRow.license} mono />
                <F label="Hire Date" value={selectedRow.hire_date} />
                <F label="Semana ISO" value={selectedRow.iso_week_label} />
                <F label="Origen" value={selectedRow.origin} />
                <F label="City" value={selectedRow.city} />
                <F label="Country" value={selectedRow.country} />
              </Section>
              <Section title="Scout">
                <F label="Scout" value={selectedRow.scout_name || 'Sin scout'} />
                <F label="Scout ID" value={selectedRow.scout_id} />
                <F label="Supervisor" value={selectedRow.supervisor_name} />
                <F label="Atribucion" value={selectedRow.attribution_status} />
              </Section>
              <Section title="Viajes Reales (trips_2025/trips_2026)">
                <F label="Viajes 7D" value={selectedRow.trips_7d} bold />
                <F label="Viajes 14D" value={selectedRow.trips_14d} bold />
                <F label="Activado" value={selectedRow.activated_flag ? 'Si' : 'No'} />
                <F label="5V / 7D" value={selectedRow.converted_5v7d ? 'Si' : 'No'} />
                <F label="5V / 14D" value={selectedRow.converted_5v14d ? 'Si' : 'No'} />
                <F label="Lifecycle" value={selectedRow.driver_lifecycle_status} />
              </Section>
              {resolvedScheme && (
                <Section title="Regla aplicada">
                  <F label="Esquema" value={`${resolvedScheme.scheme_name} · ${resolvedScheme.version_name}`} bold />
                  <F label="Cohorte" value={`${resolvedScheme.valid_from_cohort_iso_week} → ${resolvedScheme.valid_to_cohort_iso_week || 'vigente'}`} mono />
                  <F label="Maduración" value={`${resolvedScheme.maturity_days} días`} />
                  <F label="Mínimo activados" value={resolvedScheme.min_activated} bold />
                  <F label="Regla base" value={RULE_LABELS[resolvedScheme.activation_rule] || resolvedScheme.activation_rule} />
                  <F label="Regla calidad" value={RULE_LABELS[resolvedScheme.quality_rule] || resolvedScheme.quality_rule} />
                  <F label="Fórmula" value={FORMULA_LABELS[resolvedScheme.formula_type] || resolvedScheme.formula_type} />
                  <F label="Moneda" value={resolvedScheme.currency} />
                  {resolvedScheme.tiers.length > 0 && (
                    <F label="Tiers" value={resolvedScheme.tiers.map(t => `${(t.min_conversion_rate * 100).toFixed(0)}% → S/${t.payout_amount.toFixed(0)}`).join(' | ')} />
                  )}
                </Section>
              )}
              <Section title="Pago">
                <F label="Estado" value={selectedRow.payment_status} bold />
                <F label="Origen" value={PAYMENT_ORIGIN_LABELS[selectedRow.payment_origin] || selectedRow.payment_origin} />
                <F label="Monto" value={selectedRow.amount ? `S/ ${selectedRow.amount}` : '-'} bold />
                <div className="flex items-center px-3 py-1 text-xs">
                  <span className="text-gray-400 w-32 shrink-0">Trace</span>
                  <TraceStatusBadge status={selectedRow.payment_trace_status} />
                </div>
                <F label="Paid History ID" value={selectedRow.paid_history_id} />
              </Section>
              <Section title="Explicación financiera">
                <F label="Cuenta para base activada" value={selectedRow.counts_as_activated_base ? 'Sí' : 'No'} />
                <F label="Cuenta para calidad 5V/7D" value={selectedRow.counts_as_quality_5v7d ? 'Sí' : 'No'} />
                <F label="Cuenta para pago" value={selectedRow.counts_for_payment ? 'Sí' : 'No'} bold />
                <F label="Activados scout" value={selectedRow.scout_activated_base} bold />
                <F label="5V/7D scout" value={selectedRow.scout_quality_5v7d} bold />
                <F label="Conversión scout" value={`${(selectedRow.scout_conversion_rate_5v7d * 100).toFixed(1)}%`} />
                <F label="Tier alcanzado" value={selectedRow.scout_tier_amount > 0 ? `S/${selectedRow.scout_tier_amount.toFixed(0)}` : 'Ninguno'} bold />
                {selectedRow.scout_tier_amount > 0 && selectedRow.counts_for_payment && (
                  <F label="Fórmula" value={`${selectedRow.scout_activated_base} activados \u00d7 S/${selectedRow.scout_tier_amount.toFixed(0)} = S/${(selectedRow.scout_activated_base * selectedRow.scout_tier_amount).toFixed(0)}`} />
                )}
                {!selectedRow.counts_for_payment && selectedRow.payment_formula_label && (
                  <F label="Fórmula" value={selectedRow.payment_formula_label} />
                )}
                {selectedRow.payment_trace_warning && (
                  <F label="Motivo" value={selectedRow.payment_trace_warning} bold />
                )}
                {!selectedRow.payment_trace_warning && selectedRow.reason !== 'ok' && (
                  <F label="Motivo" value={REASON_LABELS[selectedRow.reason] || selectedRow.reason} bold />
                )}
                {selectedRow.payment_status === 'paid' && (
                  <div className="px-3 py-1.5 text-[11px] text-teal-700 bg-teal-50 border-t border-teal-100">
                    Ya pagados excluidos de base; mínimo recalculado sobre pendientes.
                  </div>
                )}
              </Section>
              <Section title="Motivo">
                <F label="Razon" value={REASON_LABELS[selectedRow.reason] || selectedRow.reason} bold />
              </Section>
              <Section title="Fuente">
                <F label="Legacy viajes_0_7" value={selectedRow.legacy_viajes_0_7 ? 'Si' : 'No'} />
                <F label="Legacy viajes_8_14" value={selectedRow.legacy_viajes_8_14 ? 'Si' : 'No'} />
                <F label="Total Orders" value={selectedRow.total_orders} />
                <F label="Driver Status" value={selectedRow.source_driver_status} />
                <F label="Actualizado" value={selectedRow.source_updated_at} />
              </Section>
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
