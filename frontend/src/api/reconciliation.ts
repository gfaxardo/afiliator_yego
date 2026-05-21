import axios from 'axios'

const api = axios.create({
  baseURL: '/api/scout-liq',
  timeout: 60000,
})

export interface ReconciliationCompareResponse {
  total_rows: number
  matched_rows: number
  unmatched_rows: number
  amount_mismatch: number
  already_paid: number
  missing_in_system: number
  missing_in_upload: number
  details: ReconciliationDetail[]
  suggested_actions: string[]
}

export interface ReconciliationDetail {
  driver_id?: string
  driver_name?: string
  status: string
  reason: string
  system_amount?: number | null
  upload_amount?: number | null
  system_scout?: string
  upload_scout?: string
  system_paid_history_id?: number | null
  system_manual_override_id?: number | null
  suggested_action?: string | null
}

export async function exportReconciliationCsv(params: {
  hire_date_from?: string
  hire_date_to?: string
  scheme_type?: string
  pay_until_date?: string
  only_matured?: boolean
}): Promise<Blob> {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) {
      searchParams.set(k, String(v))
    }
  })
  const url = `/reconciliation/export?${searchParams.toString()}`
  const r = await api.get(url, { responseType: 'blob' })
  return r.data
}

export async function compareUpload(
  file: File,
  params: {
    hire_date_from?: string
    hire_date_to?: string
    scheme_type?: string
  },
): Promise<ReconciliationCompareResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') {
      searchParams.set(k, String(v))
    }
  })

  const url = `/reconciliation/compare-upload?${searchParams.toString()}`
  const r = await api.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}
