import { useState } from 'react'
import { getPaidHistory, PaidHistoryList } from '../../api/scoutLiq'

export default function PaidHistoryView() {
  const [data, setData] = useState<PaidHistoryList | null>(null)
  const [filters, setFilters] = useState({
    scout_id: '',
    cutoff_run_id: '',
    import_source: '',
    payment_component: '',
    driver_license_raw: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params: any = { limit: 100, offset: 0 }
      if (filters.scout_id) params.scout_id = Number(filters.scout_id)
      if (filters.cutoff_run_id) params.cutoff_run_id = Number(filters.cutoff_run_id)
      if (filters.import_source) params.import_source = filters.import_source
      if (filters.payment_component) params.payment_component = filters.payment_component
      if (filters.driver_license_raw) params.driver_license_raw = filters.driver_license_raw

      const r = await getPaidHistory(params)
      setData(r)
    } catch (e: any) {
      setError(e.message || 'Error al cargar historial')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Historial de Pagos</h2>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <input type="number" placeholder="Scout ID" value={filters.scout_id}
            onChange={(e) => setFilters({ ...filters, scout_id: e.target.value })}
            className="border border-gray-300 rounded px-3 py-2 text-sm" />
          <input type="number" placeholder="Corte ID" value={filters.cutoff_run_id}
            onChange={(e) => setFilters({ ...filters, cutoff_run_id: e.target.value })}
            className="border border-gray-300 rounded px-3 py-2 text-sm" />
          <select value={filters.import_source}
            onChange={(e) => setFilters({ ...filters, import_source: e.target.value })}
            className="border border-gray-300 rounded px-3 py-2 text-sm">
            <option value="">Origen (todos)</option>
            <option value="cutoff_engine">Cutoff Engine</option>
            <option value="historical_upload">Historico</option>
            <option value="manual_payment">Manual</option>
          </select>
          <select value={filters.payment_component}
            onChange={(e) => setFilters({ ...filters, payment_component: e.target.value })}
            className="border border-gray-300 rounded px-3 py-2 text-sm">
            <option value="">Componente (todos)</option>
            <option value="scout_driver_payment">Pago Driver</option>
            <option value="supervisor_commission">Comision Supervisor</option>
            <option value="scout_bonus">Bono Scout</option>
            <option value="manual_adjustment">Ajuste Manual</option>
          </select>
          <input type="text" placeholder="Licencia" value={filters.driver_license_raw}
            onChange={(e) => setFilters({ ...filters, driver_license_raw: e.target.value })}
            className="border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <button onClick={load} disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {loading ? 'Cargando...' : 'Buscar'}
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}

      {data && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <p className="text-sm text-gray-500 mb-3">Total: {data.total} pagos</p>
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-left sticky top-0">
                  <th className="px-2 py-1">ID</th>
                  <th className="px-2 py-1">Corte</th>
                  <th className="px-2 py-1">Scout</th>
                  <th className="px-2 py-1">Driver</th>
                  <th className="px-2 py-1">Licencia</th>
                  <th className="px-2 py-1">Componente</th>
                  <th className="px-2 py-1">Origen</th>
                  <th className="px-2 py-1">Monto</th>
                  <th className="px-2 py-1">Estado</th>
                  <th className="px-2 py-1">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id} className="border-t border-gray-100">
                    <td className="px-2 py-1">{p.id}</td>
                    <td className="px-2 py-1">{p.cutoff_run_id || '-'}</td>
                    <td className="px-2 py-1">{p.scout_id}</td>
                    <td className="px-2 py-1 max-w-[100px] truncate">{p.driver_id || '-'}</td>
                    <td className="px-2 py-1 max-w-[80px] truncate">{p.driver_license_raw || '-'}</td>
                    <td className="px-2 py-1">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        p.payment_component === 'scout_driver_payment' ? 'bg-blue-100 text-blue-700' :
                        p.payment_component === 'supervisor_commission' ? 'bg-purple-100 text-purple-700' :
                        p.payment_component === 'scout_bonus' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>{p.payment_component}</span>
                    </td>
                    <td className="px-2 py-1">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        p.import_source === 'cutoff_engine' ? 'bg-green-100 text-green-700' :
                        p.import_source === 'historical_upload' ? 'bg-orange-100 text-orange-700' :
                        p.import_source === 'manual_payment' ? 'bg-gray-100 text-gray-700' :
                        'bg-gray-100 text-gray-500'
                      }`}>{p.import_source || '-'}</span>
                    </td>
                    <td className="px-2 py-1 font-medium">S/ {Number(p.amount_paid).toFixed(2)}</td>
                    <td className="px-2 py-1">{p.status}</td>
                    <td className="px-2 py-1 text-gray-500">{p.paid_at?.split('T')[0] || '-'}</td>
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
