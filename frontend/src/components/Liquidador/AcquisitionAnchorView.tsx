import { useEffect, useState } from 'react'
import {
  getAcquisitionAnchorSummary,
  getAcquisitionAnchorSamples,
  type AcquisitionAnchorSummary,
  type AcquisitionAnchorSample,
} from '../../api/scoutLiq'

export default function AcquisitionAnchorView() {
  const [summary, setSummary] = useState<AcquisitionAnchorSummary | null>(null)
  const [samples, setSamples] = useState<AcquisitionAnchorSample[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterSource, setFilterSource] = useState<string>('')
  const [filterOrigin, setFilterOrigin] = useState<string>('')
  const [filterType, setFilterType] = useState<string>('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const s = await getAcquisitionAnchorSummary()
      setSummary(s)
      const smp = await getAcquisitionAnchorSamples({
        origen: filterOrigin || undefined,
        anchor_source: filterSource || undefined,
        acquisition_type: filterType || undefined,
        limit: 50,
      })
      setSamples(smp.samples)
    } catch (err: any) {
      setError(err?.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filterSource, filterOrigin, filterType])

  const confidenceColor = (c: string) => {
    if (c === 'strong') return 'text-green-700 bg-green-50 border-green-200'
    if (c === 'medium') return 'text-yellow-700 bg-yellow-50 border-yellow-200'
    if (c === 'weak') return 'text-red-700 bg-red-50 border-red-200'
    return 'text-gray-500 bg-gray-50 border-gray-200'
  }

  if (loading && !summary) return <div className="p-6 text-gray-400 text-sm">Cargando diagnostico de anchor...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">Acquisition Anchor (Fase 1)</h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs px-3 py-1 rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50"
        >
          {loading ? 'Cargando...' : 'Refrescar'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-xs">{error}</div>
      )}

      {/* Warning Banner */}
      <div className="bg-amber-50 border border-amber-200 rounded p-3 text-amber-700 text-xs">
        Cabinet sin lead_created_at usa fallback. Estas cohortes son aproximadas y deben auditarse.
      </div>

      {summary && (
        <>
          {/* Overview Cards */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            <StatCard label="Total Drivers" value={summary.total} />
            <StatCard label="Cabinet sin LCA" value={summary.cabinet_missing_lca} sub={summary.cabinet_recovered_lca > 0 ? `${summary.cabinet_recovered_lca} recuperados` : undefined} />
            <StatCard label="Reactivados" value={summary.reactivation_count} />
            <StatCard label="Fleet sin hire" value={summary.fleet_without_hire_date} />
            <StatCard label="Warnings" value={summary.warning_count} alert={summary.warning_count > 0} />
            <StatCard label="Cobertura LCA" value={`${((summary.total - summary.cabinet_missing_lca) / summary.total * 100).toFixed(0)}%`} />
          </div>

          {/* Distribution Tables */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DistTable title="Por Origen" rows={summary.by_origin.map(r => [r.origen, r.count])} />
            <DistTable title="Por Fuente" rows={summary.by_anchor_source.map(r => [r.anchor_source, r.count])} />
            <DistTable title="Por Confianza" rows={summary.by_anchor_confidence.map(r => [r.anchor_confidence, r.count])} />
            <DistTable title="Por Tipo" rows={summary.by_acquisition_type.map(r => [r.acquisition_type, r.count])} />
          </div>

          {/* Filter Controls */}
          <div className="flex items-center gap-3 flex-wrap">
            <select value={filterOrigin} onChange={e => setFilterOrigin(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-xs">
              <option value="">Todos los origenes</option>
              <option value="cabinet">Cabinet</option>
              <option value="fleet">Fleet</option>
            </select>
            <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-xs">
              <option value="">Todas las fuentes</option>
              {summary.by_anchor_source.map(s => (
                <option key={s.anchor_source} value={s.anchor_source}>{s.anchor_source}</option>
              ))}
            </select>
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              className="border border-gray-200 rounded px-2 py-1 text-xs">
              <option value="">Todos los tipos</option>
              {summary.by_acquisition_type.map(s => (
                <option key={s.acquisition_type} value={s.acquisition_type}>{s.acquisition_type}</option>
              ))}
            </select>
            <span className="text-xs text-gray-400">{samples.length} muestras</span>
          </div>

          {/* Samples Table */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div className="overflow-x-auto max-h-[50vh] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Driver ID</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Origen</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Anchor Date</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Fuente</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Confianza</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Tipo</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Gap (d)</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">LCA Cab</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">HD Cab</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">HD Drv</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Warning</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {samples.map((s, i) => (
                    <tr key={i} className={s.reactivation_flag ? 'bg-orange-50' : 'hover:bg-gray-50'}>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.driver_id?.slice(0, 16)}...</td>
                      <td className="px-3 py-1.5">{s.origen}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.acquisition_anchor_date || '—'}</td>
                      <td className="px-3 py-1.5 text-gray-500 text-[10px]">{s.anchor_source.replace('cabinet_drivers.', 'cab.').replace('cabinet_leads.', 'leads.')}</td>
                      <td className="px-3 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] border ${confidenceColor(s.anchor_confidence)}`}>
                          {s.anchor_confidence}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-[10px]">{s.acquisition_type}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.days_hire_vs_anchor ?? '—'}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.cabinet_lead_created_at?.slice(0, 10) || '—'}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.cabinet_hire_date?.slice(0, 10) || '—'}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px]">{s.drivers_hire_date?.slice(0, 10) || '—'}</td>
                      <td className="px-3 py-1.5 text-[10px] text-amber-600 max-w-[120px] truncate" title={s.anchor_warning || ''}>
                        {s.anchor_warning || ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Warnings Summary */}
          {summary.warnings.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Warnings ({summary.warning_count})
              </h3>
              <div className="space-y-1 max-h-[30vh] overflow-y-auto">
                {summary.warnings.slice(0, 30).map((w, i) => (
                  <div key={i} className="text-xs px-2 py-1 rounded border border-amber-200 bg-amber-50 text-amber-700">
                    <span className="font-mono text-[10px] mr-1">[{w.origen}]</span>
                    <span className="font-mono text-[10px] mr-1">{w.driver_id?.slice(0, 12)}...</span>
                    {w.warning}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, alert }: { label: string; value: string | number; sub?: string; alert?: boolean }) {
  return (
    <div className={`bg-white border rounded-lg p-3 ${alert ? 'border-red-200' : 'border-gray-200'}`}>
      <div className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-bold ${alert ? 'text-red-600' : 'text-gray-800'}`}>{value}</div>
      {sub && <div className="text-[10px] text-gray-400">{sub}</div>}
    </div>
  )
}

function DistTable({ title, rows }: { title: string; rows: [string, number][] }) {
  const total = rows.reduce((s, r) => s + r[1], 0)
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
      <div className="divide-y divide-gray-100 max-h-[200px] overflow-y-auto">
        {rows.map(([label, count], i) => (
          <div key={i} className="px-3 py-1.5 flex justify-between text-xs">
            <span className="text-gray-600 truncate max-w-[180px]" title={label}>{label}</span>
            <span className="font-mono text-gray-800">{count} <span className="text-gray-400">({total > 0 ? (count / total * 100).toFixed(0) : 0}%)</span></span>
          </div>
        ))}
      </div>
    </div>
  )
}
