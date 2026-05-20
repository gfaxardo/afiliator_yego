import axios from 'axios'

const api = axios.create({
  baseURL: '/api/scout-liq',
  timeout: 30000,
})

// Long timeout instance for large file operations (preview/commit)
const apiLong = axios.create({
  baseURL: '/api/scout-liq',
  timeout: 300000, // 5 minutes for large files
})

export interface HealthResponse {
  status: string
  environment: string
  source_table: string
}

export interface ScoutResponse {
  id: number
  scout_name: string
  document_number: string | null
  phone: string | null
  email: string | null
  country: string | null
  city: string | null
  scout_type: string | null
  status: string | null
  supervisor_name_raw: string | null
  supervisor_id: number | null
  imported_from: string | null
  source_sheet: string | null
  source_row: number | null
  external_key: string | null
  active_from: string | null
  active_to: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ScoutCreate {
  scout_name: string
  document_number?: string
  phone?: string
  email?: string
  country?: string
  city?: string
  scout_type?: string
  status?: string
}

export interface TierResponse {
  id: number
  scheme_id: number
  min_conversion_rate: number
  payment_per_converted_driver: number
  currency: string
  active: boolean
}

export interface SchemeResponse {
  id: number
  scheme_name: string
  origin: string | null
  scout_type: string | null
  country: string | null
  city: string | null
  min_affiliations: number
  active: boolean
  effective_from: string | null
  effective_to: string | null
  tiers: TierResponse[]
  created_at: string | null
}

export interface DiagnosticResponse {
  source_table: string
  columns: Array<{ name: string; type: string }>
  total_rows: number
  null_driver_id: number
  null_hire_date: number
  hire_date_min: string | null
  hire_date_max: string | null
}

export interface SourceDriver {
  driver_id: string | null
  driver_nombre: string | null
  driver_apellido: string | null
  driver_placa: string | null
  driver_phone: string | null
  park_name: string | null
  park_id: string | null
  license: string | null
  origin: string | null
  legacy_viajes_0_7_flag: boolean | null
  legacy_viajes_8_14_flag: boolean | null
  total_orders: number | null
  trips_0_7_count: number | null
  trips_8_14_count: number | null
  trips_0_14_count: number | null
  hire_date_raw: string | null
  hire_date_parsed: string | null
  source_status: string | null
  source_quality_status: string | null
  status: string | null
  segment: string | null
  stage: string | null
  conexion: string | null
  last_active_date: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SourceDriverList {
  total: number
  limit: number
  offset: number
  drivers: SourceDriver[]
}

export interface Assignment {
  id: number
  driver_id: string
  scout_id: number
  origin: string | null
  hire_date: string | null
  notes: string | null
  status: string | null
  source_hire_date_raw: string | null
  source_origin: string | null
  assigned_by: string | null
  assigned_at: string | null
  created_at: string | null
  updated_at: string | null
  scout_name: string | null
}

export interface AssignmentCreate {
  driver_id: string
  scout_id: number
  origin?: string
  notes?: string
}

export interface AssignmentUploadResult {
  total_rows: number
  created: number
  skipped_duplicates: number
  invalid_driver: number
  invalid_scout: number
  missing_hire_date_warnings: number
  errors: string[]
  warnings: string[]
}

export interface SourceSummary {
  total_rows: number
  with_hire_date: number
  without_hire_date: number
  with_trips_0_7: number
  without_trips_0_7: number
  null_trips_0_7: number
  with_trips_8_14: number
  without_trips_8_14: number
  null_trips_8_14: number
  by_origin: Array<{ origin: string; count: number }>
  assigned_drivers: number
  unassigned_drivers: number
}

// Existing APIs

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get('/health')
  return data
}

export async function getDiagnostic(): Promise<DiagnosticResponse> {
  const { data } = await api.get('/source/diagnostic')
  return data
}

export async function getScouts(params?: {
  status?: string
  scout_type?: string
}): Promise<ScoutResponse[]> {
  const { data } = await api.get('/scouts', { params })
  return data
}

export async function createScout(scout: ScoutCreate): Promise<ScoutResponse> {
  const { data } = await api.post('/scouts', scout)
  return data
}

export async function getSchemes(): Promise<SchemeResponse[]> {
  const { data } = await api.get('/schemes')
  return data
}

export async function getTiers(schemeId?: number): Promise<TierResponse[]> {
  const { data } = await api.get('/tiers', { params: { scheme_id: schemeId } })
  return data
}

export async function getSourceDrivers(params?: {
  hire_date_from?: string
  hire_date_to?: string
  origin?: string
  limit?: number
  offset?: number
}): Promise<SourceDriverList> {
  const { data } = await api.get('/source/drivers', { params })
  return data
}

export async function getSourceDriver(driverId: string): Promise<SourceDriver> {
  const { data } = await api.get(`/source/drivers/${encodeURIComponent(driverId)}`)
  return data
}

export async function getSourceSummary(): Promise<SourceSummary> {
  const { data } = await api.get('/source/summary')
  return data
}

export async function getAssignments(params?: {
  scout_id?: number
  status?: string
}): Promise<Assignment[]> {
  const { data } = await api.get('/assignments', { params })
  return data
}

export async function createAssignment(
  assignment: AssignmentCreate
): Promise<any> {
  const { data } = await api.post('/assignments', assignment)
  return data
}

export async function deactivateAssignment(id: number): Promise<any> {
  const { data } = await api.delete(`/assignments/${id}`)
  return data
}

export async function getUnassignedDrivers(params?: {
  limit?: number
  offset?: number
}): Promise<SourceDriverList> {
  const { data } = await api.get('/assignments/unassigned-drivers', { params })
  return data
}

export async function uploadAssignments(
  file: File
): Promise<AssignmentUploadResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/assignments/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export interface QualityContract {
  status: string
  can_compute_trip_counts: boolean
  trip_sources: { trips_2025: boolean; trips_2026: boolean }
  uses_legacy_booleans_for_payment: boolean
  sample_driver_trip_count: { driver_id: string; hire_date: string; trips_0_7_count: number } | null
  errors: string[]
  fields: Record<string, string>
}

export async function getQualityContract(): Promise<QualityContract> {
  const { data } = await api.get('/source/quality-contract')
  return data
}

export interface CreateCutoffParams {
  cutoff_name: string
  hire_date_from: string
  hire_date_to: string
  scheme_id: number
  origin_filter?: string
  country_filter?: string
  city_filter?: string
  scout_type_filter?: string
}

export async function createCutoff(params: CreateCutoffParams): Promise<any> {
  const { data } = await api.post('/cutoffs', null, { params })
  return data
}

export async function listCutoffs(): Promise<any[]> {
  const { data } = await api.get('/cutoffs')
  return data
}

export async function getCutoffSummary(cutoffId: number): Promise<any[]> {
  const { data } = await api.get(`/cutoffs/${cutoffId}/summary`)
  return data
}

export async function getCutoffLines(cutoffId: number, scoutId?: number): Promise<any[]> {
  const { data } = await api.get(`/cutoffs/${cutoffId}/lines`, { params: scoutId ? { scout_id: scoutId } : {} })
  return data
}

export async function recalculateCutoff(cutoffId: number): Promise<any> {
  const { data } = await api.post(`/cutoffs/${cutoffId}/recalculate`)
  return data
}

export async function reviewCutoff(cutoffId: number): Promise<any> {
  const { data } = await api.post(`/cutoffs/${cutoffId}/review`)
  return data
}

export async function approveCutoff(cutoffId: number): Promise<any> {
  const { data } = await api.post(`/cutoffs/${cutoffId}/approve`)
  return data
}

export async function markCutoffPaid(cutoffId: number): Promise<any> {
  const { data } = await api.post(`/cutoffs/${cutoffId}/mark-paid`)
  return data
}

// ── Fase 4: Paid History ──

export interface PaidHistoryItem {
  id: number
  cutoff_run_id: number | null
  scout_id: number
  driver_id: string | null
  driver_license_raw: string | null
  scout_name_raw: string | null
  supervisor_id: number | null
  payment_scheme_id: number | null
  payment_scheme_name: string | null
  payment_scheme_type: string | null
  payment_rule: string | null
  amount_paid: number
  currency: string
  paid_at: string | null
  import_source: string | null
  payment_component: string | null
  milestone: string | null
  cutoff_external_id: string | null
  cutoff_window_from: string | null
  cutoff_window_to: string | null
  reason: string | null
  status: string
  unique_hash: string | null
  created_at: string | null
}

export interface PaidHistoryList {
  total: number
  limit: number
  offset: number
  items: PaidHistoryItem[]
}

export async function getPaidHistory(params?: {
  cutoff_run_id?: number
  scout_id?: number
  supervisor_id?: number
  driver_license_raw?: string
  payment_component?: string
  import_source?: string
  limit?: number
  offset?: number
}): Promise<PaidHistoryList> {
  const { data } = await api.get('/paid-history', { params })
  return data
}

export async function getPaidHistoryItem(id: number): Promise<any> {
  const { data } = await api.get(`/paid-history/${id}`)
  return data
}

// ── Fase 4: Historical Import ──

export interface HistoricalImportPreviewResult {
  batch_id?: number
  source_file: string
  sheet: string
  total_rows: number
  will_import: number
  will_reject: number
  manual_review: number
  duplicate_count: number
  total_amount: number
  lines: any[]
}

export interface HistoricalImportCommitResult {
  batch_id: number
  status: string
  imported: number
  rejected: number
  manual_review: number
  duplicates: number
  amount_imported: number
}

export interface HistoricalImportBatch {
  id: number
  upload_batch_id: string | null
  source_file: string | null
  uploaded_by: string | null
  status: string
  total_rows: number
  imported_count: number
  rejected_count: number
  manual_review_count: number
  duplicate_count: number
  amount_imported: number
  notes: string | null
  created_at: string | null
}

export async function previewHistoricalImport(file: File, sheet?: string): Promise<HistoricalImportPreviewResult> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/historical-imports/preview${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function commitHistoricalImport(batchId: number, uploadedBy?: string): Promise<HistoricalImportCommitResult> {
  const params = new URLSearchParams()
  params.append('batch_id', String(batchId))
  if (uploadedBy) params.append('uploaded_by', uploadedBy)
  const { data } = await apiLong.post(`/historical-imports/commit?${params}`)
  return data
}

export async function listHistoricalImports(): Promise<HistoricalImportBatch[]> {
  const { data } = await api.get('/historical-imports')
  return data
}

export async function getHistoricalImportLines(batchId: number, importStatus?: string): Promise<any[]> {
  const params: any = {}
  if (importStatus) params.import_status = importStatus
  const { data } = await api.get(`/historical-imports/${batchId}/lines`, { params })
  return data
}

// ── Operation View ──

export interface OperationSummary {
  total_affiliations: number
  total_with_driver: number
  total_without_driver: number
  total_with_scout: number
  total_without_scout: number
  total_manual_review: number
  total_paid_history: number
  total_paid_amount: number
  total_blocks_future: number
  total_financial_only: number
  total_alerts_critical: number
  total_alerts_warning: number
  scope_type?: string
  scope_label?: string
  current_iso_week?: string
  current_iso_week_label?: string
  latest_week_with_data?: string
  latest_week_with_data_label?: string
  by_iso_week: { iso_year: number; iso_week: number; label: string; total: number; with_driver: number; without_driver?: number; paid_count: number; paid_amount: number; blocks_future: number; manual_review: number }[]
}

export interface AffiliationRow {
  row_id: number
  source_type: string
  batch_id: number
  source_sheet: string
  source_row: number
  iso_year: number | null
  iso_week: number | null
  iso_week_label: string
  iso_week_start?: string
  iso_week_end?: string
  iso_week_label_full?: string
  hire_date: string | null
  origin: string | null
  driver_id: string | null
  driver_license_raw: string | null
  driver_name_raw: string | null
  driver_display_name?: string
  driver_apellido?: string
  driver_nombre?: string
  scout_id: number | null
  scout_name: string | null
  supervisor_id: number | null
  supervisor_name: string | null
  trips_0_7_count: string
  trips_8_14_count: string
  trips_0_14_count: number | null
  converted_5v_7d: number | null
  attribution_status: string | null
  attribution_reason: string | null
  assignment_status: string
  payment_financial_status: string | null
  payment_blocking_status: string | null
  blocks_future_payment: boolean | null
  blocking_display?: string
  paid_history_id: number | null
  amount_paid: number | null
  currency: string | null
  resolution_status: string | null
  final_status: string | null
  alert_level: string
  alert_codes: string[]
}

export interface AffiliationsResponse {
  total: number
  limit: number
  offset: number
  items: AffiliationRow[]
}

export interface OperationFilters {
  current_iso_week: string
  current_iso_week_label: string
  has_data_for_current_week: boolean
  latest_iso_week_with_data: string | null
  latest_iso_week_with_data_label: string | null
  default_week_iso: string
  weeks: { year: number; week: number; label: string }[]
  scouts: { id: number; name: string }[]
  origins: string[]
  alert_types: { value: string; label: string }[]
}

export async function getOperationSummary(params?: Record<string, any>): Promise<OperationSummary> {
  const { data } = await api.get('/operation/summary', { params })
  return data
}

export async function getOperationFilters(): Promise<OperationFilters> {
  const { data } = await api.get('/operation/filters')
  return data
}

export async function getAffiliations(params?: Record<string, any>): Promise<AffiliationsResponse> {
  const { data } = await api.get('/operation/affiliations', { params })
  return data
}

export async function getAffiliationDetail(rowId: number): Promise<any> {
  const { data } = await api.get(`/operation/affiliations/${rowId}`)
  return data
}

// ── Canonical Operation ──

export interface CanonicalDriver {
  driver_id: string | null
  driver_name: string
  license: string | null
  hire_date: string | null
  iso_week: string | null
  iso_week_label: string | null
  origin: string | null
  city: string | null
  country: string | null
  scout_id: number | null
  scout_name: string | null
  supervisor_name: string | null
  attribution_status: string
  trips_7d: number
  trips_14d: number
  activated_flag: boolean
  converted_5v7d: boolean
  converted_5v14d: boolean
  driver_lifecycle_status: string
  legacy_viajes_0_7: boolean | null
  legacy_viajes_8_14: boolean | null
  total_orders: number | null
  payment_status: string
  payment_origin: string
  payment_rule_label: string | null
  payment_evidence_label: string | null
  payment_trace_status: string | null
  payment_trace_warning: string | null
  payment_basis_label: string | null
  amount: number | null
  paid_history_id: number | null
  reason: string
  counts_as_activated_base: boolean
  counts_as_quality_5v7d: boolean
  counts_for_payment: boolean
  scout_activated_base: number
  scout_quality_5v7d: number
  scout_conversion_rate_5v7d: number
  scout_tier_amount: number
  scout_tier_threshold: number
  payment_formula_label: string | null
  source_driver_status: string | null
  source_updated_at: string | null
}

export interface CanonicalFreshness {
  source_max_hire_date: string | null
  data_lag_days: number | null
  source_max_updated_at: string | null
  source_max_created_at: string | null
  total_source_rows: number | null
  null_invalid_driver_id_count: number | null
  null_hire_date_count: number | null
  freshness_status: string
}

export interface CanonicalSnapshotResponse {
  total: number
  limit: number
  offset: number
  items: CanonicalDriver[]
  freshness: CanonicalFreshness
}

export interface OperationDiagnosticResponse {
  source_table: string
  filters_applied: Record<string, any>
  base_counts: {
    total_source_drivers: number
    drivers_with_scout: number
    drivers_without_scout: number
    null_invalid_driver_id: number
  }
  trip_metrics: {
    activated_1plus_7d: number
    converted_5v7d: number
    converted_5v14d: number
  }
  payment_metrics: {
    paid_history_total: number
    paid_cutoff_engine: number
    paid_historical_upload: number
    not_payable_with_activation: number
  }
  freshness: {
    source_max_hire_date: string | null
    source_max_updated_at: string | null
    source_max_created_at: string | null
    data_lag_days: number | null
    freshness_status: string
  }
  attribution_quality: {
    assignment_conflicts: number
  }
}

export async function getCanonicalOperation(params?: {
  hire_date_from?: string
  hire_date_to?: string
  origin?: string
  scout_id?: number
  attribution_status?: string
  payment_status?: string
  limit?: number
  offset?: number
}): Promise<CanonicalSnapshotResponse> {
  const { data } = await api.get('/operation/canonical', { params })
  return data
}

export async function getOperationDiagnostic(params?: {
  hire_date_from?: string
  hire_date_to?: string
  origin?: string
  scout_id?: number
}): Promise<OperationDiagnosticResponse> {
  const { data } = await api.get('/operation/diagnostic', { params })
  return data
}

export function getHistoricalErrorsUrl(batchId: number): string {
  return `${api.defaults.baseURL}/historical-imports/${batchId}/errors.csv`
}

// ── Fase 4: Scout Bulk Upload ──

export interface ScoutUploadPreview {
  sheet: string
  total_rows: number
  will_create: number
  will_update: number
  duplicate_skipped: number
  manual_review: number
  rejected: number
  lines: any[]
}

export interface ScoutUploadCommit {
  sheet: string
  total_rows: number
  created: number
  updated: number
  duplicate_skipped: number
  manual_review: number
  rejected: number
}

export async function previewScoutUpload(file: File, sheet?: string): Promise<ScoutUploadPreview> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/scouts/upload-preview${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function commitScoutUpload(file: File, sheet?: string): Promise<ScoutUploadCommit> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/scouts/upload-commit${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Fase 4: Scheme Import ──

export interface SchemeVersionItem {
  id: number
  scheme_name: string
  scheme_type: string
  origin: string | null
  scout_type: string | null
  valid_from: string | null
  valid_to: string | null
  active: boolean
  config_json: string | null
  source_sheet: string | null
  source_row: number | null
  created_by: string | null
  created_at: string | null
  change_reason: string | null
}

export async function previewSchemeImport(file: File, sheet?: string): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/schemes/import-preview${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function commitSchemeImport(file: File, sheet?: string, createdBy?: string): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  let url = `/schemes/import-commit`
  if (sheet) url += `?sheet=${encodeURIComponent(sheet)}`
  if (createdBy) url += `${sheet ? '&' : '?'}created_by=${encodeURIComponent(createdBy)}`
  const { data } = await api.post(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getSchemeVersions(schemeType?: string, activeOnly?: boolean): Promise<SchemeVersionItem[]> {
  const params: any = {}
  if (schemeType) params.scheme_type = schemeType
  if (activeOnly !== undefined) params.active_only = activeOnly
  const { data } = await api.get('/scheme-versions', { params })
  return data
}

export async function getSchemeChangeLog(schemeId?: number): Promise<any[]> {
  const params: any = {}
  if (schemeId) params.scheme_id = schemeId
  const { data } = await api.get('/scheme-change-log', { params })
  return data
}

// ── Fase 4: Manual Payments ──

export interface ManualPaymentItem {
  id: number
  scout_id: number
  supervisor_id: number | null
  driver_id: string | null
  driver_license_raw: string | null
  payment_rule: string | null
  amount: number
  currency: string
  reason: string
  status: string
  approved_by: string | null
  approved_at: string | null
  paid_history_id: number | null
  created_by: string | null
  created_at: string | null
}

export async function createManualPayment(data: {
  scout_id: number
  supervisor_id?: number
  driver_id?: string
  driver_license_raw?: string
  payment_scheme_id?: number
  payment_rule?: string
  amount: number
  reason: string
  payment_component?: string
  created_by?: string
}): Promise<ManualPaymentItem> {
  const { data: result } = await api.post('/manual-payments', data)
  return result
}

export async function getManualPayments(params?: {
  scout_id?: number
  status?: string
}): Promise<ManualPaymentItem[]> {
  const { data } = await api.get('/manual-payments', { params })
  return data
}

export async function approveManualPayment(paymentId: number, approvedBy?: string, reference?: string): Promise<any> {
  const { data } = await api.post('/manual-payments/approve', {
    approved_by: approvedBy,
    payment_reference: reference,
  }, { params: { payment_id: paymentId } })
  return data
}

export async function markManualPaymentPaid(paymentId: number, paidBy?: string): Promise<any> {
  const params: any = { payment_id: paymentId }
  if (paidBy) params.paid_by = paidBy
  const { data } = await api.post('/manual-payments/mark-paid', null, { params })
  return data
}

// ── Fase 4: Supervisor Commission ──

export interface CommissionItem {
  id: number
  cutoff_run_id: number | null
  supervisor_id: number
  base_amount: number
  commission_rate: number
  commission_amount: number
  status: string
  paid_history_id: number | null
  created_at: string | null
}

export async function calculateCommissions(cutoffRunId: number, commissionRate?: number): Promise<any[]> {
  const params: any = { cutoff_run_id: cutoffRunId }
  if (commissionRate) params.commission_rate = commissionRate
  const { data } = await api.post('/commissions/calculate', null, { params })
  return data
}

export async function getCommissions(cutoffRunId?: number): Promise<CommissionItem[]> {
  const params: any = {}
  if (cutoffRunId) params.cutoff_run_id = cutoffRunId
  const { data } = await api.get('/commissions', { params })
  return data
}

export async function markCommissionPaid(commissionId: number): Promise<any> {
  const { data } = await api.post(`/commissions/${commissionId}/mark-paid`)
  return data
}

// ── Fase 4: Scout Bonuses ──

export interface BonusItem {
  id: number
  cutoff_run_id: number | null
  scout_id: number
  bonus_type: string
  amount: number
  currency: string
  reason: string
  status: string
  approved_by: string | null
  approved_at: string | null
  paid_history_id: number | null
  created_by: string | null
  created_at: string | null
}

export async function createBonus(data: {
  cutoff_run_id?: number
  scout_id: number
  bonus_type?: string
  amount: number
  reason: string
  created_by?: string
}): Promise<BonusItem> {
  const { data: result } = await api.post('/bonuses', data)
  return result
}

export async function approveBonus(bonusId: number, approvedBy?: string): Promise<any> {
  const { data } = await api.post(`/bonuses/${bonusId}/approve`, {
    approved_by: approvedBy,
  })
  return data
}

export async function markBonusPaid(bonusId: number): Promise<any> {
  const { data } = await api.post(`/bonuses/${bonusId}/mark-paid`)
  return data
}

export async function getBonuses(params?: {
  cutoff_run_id?: number
  scout_id?: number
}): Promise<BonusItem[]> {
  const { data } = await api.get('/bonuses', { params })
  return data
}

// ── Fase 4.6: Historical Attributions ──

export interface AttributionLineItem {
  id: number
  import_batch_id: number | null
  source_file: string | null
  source_sheet: string | null
  source_row: number | null
  scout_name_raw: string | null
  scout_id_resolved: number | null
  supervisor_name_raw: string | null
  driver_license_raw: string | null
  driver_id_resolved: string | null
  driver_name_raw: string | null
  origin_raw: string | null
  payment_status_raw: string | null
  payment_amount: number | null
  import_status: string
  import_reason: string | null
  linked_assignment_id: number | null
  created_at: string | null
}

export interface AttributionPreviewResult {
  batch_id?: number
  source_file: string
  sheet: string
  total_rows: number
  ready_to_import: number
  manual_review: number
  conflicts: number
  duplicates: number
  rejected: number
  lines: any[]
}

export interface AttributionCommitResult {
  batch_id?: number
  assignments_created: number
  assignments_updated: number
  historical_attributions_created: number
  manual_review: number
  conflicts: number
  duplicates: number
  rejected: number
}

export async function previewAttributions(file: File, sheet?: string): Promise<AttributionPreviewResult> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/attributions/preview${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function commitAttributions(file: File, sheet?: string): Promise<AttributionCommitResult> {
  const form = new FormData()
  form.append('file', file)
  const params = sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''
  const { data } = await apiLong.post(`/attributions/commit${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getAttributions(params?: {
  scout_id?: number
  driver_id?: string
  license?: string
  source_file?: string
  source_sheet?: string
  import_status?: string
  origin_raw?: string
  cutoff_external_id?: string
  limit?: number
  offset?: number
}): Promise<{ total: number; items: AttributionLineItem[] }> {
  const { data } = await api.get('/attributions', { params })
  return data
}

export async function getAttributionBatchLines(batchId: number, importStatus?: string): Promise<AttributionLineItem[]> {
  const params: any = {}
  if (importStatus) params.import_status = importStatus
  const { data } = await api.get(`/attributions/imports/${batchId}/lines`, { params })
  return data
}

export function getAttributionErrorsUrl(batchId: number): string {
  return `${api.defaults.baseURL}/attributions/imports/${batchId}/errors.csv`
}

export async function listAttributionBatches(): Promise<any[]> {
  const { data } = await api.get('/attributions/imports')
  return data
}

// ── Dashboard ──

export interface DashboardOverview {
  scope_label: string
  total_affiliations: number
  total_with_driver: number
  total_without_driver: number
  total_with_scout: number
  total_without_scout: number
  total_manual_review: number
  paid_history_count: number
  paid_history_amount: number
  blocking_count: number
  blocking_amount: number
  financial_only_count: number
  financial_only_amount: number
  blocks_true_without_driver_count: number
  duplicate_hash_count: number
  active_scouts: number
  scouts_with_payments: number
  scouts_with_manual_review: number
  pending_cutoff_warning: boolean
}

export interface ScoutRanking {
  scout_id: number
  scout_name: string
  supervisor_name: string | null
  affiliations_total: number
  with_driver: number
  without_driver: number
  manual_review: number
  paid_history_count: number
  paid_history_amount: number
  blocking_count: number
  financial_only_count: number
  avg_amount_per_paid_driver: number
  alert_level: string
}

export interface WeekEvolution {
  iso_year: number
  iso_week: number
  label: string
  total: number
  paid_count: number
  paid_amount: number
  blocking_count: number
  financial_only_count: number
  manual_review: number
  with_driver: number
  without_driver: number
}

export interface QualityFunnel {
  status: string
  message?: string
  cutoff_run_id?: number
  total_affiliations?: number
  drivers_1plus_0_7?: number
  drivers_5plus_0_7?: number
  drivers_1plus_8_14?: number
  drivers_5plus_0_14?: number
  conversion_5v_7d?: number
  avg_conversion_rate?: number
}

export interface DashboardAlerts {
  manual_review_count: number
  without_driver_count: number
  without_scout_count: number
  financial_only_count: number
  blocks_true_without_driver_count: number
  duplicate_hash_count: number
  supervisor_missing_count: number
  cutoff_pending: boolean
}

export async function getDashboardOverview(params?: Record<string, any>): Promise<DashboardOverview> {
  const { data } = await api.get('/dashboard/overview', { params })
  return data
}

export async function getDashboardByScout(params?: Record<string, any>): Promise<ScoutRanking[]> {
  const { data } = await api.get('/dashboard/by-scout', { params })
  return data
}

export async function getDashboardByWeek(params?: Record<string, any>): Promise<WeekEvolution[]> {
  const { data } = await api.get('/dashboard/by-week', { params })
  return data
}

export async function getDashboardQualityFunnel(params?: Record<string, any>): Promise<QualityFunnel> {
  const { data } = await api.get('/dashboard/quality-funnel', { params })
  return data
}

export async function getDashboardAlerts(params?: Record<string, any>): Promise<DashboardAlerts> {
  const { data } = await api.get('/dashboard/alerts', { params })
  return data
}

// ── Dashboard Trend (cutoff snapshots only) ──

export interface TrendItem {
  id: number
  cutoff_name: string
  status: string
  hire_date_from: string
  hire_date_to: string
  total_affiliations: number
  total_activated: number
  converted_5v7d: number
  converted_5v14d: number
  total_payout: number
  total_payable: number
  blocked_scouts: number
  paid_scouts: number
}

export async function getCutoffTrend(): Promise<TrendItem[]> {
  const { data } = await api.get('/dashboard/trend')
  return data
}

// ── Payment Scheme Admin ──

export interface PaymentSchemeListItem {
  scheme_id: number
  name: string
  scheme_type: string
  description: string | null
  is_active: boolean
  active_version_id: number | null
  active_version_name: string | null
  active_since_cohort: string | null
  version_count: number
  created_at: string | null
}

export interface SchemeVersionDetail {
  version_id: number
  version_name: string
  valid_from_cohort_iso_week: string
  valid_to_cohort_iso_week: string | null
  maturity_days: number
  maturity_window_days: number
  min_activated: number
  min_volume_count: number
  activation_rule: string
  volume_rule: string
  quality_rule: string
  counts_volume_rule: string
  counts_quality_rule: string
  formula_type: string
  pays_on_rule: string
  payout_formula_type: string
  currency: string
  status: string
  created_at: string | null
  activated_at: string | null
  archived_at: string | null
  tiers: { min_conversion_rate: number; payout_amount: number; sort_order: number }[]
}

export interface PaymentSchemeDetail {
  scheme_id: number
  name: string
  scheme_type: string
  description: string | null
  is_active: boolean
  created_at: string | null
  versions: SchemeVersionDetail[]
}

export interface CreateVersionPayload {
  version_name: string
  valid_from_cohort_iso_week: string
  maturity_days: number
  maturity_window_days?: number
  min_activated: number
  min_volume_count?: number
  activation_rule: string
  volume_rule?: string
  quality_rule: string
  counts_volume_rule?: string
  counts_quality_rule?: string
  formula_type: string
  pays_on_rule?: string
  payout_formula_type?: string
  currency: string
  tiers: { min_conversion_rate: number; payout_amount: number }[]
}

export interface HistoryItem {
  version_id: number
  scheme_name: string
  scheme_type: string
  version_name: string
  valid_from_cohort_iso_week: string
  valid_to_cohort_iso_week: string | null
  maturity_days: number
  min_activated: number
  status: string
  created_at: string | null
  activated_at: string | null
  archived_at: string | null
}

export async function listPaymentSchemes(): Promise<PaymentSchemeListItem[]> {
  const { data } = await api.get('/payment-schemes')
  return data
}

export async function getPaymentSchemeDetail(schemeId: number): Promise<PaymentSchemeDetail> {
  const { data } = await api.get(`/payment-schemes/${schemeId}`)
  return data
}

export async function createPaymentScheme(body: { name: string; scheme_type: string; description?: string }): Promise<any> {
  const { data } = await api.post('/payment-schemes', body)
  return data
}

export async function createPaymentSchemeVersion(
  schemeId: number,
  body: CreateVersionPayload
): Promise<any> {
  const { data } = await api.post(`/payment-schemes/${schemeId}/versions`, body)
  return data
}

export async function activatePaymentSchemeVersion(versionId: number): Promise<any> {
  const { data } = await api.post(`/payment-scheme-versions/${versionId}/activate`)
  return data
}

export async function archivePaymentSchemeVersion(versionId: number): Promise<any> {
  const { data } = await api.post(`/payment-scheme-versions/${versionId}/archive`)
  return data
}

export async function getPaymentSchemesHistory(): Promise<HistoryItem[]> {
  const { data } = await api.get('/payment-schemes/history')
  return data
}

export interface ResolvedScheme {
  scheme_id: number
  scheme_name: string
  scheme_type: string
  description: string | null
  scheme_version_id: number
  version_name: string
  valid_from_cohort_iso_week: string
  valid_to_cohort_iso_week: string | null
  maturity_days: number
  maturity_window_days: number
  min_activated: number
  min_volume_count: number
  activation_rule: string
  volume_rule: string
  quality_rule: string
  counts_volume_rule: string
  counts_quality_rule: string
  formula_type: string
  pays_on_rule: string
  payout_formula_type: string
  currency: string
  tiers: { min_conversion_rate: number; payout_amount: number; sort_order: number }[]
}

export async function resolvePaymentScheme(cohort_iso_week: string, scheme_type: string): Promise<ResolvedScheme> {
  const { data } = await api.get('/payment-schemes/resolve', { params: { cohort_iso_week, scheme_type } })
  return data
}

// ── Cutoff from Cohort ──

export async function createCutoffFromCohort(params: {
  cohort_iso_week: string
  scheme_type?: string
  scheme_id?: number
  origin_filter?: string
  force_override?: boolean
}): Promise<any> {
  const { data } = await api.post('/cutoffs/from-cohort', null, { params })
  return data
}

export function getCutoffExportFinancialUrl(cutoffId: number): string {
  return `${api.defaults.baseURL}/cutoffs/${cutoffId}/export-financial.csv`
}

// ── Manual Overrides ──

export interface ManualOverrideItem {
  id: number
  driver_id: string
  cohort_iso_week: string | null
  scout_id_before: number | null
  scout_id_after: number | null
  override_type: string
  amount: number | null
  currency: string
  reason: string
  notes: string | null
  created_by: string | null
  created_at: string | null
  approved_by: string | null
  approved_at: string | null
  status: string
  blocks_future_payment: boolean
  paid_history_id: number | null
}

export async function listManualOverrides(params?: {
  driver_id?: string; override_type?: string; status?: string
}): Promise<ManualOverrideItem[]> {
  const { data } = await api.get('/manual-overrides', { params })
  return data
}

export async function getDriverOverrides(driverId: string): Promise<ManualOverrideItem[]> {
  const { data } = await api.get(`/drivers/${encodeURIComponent(driverId)}/manual-overrides`)
  return data
}

export async function createManualOverride(body: {
  driver_id: string
  override_type: string
  reason: string
  cohort_iso_week?: string
  scout_id?: number
  scout_id_before?: number
  amount?: number
  notes?: string
  created_by?: string
}): Promise<ManualOverrideItem> {
  const { data } = await api.post('/manual-overrides', body)
  return data
}
