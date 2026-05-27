import { useState, useEffect, useRef } from 'react'
import {
  previewHistoricalImport,
  commitHistoricalImport,
  listHistoricalImports,
  getHistoricalImportLines,
  getHistoricalErrorsUrl,
  HistoricalImportBatch,
} from '../../api/scoutLiq'

interface SheetInfo {
  name: string
  import_type: string
  import_type_label: string
  row_count: number
}

const ALLOWED_TYPES = ['historical_payments']
const ALLOWED_SHEETS = ['01_PAGOS_HISTORICOS', 'LIQUIDACION_DETALLE', 'Registros-conductores', 'dg-corte pagos manuales']

export default function HistoricalImportView() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<any>(null)
  const [commitResult, setCommitResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [batches, setBatches] = useState<HistoricalImportBatch[]>([])
  const [selectedBatchLines, setSelectedBatchLines] = useState<any[]>([])
  const [selectedBatch, setSelectedBatch] = useState<number | null>(null)
  const [lineFilter, setLineFilter] = useState('')
  const [selectedSheet, setSelectedSheet] = useState('')
  const [sheetInfo, setSheetInfo] = useState<SheetInfo[]>([])
  const [showLines, setShowLines] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  function addLog(msg: string) {
    setProgressLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])
  }

  useEffect(() => { loadBatches() }, [])

  async function loadBatches() {
    try { setBatches(await listHistoricalImports()) } catch (e: any) { setError(e?.message || 'Error al cargar batches') }
  }

  async function detectSheets(file: File) {
    addLog(`Detectando hojas en ${file.name}...`)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/api/scout-liq/templates/xlsx-sheets', {
        method: 'POST', body: form,
      })
      const data = await resp.json()
      const info: SheetInfo[] = data.sheet_info || []
      setSheetInfo(info)
      addLog(`Hojas detectadas: ${info.length} (${info.map(s => `${s.name}[${s.import_type_label}]`).join(', ')})`)

      // Filter to only sheets valid for this tab
      const validSheets = info.filter(
        (s: SheetInfo) => ALLOWED_TYPES.includes(s.import_type)
      )
      if (validSheets.length > 0) {
        // Prefer 01_PAGOS_HISTORICOS
        const pref = validSheets.find((s: SheetInfo) => s.name === '01_PAGOS_HISTORICOS')
        setSelectedSheet(pref?.name || validSheets[0].name)
        setWarning(null)
      } else {
        setSelectedSheet(info[0]?.name || '')
        setWarning('Ninguna hoja de pagos historicos encontrada. Selecciona manualmente o usa otra pestana.')
      }
    } catch (_) {
      setError('Error al detectar hojas')
    }
  }

  function handleSheetChange(sheetName: string) {
    setSelectedSheet(sheetName)
    setPreview(null)
    setCommitResult(null)
    const info = sheetInfo.find((s: SheetInfo) => s.name === sheetName)
    if (info && !ALLOWED_TYPES.includes(info.import_type)) {
      setWarning(
        `Hoja "${sheetName}" es de tipo "${info.import_type_label}". ` +
        `No se puede procesar como pago historico. ` +
        (info.import_type === 'scouts_bulk'
          ? 'Usa la pestana "Carga Masiva".'
          : info.import_type === 'historical_attributions'
            ? 'Usa la pestana "Atribuciones".'
            : info.import_type === 'schemes'
              ? 'Usa la pestana "Esquemas".'
              : 'Selecciona otra hoja.'))
    } else {
      setWarning(null)
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null
    setFile(f)
    setPreview(null)
    setCommitResult(null)
    setError(null)
    setSuccess(null)
    setWarning(null)
    setSheetInfo([])
    setSelectedSheet('')
    if (f) await detectSheets(f)
  }

  async function handlePreview() {
    if (!file) return
    if (warning) { setError(warning); return }
    setLoading(true)
    setError(null)
    setSuccess(null)
    setPreview(null)
    setCommitResult(null)
    addLog(`Iniciando preview: hoja=${selectedSheet} archivo=${file.name}`)
    const t0 = performance.now()
    try {
      const r = await previewHistoricalImport(file, selectedSheet || undefined)
      const elapsed = ((performance.now() - t0) / 1000).toFixed(1)
      setPreview(r)
      addLog(`Preview completado en ${elapsed}s: ${r.total_rows} filas | ready=${r.ready_to_import} review=${r.manual_review} rejected=${r.rejected} dup=${r.duplicate} | monto=S/ ${Number(r.amount_ready || 0).toFixed(2)}`)
      if (r.errors_by_type) {
        for (const [reason, count] of Object.entries(r.errors_by_type).slice(0, 3)) {
          addLog(`  ${reason}: ${count}`)
        }
      }
      if (r.ready_to_import > 0) setSuccess(`Preview OK: ${r.ready_to_import} listos para importar`)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (typeof detail === 'object' && detail?.error === 'wrong_sheet_for_import') {
        const msg = `Error de hoja: ${detail.message}`
        setError(msg)
        addLog(`ERROR: ${msg}`)
      } else {
        const msg = detail || e.message || 'Error en preview'
        setError(msg)
        addLog(`ERROR: ${msg}`)
      }
    } finally { setLoading(false) }
  }

  async function handleCommit() {
    if (!preview?.batch_id) return
    setLoading(true)
    setError(null)
    setSuccess(null)
    addLog(`Iniciando commit batch #${preview.batch_id}...`)
    const t0 = performance.now()
    try {
      const r = await commitHistoricalImport(preview.batch_id)
      const elapsed = ((performance.now() - t0) / 1000).toFixed(1)
      setCommitResult(r)
      addLog(`Commit completado en ${elapsed}s: imported=${r.imported} rejected=${r.rejected} review=${r.manual_review} dup=${r.duplicate} monto=S/ ${r.amount_imported}`)
      setSuccess(`Importacion completada: ${r.imported} importados, S/ ${Number(r.amount_imported).toFixed(2)}`)
      await loadBatches()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Error en commit'
      setError(msg)
      addLog(`ERROR commit: ${msg}`)
    } finally { setLoading(false) }
  }

  async function loadBatchLines(batchId: number, status?: string) {
    setSelectedBatch(batchId)
    setLineFilter(status || '')
    try {
      setSelectedBatchLines(await getHistoricalImportLines(batchId, status || undefined))
      setShowLines(true)
    } catch (_) { setError('Error al cargar lineas') }
  }

  function getStatusColor(status: string) {
    switch (status) {
      case 'imported': case 'ready_to_import': return 'bg-green-100 text-green-700'
      case 'rejected': return 'bg-red-100 text-red-700'
      case 'manual_review': return 'bg-yellow-100 text-yellow-700'
      case 'duplicate': return 'bg-orange-100 text-orange-700'
      default: return 'bg-gray-100 text-gray-700'
    }
  }

  const selectedInfo = sheetInfo.find(s => s.name === selectedSheet)

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Carga Historica de Pagos</h2>
        <a
          href="/api/scout-liq/templates/historical-import"
          className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 inline-flex items-center gap-2"
          download
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Descargar plantilla
        </a>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Archivo Excel</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.csv"
              onChange={handleFileChange}
              className="border border-gray-300 rounded px-3 py-2 text-sm"
            />
          </div>

          {sheetInfo.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Hoja
                {selectedInfo && (
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded ${
                    ALLOWED_TYPES.includes(selectedInfo.import_type)
                      ? 'bg-green-100 text-green-700'
                      : selectedInfo.import_type === 'reference_only'
                        ? 'bg-gray-100 text-gray-500'
                        : 'bg-red-100 text-red-600'
                  }`}>
                    {selectedInfo.import_type_label}
                    {selectedInfo.row_count > 0 && ` (${selectedInfo.row_count} filas)`}
                  </span>
                )}
              </label>
              <select
                value={selectedSheet}
                onChange={(e) => handleSheetChange(e.target.value)}
                className="border border-gray-300 rounded px-3 py-2 text-sm max-w-sm"
              >
                {sheetInfo.map((s) => {
                  const isOK = ALLOWED_TYPES.includes(s.import_type)
                  const isRef = s.import_type === 'reference_only'
                  return (
                    <option key={s.name} value={s.name}>
                      {isOK ? '✓ ' : isRef ? '📄 ' : '⚠ '}
                      {s.name} [{s.import_type_label}] {s.row_count > 0 ? `(${s.row_count})` : '(vacia)'}
                    </option>
                  )
                })}
              </select>
            </div>
          )}

          <button
            onClick={handlePreview}
            disabled={!file || loading}
            className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
          >
            {loading ? 'Procesando...' : 'Preview'}
          </button>
        </div>

        {warning && (
          <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-3 rounded text-sm">
            {warning}
          </div>
        )}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">
            {success}
          </div>
        )}
      </div>

      {progressLog.length > 0 && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 font-mono text-xs max-h-48 overflow-y-auto">
          <div className="text-gray-400 mb-1 flex justify-between">
            <span>Log de operacion</span>
            <button onClick={() => setProgressLog([])} className="text-gray-500 hover:text-gray-300">limpiar</button>
          </div>
          {progressLog.map((msg, i) => (
            <div key={i} className={`py-0.5 ${
              msg.includes('ERROR') ? 'text-red-400' :
              msg.includes('completado') || msg.includes('OK') ? 'text-green-400' :
              'text-gray-300'
            }`}>
              {msg}
            </div>
          ))}
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h3 className="font-medium text-gray-800 mb-3">
              Resultado Preview ({preview.source_file || 'N/D'} / {preview.sheet || 'auto'})
              {preview.batch_id && <span className="text-gray-400 ml-2 text-xs">Batch #{preview.batch_id}</span>}
            </h3>

            {/* Triple-layer stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <h4 className="text-xs font-bold text-blue-800 uppercase mb-2">Atribuciones</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>Listas: <b className="text-green-600">{preview.attribution?.ready || 0}</b></div>
                  <div>Revision: <b className="text-yellow-600">{preview.attribution?.manual_review || 0}</b></div>
                </div>
              </div>
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <h4 className="text-xs font-bold text-green-800 uppercase mb-2">Pago Financiero</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>Listo: <b className="text-green-600">{preview.payment_financial?.ready || 0}</b></div>
                  <div>No aplica: <b className="text-gray-600">{preview.payment_financial?.not_applicable || 0}</b></div>
                  <div>Review: <b className="text-yellow-600">{preview.payment_financial?.manual_review || 0}</b></div>
                  <div>Monto: <b>S/ {Number(preview.payment_financial?.amount_ready || 0).toFixed(2)}</b></div>
                </div>
              </div>
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                <h4 className="text-xs font-bold text-purple-800 uppercase mb-2">Bloqueo Futuro</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>Bloqueables: <b className="text-green-600">{preview.payment_blocking?.ready || 0}</b></div>
                  <div>No bloquea (sin driver): <b className="text-gray-600">{preview.payment_blocking?.manual_review || 0}</b></div>
                  <div>Monto bloqueable: <b>S/ {Number(preview.payment_blocking?.amount_ready || 0).toFixed(2)}</b></div>
                </div>
              </div>
            </div>

            {/* Global summary */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <StatBox label="Total filas" value={preview.total_rows} color="gray" />
              <StatBox label="C/ atribucion" value={(preview.attribution?.ready || 0) + (preview.attribution?.manual_review || 0)} color="blue" />
              <StatBox label="C/ pago listo" value={preview.payment?.ready || 0} color="green" />
              <StatBox label="Sin pago" value={preview.payment?.not_applicable || 0} color="gray" />
              <StatBox label="Monto S/" value={`S/ ${Number(preview.payment?.amount_ready || 0).toFixed(2)}`} color="green" />
            </div>

            {preview.errors_by_type && Object.keys(preview.errors_by_type).length > 0 && (
              <div className="mb-4">
                <p className="text-xs font-medium text-gray-500 mb-1">Detalle:</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(preview.errors_by_type).slice(0, 5).map(([reason, count]) => (
                    <span key={reason} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                      {reason}: {count as number}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(preview.attribution?.ready > 0 || preview.payment?.ready > 0) && (
              <button
                onClick={handleCommit}
                disabled={loading}
                className="bg-green-600 text-white px-6 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50 font-medium"
              >
                {loading ? 'Importando...' : 'Confirmar importacion'}
              </button>
            )}
          </div>

          {preview.lines && preview.lines.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h4 className="font-medium text-gray-800 mb-2">Filas ({preview.lines.length})</h4>
              <div className="overflow-x-auto max-h-96">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 text-left sticky top-0">
                      <th className="px-2 py-1">Row</th>
                      <th className="px-2 py-1">Scout</th>
                      <th className="px-2 py-1">Licencia</th>
                      <th className="px-2 py-1">Driver</th>
                      <th className="px-2 py-1">Monto</th>
                      <th className="px-2 py-1">Atribucion</th>
                      <th className="px-2 py-1">Financiero</th>
                      <th className="px-2 py-1">Bloqueo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.lines.map((l: any, i: number) => (
                      <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-2 py-1">{l.source_row}</td>
                        <td className="px-2 py-1 max-w-[100px] truncate">{l.scout_name_raw || '-'}</td>
                        <td className="px-2 py-1">{l.driver_license_raw || '-'}</td>
                        <td className="px-2 py-1 max-w-[80px] truncate">{l.driver_id_resolved || '-'}</td>
                        <td className="px-2 py-1">{l.amount_paid ? `S/ ${Number(l.amount_paid).toFixed(2)}` : 'S/ 0'}</td>
                        <td className="px-2 py-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${getDualColor(l.attribution_status)}`}>
                            {l.attribution_status || '-'}
                          </span>
                        </td>
                        <td className="px-2 py-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${getFinColor(l.payment_financial_status)}`}>
                            {l.payment_financial_status || '-'}
                          </span>
                        </td>
                        <td className="px-2 py-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${getBlkColor(l.payment_blocking_status)}`}>
                            {l.payment_blocking_status || '-'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {commitResult && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-medium text-blue-800 mb-2">Resultado Commit (Batch #{commitResult.batch_id})</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
            <div className="text-green-600 font-medium">Importados: {commitResult.imported}</div>
            <div className="text-red-600 font-medium">Rechazados: {commitResult.rejected}</div>
            <div className="text-yellow-600 font-medium">Manual Review: {commitResult.manual_review}</div>
            <div className="text-orange-600 font-medium">Duplicados: {commitResult.duplicate}</div>
            <div className="text-blue-600 font-medium">Monto: S/ {Number(commitResult.amount_imported).toFixed(2)}</div>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-medium text-gray-800">Batches de Importacion</h3>
          <button onClick={loadBatches} className="text-xs text-blue-600 hover:underline">Refrescar</button>
        </div>
        {batches.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">Sin batches. Ejecuta un preview para empezar.</p>
        )}
        {batches.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Archivo</th>
                  <th className="px-3 py-2">Estado</th>
                  <th className="px-3 py-2">Filas</th>
                  <th className="px-3 py-2">Imp/Rech/Rev/Dup</th>
                  <th className="px-3 py-2">Monto</th>
                  <th className="px-3 py-2">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-3 py-2">{b.id}</td>
                    <td className="px-3 py-2 max-w-[180px] truncate text-xs">{b.source_file || '-'}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        b.status === 'completed' ? 'bg-green-100 text-green-700' :
                        b.status === 'previewing' ? 'bg-blue-100 text-blue-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>{b.status}</span>
                    </td>
                    <td className="px-3 py-2">{b.total_rows}</td>
                    <td className="px-3 py-2 text-xs">
                      {b.imported_count}/{b.rejected_count}/{b.manual_review_count}/{b.duplicate_count}
                    </td>
                    <td className="px-3 py-2">S/ {Number(b.amount_imported || 0).toFixed(2)}</td>
                    <td className="px-3 py-2 space-x-2">
                      <button onClick={() => loadBatchLines(b.id)} className="text-blue-600 hover:underline text-xs font-medium">Ver</button>
                      {(b.rejected_count > 0 || b.manual_review_count > 0 || b.duplicate_count > 0) && (
                        <a href={getHistoricalErrorsUrl(b.id)} className="text-red-600 hover:underline text-xs" download>
                          Errores CSV
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showLines && selectedBatchLines.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-medium">Lineas Batch #{selectedBatch}</h3>
            <select value={lineFilter} onChange={(e) => {
              setLineFilter(e.target.value)
              if (selectedBatch) loadBatchLines(selectedBatch, e.target.value || undefined)
            }} className="border border-gray-300 rounded px-2 py-1 text-xs">
              <option value="">Todas</option>
              <option value="imported">Importadas</option>
              <option value="rejected">Rechazadas</option>
              <option value="manual_review">Manual Review</option>
              <option value="duplicate">Duplicadas</option>
            </select>
          </div>
          <div className="overflow-x-auto max-h-80">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-left sticky top-0">
                  <th className="px-2 py-1">Row</th>
                  <th className="px-2 py-1">Scout</th>
                  <th className="px-2 py-1">Licencia</th>
                  <th className="px-2 py-1">Driver ID</th>
                  <th className="px-2 py-1">Monto</th>
                  <th className="px-2 py-1">PH ID</th>
                  <th className="px-2 py-1">Estado</th>
                  <th className="px-2 py-1">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {selectedBatchLines.map((l: any) => (
                  <tr key={l.id} className="border-t border-gray-100">
                    <td className="px-2 py-1">{l.source_row}</td>
                    <td className="px-2 py-1 max-w-[100px] truncate">{l.scout_name_raw || '-'}</td>
                    <td className="px-2 py-1">{l.driver_license_raw || '-'}</td>
                    <td className="px-2 py-1 max-w-[80px] truncate">{l.driver_id_resolved || '-'}</td>
                    <td className="px-2 py-1">{l.amount_paid ? `S/ ${Number(l.amount_paid).toFixed(2)}` : '-'}</td>
                    <td className="px-2 py-1">{l.paid_history_id || '-'}</td>
                    <td className="px-2 py-1">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${getStatusColor(l.import_status)}`}>
                        {l.import_status}
                      </span>
                    </td>
                    <td className="px-2 py-1 max-w-[200px] truncate text-gray-500">{l.import_reason || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: any; color: string }) {
  const colorMap: Record<string, string> = {
    green: 'bg-green-50 border-green-200', red: 'bg-red-50 border-red-200',
    yellow: 'bg-yellow-50 border-yellow-200', orange: 'bg-orange-50 border-orange-200',
    gray: 'bg-gray-50 border-gray-200', blue: 'bg-blue-50 border-blue-200',
  }
  const textMap: Record<string, string> = {
    green: 'text-green-700', red: 'text-red-700',
    yellow: 'text-yellow-700', orange: 'text-orange-700', gray: 'text-gray-700', blue: 'text-blue-700',
  }
  return (
    <div className={`border rounded-lg p-3 text-center ${colorMap[color] || colorMap.gray}`}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-bold ${textMap[color] || textMap.gray}`}>{value}</div>
    </div>
  )
}

function getDualColor(s: string) {
  if (!s) return 'bg-gray-100 text-gray-500'
  if (s.includes('ready')) return 'bg-green-100 text-green-700'
  if (s.includes('manual_review')) return 'bg-yellow-100 text-yellow-700'
  if (s.includes('conflict')) return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-700'
}
function getPayColor(s: string) {
  if (!s) return 'bg-gray-100 text-gray-500'
  if (s === 'payment_ready') return 'bg-green-100 text-green-700'
  if (s.includes('not_applicable')) return 'bg-gray-100 text-gray-500'
  if (s.includes('manual_review')) return 'bg-yellow-100 text-yellow-700'
  if (s.includes('duplicate')) return 'bg-orange-100 text-orange-700'
  return 'bg-gray-100 text-gray-700'
}
function getFinalColor(s: string) {
  if (!s) return 'bg-gray-100 text-gray-500'
  if (s.includes('ready')) return 'bg-green-100 text-green-700 font-bold'
  if (s === 'rejected') return 'bg-red-100 text-red-700'
  if (s === 'manual_review') return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-700'
}
function getFinColor(s: string) {
  if (!s) return 'bg-gray-100 text-gray-500'
  if (s === 'payment_financial_ready') return 'bg-green-100 text-green-700'
  if (s.includes('not_applicable')) return 'bg-gray-100 text-gray-400'
  if (s.includes('manual_review')) return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-700'
}
function getBlkColor(s: string) {
  if (!s) return 'bg-gray-100 text-gray-500'
  if (s === 'payment_blocking_ready') return 'bg-purple-100 text-purple-700'
  if (s.includes('manual_review')) return 'bg-orange-100 text-orange-700'
  if (s.includes('duplicate')) return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-700'
}
