import { useEffect, useState, useMemo } from 'react'
import {
  listCutoffs, getCutoffSummary, getCutoffLines, getCutoffTrend,
  type TrendItem,
} from '../../api/scoutLiq'

interface CutoffRun {
  id: number; cutoff_name: string; hire_date_from: string; hire_date_to: string
  status: string; quality_data_contract_status: string; conversion_metric_status: string
}
interface Summary {
  id: number; scout_id: number; scout_name: string; origin: string
  total_affiliations: number; total_activated: number
  drivers_1plus_0_7: number; drivers_5plus_0_7: number
  drivers_1plus_8_14: number; drivers_5plus_0_14: number
  total_converted_5v14d: number; not_converted: number
  conversion_rate: number; conversion_rate_5v7d: number
  tier_reached: number; payment_per_converted_driver: number
  payout_per_activated: number; amount_calculated: number
  total_payable: number; status: string; blocked_reason: string
}
interface DriverLine {
  id: number; scout_id: number; driver_id: string; origin: string
  activated_flag: boolean; is_converted_5trips_7d: boolean
  is_converted_5trips_14d: boolean; payout_eligible_flag: boolean
  payment_status: string; blocked_reason: string
  line_status: string; calculated_amount: number
}

export default function DashboardView() {
  const [cutoffs, setCutoffs] = useState<CutoffRun[]>([])
  const [selectedCutoff, setSelectedCutoff] = useState<number | null>(null)
  const [summaries, setSummaries] = useState<Summary[]>([])
  const [lines, setLines] = useState<DriverLine[]>([])
  const [trend, setTrend] = useState<TrendItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([listCutoffs(), getCutoffTrend()])
      .then(([cuts, t]) => {
        setCutoffs(cuts as CutoffRun[])
        setTrend(t)
        const active = (cuts as CutoffRun[]).filter(c =>
          ['calculated', 'reviewed', 'approved', 'paid'].includes(c.status)
        )
        if (active.length > 0) {
          setSelectedCutoff(active[0].id)
        }
      })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedCutoff) return
    setSummaries([])
    setLines([])
    setError(null)
    setLoading(true)
    Promise.all([getCutoffSummary(selectedCutoff), getCutoffLines(selectedCutoff)])
      .then(([s, l]) => {
        setSummaries(s as Summary[])
        setLines(l as DriverLine[])
      })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false))
  }, [selectedCutoff])

  const kpis = useMemo(() => {
    if (!summaries.length) return null
    const totalAff = summaries.reduce((a, s) => a + (s.total_affiliations || 0), 0)
    const totalAct = summaries.reduce((a, s) => a + (s.total_activated || s.drivers_1plus_0_7 || 0), 0)
    const total5v7 = summaries.reduce((a, s) => a + (s.drivers_5plus_0_7 || 0), 0)
    const payout = summaries.reduce((a, s) => a + (Number(s.total_payable || s.amount_calculated) || 0), 0)
    const convRate = totalAct > 0 ? (total5v7 / totalAct * 100) : 0
    const scoutsEnCorte = summaries.length
    const scoutsBloqueados = summaries.filter(s => s.status === 'blocked').length

    const blockedDrivers = lines.filter(l => !l.payout_eligible_flag && l.payment_status !== 'paid').length
    const payableDrivers = lines.filter(l => l.payout_eligible_flag).length
    const paidDrivers = lines.filter(l => l.payment_status === 'paid').length

    return { totalAff, totalAct, total5v7, payout, convRate, scoutsEnCorte, scoutsBloqueados, blockedDrivers, payableDrivers, paidDrivers }
  }, [summaries, lines])

  const bloqueos = useMemo(() => {
    const map: Record<string, number> = {}
    lines.forEach(l => {
      if (!l.payout_eligible_flag && l.blocked_reason) {
        const key = l.blocked_reason.length > 60 ? l.blocked_reason.substring(0, 57) + '...' : l.blocked_reason
        map[key] = (map[key] || 0) + 1
      }
    })
    return Object.entries(map).sort((a, b) => b[1] - a[1])
  }, [lines])

  const currentTrend = useMemo(() => {
    return trend.filter(t => t.status !== 'draft').slice(0, 12).reverse()
  }, [trend])

  if (loading && !kpis) return <div className="p-6 text-gray-400 text-sm">Cargando dashboard...</div>

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">{error}</div>}

      {/* Header + Cutoff selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">Dashboard Ejecutivo</h2>
        <select
          value={selectedCutoff ?? ''}
          onChange={e => setSelectedCutoff(e.target.value ? parseInt(e.target.value) : null)}
          className="border border-gray-200 rounded px-3 py-1.5 text-xs bg-white"
        >
          <option value="">Seleccionar corte</option>
          {cutoffs.filter(c => ['calculated', 'reviewed', 'approved', 'paid'].includes(c.status)).map(c => (
            <option key={c.id} value={c.id}>
              #{c.id} {c.cutoff_name} ({c.status})
            </option>
          ))}
        </select>
      </div>

      {!kpis ? (
        <div className="text-center py-12 text-gray-400 text-sm">
          {cutoffs.length === 0
            ? 'No hay cortes calculados. Crea un corte en Liquidador primero.'
            : 'Selecciona un corte para ver el dashboard.'}
        </div>
      ) : (
        <>
          {/* BLOCK 1 — KPI Cards */}
          <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
            <KpiCard label="Afiliados" value={kpis.totalAff} color="text-gray-700" />
            <KpiCard label="Activados" value={kpis.totalAct} color="text-green-600" />
            <KpiCard label="5V/7D" value={kpis.total5v7} color="text-blue-600" />
            <KpiCard label="Conversión" value={`${kpis.convRate.toFixed(1)}%`} color="text-indigo-600" />
            <KpiCard label="Payout" value={`S/ ${kpis.payout.toLocaleString()}`} color="text-emerald-600" />
            <KpiCard label="Scouts en corte" value={kpis.scoutsEnCorte} color="text-gray-700" />
            <KpiCard label="Bloqueados" value={kpis.blockedDrivers} color="text-red-600" />
            <KpiCard label="Pagados" value={kpis.paidDrivers} color="text-teal-600" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* BLOCK 2 — Funnel */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Embudo de calidad</h3>
              <div className="space-y-2">
                <FunnelBar label="Afiliados" value={kpis.totalAff} max={kpis.totalAff} color="bg-gray-400" />
                <FunnelBar label="Activados (1+ viaje)" value={kpis.totalAct} max={kpis.totalAff} color="bg-green-500" />
                <FunnelBar label="Convertidos 5V/7D" value={kpis.total5v7} max={kpis.totalAff} color="bg-blue-500" />
                <FunnelBar label="Pagables" value={kpis.payableDrivers} max={kpis.totalAff} color="bg-emerald-500" />
                <FunnelBar label="Pagados" value={kpis.paidDrivers} max={kpis.totalAff} color="bg-teal-500" />
              </div>
              <div className="mt-3 pt-3 border-t border-gray-100">
                <div className="flex justify-between text-[10px] text-gray-400">
                  <span>Activación: {kpis.totalAff > 0 ? (kpis.totalAct / kpis.totalAff * 100).toFixed(1) : 0}%</span>
                  <span>5V/7D: {kpis.totalAct > 0 ? (kpis.total5v7 / kpis.totalAct * 100).toFixed(1) : 0}%</span>
                  <span>Pagables: {kpis.totalAct > 0 ? (kpis.payableDrivers / kpis.totalAct * 100).toFixed(1) : 0}%</span>
                </div>
              </div>
            </div>

            {/* BLOCK 4 — Bloqueos */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Bloqueos</h3>
              {bloqueos.length === 0 ? (
                <div className="text-xs text-gray-400 py-4 text-center">Sin bloqueos en este corte</div>
              ) : (
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {bloqueos.map(([reason, count]) => (
                    <div key={reason} className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-600 truncate flex-1" title={reason}>{reason}</span>
                      <span className="text-[11px] font-mono font-bold text-red-600 shrink-0">{count}</span>
                      <div className="w-20 h-2 bg-gray-100 rounded overflow-hidden shrink-0">
                        <div
                          className="h-full bg-red-400 rounded"
                          style={{ width: `${Math.min(100, count / Math.max(...bloqueos.map(b => b[1])) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* BLOCK 3 — Ranking Scouts */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-4 py-2 border-b border-gray-100">
              Ranking de Scouts
            </h3>
            <div className="overflow-x-auto max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-1.5">Scout</th>
                    <th className="text-right px-3 py-1.5">Afiliados</th>
                    <th className="text-right px-3 py-1.5">Activados</th>
                    <th className="text-right px-3 py-1.5">5V/7D</th>
                    <th className="text-right px-3 py-1.5">Conv%</th>
                    <th className="text-center px-3 py-1.5">Tier</th>
                    <th className="text-right px-3 py-1.5">Pago/act</th>
                    <th className="text-right px-3 py-1.5">Total</th>
                    <th className="text-left px-3 py-1.5">Estado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {[...summaries]
                    .sort((a, b) => (Number(b.total_payable || b.amount_calculated) || 0) - (Number(a.total_payable || a.amount_calculated) || 0))
                    .map(s => (
                      <tr key={s.id} className="hover:bg-blue-50/30">
                        <td className="px-3 py-1 font-medium text-gray-800 max-w-[140px] truncate" title={s.scout_name}>
                          {s.scout_name}
                        </td>
                        <td className="px-3 py-1 text-right font-mono">{s.total_affiliations}</td>
                        <td className="px-3 py-1 text-right font-mono font-bold text-green-700">
                          {s.total_activated ?? s.drivers_1plus_0_7}
                        </td>
                        <td className="px-3 py-1 text-right font-mono font-bold text-blue-700">
                          {s.drivers_5plus_0_7}
                        </td>
                        <td className="px-3 py-1 text-right font-mono">
                          {((Number(s.conversion_rate_5v7d ?? s.conversion_rate)) * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-1 text-center">
                          {s.tier_reached
                            ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-100 text-blue-700 font-medium">
                                {Number(s.tier_reached * 100).toFixed(0)}%
                              </span>
                            : <span className="text-gray-300">-</span>
                          }
                        </td>
                        <td className="px-3 py-1 text-right font-mono text-gray-500">
                          S/ {Number(s.payout_per_activated ?? s.payment_per_converted_driver).toFixed(0)}
                        </td>
                        <td className="px-3 py-1 text-right font-mono font-bold">
                          S/ {Number(s.total_payable || s.amount_calculated).toFixed(0)}
                        </td>
                        <td className="px-3 py-1">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            s.status === 'paid' ? 'bg-teal-100 text-teal-700' :
                            s.status === 'blocked' ? 'bg-red-100 text-red-700' :
                            s.status === 'pending' ? 'bg-green-100 text-green-700' :
                            'bg-gray-100 text-gray-500'
                          }`}>
                            {s.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* BLOCK 5 — Tendencia */}
          {currentTrend.length > 1 && (
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Tendencia por Corte
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[10px] text-gray-400 uppercase">
                      <th className="text-left pb-1 pr-3">Corte</th>
                      <th className="text-right pb-1 px-2">Afiliados</th>
                      <th className="text-right pb-1 px-2">Activados</th>
                      <th className="text-right pb-1 px-2">5V/7D</th>
                      <th className="text-right pb-1 px-2">Payout</th>
                      <th className="text-right pb-1 px-2">Bloqueos</th>
                      <th className="text-center pb-1 pl-2">Estado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {currentTrend.map((t, i) => {
                      const convRate = t.total_activated > 0 ? (t.converted_5v7d / t.total_activated * 100).toFixed(1) : '0'
                      return (
                        <tr key={t.id} className={i === currentTrend.length - 1 ? 'font-medium' : ''}>
                          <td className="py-1 pr-3 whitespace-nowrap">
                            <span className="text-gray-800">#{t.id}</span>
                            <span className="text-gray-400 ml-1">{t.cutoff_name}</span>
                          </td>
                          <td className="py-1 px-2 text-right font-mono">{t.total_affiliations}</td>
                          <td className="py-1 px-2 text-right font-mono text-green-700">{t.total_activated}</td>
                          <td className="py-1 px-2 text-right font-mono text-blue-700">
                            {t.converted_5v7d}
                            <span className="text-gray-400 ml-0.5">({convRate}%)</span>
                          </td>
                          <td className="py-1 px-2 text-right font-mono font-medium">
                            S/ {t.total_payable.toLocaleString()}
                          </td>
                          <td className="py-1 px-2 text-right font-mono text-red-600">{t.blocked_scouts}</td>
                          <td className="py-1 pl-2 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              t.status === 'paid' ? 'bg-teal-100 text-teal-700' :
                              t.status === 'approved' ? 'bg-green-100 text-green-700' :
                              t.status === 'reviewed' ? 'bg-yellow-100 text-yellow-700' :
                              'bg-blue-100 text-blue-700'
                            }`}>
                              {t.status}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function KpiCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-center hover:shadow-sm transition-shadow">
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-400 uppercase tracking-wider mt-0.5">{label}</div>
    </div>
  )
}

function FunnelBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-gray-600 w-32 shrink-0 text-right">{label}</span>
      <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden relative">
        <div className={`h-full ${color} rounded transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
        <span className="absolute inset-0 flex items-center px-2 text-[10px] font-bold text-white drop-shadow">
          {value}
        </span>
      </div>
      <span className="text-[10px] text-gray-400 w-10 shrink-0">{pct.toFixed(0)}%</span>
    </div>
  )
}
