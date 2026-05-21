import { useState, useCallback, useRef } from 'react'
import {
  downloadTemplate,
  previewUnifiedLoad,
  applyUnifiedLoad,
  type UnifiedPreviewResponse,
  type UnifiedPreviewLine,
  type UnifiedApplyResponse,
} from '../../api/unifiedLoad'

const ACTION_LABELS: Record<string, string> = {
  create_scout: 'Crear Scout',
  assign_scout: 'Asignar Scout',
  assign_to_new_scout: 'Asignar a Nuevo Scout',
  reassign_scout: 'Reasignar Scout',
  create_payment: 'Crear Pago',
  already_paid: 'Ya Pagado',
  attribution_only: 'Solo Atribucion',
  driver_not_found: 'Driver No Encontrado',
}

const ACTION_COLORS: Record<string, string> = {
  create_scout: 'bg-purple-100 text-purple-700',
  assign_scout: 'bg-blue-100 text-blue-700',
  assign_to_new_scout: 'bg-blue-100 text-blue-700',
  reassign_scout: 'bg-orange-100 text-orange-700',
  create_payment: 'bg-green-100 text-green-700',
  already_paid: 'bg-yellow-100 text-yellow-700',
  attribution_only: 'bg-gray-100 text-gray-600',
  driver_not_found: 'bg-red-100 text-red-700',
}

