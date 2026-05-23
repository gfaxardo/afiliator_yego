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
  previewObservedAffiliations,
  applyObservedAffiliations,
  getObservedExportUrl,
  type ObservedPreviewResponse,
  type ObservedApplyResponse,
  type ObservedPreviewLine,
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

function escapeCsvField(val: any): string {
  if (val === null || val === undefined) return ''
  let s = String(val)
  // CSV injection prevention: prepend apostrophe if starts with = + - @
  if (/^[=+\-@]/.test(s)) s = "'" + s
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    s = '"' + s.replace(/"/g, '""') + '"'
  }
  return s
}

function makeCsvLine(fields: any[]): string {
  return fields.map(escapeCsvField).join(',')
}

function buildTimestamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function buildPreviewLookup(previewLines: any[]): Map<number, any> {
  const m = new Map<number, any>()
  for (const p of previewLines) {
    const sr = p.source_row ?? p.row
    if (sr != null) m.set(Number(sr), p)
  }
  return m
}

function generateFullAuditCsv(
  previewLines: any[],
  applyLines: UnifiedApplyLine[],
  summary: UnifiedApplySummary | null,
  fileName: string,
  appliedAt: string,
  filter: (line: any, applyLine: UnifiedApplyLine | undefined) => boolean = () => true,
): string {
  // Build apply lookup by source_row
  const applyByRow = new Map<number, UnifiedApplyLine>()
  for (const al of applyLines) {
    const sr = al.source_row ?? al.row
    if (sr != null) applyByRow.set(Number(sr), al)
  }

  const header = [
    // Original columns from input file
    'source_row', 'licencia', 'scout', 'supervisor', 'pagado', 'monto_pagado', 'fecha_pago',
    'observacion', 'driver_id', 'nombre_conductor', 'origen', 'tipo_scout', 'motivo_pago',
    'cohorte_iso',
    // Audit columns
    'row_hash', 'audit_status', 'action', 'saved', 'applied', 'rejected', 'conflict',
    'ignored', 'already_paid', 'not_found', 'error_code', 'error_message',
    'what_happened', 'rejection_reason', 'existing_scout_id', 'existing_scout_name',
    'matched_driver_id', 'matched_driver_name', 'matched_license', 'matched_phone',
    'assignment_id', 'payment_id', 'source_file', 'import_batch_id', 'processed_at',
  ]

  const BOM = '\uFEFF'
  const lines = [BOM + makeCsvLine(header)]

  let auditApplied = 0
  let auditRejected = 0
  let auditIgnored = 0
  let auditConflict = 0
  let auditNoChange = 0
  let auditNotFound = 0
  let auditAlreadyPaid = 0

  for (const pl of previewLines) {
    const sr = pl.source_row ?? pl.row
    const applyLine = (sr != null) ? applyByRow.get(Number(sr)) : undefined

    // Determine audit fields
    const previewStatus = pl.status ?? ''
    const previewActions: string[] = pl.deduced_actions ?? []
    const previewErrors: string[] = pl.errors ?? []
    const previewWarnings: string[] = pl.warnings ?? []

    const applyAction = applyLine?.action ?? ''
    const applyStatus = applyLine?.status ?? ''
    const applySaved = applyLine?.saved ?? false
    const applyMessage = applyLine?.message ?? ''
    const applyWhat: string[] = applyLine?.what_happened ?? []

    let auditStatus = 'ok'
    let action = applyAction || 'not_processed'
    let rejected = false
    let conflictFlag = false
    let ignoredFlag = false
    let alreadyPaidFlag = false
    let notFoundFlag = false
    let errorCode = ''
    let errorMessage = ''
    let rejectionReason = ''
    let whatHappened = applyWhat.join(' | ')

    if (previewStatus === 'error' && previewActions.includes('driver_not_found')) {
      auditStatus = 'rejected'; action = 'driver_not_found'; notFoundFlag = true
      rejectionReason = previewErrors.join('; ')
      auditNotFound++
    } else if (previewStatus === 'error') {
      auditStatus = 'rejected'; action = 'validation_error'; rejected = true
      rejectionReason = previewErrors.join('; ')
      errorMessage = rejectionReason
      auditRejected++
    } else if (previewStatus === 'skipped_duplicate') {
      auditStatus = 'ignored'; action = 'skipped_duplicate'; ignoredFlag = true
      rejectionReason = previewWarnings.join('; ')
      auditIgnored++
    } else if (previewStatus === 'warning' && previewActions.includes('already_paid')) {
      auditStatus = 'ok'; action = 'already_paid'; alreadyPaidFlag = true
      whatHappened = 'Pago ya registrado — fila omitida'
      auditAlreadyPaid++
    } else if (!applyLine) {
      auditStatus = 'ignored'; action = previewActions[0] || 'not_processed'; ignoredFlag = true
      rejectionReason = [...previewWarnings, ...previewErrors].join('; ') || 'Fila no procesada'
      auditIgnored++
    } else if (applyAction === 'duplicate_existing') {
      auditStatus = 'ok'; action = 'no_change'
      whatHappened = 'Ya existia asignacion activa'
      auditNoChange++
    } else if (applyAction === 'no_change') {
      auditStatus = 'ok'; action = 'no_change'
      if (!whatHappened) whatHappened = 'Sin cambios'
      auditNoChange++
    } else if (applyAction === 'error') {
      auditStatus = 'rejected'; action = 'error'; rejected = true
      rejectionReason = applyMessage; errorMessage = applyMessage
      auditRejected++
    } else if (applyAction === 'driver_not_found' || applyAction === 'scout_not_found') {
      auditStatus = 'rejected'; notFoundFlag = true
      rejectionReason = applyMessage
      auditNotFound++
    } else if (applyAction === 'already_paid') {
      alreadyPaidFlag = true
      auditAlreadyPaid++
    } else if (applyAction === 'conflict_existing_active_scout') {
      auditStatus = 'conflict'; conflictFlag = true
      rejectionReason = applyMessage
      auditConflict++
    } else if (applyAction === 'created_assignment' || applyAction === 'reactivated_assignment') {
      auditStatus = 'ok'; auditApplied++
    } else if (applyAction === 'created_payment_history') {
      auditStatus = 'ok'; auditApplied++
    }

    if (!whatHappened) {
      if (action === 'not_processed') whatHappened = 'Fila no procesada'
      else if (action === 'no_change') whatHappened = 'Sin cambios'
      else if (action === 'already_paid') whatHappened = 'Pago ya registrado'
      else if (notFoundFlag) whatHappened = 'Driver no encontrado'
      else if (ignoredFlag) whatHappened = 'Fila ignorada: ' + rejectionReason
      else if (rejected) whatHappened = 'Fila rechazada: ' + rejectionReason
    }

    const isApplied = applySaved && auditStatus === 'ok' &&
      !['not_processed', 'no_change', 'skipped_duplicate'].includes(action)

    const rowHashRaw = `${pl.licencia ?? ''}|${pl.scout ?? ''}|${pl.supervisor ?? ''}|${pl.monto_pagado ?? ''}`
    let rowHash = ''
    try {
      // Simple hash
      let h = 0
      for (let i = 0; i < rowHashRaw.length; i++) {
        h = ((h << 5) - h) + rowHashRaw.charCodeAt(i); h |= 0
      }
      rowHash = Math.abs(h).toString(16).slice(0, 12).padStart(12, '0')
    } catch { /* ignore */ }

    if (!filter(pl, applyLine)) continue

    lines.push(makeCsvLine([
      sr ?? '',
      pl.licencia ?? '',
      pl.scout ?? '',
      pl.supervisor ?? '',
      pl.pagado ?? '',
      pl.monto_pagado ?? '',
      pl.fecha_pago ?? '',
      pl.observacion ?? '',
      pl.driver_id_resolved ?? '',
      pl.nombre_conductor ?? '',
      pl.origen ?? '',
      pl.tipo_scout ?? '',
      pl.motivo_pago ?? '',
      pl.cohorte_iso ?? '',
      rowHash,
      auditStatus,
      action,
      applySaved ? 'true' : 'false',
      isApplied ? 'true' : 'false',
      rejected ? 'true' : 'false',
      conflictFlag ? 'true' : 'false',
      ignoredFlag ? 'true' : 'false',
      alreadyPaidFlag ? 'true' : 'false',
      notFoundFlag ? 'true' : 'false',
      errorCode,
      errorMessage,
      whatHappened,
      rejectionReason,
      pl.scout_id_resolved ?? '',
      pl.scout ?? '',
      pl.driver_id_resolved ?? '',
      pl.nombre_conductor ?? '',
      pl.licencia ?? '',
      '',
      '',
      '',
      fileName,
      '',
      appliedAt,
    ]))
  }

  return lines.join('\n')
}

