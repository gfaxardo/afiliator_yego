import { useState, useCallback, useRef } from 'react'
import {
  downloadTemplate,
  previewUnifiedLoadStream,
  applyUnifiedLoadStream,
  type UnifiedPreviewResponse,
  type UnifiedPreviewLine,
  type UnifiedApplyResponse,
} from '../../api/unifiedLoad'
import {
  exportReconciliationCsv,
  compareUpload,
  type ReconciliationCompareResponse,
  type ReconciliationDetail,
} from '../../api/reconciliation'

const ACTION_LABELS: Record<string, string> = {
  create_scout: 'Crear Scout', assign_scout: 'Asignar Scout',
  assign_to_new_scout: 'Asignar a Nuevo Scout', reassign_scout: 'Reasignar',
  create_payment: 'Crear Pago', already_paid: 'Ya Pagado',
  attribution_only: 'Solo Atribucion', driver_not_found: 'Driver No Encontrado',
}

const ACTION_COLORS: Record<string, string> = {
  create_scout: 'bg-purple-100 text-purple-700', assign_scout: 'bg-blue-100 text-blue-700',
  assign_to_new_scout: 'bg-blue-100 text-blue-700', reassign_scout: 'bg-orange-100 text-orange-700',
  create_payment: 'bg-green-100 text-green-700', already_paid: 'bg-yellow-100 text-yellow-700',
  attribution_only: 'bg-gray-100 text-gray-600', driver_not_found: 'bg-red-100 text-red-700',
}

const RECON_STATUS_LABELS: Record<string, string> = {
  ok: 'OK', amount_mismatch: 'Diferencia Monto', already_paid: 'Ya Pagado',
  missing_in_system: 'No Encontrado', missing_in_upload: 'Falta Cargar',
  unexpected_payment: 'Pago Inesperado', scout_mismatch: 'Scout Distinto',
}

const RECON_STATUS_COLORS: Record<string, string> = {
  ok: 'bg-green-100 text-green-700', amount_mismatch: 'bg-red-100 text-red-700',
  already_paid: 'bg-yellow-100 text-yellow-700', missing_in_system: 'bg-red-100 text-red-700',
  missing_in_upload: 'bg-orange-100 text-orange-700', unexpected_payment: 'bg-orange-100 text-orange-700',
  scout_mismatch: 'bg-yellow-100 text-yellow-700',
}

