/**
 * Executive Dashboard — Control Tower
 * Fase 3: Executive Control Layer
 *
 * KPIs, funnel, rankings, operational health.
 * Drilldown: click KPI → filter operational views.
 */
import { useEffect, useState } from 'react'
import {
  getExecutiveSummary, getDashboardFunnel, getScoutRanking,
  getOriginRanking, getOperationalHealth,
  type ExecutiveSummary, type FunnelResponse, type FunnelStage,
  type ScoutRankItem, type OriginRankItem, type OperationalHealth,
} from '../../api/scoutLiq'
import { useNavigate } from 'react-router-dom'

const ORIGIN_LABELS: Record<string, string> = {
  cabinet: 'Adquisicion', fleet: 'Flota', fleet_migration: 'Flota Migrada', unknown: 'Desconocido',
}

export default function ExecutiveDashboard() {
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null)
  const [funnel, setFunnel] = useState<FunnelResponse | null>(null)
  const [scouts, setScouts] = useState<ScoutRankItem[]>([])
  const [origins, setOrigins] = useState<OriginRankItem[]>([])
  const [health, setHealth] = useState<OperationalHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    try {
      const [s, f, sc, or, h] = await Promise.all([
        getExecutiveSummary(), getDashboardFunnel(),
        getScoutRanking(), getOriginRanking(), getOperationalHealth(),
      ])
      setSummary(s); setFunnel(f); setScouts(sc); setOrigins(or); setHealth(h)
    } catch (err: any) {
      setError(err?.message || String(err))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading) return <div className="p-8 text-gray-400 text-sm">Cargando panel ejecutivo...</div>

  return (
    <div className="space-y-5 p-4 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Panel Ejecutivo</h2>
          <p className="text-xs text-gray-400 mt-0.5">Control Tower — Vista dominante de operaciones</p>
        </div>
        <button onClick={load} className="text-xs px-3 py-1 rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100">
          Refrescar
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-xs">{error}</div>}
      {!funnel?.stages?.length && <div className="bg-amber-50 border border-amber-200 rounded p-3 text-amber-700 text-xs">No hay datos de cutoff. Ejecuta un corte primero.</div>}

      {/* ── KPI Cards Row ── */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-7 gap-2">
          <KpiCard label="Afiliados" value={summary.total_affiliations} color="slate" onClick={() => navigate('/scout-liq/liquidador')} />
          <KpiCard label="Conectados" value={summary.total_connected} color="blue" />
          <KpiCard label="1+ viaje" value={summary.total_1_trip} color="green" />
          <KpiCard label="5V/7D" value={summary.total_5v7d} color="emerald" />
          <KpiCard label="Conversion" value={`${summary.global_conversion_rate}%`} color="purple" />
          <KpiCard label="A pagar" value={`S/ ${summary.total_to_pay.toLocaleString()}`} color="amber" />
          <KpiCard label="Costo/conv" value={`S/ ${summary.cost_per_converted.toFixed(0)}`} color="orange" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* ── Funnel ── */}
        <div className="lg:col-span-1 bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Embudo de Conversion</h3>
          {funnel?.stages && <ConversionFunnel stages={funnel.stages} />}
        </div>

        {/* ── Operational Health ── */}
        <div className="lg:col-span-2 bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Salud Operacional</h3>
          {health && <HealthGrid health={health} onDrill={(filter) => navigate(`/scout-liq/liquidador`)} />}
        </div>
      </div>

      {/* ── Rankings ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Top Scouts</h3>
          <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0"><tr>
                <th className="text-left p-2">Scout</th>
                <th className="text-right p-2">Afiliados</th>
                <th className="text-right p-2">Activados</th>
                <th className="text-right p-2">5V/7D</th>
                <th className="text-right p-2">Conv %</th>
                <th className="text-right p-2">Pago</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-50">
                {scouts.length === 0 ? (
                  <tr><td colSpan={6} className="p-4 text-center text-xs text-gray-400">Sin datos de scouts</td></tr>
                ) : scouts.map((s, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="p-2 font-medium text-gray-700">{s.scout_name}</td>
                    <td className="p-2 text-right">{s.affiliations}</td>
                    <td className="p-2 text-right text-green-700">{s.activated}</td>
                    <td className="p-2 text-right text-blue-700 font-bold">{s.converted_5v7d}</td>
                    <td className="p-2 text-right">{s.conversion_rate}%</td>
                    <td className="p-2 text-right font-medium">S/ {s.total_payout.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Por Origen</h3>
          <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0"><tr>
                <th className="text-left p-2">Origen</th>
                <th className="text-right p-2">Afiliados</th>
                <th className="text-right p-2">Activados</th>
                <th className="text-right p-2">5V/7D</th>
                <th className="text-right p-2">Conv %</th>
                <th className="text-right p-2">Pago</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-50">
                {origins.length === 0 ? (
                  <tr><td colSpan={6} className="p-4 text-center text-xs text-gray-400">Sin datos de origenes</td></tr>
                ) : origins.map((o, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="p-2 font-medium text-gray-700">{ORIGIN_LABELS[o.origin] || o.origin}</td>
                    <td className="p-2 text-right">{o.affiliations}</td>
                    <td className="p-2 text-right text-green-700">{o.activated}</td>
                    <td className="p-2 text-right text-blue-700 font-bold">{o.converted_5v7d}</td>
                    <td className="p-2 text-right">{o.conversion_rate}%</td>
                    <td className="p-2 text-right font-medium">S/ {o.total_payout.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Source Drivers KPI */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <MiniCard label="Drivers en fuente" value={summary.total_source_drivers} />
          <MiniCard label="Scouts activos" value={summary.scouts_active} />
          <MiniCard label="Sin scout" value={summary.drivers_without_scout} color="amber" />
          <MiniCard label="Pagables" value={summary.payout_eligible_count} color="green" />
        </div>
      )}
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────

