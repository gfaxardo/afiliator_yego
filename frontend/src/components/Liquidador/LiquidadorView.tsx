import { useEffect, useState } from 'react'
import {
  getQualityContract, getSchemes,
  createCutoff, createCutoffFromCohort, createSweepCutoff, listCutoffs, getCutoffSummary, getCutoffLines,
  reviewCutoff, approveCutoff, markCutoffPaid,
  getCutoffExportFinancialUrl, getOperationFilters,
} from '../../api/scoutLiq'
import type { SchemeResponse } from '../../api/scoutLiq'

interface QualityContract { status: string; can_compute_trip_counts: boolean; uses_legacy_booleans_for_payment: boolean; sample_driver_trip_count: any; errors: string[] }
interface CutoffRun { id: number; cutoff_name: string; hire_date_from: string; hire_date_to: string; status: string; quality_data_contract_status: string; conversion_metric_status: string; created_at: string; cohort_iso_week?: string; cohort_from?: string; cohort_to?: string; maturity_days?: number; scheme_name?: string; scheme_type?: string; version_name?: string; min_activated?: number; activation_rule?: string; quality_rule?: string; snapshot_locked_at?: string; config_snapshot?: any; cutoff_mode?: string }
interface Summary { id: number; scout_id: number; scout_name: string; origin: string; total_affiliations: number; total_activated: number; drivers_1plus_0_7: number; drivers_5plus_0_7: number; drivers_1plus_8_14: number; drivers_5plus_0_14: number; total_converted_5v14d: number; not_converted: number; conversion_rate: number; conversion_rate_5v7d: number; conversion_5plus_0_7_rate: number; tier_reached: number; payment_per_converted_driver: number; payout_per_activated: number; amount_calculated: number; total_payable: number; status: string; blocked_reason: string; metric_used: string }
interface DriverLine { id: number; scout_id: number; driver_id: string; hire_date: string; origin: string; trips_0_7_count: number; trips_8_14_count: number; trips_0_14_count: number; total_orders: number; legacy_viajes_0_7_flag: boolean; legacy_viajes_8_14_flag: boolean; activated_flag: boolean; is_converted_5trips_7d: boolean; is_converted_5trips_14d: boolean; driver_lifecycle_status: string; line_status: string; payment_status: string; blocked_reason: string; eligible: boolean; already_paid: boolean; payout_eligible_flag: boolean; calculated_amount: number; payment_rule: string; source_quality_status: string; payment_formula_explanation?: string }

// ── Derived display helpers (PRESENTATIONAL – no business logic) ──

function deriveDisplayLifecycle(l: DriverLine): string {
  if (!l.driver_id || l.source_quality_status !== 'ok') return 'no_driver_id'
  if (l.payment_status === 'paid') return 'paid'
  if (l.payout_eligible_flag) return 'payable'
  if (l.is_converted_5trips_7d) return 'converted_5v7d'
  if (l.is_converted_5trips_14d) return 'converted_5v14d'
  if (l.activated_flag) return 'activated'
  return 'no_trip'
}

const LIFECYCLE_LABELS: Record<string, string> = {
  no_driver_id: 'Sin ID',
  no_trip: 'Sin viajes',
  activated: 'Activado',
  converted_5v7d: '5V/7D',
  converted_5v14d: '5V/14D',
  payable: 'Pagable',
  paid: 'Pagado',
}

const LIFECYCLE_COLORS: Record<string, string> = {
  no_driver_id: 'bg-red-100 text-red-700',
  no_trip: 'bg-gray-100 text-gray-500',
  activated: 'bg-green-100 text-green-700',
  converted_5v7d: 'bg-blue-100 text-blue-700',
  converted_5v14d: 'bg-purple-100 text-purple-700',
  payable: 'bg-emerald-100 text-emerald-700',
  paid: 'bg-teal-100 text-teal-700',
}