export default function UnifiedLoadView() {
  const [preview, setPreview] = useState<UnifiedPreviewResponse | null>(null)
  const [applyResult, setApplyResult] = useState<UnifiedApplyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pendingFileRef = useRef<File | null>(null)

  const handleDownloadTemplate = useCallback(async () => {
    try {
      const blob = await downloadTemplate()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'plantilla_unificada.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al descargar plantilla')
    }
  }, [])

  const handlePreview = useCallback(async (file: File) => {
    setLoading(true)
    setError(null)
    setPreview(null)
    setApplyResult(null)
    pendingFileRef.current = file
    try {
      const result = await previewUnifiedLoad(file)
      setPreview(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error en preview')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleApply = useCallback(async () => {
    const file = pendingFileRef.current
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const result = await applyUnifiedLoad(file)
      setApplyResult(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al aplicar')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handlePreview(file)
  }, [handlePreview])

  const filteredLines = preview?.lines?.filter((l: UnifiedPreviewLine) => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'warnings') return l.status === 'warning' || l.warnings.length > 0
    if (statusFilter === 'errors') return l.status === 'error'
    if (statusFilter === 'payments') return l.deduced_actions.includes('create_payment')
    if (statusFilter === 'reassign') return l.deduced_actions.includes('reassign_scout')
    if (statusFilter === 'new_scouts') return l.deduced_actions.includes('create_scout')
    return true
  }) || []

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Carga Unificada</h2>
        <span className="text-xs text-gray-400">
          Plantilla plana: licencia, scout, supervisor, pagado, monto, fecha
        </span>
      </div>

      {/* ── Acciones ── */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex flex-wrap gap-3 items-center">
          <button
            onClick={handleDownloadTemplate}
            className="px-4 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
          >
            Descargar Plantilla CSV
          </button>

          <label className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 cursor-pointer">
            {loading ? 'Procesando...' : 'Subir y Previsualizar'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={handleFileChange}
              disabled={loading}
            />
          </label>

          {preview && !applyResult && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleApply}
                disabled={loading || preview.valid_rows === 0}
                className="px-4 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
              >
                Aplicar {preview.valid_rows} validas
              </button>
              <span className="text-xs text-gray-500">
                ({preview.valid_rows} listas · {preview.error_rows} requieren correccion)
              </span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{error}</div>
      )}

      {/* ── Apply Result ── */}
      {applyResult && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <h3 className="text-sm font-medium text-green-800 mb-2">Aplicado</h3>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><span className="text-green-700 font-bold">{applyResult.applied}</span> aplicadas</div>
            <div><span className="text-red-700 font-bold">{applyResult.skipped}</span> saltadas</div>
            <div><span className="text-gray-600">{applyResult.details.length} total</span></div>
          </div>
        </div>
      )}

      {/* ── Preview Summary ── */}
      {preview && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Total Filas" value={preview.total_rows} color="gray" />
            <StatCard label="Listas" value={preview.valid_rows} color="green" />
            <StatCard label="Errores" value={preview.error_rows} color="red" />
            <StatCard label="Drivers Encontrados" value={preview.drivers_found} color="blue" />
            <StatCard label="No Encontrados" value={preview.drivers_not_found} color="orange" />
            <StatCard label="Scouts a Crear" value={preview.scouts_to_create} color="purple" />
            <StatCard label="Supervisores" value={preview.supervisors_to_create} color="purple" />
            <StatCard label="Asignaciones Nuevas" value={preview.assignments_to_create} color="blue" />
            <StatCard label="Reasignaciones" value={preview.assignments_to_change} color="orange" />
            <StatCard label="Pagos a Crear" value={preview.payments_to_create} color="green" />
            <StatCard label="Ya Pagados" value={preview.already_paid} color="yellow" />
            <StatCard label="Mismatch Monto" value={preview.amount_mismatch} color="red" />
          </div>

          {/* ── Resumen categorico ── */}
          <div className="flex gap-4 text-sm">
            <span className="text-green-700 font-medium">
              {preview.valid_rows} listas para aplicar
            </span>
            <span className="text-red-600 font-medium">
              {preview.error_rows} requieren correccion
            </span>
          </div>

          {/* ── Filtros ── */}
          <div className="flex flex-wrap gap-2">
            {['all', 'warnings', 'errors', 'payments', 'reassign', 'new_scouts'].map((f) => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
                className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                  statusFilter === f
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {f === 'all' ? 'Todas' :
                 f === 'warnings' ? 'Con Avisos' :
                 f === 'errors' ? 'Errores' :
                 f === 'payments' ? 'Pagos' :
                 f === 'reassign' ? 'Reasignar' :
                 f === 'new_scouts' ? 'Scouts Nuevos' : f}
              </button>
            ))}
          </div>

          {/* ── Tabla ── */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 w-12">#</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Licencia</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Scout</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Supervisor</th>
                    <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 w-16">Pagado</th>
                    <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">Monto</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Estado</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Acciones Deducidas</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Avisos</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredLines.map((l: UnifiedPreviewLine, i: number) => (
                    <tr
                      key={i}
                      className={`hover:bg-gray-50 ${
                        l.status === 'error' ? 'bg-red-50' :
                        l.status === 'warning' ? 'bg-yellow-50' : ''
                      }`}
                    >
                      <td className="px-3 py-2 text-xs text-gray-400">{l.source_row}</td>
                      <td className="px-3 py-2 font-mono text-xs">{l.licencia}</td>
                      <td className="px-3 py-2 text-xs">
                        {l.scout}
                        {l.deduced_actions.includes('create_scout') && (
                          <span className="ml-1 text-purple-600 text-[10px]">(nuevo)</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs">{l.supervisor}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          l.pagado?.toUpperCase() === 'SI' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {l.pagado}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-right font-mono">
                        {l.monto_pagado > 0 ? `S/ ${l.monto_pagado.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-3 py-2">
                        {l.status === 'error' ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700">
                            ERROR
                          </span>
                        ) : l.warnings.length > 0 ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-100 text-yellow-700">
                            AVISO
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">
                            OK
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {l.deduced_actions.map((a: string, j: number) => (
                            <span
                              key={j}
                              className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${ACTION_COLORS[a] || 'bg-gray-100 text-gray-600'}`}
                            >
                              {ACTION_LABELS[a] || a}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500 max-w-[200px]">
                        {l.errors.length > 0 && (
                          <div className="text-red-600">
                            {l.errors.map((e: string, j: number) => (
                              <div key={j}>• {e}</div>
                            ))}
                          </div>
                        )}
                        {l.warnings.map((w: string, j: number) => (
                          <div key={j} className="text-yellow-600">• {w}</div>
                        ))}
                      </td>
                    </tr>
                  ))}
                  {filteredLines.length === 0 && (
                    <tr>
                      <td colSpan={9} className="text-center py-6 text-gray-400 text-sm">
                        Sin resultados para este filtro
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!preview && !loading && (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-12 text-center">
          <p className="text-gray-400 text-sm mb-2">
            Sube un archivo CSV o XLSX con las columnas:
          </p>
          <code className="text-xs bg-gray-100 px-2 py-1 rounded">
            licencia, scout, supervisor, pagado, monto_pagado, fecha_pago, observacion
          </code>
          <p className="text-gray-400 text-xs mt-3">
            El sistema deducira automaticamente si debe crear scout, asignar driver, o registrar pago.
          </p>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const borders: Record<string, string> = {
    green: 'border-l-green-500', red: 'border-l-red-500',
    blue: 'border-l-blue-500', orange: 'border-l-orange-500',
    yellow: 'border-l-yellow-500', purple: 'border-l-purple-500',
    gray: 'border-l-gray-400',
  }
  return (
    <div className={`bg-white border border-gray-200 border-l-4 ${borders[color] || 'border-l-gray-400'} rounded-lg p-3`}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-xl font-bold text-gray-800">{value}</div>
    </div>
  )
}