function KpiCard({ label, value, color, onClick }: {
  label: string; value: string | number; color: string; onClick?: () => void
}) {
  const colors: Record<string, string> = {
    slate: 'border-l-slate-400 bg-slate-50', blue: 'border-l-blue-400 bg-blue-50',
    green: 'border-l-green-400 bg-green-50', emerald: 'border-l-emerald-400 bg-emerald-50',
    purple: 'border-l-purple-400 bg-purple-50', amber: 'border-l-amber-400 bg-amber-50',
    orange: 'border-l-orange-400 bg-orange-50', red: 'border-l-red-400 bg-red-50',
  }
  return (
    <div
      className={`border-l-4 rounded-r-lg p-3 cursor-pointer hover:shadow-sm transition-shadow ${colors[color] || colors.slate}`}
      onClick={onClick}
    >
      <div className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</div>
      <div className="text-lg font-bold text-gray-800">{value}</div>
    </div>
  )
}

function MiniCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 text-center">
      <div className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</div>
      <div className={`text-base font-bold ${color === 'green' ? 'text-green-700' : color === 'amber' ? 'text-amber-700' : 'text-gray-800'}`}>{value}</div>
    </div>
  )
}

function ConversionFunnel({ stages }: { stages: FunnelStage[] }) {
  const max = Math.max(...stages.map(s => s.count), 1)
  const colors = ['bg-slate-500', 'bg-blue-500', 'bg-green-500', 'bg-emerald-600', 'bg-teal-600', 'bg-cyan-700']

  return (
    <div className="space-y-1.5">
      {stages.map((s, i) => {
        const width = (s.count / max * 100)
        const prev = i > 0 ? stages[i - 1].count : s.count
        const rate = prev > 0 ? (s.count / prev * 100).toFixed(0) : '100'
        return (
          <div key={s.stage} className="group">
            <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
              <span>{s.label}</span>
              <span className="font-mono">{s.count} <span className="text-gray-300">({rate}%)</span></span>
            </div>
            <div className="h-4 bg-gray-100 rounded overflow-hidden">
              <div
                className={`h-full rounded transition-all ${colors[i] || 'bg-gray-400'}`}
                style={{ width: `${Math.max(width, 2)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function HealthGrid({ health, onDrill }: { health: OperationalHealth; onDrill: (filter: string) => void }) {
  const items = [
    { key: 'critical', label: 'Criticos', value: health.critical, bg: 'bg-red-50 border-red-200 text-red-800' },
    { key: 'warning', label: 'Warnings', value: health.warning, bg: 'bg-amber-50 border-amber-200 text-amber-800' },
    { key: 'pending_review', label: 'Pendientes', value: health.pending_review, bg: 'bg-yellow-50 border-yellow-200 text-yellow-800' },
    { key: 'supervisor_review', label: 'Supervisor', value: health.supervisor_review, bg: 'bg-orange-50 border-orange-200 text-orange-800' },
    { key: 'no_scout', label: 'Sin scout', value: health.no_scout, bg: 'bg-gray-50 border-gray-300 text-gray-700' },
    { key: 'no_lead_date', label: 'Sin fecha lead', value: health.no_lead_date, bg: 'bg-purple-50 border-purple-200 text-purple-800' },
    { key: 'duplicates', label: 'Duplicados', value: health.duplicates, bg: 'bg-pink-50 border-pink-200 text-pink-800' },
    { key: 'blocked', label: 'Bloqueados', value: health.blocked, bg: 'bg-red-100 border-red-300 text-red-800' },
    { key: 'approved_manual', label: 'Aprob Manual', value: health.approved_manual, bg: 'bg-blue-50 border-blue-200 text-blue-800' },
    { key: 'payable', label: 'Pagables', value: health.payable, bg: 'bg-green-50 border-green-200 text-green-800' },
    { key: 'paid', label: 'Pagados', value: health.paid, bg: 'bg-teal-50 border-teal-200 text-teal-800' },
  ]

  return (
    <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onDrill(item.key)}
          className={`border rounded-lg p-2 text-center hover:shadow-sm transition-shadow cursor-pointer ${item.bg}`}
        >
          <div className="text-lg font-bold">{item.value}</div>
          <div className="text-[10px] uppercase tracking-wider mt-0.5">{item.label}</div>
        </button>
      ))}
    </div>
  )
}
