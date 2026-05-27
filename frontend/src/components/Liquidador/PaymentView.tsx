import { useEffect, useState } from 'react'
import {
  getSchemes, listCutoffs, getCutoffSummary, getCutoffLines,
  createPaymentDraft, recalculatePaymentDraft,
  reviewPayment, approvePayment, markPaymentPaid,
  cancelPayment, undoPaymentStatus,
  getPaymentReport, getScoutPaymentReport, getCohortPaymentReport,
  getPaymentExportCsvUrl, getPaymentExportXlsxUrl,
  getScouts,
} from '../../api/scoutLiq'
import type { SchemeResponse } from '../../api/scoutLiq'

interface CutoffRun {
  id: number; cutoff_name: string; hire_date_from: string; hire_date_to: string
  status: string; config_snapshot?: string; notes?: string
  origin_filter?: string; country_filter?: string; city_filter?: string
  scout_type_filter?: string
  cohort_iso_week?: string; cohort_from?: string; cohort_to?: string
  scheme_name?: string; scheme_type?: string; version_name?: string
  approved_by?: string; approved_at?: string; paid_at?: string
  cancelled_at?: string; cancelled_reason?: string; created_at?: string
}

interface Summary {
  id: number; scout_id: number; scout_name: string; origin: string
  total_affiliations: number; total_activated: number
  drivers_5plus_0_7: number; not_converted: number
  conversion_rate: number; tier_reached: number
  payout_per_activated: number; amount_calculated: number
  amount_approved: number; status: string; blocked_reason: string
}

interface DriverLine {
  id: number; scout_id: number; driver_id: string; hire_date: string
  origin: string; trips_0_7_count: number; trips_0_14_count: number
  is_converted_5trips_7d: boolean; is_converted_5trips_14d: boolean
  activated_flag: boolean; driver_lifecycle_status: string
  line_status: string; payment_status: string; blocked_reason: string
  eligible: boolean; already_paid: boolean; payout_eligible_flag: boolean
  calculated_amount: number; payment_rule: string
}

interface Scout { id: number; scout_name: string }

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador', calculated: 'Calculado', reviewed: 'Revisado',
  approved: 'Aprobado', paid: 'Pagado', cancelled: 'Cancelado',
}
const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  calculated: 'bg-blue-100 text-blue-700',
  reviewed: 'bg-yellow-100 text-yellow-700',
  approved: 'bg-green-100 text-green-700',
  paid: 'bg-purple-100 text-purple-700',
  cancelled: 'bg-red-100 text-red-700',
}

