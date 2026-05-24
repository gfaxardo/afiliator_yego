import axios from 'axios'

const api = axios.create({
  baseURL: '/api/scout-liq',
  timeout: 120000,
})

export interface UnifiedPreviewLine {
  source_row: number
  licencia: string
  scout: string
  supervisor: string
  pagado: string
  monto_pagado: number
  fecha_pago: string
  fecha_atribucion?: string
  tipo_evento?: string
  status: string
  errors: string[]
  warnings: string[]
  deduced_actions: string[]
  driver_id_resolved: string | null
  scout_id_resolved: number | null
}

export interface UnifiedPreviewResponse {
  total_rows: number
  valid_rows: number
  error_rows: number
  duplicate_rows: number
  drivers_found: number
  drivers_not_found: number
  scouts_to_create: number
  supervisors_to_create: number
  assignments_to_create: number
  assignments_to_change: number
  assignments_already_exist: number
  payments_to_create: number
  already_paid: number
  amount_mismatch: number
  warnings: string[]
  lines: UnifiedPreviewLine[]
  apply_plan: any[]
  parse_metadata?: Record<string, any>
}

export type UnifiedApplyAction =
  | 'created_assignment'
  | 'reactivated_assignment'
  | 'created_payment_history'
  | 'no_change'
  | 'already_paid'
  | 'driver_not_found'
  | 'driver_not_found_observed_saved'
  | 'driver_not_found_observed_existing'
  | 'scout_not_found'
  | 'duplicate_existing'
  | 'conflict_existing_active_scout'
  | 'error'
  | 'validation_error'

export type UnifiedApplyLineStatus = 'ok' | 'warning' | 'observed' | 'manual_review' | 'error'

export interface UnifiedApplyLine {
  source_row?: number
  row?: number
  licencia?: string
  scout?: string
  driver_id?: string
  scout_id?: number
  scout_name?: string
  action: UnifiedApplyAction
  status: UnifiedApplyLineStatus
  saved: boolean
  message: string
  what_happened?: string[]
  error_code?: string | null
  observed_affiliation_created?: boolean
  observed_affiliation_id?: number | null
  observed_affiliation_status?: string
  assignment_created?: boolean
  payment_created?: boolean
  eligible_for_cutoff?: boolean
  reconciliation_status?: string | null
  driver_operational_state?: string | null
  // Parity truth source (from backend streaming)
  parity_status?: string
  parity_explanation?: string
  system_confidence_level?: string
  operational_readiness?: string
  next_action?: string
  driver_resolution_status?: string
  assignment_status?: string
  payment_history_status?: string
  applied_entities?: string
  skipped_entities?: string
  rejected_entities?: string
}

export interface UnifiedApplySummary {
  total_rows?: number
  applied: number
  skipped?: number
  created_assignment?: number
  created_payment_history?: number
  no_change: number
  conflicts: number
  already_paid: number
  not_found: number
  errors: number
  observed_created?: number
  observed_existing?: number
  rejected_no_evidence?: number
  commit_ok: boolean
  commit_error?: string | null
  done?: boolean
}

export interface UnifiedApplyDetail {
  source_row: number
  status: string
  reason?: string | null
  driver_id?: string | null
  scout_id?: number | null
  scout_name?: string | null
  payment_created: boolean
  assignment_created: boolean
  observed_affiliation_created?: boolean | null
  observed_affiliation_id?: number | null
  observed_affiliation_status?: string | null
  eligible_for_cutoff?: boolean | null
  reconciliation_status?: string | null
  driver_operational_state?: string | null
  what_happened?: string[] | null
  action_requested?: string | null
  action_executed?: string | null
  skipped_reason?: string | null
  existing_assignment_id?: number | null
}

export interface UnifiedApplyResponse {
  applied: number
  skipped: number
  errors: number
  no_change?: number
  conflicts?: number
  already_paid?: number
  not_found?: number
  observed_created?: number
  observed_existing?: number
  rejected_no_evidence?: number
  details: UnifiedApplyDetail[]
  assignments_new: number
  assignments_existing: number
  payments_new: number
  payments_existing: number
  commit_ok?: boolean | null
  commit_error?: string | null
}

export async function downloadTemplate(): Promise<Blob> {
  const r = await api.get('/unified-load/template', { responseType: 'blob' })
  return r.data
}

export async function downloadPreviewReport(file: File): Promise<Blob> {
  const formData = new FormData()
  formData.append('file', file)
  const r = await api.post('/unified-load/report/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: 'blob',
  })
  return r.data
}