const PAYMENT_LABELS: Record<string, string> = {
  blocked: 'Bloqueado',
  payable: 'Pagable',
  paid: 'Pagado',
}

const PAYMENT_COLORS: Record<string, string> = {
  blocked: 'bg-red-100 text-red-700',
  payable: 'bg-emerald-100 text-emerald-700',
  paid: 'bg-teal-100 text-teal-700',
}

// ── Progress Icons component ──

function ProgressIcons({ line }: { line: DriverLine }) {
  const hasId = !!(line.driver_id && line.source_quality_status === 'ok')
  const activated = !!line.activated_flag
  const conv7 = !!line.is_converted_5trips_7d
  const conv14 = !!line.is_converted_5trips_14d && !conv7
  const payable = !!line.payout_eligible_flag
  const paid = line.payment_status === 'paid'

  const steps = [
    { key: 'id',   icon: 'ID', label: 'Driver ID', active: hasId },
    { key: '1v',   icon: '1',  label: '1+ viaje (7d)', active: activated },
    { key: '5v7d', icon: '7',  label: '5 viajes en 7d', active: conv7 },
    { key: '5v14d',icon: '14', label: '5 viajes en 14d', active: conv14 },
    { key: 'pay',  icon: '$',  label: 'Pagable', active: payable },
    { key: 'paid', icon: '✓',  label: 'Pagado', active: paid },
  ]

  return (
    <div className="flex items-center gap-0.5">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-0.5">
          <span
            className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold border ${
              s.active
                ? 'bg-green-500 text-white border-green-500'
                : 'bg-white text-gray-300 border-gray-200'
            }`}
            title={s.label + (s.active ? ' ✓' : '')}
          >
            {s.icon}
          </span>
          {i < steps.length - 1 && (
            <span className={`w-3 h-0.5 rounded ${s.active ? 'bg-green-400' : 'bg-gray-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Lifecycle Badge ──

function LifecycleBadge({ status }: { status: string }) {
  const color = LIFECYCLE_COLORS[status] || 'bg-gray-100 text-gray-500'
  const label = LIFECYCLE_LABELS[status] || status
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${color}`}>
      {label}
    </span>
  )
}

// ── Payment Badge ──

function PaymentBadge({ status, reason, lineStatus }: { status: string; reason?: string; lineStatus?: string }) {
  // If reason is empty and lineStatus is available, derive display
  const effectiveStatus = lineStatus || status
  const label = LINE_STATUS_LABELS[effectiveStatus] || PAYMENT_LABELS[effectiveStatus] || effectiveStatus
  const color = LINE_STATUS_COLORS[effectiveStatus] || PAYMENT_COLORS[effectiveStatus] || 'bg-gray-100 text-gray-500'
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${color}`} title={reason || ''}>
      {label}
    </span>
  )
}

const LINE_STATUS_LABELS: Record<string, string> = {
  payable: 'Pagable',
  paid: 'Pagado',
  blocked_min_activated: 'No llega al minimo',
  blocked_already_paid: 'Ya pagado',
  blocked_invalid_hire_date: 'Fecha invalida',
  activated_no_tier: 'Sin tramo',
  no_trip: 'Sin viajes',
  below_pay_threshold: 'No cumple hito',
  eligible: 'Elegible',
  not_converted: 'No convierte',
  blocked_min_affiliations: 'Min afiliaciones',
}

const LINE_STATUS_COLORS: Record<string, string> = {
  payable: 'bg-green-100 text-green-700',
  paid: 'bg-emerald-100 text-emerald-700',
  blocked_min_activated: 'bg-amber-100 text-amber-700',
  blocked_already_paid: 'bg-red-100 text-red-700',
  blocked_invalid_hire_date: 'bg-red-100 text-red-700',
  activated_no_tier: 'bg-orange-100 text-orange-700',
  no_trip: 'bg-gray-100 text-gray-500',
  below_pay_threshold: 'bg-gray-100 text-gray-500',
  eligible: 'bg-blue-100 text-blue-700',
  not_converted: 'bg-yellow-100 text-yellow-700',
  blocked_min_affiliations: 'bg-amber-100 text-amber-700',
}

export default function LiquidadorView() {
  const [contract, setContract] = useState<QualityContract | null>(null)
  const [schemes, setSchemes] = useState<SchemeResponse[]>([])
  const [cutoffs, setCutoffs] = useState<CutoffRun[]>([])
  const [selectedCutoff, setSelectedCutoff] = useState<number | null>(null)
  const [summaries, setSummaries] = useState<Summary[]>([])
  const [lines, setLines] = useState<DriverLine[]>([])
  const [selectedScoutId, setSelectedScoutId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Client-side filters for driver lines
  const [filterLifecycle, setFilterLifecycle] = useState('')
  const [filterPayment, setFilterPayment] = useState('')
  const [filterOrigin, setFilterOrigin] = useState('')

  // Create form
  const [formName, setFormName] = useState('Corte ' + new Date().toISOString().slice(0, 10))
  const [formFrom, setFormFrom] = useState('2025-04-01')
  const [formTo, setFormTo] = useState('2026-05-15')
  const [formScheme, setFormScheme] = useState('')
  const [formOrigin, setFormOrigin] = useState('')
  // Cohort-based creation mode
  const [createMode, setCreateMode] = useState<'dates' | 'cohort' | 'sweep'>('cohort')
  const [formCohort, setFormCohort] = useState('')
  const [formSchemeType, setFormSchemeType] = useState('cabinet')
  const [cohorts, setCohorts] = useState<any[]>([])

  const load = () => {
    setLoading(true)
    Promise.all([getQualityContract(), getSchemes(), listCutoffs(), getOperationFilters()])
      .then(([c, s, cuts, filters]) => {
        setContract(c); setSchemes(s); setCutoffs(cuts);
        if (cuts.length > 0 && !formScheme) { setFormScheme(String(s[0]?.id || '')) }
        if (filters?.weeks?.length) {
          setCohorts(filters.weeks.map((w: any) => ({ cohort_iso_week: `${w.year}-W${String(w.week).padStart(2, '0')}`, cohort_label: w.label })))
        }
      })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const loadCutoffDetails = (id: number) => {
    setSelectedCutoff(id)
    setSelectedScoutId(null)
    setFilterLifecycle(''); setFilterPayment(''); setFilterOrigin('')
    Promise.all([getCutoffSummary(id), getCutoffLines(id)])
      .then(([s, l]) => { setSummaries(s); setLines(l) })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
  }

  const applyScoutFilter = (scoutId: number) => {
    setSelectedScoutId(scoutId)
  }

  const clearLineFilters = () => {
    setFilterLifecycle(''); setFilterPayment(''); setFilterOrigin('')
    setSelectedScoutId(null)
  }

  const applyPreset = (preset: string) => {
    clearLineFilters()
    if (preset === 'no_driver_id') setFilterLifecycle('no_driver_id')
    else if (preset === 'no_trip') setFilterLifecycle('no_trip')
    else if (preset === 'activated') setFilterLifecycle('activated')
    else if (preset === 'converted_5v7d') setFilterLifecycle('converted_5v7d')
    else if (preset === 'converted_5v14d') setFilterLifecycle('converted_5v14d')
    else if (preset === 'payable') setFilterLifecycle('payable')
    else if (preset === 'paid') setFilterLifecycle('paid')
    else if (preset === 'blocked') setFilterPayment('blocked')
  }

  // Client-side filtered lines
  const filteredLines = lines.filter(l => {
    if (selectedScoutId && l.scout_id !== selectedScoutId) return false
    if (filterLifecycle && deriveDisplayLifecycle(l) !== filterLifecycle) return false
    if (filterPayment && l.payment_status !== filterPayment) return false
    if (filterOrigin && l.origin !== filterOrigin) return false
    return true
  })

  const originOptions = [...new Set(lines.map(l => l.origin).filter(Boolean))].sort()

  const handleSweep = async () => {
    if (!formSchemeType) { setError('Selecciona tipo de esquema'); return }
    setLoading(true)
    try {
      await createSweepCutoff({
        scheme_type: formSchemeType,
        origin_filter: formOrigin || undefined,
      })
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message)
    } finally { setLoading(false) }
  }

  const handleCreate = async () => {
    setLoading(true)
    try {
      if (createMode === 'cohort') {
        if (!formCohort || !formSchemeType) { setError('Selecciona cohorte y tipo de esquema'); setLoading(false); return }
        await createCutoffFromCohort({
          cohort_iso_week: formCohort,
          scheme_type: formSchemeType,
          origin_filter: formOrigin || undefined,
        })
      } else {
        if (!formName || !formFrom || !formTo || !formScheme) return
        await createCutoff({
          cutoff_name: formName,
          hire_date_from: formFrom,
          hire_date_to: formTo,
          scheme_id: parseInt(formScheme),
          origin_filter: formOrigin || undefined,
        })
      }
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const action = async (fn: (id: number) => Promise<any>, id: number, label: string) => {
    try {
      await fn(id)
      load()
      if (selectedCutoff === id) loadCutoffDetails(id)
    } catch (err: any) {
      setError(`${label}: ${err.response?.data?.detail || err.message}`)
    }
  }

  const exportCsv = (id: number) => {
    window.open(getCutoffExportFinancialUrl(id), '_blank')
  }

  if (loading && !contract) return <div className="text-gray-500 p-4">Cargando...</div>

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">{error}</div>}

      {/* Quality contract */}
      {contract && (
        <div className={`border rounded-lg p-4 ${contract.can_compute_trip_counts ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
          <div className="font-semibold mb-1">
            Data Contract: {contract.can_compute_trip_counts ? 'OK - Conteos reales disponibles' : 'BLOQUEADO - Sin conteos reales'}
          </div>
          <div className="text-xs text-gray-600">
            Fuentes: trips_2025={contract.trip_sources?.trips_2025 ? 'Si' : 'No'}, trips_2026={contract.trip_sources?.trips_2026 ? 'Si' : 'No'} |
            Usa booleanos para pago: {contract.uses_legacy_booleans_for_payment ? 'SI (INVALIDO)' : 'NO (correcto)'}
          </div>
          {contract.sample_driver_trip_count && (
            <div className="text-xs text-gray-500 mt-1">
              Sample: {contract.sample_driver_trip_count.driver_id?.substring(0, 8)}... hire={contract.sample_driver_trip_count.hire_date} trips_0_7={contract.sample_driver_trip_count.trips_0_7_count}
            </div>
          )}
          {!contract.can_compute_trip_counts && (
            <div className="text-sm font-medium text-red-700 mt-2">
              Bloqueado para pago: la fuente no entrega conteos reales. Los booleanos legacy son solo informativos.
            </div>
          )}
        </div>
      )}

      {/* Create cutoff form */}
      <div className="bg-white border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Crear Corte</h2>
          <div className="flex gap-1">
            <button onClick={() => setCreateMode('cohort')}
              className={`px-3 py-1 text-xs rounded ${createMode === 'cohort' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              Desde Cohorte
            </button>
            <button onClick={() => setCreateMode('sweep')}
              className={`px-3 py-1 text-xs rounded ${createMode === 'sweep' ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              Barrido Pagable
            </button>
            <button onClick={() => setCreateMode('dates')}
              className={`px-3 py-1 text-xs rounded ${createMode === 'dates' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              Por Fechas
            </button>
          </div>
        </div>
        {createMode === 'cohort' ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Cohorte ISO</label>
              <select value={formCohort} onChange={e => setFormCohort(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Seleccionar...</option>
                {cohorts.map((c: any) => <option key={c.cohort_iso_week} value={c.cohort_iso_week}>{c.cohort_label || c.cohort_iso_week}</option>)}
              </select>
            </div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Tipo Esquema</label>
              <select value={formSchemeType} onChange={e => setFormSchemeType(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                <option value="cabinet">Cabinet</option><option value="fleet">Fleet</option>
              </select>
            </div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Origen (opcional)</label>
              <select value={formOrigin} onChange={e => setFormOrigin(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Todos</option><option value="cabinet">Cabinet</option><option value="fleet">Fleet</option>
              </select>
            </div>
            <div className="flex items-end">
              <button onClick={handleCreate} disabled={!formCohort} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">Crear desde Cohorte</button>
            </div>
          </div>
        ) : createMode === 'sweep' ? (
          <div className="space-y-2">
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-xs text-purple-700">
              Busca todos los conductores activos que cumplen la regla del esquema vigente hoy y que nunca fueron pagados. No se ejecuta automaticamente.
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div><label className="block text-xs font-medium text-gray-500 mb-1">Tipo Esquema</label>
                <select value={formSchemeType} onChange={e => setFormSchemeType(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                  <option value="cabinet">Cabinet</option><option value="fleet">Fleet</option>
                </select>
              </div>
              <div><label className="block text-xs font-medium text-gray-500 mb-1">Origen (opcional)</label>
                <select value={formOrigin} onChange={e => setFormOrigin(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                  <option value="">Todos</option><option value="cabinet">Cabinet</option><option value="fleet">Fleet</option>
                </select>
              </div>
              <div className="flex items-end">
                <button onClick={handleSweep} disabled={!formSchemeType}
                  className="px-4 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50">
                  Crear Barrido
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Nombre</label><input value={formName} onChange={e => setFormName(e.target.value)} className="w-full border rounded px-3 py-2 text-sm" /></div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Desde</label><input type="date" value={formFrom} onChange={e => setFormFrom(e.target.value)} className="w-full border rounded px-3 py-2 text-sm" /></div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Hasta</label><input type="date" value={formTo} onChange={e => setFormTo(e.target.value)} className="w-full border rounded px-3 py-2 text-sm" /></div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Esquema</label>
              <select value={formScheme} onChange={e => setFormScheme(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Seleccionar...</option>
                {schemes.filter(s => s.active).map(s => <option key={s.id} value={s.id}>{s.scheme_name}</option>)}
              </select>
            </div>
            <div><label className="block text-xs font-medium text-gray-500 mb-1">Origen</label>
              <select value={formOrigin} onChange={e => setFormOrigin(e.target.value)} className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Todos</option><option value="cabinet">Cabinet</option><option value="fleet">Fleet</option>
              </select>
            </div>
            <div className="flex items-end">
              <button onClick={handleCreate} disabled={!formScheme} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">Generar Corte</button>
            </div>
          </div>
        )}
      </div>

      {/* Cutoff list */}
      {cutoffs.length > 0 && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b"><tr>
              <th className="text-left p-3">ID</th><th className="text-left p-3">Nombre</th><th className="text-left p-3">Cohorte</th><th className="text-left p-3">Esquema</th><th className="text-left p-3">Estado</th><th className="text-left p-3">Acciones</th>
            </tr></thead>
            <tbody>
              {cutoffs.map(c => (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-mono text-xs">{c.id}</td>
                  <td className="p-3 font-medium cursor-pointer text-blue-700 hover:underline" onClick={() => loadCutoffDetails(c.id)}>{c.cutoff_name}</td>
                  <td className="p-3 text-xs">
                    {c.cohort_iso_week ? (
                      <span className="font-mono">{c.cohort_iso_week}</span>
                    ) : (
                      <span className="text-gray-400">{c.hire_date_from} → {c.hire_date_to}</span>
                    )}
                  </td>
                  <td className="p-3 text-xs">
                    {c.scheme_name ? (
                      <span>{c.scheme_name} <span className="text-gray-400">{c.version_name}</span></span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs ${c.status === 'draft' ? 'bg-gray-100' : c.status === 'calculated' ? 'bg-blue-100 text-blue-700' : c.status === 'reviewed' ? 'bg-yellow-100 text-yellow-700' : c.status === 'approved' ? 'bg-green-100 text-green-700' : c.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-yellow-100 text-yellow-700'}`}>{c.status}{c.cutoff_mode === 'PAYABLE_SWEEP' ? <span className="ml-1 px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-[10px] font-medium">Barrido</span> : c.cohort_iso_week ? <span className="ml-1 px-1 py-0.5 bg-blue-100 text-blue-600 rounded text-[10px] font-medium">Cohorte</span> : null}</span></td>
                  <td className="p-3 flex gap-1 flex-wrap">
                    <button onClick={() => loadCutoffDetails(c.id)} className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Ver</button>
                    {c.status === 'calculated' && <button onClick={() => action(reviewCutoff, c.id, 'Revisar')} className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs hover:bg-yellow-200">Revisar</button>}
                    {c.status === 'reviewed' && contract?.can_compute_trip_counts && <button onClick={() => action(approveCutoff, c.id, 'Aprobar')} className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs hover:bg-green-200">Aprobar</button>}
                    {c.status === 'approved' && <button onClick={() => action(markCutoffPaid, c.id, 'Pagar')} className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs hover:bg-purple-200">Pagar</button>}
                    <button onClick={() => exportCsv(c.id)} className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">CSV</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      {selectedCutoff && summaries.length > 0 && (
        <div>
          {(() => {
            const c = cutoffs.find(x => x.id === selectedCutoff)
            if (!c) return null
            const snap = c.config_snapshot
            return (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3 text-xs space-y-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-blue-800 text-sm">Regla usada en este corte</span>
                  {c.cutoff_mode === 'PAYABLE_SWEEP' && (
                    <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-[10px] font-bold">Barrido Pagable</span>
                  )}
                  {(!c.cutoff_mode || c.cutoff_mode === 'COHORT') && c.cohort_iso_week && (
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-600 rounded text-[10px] font-bold">Cohorte {c.cohort_iso_week}</span>
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-1 text-blue-700">
                  <div><span className="text-blue-400">Esquema:</span> {snap?.scheme_name || c.scheme_name || '-'}</div>
                  <div><span className="text-blue-400">Version:</span> {snap?.version_name || c.version_name || '-'}</div>
                  <div><span className="text-blue-400">Cohorte:</span> {c.cohort_iso_week || (c.hire_date_from ? `${c.hire_date_from} -> ${c.hire_date_to}` : '-')}</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-1 text-blue-600">
                  <div><span className="text-blue-400">Hito base:</span> {snap?.activation_rule_label || c.activation_rule || '-'}</div>
                  <div><span className="text-blue-400">Hito calidad:</span> {snap?.quality_rule_label || c.quality_rule || '-'}</div>
                  <div><span className="text-blue-400">Formula:</span> {snap?.payment_formula_label || '-'}</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-1 text-blue-600">
                  <div><span className="text-blue-400">Minimo:</span> {snap?.minimum_rule_label || '-'}</div>
                  <div><span className="text-blue-400">Tramos:</span> <span className="font-mono">{snap?.tier_summary_label || '-'}</span></div>
                  <div><span className="text-blue-400">Pago:</span> {snap?.pays_on_label || '-'}</div>
                </div>
                {(snap?.frozen_at || c.snapshot_locked_at) && (
                  <div className="text-gray-400 text-[10px]">
                    Snapshot congelado: {(snap?.frozen_at || c.snapshot_locked_at || '').replace('T', ' ').slice(0, 19)}
                  </div>
                )}
              </div>
            )
          })()}
          <h3 className="font-semibold mb-3">Resumen por Scout (Corte #{selectedCutoff})</h3>
          <div className="bg-white border rounded-lg overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b"><tr>
                <th className="text-left p-2">Scout</th><th className="text-left p-2">Origen</th><th className="text-left p-2">Afiliados</th><th className="text-left p-2">Activados</th><th className="text-left p-2">5V/7D</th><th className="text-left p-2">5V/14D</th><th className="text-left p-2">Conv 5V/7D</th><th className="text-left p-2">Tramo</th><th className="text-left p-2">Pago/act</th><th className="text-left p-2">Total</th><th className="text-left p-2">Estado</th>
              </tr></thead>
              <tbody>
                {summaries.map(s => (
                  <tr key={s.id} className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => applyScoutFilter(s.scout_id)}>
                    <td className="p-2 font-medium">{s.scout_name}</td><td className="p-2">{s.origin || '-'}</td><td className="p-2 font-bold">{s.total_affiliations}</td>
                    <td className="p-2 font-bold text-green-700">{s.total_activated ?? s.drivers_1plus_0_7}</td>
                    <td className="p-2 font-bold text-blue-700">{s.drivers_5plus_0_7}</td>
                    <td className="p-2">{s.total_converted_5v14d ?? s.drivers_5plus_0_14}</td>
                    <td className="p-2">{Number(s.conversion_rate_5v7d ?? s.conversion_rate * 100).toFixed(1)}%</td>
                    <td className="p-2">{s.tier_reached ? `${Number(s.tier_reached * 100).toFixed(0)}%` : '-'}</td>
                    <td className="p-2">S/ {Number(s.payout_per_activated ?? s.payment_per_converted_driver).toFixed(2)}</td>
                    <td className="p-2 font-bold">S/ {Number(s.amount_calculated).toFixed(2)}</td>
                    <td className="p-2"><span className={`px-1.5 py-0.5 rounded text-xs ${s.status === 'pending' ? 'bg-blue-100 text-blue-700' : s.status === 'blocked' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{s.status}{s.blocked_reason ? `: ${s.blocked_reason?.substring(0, 40)}` : ''}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lines detail — enhanced operational view */}
      {selectedCutoff && lines.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">
              Detalle por Conductor (Corte #{selectedCutoff})
              {selectedScoutId ? <span className="text-blue-600"> — Scout #{selectedScoutId}</span> : ''}
            </h3>
            <span className="text-xs text-gray-400">{filteredLines.length} de {lines.length} conductores</span>
          </div>

          {/* Presets */}
          <div className="flex flex-wrap gap-1 mb-2">
            {[
              { key: 'no_driver_id', label: 'Sin ID', color: 'border-red-300 text-red-600 hover:bg-red-50' },
              { key: 'no_trip', label: 'Sin viajes', color: 'border-gray-300 text-gray-500 hover:bg-gray-50' },
              { key: 'activated', label: 'Activados', color: 'border-green-300 text-green-600 hover:bg-green-50' },
              { key: 'converted_5v7d', label: '5V/7D', color: 'border-blue-300 text-blue-600 hover:bg-blue-50' },
              { key: 'converted_5v14d', label: '5V/14D', color: 'border-purple-300 text-purple-600 hover:bg-purple-50' },
              { key: 'payable', label: 'Pagables', color: 'border-emerald-300 text-emerald-600 hover:bg-emerald-50' },
              { key: 'paid', label: 'Pagados', color: 'border-teal-300 text-teal-600 hover:bg-teal-50' },
              { key: 'blocked', label: 'Bloqueados', color: 'border-red-300 text-red-700 hover:bg-red-50' },
            ].map(p => (
              <button
                key={p.key}
                onClick={() => applyPreset(p.key)}
                className={`px-2 py-0.5 text-[10px] font-medium border rounded transition-colors ${
                  (filterLifecycle === p.key || (p.key === 'blocked' && filterPayment === 'blocked'))
                    ? `${p.color} bg-opacity-20`
                    : `bg-white ${p.color}`
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-2 mb-3 items-center bg-white rounded-lg border border-gray-200 px-3 py-1.5">
            <select
              value={filterLifecycle}
              onChange={e => setFilterLifecycle(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white"
            >
              <option value="">Todos los estados</option>
              {Object.entries(LIFECYCLE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>

            <select
              value={filterPayment}
              onChange={e => setFilterPayment(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white"
            >
              <option value="">Todos los pagos</option>
              {Object.entries(PAYMENT_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>

            <select
              value={filterOrigin}
              onChange={e => setFilterOrigin(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white"
            >
              <option value="">Todos los origenes</option>
              {originOptions.map(o => <option key={o} value={o!}>{o}</option>)}
            </select>

            {(filterLifecycle || filterPayment || filterOrigin || selectedScoutId) && (
              <button
                onClick={clearLineFilters}
                className="text-[11px] text-blue-600 hover:text-blue-800 ml-auto"
              >
                Limpiar filtros
              </button>
            )}
          </div>

          {/* Grid */}
          <div className="bg-white border rounded-lg overflow-x-auto max-h-[60vh] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0 border-b z-10"><tr>
                <th className="text-left p-2">Progreso</th>
                <th className="text-left p-2">Driver ID</th>
                <th className="text-left p-2">Hire</th>
                <th className="text-left p-2">Origen</th>
                <th className="text-center p-2 w-10">7d</th>
                <th className="text-center p-2 w-10">14d</th>
                <th className="text-left p-2">Ciclo</th>
                <th className="text-left p-2">Pago</th>
                <th className="text-left p-2">Motivo</th>
                <th className="text-right p-2">S/</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-50">
                {filteredLines.map(l => {
                  const lifecycle = deriveDisplayLifecycle(l)
                  return (
                    <tr key={l.id} className="hover:bg-blue-50/30 transition-colors">
                      <td className="p-1.5">
                        <ProgressIcons line={l} />
                      </td>
                      <td className="p-2 font-mono text-[11px] max-w-[110px] truncate" title={l.driver_id}>
                        {l.driver_id ? l.driver_id.substring(0, 14) + (l.driver_id.length > 14 ? '...' : '') : '-'}
                      </td>
                      <td className="p-2 text-[11px] whitespace-nowrap text-gray-500">
                        {l.hire_date || '-'}
                      </td>
                      <td className="p-2 text-[11px] text-gray-600 whitespace-nowrap">
                        {l.origin || '-'}
                      </td>
                      <td className="p-2 text-center font-mono text-[11px] font-bold">
                        {l.trips_0_7_count ?? 0}
                      </td>
                      <td className="p-2 text-center font-mono text-[11px]">
                        {l.trips_0_14_count ?? 0}
                      </td>
                      <td className="p-1.5">
                        <LifecycleBadge status={lifecycle} />
                      </td>
                      <td className="p-1.5">
                        <PaymentBadge
                          status={l.payment_status || l.line_status || '-'}
                          reason={l.blocked_reason || undefined}
                          lineStatus={l.line_status}
                        />
                      </td>
                      <td className="p-2 text-[10px] text-gray-500 max-w-[200px]">
                        <span
                          className="cursor-help truncate block"
                          title={l.payment_formula_explanation || l.blocked_reason || l.payment_rule || ''}
                        >
                          {l.payment_formula_explanation || l.blocked_reason || l.payment_rule || '-'}
                        </span>
                      </td>
                      <td className="p-2 text-right font-mono text-[11px] font-medium whitespace-nowrap">
                        {l.payout_eligible_flag && l.calculated_amount
                          ? <span className="text-emerald-700">S/ {Number(l.calculated_amount).toFixed(0)}</span>
                          : <span className="text-gray-300">-</span>
                        }
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