export default function PaymentView() {
  const [schemes, setSchemes] = useState<SchemeResponse[]>([])
  const [scouts, setScouts] = useState<Scout[]>([])
  const [cutoffs, setCutoffs] = useState<CutoffRun[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [selectedCutoff, setSelectedCutoff] = useState<CutoffRun | null>(null)
  const [summaries, setSummaries] = useState<Summary[]>([])
  const [lines, setLines] = useState<DriverLine[]>([])
  const [viewMode, setViewMode] = useState<'list' | 'create' | 'detail' | 'reports'>('list')

  const [filterScoutId, setFilterScoutId] = useState<number | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterOrigin, setFilterOrigin] = useState('')

  const [formFrom, setFormFrom] = useState('2025-04-01')
  const [formTo, setFormTo] = useState('2026-05-15')
  const [formScheme, setFormScheme] = useState('')
  const [formOrigin, setFormOrigin] = useState('')
  const [formScoutType, setFormScoutType] = useState('')
  const [formNotes, setFormNotes] = useState('')
  const [cancelReason, setCancelReason] = useState('')

  const [reportScoutId, setReportScoutId] = useState('')
  const [reportCohort, setReportCohort] = useState('')
  const [reportResult, setReportResult] = useState<any>(null)
  const [reportType, setReportType] = useState<'scout' | 'cohort' | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([getSchemes(), listCutoffs(), getScouts()])
      .then(([s, c, sc]) => {
        setSchemes(s); setCutoffs(c); setScouts(sc)
        if (s.length > 0 && !formScheme) setFormScheme(String(s[0]?.id || ''))
      })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const loadCutoffDetail = (c: CutoffRun) => {
    setSelectedCutoff(c)
    setViewMode('detail')
    setFilterScoutId(null); setFilterStatus(''); setFilterOrigin('')
    Promise.all([getCutoffSummary(c.id), getCutoffLines(c.id)])
      .then(([s, l]) => { setSummaries(s); setLines(l) })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
  }

  const action = async (fn: () => Promise<any>, label: string) => {
    try {
      const result = await fn()
      setSuccess(`${label}: OK`)
      setError(null)
      load()
      if (selectedCutoff) loadCutoffDetail(selectedCutoff)
    } catch (err: any) {
      setError(`${label}: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleCreateDraft = () => {
    setLoading(true)
    action(async () => createPaymentDraft({
      hire_date_from: formFrom,
      hire_date_to: formTo,
      scheme_id: parseInt(formScheme),
      origin: formOrigin || undefined,
      scout_type: formScoutType || undefined,
      notes: formNotes || undefined,
    }), 'Crear Borrador').finally(() => setLoading(false))
  }

  const filteredLines = lines.filter(l => {
    if (filterScoutId && l.scout_id !== filterScoutId) return false
    if (filterStatus && l.line_status !== filterStatus && l.payment_status !== filterStatus) return false
    if (filterOrigin && l.origin !== filterOrigin) return false
    return true
  })

  const originOptions = [...new Set(lines.map(l => l.origin).filter(Boolean))].sort()
  const lifecycles = [...new Set(lines.map(l => l.driver_lifecycle_status).filter(Boolean))].sort()
  const lineStatuses = [...new Set(lines.map(l => l.line_status).filter(Boolean))].sort()

  const showSpinner = loading && cutoffs.length === 0

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 font-bold text-lg leading-none">&times;</button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 rounded p-3 text-green-700 text-sm flex justify-between items-center">
          <span>{success}</span>
          <button onClick={() => setSuccess(null)} className="text-green-400 hover:text-green-600 font-bold text-lg leading-none">&times;</button>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <button onClick={() => { setViewMode('list'); setSelectedCutoff(null); setReportResult(null) }}
          className={`px-3 py-1.5 text-sm rounded ${viewMode === 'list' ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>
          Cortes
        </button>
        <button onClick={() => setViewMode('create')}
          className={`px-3 py-1.5 text-sm rounded ${viewMode === 'create' ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>
          Crear Borrador
        </button>
        <button onClick={() => setViewMode('reports')}
          className={`px-3 py-1.5 text-sm rounded ${viewMode === 'reports' ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>
          Reportes
        </button>
      </div>

      {showSpinner && <div className="text-gray-500 p-4">Cargando...</div>}

      {/* CREATE DRAFT */}
      {viewMode === 'create' && (
        <div className="bg-white border rounded-lg p-6">
          <h2 className="font-semibold mb-4">Crear Borrador de Pago</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Fecha Desde</label>
              <input type="date" value={formFrom} onChange={e => setFormFrom(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Fecha Hasta</label>
              <input type="date" value={formTo} onChange={e => setFormTo(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Esquema</label>
              <select value={formScheme} onChange={e => setFormScheme(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Seleccionar...</option>
                {schemes.filter(s => s.active).map(s => <option key={s.id} value={s.id}>{s.scheme_name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Origen (opcional)</label>
              <select value={formOrigin} onChange={e => setFormOrigin(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm">
                <option value="">Todos</option>
                <option value="cabinet">Adquisicion</option><option value="fleet">Flota</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Tipo Scout (opcional)</label>
              <input value={formScoutType} onChange={e => setFormScoutType(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm" placeholder="adquisicion, flota..." />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Notas</label>
              <input value={formNotes} onChange={e => setFormNotes(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm" placeholder="Notas del corte..." />
            </div>
          </div>
          <button onClick={handleCreateDraft} disabled={!formScheme || !formFrom || !formTo}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            Generar Borrador
          </button>
        </div>
      )}

      {/* CUTOFF LIST */}
      {viewMode === 'list' && !showSpinner && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left p-3">ID</th>
                <th className="text-left p-3">Nombre</th>
                <th className="text-left p-3">Ventana</th>
                <th className="text-left p-3">Origen</th>
                <th className="text-left p-3">Esquema</th>
                <th className="text-left p-3">Estado</th>
                <th className="text-left p-3">Creado</th>
                <th className="text-left p-3">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cutoffs.map(c => (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-mono text-xs">{c.id}</td>
                  <td className="p-3 font-medium text-blue-700 cursor-pointer hover:underline"
                    onClick={() => loadCutoffDetail(c)}>
                    {c.cutoff_name}
                  </td>
                  <td className="p-3 text-xs text-gray-500">
                    {c.cohort_iso_week || `${c.hire_date_from} → ${c.hire_date_to}`}
                  </td>
                  <td className="p-3 text-xs">{c.origin_filter || '-'}</td>
                  <td className="p-3 text-xs">{c.scheme_name || '-'}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[c.status] || 'bg-gray-100'}`}>
                      {STATUS_LABELS[c.status] || c.status}
                    </span>
                  </td>
                  <td className="p-3 text-xs text-gray-400">
                    {c.created_at ? c.created_at.replace('T', ' ').slice(0, 16) : '-'}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-1 flex-wrap">
                      <button onClick={() => loadCutoffDetail(c)}
                        className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Ver</button>
                    </div>
                  </td>
                </tr>
              ))}
              {cutoffs.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-gray-400">No hay cortes. Crea un borrador.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* CUTOFF DETAIL */}
      {viewMode === 'detail' && selectedCutoff && (
        <div className="space-y-4">
          <button onClick={() => setViewMode('list')}
            className="text-sm text-blue-600 hover:underline">&larr; Volver a lista</button>

          {/* Header */}
          <div className="bg-white border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-lg">{selectedCutoff.cutoff_name}</h2>
                <div className="text-xs text-gray-500 mt-1 space-x-3">
                  <span>ID: {selectedCutoff.id}</span>
                  <span>Estado: <span className={`px-1.5 py-0.5 rounded ${STATUS_COLORS[selectedCutoff.status]}`}>{STATUS_LABELS[selectedCutoff.status]}</span></span>
                  <span>Ventana: {selectedCutoff.hire_date_from} → {selectedCutoff.hire_date_to}</span>
                  <span>Esquema: {selectedCutoff.scheme_name || '-'}</span>
                  {selectedCutoff.notes && <span>Notas: {selectedCutoff.notes}</span>}
                </div>
              </div>
            </div>

            {/* Actions by status */}
            <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t">
              {(selectedCutoff.status === 'draft' || selectedCutoff.status === 'calculated') && (
                <>
                  <button onClick={() => action(() => recalculatePaymentDraft(selectedCutoff.id), 'Recalcular')}
                    className="px-3 py-1.5 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200">Recalcular</button>
                  <button onClick={() => action(() => reviewPayment(selectedCutoff.id), 'Revisar')}
                    className="px-3 py-1.5 bg-yellow-100 text-yellow-700 rounded text-xs hover:bg-yellow-200">
                    {selectedCutoff.status === 'calculated' ? 'Enviar a Revision' : 'Enviar a Revision'}
                  </button>
                  <button onClick={() => {
                    const reason = prompt('Motivo de cancelacion:')
                    if (reason) action(() => cancelPayment(selectedCutoff.id, reason), 'Cancelar')
                  }}
                    className="px-3 py-1.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">Cancelar</button>
                </>
              )}
              {selectedCutoff.status === 'reviewed' && (
                <>
                  <button onClick={() => action(() => approvePayment(selectedCutoff.id), 'Aprobar')}
                    className="px-3 py-1.5 bg-green-100 text-green-700 rounded text-xs hover:bg-green-200">Aprobar</button>
                  <button onClick={() => action(() => undoPaymentStatus(selectedCutoff.id), 'Devolver a Borrador')}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Devolver a Borrador</button>
                  <button onClick={() => {
                    const reason = prompt('Motivo de cancelacion:')
                    if (reason) action(() => cancelPayment(selectedCutoff.id, reason), 'Cancelar')
                  }}
                    className="px-3 py-1.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">Cancelar</button>
                </>
              )}
              {selectedCutoff.status === 'approved' && (
                <>
                  <button onClick={() => {
                    if (window.confirm('CONFIRMAR: Esto marcara el corte como PAGADO y bloqueara duplicados futuros. No se puede deshacer.'))
                      action(() => markPaymentPaid(selectedCutoff.id), 'Marcar Pagado')
                  }}
                    className="px-3 py-1.5 bg-purple-100 text-purple-700 rounded text-xs hover:bg-purple-200 font-bold">
                    Marcar Pagado
                  </button>
                  <button onClick={() => action(() => undoPaymentStatus(selectedCutoff.id), 'Devolver a Revisado')}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Devolver a Revisado</button>
                  <button onClick={() => {
                    const reason = prompt('Motivo de cancelacion (solo si no hay pagos realizados):')
                    if (reason) action(() => cancelPayment(selectedCutoff.id, reason), 'Cancelar')
                  }}
                    className="px-3 py-1.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">Cancelar</button>
                </>
              )}
              {selectedCutoff.status === 'paid' && (
                <>
                  <button onClick={() => window.open(getPaymentExportCsvUrl(selectedCutoff.id), '_blank')}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Export CSV</button>
                  <button onClick={() => window.open(getPaymentExportXlsxUrl(selectedCutoff.id), '_blank')}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Export XLSX</button>
                  <span className="px-3 py-1.5 text-xs text-gray-400 italic">Pagado - No reversible</span>
                </>
              )}
              {selectedCutoff.status === 'cancelled' && (
                <span className="px-3 py-1.5 text-xs text-gray-400 italic">Cancelado: {selectedCutoff.cancelled_reason}</span>
              )}
              {(selectedCutoff.status === 'draft' || selectedCutoff.status === 'calculated' || selectedCutoff.status === 'reviewed') && (
                <>
                  <button onClick={() => window.open(getPaymentExportCsvUrl(selectedCutoff.id), '_blank')}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Export CSV</button>
                </>
              )}
            </div>
          </div>

          {/* Summaries */}
          {summaries.length > 0 && (
            <div className="bg-white border rounded-lg overflow-x-auto">
              <h3 className="font-semibold p-3 border-b">Resumen por Scout</h3>
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-2">Scout</th><th className="text-left p-2">Origen</th>
                    <th className="text-left p-2">Afiliados</th><th className="text-left p-2">Activados</th>
                    <th className="text-left p-2">5V/7D</th><th className="text-left p-2">No Conv</th>
                    <th className="text-left p-2">Conversion</th><th className="text-left p-2">Tramo</th>
                    <th className="text-left p-2">Pago/conv</th><th className="text-right p-2">Total Calc</th>
                    <th className="text-right p-2">Total Aprob</th><th className="text-left p-2">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {summaries.map(s => (
                    <tr key={s.id} className="border-t hover:bg-gray-50 cursor-pointer"
                      onClick={() => setFilterScoutId(filterScoutId === s.scout_id ? null : s.scout_id)}>
                      <td className="p-2 font-medium">{s.scout_name}</td>
                      <td className="p-2">{s.origin || '-'}</td>
                      <td className="p-2 font-bold">{s.total_affiliations}</td>
                      <td className="p-2 text-green-700">{s.total_activated ?? 0}</td>
                      <td className="p-2 text-blue-700">{s.drivers_5plus_0_7 ?? 0}</td>
                      <td className="p-2">{s.not_converted ?? 0}</td>
                      <td className="p-2">{Number(s.conversion_rate * 100).toFixed(1)}%</td>
                      <td className="p-2">{s.tier_reached ? `${Number(s.tier_reached * 100).toFixed(0)}%` : '-'}</td>
                      <td className="p-2">S/ {Number(s.payout_per_activated).toFixed(2)}</td>
                      <td className="p-2 text-right font-bold">S/ {Number(s.amount_calculated).toFixed(2)}</td>
                      <td className="p-2 text-right">S/ {Number(s.amount_approved).toFixed(2)}</td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-xs ${s.status === 'pending' ? 'bg-blue-100 text-blue-700' : s.status === 'blocked' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                          {s.status}{s.blocked_reason ? `: ${s.blocked_reason.substring(0, 30)}` : ''}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Driver lines with filters */}
          {lines.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">Detalle por Driver ({filteredLines.length} de {lines.length})</h3>
                {(filterScoutId || filterStatus || filterOrigin) && (
                  <button onClick={() => { setFilterScoutId(null); setFilterStatus(''); setFilterOrigin('') }}
                    className="text-xs text-blue-600 hover:underline">Limpiar filtros</button>
                )}
              </div>

              <div className="flex gap-2 mb-3 flex-wrap bg-white rounded-lg border border-gray-200 px-3 py-1.5">
                <select value={filterScoutId || ''} onChange={e => setFilterScoutId(e.target.value ? parseInt(e.target.value) : null)}
                  className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white">
                  <option value="">Todos los scouts</option>
                  {summaries.map(s => (
                    <option key={s.scout_id} value={s.scout_id}>{s.scout_name}</option>
                  ))}
                </select>

                <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white">
                  <option value="">Todos los estados</option>
                  {lineStatuses.map(s => <option key={s} value={s}>{s}</option>)}
                </select>

                <select value={filterOrigin} onChange={e => setFilterOrigin(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-[11px] bg-white">
                  <option value="">Todos los origenes</option>
                  {originOptions.map(o => <option key={o} value={o!}>{o}</option>)}
                </select>
              </div>

              <div className="bg-white border rounded-lg overflow-x-auto max-h-[55vh] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0 border-b z-10">
                    <tr>
                      <th className="text-left p-2">Driver ID</th>
                      <th className="text-left p-2">Hire</th>
                      <th className="text-left p-2">Origen</th>
                      <th className="text-center p-2">7D</th>
                      <th className="text-center p-2">14D</th>
                      <th className="text-left p-2">Conv 5V/7D</th>
                      <th className="text-left p-2">Lifecycle</th>
                      <th className="text-left p-2">Line Status</th>
                      <th className="text-left p-2">Pago</th>
                      <th className="text-left p-2">Motivo</th>
                      <th className="text-right p-2">S/</th>
                      <th className="text-center p-2">Ya Pagado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {filteredLines.map(l => (
                      <tr key={l.id} className="hover:bg-blue-50/30 transition-colors">
                        <td className="p-2 font-mono text-[11px] truncate max-w-[100px]" title={l.driver_id}>
                          {l.driver_id ? l.driver_id.substring(0, 12) + (l.driver_id.length > 12 ? '...' : '') : '-'}
                        </td>
                        <td className="p-2 text-[11px] text-gray-500 whitespace-nowrap">{l.hire_date || '-'}</td>
                        <td className="p-2 text-[11px] text-gray-600 whitespace-nowrap">{l.origin || '-'}</td>
                        <td className="p-2 text-center font-mono font-bold">{l.trips_0_7_count ?? 0}</td>
                        <td className="p-2 text-center font-mono">{l.trips_0_14_count ?? 0}</td>
                        <td className="p-2">
                          {l.is_converted_5trips_7d
                            ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-100 text-blue-700">Si</span>
                            : <span className="text-gray-300">-</span>}
                        </td>
                        <td className="p-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100">{l.driver_lifecycle_status || '-'}</span>
                        </td>
                        <td className="p-2">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${l.line_status?.startsWith('blocked') ? 'bg-red-100 text-red-700' : l.line_status === 'payable' ? 'bg-emerald-100 text-emerald-700' : l.line_status === 'paid' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                            {l.line_status || '-'}
                          </span>
                        </td>
                        <td className="p-2">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${l.payment_status === 'payable' ? 'bg-emerald-100 text-emerald-700' : l.payment_status === 'paid' ? 'bg-purple-100 text-purple-700' : l.payment_status === 'blocked' ? 'bg-red-100 text-red-700' : 'bg-gray-100'}`}>
                            {l.payment_status || '-'}
                          </span>
                        </td>
                        <td className="p-2 text-[10px] text-gray-400 max-w-[140px] truncate" title={l.blocked_reason || ''}>
                          {l.blocked_reason || '-'}
                        </td>
                        <td className="p-2 text-right font-mono font-medium whitespace-nowrap">
                          {l.payout_eligible_flag && l.calculated_amount
                            ? <span className="text-emerald-700">S/ {Number(l.calculated_amount).toFixed(0)}</span>
                            : <span className="text-gray-300">-</span>}
                        </td>
                        <td className="p-2 text-center">
                          {l.already_paid
                            ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-orange-100 text-orange-700">Si</span>
                            : <span className="text-gray-300">-</span>}
                        </td>
                      </tr>
                    ))}
                    {filteredLines.length === 0 && (
                      <tr><td colSpan={12} className="p-6 text-center text-gray-400">Sin resultados con estos filtros</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* REPORTS */}
      {viewMode === 'reports' && (
        <div className="space-y-6">
          <div className="bg-white border rounded-lg p-6">
            <h2 className="font-semibold mb-3">Reporte por Scout</h2>
            <div className="flex gap-3 items-end">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Scout</label>
                <select value={reportScoutId} onChange={e => setReportScoutId(e.target.value)}
                  className="border rounded px-3 py-2 text-sm">
                  <option value="">Seleccionar...</option>
                  {scouts.map(s => <option key={s.id} value={s.id}>{s.scout_name}</option>)}
                </select>
              </div>
              <button onClick={async () => {
                if (!reportScoutId) return
                setLoading(true)
                try {
                  const result = await getScoutPaymentReport(parseInt(reportScoutId))
                  setReportResult(result)
                  setReportType('scout')
                } catch (err: any) { setError(err.response?.data?.detail || err.message) }
                finally { setLoading(false) }
              }} disabled={!reportScoutId}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                Generar Reporte
              </button>
            </div>
          </div>

          <div className="bg-white border rounded-lg p-6">
            <h2 className="font-semibold mb-3">Reporte por Cohorte</h2>
            <div className="flex gap-3 items-end">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Cohorte (ej: 2026-W18)</label>
                <input value={reportCohort} onChange={e => setReportCohort(e.target.value)}
                  className="border rounded px-3 py-2 text-sm" placeholder="2026-W18" />
              </div>
              <button onClick={async () => {
                if (!reportCohort) return
                setLoading(true)
                try {
                  const result = await getCohortPaymentReport(reportCohort)
                  setReportResult(result)
                  setReportType('cohort')
                } catch (err: any) { setError(err.response?.data?.detail || err.message) }
                finally { setLoading(false) }
              }} disabled={!reportCohort}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                Generar Reporte
              </button>
            </div>
          </div>

          {/* Report result */}
          {reportResult && (
            <div className="bg-white border rounded-lg p-6">
              <h3 className="font-semibold mb-3">
                {reportType === 'scout' ? `Reporte Scout: ${reportResult.scout_name}` : `Reporte Cohorte: ${reportResult.cohort_key}`}
              </h3>
              {reportType === 'scout' && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="bg-blue-50 rounded p-3"><div className="text-xs text-gray-500">Total Drivers</div><div className="font-bold text-lg">{reportResult.drivers_total}</div></div>
                  <div className="bg-green-50 rounded p-3"><div className="text-xs text-gray-500">Convertidos 5V/7D</div><div className="font-bold text-lg">{reportResult.drivers_converted_5v7d}</div></div>
                  <div className="bg-yellow-50 rounded p-3"><div className="text-xs text-gray-500">Conversion Rate</div><div className="font-bold text-lg">{reportResult.conversion_rate_5v7d_pct}%</div></div>
                  <div className="bg-purple-50 rounded p-3"><div className="text-xs text-gray-500">Total Pagado</div><div className="font-bold text-lg">S/ {Number(reportResult.total_paid_amount).toFixed(2)}</div></div>
                  <div className="bg-red-50 rounded p-3"><div className="text-xs text-gray-500">Bloqueados (ya pagados)</div><div className="font-bold text-lg">{reportResult.drivers_blocked_already_paid}</div></div>
                  <div className="bg-gray-50 rounded p-3"><div className="text-xs text-gray-500">Pagados en ventana</div><div className="font-bold text-lg">{reportResult.drivers_paid_in_window}</div></div>
                </div>
              )}
              {reportType === 'cohort' && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="bg-blue-50 rounded p-3"><div className="text-xs text-gray-500">Total Drivers</div><div className="font-bold text-lg">{reportResult.drivers_total}</div></div>
                  <div className="bg-green-50 rounded p-3"><div className="text-xs text-gray-500">Con Scout</div><div className="font-bold text-lg">{reportResult.drivers_with_scout}</div></div>
                  <div className="bg-yellow-50 rounded p-3"><div className="text-xs text-gray-500">Sin Scout</div><div className="font-bold text-lg">{reportResult.drivers_without_scout}</div></div>
                  <div className="bg-purple-50 rounded p-3"><div className="text-xs text-gray-500">Total Pagado</div><div className="font-bold text-lg">S/ {Number(reportResult.total_paid_amount).toFixed(2)}</div></div>
                  <div className="bg-emerald-50 rounded p-3"><div className="text-xs text-gray-500">Convertidos 5V/7D</div><div className="font-bold text-lg">{reportResult.drivers_converted_5v7d}</div></div>
                  <div className="bg-cyan-50 rounded p-3"><div className="text-xs text-gray-500">Pagables</div><div className="font-bold text-lg">{reportResult.drivers_payable}</div></div>
                  <div className="bg-red-50 rounded p-3"><div className="text-xs text-gray-500">Bloqueados</div><div className="font-bold text-lg">{reportResult.drivers_blocked_already_paid}</div></div>
                  <div className="bg-gray-50 rounded p-3"><div className="text-xs text-gray-500">Estado</div><div className="font-bold">{reportResult.readiness_status}</div></div>
                </div>
              )}
              <pre className="text-xs bg-gray-50 p-3 rounded max-h-96 overflow-auto">{JSON.stringify(reportResult, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
