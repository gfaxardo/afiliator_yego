import { useState, useCallback, useRef } from 'react'
import {
  exportReconciliationCsv,
  compareUpload,
  type ReconciliationCompareResponse,
  type ReconciliationDetail,
} from '../../api/reconciliation'

const STATUS_LABELS: Record<string, string> = {
  ok: 'OK',
  amount_mismatch: 'Diferencia Monto',
  already_paid: 'Ya Pagado',
  missing_in_system: 'No Encontrado',
  missing_in_upload: 'Falta Cargar',
  unexpected_payment: 'Pago Inesperado',
  scout_mismatch: 'Scout Distinto',
  expected_to_pay: 'Espera Pago',
  pending_maturity: 'Pendiente Madurez',
  no_activation: 'Sin Activacion',
  not_payable: 'No Pagable',
  manual_override: 'Override Manual',
  historical_paid: 'Historico',
  cutoff_paid: 'Cutoff Sistema',
  system_paid: 'Sistema',
  manual_exclude: 'Excluido Manual',
  invalid_row: 'Fila Invalida',
  unknown: 'Desconocido',
}

const STATUS_COLORS: Record<string, string> = {
  ok: 'bg-green-100 text-green-700',
  amount_mismatch: 'bg-red-100 text-red-700',
  already_paid: 'bg-yellow-100 text-yellow-700',
  missing_in_system: 'bg-red-100 text-red-700',
  missing_in_upload: 'bg-orange-100 text-orange-700',
  unexpected_payment: 'bg-orange-100 text-orange-700',
  scout_mismatch: 'bg-yellow-100 text-yellow-700',
  expected_to_pay: 'bg-blue-100 text-blue-700',
  pending_maturity: 'bg-gray-100 text-gray-500',
  no_activation: 'bg-gray-100 text-gray-500',
  not_payable: 'bg-gray-100 text-gray-500',
  manual_override: 'bg-purple-100 text-purple-700',
  historical_paid: 'bg-indigo-100 text-indigo-700',
  cutoff_paid: 'bg-green-100 text-green-700',
  system_paid: 'bg-green-100 text-green-700',
  manual_exclude: 'bg-red-100 text-red-700',
  invalid_row: 'bg-red-100 text-red-700',
  unknown: 'bg-gray-100 text-gray-500',
}

