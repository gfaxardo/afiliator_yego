import { useState } from 'react'
import { previewScoutUpload, commitScoutUpload } from '../../api/scoutLiq'

interface SheetInfo { name: string; import_type: string; import_type_label: string; row_count: number }

const ALLOWED_TYPES = ['scouts_bulk']

export default function BulkScoutView() {
  const [file, setFile] = useState<File | null>(null)
  const [sheet, setSheet] = useState('')
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<any>(null)
  const [commitResult, setCommitResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [sheetInfo, setSheetInfo] = useState<SheetInfo[]>([])

  async function detectSheets(file: File) {
    try {
      const form = new FormData(); form.append('file', file)
      const resp = await fetch('/api/scout-liq/templates/xlsx-sheets', { method: 'POST', body: form })
      const data = await resp.json()
      const info: SheetInfo[] = data.sheet_info || []
      setSheetInfo(info)
      const valid = info.filter((s: SheetInfo) => ALLOWED_TYPES.includes(s.import_type))
      if (valid.length > 0) {
        setSheet(valid[0].name)
        setWarning(null)
      } else {
        setSheet(info[0]?.name || '')
        setWarning('Ninguna hoja de scouts encontrada.')
      }
    } catch (_) { setError('Error al detectar hojas') }
  }

  function handleSheetChange(s: string) {
    setSheet(s); setPreview(null); setCommitResult(null)
    const info = sheetInfo.find((si: SheetInfo) => si.name === s)
    if (info && !ALLOWED_TYPES.includes(info.import_type)) {
      setWarning(`Hoja "${s}" es de tipo "${info.import_type_label}". Usa la pestana correcta.`)
    } else { setWarning(null) }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null; setFile(f)
    setPreview(null); setCommitResult(null); setError(null); setSuccess(null); setWarning(null)
    setSheetInfo([]); setSheet('')
    if (f) await detectSheets(f)
  }

  async function handlePreview() {
    if (!file) return; if (warning) { setError(warning); return }
    setLoading(true); setError(null); setSuccess(null); setPreview(null)
    try {
      const r = await previewScoutUpload(file, sheet || undefined)
      setPreview(r)
    } catch (e: any) {
      const d = e.response?.data?.detail
      setError(typeof d === 'object' ? (d.message || 'Error de hoja') : (d || e.message || 'Error'))
    } finally { setLoading(false) }
  }

  async function handleCommit() {
    if (!file) return
    setLoading(true); setError(null); setSuccess(null)
    try {
      const r = await commitScoutUpload(file, sheet || undefined)
      setCommitResult(r); setSuccess(`Carga completada: ${r.created} creados, ${r.updated} actualizados`)
    } catch (e: any) {
      const d = e.response?.data?.detail
      setError(typeof d === 'object' ? (d.message || 'Error') : (d || e.message || 'Error'))
    } finally { setLoading(false) }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Carga Masiva de Scouts</h2>
      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Archivo Excel</label>
            <input type="file" accept=".xlsx" onChange={handleFileChange} className="border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          {sheetInfo.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Hoja</label>
              <select value={sheet} onChange={(e) => handleSheetChange(e.target.value)} className="border border-gray-300 rounded px-3 py-2 text-sm max-w-sm">
                {sheetInfo.map((s) => {
                  const ok = ALLOWED_TYPES.includes(s.import_type)
                  return <option key={s.name} value={s.name}>{ok ? '✓ ' : '⚠ '}{s.name} [{s.import_type_label}] ({s.row_count})</option>
                })}
              </select>
            </div>
          )}
          <button onClick={handlePreview} disabled={!file || loading} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">Preview</button>
          <button onClick={handleCommit} disabled={!file || loading} className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50">Commit</button>
        </div>
        {warning && <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-3 rounded text-sm">{warning}</div>}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
        {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}
        {preview && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h4 className="font-medium text-blue-800 mb-2">Preview - {preview.sheet}</h4>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div>Total: <b>{preview.total_rows}</b></div>
              <div className="text-green-600">Crearan: <b>{preview.will_create}</b></div>
              <div className="text-blue-600">Actualizaran: <b>{preview.will_update}</b></div>
              <div className="text-yellow-600">Revision: <b>{preview.manual_review}</b></div>
              <div className="text-gray-600">Skip: <b>{preview.duplicate_skipped}</b></div>
            </div>
          </div>
        )}
        {commitResult && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <h4 className="font-medium text-green-800 mb-2">Resultado</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="text-green-600">Creados: <b>{commitResult.created}</b></div>
              <div className="text-blue-600">Actualizados: <b>{commitResult.updated}</b></div>
              <div className="text-red-600">Rechazados: <b>{commitResult.rejected}</b></div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
