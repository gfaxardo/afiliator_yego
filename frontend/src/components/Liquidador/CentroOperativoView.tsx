import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  getSchemes, getScouts, listCutoffs,
  createCutoffFromCohort, createSweepCutoff,
  getCutoffSummary, getCutoffLines,
  reviewPayment, approvePayment, markPaymentPaid, cancelPayment,
  getPaymentExportCsvUrl, getPaymentExportXlsxUrl,
  getPaidHistory, getDashboardAlerts, getCutoffExportFinancialUrl,
  getOperationFilters,
  getCanonicalOperation, type CanonicalDriver, type CanonicalFreshness,
} from '../../api/scoutLiq'
import DriverDetailDrawer from './DriverDetailDrawer'
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

const ANCHOR_SOURCE_LABEL: Record<string, string> = {
  lead_cabinet: 'Lead Cabinet', lead_fleet: 'Lead Fleet', hire_date: 'Hire date', unknown: '---',
}
const ANCHOR_CONFIDENCE_COLOR: Record<string, string> = {
  strong: 'bg-emerald-100 text-emerald-700', medium: 'bg-amber-100 text-amber-700', weak: 'bg-red-100 text-red-600', unknown: 'bg-gray-100 text-gray-400',
}
const COL_GROUP_KEYS = ['driver', 'anchor', 'attribution', 'progress', 'payment', 'risk'] as const
type ColGroup = typeof COL_GROUP_KEYS[number]

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

  // ── Driver Table ──
  const [drivers, setDrivers] = useState<CanonicalDriver[]>([])
  const [driversLoading, setDriversLoading] = useState(true)
  const [driversTotal, setDriversTotal] = useState(0)
  const [driversHasNext, setDriversHasNext] = useState(false)
  const [driversFreshness, setDriversFreshness] = useState<CanonicalFreshness | null>(null)
  const [driverPage, setDriverPage] = useState(0)
  const [driverSearch, setDriverSearch] = useState('')
  const [driverOriginFilter, setDriverOriginFilter] = useState('')
  const [driverLifecycleFilter, setDriverLifecycleFilter] = useState('')
  const [driverTagFilter, setDriverTagFilter] = useState<string | null>(null)
  const [selectedDriver, setSelectedDriver] = useState<CanonicalDriver | null>(null)
  const [driversPageSize, setDriversPageSize] = useState(100)

  // ── Advanced filters ──
  const [showFilters, setShowFilters] = useState(false)
  const [filterAnchorSource, setFilterAnchorSource] = useState('')
  const [filterAnchorConfidence, setFilterAnchorConfidence] = useState('')
  const [filterHasWarning, setFilterHasWarning] = useState('')
  const [filterPaymentStatus, setFilterPaymentStatus] = useState('')
  const [filterScoutId, setFilterScoutId] = useState('')
  const [filterBlockReason, setFilterBlockReason] = useState('')
  const [filterMinTrips7d, setFilterMinTrips7d] = useState(0)
  const [sortField, setSortField] = useState('anchor_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  // ── Scouts list for filter ──
  const [scoutsList, setScoutsList] = useState<{ id: number; scout_name: string; scout_type: string | null; city: string | null }[]>([])
  const [scoutFilterSearch, setScoutFilterSearch] = useState('')

  // ── Column visibility ──
  const [visibleCols, setVisibleCols] = useState<Set<ColGroup>>(new Set(COL_GROUP_KEYS))
  const [showColSelector, setShowColSelector] = useState(false)

  // ── Workflow collapsed ──
  const [showWorkflow, setShowWorkflow] = useState(false)

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
  // DRIVER TABLE DATA
  // ═══════════════════════════════════════════════════════════════

  function deriveDriverLifecycle(row: CanonicalDriver): string {
    if (row.attribution_status === 'unassigned') return 'sin_scout'
    if (row.converted_5v14d) return 'converted_5v14d'
    if (row.converted_5v7d) return 'converted_5v7d'
    if (row.activated_flag) return 'activated'
    if (row.driver_id) return 'no_trips'
    return 'no_driver_id'
  }

  function getDriverTags(row: CanonicalDriver): { key: string; label: string; color: string }[] {
    const tags: { key: string; label: string; color: string }[] = []
    if (row.attribution_status === 'unassigned') tags.push({ key: 'sin_scout', label: 'Sin scout', color: 'bg-yellow-100 text-yellow-700' })
    if (row.payment_status === 'paid') tags.push({ key: 'ya_pagado', label: 'Ya pagado', color: 'bg-teal-100 text-teal-700' })
    if (row.reason === 'manual_review') tags.push({ key: 'manual_review', label: 'Revision manual', color: 'bg-orange-100 text-orange-700' })
    if (row.source_driver_status === 'weak') tags.push({ key: 'fuente_debil', label: 'Fuente debil', color: 'bg-red-100 text-red-700' })
    if (row.converted_5v7d) tags.push({ key: 'cumple_calidad', label: '5V/7D', color: 'bg-blue-100 text-blue-700' })
    if (!row.activated_flag && row.driver_id) tags.push({ key: 'no_convierte', label: 'No activa', color: 'bg-gray-100 text-gray-500' })
    return tags
  }

  const DRIVER_LIFECYCLE_OPTIONS = [
    { key: '', label: 'Todos los estados' },
    { key: 'no_driver_id', label: 'Sin ID' },
    { key: 'no_trips', label: 'Sin viajes' },
    { key: 'sin_scout', label: 'Sin scout' },
    { key: 'activated', label: 'Activado' },
    { key: 'converted_5v7d', label: '5V/7D' },
    { key: 'converted_5v14d', label: '5V/14D' },
  ]

  const DRIVER_LIFECYCLE_LABELS: Record<string, string> = {
    no_driver_id: 'SIN ID', no_trips: 'SIN VIAJES', sin_scout: 'SIN SCOUT',
    activated: 'ACTIVADO', converted_5v7d: '5V/7D', converted_5v14d: '5V/14D',
  }
  const DRIVER_LIFECYCLE_COLORS: Record<string, string> = {
    no_driver_id: 'bg-red-100 text-red-700', no_trips: 'bg-gray-100 text-gray-500',
    sin_scout: 'bg-yellow-100 text-yellow-700', activated: 'bg-green-100 text-green-700',
    converted_5v7d: 'bg-blue-100 text-blue-700', converted_5v14d: 'bg-purple-100 text-purple-700',
  }
  const DRIVER_LIFECYCLE_BORDER: Record<string, string> = {
    sin_scout: 'border-l-4 border-l-yellow-400',
    converted_5v7d: 'border-l-4 border-l-blue-400',
    converted_5v14d: 'border-l-4 border-l-purple-400',
    activated: 'border-l-4 border-l-green-400',
  }

  const loadDrivers = useCallback(async (page: number, append = false, pageSize: number = driversPageSize) => {
    setDriversLoading(true)
    try {
      const params: any = { limit: pageSize, offset: page * pageSize }
      if (driverOriginFilter) params.origin = driverOriginFilter
      if (filterScoutId && filterScoutId !== 'none') params.scout_id = Number(filterScoutId)
      if (filterScoutId === 'none') params.attribution_status = 'unassigned'
      if (driverSearch && driverSearch.trim()) params.search = driverSearch.trim()
      const result = await getCanonicalOperation(params)
      const items: CanonicalDriver[] = result.items || []
      if (append) setDrivers(prev => [...prev, ...items])
      else setDrivers(items)
      setDriversTotal(result.total || 0)
      setDriversHasNext(result.has_next || false)
      setDriversFreshness(result.freshness || null)
    } catch (e: any) { setError(e?.response?.data?.detail || e.message) }
    finally { setDriversLoading(false) }
  }, [driverOriginFilter, filterScoutId, driverSearch, driversPageSize])

  useEffect(() => {
    if (loadingInitial) return
    setDriverPage(0)
    loadDrivers(0)
  }, [loadingInitial, driverOriginFilter, filterScoutId])

  // Debounced search -> server-side
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(driverSearch), 400)
    return () => clearTimeout(t)
  }, [driverSearch])
  useEffect(() => {
    if (loadingInitial) return
    setDriverPage(0)
    loadDrivers(0)
  }, [debouncedSearch])

  // Load scouts for filter
  useEffect(() => {
    if (loadingInitial) return
    getScouts({ status: 'active' }).then(list => {
      setScoutsList(list.map(s => ({ id: s.id, scout_name: s.scout_name, scout_type: s.scout_type, city: s.city })))
    }).catch(() => setScoutsList([]))
  }, [loadingInitial])

  const filteredDrivers = useMemo(() => {
    let filtered = [...drivers]
    if (driverSearch) {
      const q = driverSearch.toLowerCase()
      filtered = filtered.filter(d =>
        (d.driver_id || '').toLowerCase().includes(q) ||
        (d.driver_name || '').toLowerCase().includes(q) ||
        (d.license || '').toLowerCase().includes(q) ||
        (d.scout_name || '').toLowerCase().includes(q)
      )
    }
    if (driverLifecycleFilter) {
      filtered = filtered.filter(d => deriveDriverLifecycle(d) === driverLifecycleFilter)
    }
    if (driverTagFilter) {
      filtered = filtered.filter(d => getDriverTags(d).some(t => t.key === driverTagFilter))
    }
    if (filterAnchorSource) {
      filtered = filtered.filter(d => (d.anchor_source || '') === filterAnchorSource)
    }
    if (filterAnchorConfidence) {
      filtered = filtered.filter(d => (d.anchor_confidence || '') === filterAnchorConfidence)
    }
    if (filterHasWarning === 'yes') {
      filtered = filtered.filter(d => (d.payment_trace_warning || d.reason === 'manual_review'))
    } else if (filterHasWarning === 'no') {
      filtered = filtered.filter(d => !d.payment_trace_warning && d.reason !== 'manual_review')
    }
    if (filterPaymentStatus) {
      filtered = filtered.filter(d => (d.payment_status || '') === filterPaymentStatus)
    }
    if (filterBlockReason) {
      filtered = filtered.filter(d => (d.reason || '') === filterBlockReason || d.payment_trace_status === filterBlockReason)
    }
    if (filterMinTrips7d > 0) {
      filtered = filtered.filter(d => d.trips_7d >= filterMinTrips7d)
    }
    if (filterScoutId) {
      if (filterScoutId === 'none') {
        filtered = filtered.filter(d => !d.scout_id)
      } else {
        filtered = filtered.filter(d => d.scout_id?.toString() === filterScoutId)
      }
    }
    // Sort
    filtered.sort((a, b) => {
      let cmp = 0
      const mul = sortDir === 'desc' ? -1 : 1
      if (sortField === 'anchor_date') {
        const da = a.anchor_date || a.hire_date || ''
        const db = b.anchor_date || b.hire_date || ''
        cmp = da.localeCompare(db) * mul
      } else if (sortField === 'hire_date') {
        cmp = ((a.hire_date || '') > (b.hire_date || '') ? 1 : -1) * mul
      } else if (sortField === 'scout') {
        cmp = ((a.scout_name || '') > (b.scout_name || '') ? 1 : -1) * mul
      } else if (sortField === 'driver_name') {
        cmp = ((a.driver_name || '') > (b.driver_name || '') ? 1 : -1) * mul
      } else if (sortField === 'anchor_confidence') {
        const order = { strong: 0, medium: 1, weak: 2, unknown: 3 }
        cmp = ((order[a.anchor_confidence || 'unknown'] || 9) - (order[b.anchor_confidence || 'unknown'] || 9)) * mul
      }
      return cmp
    })
    return filtered
  }, [drivers, driverSearch, driverLifecycleFilter, driverTagFilter, filterAnchorSource, filterAnchorConfidence, filterHasWarning, filterPaymentStatus, filterBlockReason, filterMinTrips7d, filterScoutId, sortField, sortDir])

  const driverTagCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const d of drivers) {
      for (const tag of getDriverTags(d)) {
        counts[tag.key] = (counts[tag.key] || 0) + 1
      }
    }
    return counts
  }, [drivers])

  const driverKpis = useMemo(() => {
    const total = driversTotal
    const assigned = drivers.filter(d => d.attribution_status === 'assigned').length
    const unassigned = drivers.filter(d => d.attribution_status === 'unassigned').length
    const activated = drivers.filter(d => d.activated_flag).length
    const converted7 = drivers.filter(d => d.converted_5v7d).length
    const converted14 = drivers.filter(d => d.converted_5v14d).length
    const payable = drivers.filter(d => d.payment_status === 'payable').length
    const paid = drivers.filter(d => d.payment_status === 'paid').length
    const blocked = drivers.filter(d => d.payment_status === 'no_payable' && d.reason && d.reason !== 'ok' && d.reason !== 'no_activation').length
    const manualReview = drivers.filter(d => d.reason === 'manual_review').length
    const weakSource = drivers.filter(d => d.anchor_confidence === 'weak').length
    return { total, assigned, unassigned, activated, converted7, converted14, payable, paid, blocked, manualReview, weakSource }
  }, [drivers, driversTotal])

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
      <div className="max-w-7xl mx-auto space-y-4 p-6">
        <Skeleton w="w-48" h="h-7" />
        <Skeleton w="w-full" h="h-12" />
        <Skeleton w="w-full" h="h-64" />
      </div>
    )
  }

  return (
    <div className="px-3">
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

      {/* ── STICKY HEADER ── */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-gray-200 -mx-3 px-3 py-2 mb-2 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold text-gray-800">Centro Operativo</h2>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Operacion</span>
            <button onClick={() => setDensity(d => d === 'comfortable' ? 'compact' : 'comfortable')}
              className="text-[10px] text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-0.5">
              {density === 'comfortable' ? 'Compacto' : 'Comodo'}
            </button>
            <span className="text-[10px] text-gray-300">|</span>
            <button onClick={() => setShowFilters(!showFilters)}
              className={`text-[10px] font-medium px-2 py-0.5 rounded border ${showFilters ? 'bg-gray-800 text-white border-gray-800' : 'border-gray-200 text-gray-500 hover:bg-gray-100'}`}>
              Filtros {showFilters ? '▲' : '▼'}
            </button>
            <div className="relative">
              <button onClick={() => setShowColSelector(!showColSelector)}
                className="text-[10px] font-medium px-2 py-0.5 rounded border border-gray-200 text-gray-500 hover:bg-gray-100">
                Columnas
              </button>
              {showColSelector && (
                <div className="absolute left-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 w-40 py-1">
                  {COL_GROUP_KEYS.map(g => (
                    <label key={g} className="flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-gray-50 cursor-pointer">
                      <input type="checkbox" checked={visibleCols.has(g)}
                        onChange={() => {
                          const next = new Set(visibleCols)
                          next.has(g) ? next.delete(g) : next.add(g)
                          setVisibleCols(next)
                        }}
                        className="rounded w-3 h-3" />
                      <span className="text-gray-600 capitalize">{g === 'driver' ? 'Conductor' : g === 'anchor' ? 'Fecha ancla' : g === 'attribution' ? 'Atribucion' : g === 'progress' ? 'Progreso' : g === 'payment' ? 'Pago' : 'Riesgo'}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
          {/* KPI pills */}
          <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
            <span className="font-bold text-gray-700">{driversTotal} drivers</span>
            {driverKpis.unassigned > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold ${YELLOW.badge}`}>{driverKpis.unassigned} sin scout</span>}
            {driverKpis.activated > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold ${BLUE.badge}`}>{driverKpis.activated} activ.</span>}
            {driverKpis.converted7 > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold bg-indigo-100 text-indigo-700`}>{driverKpis.converted7} 5V/7D</span>}
            {driverKpis.converted14 > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold bg-purple-100 text-purple-700`}>{driverKpis.converted14} 5V/14D</span>}
            {driverKpis.payable > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold ${GREEN.badge}`}>{driverKpis.payable} pagables</span>}
            {driverKpis.paid > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold bg-teal-100 text-teal-700`}>{driverKpis.paid} pagados</span>}
            {driverKpis.blocked > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold ${RED.badge}`}>{driverKpis.blocked} bloq.</span>}
            {driverKpis.manualReview > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold bg-orange-100 text-orange-700`}>{driverKpis.manualReview} rev.</span>}
            {driverKpis.weakSource > 0 && <span className={`px-1.5 py-0.5 rounded-full font-semibold bg-red-100 text-red-600`}>{driverKpis.weakSource} debil</span>}
          </div>
        </div>
      </div>

      {/* ── ADVANCED FILTER PANEL ── */}
      {showFilters && (
        <div className="bg-white border border-gray-200 rounded-lg mb-2 p-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {/* Search */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Buscar</label>
              <input type="text" value={driverSearch} onChange={e => setDriverSearch(e.target.value)}
                placeholder="Driver, nombre, licencia..."
                className="w-full border rounded px-2 py-1 text-[11px] focus:outline-none focus:border-blue-400" />
            </div>
            {/* Origin */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Origen</label>
              <select value={driverOriginFilter} onChange={e => setDriverOriginFilter(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todos</option>
                <option value="cabinet">Cabinet</option>
                <option value="fleet">Flota</option>
              </select>
            </div>
            {/* Anchor source */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Fuente ancla</label>
              <select value={filterAnchorSource} onChange={e => setFilterAnchorSource(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todas</option>
                <option value="lead_cabinet">Lead Cabinet</option>
                <option value="lead_fleet">Lead Fleet</option>
                <option value="hire_date">Hire date</option>
              </select>
            </div>
            {/* Anchor confidence */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Confianza</label>
              <select value={filterAnchorConfidence} onChange={e => setFilterAnchorConfidence(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todas</option>
                <option value="strong">Strong</option>
                <option value="medium">Medium</option>
                <option value="weak">Weak</option>
              </select>
            </div>
            {/* Warning */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Warning</label>
              <select value={filterHasWarning} onChange={e => setFilterHasWarning(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todos</option>
                <option value="yes">Con warning</option>
                <option value="no">Sin warning</option>
              </select>
            </div>
            {/* Payment status */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Pago</label>
              <select value={filterPaymentStatus} onChange={e => setFilterPaymentStatus(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todos</option>
                <option value="payable">Pagable</option>
                <option value="paid">Pagado</option>
                <option value="no_payable">No pagable</option>
              </select>
            </div>
            {/* Block reason */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Bloqueo</label>
              <select value={filterBlockReason} onChange={e => setFilterBlockReason(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todos</option>
                <option value="no_scout">Sin scout</option>
                <option value="already_paid">Ya pagado</option>
                <option value="manual_review">Manual review</option>
                <option value="no_activation">Sin activacion</option>
                <option value="tier_not_reached">No alcanzo tier</option>
                <option value="min_activated_not_reached">Min. no alcanzado</option>
              </select>
            </div>
            {/* Scout */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Scout</label>
              <select value={filterScoutId} onChange={e => setFilterScoutId(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                <option value="">Todos</option>
                <option value="none">Sin scout</option>
                {scoutsList.map(s => (
                  <option key={s.id} value={String(s.id)}>
                    {s.scout_name}{s.scout_type ? ` (${s.scout_type})` : ''}
                  </option>
                ))}
              </select>
            </div>
            {/* Lifecycle / status */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Estado op.</label>
              <select value={driverLifecycleFilter} onChange={e => setDriverLifecycleFilter(e.target.value)}
                className="w-full border rounded px-2 py-1 text-[11px]">
                {DRIVER_LIFECYCLE_OPTIONS.map(o => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
            </div>
            {/* Min trips 7d */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Min trips 7D</label>
              <input type="number" value={filterMinTrips7d || ''} onChange={e => setFilterMinTrips7d(Number(e.target.value) || 0)}
                placeholder="0" min={0}
                className="w-full border rounded px-2 py-1 text-[11px]" />
            </div>
            {/* Sort */}
            <div>
              <label className="block text-[10px] text-gray-400 uppercase mb-0.5">Orden</label>
              <div className="flex gap-1">
                <select value={sortField} onChange={e => setSortField(e.target.value)}
                  className="flex-1 border rounded px-2 py-1 text-[11px]">
                  <option value="anchor_date">Fecha ancla</option>
                  <option value="hire_date">Hire date</option>
                  <option value="scout">Scout</option>
                  <option value="driver_name">Driver</option>
                  <option value="anchor_confidence">Confianza</option>
                </select>
                <button onClick={() => setSortDir(s => s === 'desc' ? 'asc' : 'desc')}
                  className="px-2 py-1 border rounded text-[11px] bg-gray-50 hover:bg-gray-100 font-mono"
                  title={sortDir === 'desc' ? 'Descendente' : 'Ascendente'}>
                  {sortDir === 'desc' ? '↓' : '↑'}
                </button>
              </div>
            </div>
            {/* Reset */}
            <div className="flex items-end">
              <button onClick={() => {
                setDriverSearch(''); setDriverOriginFilter(''); setDriverLifecycleFilter('')
                setFilterAnchorSource(''); setFilterAnchorConfidence(''); setFilterHasWarning('')
                setFilterPaymentStatus(''); setFilterBlockReason(''); setFilterScoutId('')
                setFilterMinTrips7d(0); setSortField('anchor_date'); setSortDir('desc')
              }} className="px-2 py-1 text-[10px] text-red-500 hover:text-red-700 border border-red-200 rounded">
                Limpiar filtros
              </button>
            </div>
          </div>
          {/* Freshness */}
          {driversFreshness && (
            <div className="mt-2 pt-2 border-t border-gray-100 flex items-center gap-2 text-[10px]">
              <span className="text-gray-400">Fuente:</span>
              <span className={`px-1.5 py-0.5 rounded ${
                driversFreshness.freshness_status === 'ok' ? 'bg-green-50 text-green-600' :
                driversFreshness.freshness_status === 'warning' ? 'bg-yellow-50 text-yellow-600' : 'bg-red-50 text-red-600'
              }`}>
                {driversFreshness.freshness_status?.toUpperCase()} · max hire: {driversFreshness.source_max_hire_date || '—'} · lag: {driversFreshness.data_lag_days}d
              </span>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* DRIVER TABLE — wide operational view */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm mb-2 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] whitespace-nowrap">
            <thead>
              <tr className="text-left text-[10px] text-gray-400 uppercase bg-gray-50/80 border-b border-gray-200 sticky top-0 z-10">
                {visibleCols.has('driver') && (
                  <>
                    <th className="px-2 py-1.5 font-medium sticky left-0 bg-gray-50/80 z-10">Driver</th>
                    <th className="px-2 py-1.5 font-medium w-16">Origen</th>
                  </>
                )}
                {visibleCols.has('anchor') && (
                  <>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60" title="Fecha usada para ordenar y evaluar la afiliacion. Sale de lead_created_at_fleet, lead_created_at_cabinet o hire_date fallback segun origen y disponibilidad.">Fecha ancla</th>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60">Fuente</th>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60">Conf.</th>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60 w-10">Gap</th>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60">Hire date</th>
                    <th className="px-2 py-1.5 font-medium bg-amber-50/60">Ancla tipo</th>
                    <th className="px-2 py-1.5 font-medium">Hire ref</th>
                    <th className="px-2 py-1.5 font-medium">Date basis</th>
                    <th className="px-2 py-1.5 font-medium">Lead cab.</th>
                    <th className="px-2 py-1.5 font-medium">Lead fl.</th>
                  </>
                )}
                {visibleCols.has('attribution') && (
                  <>
                    <th className="px-2 py-1.5 font-medium">Scout</th>
                    <th className="px-2 py-1.5 font-medium w-16">Asig.</th>
                  </>
                )}
                {visibleCols.has('progress') && (
                  <>
                    <th className="px-2 py-1.5 font-medium w-10">Act.</th>
                    <th className="px-2 py-1.5 font-medium w-10">7D</th>
                    <th className="px-2 py-1.5 font-medium w-10">14D</th>
                    <th className="px-2 py-1.5 font-medium w-10">5V7</th>
                    <th className="px-2 py-1.5 font-medium w-10">5V14</th>
                  </>
                )}
                {visibleCols.has('payment') && (
                  <>
                    <th className="px-2 py-1.5 font-medium">Pago</th>
                    <th className="px-2 py-1.5 font-medium">Monto</th>
                  </>
                )}
                {visibleCols.has('risk') && (
                  <>
                    <th className="px-2 py-1.5 font-medium">Bloqueo</th>
                    <th className="px-2 py-1.5 font-medium">Warning</th>
                    <th className="px-2 py-1.5 font-medium w-10">Rev.</th>
                  </>
                )}
                <th className="px-2 py-1.5 font-medium w-12">Accion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {driversLoading && drivers.length === 0 ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-24" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-10" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-16" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-16" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-12" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-12" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-15" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-15" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-12" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-10" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-10" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-14" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-10" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-16" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-16" /></td>
                    <td className="px-2 py-2"><div className="bg-gray-200 rounded animate-pulse h-3 w-10" /></td>
                    <td className="px-2 py-2" />
                  </tr>
                ))
              ) : filteredDrivers.length === 0 ? (
                <tr><td colSpan={20} className="px-2 py-8 text-center text-gray-400">No se encontraron conductores con los filtros actuales.</td></tr>
              ) : (
                filteredDrivers.map((d, idx) => {
                  const lifecycle = deriveDriverLifecycle(d)
                  const borderClass = DRIVER_LIFECYCLE_BORDER[lifecycle] || ''
                  const payStatus = d.payment_status || 'no_payable'
                  const anchorSource = d.anchor_source || 'unknown'
                  const anchorConf = d.anchor_confidence || 'unknown'
                  const hasWarning = !!(d.payment_trace_warning || d.reason === 'manual_review')
                  const isManualReview = d.reason === 'manual_review' || d.payment_trace_status === 'blocked_manual_exclude'
                  return (
                    <tr key={d.driver_id || idx}
                      onClick={() => setSelectedDriver(d)}
                      className={`${borderClass} hover:bg-blue-50/30 cursor-pointer transition-colors`}>
                      {/* Driver group */}
                      {visibleCols.has('driver') && (
                        <>
                          <td className="px-2 py-1.5 sticky left-0 bg-white z-5">
                            <div className="font-semibold text-gray-800 truncate max-w-[140px]">{d.driver_name || d.driver_id}</div>
                            <div className="text-[9px] text-gray-400 font-mono">{d.driver_id ? d.driver_id.substring(0, 14) : 'SIN ID'}</div>
                            {d.license && <div className="text-[9px] text-gray-300 font-mono">Lic: {d.license.substring(0, 10)}</div>}
                          </td>
                          <td className="px-2 py-1.5">
                            <span className={`px-1 py-0.5 rounded text-[9px] font-medium ${
                              d.origin === 'cabinet' ? 'bg-blue-50 text-blue-600' : d.origin === 'fleet' ? 'bg-purple-50 text-purple-600' : 'bg-gray-100 text-gray-500'
                            }`}>{d.origin || '—'}</span>
                          </td>
                        </>
                      )}
                      {/* Anchor date group */}
                      {visibleCols.has('anchor') && (
                        <>
                          <td className="px-2 py-1.5 bg-amber-50/20 font-mono text-gray-800">
                            {d.anchor_date ? d.anchor_date.substring(0, 10) : (d.hire_date || '—')}
                          </td>
                          <td className="px-2 py-1.5 bg-amber-50/20">
                            <span className={`px-1 py-0.5 rounded text-[9px] font-medium ${
                              anchorSource === 'lead_cabinet' ? 'bg-blue-50 text-blue-600' :
                              anchorSource === 'lead_fleet' ? 'bg-purple-50 text-purple-600' :
                              anchorSource === 'hire_date' ? 'bg-amber-50 text-amber-600' : 'bg-gray-100 text-gray-400'
                            }`}>{ANCHOR_SOURCE_LABEL[anchorSource] || anchorSource}</span>
                          </td>
                          <td className="px-2 py-1.5 bg-amber-50/20">
                            <span className={`px-1 py-0.5 rounded text-[9px] font-medium ${ANCHOR_CONFIDENCE_COLOR[anchorConf] || 'bg-gray-100 text-gray-400'}`}>
                              {anchorConf === 'strong' ? 'Fuerte' : anchorConf === 'medium' ? 'Medio' : anchorConf === 'weak' ? 'Debil' : '—'}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 bg-amber-50/20 text-center text-gray-500">
                            {d.anchor_gap_days != null ? `${d.anchor_gap_days}d` : '—'}
                          </td>
                          <td className="px-2 py-1.5 bg-amber-50/20 text-gray-600 font-mono">{d.hire_date ? d.hire_date.substring(0, 10) : '—'}</td>
                          <td className="px-2 py-1.5 bg-amber-50/20 text-[9px] text-gray-500">{d.anchor_type || '—'}</td>
                          <td className="px-2 py-1.5 font-mono text-gray-500 text-[9px]">{d.hire_date_reference ? d.hire_date_reference.substring(0, 10) : '—'}</td>
                          <td className="px-2 py-1.5 font-mono text-gray-400 text-[9px]">{d.date_basis || '—'}</td>
                          <td className="px-2 py-1.5 font-mono text-gray-500">{d.lead_created_at_cabinet ? d.lead_created_at_cabinet.substring(0, 10) : '—'}</td>
                          <td className="px-2 py-1.5 font-mono text-gray-500">{d.lead_created_at_fleet ? d.lead_created_at_fleet.substring(0, 10) : '—'}</td>
                        </>
                      )}
                      {/* Attribution */}
                      {visibleCols.has('attribution') && (
                        <>
                          <td className="px-2 py-1.5">
                            <span className={d.scout_name ? 'text-gray-700 font-medium' : 'text-gray-400 italic text-[9px]'}>
                              {d.scout_name || 'Sin scout'}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <span className={`px-1 py-0.5 rounded text-[9px] font-medium ${
                              d.attribution_status === 'assigned' ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600'
                            }`}>{d.attribution_status === 'assigned' ? 'OK' : 'NO'}</span>
                          </td>
                        </>
                      )}
                      {/* Progress */}
                      {visibleCols.has('progress') && (
                        <>
                          <td className="px-2 py-1.5 text-center">
                            <span className={d.activated_flag ? 'text-green-600 font-bold' : 'text-gray-300'}>{d.activated_flag ? 'Si' : '—'}</span>
                          </td>
                          <td className="px-2 py-1.5 text-center font-mono">
                            <span className={d.trips_7d >= 5 ? 'text-blue-600 font-bold' : 'text-gray-500'}>{d.trips_7d}</span>
                          </td>
                          <td className="px-2 py-1.5 text-center font-mono">
                            <span className={d.trips_14d >= 5 ? 'text-purple-600 font-bold' : 'text-gray-500'}>{d.trips_14d}</span>
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <span className={d.converted_5v7d ? 'text-blue-600 font-bold' : 'text-gray-300'}>{d.converted_5v7d ? 'Si' : '—'}</span>
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <span className={d.converted_5v14d ? 'text-purple-600 font-bold' : 'text-gray-300'}>{d.converted_5v14d ? 'Si' : '—'}</span>
                          </td>
                        </>
                      )}
                      {/* Payment */}
                      {visibleCols.has('payment') && (
                        <>
                          <td className="px-2 py-1.5">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                              payStatus === 'payable' ? 'bg-emerald-100 text-emerald-700' :
                              payStatus === 'paid' ? 'bg-teal-100 text-teal-700' :
                              'bg-gray-100 text-gray-500'
                            }`}>
                              {payStatus === 'payable' ? 'PAGABLE' : payStatus === 'paid' ? 'PAGADO' : 'NO PAGABLE'}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 font-mono text-gray-700 text-right">
                            {d.amount ? `S/ ${d.amount.toFixed(0)}` : '—'}
                          </td>
                        </>
                      )}
                      {/* Risk */}
                      {visibleCols.has('risk') && (
                        <>
                          <td className="px-2 py-1.5 text-[9px] text-gray-500">
                            {d.reason === 'no_scout' ? 'Sin scout' :
                             d.reason === 'no_activation' ? 'Sin activ.' :
                             d.reason === 'already_paid' ? 'Ya pagado' :
                             d.reason === 'min_activated_not_reached' ? 'Min activ.' :
                             d.reason === 'tier_not_reached' ? 'No tier' :
                             d.reason === 'manual_review' ? 'Rev manual' :
                             d.reason === 'manual_exclude' ? 'Excluido' : d.reason || '—'}
                          </td>
                          <td className="px-2 py-1.5">
                            {hasWarning && <span className="px-1 py-0.5 rounded text-[9px] bg-orange-100 text-orange-600 font-medium">WARN</span>}
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            {isManualReview && <span className="px-1 py-0.5 rounded text-[9px] bg-red-100 text-red-600 font-medium">REV</span>}
                          </td>
                        </>
                      )}
                      <td className="px-2 py-1.5 text-right">
                        <span className="text-gray-300 text-base leading-none cursor-pointer">&rsaquo;</span>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="px-3 py-1.5 border-t border-gray-100 flex items-center justify-between text-[10px] text-gray-400 flex-wrap gap-1">
          <div className="flex items-center gap-2">
            <span>Mostrando <strong className="text-gray-600">{drivers.length > 0 ? driverPage * driversPageSize + 1 : 0}</strong>-<strong className="text-gray-600">{Math.min((driverPage + 1) * driversPageSize, driversTotal)}</strong> de <strong className="text-gray-600">{driversTotal}</strong></span>
            <span className="text-gray-300">|</span>
            <span className="text-gray-300">{filteredDrivers.length} filtrados</span>
            {!driversHasNext && drivers.length > 0 && <span className="text-gray-300 ml-1">· fin</span>}
          </div>
          <div className="flex items-center gap-1.5">
            <select value={driversPageSize} onChange={e => {
              const newSize = Number(e.target.value)
              setDriversPageSize(newSize)
              setDriverPage(0)
              loadDrivers(0, false, newSize)
            }}
              className="border rounded px-1.5 py-0.5 text-[10px]">
              <option value="50">50/pag</option>
              <option value="100">100/pag</option>
              <option value="200">200/pag</option>
            </select>
            <button onClick={() => { const p = Math.max(0, driverPage - 1); setDriverPage(p); loadDrivers(p, false) }}
              disabled={driverPage === 0 || driversLoading}
              className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-30">Anterior</button>
            <span className="px-1 font-mono text-gray-500">Pag {driverPage + 1}</span>
            <button onClick={() => { const p = driverPage + 1; setDriverPage(p); loadDrivers(p, false) }}
              disabled={!driversHasNext || driversLoading}
              className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-30">Siguiente</button>
          </div>
        </div>
        {/* Filter scope note */}
        <div className="px-3 py-1 bg-amber-50/40 border-t border-amber-100 text-[9px] text-amber-700">
          Filtros server-side: origen, scout, busqueda de texto. Los demas filtros (confianza, warning, pago, bloqueo, estado op., trips) se aplican sobre los datos ya cargados en esta pagina.
        </div>
      </div>

      {/* ── WORKFLOW / SECONDARY TOOLS (collapsible) ── */}
      <div className="mb-4">
        <button onClick={() => setShowWorkflow(!showWorkflow)}
          className="text-xs font-medium text-gray-400 hover:text-gray-600 flex items-center gap-1"
        >
          {showWorkflow ? '▲' : '▼'} Workflow operativo y herramientas
        </button>
        {showWorkflow && (
          <div className="mt-3 space-y-4">
            {/* ── ATTENTION CARDS ── */}
            {(quickFilter === 'all' || quickFilter === 'blocked') && attentionCards.filter(c => c.level === 'critical').map(card => (
              <AttentionCard key={card.id} card={card} />
            ))}
            {(quickFilter === 'all' || quickFilter === 'warnings') && attentionCards.filter(c => c.level === 'warning').map(card => (
              <AttentionCard key={card.id} card={card} />
            ))}
            {(quickFilter === 'all' || quickFilter === 'pending' || quickFilter === 'trusted') && attentionCards.filter(c => c.level === 'operational').map(card => (
              <AttentionCard key={card.id} card={card} />
            ))}

            {/* ── WORKFLOW STEPPER ── */}
            <div ref={stepperRef} className={`bg-white border border-gray-200 rounded-xl shadow-sm ${pad}`}>
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
          </div>
        )}
      </div>

      {/* ── ANALYTICS ── */}
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

      {/* ── HERRAMIENTAS DE DIAGNOSTICO ── */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 mb-4">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Herramientas de diagnostico</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <a href="/scout-liq/anchor" className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-gray-100 hover:bg-gray-50 text-xs font-medium text-gray-600 hover:text-gray-800 transition-colors">
            <span className="w-5 h-5 rounded bg-amber-100 text-amber-600 flex items-center justify-center text-[10px] font-bold">A</span>
            Diagnostico de fechas / Anchor
          </a>
          <a href="/scout-liq/review-queue" className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-gray-100 hover:bg-gray-50 text-xs font-medium text-gray-600 hover:text-gray-800 transition-colors">
            <span className="w-5 h-5 rounded bg-purple-100 text-purple-600 flex items-center justify-center text-[10px] font-bold">R</span>
            Cola de revision
          </a>
          <a href="/scout-liq/salud" className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-gray-100 hover:bg-gray-50 text-xs font-medium text-gray-600 hover:text-gray-800 transition-colors">
            <span className="w-5 h-5 rounded bg-emerald-100 text-emerald-600 flex items-center justify-center text-[10px] font-bold">S</span>
            Salud de data
          </a>
        </div>
      </div>

      {/* ── DRIVER DETAIL DRAWER ── */}
      {selectedDriver && (
        <DriverDetailDrawer driver={selectedDriver} onClose={() => setSelectedDriver(null)} onDriverUpdated={() => { setSelectedDriver(null); loadDrivers(driverPage, false) }} />
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
