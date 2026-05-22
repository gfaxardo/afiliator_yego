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
      {/* LEGACY DEPRECATION BANNER */}
      <div className="bg-amber-50 border-2 border-amber-300 rounded-lg p-5">
        <div className="flex items-start gap-3">
          <span className="text-2xl">{'\u26A0'}</span>
          <div>
            <h3 className="text-base font-bold text-amber-800">
              LEGACY — SOLO HISTORICO
            </h3>
            <p className="text-sm text-amber-700 mt-1">
              Estos esquemas de conversion son el sistema legacy. Ya no se crean ni modifican desde aqui.
            </p>
            <p className="text-xs text-amber-600 mt-2">
              Para crear, versionar y administrar reglas de pago, usa la pestana{' '}
              <strong>Configuracion</strong> (PaymentScheme + PaymentSchemeVersion + Tiers).
              Este panel es solo lectura historica.
            </p>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4">
          Esquemas de Conversion <span className="text-xs text-amber-600 font-normal ml-2">(LEGACY — READ ONLY)</span>
        </h2>
        {schemes.length === 0 ? (
          <div className="text-gray-400 py-8 text-center bg-white border rounded-lg">
            No hay esquemas configurados.
          </div>
        ) : (
          <div className="space-y-4">
            {schemes.map((scheme) => (
              <div key={scheme.id} className="bg-white border border-gray-200 rounded-lg p-6 opacity-75">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="font-semibold text-lg">{scheme.scheme_name}</h3>
                    <div className="flex gap-3 mt-1 text-sm text-gray-500">
                      <span>Origin: {scheme.origin || '-'}</span>
                      <span>Tipo: {scheme.scout_type || '-'}</span>
                      <span>Min. Afiliaciones: {scheme.min_affiliations}</span>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                    LEGACY
                  </span>
                </div>

                <h4 className="text-sm font-medium text-gray-500 mb-2">Tramos</h4>
                <div className="overflow-hidden border rounded">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2 font-medium text-gray-500">Tasa Conversion Min.</th>
                        <th className="text-left p-2 font-medium text-gray-500">Pago por Convertido</th>
                        <th className="text-left p-2 font-medium text-gray-500">Moneda</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scheme.tiers && scheme.tiers.length > 0 ? (
                        scheme.tiers.map((tier) => (
                          <tr key={tier.id} className="border-t">
                            <td className="p-2">{(tier.min_conversion_rate * 100).toFixed(0)}%</td>
                            <td className="p-2 font-medium">S/ {tier.payment_per_converted_driver.toFixed(2)}</td>
                            <td className="p-2">{tier.currency}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={3} className="p-4 text-center text-gray-400">Sin tramos asociados</td>
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
        <div className="bg-white border border-gray-200 rounded-lg p-6 opacity-75">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            Resumen de Tramos Legacy ({tiers.length})
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {tiers
              .filter((t) => t.active)
              .sort((a, b) => a.min_conversion_rate - b.min_conversion_rate)
              .map((t) => (
                <div key={t.id} className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-gray-500">
                    {(t.min_conversion_rate * 100).toFixed(0)}%
                  </div>
                  <div className="text-sm text-gray-400 mt-1">
                    S/ {t.payment_per_converted_driver.toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-400">{t.currency}</div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
