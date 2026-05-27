import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  getSchemes, getScouts, listCutoffs,
  createCutoffFromCohort, createSweepCutoff,
  getCutoffSummary, getCutoffLines,
  reviewPayment, approvePayment, markPaymentPaid, cancelPayment,
  getPaymentExportCsvUrl, getPaymentExportXlsxUrl,
  getPaidHistory, getDashboardAlerts, getCutoffExportFinancialUrl,
  getOperationFilters,
} from '../../api/scoutLiq'
import {
  previewUnifiedLoadStream, applyUnifiedLoadStream, downloadTemplate,
  type UnifiedApplyLine, type UnifiedApplySummary,
  getReconciliationSummary, getIntegrityMetrics,
} from '../../api/unifiedLoad'
import { exportReconciliationCsv } from '../../api/reconciliation'
import type { SchemeResponse } from '../../api/scoutLiq'

// ═══════════════════════════════════════════════════════════════
// SEMANTIC COLOR TOKENS — Strict usage per Priority 6
// ═══════════════════════════════════════════════════════════════

const GREEN = { bg: 'bg-emerald-50', border: 'border-emerald-300', text: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-800', dot: 'bg-emerald-500' }
const YELLOW = { bg: 'bg-amber-50', border: 'border-amber-300', text: 'text-amber-700', badge: 'bg-amber-100 text-amber-800', dot: 'bg-amber-500' }
const RED = { bg: 'bg-red-50', border: 'border-red-300', text: 'text-red-700', badge: 'bg-red-100 text-red-800', dot: 'bg-red-500' }
const BLUE = { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-700', badge: 'bg-blue-100 text-blue-800', dot: 'bg-blue-500' }
const GRAY = { bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-500', badge: 'bg-gray-100 text-gray-600', dot: 'bg-gray-400' }

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type StepStatus = 'pending' | 'in_progress' | 'ready' | 'blocked' | 'completed'
type StepId = 'carga' | 'validacion' | 'revision_bloqueos' | 'revision_warnings' | 'corte' | 'aprobacion' | 'exportacion_pago' | 'historial'
type AttentionLevel = 'critical' | 'warning' | 'operational' | 'analytics'

interface WorkflowStep {
  id: StepId; label: string; description: string; status: StepStatus
  pendingCount: number; ctaLabel: string; subtext: string; enabled: boolean
}

interface CutoffRun {
  id: number; cutoff_name: string; status: string; hire_date_from: string; hire_date_to: string
  cohort_iso_week?: string; scheme_name?: string; created_at?: string
  approved_by?: string; approved_at?: string; paid_at?: string; notes?: string
}

interface Scout { id: number; scout_name: string }

interface AttentionCard {
  id: string; level: AttentionLevel; label: string; count: number
  description: string; cta?: { label: string; action: () => void }; children?: React.ReactNode
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const STEP_ORDER: StepId[] = ['carga', 'validacion', 'revision_bloqueos', 'revision_warnings', 'corte', 'aprobacion', 'exportacion_pago', 'historial']

const STEP_DEF: Record<StepId, { label: string; desc: string; cta: string }> = {
  carga: { label: 'Carga', desc: 'Subir archivo CSV/XLSX con afiliaciones, pagos y atribuciones.', cta: 'Cargar archivo' },
  validacion: { label: 'Validacion', desc: 'Los datos pasan reglas de calidad y consistencia.', cta: 'Validar' },
  revision_bloqueos: { label: 'Bloqueos', desc: 'Items U1: conflictos, duplicados, sin driver. Impiden el pago.', cta: 'Revisar' },
  revision_warnings: { label: 'Warnings', desc: 'U2/U3: anclajes debiles, sin scout, revision manual pendiente.', cta: 'Revisar' },
  corte: { label: 'Corte', desc: 'Crear corte de liquidacion para el periodo actual.', cta: 'Crear corte' },
  aprobacion: { label: 'Aprobacion', desc: 'Revisar detalle del corte y aprobarlo.', cta: 'Aprobar' },
  exportacion_pago: { label: 'Export / Pago', desc: 'Exportar reporte CSV/XLSX y marcar como pagado.', cta: 'Exportar' },
  historial: { label: 'Historial', desc: 'Historial de pagos y reconciliacion de datos.', cta: 'Ver' },
}

const STATUS_ICON: Record<StepStatus, string> = { pending: '○', in_progress: '◉', ready: '●', blocked: '⊗', completed: '✓' }

const APPLY_LABEL: Record<string, string> = {
  created_assignment: 'Asignacion', reactivated_assignment: 'Reactivada', created_payment_history: 'Pago',
  no_change: 'Sin cambios', already_paid: 'Ya pagado', driver_not_found: 'No encontrado',
  driver_not_found_observed_saved: 'Observado', driver_not_found_observed_existing: 'Obs existente',
  scout_not_found: 'Scout ?', duplicate_existing: 'Duplicado', conflict_existing_active_scout: 'Conflicto',
  error: 'Error', validation_error: 'Val error',
}

// ═══════════════════════════════════════════════════════════════
// SUB-COMPONENTS (memoized helpers)
// ═══════════════════════════════════════════════════════════════

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${color}`}>{label}</span>
}

function Dot({ color, pulse }: { color: string; pulse?: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${color} ${pulse ? 'animate-pulse' : ''}`} />
}

const skeletonClass = 'bg-gray-200 rounded animate-pulse'

function Skeleton({ w = 'w-full', h = 'h-4' }: { w?: string; h?: string }) {
  return <div className={`${w} ${h} ${skeletonClass}`} />
}

const DEFAULT_EXPANDED_STEPS: Set<StepId> = new Set(['carga', 'validacion', 'revision_bloqueos', 'revision_warnings'])

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export default function CentroOperativoView() {
  // ── UI mode ──
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable')

  // ── Stepper ──
  const [expandedSteps, setExpandedSteps] = useState<Set<StepId>>(DEFAULT_EXPANDED_STEPS)
  const stepperRef = useRef<HTMLDivElement>(null)

  // ── Carga ──
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [previewSummary, setPreviewSummary] = useState<any>(null)
  const [applyLines, setApplyLines] = useState<UnifiedApplyLine[]>([])
  const [applySummary, setApplySummary] = useState<UnifiedApplySummary | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<string>('')
  const [uploadPhase, setUploadPhase] = useState<'idle' | 'previewing' | 'preview_done' | 'applying' | 'applied'>('idle')
  const [isApplying, setIsApplying] = useState(false)

  // ── Validacion ──
  const [dashboardAlerts, setDashboardAlerts] = useState<any>(null)
  const [loadingValidation, setLoadingValidation] = useState(false)
  const [loadingInitial, setLoadingInitial] = useState(true)

  // ── Corte ──
  const [schemes, setSchemes] = useState<SchemeResponse[]>([])
  const [cutoffs, setCutoffs] = useState<CutoffRun[]>([])
  const [selectedCutoff, setSelectedCutoff] = useState<CutoffRun | null>(null)
  const [cutoffSummaries, setCutoffSummaries] = useState<any[]>([])
  const [cutoffLines, setCutoffLines] = useState<any[]>([])
  const [cutoffLoading, setCutoffLoading] = useState(false)
  const [creatingCutoff, setCreatingCutoff] = useState(false)
  const [cohortWeek, setCohortWeek] = useState('')
  const [originFilter, setOriginFilter] = useState('')
  const [cutoffMode, setCutoffMode] = useState<'cohort' | 'sweep'>('cohort')

  // ── Aprobacion / Pago ──
  const [approving, setApproving] = useState(false)
  const [paying, setPaying] = useState(false)
  const [cancelReason, setCancelReason] = useState('')

  // ── Historial ──
  const [paidHistory, setPaidHistory] = useState<any[]>([])
  const [reconciliationData, setReconciliationData] = useState<any>(null)
  const [loadingHistory, setLoadingHistory] = useState(false)

  // ── Quick filters ──
  const [quickFilter, setQuickFilter] = useState<'all' | 'blocked' | 'warnings' | 'trusted' | 'pending'>('all')
  const [showAnalytics, setShowAnalytics] = useState(false)

  // ── General ──
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // ── Utils ──
  const showMsg = useCallback((msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 4000) }, [])
  const showErr = useCallback((msg: string) => { setError(msg); setTimeout(() => setError(null), 8000) }, [])
  const toggleStep = useCallback((id: StepId) => setExpandedSteps(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  }), [])

  const resetCarga = useCallback(() => {
    setUploadFile(null); setPreviewSummary(null); setApplyLines([])
    setApplySummary(null); setUploadPhase('idle'); setUploadError(null)
  }, [])

  // ── Initial load ──
  useEffect(() => {
    let cancelled = false
    Promise.all([
      getSchemes(), getScouts(), listCutoffs(), getOperationFilters().catch(() => null), getDashboardAlerts().catch(() => null),
    ]).then(([s, sc, c, f, alerts]) => {
      if (cancelled) return
      setSchemes(s); setCutoffs(c)
      if (f) setCohortWeek(f.current_iso_week || '')
      if (alerts) setDashboardAlerts(alerts)
    }).catch((err: any) => { if (!cancelled) setError(err?.response?.data?.detail || err.message) })
      .finally(() => { if (!cancelled) setLoadingInitial(false) })
    return () => { cancelled = true }
  }, [])

  // ═══════════════════════════════════════════════════════════════
  // DERIVED: Step statuses
  // ═══════════════════════════════════════════════════════════════

  const steps = useMemo((): WorkflowStep[] => {
    const cargaStatus: StepStatus = uploadPhase === 'applied' ? 'completed' : uploadPhase === 'preview_done' ? 'ready' : uploadPhase === 'applying' || uploadPhase === 'previewing' ? 'in_progress' : 'pending'
    const validStatus: StepStatus = dashboardAlerts ? ((dashboardAlerts.blocks_true_without_driver_count || 0) + (dashboardAlerts.without_driver_count || 0) === 0 ? 'completed' : 'ready') : cargaStatus === 'completed' ? 'pending' : 'pending'
    const bloqStatus: StepStatus = dashboardAlerts && (dashboardAlerts.blocks_true_without_driver_count || 0) > 0 ? 'blocked' : validStatus === 'completed' ? 'completed' : 'pending'
    const warnsD = dashboardAlerts ? ((dashboardAlerts.manual_review_count || 0) + (dashboardAlerts.without_scout_count || 0)) : 0
    const warnStatus: StepStatus = warnsD > 0 ? 'ready' : validStatus === 'completed' ? 'completed' : 'pending'
    const hasActive = cutoffs.some((c: any) => c.status !== 'cancelled')
    const isApproved = selectedCutoff?.status === 'approved' || selectedCutoff?.status === 'paid'
    const isPaid = selectedCutoff?.status === 'paid'

    const all: { id: StepId; status: StepStatus; pendingCount: number; enabled: boolean; subtext: string }[] = [
      { id: 'carga', status: cargaStatus, pendingCount: previewSummary?.error_rows || 0, enabled: true, subtext: previewSummary ? `${previewSummary.valid_rows} filas validas` : '' },
      { id: 'validacion', status: validStatus, pendingCount: (dashboardAlerts?.blocks_true_without_driver_count || 0) + (dashboardAlerts?.without_driver_count || 0), enabled: cargaStatus === 'completed' || cargaStatus === 'ready' || validStatus !== 'pending', subtext: dashboardAlerts ? `${(dashboardAlerts.blocks_true_without_driver_count || 0) + (dashboardAlerts.without_driver_count || 0)} requieren atencion` : '' },
      { id: 'revision_bloqueos', status: bloqStatus, pendingCount: dashboardAlerts?.blocks_true_without_driver_count || 0, enabled: true, subtext: dashboardAlerts?.blocks_true_without_driver_count > 0 ? `${dashboardAlerts.blocks_true_without_driver_count} bloqueos` : 'Sin bloqueos' },
      { id: 'revision_warnings', status: warnStatus, pendingCount: warnsD, enabled: true, subtext: warnsD > 0 ? `${warnsD} warnings` : 'Sin warnings' },
      { id: 'corte', status: isPaid ? 'completed' : isApproved ? 'completed' : hasActive ? 'ready' : cargaStatus === 'completed' ? 'ready' : 'pending', pendingCount: hasActive ? 0 : 1, enabled: cargaStatus === 'completed' || hasActive, subtext: hasActive ? `${cutoffs.filter(c => c.status !== 'cancelled').length} cortes activos` : '' },
      { id: 'aprobacion', status: isApproved ? 'completed' : hasActive ? 'ready' : 'pending', pendingCount: hasActive && !isApproved ? 1 : 0, enabled: hasActive, subtext: selectedCutoff ? `${selectedCutoff.cutoff_name} (${selectedCutoff.status})` : '' },
      { id: 'exportacion_pago', status: isPaid ? 'completed' : isApproved ? 'ready' : 'pending', pendingCount: isApproved && !isPaid ? 1 : 0, enabled: isApproved, subtext: isPaid ? 'Pagado' : isApproved ? 'Listo para exportar' : '' },
      { id: 'historial', status: (paidHistory.length > 0 || reconciliationData) ? 'completed' : 'pending', pendingCount: 0, enabled: true, subtext: paidHistory.length > 0 ? `${paidHistory.length} registros` : '' },
    ]
    return all.map(a => ({ ...a, label: STEP_DEF[a.id].label, description: STEP_DEF[a.id].desc, ctaLabel: STEP_DEF[a.id].cta }))
  }, [uploadPhase, previewSummary, dashboardAlerts, cutoffs, selectedCutoff, paidHistory, reconciliationData])

  // ═══════════════════════════════════════════════════════════════
  // DERIVED: Attention cards
  // ═══════════════════════════════════════════════════════════════

  const attentionCards = useMemo((): AttentionCard[] => {
    const cards: AttentionCard[] = []
    const alerts = dashboardAlerts
    const hasBlocked = alerts?.blocks_true_without_driver_count > 0 || (applyLines.some(l => l.action === 'error' || l.action === 'conflict_existing_active_scout'))
    const errorLines = applyLines.filter(l => l.action === 'error' || l.action === 'conflict_existing_active_scout').length
    const hasWarnings = (alerts?.manual_review_count > 0) || (alerts?.without_scout_count > 0)

    if (hasBlocked) {
      cards.push({
        id: 'blocked', level: 'critical', label: 'Bloqueados', count: (alerts?.blocks_true_without_driver_count || 0) + errorLines,
        description: 'Items que impiden el pago: conflictos de scout, sin driver, errores de validacion.',
        cta: { label: 'Ver bloqueos', action: () => { toggleStep('revision_bloqueos'); toggleStep('revision_bloqueos') } },
      })
    }
    if (hasWarnings) {
      cards.push({
        id: 'warnings', level: 'warning', label: 'Warnings U2/U3',
        count: (alerts?.manual_review_count || 0) + (alerts?.without_scout_count || 0),
        description: 'No bloquean el pago pero requieren atencion: anclajes debiles, sin scout, revision pendiente.',
        cta: { label: 'Ver warnings', action: () => { toggleStep('revision_warnings'); toggleStep('revision_warnings') } },
      })
    }
    const activeCutoffs = cutoffs.filter(c => c.status !== 'cancelled' && c.status !== 'paid')
    const needsApproval = activeCutoffs.filter(c => c.status === 'reviewed' || c.status === 'calculated' || c.status === 'draft')
    if (needsApproval.length > 0) {
      cards.push({
        id: 'pending_approval', level: 'operational', label: 'Pendientes de aprobacion', count: needsApproval.length,
        description: 'Cortes que requieren revision o aprobacion antes de exportar.',
        cta: { label: 'Ir a aprobacion', action: () => { const c = needsApproval[0]; setSelectedCutoff(c); loadCutoffDetail(c); toggleStep('aprobacion'); toggleStep('aprobacion') } },
      })
    }
    const readyCutoffs = activeCutoffs.filter(c => c.status === 'approved')
    if (readyCutoffs.length > 0) {
      cards.push({
        id: 'ready_export', level: 'operational', label: 'Listos para exportar', count: readyCutoffs.length,
        description: 'Cortes aprobados listos para exportar y marcar como pagados.',
        cta: { label: 'Exportar', action: () => { const c = readyCutoffs[0]; setSelectedCutoff(c); toggleStep('exportacion_pago'); toggleStep('exportacion_pago') } },
      })
    }
    return cards
  }, [dashboardAlerts, applyLines, cutoffs, toggleStep])

  // ═══════════════════════════════════════════════════════════════
  // HANDLERS (same business logic, refined UX)
  // ═══════════════════════════════════════════════════════════════

  const handleFile = useCallback((file: File) => {
    setUploadFile(file); setUploadPhase('previewing'); setUploadError(null)
    setUploadProgress('Leyendo archivo...'); setPreviewSummary(null); setApplyLines([]); setApplySummary(null)
    previewUnifiedLoadStream(file,
      () => {}, // lines handled via summary
      (summary) => { setPreviewSummary(summary); setUploadProgress(''); setUploadPhase('preview_done') },
      (err) => { setUploadError(err); setUploadPhase('idle') },
      (event) => {
        if (event.type === 'started') setUploadProgress('Analizando...')
        else if (event.type === 'file_parsed') setUploadProgress(`${event.total_rows || '?'} filas leidas`)
        else if (event.type === 'caches_loading') setUploadProgress('Cargando referencias...')
        else if (event.type === 'processing_started') setUploadProgress('Validando...')
      },
    )
  }, [])

  const handleApply = useCallback(async () => {
    if (!previewSummary?.apply_plan) return
    setUploadPhase('applying'); setIsApplying(true); setApplyLines([]); setApplySummary(null); setUploadError(null)
    try {
      await applyUnifiedLoadStream(previewSummary.apply_plan,
        (line) => setApplyLines(prev => [...prev, line]),
        (summary) => { setApplySummary(summary); setUploadPhase('applied'); setIsApplying(false) },
        (err) => { setUploadError(err); setUploadPhase('preview_done'); setIsApplying(false) },
      )
    } catch (e: any) { setUploadError(e.message); setUploadPhase('preview_done'); setIsApplying(false) }
  }, [previewSummary])

  const runValidation = useCallback(async () => {
    setLoadingValidation(true)
    try {
      const alerts = await getDashboardAlerts()
      setDashboardAlerts(alerts); showMsg('Validacion completada')
    } catch (e: any) { showErr('Error: ' + (e.message || e)) }
    finally { setLoadingValidation(false) }
  }, [showMsg, showErr])

  const handleCreateCutoff = useCallback(async () => {
    setCreatingCutoff(true); setError(null)
    try {
      let result: any
      if (cutoffMode === 'cohort') {
        if (!cohortWeek) { showErr('Selecciona una cohorte ISO'); return }
        result = await createCutoffFromCohort({ cohort_iso_week: cohortWeek, scheme_type: originFilter || undefined })
      } else {
        result = await createSweepCutoff({ scheme_type: originFilter || undefined })
      }
      showMsg('Corte creado: ' + (result.cutoff_name || result.id))
      const updated = await listCutoffs(); setCutoffs(updated)
      if (result.cutoff_run_id) {
        const c = updated.find((x: CutoffRun) => x.id === result.cutoff_run_id)
        if (c) { setSelectedCutoff(c); loadCutoffDetail(c) }
      }
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setCreatingCutoff(false) }
  }, [cutoffMode, cohortWeek, originFilter, showMsg, showErr])

  const loadCutoffDetail = useCallback(async (c: CutoffRun) => {
    setCutoffLoading(true)
    try {
      const [sums, linesData] = await Promise.all([getCutoffSummary(c.id), getCutoffLines(c.id)])
      setCutoffSummaries(sums); setCutoffLines(linesData.lines || [])
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setCutoffLoading(false) }
  }, [showErr])

  const refreshCutoffs = useCallback(async () => {
    try { const c = await listCutoffs(); setCutoffs(c) } catch (e: any) { showErr('Error al refrescar cortes: ' + (e?.message || e)) }
  }, [showErr])

  const handleReview = useCallback(async () => {
    if (!selectedCutoff) return; setApproving(true)
    try { await reviewPayment(selectedCutoff.id); showMsg('Revisado'); await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u); const r = u.find(x => x.id === selectedCutoff.id); if (r) setSelectedCutoff(r) }
    catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setApproving(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs])

  const handleApprove = useCallback(async () => {
    if (!selectedCutoff) return; setApproving(true)
    try { await approvePayment(selectedCutoff.id); showMsg('Aprobado'); await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u); const r = u.find(x => x.id === selectedCutoff.id); if (r) setSelectedCutoff(r) }
    catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setApproving(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs])

  const handleCancel = useCallback(async () => {
    if (!selectedCutoff || !cancelReason) return
    try { await cancelPayment(selectedCutoff.id, cancelReason); showMsg('Cancelado'); setCancelReason(''); await refreshCutoffs(); setSelectedCutoff(null) }
    catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
  }, [selectedCutoff, cancelReason, showMsg, showErr, refreshCutoffs])

  const handleMarkPaid = useCallback(async () => {
    if (!selectedCutoff) return; setPaying(true)
    try { await markPaymentPaid(selectedCutoff.id); showMsg('Marcado como pagado'); await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u); const r = u.find(x => x.id === selectedCutoff.id); if (r) setSelectedCutoff(r) }
    catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setPaying(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs])

  const openExport = useCallback((urlFn: (id: number) => string) => {
    if (!selectedCutoff) return; window.open(urlFn(selectedCutoff.id), '_blank')
  }, [selectedCutoff])

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const [hist, rec, integrity] = await Promise.all([
        getPaidHistory({ limit: 50 }), getReconciliationSummary().catch(() => null), getIntegrityMetrics().catch(() => null),
      ])
      setPaidHistory(hist.items || []); setReconciliationData(rec || integrity)
    } catch (e: any) { showErr(e?.message || e) }
    finally { setLoadingHistory(false) }
  }, [showErr])

  const handleExportReconciliation = useCallback(async () => {
    try {
      const blob = await exportReconciliationCsv({})
      const url = URL.createObjectURL(blob); const a = document.createElement('a')
      a.href = url; a.download = 'reconciliacion.csv'; a.click(); URL.revokeObjectURL(url)
    } catch (e: any) { showErr('Error: ' + (e.message || e)) }
  }, [showErr])

  const downloadTemplateFile = useCallback(async () => {
    try {
      const blob = await downloadTemplate(); const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'plantilla_carga_unificada.csv'; a.click(); URL.revokeObjectURL(url)
    } catch (e: any) { showErr('Error: ' + (e.message || e)) }
  }, [showErr])

  // ═══════════════════════════════════════════════════════════════
  // SUMMARY KPI
  // ═══════════════════════════════════════════════════════════════

  const summaryKpi = useMemo(() => {
    const alerts = dashboardAlerts
    return {
      blocked: alerts?.blocks_true_without_driver_count || 0,
      warnings: (alerts?.manual_review_count || 0) + (alerts?.without_scout_count || 0),
      withoutDriver: alerts?.without_driver_count || 0,
      pendingCutoff: alerts?.cutoff_pending ? 1 : 0,
      activeCutoffs: cutoffs.filter(c => c.status !== 'cancelled' && c.status !== 'paid').length,
      readyExport: cutoffs.filter(c => c.status === 'approved').length,
    }
  }, [dashboardAlerts, cutoffs])

  // ═══════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════

  const pad = density === 'compact' ? 'p-2' : 'p-4'
  const gap = density === 'compact' ? 'gap-1.5' : 'gap-3'

  if (loadingInitial) {
    return (
      <div className="max-w-5xl mx-auto space-y-4 p-6">
        <Skeleton w="w-48" h="h-7" />
        <Skeleton w="w-full" h="h-12" />
        <Skeleton w="w-full" h="h-64" />
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* ── ALERTS ── */}
      {error && (
        <div className="mb-2 px-4 py-2.5 bg-red-50 border border-red-300 rounded-lg text-sm text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-3 text-red-400 hover:text-red-600 font-bold text-lg leading-none">&times;</button>
        </div>
      )}
      {success && (
        <div className="mb-2 px-4 py-2.5 bg-emerald-50 border border-emerald-300 rounded-lg text-sm text-emerald-700">{success}</div>
      )}

      {/* ── STICKY HEADER BAR (P7: Layout Dominance) ── */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-gray-200 -mx-4 px-4 py-2 mb-3 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-gray-800">Centro Operativo</h2>
            {/* Density toggle (P10) */}
            <button onClick={() => setDensity(d => d === 'comfortable' ? 'compact' : 'comfortable')}
              className="text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-0.5"
              title="Alternar densidad"
            >
              {density === 'comfortable' ? 'Compacto' : 'Comodo'}
            </button>
          </div>
          {/* Quick summary KPI pills */}
          <div className="flex items-center gap-2 flex-wrap text-xs">
            {summaryKpi.blocked > 0 && <span className={`px-2 py-0.5 rounded-full font-semibold ${RED.badge}`}><Dot color={RED.dot} /> {summaryKpi.blocked} bloqueados</span>}
            {summaryKpi.warnings > 0 && <span className={`px-2 py-0.5 rounded-full font-semibold ${YELLOW.badge}`}><Dot color={YELLOW.dot} /> {summaryKpi.warnings} warnings</span>}
            {summaryKpi.activeCutoffs > 0 && <span className={`px-2 py-0.5 rounded-full font-semibold ${BLUE.badge}`}>{summaryKpi.activeCutoffs} cortes activos</span>}
            {summaryKpi.readyExport > 0 && <span className={`px-2 py-0.5 rounded-full font-semibold ${GREEN.badge}`}>{summaryKpi.readyExport} listos exportar</span>}
            {!summaryKpi.blocked && !summaryKpi.warnings && !summaryKpi.activeCutoffs && <span className="text-gray-400">Sin actividad</span>}
          </div>
        </div>
      </div>

      {/* ── QUICK FILTERS (P5: Operational Speed) ── */}
      <div className="flex items-center gap-1.5 mb-3 flex-wrap">
        {(['all', 'blocked', 'warnings', 'trusted', 'pending'] as const).map(f => (
          <button key={f} onClick={() => setQuickFilter(f)}
            className={`px-3 py-1 text-[11px] rounded-full font-medium transition-colors ${quickFilter === f ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
          >
            {f === 'all' ? 'Todo' : f === 'blocked' ? 'Bloqueados' : f === 'warnings' ? 'Warnings' : f === 'trusted' ? 'Confiables' : 'Pendientes revision'}
          </button>
        ))}
      </div>

      {/* ── ATTENTION CARDS (P1: Attention Hierarchy — Level 1 first) ── */}
      {(quickFilter === 'all' || quickFilter === 'blocked') && attentionCards.filter(c => c.level === 'critical').map(card => (
        <AttentionCard key={card.id} card={card} />
      ))}
      {(quickFilter === 'all' || quickFilter === 'warnings') && attentionCards.filter(c => c.level === 'warning').map(card => (
        <AttentionCard key={card.id} card={card} />
      ))}
      {(quickFilter === 'all' || quickFilter === 'pending' || quickFilter === 'trusted') && attentionCards.filter(c => c.level === 'operational').map(card => (
        <AttentionCard key={card.id} card={card} />
      ))}

      {/* ── WORKFLOW STEPPER (P3: Workflow Focus + P2: Progressive Disclosure) ── */}
      <div ref={stepperRef} className={`bg-white border border-gray-200 rounded-xl shadow-sm mb-4 ${pad}`}>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Workflow operativo</h3>
        <div className={`flex flex-col ${gap}`}>
          {steps.map((step, idx) => {
            const isExpanded = expandedSteps.has(step.id)
            const colorSet = step.status === 'completed' ? GREEN : step.status === 'blocked' ? RED : step.status === 'in_progress' ? BLUE : step.status === 'ready' ? YELLOW : GRAY
            const canExpand = step.enabled || step.status === 'completed'

            return (
              <div key={step.id}>
                <button onClick={() => canExpand && toggleStep(step.id)}
                  disabled={!canExpand}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border text-left transition-all ${!canExpand ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:shadow-sm'} ${colorSet.border} ${colorSet.bg}`}
                >
                  <span className="text-base w-6 text-center font-bold flex-shrink-0">{STATUS_ICON[step.status]}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-xs">{idx + 1}. {step.label}</span>
                      {step.pendingCount > 0 && <Badge label={`${step.pendingCount}`} color={colorSet.badge} />}
                    </div>
                    {density === 'comfortable' && <p className="text-[11px] mt-0.5 opacity-70">{step.subtext || step.description}</p>}
                  </div>
                  <span className="text-[10px] font-medium flex-shrink-0 hidden sm:inline opacity-60">{step.ctaLabel}</span>
                  <span className="text-xs flex-shrink-0">{canExpand ? (isExpanded ? '▲' : '▼') : '·'}</span>
                </button>
                {isExpanded && canExpand && (
                  <div className={`ml-9 mt-1.5 mb-2 ${pad} bg-gray-50/70 rounded-lg border border-gray-100`}>
                    {renderStepContent(step.id)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── ANALYTICS (P7: at bottom, collapsible) ── */}
      {dashboardAlerts && (
        <div className="mb-4">
          <button onClick={() => setShowAnalytics(!showAnalytics)}
            className="text-xs font-medium text-gray-400 hover:text-gray-600 flex items-center gap-1"
          >
            {showAnalytics ? '▲' : '▼'} Analitica secundaria
          </button>
          {showAnalytics && (
            <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="bg-white border border-gray-200 rounded-lg p-2.5">
                <span className="text-gray-400">Revision manual</span>
                <div className="font-bold text-gray-700">{dashboardAlerts.manual_review_count ?? 0}</div>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-2.5">
                <span className="text-gray-400">Sin driver</span>
                <div className="font-bold text-gray-700">{dashboardAlerts.without_driver_count ?? 0}</div>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-2.5">
                <span className="text-gray-400">Sin scout</span>
                <div className="font-bold text-gray-700">{dashboardAlerts.without_scout_count ?? 0}</div>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-2.5">
                <span className="text-gray-400">Solo financiero</span>
                <div className="font-bold text-gray-700">{dashboardAlerts.financial_only_count ?? 0}</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )

  // ═══════════════════════════════════════════════════════════════
  // STEP CONTENT RENDERERS (P2: Progressive Disclosure + P4: Cognitive Load)
  // ═══════════════════════════════════════════════════════════════

  function renderStepContent(stepId: StepId) {
    switch (stepId) {
      case 'carga': return renderCarga()
      case 'validacion': return renderValidacion()
      case 'revision_bloqueos': return renderBloqueos()
      case 'revision_warnings': return renderWarnings()
      case 'corte': return renderCorte()
      case 'aprobacion': return renderAprobacion()
      case 'exportacion_pago': return renderExport()
      case 'historial': return renderHistorial()
    }
  }

  function renderCarga() {
    return (
      <div className="space-y-3">
        {uploadPhase === 'idle' && (
          <div className="text-center py-4">
            <button onClick={downloadTemplateFile} className="text-xs text-blue-600 hover:text-blue-800 underline mb-3 block">
              Descargar plantilla CSV
            </button>
            <label className="block border-2 border-dashed border-gray-300 hover:border-blue-400 rounded-lg p-6 cursor-pointer transition-colors">
              <input type="file" accept=".csv,.xlsx,.xls" onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} className="hidden" />
              <p className="text-sm text-gray-500">Arrastra un archivo o haz clic</p>
              <p className="text-xs text-gray-400 mt-1">CSV, XLSX o XLS — max 20000 filas</p>
            </label>
          </div>
        )}

        {uploadPhase === 'previewing' && (
          <div className="text-center py-4">
            <div className="inline-block w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-2" />
            <p className="text-sm text-blue-600">{uploadProgress || 'Procesando...'}</p>
          </div>
        )}

        {previewSummary && (uploadPhase === 'preview_done' || uploadPhase === 'applying') && (
          <div className="space-y-2">
            {/* Compact KPI grid */}
            <div className="grid grid-cols-3 gap-1.5 text-[11px]">
              <KpiBox label="Total" value={previewSummary.total_rows} />
              <KpiBox label="Validas" value={previewSummary.valid_rows} color={GREEN} />
              <KpiBox label="Errores" value={previewSummary.error_rows} color={previewSummary.error_rows > 0 ? RED : GRAY} />
              <KpiBox label="Drivers encontrados" value={previewSummary.drivers_found} />
              <KpiBox label="No encontrados" value={previewSummary.drivers_not_found} color={previewSummary.drivers_not_found > 0 ? YELLOW : GRAY} />
              <KpiBox label="Asignaciones" value={previewSummary.assignments_to_create} />
            </div>
            {uploadPhase === 'preview_done' && (
              <button onClick={handleApply} disabled={isApplying}
                className={`w-full py-2 rounded-lg text-sm font-semibold text-white transition-colors ${GREEN.bg.replace('bg-emerald-50','bg-emerald-600')} hover:bg-emerald-700 disabled:opacity-50`}
              >
                Aplicar carga
              </button>
            )}
          </div>
        )}

        {applySummary && (
          <div className="space-y-2">
            <div className="grid grid-cols-3 gap-1.5 text-[11px]">
              <KpiBox label="Aplicados" value={applySummary.applied} color={GREEN} />
              <KpiBox label="Errores" value={applySummary.errors} color={applySummary.errors > 0 ? RED : GRAY} />
              <KpiBox label="Conflictos" value={applySummary.conflicts ?? 0} color={(applySummary.conflicts ?? 0) > 0 ? RED : GRAY} />
            </div>
            {applyLines.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700 py-1">Detalle por fila ({applyLines.length} lineas)</summary>
                <div className="max-h-48 overflow-y-auto mt-1 border rounded">
                  <table className="w-full text-[11px]">
                    <thead><tr className="text-left text-gray-400 bg-gray-50 border-b"><th className="py-1 px-2">Fila</th><th className="py-1 px-2">Licencia</th><th className="py-1 px-2">Accion</th><th className="py-1 px-2">Estado</th></tr></thead>
                    <tbody>
                      {applyLines.slice(0, 100).map((al, i) => (
                        <tr key={i} className="border-b border-gray-50">
                          <td className="py-1 px-2 text-gray-400">{al.source_row}</td>
                          <td className="py-1 px-2 font-mono">{al.licencia || al.driver_id || '-'}</td>
                          <td className="py-1 px-2"><span className={`px-1 py-0.5 rounded text-[10px] ${al.action === 'error' || al.action === 'conflict_existing_active_scout' ? RED.badge : al.action === 'created_assignment' || al.action === 'created_payment_history' ? GREEN.badge : YELLOW.badge}`}>{APPLY_LABEL[al.action] || al.action}</span></td>
                          <td className="py-1 px-2"><span className={al.status === 'ok' ? 'text-emerald-600' : 'text-red-600'}>{al.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
            <button onClick={resetCarga} className="w-full py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 text-sm font-semibold">Nueva carga</button>
          </div>
        )}
      </div>
    )
  }

  function renderValidacion() {
    return (
      <div className="space-y-3">
        {!dashboardAlerts ? (
          <div className="text-center py-3">
            <button onClick={runValidation} disabled={loadingValidation}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold disabled:opacity-50"
            >
              {loadingValidation ? 'Validando...' : 'Ejecutar validacion'}
            </button>
            <p className="text-xs text-gray-400 mt-2">Verifica calidad de datos y consistencia.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 text-xs">
            <AlertItem label="Revision manual" value={dashboardAlerts.manual_review_count ?? 0} level={dashboardAlerts.manual_review_count > 0 ? 'warning' : 'ok'} />
            <AlertItem label="Sin driver" value={dashboardAlerts.without_driver_count ?? 0} level={dashboardAlerts.without_driver_count > 0 ? 'critical' : 'ok'} />
            <AlertItem label="Sin scout" value={dashboardAlerts.without_scout_count ?? 0} level={dashboardAlerts.without_scout_count > 0 ? 'warning' : 'ok'} />
            <AlertItem label="Bioq sin driver" value={dashboardAlerts.blocks_true_without_driver_count ?? 0} level={dashboardAlerts.blocks_true_without_driver_count > 0 ? 'critical' : 'ok'} />
            <AlertItem label="Hash duplicados" value={dashboardAlerts.duplicate_hash_count ?? 0} level={dashboardAlerts.duplicate_hash_count > 0 ? 'warning' : 'ok'} />
            <AlertItem label="Corte pendiente" value={dashboardAlerts.cutoff_pending ? 'Si' : 'No'} level={dashboardAlerts.cutoff_pending ? 'warning' : 'ok'} />
          </div>
        )}
      </div>
    )
  }

  function renderBloqueos() {
    return (
      <div className="space-y-3">
        <p className="text-xs text-gray-500">Los bloqueos (U1) impiden que un item sea considerado en el corte. Incluyen conflictos de asignacion, duplicados y drivers sin ID valido.</p>
        {dashboardAlerts?.blocks_true_without_driver_count > 0 && (
          <div className={`p-3 rounded-lg border ${RED.border} ${RED.bg} text-xs`}>
            <strong className={RED.text}>{dashboardAlerts.blocks_true_without_driver_count} conductores bloquean el pago</strong>
          </div>
        )}
        {!dashboardAlerts?.blocks_true_without_driver_count && (
          <div className={`p-3 rounded-lg border ${GREEN.border} ${GREEN.bg} text-xs`}>
            <span className={GREEN.text}>No hay bloqueos activos. Todo listo para el corte.</span>
          </div>
        )}
        <div className="flex gap-2">
          <a href="/scout-liq/operation" className="px-3 py-1.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">Ver grilla completa</a>
          <a href="/scout-liq/review-queue" className="px-3 py-1.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">Cola de anclajes</a>
        </div>
      </div>
    )
  }

  function renderWarnings() {
    return (
      <div className="space-y-3">
        <p className="text-xs text-gray-500">Warnings U2/U3: no bloquean el pago pero requieren atencion (anclajes debiles, sin scout, revision manual).</p>
        {dashboardAlerts && (
          <div className="grid grid-cols-3 gap-2 text-xs">
            <AlertItem label="Revision manual" value={dashboardAlerts.manual_review_count ?? 0} level={dashboardAlerts.manual_review_count > 0 ? 'warning' : 'ok'} />
            <AlertItem label="Sin driver" value={dashboardAlerts.without_driver_count ?? 0} level={dashboardAlerts.without_driver_count > 0 ? 'warning' : 'ok'} />
            <AlertItem label="Sin scout" value={dashboardAlerts.without_scout_count ?? 0} level={dashboardAlerts.without_scout_count > 0 ? 'warning' : 'ok'} />
          </div>
        )}
        <a href="/scout-liq/operation" className="inline-block px-3 py-1.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">Ver grilla completa</a>
      </div>
    )
  }

  function renderCorte() {
    const origins = useMemo(() => [...new Set(schemes.map(s => s.origin).filter(Boolean))] as string[], [schemes])

    return (
      <div className="space-y-3">
        <div className="flex gap-1.5">
          {(['cohort', 'sweep'] as const).map(m => (
            <button key={m} onClick={() => setCutoffMode(m)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${cutoffMode === m ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
            >
              {m === 'cohort' ? 'Cohorte ISO' : 'Barrido'}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {cutoffMode === 'cohort' && (
            <input type="text" value={cohortWeek} onChange={e => setCohortWeek(e.target.value)}
              placeholder="Ej: 2025-W20" className="w-full border rounded px-3 py-1.5 text-sm"
            />
          )}
          {origins.length > 0 && (
            <select value={originFilter} onChange={e => setOriginFilter(e.target.value)} className="w-full border rounded px-3 py-1.5 text-sm">
              <option value="">Todos los origenes</option>
              {origins.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
          <button onClick={handleCreateCutoff} disabled={creatingCutoff}
            className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold disabled:opacity-50"
          >
            {creatingCutoff ? 'Creando...' : 'Crear corte'}
          </button>
        </div>

        {cutoffs.length > 0 && (
          <details className="text-xs" open={cutoffs.length <= 5}>
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 py-1 font-medium">
              Cortes existentes ({cutoffs.length})
            </summary>
            <div className="max-h-48 overflow-y-auto space-y-1 mt-1">
              {cutoffs.map(c => (
                <button key={c.id} onClick={() => { setSelectedCutoff(c); loadCutoffDetail(c) }}
                  className={`w-full text-left px-3 py-2 rounded border text-xs transition-colors ${selectedCutoff?.id === c.id ? 'border-blue-300 bg-blue-50' : 'border-gray-100 hover:bg-gray-50'}`}
                >
                  <div className="flex justify-between">
                    <span className="font-medium truncate mr-2">{c.cutoff_name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium flex-shrink-0 ${
                      c.status === 'paid' ? GREEN.badge : c.status === 'approved' ? GREEN.badge : c.status === 'reviewed' ? YELLOW.badge : c.status === 'calculated' ? BLUE.badge : GRAY.badge
                    }`}>{c.status}</span>
                  </div>
                  <div className="text-gray-400 mt-0.5">{c.cohort_iso_week && `${c.cohort_iso_week} · `}{c.hire_date_from} → {c.hire_date_to}</div>
                </button>
              ))}
            </div>
          </details>
        )}
      </div>
    )
  }

  function renderAprobacion() {
    if (!selectedCutoff) {
      return <EmptyState title={STEP_DEF.aprobacion.desc} action="Selecciona un corte en el paso 'Corte'." />
    }
    const c = selectedCutoff
    const canReview = c.status === 'draft' || c.status === 'calculated'
    const canApprove = c.status === 'reviewed'
    return (
      <div className="space-y-3">
        <div className="bg-white border rounded-lg p-3">
          <div className="flex justify-between items-start">
            <div>
              <h4 className="font-semibold text-sm">{c.cutoff_name}</h4>
              <div className="text-xs text-gray-400 mt-0.5">{c.cohort_iso_week && `Cohorte ${c.cohort_iso_week} · `}{c.hire_date_from} → {c.hire_date_to}</div>
            </div>
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${c.status === 'approved' ? GREEN.badge : c.status === 'reviewed' ? YELLOW.badge : BLUE.badge}`}>{c.status}</span>
          </div>
        </div>

        {cutoffLoading ? (
          <div className="space-y-2">{Array.from({length:3}).map((_,i)=><Skeleton key={i} h="h-10"/>)}</div>
        ) : cutoffSummaries.length > 0 ? (
          <details className="text-xs" open>
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 py-1 font-medium">Resumen por scout ({cutoffSummaries.length})</summary>
            <div className="max-h-48 overflow-y-auto space-y-1 mt-1">
              {cutoffSummaries.map((s: any, i: number) => (
                <div key={i} className="bg-white border rounded p-2 flex justify-between items-center text-[11px]">
                  <div>
                    <span className="font-medium">{s.scout_name}</span>
                    <span className="text-gray-400 ml-2">{s.total_affiliations} afil · Conv {s.conversion_rate?.toFixed(1)}%</span>
                  </div>
                  <span className={s.status === 'blocked' ? RED.text : GREEN.text + ' font-semibold'}>
                    {s.status === 'blocked' ? `Bloqueado` : `$${(s.amount_calculated || 0).toLocaleString()}`}
                  </span>
                </div>
              ))}
            </div>
          </details>
        ) : (
          <EmptyState title="Sin resumen" action="No hay datos de scout para este corte." />
        )}

        <div className="flex flex-wrap gap-2">
          {canReview && <button onClick={handleReview} disabled={approving} className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 text-sm font-semibold disabled:opacity-50">Revisar</button>}
          {canApprove && <button onClick={handleApprove} disabled={approving} className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-semibold disabled:opacity-50">Aprobar</button>}
          {c.status !== 'paid' && c.status !== 'cancelled' && (
            <div className="flex items-center gap-2">
              <input type="text" value={cancelReason} onChange={e => setCancelReason(e.target.value)} placeholder="Razon cancelacion" className="border rounded px-2 py-1.5 text-xs w-40" />
              <button onClick={handleCancel} disabled={!cancelReason} className="px-3 py-1.5 bg-red-100 text-red-700 rounded hover:bg-red-200 text-xs font-semibold disabled:opacity-40">Cancelar</button>
            </div>
          )}
        </div>
      </div>
    )
  }

  function renderExport() {
    if (!selectedCutoff) {
      return <EmptyState title={STEP_DEF.exportacion_pago.desc} action="Selecciona un corte aprobado para exportar." />
    }
    const c = selectedCutoff
    const canPay = c.status === 'approved'
    const isPaid = c.status === 'paid'
    return (
      <div className="space-y-3">
        <div className="bg-white border rounded-lg p-3">
          <div className="flex justify-between items-center">
            <span className="font-semibold text-sm">{c.cutoff_name}</span>
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${isPaid ? GREEN.badge : YELLOW.badge}`}>{c.status}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {canPay && <button onClick={handleMarkPaid} disabled={paying} className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-semibold disabled:opacity-50">{paying ? 'Procesando...' : 'Marcar pagado'}</button>}
          <button onClick={() => openExport(getPaymentExportCsvUrl)} className="px-3 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 text-sm">CSV</button>
          <button onClick={() => openExport(getPaymentExportXlsxUrl)} className="px-3 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 text-sm">XLSX</button>
          <button onClick={() => openExport(getCutoffExportFinancialUrl)} className="px-3 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 text-sm">Financiero</button>
        </div>
      </div>
    )
  }

  function renderHistorial() {
    return (
      <div className="space-y-3">
        <button onClick={loadHistory} disabled={loadingHistory}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold disabled:opacity-50"
        >
          {loadingHistory ? 'Cargando...' : 'Cargar historial y reconciliacion'}
        </button>

        {reconciliationData && (
          <details className="text-xs" open>
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 py-1 font-medium">Reconciliacion</summary>
            <div className="grid grid-cols-3 gap-1.5 mt-1">
              {'attribution_integrity_pct' in reconciliationData && <KpiBox label="Integridad" value={`${reconciliationData.attribution_integrity_pct?.toFixed(1)}%`} />}
              {'total_observed' in reconciliationData && <KpiBox label="Observados" value={reconciliationData.total_observed} />}
              {'total_validated' in reconciliationData && <KpiBox label="Validados" value={reconciliationData.total_validated} color={GREEN} />}
              {'total_rejected' in reconciliationData && <KpiBox label="Rechazados" value={reconciliationData.total_rejected} color={reconciliationData.total_rejected > 0 ? RED : GRAY} />}
              {'active_conflicts' in reconciliationData && <KpiBox label="Conflictos" value={reconciliationData.active_conflicts} color={reconciliationData.active_conflicts > 0 ? RED : GRAY} />}
            </div>
            <button onClick={handleExportReconciliation} className="mt-2 px-3 py-1.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">Exportar CSV</button>
          </details>
        )}

        {paidHistory.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 py-1 font-medium">Historial de pagos ({paidHistory.length})</summary>
            <div className="max-h-48 overflow-y-auto space-y-1 mt-1">
              {paidHistory.map((item: any, i: number) => (
                <div key={i} className="bg-white border rounded p-2 flex justify-between items-center text-[11px]">
                  <div>
                    <span className="font-medium">{item.scout_name_raw || 'Scout #' + item.scout_id}</span>
                    <span className="text-gray-400 ml-2">Driver: {item.driver_id || item.driver_license_raw || '-'}</span>
                  </div>
                  <span className="font-semibold text-emerald-700">{item.amount_paid?.toLocaleString()} {item.currency}</span>
                </div>
              ))}
            </div>
          </details>
        )}
        <a href="/scout-liq/paid-history" className="inline-block px-3 py-1.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">Historial completo</a>
      </div>
    )
  }
}

// ═══════════════════════════════════════════════════════════════
// SMALL REUSABLE COMPONENTS (inline for simplicity)
// ═══════════════════════════════════════════════════════════════

function KpiBox({ label, value, color }: { label: string; value: number | string; color?: typeof GREEN }) {
  const c = color || GRAY
  return (
    <div className={`${c.bg} rounded-lg p-2 text-center`}>
      <div className="text-gray-400 text-[10px]">{label}</div>
      <div className={`font-bold text-sm ${c.text}`}>{typeof value === 'number' ? value.toLocaleString() : value}</div>
    </div>
  )
}

function AlertItem({ label, value, level }: { label: string; value: number | string; level: 'ok' | 'warning' | 'critical' }) {
  const c = level === 'critical' ? RED : level === 'warning' ? YELLOW : GREEN
  return (
    <div className={`${c.bg} rounded-lg p-2 text-center border ${c.border}`}>
      <div className="text-gray-400 text-[10px]">{label}</div>
      <div className={`font-bold text-xs ${c.text}`}>{typeof value === 'number' ? value.toLocaleString() : value}</div>
    </div>
  )
}

function EmptyState({ title, action }: { title: string; action: string }) {
  return (
    <div className="text-center py-3 text-xs text-gray-400">
      <p className="font-medium text-gray-500 mb-1">{title}</p>
      <p>{action}</p>
    </div>
  )
}

function AttentionCard({ card }: { card: AttentionCard }) {
  const c = card.level === 'critical' ? RED : card.level === 'warning' ? YELLOW : BLUE
  return (
    <div className={`mb-3 rounded-xl border ${c.border} ${c.bg} p-4`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Dot color={c.dot} pulse={card.level === 'critical'} />
          <span className={`font-semibold text-sm ${c.text}`}>{card.label}</span>
          <Badge label={String(card.count)} color={c.badge} />
        </div>
        {card.cta && (
          <button onClick={card.cta.action}
            className={`text-[11px] font-semibold px-3 py-1 rounded-full ${c.badge} hover:opacity-80 transition-opacity`}
          >
            {card.cta.label}
          </button>
        )}
      </div>
      <p className="text-xs mt-1 text-gray-500">{card.description}</p>
    </div>
  )
}