export default function CentroCargaView() {
  // ── Carga Unificada state ──
  const [preview, setPreview] = useState<UnifiedPreviewResponse | null>(null)
  const [applyResult, setApplyResult] = useState<UnifiedApplyResponse | null>(null)
  const pendingFileRef = useRef<File | null>(null)

  // ── Conciliacion state ──
  const [reconFilters, setReconFilters] = useState({ hire_date_from: '', hire_date_to: '', scheme_type: '' })
  const [compareResult, setCompareResult] = useState<ReconciliationCompareResponse | null>(null)
  const [reconStatusFilter, setReconStatusFilter] = useState<string>('all')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeStep, setActiveStep] = useState<number>(0)

  // ── Paso 1: Descargar plantilla ──
  const handleDownloadTemplate = useCallback(async () => {
    try {
      const blob = await downloadTemplate()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'plantilla_unificada.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError('Error al descargar plantilla')
    }
  }, [])

  // ── Streaming state ──
  const [streamLines, setStreamLines] = useState<any[]>([])
  const [streamProgress, setStreamProgress] = useState({ valid: 0, errors: 0, total: 0 })

  // ── Paso 2+3: Subir y previsualizar (streaming) ──
  const handlePreview = useCallback(async (file: File) => {
    setLoading(true); setError(null); setPreview(null); setApplyResult(null)
    setStreamLines([]); setStreamProgress({ valid: 0, errors: 0, total: 0 })
    pendingFileRef.current = file

    await previewUnifiedLoadStream(
      file,
      (line) => {
        setStreamLines(prev => [...prev, line])
        setStreamProgress(p => ({
          valid: line.valid_rows ?? p.valid,
          errors: line.error_rows ?? p.errors,
          total: line.total ?? p.total,
        }))
      },
      (summary) => {
        setPreview({
          total_rows: summary.total_rows,
          valid_rows: summary.valid_rows,
          error_rows: summary.error_rows,
          duplicate_rows: summary.duplicate_rows || 0,
          drivers_found: summary.drivers_found,
          drivers_not_found: summary.drivers_not_found,
          scouts_to_create: summary.scouts_to_create,
          supervisors_to_create: summary.supervisors_to_create,
          assignments_to_create: summary.assignments_to_create,
          assignments_to_change: summary.assignments_to_change,
          payments_to_create: summary.payments_to_create,
          already_paid: summary.already_paid,
          amount_mismatch: summary.amount_mismatch || 0,
          warnings: [],
          lines: [],
          apply_plan: summary.apply_plan || [],
          parse_metadata: {},
        })
        setLoading(false)
        setActiveStep(2)
      },
      (err) => {
        setError(err)
        setLoading(false)
      },
    )
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handlePreview(file)
  }, [handlePreview])

  // ── Apply detail lines collected from stream ──
  const [applyLines, setApplyLines] = useState<any[]>([])

  // ── Paso 4: Aplicar (envia apply_plan, no archivo) ──
  const handleApply = useCallback(async () => {
    const plan = preview?.apply_plan
    if (!plan || plan.length === 0) return
    setLoading(true); setError(null); setApplyResult(null)
    setStreamLines([]); setStreamProgress({ valid: 0, errors: 0, total: 0 })
    setApplyLines([])

    await applyUnifiedLoadStream(
      plan,
      (line) => {
        setStreamLines(prev => [...prev, line])
        setApplyLines(prev => [...prev, line])
        setStreamProgress(p => ({
          valid: line.applied ?? p.valid,
          errors: p.errors,
          total: line.total ?? p.total,
        }))
      },
      (summary) => {
        setApplyResult({
          applied: summary.applied,
          skipped: summary.skipped,
          errors: summary.errors || 0,
          details: [],
          commit_ok: summary.commit_ok !== false,
          commit_error: summary.commit_error || null,
        })
        setLoading(false)
        if (summary.commit_ok === false) {
          setError('ERROR CRITICO: Los cambios NO se guardaron en la base de datos. Motivo: ' + (summary.commit_error || 'desconocido'))
        }
      },
      (err) => {
        setError(err)
        setLoading(false)
      },
    )
  }, [preview])

  // ── Contraste: Exportar estado sistema ──
  const handleExportSystemState = useCallback(async () => {
    setError(null)
    try {
      const blob = await exportReconciliationCsv({
        hire_date_from: reconFilters.hire_date_from || undefined,
        hire_date_to: reconFilters.hire_date_to || undefined,
        scheme_type: reconFilters.scheme_type || undefined,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'estado_sistema.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError('Error al exportar estado del sistema')
    }
  }, [reconFilters])

  // ── Contraste: Comparar archivo externo ──
  const handleCompare = useCallback(async (file: File) => {
    setLoading(true); setError(null); setCompareResult(null)
    try {
      const result = await compareUpload(file, {
        hire_date_from: reconFilters.hire_date_from || undefined,
        hire_date_to: reconFilters.hire_date_to || undefined,
        scheme_type: reconFilters.scheme_type || undefined,
      })
      setCompareResult(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al comparar')
    } finally {
      setLoading(false)
    }
  }, [reconFilters])

  const filteredLines = preview?.lines?.filter((l: UnifiedPreviewLine) => {
    return l.status !== 'error'
  }) || []

  const errorLines = preview?.lines?.filter((l: UnifiedPreviewLine) => {
    return l.status === 'error'
  }) || []

  const filteredRecon = compareResult?.details?.filter((d: ReconciliationDetail) => {
    if (reconStatusFilter === 'all') return true
    if (reconStatusFilter === 'issues') return d.status !== 'ok'
    return d.status === reconStatusFilter
  }) || []

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      {/* ── Header ── */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Centro de Carga</h2>
        <p className="text-xs text-gray-500 mt-1">
          Carga pagos, scouts, supervisores y atribuciones en una sola plantilla.
          Antes de aplicar, el sistema valida y compara contra lo ya registrado.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{error}</div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* SECCION 1: Carga de datos */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          Carga de datos
        </h3>

        <div className="flex flex-wrap gap-3 items-center">
          {/* Paso 1 */}
          <button onClick={handleDownloadTemplate}
            className="px-4 py-2 text-sm bg-gray-700 text-white rounded hover:bg-gray-800">
            Paso 1: Descargar plantilla
          </button>

          {/* Paso 2 */}
          <label className={`px-4 py-2 text-sm rounded cursor-pointer transition-colors ${
            loading ? 'bg-gray-400 text-white' : 'bg-blue-600 text-white hover:bg-blue-700'
          }`}>
            {loading ? 'Procesando...' : 'Paso 2: Subir archivo'}
            <input type="file" accept=".csv,.xlsx" className="hidden"
              onChange={handleFileChange} disabled={loading} />
          </label>

          {/* Paso 4: Aplicar */}
          {preview && preview.valid_rows > 0 && !applyResult && (
            <div className="flex items-center gap-2">
              <button onClick={handleApply} disabled={loading}
                className="px-4 py-2 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
                Paso 4: Aplicar {preview.valid_rows} filas validas
              </button>
              <span className="text-xs text-gray-500">
                ({preview.valid_rows} listas · {preview.error_rows} requieren correccion)
              </span>
            </div>
          )}
        </div>

        {/* ── Streaming log (terminal-style) ── */}
        {(loading || streamLines.length > 0) && (
          <div className="mt-3 bg-gray-900 text-green-400 font-mono text-[11px] rounded-lg p-3 max-h-[300px] overflow-y-auto">
            <div className="text-gray-500 mb-1">
              {loading ? 'Procesando...' : 'Completado'} [{streamProgress.valid} OK, {streamProgress.errors} errores de {streamProgress.total}]
            </div>
            {streamLines.slice(-25).map((l, i) => (
              <div key={i} className={l.status === 'error' ? 'text-red-400' : l.status === 'warning' ? 'text-yellow-400' : 'text-green-400'}>
                [{String(l.source_row).padStart(4, ' ')}] {String(l.licencia || '---').padEnd(16, ' ')} {l.status === 'error' ? 'ERR' : l.status === 'warning' ? 'WRN' : 'OK '} {(l.deduced_actions || []).join(', ') || (l.errors?.[0] || '')}
              </div>
            ))}
          </div>
        )}

        {/* ── Aplicado ── */}
        {applyResult && (
          <div className="mt-4 space-y-3">
            {/* Header */}
            <div className={`rounded-lg p-4 ${applyResult.applied > 0 ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'}`}>
              <div className="flex items-center gap-4 flex-wrap">
                <div className="text-center min-w-[60px]">
                  <div className="text-2xl font-bold text-green-700">{applyResult.applied}</div>
                  <div className="text-[10px] text-green-600">aplicadas</div>
                </div>
                <div className="text-center min-w-[60px]">
                  <div className="text-2xl font-bold text-gray-500">{applyResult.skipped}</div>
                  <div className="text-[10px] text-gray-400">saltadas</div>
                </div>
                {applyResult.errors > 0 && (
                  <div className="text-center min-w-[60px]">
                    <div className="text-2xl font-bold text-red-600">{applyResult.errors}</div>
                    <div className="text-[10px] text-red-500">errores</div>
                  </div>
                )}
                <div className="flex-1" />
                <div className={`px-4 py-2 rounded-lg text-sm font-bold ${
                  (applyResult as any).commit_ok === false
                    ? 'bg-red-100 text-red-800 border-2 border-red-400'
                    : 'bg-green-100 text-green-800'
                }`}>
                  {(applyResult as any).commit_ok === false ? 'NO GUARDADO' : 'GUARDADO EN BD'}
                </div>
              </div>
              {(applyResult as any).commit_error && (
                <div className="mt-2 bg-red-100 border border-red-300 rounded p-2 text-xs text-red-800 font-mono">
                  {(applyResult as any).commit_error}
                </div>
              )}
            </div>

            {/* Categorized breakdown */}
            {applyLines.length > 0 && (
              <>
                {/* Group by status */}
                {(() => {
                  const applied = applyLines.filter((l: any) => l.status === 'applied')
                  const skipped = applyLines.filter((l: any) => l.status === 'skipped')
                  const errors = applyLines.filter((l: any) => l.status === 'error')

                  // Group skipped by reason
                  const byReason: Record<string, any[]> = {}
                  for (const l of skipped) {
                    const r = l.reason || 'desconocido'
                    if (!byReason[r]) byReason[r] = []
                    byReason[r].push(l)
                  }

                  return (
                    <div className="space-y-3">
                      {/* Applied summary */}
                      {applied.length > 0 && (
                        <details open className="text-xs">
                          <summary className="font-medium text-green-700 cursor-pointer">
                            {applied.length} aplicadas — se crearon asignaciones y pagos
                          </summary>
                          <div className="mt-1 max-h-[200px] overflow-y-auto border rounded bg-white">
                            <table className="w-full text-[11px]">
                              <thead className="bg-green-50 sticky top-0">
                                <tr>
                                  <th className="text-left px-2 py-1">#</th>
                                  <th className="text-left px-2 py-1">Driver</th>
                                  <th className="text-left px-2 py-1">Scout</th>
                                  <th className="text-left px-2 py-1">Que se hizo</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {applied.slice(0, 50).map((l: any, i: number) => (
                                  <tr key={i} className="bg-green-50">
                                    <td className="px-2 py-1 text-gray-400">{l.source_row}</td>
                                    <td className="px-2 py-1 font-mono">{l.driver_id || l.licencia || '-'}</td>
                                    <td className="px-2 py-1">{l.scout || '-'}</td>
                                    <td className="px-2 py-1 text-green-700">{(l.what_happened || []).join(' | ')}</td>
                                  </tr>
                                ))}
                                {applied.length > 50 && (
                                  <tr><td colSpan={4} className="text-center text-gray-400 py-1">... y {applied.length - 50} mas</td></tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </details>
                      )}

                      {/* Skipped grouped by reason */}
                      {skipped.length > 0 && (
                        <details className="text-xs">
                          <summary className="font-medium text-yellow-700 cursor-pointer">
                            {skipped.length} saltadas — agrupadas por motivo
                          </summary>
                          <div className="mt-2 space-y-2">
                            {Object.entries(byReason).map(([reason, lines]) => (
                              <details key={reason} className="ml-2">
                                <summary className="text-gray-600 cursor-pointer">
                                  {reason} ({lines.length})
                                </summary>
                                <div className="max-h-[150px] overflow-y-auto border rounded bg-white mt-1">
                                  <table className="w-full text-[11px]">
                                    <thead className="bg-yellow-50 sticky top-0">
                                      <tr>
                                        <th className="text-left px-2 py-1">#</th>
                                        <th className="text-left px-2 py-1">Licencia</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                      {lines.slice(0, 30).map((l: any, i: number) => (
                                        <tr key={i}>
                                          <td className="px-2 py-1 text-gray-400">{l.source_row}</td>
                                          <td className="px-2 py-1 font-mono">{l.licencia || '-'}</td>
                                        </tr>
                                      ))}
                                      {lines.length > 30 && (
                                        <tr><td colSpan={2} className="text-center text-gray-400 py-1">... y {lines.length - 30} mas</td></tr>
                                      )}
                                    </tbody>
                                  </table>
                                </div>
                              </details>
                            ))}
                          </div>
                        </details>
                      )}

                      {/* Errors */}
                      {errors.length > 0 && (
                        <details className="text-xs">
                          <summary className="font-medium text-red-600 cursor-pointer">
                            {errors.length} errores tecnicos
                          </summary>
                          <div className="mt-1 max-h-[150px] overflow-y-auto border rounded bg-white">
                            <table className="w-full text-[11px]">
                              <thead className="bg-red-50 sticky top-0">
                                <tr>
                                  <th className="text-left px-2 py-1">#</th>
                                  <th className="text-left px-2 py-1">Error</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {errors.slice(0, 20).map((l: any, i: number) => (
                                  <tr key={i} className="bg-red-50">
                                    <td className="px-2 py-1 text-gray-400">{l.source_row}</td>
                                    <td className="px-2 py-1 text-red-600">{l.reason}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </details>
                      )}
                    </div>
                  )
                })()}
              </>
            )}
          </div>
        )}

        {/* ── Preview summary ── */}
        {preview && (
          <div className="mt-4 space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Paso 3: Resultado de validacion
              </span>
            </div>

            {/* Panel: Error estructural del archivo */}
            {preview.parse_metadata?.structural_error && (
              <div className="bg-red-50 border-2 border-red-300 rounded-lg p-5">
                <div className="flex items-start gap-3">
                  <span className="text-2xl">&#9888;</span>
                  <div className="flex-1 space-y-3">
                    <h3 className="text-base font-semibold text-red-800">
                      Error estructural del archivo
                    </h3>
                    <p className="text-sm text-red-700">
                      El archivo no contiene las columnas requeridas. No se procesaron filas.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                      <div className="bg-white border border-red-200 rounded p-3">
                        <div className="font-medium text-gray-600 mb-1">Columnas esperadas</div>
                        <code className="text-xs text-gray-800">
                          {preview.parse_metadata.expected_columns?.join(', ') || 'licencia, scout, supervisor, pagado, monto_pagado, fecha_pago, observacion'}
                        </code>
                      </div>
                      <div className="bg-white border border-red-200 rounded p-3">
                        <div className="font-medium text-gray-600 mb-1">Columnas encontradas</div>
                        <code className="text-xs text-gray-800">
                          {preview.parse_metadata.columns_detected?.join(', ') || '(ninguna)'}
                        </code>
                      </div>
                    </div>

                    {preview.parse_metadata.suggested_mapping && Object.keys(preview.parse_metadata.suggested_mapping).length > 0 && (
                      <div className="bg-white border border-blue-200 rounded p-3">
                        <div className="font-medium text-blue-700 mb-2 text-sm">Sugerencias de mapeo</div>
                        <div className="space-y-1">
                          {Object.entries(preview.parse_metadata.suggested_mapping).map(([detected, expected]) => (
                            <div key={detected} className="text-xs flex items-center gap-2">
                              <code className="bg-red-100 text-red-700 px-1.5 py-0.5 rounded">{detected}</code>
                              <span className="text-gray-400">→</span>
                              <code className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded">{expected}</code>
                            </div>
                          ))}
                        </div>
                        <p className="text-xs text-gray-500 mt-2">
                          Renombra las columnas en tu archivo para que coincidan con las esperadas.
                        </p>
                      </div>
                    )}

                    {preview.parse_metadata.delimiter_detected && (
                      <div className="text-xs text-gray-500">
                        Delimitador detectado: <code className="bg-gray-100 px-1 rounded">{preview.parse_metadata.delimiter_detected === '\t' ? 'TAB' : preview.parse_metadata.delimiter_detected}</code>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              <MiniStat label="Filas" value={preview.total_rows} color="gray" />
              <MiniStat label="Listas" value={preview.valid_rows} color="green" />
              <MiniStat label="Errores" value={preview.error_rows} color="red" />
              <MiniStat label="Pagos" value={preview.payments_to_create} color="green" />
              <MiniStat label="Asignaciones" value={preview.assignments_to_create + preview.assignments_to_change} color="blue" />
              <MiniStat label="Scouts nuevos" value={preview.scouts_to_create} color="purple" />
              <MiniStat label="Ya pagados" value={preview.already_paid} color="yellow" />
              <MiniStat label="No encontrados" value={preview.drivers_not_found} color="orange" />
              <MiniStat label="Duplicados" value={preview.duplicate_rows} color="red" />
            </div>

            {/* Filas validas */}
            {filteredLines.length > 0 && (
              <details open className="mt-2">
                <summary className="text-xs font-medium text-green-700 cursor-pointer mb-2">
                  {filteredLines.length} filas listas para aplicar
                </summary>
                <div className="overflow-x-auto max-h-[300px] overflow-y-auto border rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="text-left px-2 py-1.5">#</th>
                        <th className="text-left px-2 py-1.5">Licencia</th>
                        <th className="text-left px-2 py-1.5">Scout</th>
                        <th className="text-left px-2 py-1.5">Supervisor</th>
                        <th className="text-center px-2 py-1.5">Pago</th>
                        <th className="text-right px-2 py-1.5">Monto</th>
                        <th className="text-left px-2 py-1.5">Acciones</th>
                        <th className="text-left px-2 py-1.5">Avisos</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {filteredLines.map((l: UnifiedPreviewLine, i: number) => (
                        <tr key={i} className={l.status === 'warning' ? 'bg-yellow-50' : ''}>
                          <td className="px-2 py-1.5 text-gray-400">{l.source_row}</td>
                          <td className="px-2 py-1.5 font-mono">{l.licencia}</td>
                          <td className="px-2 py-1.5">{l.scout}</td>
                          <td className="px-2 py-1.5">{l.supervisor}</td>
                          <td className="px-2 py-1.5 text-center">
                            <span className={`px-1 py-0.5 rounded text-[10px] font-medium ${
                              l.pagado?.toUpperCase() === 'SI' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                            }`}>{l.pagado}</span>
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">
                            {l.monto_pagado > 0 ? `S/ ${l.monto_pagado.toFixed(0)}` : '-'}
                          </td>
                          <td className="px-2 py-1.5">
                            <div className="flex flex-wrap gap-0.5">
                              {l.deduced_actions.map((a: string, j: number) => (
                                <span key={j} className={`px-1 py-0.5 rounded text-[9px] font-medium ${ACTION_COLORS[a] || 'bg-gray-100'}`}>
                                  {ACTION_LABELS[a] || a}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="px-2 py-1.5 text-yellow-600 max-w-[150px] truncate">
                            {l.warnings[0] || ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            {/* Filas con error */}
            {errorLines.length > 0 && (
              <details className="mt-2">
                <summary className="text-xs font-medium text-red-600 cursor-pointer mb-2">
                  {errorLines.length} filas requieren correccion
                </summary>
                <div className="overflow-x-auto max-h-[200px] overflow-y-auto border border-red-200 rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-red-50 sticky top-0">
                      <tr>
                        <th className="text-left px-2 py-1.5">#</th>
                        <th className="text-left px-2 py-1.5">Licencia</th>
                        <th className="text-left px-2 py-1.5">Scout</th>
                        <th className="text-left px-2 py-1.5">Errores</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-red-100">
                      {errorLines.map((l: UnifiedPreviewLine, i: number) => (
                        <tr key={i} className="bg-red-50">
                          <td className="px-2 py-1.5 text-gray-400">{l.source_row}</td>
                          <td className="px-2 py-1.5 font-mono">{l.licencia}</td>
                          <td className="px-2 py-1.5">{l.scout}</td>
                          <td className="px-2 py-1.5 text-red-600">
                            {l.errors.map((e: string, j: number) => (
                              <div key={j}>• {e}</div>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* SECCION 2: Contraste con realidad (conciliacion) */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          Contraste opcional — Compara el sistema contra pagos reales
        </h3>

        {/* Filtros */}
        <div className="flex flex-wrap gap-2 items-end mb-4">
          <div>
            <label className="block text-[11px] text-gray-400 mb-0.5">Desde</label>
            <input type="date" value={reconFilters.hire_date_from}
              onChange={(e) => setReconFilters({ ...reconFilters, hire_date_from: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1 text-xs w-32" />
          </div>
          <div>
            <label className="block text-[11px] text-gray-400 mb-0.5">Hasta</label>
            <input type="date" value={reconFilters.hire_date_to}
              onChange={(e) => setReconFilters({ ...reconFilters, hire_date_to: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1 text-xs w-32" />
          </div>
          <div>
            <label className="block text-[11px] text-gray-400 mb-0.5">Esquema</label>
            <select value={reconFilters.scheme_type}
              onChange={(e) => setReconFilters({ ...reconFilters, scheme_type: e.target.value })}
              className="border border-gray-300 rounded px-2 py-1 text-xs bg-white">
              <option value="">Todos</option>
              <option value="cabinet">Cabinet</option>
              <option value="fleet">Fleet</option>
            </select>
          </div>

          <button onClick={handleExportSystemState}
            className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700">
            Exportar estado del sistema
          </button>

          <label className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 cursor-pointer">
            Comparar archivo externo
            <input type="file" accept=".csv,.txt" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCompare(f) }} />
          </label>
        </div>

        {/* ── Contraste results ── */}
        {compareResult && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              <MiniStat label="En archivo" value={compareResult.total_rows} color="gray" />
              <MiniStat label="Coinciden" value={compareResult.matched_rows} color="green" />
              <MiniStat label="Diferencias" value={compareResult.unmatched_rows} color="red" />
              <MiniStat label="Monto distinto" value={compareResult.amount_mismatch} color="orange" />
              <MiniStat label="Ya pagados" value={compareResult.already_paid} color="yellow" />
              <MiniStat label="No en sistema" value={compareResult.missing_in_system} color="red" />
            </div>

            {compareResult.suggested_actions.length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded p-2 text-xs text-blue-700">
                {compareResult.suggested_actions.map((a, i) => (
                  <div key={i}>• {a}</div>
                ))}
              </div>
            )}

            <div className="flex flex-wrap gap-1">
              {['all', 'issues', 'amount_mismatch', 'already_paid', 'missing_in_system', 'scout_mismatch'].map((s) => (
                <button key={s} onClick={() => setReconStatusFilter(s)}
                  className={`px-2 py-0.5 text-[10px] rounded-full border ${
                    reconStatusFilter === s ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-500 border-gray-300'
                  }`}>
                  {s === 'all' ? 'Todos' : s === 'issues' ? 'Con diferencias' : (RECON_STATUS_LABELS[s] || s)}
                </button>
              ))}
            </div>

            <div className="overflow-x-auto max-h-[250px] overflow-y-auto border rounded">
              <table className="w-full text-[11px]">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-2 py-1.5">Driver</th>
                    <th className="text-left px-2 py-1.5">Estado</th>
                    <th className="text-left px-2 py-1.5">Motivo</th>
                    <th className="text-right px-2 py-1.5">Sistema</th>
                    <th className="text-right px-2 py-1.5">Archivo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredRecon.map((d: ReconciliationDetail, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-2 py-1.5 font-mono">{d.driver_id || '-'}</td>
                      <td className="px-2 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${RECON_STATUS_COLORS[d.status] || 'bg-gray-100'}`}>
                          {RECON_STATUS_LABELS[d.status] || d.status}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-gray-500 max-w-[180px] truncate">{d.reason}</td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {d.system_amount != null ? `S/ ${(d.system_amount).toFixed(0)}` : '-'}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {d.upload_amount != null ? `S/ ${(d.upload_amount).toFixed(0)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!compareResult && (
          <p className="text-xs text-gray-400 mt-2">
            Sube un archivo externo con columnas <code className="bg-gray-100 px-1 rounded">driver_id</code> y <code className="bg-gray-100 px-1 rounded">amount_paid</code> para detectar diferencias contra lo que el sistema espera.
          </p>
        )}
      </div>
    </div>
  )
}

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  const textColors: Record<string, string> = {
    green: 'text-green-700', red: 'text-red-600', blue: 'text-blue-700',
    orange: 'text-orange-600', yellow: 'text-yellow-700', purple: 'text-purple-700',
    gray: 'text-gray-600',
  }
  return (
    <div className="bg-gray-50 rounded p-2 text-center">
      <div className="text-[10px] text-gray-400">{label}</div>
      <div className={`text-sm font-bold ${textColors[color] || 'text-gray-700'}`}>{value}</div>
    </div>
  )
}
