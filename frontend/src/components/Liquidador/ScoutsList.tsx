import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getScouts, ScoutResponse } from '../../api/scoutLiq'

export default function ScoutsList() {
  const [scouts, setScouts] = useState<ScoutResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    getScouts()
      .then(setScouts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  if (loading) return <div className="text-gray-500">Cargando scouts...</div>
  if (error) return <div className="text-red-600">Error: {error}</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Scouts ({scouts.length})</h2>
        <Link
          to="/scout-liq/scouts/new"
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
        >
          + Nuevo Scout
        </Link>
      </div>

      {scouts.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-lg">No hay scouts registrados</p>
          <p className="text-sm mt-1">Crea el primer scout para comenzar</p>
        </div>
      ) : (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left p-3 font-medium text-gray-500">ID</th>
                <th className="text-left p-3 font-medium text-gray-500">Nombre</th>
                <th className="text-left p-3 font-medium text-gray-500">Documento</th>
                <th className="text-left p-3 font-medium text-gray-500">Tipo</th>
                <th className="text-left p-3 font-medium text-gray-500">Pais</th>
                <th className="text-left p-3 font-medium text-gray-500">Ciudad</th>
                <th className="text-left p-3 font-medium text-gray-500">Estado</th>
              </tr>
            </thead>
            <tbody>
              {scouts.map((s) => (
                <tr key={s.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-mono text-xs">{s.id}</td>
                  <td className="p-3 font-medium">{s.scout_name}</td>
                  <td className="p-3 text-gray-500">{s.document_number || '-'}</td>
                  <td className="p-3">{s.scout_type || '-'}</td>
                  <td className="p-3">{s.country || '-'}</td>
                  <td className="p-3">{s.city || '-'}</td>
                  <td className="p-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        s.status === 'active'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {s.status || '-'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