export async function downloadApplyReport(previewLines: any[], applyLines: any[]): Promise<Blob> {
  const r = await api.post('/unified-load/report/apply', {
    preview_lines: previewLines,
    apply_lines: applyLines,
  }, {
    responseType: 'blob',
  })
  return r.data
}

export async function fetchPreviewResult(previewId: string): Promise<any> {
  const r = await api.get(`/unified-load/preview-result/${previewId}`)
  return r.data
}

export async function downloadRescueCsv(previewId: string): Promise<Blob> {
  const r = await api.get(`/unified-load/rescue-csv/${previewId}`, { responseType: 'blob' })
  return r.data
}

export async function previewUnifiedLoad(file: File): Promise<UnifiedPreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const r = await api.post('/unified-load/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}

export async function previewUnifiedLoadStream(
  file: File,
  onLine: (line: any) => void,
  onSummary: (summary: any) => void,
  onError: (err: string) => void,
  onEvent?: (event: any) => void,
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 120000)

  try {
    const response = await fetch('/api/scout-liq/unified-load/preview-stream', {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    })

    if (!response.ok) {
      const text = await response.text()
      onError(text)
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      onError('No se pudo leer el stream')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let lastEventTime = Date.now()

    const readLoop = async () => {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        lastEventTime = Date.now()
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const parsed = JSON.parse(line)
            if (parsed.type === 'summary') {
              onSummary(parsed)
            } else if (parsed.type === 'structural_error') {
              onError('Error estructural: ' + JSON.stringify(parsed))
            } else if (parsed.type === 'started' || parsed.type === 'file_parsed' ||
                       parsed.type === 'caches_loading' || parsed.type === 'caches_progress' ||
                       parsed.type === 'caches_loaded' || parsed.type === 'processing_started') {
              if (onEvent) onEvent(parsed)
            } else if (parsed.type === 'line') {
              onLine(parsed)
            } else {
              onLine(parsed)
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    }

    await readLoop()
  } finally {
    clearTimeout(timeoutId)
  }
}

export function parseApplyLine(raw: any): UnifiedApplyLine {
  return {
    source_row: raw.source_row ?? raw.row,
    licencia: raw.licencia ?? '',
    scout: raw.scout ?? '',
    driver_id: raw.driver_id ?? '',
    scout_id: raw.scout_id ?? undefined,
    scout_name: raw.scout_name ?? raw.scout ?? '',
    action: raw.action ?? (raw.status === 'error' ? 'error' : 'no_change'),
    status: raw.status ?? 'ok',
    saved: raw.saved ?? false,
    message: raw.message ?? (raw.what_happened || []).join(' | ') ?? '',
    what_happened: raw.what_happened ?? [],
    error_code: raw.error_code ?? null,
    // Parity fields from backend truth source
    parity_status: raw.parity_status ?? undefined,
    parity_explanation: raw.parity_explanation ?? undefined,
    system_confidence_level: raw.system_confidence_level ?? undefined,
    operational_readiness: raw.operational_readiness ?? undefined,
    next_action: raw.next_action ?? undefined,
    driver_resolution_status: raw.driver_resolution_status ?? undefined,
    assignment_status: raw.assignment_status ?? undefined,
    payment_history_status: raw.payment_history_status ?? undefined,
    observed_affiliation_status: raw.observed_affiliation_status ?? undefined,
    applied_entities: raw.applied_entities ?? undefined,
    skipped_entities: raw.skipped_entities ?? undefined,
    rejected_entities: raw.rejected_entities ?? undefined,
  }
}

export function parseApplySummary(raw: any): UnifiedApplySummary {
  return {
    total_rows: raw.total ?? raw.applied + (raw.skipped ?? 0),
    applied: raw.applied ?? 0,
    skipped: raw.skipped ?? 0,
    no_change: raw.no_change ?? 0,
    conflicts: raw.conflicts ?? 0,
    already_paid: raw.already_paid ?? 0,
    not_found: raw.not_found ?? 0,
    errors: raw.errors ?? 0,
    commit_ok: raw.commit_ok !== false,
    commit_error: raw.commit_error ?? null,
    done: raw.done ?? false,
  }
}

export async function applyUnifiedLoadStream(
  plan: any[],
  onLine: (line: UnifiedApplyLine) => void,
  onSummary: (summary: UnifiedApplySummary) => void,
  onError: (err: string) => void,
): Promise<void> {
  const response = await fetch('/api/scout-liq/unified-load/apply-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apply_plan: plan }),
  })

  if (!response.ok) {
    const text = await response.text()
    onError(text)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) { onError('No se pudo leer el stream'); return }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const parsed = JSON.parse(line)
        if (parsed.type === 'summary') {
          onSummary(parseApplySummary(parsed))
        } else {
          onLine(parseApplyLine(parsed))
        }
      } catch { /* skip */ }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// OBSERVED AFFILIATIONS API
// ═══════════════════════════════════════════════════════════════════════════

export interface ObservedPreviewLine {
  row: number
  fecha_afiliacion: string | null
  origen: string | null
  scout: string | null
  supervisor: string | null
  nombre_driver: string | null
  licencia: string | null
  telefono: string | null
  normalized_license: string | null
  normalized_phone: string | null
  matched_driver_id: string | null
  match_status: string | null
  match_confidence: string | null
  match_reason: string | null
  official_source_status: string | null
  review_status: string | null
  has_error: boolean
}

export interface ObservedPreviewSummary {
  total: number
  matched_high: number
  matched_medium: number
  manual_review: number
  unmatched: number
  official_missing: number
  errors: number
  valid: number
  duplicate_claims: number
}

export interface ObservedPreviewResponse {
  total_rows: number
  lines: ObservedPreviewLine[]
  errors: { row: number; error: string }[]
  summary: ObservedPreviewSummary
}

export interface ObservedApplyResponse {
  saved: number
  duplicates: number
  duplicate_claims: number
  errors: number
  error_details: { row: number; error: string }[]
}

export interface ObservedItem {
  id: number
  reported_affiliation_date: string | null
  reported_origin: string | null
  reported_scout_name: string | null
  reported_supervisor_name: string | null
  reported_driver_name: string | null
  reported_license: string | null
  reported_phone: string | null
  matched_driver_id: string | null
  match_status: string | null
  match_confidence: string | null
  match_reason: string | null
  official_source_status: string | null
  review_status: string | null
  review_notes: string | null
  created_at: string | null
}

export interface ObservedListResponse {
  total: number
  limit: number
  offset: number
  items: ObservedItem[]
}

const API_BASE = '/api/scout-liq'
const apiObserved = axios.create({ baseURL: API_BASE, timeout: 120000 })

export async function previewObservedAffiliations(file: File): Promise<ObservedPreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await apiObserved.post('/observed-affiliations/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function applyObservedAffiliations(file: File): Promise<ObservedApplyResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await apiObserved.post('/observed-affiliations/apply', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function listObservedAffiliations(
  reviewStatus?: string,
  matchStatus?: string,
  limit = 100,
  offset = 0,
): Promise<ObservedListResponse> {
  const params: Record<string, string | number> = { limit, offset }
  if (reviewStatus) params.review_status = reviewStatus
  if (matchStatus) params.match_status = matchStatus
  const res = await apiObserved.get('/observed-affiliations', { params })
  return res.data
}

export async function updateObservedReview(
  id: number,
  reviewStatus: string,
  reviewNotes?: string,
): Promise<any> {
  const res = await apiObserved.put(`/observed-affiliations/${id}/review`, {
    review_status: reviewStatus,
    review_notes: reviewNotes,
  })
  return res.data
}

export function getObservedExportUrl(): string {
  return `${API_BASE}/observed-affiliations/export`
}

// ═══════════════════════════════════════════════════════════════════════════
// RECONCILIATION & GOVERNANCE API
// ═══════════════════════════════════════════════════════════════════════════

export interface ReconciliationSummary {
  attribution_integrity_pct: number
  total_observed: number
  total_pending: number
  total_validated: number
  total_rejected: number
  matched_high: number
  matched_medium: number
  manual_review: number
  unmatched: number
  official_missing: number
  official_found: number
  operational_gaps: number
  total_source_drivers: number
  total_drivers_in_db: number
  auto_detectable_reconciliations: number
  active_conflicts: number
  aging: { pending_24h: number; pending_1_3d: number; pending_gt_3d: number }
  scouts_with_most_conflicts: { scout: string; count: number }[]
}

export interface ReconciliationItem {
  observed_id: number
  driver_id: string | null
  reported_driver_name: string | null
  reported_scout_name: string | null
  reported_supervisor_name: string | null
  reported_origin: string | null
  reported_license: string | null
  reported_phone: string | null
  match_status: string | null
  match_confidence: string | null
  match_reason: string | null
  official_source_status: string | null
  review_status: string | null
  review_notes: string | null
  reported_affiliation_date: string | null
  observed_created_at: string | null
  classification: string
  confidence_level: string
  in_official: boolean
  has_active_assignment: boolean
  has_paid_blocking: boolean
  has_cutoff_line: boolean
  aging: string
}

export interface ReconciliationListResponse {
  total: number
  limit: number
  offset: number
  items: ReconciliationItem[]
}

export interface DriverTimeline {
  driver_id: string
  in_official_source: boolean
  first_trip_at: string | null
  observed_history: {
    id: number; observed_at: string; reported_scout: string
    match_confidence: string; review_status: string; official_source_status: string
  }[]
  cutoff_lines: {
    id: number; cutoff_run_id: number; scout_id: number
    attribution_source: string; payment_status: string
    calculated_amount: number | null; line_explanation: string
    created_at: string
  }[]
  paid_history: {
    id: number; paid_at: string; amount_paid: number
    import_source: string; blocks_future_payment: boolean
  }[]
  audit_trail: {
    id: number; action: string; actor: string
    reason: string; reconciliation_status: string; created_at: string
  }[]
}

export interface ReconciliationActionResult {
  observed_id: number
  action: string
  error?: string
  before?: any
  after?: any
  assignment_created?: boolean
  driver_id?: string
}

export interface AutoDetectItem {
  observed_id: number
  driver_id: string
  reported_scout_name: string
  reported_driver_name: string
  original_official_status: string
  now_in_official: boolean
  suggested_action: string
}

export interface IntegrityMetrics {
  attribution_integrity_pct: number
  missing_attribution_rate: number
  observed_only_count: number
  official_only_count: number
  active_conflicts: number
  auto_detectable: number
  scouts_with_conflicts: { scout: string; count: number }[]
  aging: { pending_24h: number; pending_1_3d: number; pending_gt_3d: number }
  total_observed: number
  total_validated: number
  total_rejected: number
}

export interface ReconciliationFreshness {
  last_refreshed_at: string | null
  age_minutes: number | null
  status: 'fresh' | 'stale' | 'stale_critical' | 'never_refreshed' | 'error'
  last_error: string | null
  row_count: number | null
  refresh_duration_ms: number | null
}

export interface OperationalGapsBreakdown {
  label: string
  count: number
  description: string
}

export interface OperationalGapsDiagnostic {
  total_operational_gaps: number
  total_source_drivers: number
  gap_rate_pct: number
  note: string
  breakdown: OperationalGapsBreakdown[]
}

const apiRec = axios.create({ baseURL: API_BASE, timeout: 60000 })

export async function getReconciliationSummary(): Promise<ReconciliationSummary> {
  const res = await apiRec.get('/reconciliation/summary')
  return res.data
}

export async function getIntegrityMetrics(): Promise<IntegrityMetrics> {
  const res = await apiRec.get('/reconciliation/integrity')
  return res.data
}

export async function getReconciliationList(params: Record<string, string | number>): Promise<ReconciliationListResponse> {
  const cleanParams: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') cleanParams[k] = v
  }
  const res = await apiRec.get('/reconciliation/list', { params: cleanParams })
  return res.data
}

