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

export async function applyUnifiedLoadStream(
  plan: any[],
  onLine: (line: any) => void,
  onSummary: (summary: any) => void,
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
        if (parsed.type === 'summary') onSummary(parsed)
        else onLine(parsed)
      } catch { /* skip */ }
    }
  }
}