export default function ReconciliationView() {
  const [filters, setFilters] = useState({
    hire_date_from: '',
    hire_date_to: '',
    scheme_type: '',
  })

  const [compareResult, setCompareResult] = useState<ReconciliationCompareResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleExport = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const blob = await exportReconciliationCsv({
        hire_date_from: filters.hire_date_from || undefined,
        hire_date_to: filters.hire_date_to || undefined,
        scheme_type: filters.scheme_type || undefined,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'reconciliation_export.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al exportar')
    } finally {
      setLoading(false)
    }
  }, [filters])

  const handleCompare = useCallback(async (file: File) => {
    setLoading(true)
    setError(null)
    setCompareResult(null)
    try {
      const result = await compareUpload(file, {
        hire_date_from: filters.hire_date_from || undefined,
        hire_date_to: filters.hire_date_to || undefined,
        scheme_type: filters.scheme_type || undefined,
      })
      setCompareResult(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al comparar')
    } finally {
      setLoading(false)
    }
  }, [filters])

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleCompare(file)
    }
  }, [handleCompare])

  const filteredDetails = compareResult?.details?.filter((d: ReconciliationDetail) => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'issues') {
      return d.status !== 'ok' && d.status !== 'system_paid' && d.status !== 'cutoff_paid'
    }
    return d.status === statusFilter
  }) || []

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Conciliacion</h2>
        <span className="text-xs text-gray-400">
          Contrasta sistema vs pagos reales
        </span>
      </div>

      {/* ── Filtros ── */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Desde</label>
            <input
              type="date"
              value={filters.hire_date_from}
              onChange={(e) => setFilters({ ...filters, hire_date_from: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Hasta</label>
            <input
              type="date"
              value={filters.hire_date_to}
              onChange={(e) => setFilters({ ...filters, hire_date_to: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Esquema</label>
            <select
              value={filters.scheme_type}
              onChange={(e) => setFilters({ ...filters, scheme_type: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
            >
              <option value="">Todos</option>
              <option value="cabinet">Adquisicion</option>
              <option value="fleet">Flota</option>
              <option value="custom">Custom</option>
            </select>
          </div>

          <button
            onClick={handleExport}
            disabled={loading}
            className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Exportando...' : 'Exportar CSV Sistema'}
          </button>

          <label className="px-4 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700 cursor-pointer">
            {loading ? 'Comparando...' : 'Subir CSV para Comparar'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              className="hidden"
              onChange={handleFileUpload}
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      {/* ── Resumen ── */}
      {compareResult && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SummaryCard label="Total Filas Upload" value={compareResult.total_rows} color="gray" />
            <SummaryCard label="Coinciden" value={compareResult.matched_rows} color="green" />
            <SummaryCard label="Diferencias" value={compareResult.unmatched_rows} color="red" />
            <SummaryCard label="Mismatch Monto" value={compareResult.amount_mismatch} color="orange" />
            <SummaryCard label="Ya Pagados" value={compareResult.already_paid} color="yellow" />
            <SummaryCard label="No en Sistema" value={compareResult.missing_in_system} color="red" />
            <SummaryCard label="Falta en Upload" value={compareResult.missing_in_upload} color="orange" />
            <SummaryCard label="Acciones Sugeridas" value={compareResult.suggested_actions.length} color="blue" />
          </div>

          {/* ── Acciones sugeridas ── */}
          {compareResult.suggested_actions.length > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <h3 className="text-sm font-medium text-blue-800 mb-2">Acciones Sugeridas</h3>
              <ul className="list-disc list-inside text-sm text-blue-700 space-y-1">
                {compareResult.suggested_actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Filtro de estado ── */}
          <div className="flex flex-wrap gap-2">
            {['all', 'issues', 'amount_mismatch', 'already_paid', 'missing_in_system', 'missing_in_upload', 'scout_mismatch', 'expected_to_pay'].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                  statusFilter === s
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {s === 'all' ? 'Todos' : s === 'issues' ? 'Con Problemas' : (STATUS_LABELS[s] || s)}
              </button>
            ))}
          </div>

          {/* ── Tabla ── */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Driver ID</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Nombre</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Estado</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Motivo</th>
                    <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">Sist. Monto</th>
                    <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">Upload Monto</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Sist. Scout</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Upload Scout</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Accion</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredDetails.map((d: ReconciliationDetail, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono text-xs">{d.driver_id || '-'}</td>
                      <td className="px-3 py-2 text-xs">{d.driver_name || '-'}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[d.status] || 'bg-gray-100 text-gray-600'}`}>
                          {STATUS_LABELS[d.status] || d.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-600 max-w-[200px] truncate">{d.reason}</td>
                      <td className="px-3 py-2 text-xs text-right font-mono">
                        {d.system_amount != null ? `S/ ${(d.system_amount).toFixed(2)}` : '-'}
                      </td>
                      <td className="px-3 py-2 text-xs text-right font-mono">
                        {d.upload_amount != null ? `S/ ${(d.upload_amount).toFixed(2)}` : '-'}
                      </td>
                      <td className="px-3 py-2 text-xs">{d.system_scout || '-'}</td>
                      <td className="px-3 py-2 text-xs">{d.upload_scout || '-'}</td>
                      <td className="px-3 py-2 text-xs text-gray-500 max-w-[180px] truncate">
                        {d.suggested_action || '-'}
                      </td>
                    </tr>
                  ))}
                  {filteredDetails.length === 0 && (
                    <tr>
                      <td colSpan={9} className="text-center py-6 text-gray-400 text-sm">
                        {compareResult ? 'Sin resultados para este filtro' : 'Sube un CSV para comparar'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!compareResult && !loading && (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-12 text-center">
          <p className="text-gray-400 text-sm mb-4">
            Sube un archivo CSV con columnas: <code className="bg-gray-100 px-1 rounded">driver_id</code>,{' '}
            <code className="bg-gray-100 px-1 rounded">amount_paid</code> (y opcional <code className="bg-gray-100 px-1 rounded">scout_name</code>)
          </p>
          <p className="text-gray-400 text-xs">
            El sistema comparara contra su estado esperado y detectara diferencias.
          </p>
        </div>
      )}
    </div>
  )
}

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  const borderColors: Record<string, string> = {
    green: 'border-l-green-500',
    red: 'border-l-red-500',
    orange: 'border-l-orange-500',
    yellow: 'border-l-yellow-500',
    blue: 'border-l-blue-500',
    gray: 'border-l-gray-400',
  }
  return (
    <div className={`bg-white border border-gray-200 border-l-4 ${borderColors[color] || 'border-l-gray-400'} rounded-lg p-3`}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-xl font-bold text-gray-800">{value}</div>
    </div>
  )
}