export async function autoDetectReconciliations(): Promise<AutoDetectItem[]> {
  const res = await apiRec.post('/reconciliation/auto-detect')
  return res.data
}

export async function refreshReconciliationView(): Promise<{ status: string; duration_ms: number; row_count: number }> {
  const res = await apiRec.post('/reconciliation/refresh-view')
  return res.data
}

export async function getReconciliationFreshness(): Promise<ReconciliationFreshness> {
  const res = await apiRec.get('/reconciliation/freshness')
  return res.data
}

export async function getOperationalGapsDiagnostic(): Promise<OperationalGapsDiagnostic> {
  const res = await apiRec.get('/reconciliation/operational-gaps/diagnostic')
  return res.data
}

export async function approveReconciliation(id: number, reason?: string): Promise<ReconciliationActionResult> {
  const res = await apiRec.post(`/reconciliation/${id}/approve`, { reason })
  return res.data
}

export async function rejectReconciliation(id: number, reason?: string): Promise<ReconciliationActionResult> {
  const res = await apiRec.post(`/reconciliation/${id}/reject`, { reason })
  return res.data
}

export async function mergeReconciliation(id: number, assign_scout?: boolean): Promise<ReconciliationActionResult> {
  const res = await apiRec.post(`/reconciliation/${id}/merge`, { assign_scout })
  return res.data
}

export async function getDriverTimeline(driverId: string): Promise<DriverTimeline> {
  const res = await apiRec.get(`/reconciliation/driver/${encodeURIComponent(driverId)}/timeline`)
  return res.data
}

export function getReconciliationExportUrl(): string {
  return `${API_BASE}/reconciliation/export`
}
