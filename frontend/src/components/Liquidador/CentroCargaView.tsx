import { useState, useCallback, useRef, useMemo } from 'react'
import {
  downloadTemplate,
  previewUnifiedLoadStream,
  applyUnifiedLoadStream,
  type UnifiedPreviewResponse,
  type UnifiedPreviewLine,
  type UnifiedApplyLine,
  type UnifiedApplySummary,
  type UnifiedApplyAction,
} from '../../api/unifiedLoad'
import {
  exportReconciliationCsv,
  compareUpload,
  type ReconciliationCompareResponse,
  type ReconciliationDetail,
} from '../../api/reconciliation'

const PREVIEW_ACTION_LABELS: Record<string, string> = {
  create_scout: 'Crear Scout', assign_scout: 'Asignar Scout',
  assign_to_new_scout: 'Asignar a Nuevo Scout', reassign_scout: 'Reasignar',
  create_payment: 'Crear Pago', already_paid: 'Ya Pagado',
  attribution_only: 'Solo Atribucion', driver_not_found: 'Driver No Encontrado',
}

const PREVIEW_ACTION_COLORS: Record<string, string> = {
  create_scout: 'bg-purple-100 text-purple-700', assign_scout: 'bg-blue-100 text-blue-700',
  assign_to_new_scout: 'bg-blue-100 text-blue-700', reassign_scout: 'bg-orange-100 text-orange-700',
  create_payment: 'bg-green-100 text-green-700', already_paid: 'bg-yellow-100 text-yellow-700',
  attribution_only: 'bg-gray-100 text-gray-600', driver_not_found: 'bg-red-100 text-red-700',
}

const APPLY_ACTION_LABEL: Record<string, string> = {
  created_assignment: 'Asignacion creada',
  reactivated_assignment: 'Asignacion reactivada',
  created_payment_history: 'Pago creado',
  no_change: 'Sin cambios',
  already_paid: 'Ya pagado',
  driver_not_found: 'Driver no encontrado',
  scout_not_found: 'Scout no encontrado',
  duplicate_existing: 'Duplicado',
  conflict_existing_active_scout: 'Conflicto de scout',
  error: 'Error',
  validation_error: 'Error validacion',
}

const APPLY_ACTION_COLOR: Record<string, string> = {
  created_assignment: 'bg-blue-100 text-blue-700',
  reactivated_assignment: 'bg-indigo-100 text-indigo-700',
  created_payment_history: 'bg-green-100 text-green-700',
  no_change: 'bg-gray-100 text-gray-500',
  already_paid: 'bg-yellow-100 text-yellow-700',
  driver_not_found: 'bg-orange-100 text-orange-700',
  scout_not_found: 'bg-orange-100 text-orange-700',
  duplicate_existing: 'bg-gray-100 text-gray-500',
  conflict_existing_active_scout: 'bg-red-100 text-red-700',
  error: 'bg-red-100 text-red-700',
  validation_error: 'bg-red-100 text-red-700',
}