function generateAuditSummaryCsv(
  previewLines: any[],
  applyLines: UnifiedApplyLine[],
  summary: UnifiedApplySummary | null,
  fileName: string,
  appliedAt: string,
): string {
  const BOM = '\uFEFF'
  const lines: string[] = [BOM + 'metrica,valor']
  const add = (k: string, v: any) => lines.push(makeCsvLine([k, v]))
  add('file_name', fileName)
  add('processed_at', appliedAt)
  add('audit_total_rows', previewLines.length)
  add('apply_total_rows', applyLines.length)
  add('total_rows', summary?.total_rows ?? previewLines.length)
  add('applied', summary?.applied ?? 0)
  add('no_change', summary?.no_change ?? 0)
  add('conflicts', summary?.conflicts ?? 0)
  add('already_paid', summary?.already_paid ?? 0)
  add('not_found', summary?.not_found ?? 0)
  add('errors', summary?.errors ?? 0)
  add('commit_ok', String(summary?.commit_ok ?? true))
  add('commit_error', summary?.commit_error ?? '')
  add('audit_matches_input', String(previewLines.length === (summary?.total_rows ?? previewLines.length)))
  return lines.join('\n')
}

function triggerCsvDownload(csvContent: string, filename: string) {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function CentroCargaView() {
  const [loadType, setLoadType] = useState<'unified' | 'observed'>('unified')

  const [preview, setPreview] = useState<UnifiedPreviewResponse | null>(null)
  const [previewStreamLines, setPreviewStreamLines] = useState<any[]>([])
  const [applySummary, setApplySummary] = useState<UnifiedApplySummary | null>(null)
  const [applyLines, setApplyLines] = useState<UnifiedApplyLine[]>([])
  const [appliedAt, setAppliedAt] = useState<string>('')
  const [sourceFileName, setSourceFileName] = useState<string>('')
  const [applyActionFilter, setApplyActionFilter] = useState<string>('all')
  const pendingFileRef = useRef<File | null>(null)

  const [observedPreview, setObservedPreview] = useState<ObservedPreviewResponse | null>(null)
  const [observedApplyResult, setObservedApplyResult] = useState<ObservedApplyResponse | null>(null)
  const [observedLoading, setObservedLoading] = useState(false)
  const [observedError, setObservedError] = useState<string | null>(null)

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
    setPreviewStreamLines([]); setStreamLines([]); setStreamProgress({ progress: 0, total: 0 })
    pendingFileRef.current = file
    setSourceFileName(file.name)

    await previewUnifiedLoadStream(
      file,
      (line) => {
        setStreamLines(prev => [...prev, line])
        setPreviewStreamLines(prev => [...prev, line])
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
          assignments_already_exist: 0,
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
        setAppliedAt(new Date().toISOString())
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

  // ── Descarga de reportes post-apply ──
  const previewLookup = useMemo(() => {
    return buildPreviewLookup(previewStreamLines)
  }, [previewStreamLines])

  const downloadFullReport = useCallback(async () => {
    const ts = buildTimestamp()
    try {
      const response = await fetch('/api/scout-liq/unified-load/report/full-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preview_lines: previewStreamLines,
          apply_lines: applyLines,
          file_name: sourceFileName,
          preview_result: preview || {},
          apply_summary: applySummary || {},
        }),
      })
      if (!response.ok) {
        // Fallback to client-side generation
        const csv = generateFullAuditCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt)
        triggerCsvDownload(csv, `apply_full_audit_report_${ts}.csv`)
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `apply_full_audit_report_${ts}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // Fallback: client-side generation
      const csv = generateFullAuditCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt)
      triggerCsvDownload(csv, `apply_full_audit_report_${ts}.csv`)
    }
  }, [previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt, preview])

  const downloadSummaryCsv = useCallback(async () => {
    const ts = buildTimestamp()
    try {
      const response = await fetch('/api/scout-liq/unified-load/report/summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preview_lines: previewStreamLines,
          apply_lines: applyLines,
          file_name: sourceFileName,
          preview_result: preview || {},
          apply_summary: applySummary || {},
        }),
      })
      if (!response.ok) {
        const csv = generateAuditSummaryCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt)
        triggerCsvDownload(csv, `apply_summary_${ts}.csv`)
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `apply_summary_${ts}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      const csv = generateAuditSummaryCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt)
      triggerCsvDownload(csv, `apply_summary_${ts}.csv`)
    }
  }, [previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt, preview])

  const downloadProblemsCsv = useCallback(() => {
    const ts = buildTimestamp()
    const csv = generateFullAuditCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt, (_pl, al) => {
      const a = al?.action ?? ''
      const s = al?.status ?? ''
      return s !== 'ok' || a === 'driver_not_found' || a === 'scout_not_found'
        || a === 'conflict_existing_active_scout' || a === 'error' || a === 'already_paid'
        || a === 'duplicate_existing'
    })
    triggerCsvDownload(csv, `apply_problems_${ts}.csv`)
  }, [previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt])

  const downloadConflictsCsv = useCallback(() => {
    const ts = buildTimestamp()
    const csv = generateFullAuditCsv(previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt, (_pl, al) => {
      const a = al?.action ?? ''
      return a === 'conflict_existing_active_scout' || al?.status === 'manual_review'
    })
    triggerCsvDownload(csv, `apply_conflicts_${ts}.csv`)
  }, [previewStreamLines, applyLines, applySummary, sourceFileName, appliedAt])

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

      {/* ── Load Type Selector ── */}
      <div className="flex gap-2">
        <button
          onClick={() => setLoadType('unified')}
          className={`px-4 py-1.5 rounded-full text-xs font-medium transition ${
            loadType === 'unified'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Asignaciones Oficiales
        </button>
        <button
          onClick={() => setLoadType('observed')}
          className={`px-4 py-1.5 rounded-full text-xs font-medium transition ${
            loadType === 'observed'
              ? 'bg-amber-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Atribuciones Observadas
        </button>
      </div>

      {loadType === 'observed' ? (
        <ObservedLoadPanel
          preview={observedPreview}
          applyResult={observedApplyResult}
          loading={observedLoading}
          error={observedError}
          onPreview={async (file: File) => {
            setObservedLoading(true)
            setObservedError(null)
            setObservedPreview(null)
            setObservedApplyResult(null)
            try {
              const result = await previewObservedAffiliations(file)
              setObservedPreview(result)
            } catch (e: any) {
              setObservedError(e?.response?.data?.detail || e?.message || 'Error en preview')
            } finally {
              setObservedLoading(false)
            }
          }}
          onApply={async (file: File) => {
            setObservedLoading(true)
            setObservedError(null)
            setObservedApplyResult(null)
            try {
              const result = await applyObservedAffiliations(file)
              setObservedApplyResult(result)
            } catch (e: any) {
              setObservedError(e?.response?.data?.detail || e?.message || 'Error al aplicar')
            } finally {
              setObservedLoading(false)
            }
          }}
        />
      ) : (
        <>
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

            {/* ── Auditoria y descarga post-apply ── */}
            <div className="space-y-2 pt-2 border-t border-gray-100">
              {/* NO GO warning */}
              {(() => {
                const auditRows = previewStreamLines.length
                const inputRows = preview?.total_rows ?? 0
                const mismatch = auditRows > 0 && inputRows > 0 && auditRows !== inputRows
                return mismatch ? (
                  <div className="bg-red-100 border-2 border-red-400 rounded-lg p-3 flex items-start gap-2">
                    <span className="text-xl">{'\u26A0'}</span>
                    <div>
                      <div className="text-sm font-bold text-red-800">NO GO: el reporte no cubre todas las filas del archivo.</div>
                      <div className="text-xs text-red-600 mt-0.5">
                        Filas en archivo: {inputRows} | Filas en auditoria: {auditRows} | Diferencia: {Math.abs(auditRows - inputRows)} filas omitidas
                      </div>
                    </div>
                  </div>
                ) : auditRows > 0 ? (
                  <div className="bg-green-50 border border-green-200 rounded px-3 py-1.5 text-xs text-green-700">
                    Auditoria completa: {auditRows} filas en archivo = {auditRows} filas en reporte
                  </div>
                ) : null
              })()}

              {/* Stats row */}
              {previewStreamLines.length > 0 && (
                <div className="grid grid-cols-4 md:grid-cols-8 gap-1.5">
                  <MiniStat label="Filas archivo" value={previewStreamLines.length} color="gray" />
                  <MiniStat label="En reporte" value={previewStreamLines.length} color="gray" />
                  <MiniStat label="Procesadas" value={applySummary?.applied ?? 0} color="green" />
                  <MiniStat label="Sin cambios" value={applySummary?.no_change ?? 0} color="gray" />
                  <MiniStat label="Rechazadas" value={Math.max(0, (preview?.error_rows ?? 0) + (applySummary?.errors ?? 0) - (preview?.drivers_not_found ?? 0))} color="red" />
                  <MiniStat label="Ignoradas" value={Math.max(0, (preview?.duplicate_rows ?? 0))} color="orange" />
                  <MiniStat label="Conflictos" value={applySummary?.conflicts ?? 0} color="red" />
                  <MiniStat label="No encontrados" value={Math.max(0, (applySummary?.not_found ?? 0) + (preview?.drivers_not_found ?? 0))} color="orange" />
                </div>
              )}

              {applyLines.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  <button onClick={downloadFullReport}
                    className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors font-medium">
                    Descargar auditoria completa ({previewStreamLines.length} filas)
                  </button>
                  <button onClick={downloadSummaryCsv}
                    className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors">
                    Descargar resumen
                  </button>
                  <button onClick={downloadProblemsCsv}
                    className="px-3 py-1.5 text-xs bg-orange-500 text-white rounded hover:bg-orange-600 transition-colors">
                    Descargar problemas
                  </button>
                  <button onClick={downloadConflictsCsv}
                    className="px-3 py-1.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 transition-colors">
                    Descargar conflictos
                  </button>
                </div>
              )}
            </div>
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
        </>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// OBSERVED LOAD PANEL
// ═══════════════════════════════════════════════════════════════════════════

function ObservedLoadPanel({
  preview,
  applyResult,
  loading,
  error,
  onPreview,
  onApply,
}: {
  preview: ObservedPreviewResponse | null
  applyResult: ObservedApplyResponse | null
  loading: boolean
  error: string | null
  onPreview: (file: File) => void
  onApply: (file: File) => void
}) {
  const [file, setFile] = useState<File | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      onPreview(f)
    }
  }

  const handleApply = () => {
    if (file) onApply(file)
  }

  const handleExport = () => {
    const url = getObservedExportUrl()
    const a = document.createElement('a')
    a.href = url
    a.download = 'atribuciones_observadas.csv'
    a.click()
  }

  const matchBadge = (status: string | null) => {
    const m: Record<string, { label: string; cls: string }> = {
      matched: { label: 'Match', cls: 'bg-green-100 text-green-700' },
      unmatched: { label: 'Sin match', cls: 'bg-red-100 text-red-700' },
      manual_review: { label: 'Revision', cls: 'bg-yellow-100 text-yellow-700' },
    }
    const s = status || 'pending'
    const b = m[s] || { label: s, cls: 'bg-gray-100 text-gray-500' }
    return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${b.cls}`}>{b.label}</span>
  }

  const officialBadge = (status: string | null) => {
    const m: Record<string, { label: string; cls: string }> = {
      official_found: { label: 'Oficial OK', cls: 'bg-green-100 text-green-700' },
      official_missing: { label: 'Fuera oficial', cls: 'bg-amber-100 text-amber-700' },
      official_unknown: { label: 'Desconocido', cls: 'bg-gray-100 text-gray-500' },
    }
    const s = status || 'official_unknown'
    const b = m[s] || { label: s, cls: 'bg-gray-100 text-gray-500' }
    return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${b.cls}`}>{b.label}</span>
  }

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-lg border border-amber-200 bg-amber-50">
        <h3 className="text-sm font-semibold text-amber-800 mb-2">Atribuciones Observadas</h3>
        <p className="text-xs text-amber-600 mb-3">
          Carga conductores reportados por scouts/supervisores que no aparecen en la fuente oficial.
          Columnas: fecha_afiliacion, origen, scout, supervisor, nombre_driver, licencia, telefono.
        </p>

        <input
          type="file"
          accept=".csv,.xlsx"
          onChange={handleFileChange}
          disabled={loading}
          className="text-xs"
        />

        {loading && (
          <div className="mt-2 text-xs text-amber-700">Procesando...</div>
        )}

        {error && (
          <div className="mt-2 bg-red-50 border border-red-200 text-red-700 rounded p-2 text-xs">{error}</div>
        )}
      </div>

      {/* Preview */}
      {preview && (
        <div className="space-y-3">
          {/* Summary stats */}
          <div className="grid grid-cols-4 gap-2">
            <div className="bg-white border rounded p-2 text-center">
              <div className="text-[10px] text-gray-400">Total</div>
              <div className="text-sm font-bold">{preview.summary.total}</div>
            </div>
            <div className="bg-green-50 border border-green-200 rounded p-2 text-center">
              <div className="text-[10px] text-green-600">Match High</div>
              <div className="text-sm font-bold text-green-700">{preview.summary.matched_high}</div>
            </div>
            <div className="bg-blue-50 border border-blue-200 rounded p-2 text-center">
              <div className="text-[10px] text-blue-600">Match Medium</div>
              <div className="text-sm font-bold text-blue-700">{preview.summary.matched_medium}</div>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded p-2 text-center">
              <div className="text-[10px] text-amber-600">Official Missing</div>
              <div className="text-sm font-bold text-amber-700">{preview.summary.official_missing}</div>
            </div>
            <div className="bg-yellow-50 border border-yellow-200 rounded p-2 text-center">
              <div className="text-[10px] text-yellow-600">Manual Review</div>
              <div className="text-sm font-bold text-yellow-700">{preview.summary.manual_review}</div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded p-2 text-center">
              <div className="text-[10px] text-red-600">Unmatched</div>
              <div className="text-sm font-bold text-red-700">{preview.summary.unmatched}</div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded p-2 text-center">
              <div className="text-[10px] text-red-600">Errores</div>
              <div className="text-sm font-bold text-red-700">{preview.summary.errors}</div>
            </div>
            <div className="bg-white border rounded p-2 text-center">
              <div className="text-[10px] text-gray-400">Validos</div>
              <div className="text-sm font-bold">{preview.summary.valid}</div>
            </div>
          </div>

          {/* Apply + Actions */}
          <div className="flex gap-2">
            <button
              onClick={handleApply}
              disabled={preview.summary.valid === 0}
              className="px-4 py-2 bg-amber-600 text-white rounded text-xs font-medium hover:bg-amber-700 disabled:opacity-50"
            >
              Guardar Atribuciones ({preview.summary.valid})
            </button>
            <button
              onClick={handleExport}
              className="px-4 py-2 bg-white border border-gray-300 rounded text-xs text-gray-600 hover:bg-gray-50"
            >
              Exportar CSV
            </button>
          </div>

          {/* Lines table */}
          {preview.lines.length > 0 && (
            <div className="overflow-x-auto max-h-[400px] overflow-y-auto border rounded">
              <table className="w-full text-[11px]">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-2 py-1.5">#</th>
                    <th className="text-left px-2 py-1.5">Fecha</th>
                    <th className="text-left px-2 py-1.5">Scout</th>
                    <th className="text-left px-2 py-1.5">Supervisor</th>
                    <th className="text-left px-2 py-1.5">Licencia</th>
                    <th className="text-left px-2 py-1.5">Telefono</th>
                    <th className="text-left px-2 py-1.5">Driver ID</th>
                    <th className="text-left px-2 py-1.5">Match</th>
                    <th className="text-left px-2 py-1.5">Oficial</th>
                    <th className="text-left px-2 py-1.5">Review</th>
                    <th className="text-left px-2 py-1.5">Motivo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {preview.lines.map((l, i) => (
                    <tr key={i} className={l.has_error ? 'bg-red-50' : ''}>
                      <td className="px-2 py-1.5 text-gray-400">{l.row}</td>
                      <td className="px-2 py-1.5 font-mono">{l.fecha_afiliacion || '-'}</td>
                      <td className="px-2 py-1.5">{l.scout || '-'}</td>
                      <td className="px-2 py-1.5">{l.supervisor || '-'}</td>
                      <td className="px-2 py-1.5 font-mono">{l.licencia || '-'}</td>
                      <td className="px-2 py-1.5 font-mono">{l.telefono || '-'}</td>
                      <td className="px-2 py-1.5 font-mono text-[10px] max-w-[120px] truncate">{l.matched_driver_id || '-'}</td>
                      <td className="px-2 py-1.5">{matchBadge(l.match_status)}</td>
                      <td className="px-2 py-1.5">{officialBadge(l.official_source_status)}</td>
                      <td className="px-2 py-1.5">{l.review_status || '-'}</td>
                      <td className="px-2 py-1.5 text-gray-500 max-w-[200px] truncate">{l.match_reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Apply Result */}
      {applyResult && (
        <div className={`p-3 rounded-lg border ${
          applyResult.errors > 0 ? 'bg-yellow-50 border-yellow-200' : 'bg-green-50 border-green-200'
        }`}>
          <p className="text-xs font-medium">
            {applyResult.saved > 0 ? `Guardado: ${applyResult.saved} atribuciones` : ''}
            {applyResult.duplicates > 0 ? `, ${applyResult.duplicates} duplicados` : ''}
            {applyResult.errors > 0 ? `, ${applyResult.errors} errores` : ''}
          </p>
          {applyResult.error_details?.length > 0 && (
            <div className="mt-2 text-[10px] text-red-600 space-y-0.5">
              {applyResult.error_details.map((e, i) => (
                <div key={i}>Fila {e.row}: {e.error}</div>
              ))}
            </div>
          )}
        </div>
      )}
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
