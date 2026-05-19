import { useEffect, useState } from 'react'
import { getSchemes, getTiers, SchemeResponse, TierResponse } from '../../api/scoutLiq'

export default function ConfigView() {
  const [schemes, setSchemes] = useState<SchemeResponse[]>([])
  const [tiers, setTiers] = useState<TierResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getSchemes(), getTiers()])
      .then(([s, t]) => {
        setSchemes(s)
        setTiers(t)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-gray-500">Cargando configuracion...</div>
  if (error) return <div className="text-red-600">Error: {error}</div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-4">Esquemas de Conversion</h2>
        {schemes.length === 0 ? (
          <div className="text-gray-400 py-8 text-center bg-white border rounded-lg">
            No hay esquemas configurados. Ejecuta el seed inicial.
          </div>
        ) : (
          <div className="space-y-4">
            {schemes.map((scheme) => (
              <div key={scheme.id} className="bg-white border rounded-lg p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="font-semibold text-lg">{scheme.scheme_name}</h3>
                    <div className="flex gap-3 mt-1 text-sm text-gray-500">
                      <span>Origin: {scheme.origin || '-'}</span>
                      <span>Tipo: {scheme.scout_type || '-'}</span>
                      <span>Min. Afiliaciones: {scheme.min_affiliations}</span>
                    </div>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      scheme.active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {scheme.active ? 'Activo' : 'Inactivo'}
                  </span>
                </div>

                <h4 className="text-sm font-medium text-gray-500 mb-2">Tramos</h4>
                <div className="overflow-hidden border rounded">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2 font-medium text-gray-500">
                          Tasa Conversion Min.
                        </th>
                        <th className="text-left p-2 font-medium text-gray-500">
                          Pago por Convertido
                        </th>
                        <th className="text-left p-2 font-medium text-gray-500">
                          Moneda
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {scheme.tiers && scheme.tiers.length > 0 ? (
                        scheme.tiers.map((tier) => (
                          <tr key={tier.id} className="border-t">
                            <td className="p-2">
                              {(tier.min_conversion_rate * 100).toFixed(0)}%
                            </td>
                            <td className="p-2 font-medium">
                              S/ {tier.payment_per_converted_driver.toFixed(2)}
                            </td>
                            <td className="p-2">{tier.currency}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={3} className="p-4 text-center text-gray-400">
                            Sin tramos asociados
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {tiers.length > 0 && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            Resumen de Tramos ({tiers.length})
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {tiers
              .filter((t) => t.active)
              .sort((a, b) => a.min_conversion_rate - b.min_conversion_rate)
              .map((t) => (
                <div key={t.id} className="bg-blue-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-blue-700">
                    {(t.min_conversion_rate * 100).toFixed(0)}%
                  </div>
                  <div className="text-sm text-blue-600 mt-1">
                    S/ {t.payment_per_converted_driver.toFixed(2)}
                  </div>
                  <div className="text-xs text-blue-400">{t.currency}</div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
