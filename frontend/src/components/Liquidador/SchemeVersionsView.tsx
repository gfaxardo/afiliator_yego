import { useState } from 'react'
import {
  getSchemeVersions,
  getSchemeChangeLog,
  previewSchemeImport,
  commitSchemeImport,
  SchemeVersionItem,
} from '../../api/scoutLiq'

export default function SchemeVersionsView() {
  const [versions, setVersions] = useState<SchemeVersionItem[]>([])
  const [changeLog, setChangeLog] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [sheet, setSheet] = useState('')
  const [importPreview, setImportPreview] = useState<any>(null)

  async function loadVersions() {
    setLoading(true)
    try {
      const v = await getSchemeVersions()
      setVersions(v)
    } catch (e: any) { setError('Error al cargar') }
    finally { setLoading(false) }
  }

  async function handlePreview() {
    if (!file) return
    setLoading(true)
    try {
      const r = await previewSchemeImport(file, sheet || undefined)
      setImportPreview(r)
    } catch (e: any) { setError(e.response?.data?.detail || 'Error') }
    finally { setLoading(false) }
  }

  async function handleCommit() {
    if (!file) return
    setLoading(true)
    try {
      const r = await commitSchemeImport(file, sheet || undefined)
      setSuccess(`Importado: ${r.created} esquemas creados`)
      setImportPreview(null)
      await loadVersions()
    } catch (e: any) { setError(e.response?.data?.detail || 'Error') }
    finally { setLoading(false) }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Esquemas de Pago (Versionados)</h2>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h3 className="font-medium">Importar Esquemas desde Excel</h3>
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Archivo</label>
            <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Hoja</label>
            <input type="text" value={sheet} onChange={(e) => setSheet(e.target.value)}
              placeholder="ESQUEMA DE PAGOS" className="border border-gray-300 rounded px-3 py-2 text-sm w-48" />
          </div>
          <button onClick={handlePreview} disabled={!file || loading}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            Preview
          </button>
        </div>
        {importPreview && (
          <div className="bg-blue-50 border border-blue-200 rounded p-3">
            <p className="text-sm">{importPreview.total_rows} filas: {importPreview.will_import} importaran, {importPreview.will_skip} skip, {importPreview.errors} errores</p>
            <button onClick={handleCommit} className="mt-2 bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700">
              Commit Importacion
            </button>
          </div>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-medium">Esquemas Vigentes</h3>
          <button onClick={loadVersions} className="bg-gray-100 text-gray-600 px-3 py-1 rounded text-xs hover:bg-gray-200">
            {loading ? 'Cargando...' : 'Refrescar'}
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Nombre</th>
                <th className="px-3 py-2">Tipo</th>
                <th className="px-3 py-2">Origen</th>
                <th className="px-3 py-2">Vigencia</th>
                <th className="px-3 py-2">Activo</th>
                <th className="px-3 py-2">Origen (sheet)</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id} className="border-t border-gray-100">
                  <td className="px-3 py-2">{v.id}</td>
                  <td className="px-3 py-2 max-w-[200px] truncate">{v.scheme_name}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      v.scheme_type === 'quality_conversion' ? 'bg-blue-100 text-blue-700' :
                      v.scheme_type === 'legacy_milestone' ? 'bg-yellow-100 text-yellow-700' :
                      v.scheme_type === 'supervisor_commission' ? 'bg-purple-100 text-purple-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>{v.scheme_type}</span>
                  </td>
                  <td className="px-3 py-2">{v.origin || '-'}</td>
                  <td className="px-3 py-2 text-xs">{v.valid_from || '-'} al {v.valid_to || '-'}</td>
                  <td className="px-3 py-2">{v.active ? 'Si' : 'No'}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{v.source_sheet || '-'}</td>
                </tr>
              ))}
              {versions.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-4 text-center text-gray-400">Sin esquemas. Importa o carga para empezar.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