type ApplyFinalState = 'GUARDADO' | 'GUARDADO_OBS' | 'SIN_CAMBIOS' | 'REQUIERE_REVISION' | 'NO_GUARDADO'

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
  const [preview, setPreview] = useState<UnifiedPreviewResponse | null>(null)
  const [applySummary, setApplySummary] = useState<UnifiedApplySummary | null>(null)
  const [applyLines, setApplyLines] = useState<UnifiedApplyLine[]>([])
  const [applyActionFilter, setApplyActionFilter] = useState<string>('all')
  const pendingFileRef = useRef<File | null>(null)

  const [reconFilters, setReconFilters] = useState({ hire_date_from: '', hire_date_to: '', scheme_type: '' })
  const [compareResult, setCompareResult] = useState<ReconciliationCompareResponse | null>(null)
  const [reconStatusFilter, setReconStatusFilter] = useState<string>('all')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeStep, setActiveStep] = useState<number>(0)

  const [streamLines, setStreamLines] = useState<any[]>([])
  const [streamProgress, setStreamProgress] = useState({ progress: 0, total: 0 })

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

  const handlePreview = useCallback(async (file: File) => {
    setLoading(true); setError(null); setPreview(null); setApplySummary(null); setApplyLines([])
    setStreamLines([]); setStreamProgress({ progress: 0, total: 0 })
    pendingFileRef.current = file

    await previewUnifiedLoadStream(
      file,
      (line) => {
        setStreamLines(prev => [...prev, line])
        setStreamProgress(p => ({
          progress: p.progress + 1,
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

  const handleApply = useCallback(async () => {
    const plan = preview?.apply_plan
    if (!plan || plan.length === 0) return
    setLoading(true); setError(null); setApplySummary(null); setApplyLines([])
    setStreamLines([]); setStreamProgress({ progress: 0, total: 0 })
    setApplyActionFilter('all')

    await applyUnifiedLoadStream(
      plan,
      (line) => {
        setStreamLines(prev => [...prev, line])
        setApplyLines(prev => [...prev, line])
        setStreamProgress(p => ({
          progress: p.progress + 1,
          total: p.total,
        }))
      },
      (summary) => {
        setApplySummary(summary)
        setLoading(false)
        if (summary.commit_ok === false) {
          setError('NO GUARDADO: Los cambios no se guardaron en la base de datos. ' + (summary.commit_error || ''))
        } else if (summary.errors > 0 && summary.applied === 0) {
          setError('NO GUARDADO: Todas las filas fallaron.')
        }
      },
      (err) => {
        setError(err)
        setLoading(false)
      },
    )
  }, [preview])

  const applyFinalState: ApplyFinalState = useMemo(() => {
    const s = applySummary
    if (!s) return 'NO_GUARDADO'
    if (s.commit_ok === false) return 'NO_GUARDADO'
    if (s.errors > 0 && s.applied === 0) return 'NO_GUARDADO'
    if (s.conflicts > 0) return 'REQUIERE_REVISION'
    const created = (s.created_assignment ?? 0) + (s.created_payment_history ?? 0)
    if (created === 0 && s.no_change > 0 && s.errors === 0) return 'SIN_CAMBIOS'
    if (s.errors === 0 && s.no_change > 0) return 'GUARDADO_OBS'
    if (s.errors === 0 && created > 0) return 'GUARDADO'
    if (s.errors > 0 && s.applied > 0) return 'GUARDADO_OBS'
    return 'GUARDADO'
  }, [applySummary])

  const applyFinalStateConfig: Record<ApplyFinalState, { label: string; bg: string; text: string; border: string }> = {
    GUARDADO: { label: 'GUARDADO', bg: 'bg-green-50', text: 'text-green-800', border: 'border-green-300' },
    GUARDADO_OBS: { label: 'GUARDADO CON OBSERVACIONES', bg: 'bg-blue-50', text: 'text-blue-800', border: 'border-blue-300' },
    SIN_CAMBIOS: { label: 'SIN CAMBIOS — La carga ya estaba aplicada', bg: 'bg-gray-50', text: 'text-gray-600', border: 'border-gray-300' },
    REQUIERE_REVISION: { label: 'APLICADO — Requiere revision de conflictos', bg: 'bg-yellow-50', text: 'text-yellow-800', border: 'border-yellow-300' },
    NO_GUARDADO: { label: 'NO GUARDADO', bg: 'bg-red-50', text: 'text-red-800', border: 'border-red-400' },
  }

  const groupedApplyLines = useMemo(() => {
    const groups: Record<string, UnifiedApplyLine[]> = {}
    for (const l of applyLines) {
      const a = l.action || 'unknown'
      if (!groups[a]) groups[a] = []
      groups[a].push(l)
    }
    return groups
  }, [applyLines])

  const filteredApplyLines = useMemo(() => {
    if (applyActionFilter === 'all') return applyLines
    if (applyActionFilter === 'issues') return applyLines.filter(l => l.action === 'error' || l.action === 'conflict_existing_active_scout')
    return applyLines.filter(l => l.action === applyActionFilter)
  }, [applyLines, applyActionFilter])

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
          {preview && preview.valid_rows > 0 && !applySummary && (
            <div className="flex items-center gap-2">
              <button onClick={handleApply} disabled={loading}
                className="px-4 py-2 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
                Paso 4: Aplicar {preview.valid_rows} filas validas
              </button>
              <span className="text-xs text-gray-500">
                ({preview.valid_rows} listas &middot; {preview.error_rows} requieren correccion)
              </span>
            </div>
          )}
        </div>

        {/* ── Streaming log ── */}
        {(loading || streamLines.length > 0) && (
          <div className="mt-3 bg-gray-900 text-green-400 font-mono text-[11px] rounded-lg p-3 max-h-[300px] overflow-y-auto">
            <div className="text-gray-500 mb-1">
              {loading ? 'Procesando...' : 'Completado'} [{streamProgress.progress}/{streamProgress.total}]
            </div>
            {streamLines.slice(-25).map((l, i) => (
              <div key={i} className={
                l.status === 'error' ? 'text-red-400' :
                l.status === 'warning' || l.action === 'already_paid' ? 'text-yellow-400' :
                l.action === 'no_change' || l.action === 'duplicate_existing' ? 'text-gray-400' :
                'text-green-400'
              }>
                [{String(l.source_row).padStart(4, ' ')}] {String(l.licencia || l.driver_id || '---').padEnd(16, ' ')} {l.action ?? l.status ?? '--'} {(l.what_happened || []).join(', ') || (l.errors?.[0] || l.message || '')}
              </div>
            ))}
          </div>
        )}

        {/* ── Apply Result ── */}
        {applySummary && (
          <div className="mt-4 space-y-3">
            {/* Banner principal */}
            {(() => {
              const cfg = applyFinalStateConfig[applyFinalState]
              return (
                <div className={`rounded-lg p-4 border-2 ${cfg.border} ${cfg.bg}`}>
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <div className={`text-lg font-bold ${cfg.text}`}>{cfg.label}</div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {applySummary.applied} filas procesadas
                        {applySummary.commit_error && (
                          <span className="text-red-500 ml-2">({applySummary.commit_error})</span>
                        )}
                      </div>
                    </div>
                    {applyFinalState === 'NO_GUARDADO' && applySummary.commit_error && (
                      <details className="max-w-lg">
                        <summary className="text-[10px] text-red-400 cursor-pointer">Detalle tecnico</summary>
                        <pre className="text-[10px] text-red-300 mt-1 max-h-[120px] overflow-auto">{applySummary.commit_error}</pre>
                      </details>
                    )}
                  </div>
                </div>
              )
            })()}

            {/* Cards resumen */}
            <div className="grid grid-cols-3 md:grid-cols-7 gap-2">
              <MiniStat label="Aplicadas" value={applySummary.applied} color="green" />
              <MiniStat label="Sin cambios" value={applySummary.no_change} color="gray" />
              <MiniStat label="Ya pagados" value={applySummary.already_paid} color="yellow" />
              <MiniStat label="No encontrados" value={applySummary.not_found} color="orange" />
              <MiniStat label="Conflictos" value={applySummary.conflicts} color="red" />
              <MiniStat label="Errores" value={applySummary.errors} color="red" />
              <MiniStat label="Total filas" value={applySummary.total_rows ?? applyLines.length} color="gray" />
            </div>

            {/* Filtros rapidos */}
            <div className="flex flex-wrap gap-1">
              {[
                { key: 'all', label: 'Todas' },
                { key: 'issues', label: 'Con problemas' },
                { key: 'created_assignment', label: 'Creadas' },
                { key: 'created_payment_history', label: 'Pagos creados' },
                { key: 'no_change', label: 'Sin cambios' },
                { key: 'already_paid', label: 'Ya pagados' },
                { key: 'driver_not_found', label: 'No encontrados' },
                { key: 'duplicate_existing', label: 'Duplicados' },
                { key: 'conflict_existing_active_scout', label: 'Conflictos' },
                { key: 'error', label: 'Errores' },
              ].map(({ key, label }) => (
                <button key={key} onClick={() => setApplyActionFilter(key)}
                  className={`px-2 py-0.5 text-[10px] rounded-full border transition-colors ${
                    applyActionFilter === key
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-500 border-gray-300 hover:border-gray-400'
                  }`}>
                  {label}
                </button>
              ))}
            </div>

            {/* Tabla detalle */}
            {filteredApplyLines.length > 0 && (
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto border rounded">
                <table className="w-full text-[11px]">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left px-2 py-1.5">#</th>
                      <th className="text-left px-2 py-1.5">Driver</th>
                      <th className="text-left px-2 py-1.5">Scout</th>
                      <th className="text-left px-2 py-1.5">Accion</th>
                      <th className="text-center px-2 py-1.5 w-16">Guardado</th>
                      <th className="text-left px-2 py-1.5">Mensaje</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredApplyLines.slice(0, 100).map((l, i) => (
                      <tr key={i} className={
                        l.status === 'error' ? 'bg-red-50' :
                        l.status === 'warning' ? 'bg-yellow-50' :
                        l.action === 'no_change' || l.action === 'duplicate_existing' ? 'bg-gray-50' :
                        ''
                      }>
                        <td className="px-2 py-1.5 text-gray-400 font-mono">{l.source_row ?? '-'}</td>
                        <td className="px-2 py-1.5 font-mono text-[10px]">{l.driver_id || l.licencia || '-'}</td>
                        <td className="px-2 py-1.5">{l.scout || l.scout_name || '-'}</td>
                        <td className="px-2 py-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${APPLY_ACTION_COLOR[l.action] || 'bg-gray-100 text-gray-600'}`}>
                            {APPLY_ACTION_LABEL[l.action] || l.action}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          {l.saved
                            ? <span className="text-green-600 font-bold text-xs">SI</span>
                            : <span className="text-gray-400 text-xs">NO</span>
                          }
                        </td>
                        <td className="px-2 py-1.5 text-gray-600 max-w-[200px] truncate" title={l.message}>
                          {l.message}
                        </td>
                      </tr>
                    ))}
                    {filteredApplyLines.length > 100 && (
                      <tr><td colSpan={6} className="text-center text-gray-400 py-1 text-[10px]">... y {filteredApplyLines.length - 100} filas mas</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* Resumen agrupado por accion */}
            {Object.keys(groupedApplyLines).length > 0 && applyLines.length > 0 && (
              <div className="space-y-1">
                {Object.entries(groupedApplyLines).map(([action, lines]) => (
                  <details key={action} className="text-xs">
                    <summary className="cursor-pointer text-gray-600 hover:text-gray-800">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium mr-2 ${APPLY_ACTION_COLOR[action] || 'bg-gray-100 text-gray-600'}`}>
                        {APPLY_ACTION_LABEL[action] || action}
                      </span>
                      {lines.length} fila{lines.length !== 1 ? 's' : ''}
                    </summary>
                    <div className="mt-1 max-h-[120px] overflow-y-auto ml-4 border-l-2 border-gray-100 pl-2">
                      {lines.slice(0, 20).map((l, j) => (
                        <div key={j} className="text-gray-500 py-0.5 flex gap-2">
                          <span className="text-gray-300 w-8 text-right font-mono">{l.source_row ?? '-'}</span>
                          <span className="font-mono text-[10px]">{l.driver_id || l.licencia || '-'}</span>
                          <span className="truncate">{l.message}</span>
                        </div>
                      ))}
                      {lines.length > 20 && (
                        <div className="text-gray-400 text-[10px]">... y {lines.length - 20} mas</div>
                      )}
                    </div>
                  </details>
                ))}
              </div>
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
                                <span key={j} className={`px-1 py-0.5 rounded text-[9px] font-medium ${PREVIEW_ACTION_COLORS[a] || 'bg-gray-100'}`}>
                                  {PREVIEW_ACTION_LABELS[a] || a}
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
