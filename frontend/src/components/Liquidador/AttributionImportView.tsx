import { useState, useEffect } from 'react'
import {
  previewAttributions,
  commitAttributions,
  listAttributionBatches,
  getAttributionBatchLines,
  getAttributionErrorsUrl,
} from '../../api/scoutLiq'

interface SheetInfo {
  name: string
  import_type: string
  import_type_label: string
  row_count: number
}

const ALLOWED_TYPES = ['historical_attributions']
const ALLOWED_SHEETS = ['06_ATRIBUCIONES_HISTORICAS', 'Registros-conductores', 'LIQUIDACION_DETALLE', 'LIQUIDACION_AUDITORIA']

export default function AttributionImportView() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<any>(null)
  const [commitResult, setCommitResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [batches, setBatches] = useState<any[]>([])
  const [batchLines, setBatchLines] = useState<any[]>([])
  const [selectedBatch, setSelectedBatch] = useState<number | null>(null)
  const [lineFilter, setLineFilter] = useState('')
  const [selectedSheet, setSelectedSheet] = useState('')
  const [sheetInfo, setSheetInfo] = useState<SheetInfo[]>([])

  useEffect(() => { loadBatches() }, [])

  async function loadBatches() {
    try { setBatches(await listAttributionBatches()) } catch (_) {}
  }

  async function detectSheets(file: File) {
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/api/scout-liq/templates/xlsx-sheets', { method: 'POST', body: form })
      const data = await resp.json()
      const info: SheetInfo[] = data.sheet_info || []
      setSheetInfo(info)

      const validSheets = info.filter((s: SheetInfo) => ALLOWED_TYPES.includes(s.import_type))
      if (validSheets.length > 0) {
        const pref = validSheets.find((s: SheetInfo) => s.name === '06_ATRIBUCIONES_HISTORICAS')
        setSelectedSheet(pref?.name || validSheets[0].name)
        setWarning(null)
      } else {
        setSelectedSheet(info[0]?.name || '')
        setWarning('Ninguna hoja de atribuciones encontrada. Selecciona manualmente o usa otra pestana.')
      }
    } catch (_) { setError('Error al detectar hojas') }
  }

  function handleSheetChange(sheetName: string) {
    setSelectedSheet(sheetName)
    setPreview(null)
    setCommitResult(null)
    const info = sheetInfo.find((s: SheetInfo) => s.name === sheetName)
    if (info && !ALLOWED_TYPES.includes(info.import_type)) {
      setWarning(
        `Hoja "${sheetName}" es de tipo "${info.import_type_label}". ` +
        `No se puede procesar como atribucion. Selecciona otra hoja o usa la pestana correcta.`)
    } else {
      setWarning(null)
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null
    setFile(f)
    setPreview(null); setCommitResult(null); setError(null); setSuccess(null); setWarning(null)
    setSheetInfo([]); setSelectedSheet('')
    if (f) await detectSheets(f)
  }

  async function handlePreview() {
    if (!file) return
    if (warning) { setError(warning); return }
    setLoading(true); setError(null); setSuccess(null); setPreview(null); setCommitResult(null)
    try {
      const r = await previewAttributions(file, selectedSheet || undefined)
      setPreview(r)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (typeof detail === 'object' && detail?.error === 'wrong_sheet_for_import') {
        setError(detail.message || 'Error de hoja')
      } else {
        setError(typeof detail === 'string' ? detail : (e.message || 'Error en preview'))
      }
    } finally { setLoading(false) }
  }

  async function handleCommit() {
    if (!file) return
    setLoading(true); setError(null); setSuccess(null)
    try {
      const r = await commitAttributions(file, selectedSheet || undefined)
      setCommitResult(r)
      setSuccess(`Commit OK: ${r.assignments_created} creados, ${r.assignments_updated} actualizados, ${r.historical_attributions_created} atribuciones`)
      await loadBatches()
    } catch (e: any) {
      const detail = e.response?.data?.detail
      setError(typeof detail === 'string' ? detail : (e.message || 'Error en commit'))
    } finally { setLoading(false) }
  }

  async function loadBatchLines(batchId: number, status?: string) {
    setSelectedBatch(batchId); setLineFilter(status || '')
    try { setBatchLines(await getAttributionBatchLines(batchId, status || undefined)) }
    catch (_) { setError('Error al cargar lineas') }
  }

  const selectedInfo = sheetInfo.find(s => s.name === selectedSheet)

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Atribuciones Historicas</h2>
        <a href="/api/scout-liq/templates/historical-import"
          className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 inline-flex items-center gap-2" download>
          Descargar plantilla
        </a>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Archivo Excel</label>
            <input type="file" accept=".xlsx,.csv" onChange={handleFileChange}
              className="border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          {sheetInfo.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Hoja
                {selectedInfo && (
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded ${
                    ALLOWED_TYPES.includes(selectedInfo.import_type)
                      ? 'bg-green-100 text-green-700'
                      : 'bg-red-100 text-red-600'
                  }`}>{selectedInfo.import_type_label} ({selectedInfo.row_count} filas)</span>
                )}
              </label>
              <select value={selectedSheet} onChange={(e) => handleSheetChange(e.target.value)}
                className="border border-gray-300 rounded px-3 py-2 text-sm max-w-sm">
                {sheetInfo.map((s) => {
                  const ok = ALLOWED_TYPES.includes(s.import_type)
                  return (
                    <option key={s.name} value={s.name}>
                      {ok ? '✓ ' : '⚠ '}{s.name} [{s.import_type_label}] {s.row_count > 0 ? `(${s.row_count})` : '(vacia)'}
                    </option>
                  )
                })}
              </select>
            </div>
          )}
          <button onClick={handlePreview} disabled={!file || loading}
            className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50 font-medium">
            {loading ? 'Procesando...' : 'Preview'}
          </button>
        </div>
        {warning && <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-3 rounded text-sm">{warning}</div>}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
        {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}
      </div>

      {preview && (
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h3 className="font-medium text-gray-800 mb-3">Preview ({preview.source_file} / {preview.sheet})</h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <StatBox label="Total" value={preview.total_rows} color="gray" />
              <StatBox label="Importaran" value={preview.ready_to_import} color="green" />
              <StatBox label="Revision" value={preview.manual_review} color="yellow" />
              <StatBox label="Conflictos" value={preview.conflicts} color="red" />
              <StatBox label="Rechazados" value={preview.rejected} color="red" />
            </div>
            {preview.ready_to_import > 0 && (
              <button onClick={handleCommit} disabled={loading}
                className="bg-green-600 text-white px-6 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50 font-medium">
                Confirmar importacion
              </button>
            )}
          </div>
        </div>
      )}

      {commitResult && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-medium text-blue-800 mb-2">Resultado Commit</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div className="text-green-600">Creados: <b>{commitResult.assignments_created}</b></div>
            <div className="text-blue-600">Actualizados: <b>{commitResult.assignments_updated}</b></div>
            <div className="text-purple-600">Atribuciones: <b>{commitResult.historical_attributions_created}</b></div>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-medium">Batches</h3>
          <button onClick={loadBatches} className="text-xs text-blue-600 hover:underline">Refrescar</button>
        </div>
        {batches.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">Sin batches.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="bg-gray-50 text-left"><th className="px-3 py-2">Batch</th><th className="px-3 py-2">Archivo</th><th className="px-3 py-2">Filas</th><th className="px-3 py-2">Importados</th><th className="px-3 py-2">Acciones</th></tr></thead>
              <tbody>
                {batches.map(b => (
                  <tr key={b.batch_id} className="border-t border-gray-100">
                    <td className="px-3 py-2">{b.batch_id}</td>
                    <td className="px-3 py-2 max-w-[180px] truncate text-xs">{b.source_file || '-'}</td>
                    <td className="px-3 py-2">{b.total_rows}</td>
                    <td className="px-3 py-2">{b.imported}</td>
                    <td className="px-3 py-2 space-x-2">
                      <button onClick={() => loadBatchLines(b.batch_id)} className="text-blue-600 hover:underline text-xs">Ver</button>
                      <a href={getAttributionErrorsUrl(b.batch_id)} className="text-red-600 hover:underline text-xs" download>CSV</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: any; color: string }) {
  const c: Record<string, string> = { green: 'bg-green-50 border-green-200', red: 'bg-red-50 border-red-200', yellow: 'bg-yellow-50 border-yellow-200', gray: 'bg-gray-50 border-gray-200' }
  const t: Record<string, string> = { green: 'text-green-700', red: 'text-red-700', yellow: 'text-yellow-700', gray: 'text-gray-700' }
  return <div className={`border rounded-lg p-3 text-center ${c[color]||c.gray}`}><div className="text-xs text-gray-500">{label}</div><div className={`text-lg font-bold ${t[color]||t.gray}`}>{value}</div></div>
}
