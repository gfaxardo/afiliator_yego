import { useEffect, useState } from 'react'
import {
  getQualityContract, getSchemes,
  createCutoff, listCutoffs, getCutoffSummary, getCutoffLines,
  reviewCutoff, approveCutoff, markCutoffPaid,
} from '../../api/scoutLiq'
import type { SchemeResponse } from '../../api/scoutLiq'

interface QualityContract { status: string; can_compute_trip_counts: boolean; uses_legacy_booleans_for_payment: boolean; sample_driver_trip_count: any; errors: string[] }
interface CutoffRun { id: number; cutoff_name: string; hire_date_from: string; hire_date_to: string; status: string; quality_data_contract_status: string; conversion_metric_status: string; created_at: string }
interface Summary { id: number; scout_id: number; scout_name: string; origin: string; total_affiliations: number; drivers_1plus_0_7: number; drivers_5plus_0_7: number; drivers_1plus_8_14: number; drivers_5plus_0_14: number; not_converted: number; conversion_rate: number; conversion_5plus_0_7_rate: number; tier_reached: number; payment_per_converted_driver: number; amount_calculated: number; status: string; blocked_reason: string; metric_used: string }
interface DriverLine { id: number; scout_id: number; driver_id: string; hire_date: string; origin: string; trips_0_7_count: number; trips_8_14_count: number; trips_0_14_count: number; total_orders: number; legacy_viajes_0_7_flag: boolean; legacy_viajes_8_14_flag: boolean; is_converted_5trips_7d: boolean; line_status: string; blocked_reason: string; eligible: boolean; already_paid: boolean; payment_rule: string; source_quality_status: string }

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

  // Create form
  const [formName, setFormName] = useState('Corte ' + new Date().toISOString().slice(0, 10))
  const [formFrom, setFormFrom] = useState('2025-04-01')
  const [formTo, setFormTo] = useState('2026-05-15')
  const [formScheme, setFormScheme] = useState('')
  const [formOrigin, setFormOrigin] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([getQualityContract(), getSchemes(), listCutoffs()])
      .then(([c, s, cuts]) => { setContract(c); setSchemes(s); setCutoffs(cuts); if (cuts.length > 0 && !formScheme) { setFormScheme(String(s[0]?.id || '')) } })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const loadCutoffDetails = (id: number) => {
    setSelectedCutoff(id)
    setSelectedScoutId(null)
    Promise.all([getCutoffSummary(id), getCutoffLines(id)])
      .then(([s, l]) => { setSummaries(s); setLines(l) })
      .catch((err: any) => setError(err.response?.data?.detail || err.message))
  }

  const loadLines = (scoutId: number) => {
    setSelectedScoutId(scoutId)
    getCutoffLines(selectedCutoff!, scoutId)
      .then(setLines)
      .catch((err: any) => setError(err.message))
  }

  const handleCreate = async () => {
    if (!formName || !formFrom || !formTo || !formScheme) return
    setLoading(true)
    try {
      await createCutoff({
        cutoff_name: formName,
        hire_date_from: formFrom,
        hire_date_to: formTo,
        scheme_id: parseInt(formScheme),
        origin_filter: formOrigin || undefined,
      })
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
    window.open(`/api/scout-liq/cutoffs/${id}/export.csv`, '_blank')
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
        <h2 className="font-semibold mb-4">Crear Corte</h2>
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
      </div>

      {/* Cutoff list */}
      {cutoffs.length > 0 && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b"><tr>
              <th className="text-left p-3">ID</th><th className="text-left p-3">Nombre</th><th className="text-left p-3">Rango</th><th className="text-left p-3">Estado</th><th className="text-left p-3">Data</th><th className="text-left p-3">Acciones</th>
            </tr></thead>
            <tbody>
              {cutoffs.map(c => (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-mono text-xs">{c.id}</td>
                  <td className="p-3 font-medium cursor-pointer text-blue-700 hover:underline" onClick={() => loadCutoffDetails(c.id)}>{c.cutoff_name}</td>
                  <td className="p-3 text-xs">{c.hire_date_from} → {c.hire_date_to}</td>
                  <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs ${c.status === 'draft' ? 'bg-gray-100' : c.status === 'calculated' ? 'bg-blue-100 text-blue-700' : c.status === 'approved' ? 'bg-green-100 text-green-700' : c.status === 'paid' ? 'bg-purple-100 text-purple-700' : 'bg-yellow-100 text-yellow-700'}`}>{c.status}</span></td>
                  <td className="p-3 text-xs">{c.quality_data_contract_status}</td>
                  <td className="p-3 flex gap-1 flex-wrap">
                    <button onClick={() => loadCutoffDetails(c.id)} className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">Ver</button>
                    {c.status === 'calculated' && <button onClick={() => action(reviewCutoff, c.id, 'review')} className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs hover:bg-yellow-200">Revisar</button>}
                    {c.status === 'reviewed' && contract?.can_compute_trip_counts && <button onClick={() => action(approveCutoff, c.id, 'approve')} className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs hover:bg-green-200">Aprobar</button>}
                    {c.status === 'approved' && <button onClick={() => action(markCutoffPaid, c.id, 'paid')} className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs hover:bg-purple-200">Pagar</button>}
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
          <h3 className="font-semibold mb-3">Resumen por Scout (Corte #{selectedCutoff})</h3>
          <div className="bg-white border rounded-lg overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b"><tr>
                <th className="text-left p-2">Scout</th><th className="text-left p-2">Origen</th><th className="text-left p-2">Afiliados</th><th className="text-left p-2">1+ 0-7d</th><th className="text-left p-2">5+ 0-7d</th><th className="text-left p-2">1+ 8-14d</th><th className="text-left p-2">5+ 0-14d</th><th className="text-left p-2">Conv 5V/7D</th><th className="text-left p-2">Tramo</th><th className="text-left p-2">Pago/conv</th><th className="text-left p-2">Total</th><th className="text-left p-2">Estado</th>
              </tr></thead>
              <tbody>
                {summaries.map(s => (
                  <tr key={s.id} className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => loadLines(s.scout_id)}>
                    <td className="p-2 font-medium">{s.scout_name}</td><td className="p-2">{s.origin || '-'}</td><td className="p-2 font-bold">{s.total_affiliations}</td>
                    <td className="p-2">{s.drivers_1plus_0_7}</td><td className="p-2 font-bold text-blue-700">{s.drivers_5plus_0_7}</td>
                    <td className="p-2">{s.drivers_1plus_8_14}</td><td className="p-2">{s.drivers_5plus_0_14}</td>
                    <td className="p-2">{Number(s.conversion_5plus_0_7_rate * 100).toFixed(1)}%</td>
                    <td className="p-2">{s.tier_reached ? `${Number(s.tier_reached * 100).toFixed(0)}%` : '-'}</td>
                    <td className="p-2">S/ {Number(s.payment_per_converted_driver).toFixed(2)}</td>
                    <td className="p-2 font-bold">S/ {Number(s.amount_calculated).toFixed(2)}</td>
                    <td className="p-2"><span className={`px-1.5 py-0.5 rounded text-xs ${s.status === 'pending' ? 'bg-blue-100 text-blue-700' : s.status === 'blocked' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{s.status}{s.blocked_reason ? `: ${s.blocked_reason}` : ''}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lines detail */}
      {selectedCutoff && lines.length > 0 && (
        <div>
          <h3 className="font-semibold mb-3">Detalle por Conductor {selectedScoutId ? `(Scout #${selectedScoutId})` : ''}</h3>
          <div className="bg-white border rounded-lg overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0 border-b"><tr>
                <th className="text-left p-2">Driver ID</th><th className="text-left p-2">Hire Date</th><th className="text-left p-2">Origen</th><th className="text-left p-2">Viajes 0-7d</th><th className="text-left p-2">Viajes 8-14d</th><th className="text-left p-2">Viajes 0-14d</th><th className="text-left p-2">Orders</th><th className="text-left p-2">Hito</th><th className="text-left p-2">Estado</th><th className="text-left p-2">Motivo</th>
              </tr></thead>
              <tbody>
                {lines.map(l => (
                  <tr key={l.id} className="border-t hover:bg-gray-50">
                    <td className="p-2 font-mono text-xs">{l.driver_id?.substring(0, 12)}...</td>
                    <td className="p-2">{l.hire_date || '-'}</td>
                    <td className="p-2">{l.origin || '-'}</td>
                    <td className="p-2 font-bold">{l.trips_0_7_count ?? '-'}</td>
                    <td className="p-2">{l.trips_8_14_count ?? '-'}</td>
                    <td className="p-2">{l.trips_0_14_count ?? '-'}</td>
                    <td className="p-2">{l.total_orders ?? '-'}</td>
                    <td className="p-2">{l.is_converted_5trips_7d ? <span className="text-green-600 font-bold">5+ (0-7d)</span> : <span className="text-gray-400">No</span>}</td>
                    <td className="p-2"><span className={`px-1.5 py-0.5 rounded text-xs ${l.line_status?.includes('eligible') ? 'bg-green-100 text-green-700' : l.line_status?.includes('blocked') ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>{l.line_status}</span></td>
                    <td className="p-2 text-xs text-gray-500">{l.blocked_reason || l.payment_rule || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
