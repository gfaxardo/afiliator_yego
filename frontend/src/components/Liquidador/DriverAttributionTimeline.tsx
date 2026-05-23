import { useState } from 'react'
import { getDriverTimeline, type DriverTimeline } from '../../api/unifiedLoad'

export default function DriverAttributionTimeline() {
  const [driverId, setDriverId] = useState('')
  const [timeline, setTimeline] = useState<DriverTimeline | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async () => {
    if (!driverId.trim()) return
    setLoading(true); setError(null); setTimeline(null)
    try {
      const result = await getDriverTimeline(driverId.trim())
      setTimeline(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al buscar')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Timeline de Atribucion del Driver</h2>
        <p className="text-xs text-gray-500 mt-1">
          Busca un driver_id para ver su historial de atribucion, pagos y auditoria.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Driver ID (UUID)..."
          value={driverId}
          onChange={e => setDriverId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          className="border rounded px-3 py-2 text-sm flex-1 font-mono"
        />
        <button onClick={handleSearch} disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error}</div>}

      {timeline && (
        <div className="space-y-4">
          {/* Status bar */}
          <div className="bg-white border rounded-lg p-3 flex gap-4 text-xs">
            <StatusPill label={timeline.in_official_source ? 'En Fuente Oficial' : 'Fuera de Oficial'}
              color={timeline.in_official_source ? 'green' : 'red'} />
            {timeline.first_trip_at && (
              <StatusPill label={`Primer viaje: ${timeline.first_trip_at}`} color="blue" />
            )}
            <StatusPill label={`${timeline.observed_history.length} observaciones`} color="amber" />
            <StatusPill label={`${timeline.paid_history.length} pagos`} color="purple" />
          </div>

          {/* Observed History */}
          {timeline.observed_history.length > 0 && (
            <div className="bg-white border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Historial de Observaciones</h3>
              <div className="space-y-2">
                {timeline.observed_history.map((o, i) => (
                  <div key={i} className="flex items-center justify-between text-xs border-b pb-1.5">
                    <div>
                      <span className="font-mono text-[10px] text-gray-400">#{o.id}</span>
                      <span className="ml-2 font-medium">{o.reported_scout || '-'}</span>
                    </div>
                    <div className="flex gap-1.5">
                      <span className="px-1.5 py-0.5 rounded text-[9px] bg-gray-100">{o.match_confidence || 'N/A'}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] ${o.review_status?.includes('validated') ? 'bg-green-100 text-green-700' : o.review_status?.includes('rejected') ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                        {o.review_status?.replace('observed_', '') || 'N/A'}
                      </span>
                      {o.official_source_status === 'official_found' && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-green-100 text-green-700">Official OK</span>
                      )}
                    </div>
                    <span className="text-[10px] text-gray-400">{o.observed_at?.substring(0, 19) || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cutoff Lines */}
          {timeline.cutoff_lines.length > 0 && (
            <div className="bg-white border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Lineas de Corte</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-left text-gray-400">
                      <th className="px-2 py-1">Corte</th>
                      <th className="px-2 py-1">Fuente</th>
                      <th className="px-2 py-1">Pago</th>
                      <th className="px-2 py-1">Monto</th>
                      <th className="px-2 py-1">Explicacion</th>
                      <th className="px-2 py-1">Fecha</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {timeline.cutoff_lines.map(cl => (
                      <tr key={cl.id}>
                        <td className="px-2 py-1 font-mono text-[10px]">#{cl.cutoff_run_id}</td>
                        <td className="px-2 py-1">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] ${cl.attribution_source === 'observed' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>
                            {cl.attribution_source || 'official'}
                          </span>
                        </td>
                        <td className="px-2 py-1">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] ${cl.payment_status === 'paid' ? 'bg-green-100 text-green-700' : cl.payment_status === 'payable' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                            {cl.payment_status || '-'}
                          </span>
                        </td>
                        <td className="px-2 py-1 font-mono">
                          {cl.calculated_amount != null ? `S/ ${cl.calculated_amount.toFixed(0)}` : '-'}
                        </td>
                        <td className="px-2 py-1 text-gray-500 max-w-[200px] truncate">{cl.line_explanation || '-'}</td>
                        <td className="px-2 py-1 text-[10px] text-gray-400">{cl.created_at?.substring(0, 19) || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Paid History */}
          {timeline.paid_history.length > 0 && (
            <div className="bg-white border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Historial de Pagos</h3>
              <div className="space-y-1">
                {timeline.paid_history.map(ph => (
                  <div key={ph.id} className="flex items-center justify-between text-xs border-b pb-1">
                    <span className="font-mono text-[10px] text-gray-400">#{ph.id}</span>
                    <span className="font-medium text-green-700">S/ {ph.amount_paid?.toFixed(0) || '-'}</span>
                    <span className="text-[10px] text-gray-400">{ph.import_source}</span>
                    {ph.blocks_future_payment && <span className="px-1 py-0.5 bg-red-100 text-red-700 rounded text-[9px]">Bloqueante</span>}
                    <span className="text-[10px] text-gray-400">{ph.paid_at?.substring(0, 19) || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Audit Trail */}
          {timeline.audit_trail.length > 0 && (
            <div className="bg-white border rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-2">Audit Trail de Reconciliacion</h3>
              <div className="space-y-1">
                {timeline.audit_trail.map(a => (
                  <div key={a.id} className="flex items-center justify-between text-xs border-b pb-1">
                    <span className="font-mono text-[10px] text-gray-400">#{a.id}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] ${
                      a.action === 'approve' ? 'bg-green-100 text-green-700' :
                      a.action === 'reject' ? 'bg-red-100 text-red-700' :
                      a.action === 'merge' ? 'bg-purple-100 text-purple-700' :
                      'bg-blue-100 text-blue-700'
                    }`}>{a.action}</span>
                    <span className="text-gray-500 max-w-[200px] truncate">{a.reason || '-'}</span>
                    <span className="text-[10px] text-gray-400">{a.actor || 'system'}</span>
                    <span className="text-[10px] text-gray-400">{a.reconciliation_status}</span>
                    <span className="text-[10px] text-gray-400">{a.created_at?.substring(0, 19) || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {timeline.observed_history.length === 0 && timeline.cutoff_lines.length === 0 && (
            <div className="text-xs text-gray-400 p-4">No hay historial de atribucion para este driver.</div>
          )}
        </div>
      )}
    </div>
  )
}

function StatusPill({ label, color }: { label: string; color: string }) {
  const m: Record<string, string> = {
    green: 'bg-green-100 text-green-700', red: 'bg-red-100 text-red-700',
    blue: 'bg-blue-100 text-blue-700', amber: 'bg-amber-100 text-amber-700',
    purple: 'bg-purple-100 text-purple-700',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${m[color] || 'bg-gray-100 text-gray-500'}`}>
      {label}
    </span>
  )
}
