import { useState } from 'react'

export default function WorkbookImportView() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<any>(null)
  const [commitResult, setCommitResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])

  function addLog(msg: string) { setLogs(p => [...p, `[${new Date().toLocaleTimeString()}] ${msg}`]) }

  async function handlePreview() {
    if (!file) return
    setLoading(true); setError(null); setSuccess(null); setPreview(null); setCommitResult(null)
    addLog(`Iniciando preview global: ${file.name}`)
    const t0 = performance.now()
    try {
      const form = new FormData(); form.append('file', file)
      const r = await fetch('/api/scout-liq/workbook-import/preview', { method: 'POST', body: form })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Error'); addLog(`ERROR: ${r.status}`); return }
      setPreview(data)
      const g = data.global || {}
      addLog(`Preview completado en ${((performance.now()-t0)/1000).toFixed(1)}s: ${g.total_rows} filas | scouts=${g.scouts_ready} | attr_ready=${g.attribution_ready} | pay_ready=${g.payment_ready} | pay_na=${g.payment_not_applicable} | monto=S/ ${Number(g.amount_ready||0).toFixed(2)}`)
      setSuccess('Preview OK')
    } catch (e: any) { setError(e.message); addLog(`ERROR: ${e.message}`) }
    finally { setLoading(false) }
  }

  async function handleCommit() {
    if (!file) return
    setLoading(true); setError(null); setSuccess(null); setCommitResult(null)
    addLog('Iniciando commit global...')
    try {
      const form = new FormData(); form.append('file', file)
      const r = await fetch('/api/scout-liq/workbook-import/commit', { method: 'POST', body: form })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Error'); addLog(`ERROR commit: ${r.status}`); return }
      setCommitResult(data)
      addLog(`Commit completado: scouts_created=${data.scouts_created} attr=${data.historical_attributions_created} paid=${data.paid_history_created} supervisor_links=${data.scout_supervisor_links_created}`)
      setSuccess(`Importacion completada: ${data.scouts_created} scouts, ${data.historical_attributions_created} atribuciones, ${data.paid_history_created} pagos`)
    } catch (e: any) { setError(e.message); addLog(`ERROR: ${e.message}`) }
    finally { setLoading(false) }
  }

  const g = preview?.global || {}
  const pay = preview?.payments?.payment || {}
  const attr = preview?.payments?.attribution || {}

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Importacion Integral</h2>
        <a href="/api/scout-liq/templates/historical-import"
          className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 inline-flex items-center gap-2" download>
          Descargar plantilla
        </a>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Archivo Excel (workbook completo)</label>
            <input type="file" accept=".xlsx" onChange={e => { setFile(e.target.files?.[0]||null); setPreview(null); setCommitResult(null); setError(null); setSuccess(null); setLogs([]) }}
              className="border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          <button onClick={handlePreview} disabled={!file || loading}
            className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50 font-medium">
            {loading ? 'Procesando...' : 'Preview Global'}
          </button>
        </div>
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
        {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}
      </div>

      {preview && (
        <div className="space-y-4">
          {/* Sheets detected */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h3 className="font-medium mb-3">Hojas detectadas</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-sm">
              {(preview.detected_sheets || []).map((s: any) => (
                <div key={s.name} className="flex justify-between bg-gray-50 px-3 py-2 rounded">
                  <span>{s.name}</span>
                  <span className="text-gray-500">{s.import_type} ({s.rows} filas)</span>
                </div>
              ))}
              {(preview.ignored_sheets || []).map((s: any) => (
                <div key={s.name} className="flex justify-between bg-gray-100 px-3 py-2 rounded text-gray-400">
                  <span>{s.name}</span><span>solo referencia</span>
                </div>
              ))}
            </div>
          </div>

          {/* Module summaries */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ModCard title="Scouts" color="blue">
              <div>Crear: <b>{preview.scouts?.will_create || 0}</b></div>
              <div>Actualizar: <b>{preview.scouts?.will_update || 0}</b></div>
            </ModCard>
            <ModCard title="Supervisores" color="purple">
              <div>Detectados: <b>{preview.supervisors?.total_detected || 0}</b></div>
              <div>Conflictos: <b className="text-red-600">{preview.supervisors?.conflicts || 0}</b></div>
            </ModCard>
            <ModCard title="Atribuciones" color="blue">
              <div>Ready: <b className="text-green-600">{preview.attributions?.ready || 0}</b></div>
              <div>Review: <b className="text-yellow-600">{preview.attributions?.manual_review || 0}</b></div>
            </ModCard>
            <ModCard title="Pagos Historicos" color="green">
              <div>Pay Ready: <b className="text-green-600">{pay.ready || 0}</b></div>
              <div>No Aplica: <b className="text-gray-600">{pay.not_applicable || 0}</b></div>
              <div>Monto: <b>S/ {Number(pay.amount_ready || 0).toFixed(2)}</b></div>
            </ModCard>
            <ModCard title="Atribuciones (desde pagos)" color="indigo">
              <div>Ready: <b className="text-green-600">{attr.ready || 0}</b></div>
              <div>Review: <b className="text-yellow-600">{attr.manual_review || 0}</b></div>
            </ModCard>
            <ModCard title="Esquemas" color="gray">
              <div>Filas: <b>{preview.schemes?.total_rows || 0}</b></div>
            </ModCard>
          </div>

          {/* Global summary */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h3 className="font-medium mb-3">Resumen Global</h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div>Filas totales: <b>{g.total_rows}</b></div>
              <div>Scouts: <b className="text-blue-600">{g.scouts_ready}</b></div>
              <div>Supervisores: <b className="text-purple-600">{g.supervisors_detected}</b></div>
              <div>Attr Ready: <b className="text-green-600">{g.attribution_ready}</b></div>
              <div>Pay Ready: <b className="text-green-600">{g.payment_ready}</b></div>
              <div>Pay N/A: <b className="text-gray-600">{g.payment_not_applicable}</b></div>
              <div>Monto: <b>S/ {Number(g.amount_ready || 0).toFixed(2)}</b></div>
              <div>Tiempo: <b>{g.elapsed_ms}ms</b></div>
            </div>
            <button onClick={handleCommit} disabled={loading}
              className="mt-4 bg-green-600 text-white px-6 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50 font-medium">
              {loading ? 'Importando...' : 'Commit Global'}
            </button>
          </div>

          {/* Supervisor links */}
          {(preview.supervisors?.scout_supervisor_links || []).length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h3 className="font-medium mb-2">Relaciones Scout-Supervisor detectadas</h3>
              <div className="overflow-x-auto max-h-48">
                <table className="w-full text-xs">
                  <thead><tr className="bg-gray-50 text-left"><th className="px-2 py-1">Scout</th><th className="px-2 py-1">Supervisor</th></tr></thead>
                  <tbody>
                    {(preview.supervisors?.scout_supervisor_links || []).map((l: any, i: number) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="px-2 py-1">{l.scout}</td>
                        <td className="px-2 py-1 text-gray-600">{l.supervisor}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Supervisor candidates */}
          {(preview.supervisors?.candidates || []).length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h3 className="font-medium mb-2">Supervisores candidatos ({preview.supervisors?.candidates?.length})</h3>
              <div className="overflow-x-auto max-h-48">
                <table className="w-full text-xs">
                  <thead><tr className="bg-gray-50 text-left">
                    <th className="px-2 py-1">Nombre</th><th className="px-2 py-1">Fuente</th><th className="px-2 py-1">Frecuencia</th><th className="px-2 py-1">Scouts</th><th className="px-2 py-1">Estado</th>
                  </tr></thead>
                  <tbody>
                    {(preview.supervisors?.candidates || []).slice(0, 20).map((c: any, i: number) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="px-2 py-1 font-medium">{c.supervisor_name}</td>
                        <td className="px-2 py-1 text-gray-500">{(c.sources||[]).join(', ')}</td>
                        <td className="px-2 py-1">{c.frequency_total}</td>
                        <td className="px-2 py-1 text-gray-500">{(c.top_scouts||[]).slice(0,3).join(', ')}</td>
                        <td className="px-2 py-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${c.exists_in_db ? 'bg-green-100 text-green-700' : c.has_conflict ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>
                            {c.status}
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
          <h3 className="font-medium text-blue-800 mb-2">Resultado Commit</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="text-green-600">Scouts: <b>{commitResult.scouts_created} creados, {commitResult.scouts_updated} actualizados</b></div>
            <div className="text-purple-600">Sup links: <b>{commitResult.scout_supervisor_links_created}</b></div>
            <div className="text-blue-600">Atribuciones: <b>{commitResult.historical_attributions_created}</b></div>
            <div className="text-green-600">Paid history: <b>{commitResult.paid_history_created}</b></div>
            {commitResult.supervisor_conflicts > 0 && <div className="text-red-600">Conflictos superv: <b>{commitResult.supervisor_conflicts}</b></div>}
            {commitResult.manual_review_saved > 0 && <div className="text-yellow-600">Manual review: <b>{commitResult.manual_review_saved}</b></div>}
          </div>
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 font-mono text-xs max-h-48 overflow-y-auto">
          <div className="text-gray-400 mb-1 flex justify-between">
            <span>Log</span><button onClick={() => setLogs([])} className="text-gray-500 hover:text-gray-300">limpiar</button>
          </div>
          {logs.map((msg, i) => (
            <div key={i} className={`py-0.5 ${msg.includes('ERROR') ? 'text-red-400' : msg.includes('completado') || msg.includes('OK') ? 'text-green-400' : 'text-gray-300'}`}>{msg}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function ModCard({ title, color, children }: { title: string; color: string; children: any }) {
  const c: Record<string, string> = {
    blue: 'border-blue-200 bg-blue-50', green: 'border-green-200 bg-green-50',
    purple: 'border-purple-200 bg-purple-50', gray: 'border-gray-200 bg-gray-50',
    indigo: 'border-indigo-200 bg-indigo-50',
  }
  return (
    <div className={`border rounded-lg p-3 text-xs space-y-1 ${c[color] || c.gray}`}>
      <h4 className="font-bold uppercase text-gray-700">{title}</h4>
      {children}
    </div>
  )
}
