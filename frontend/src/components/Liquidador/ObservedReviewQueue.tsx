import { useState, useEffect, useCallback } from 'react'
import {
  getReconciliationList,
  approveReconciliation,
  rejectReconciliation,
  mergeReconciliation,
  getReconciliationExportUrl,
  type ReconciliationItem,
  type ReconciliationListResponse,
} from '../../api/unifiedLoad'

const CLASS_COLORS: Record<string, string> = {
  both_matched: 'bg-green-100 text-green-700',
  observed_only: 'bg-blue-100 text-blue-700',
  official_only: 'bg-purple-100 text-purple-700',
  official_without_scout: 'bg-yellow-100 text-yellow-700',
  conflicting_scouts: 'bg-red-100 text-red-700',
  orphan_driver: 'bg-gray-100 text-gray-500',
  operational_without_attribution: 'bg-red-100 text-red-700',
}

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-blue-100 text-blue-700',
  LOW: 'bg-yellow-100 text-yellow-700',
  BLOCKED: 'bg-red-100 text-red-700',
}

const AGING_COLORS: Record<string, string> = {
  pending_24h: 'bg-green-100 text-green-600',
  pending_1_3d: 'bg-amber-100 text-amber-600',
  pending_gt_3d: 'bg-red-100 text-red-600',
}

const REVIEW_COLORS: Record<string, string> = {
  observed_pending_review: 'bg-amber-100 text-amber-700',
  observed_validated: 'bg-green-100 text-green-700',
  observed_rejected: 'bg-red-100 text-red-700',
  observed_error: 'bg-red-100 text-red-700',
}

