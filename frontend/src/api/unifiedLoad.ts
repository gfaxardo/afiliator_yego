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
  | 'scout_not_found'
  | 'duplicate_existing'
  | 'conflict_existing_active_scout'
  | 'error'
  | 'validation_error'

export type UnifiedApplyLineStatus = 'ok' | 'warning' | 'manual_review' | 'error'

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
  what_happened?: string[] | null
}

export interface UnifiedApplyResponse {
  applied: number
  skipped: number
  errors: number
  no_change?: number
  conflicts?: number
  already_paid?: number
  not_found?: number
  details: UnifiedApplyDetail[]
}

export async function downloadTemplate(): Promise<Blob> {
  const r = await api.get('/unified-load/template', { responseType: 'blob' })
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
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/scout-liq/unified-load/preview-stream', {
    method: 'POST',
    body: formData,
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
          onSummary(parsed)
        } else if (parsed.type === 'structural_error') {
          onError('Error estructural: ' + JSON.stringify(parsed))
        } else {
          onLine(parsed)
        }
      } catch {
        // skip malformed lines
      }
    }
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
