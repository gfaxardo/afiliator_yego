import { useEffect, useState } from 'react'
import { getHealth, getDiagnostic, HealthResponse, DiagnosticResponse } from '../../api/scoutLiq'

export default function HealthCheck() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [diagnostic, setDiagnostic] = useState<DiagnosticResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getHealth(), getDiagnostic()])
      .then(([h, d]) => {
        setHealth(h)
        setDiagnostic(d)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="text-gray-500">Cargando health check...</div>
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        <h2 className="font-semibold">Error de conexion</h2>
        <p className="text-sm mt-1">{error}</p>
        <p className="text-xs mt-2 text-red-500">
          Verifica que el backend este corriendo en http://127.0.0.1:8000
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="bg-white border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">API Health</h2>
        {health && (
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Status:</span>
              <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-800 rounded font-medium">
                {health.status}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Environment:</span>
              <span className="ml-2 font-medium">{health.environment}</span>
            </div>
            <div>
              <span className="text-gray-500">Source Table:</span>
              <span className="ml-2 font-mono text-xs">{health.source_table}</span>
            </div>
          </div>
        )}
      </div>

      {diagnostic && (
        <div className="bg-white border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">
            Diagnostico: {diagnostic.source_table}
          </h2>
          {typeof diagnostic.total_rows === 'number' && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
              <div className="bg-gray-50 rounded p-3">
                <div className="text-gray-500">Total Filas</div>
                <div className="text-xl font-bold">{diagnostic.total_rows}</div>
              </div>
              <div className="bg-gray-50 rounded p-3">
                <div className="text-gray-500">driver_id nulos</div>
                <div className="text-xl font-bold">{diagnostic.null_driver_id}</div>
              </div>
              <div className="bg-gray-50 rounded p-3">
                <div className="text-gray-500">hire_date nulos</div>
                <div className="text-xl font-bold">{diagnostic.null_hire_date}</div>
              </div>
              <div className="bg-gray-50 rounded p-3">
                <div className="text-gray-500">Rango hire_date</div>
                <div className="text-xs font-medium">
                  {diagnostic.hire_date_min || 'N/A'} → {diagnostic.hire_date_max || 'N/A'}
                </div>
              </div>
            </div>
          )}
          {diagnostic.columns && (
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">
                Columnas ({diagnostic.columns.length})
              </h3>
              <div className="max-h-48 overflow-y-auto border rounded">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left p-2">Nombre</th>
                      <th className="text-left p-2">Tipo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diagnostic.columns.map((c, i) => (
                      <tr key={i} className="border-t">
                        <td className="p-2 font-mono">{c.name}</td>
                        <td className="p-2 text-gray-500">{c.type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