export default function ObservedReviewQueue() {
  const [items, setItems] = useState<ReconciliationItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [filters, setFilters] = useState({
    review_status: '',
    confidence: '',
    scout: '',
    origin: '',
    aging: '',
    classification: '',
  })
  const [page, setPage] = useState(0)
  const limit = 50

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const params: Record<string, string | number> = { limit, offset: page * limit }
      if (filters.review_status) params.review_status = filters.review_status
      if (filters.confidence) params.confidence = filters.confidence
      if (filters.scout) params.scout = filters.scout
      if (filters.origin) params.origin = filters.origin
      if (filters.aging) params.aging = filters.aging
      if (filters.classification) params.reconciliation_class = filters.classification

      const res: ReconciliationListResponse = await getReconciliationList(params)
      setItems(res.items); setTotal(res.total)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error')
    } finally { setLoading(false) }
  }, [filters, page])

  useEffect(() => { load() }, [load])

  const handleAction = async (id: number, action: string) => {
    setActionResult(null)
    try {
      if (action === 'approve') await approveReconciliation(id)
      else if (action === 'reject') await rejectReconciliation(id)
      else if (action === 'merge') await mergeReconciliation(id, true)
      setActionResult(`Accion '${action}' ejecutada en #${id}`)
      load()
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error')
    }
  }

  const handleExport = () => {
    const a = document.createElement('a')
    a.href = getReconciliationExportUrl()
    a.download = 'reconciliation_state.csv'
    a.click()
  }

  return (
    <div className="max-w-7xl mx-auto space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">Cola de Revision de Observados</h2>
          <p className="text-xs text-gray-500 mt-1">
            {total} registros pendientes de reconciliacion
          </p>
        </div>
        <button onClick={handleExport} className="px-3 py-1.5 bg-white border rounded text-xs text-gray-600 hover:bg-gray-50">
          Exportar CSV
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-2 text-xs">{error}</div>}
      {actionResult && <div className="bg-green-50 border border-green-200 text-green-700 rounded p-2 text-xs">{actionResult}</div>}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 bg-white border rounded-lg p-2">
        <FilterSelect value={filters.review_status} onChange={v => { setFilters(f => ({ ...f, review_status: v })); setPage(0) }}
          options={[
            { value: '', label: 'Todos estados' },
            { value: 'observed_pending_review', label: 'Pendiente' },
            { value: 'observed_validated', label: 'Validado' },
            { value: 'observed_rejected', label: 'Rechazado' },
          ]} />
        <FilterSelect value={filters.confidence} onChange={v => { setFilters(f => ({ ...f, confidence: v })); setPage(0) }}
          options={[
            { value: '', label: 'Todo confidence' },
            { value: 'high', label: 'HIGH' },
            { value: 'medium', label: 'MEDIUM' },
            { value: 'manual_review', label: 'MANUAL REVIEW' },
          ]} />
        <FilterSelect value={filters.aging} onChange={v => { setFilters(f => ({ ...f, aging: v })); setPage(0) }}
          options={[
            { value: '', label: 'Todo aging' },
            { value: 'pending_24h', label: '< 24h' },
            { value: 'pending_1_3d', label: '1-3d' },
            { value: 'pending_gt_3d', label: '> 3d' },
          ]} />
        <input
          placeholder="Filtrar por scout..."
          value={filters.scout}
          onChange={e => { setFilters(f => ({ ...f, scout: e.target.value })); setPage(0) }}
          className="border rounded px-2 py-1 text-[11px] w-32"
        />
        <input
          placeholder="Filtrar por origen..."
          value={filters.origin}
          onChange={e => { setFilters(f => ({ ...f, origin: e.target.value })); setPage(0) }}
          className="border rounded px-2 py-1 text-[11px] w-24"
        />
        <button onClick={load} className="px-3 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700">Buscar</button>
      </div>

      {/* Table */}
      {loading && <div className="text-xs text-gray-400">Cargando...</div>}

      {!loading && items.length > 0 && (
        <div className="overflow-x-auto border rounded-lg max-h-[65vh] overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="bg-gray-50 sticky top-0 z-10">
              <tr>
                <th className="text-left px-2 py-1.5">ID</th>
                <th className="text-left px-2 py-1.5">Driver</th>
                <th className="text-left px-2 py-1.5">Scout</th>
                <th className="text-left px-2 py-1.5">Origen</th>
                <th className="text-left px-2 py-1.5">Licencia</th>
                <th className="text-left px-2 py-1.5">Class</th>
                <th className="text-left px-2 py-1.5">Conf.</th>
                <th className="text-left px-2 py-1.5">Review</th>
                <th className="text-left px-2 py-1.5">Aging</th>
                <th className="text-left px-2 py-1.5">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map(item => (
                <tr key={item.observed_id} className="hover:bg-gray-50">
                  <td className="px-2 py-1.5 font-mono text-[10px]">{item.observed_id}</td>
                  <td className="px-2 py-1.5">
                    <div className="font-medium max-w-[120px] truncate" title={item.driver_id || ''}>{item.reported_driver_name || item.driver_id?.substring(0, 12) || '-'}</div>
                    {item.driver_id && <div className="text-[9px] text-gray-400 font-mono">{item.driver_id.substring(0, 10)}...</div>}
                  </td>
                  <td className="px-2 py-1.5 max-w-[100px] truncate">{item.reported_scout_name || '-'}</td>
                  <td className="px-2 py-1.5">{item.reported_origin || '-'}</td>
                  <td className="px-2 py-1.5 font-mono text-[10px]">{item.reported_license || '-'}</td>
                  <td className="px-2 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${CLASS_COLORS[item.classification] || 'bg-gray-100'}`}>
                      {item.classification?.replace(/_/g, ' ') || '-'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${CONFIDENCE_COLORS[item.confidence_level] || 'bg-gray-100'}`}>
                      {item.confidence_level}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${REVIEW_COLORS[item.review_status || ''] || 'bg-gray-100'}`}>
                      {item.review_status?.replace('observed_', '') || '-'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] ${AGING_COLORS[item.aging] || 'text-gray-500'}`}>
                      {item.aging === 'pending_24h' ? '< 24h' : item.aging === 'pending_1_3d' ? '1-3d' : item.aging === 'pending_gt_3d' ? '> 3d' : item.aging}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex gap-1">
                      {item.review_status !== 'observed_validated' && (
                        <button onClick={() => handleAction(item.observed_id, 'approve')}
                          className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-[9px] hover:bg-green-200">
                          Approve
                        </button>
                      )}
                      {item.review_status !== 'observed_rejected' && (
                        <button onClick={() => handleAction(item.observed_id, 'reject')}
                          className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[9px] hover:bg-red-200">
                          Reject
                        </button>
                      )}
                      <button onClick={() => handleAction(item.observed_id, 'merge')}
                        className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-[9px] hover:bg-purple-200">
                        Merge
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="text-xs text-gray-400 p-4">No hay registros con estos filtros.</div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex justify-between items-center text-xs">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="px-3 py-1 border rounded disabled:opacity-30">Anterior</button>
          <span className="text-gray-500">Pagina {page + 1} de {Math.ceil(total / limit)}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={(page + 1) * limit >= total}
            className="px-3 py-1 border rounded disabled:opacity-30">Siguiente</button>
        </div>
      )}
    </div>
  )
}

function FilterSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="border rounded px-2 py-1 text-[11px] bg-white">
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}
