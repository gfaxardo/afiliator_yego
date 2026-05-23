import { useEffect, useState } from 'react'
import {
  getReconciliationSummary,
  getIntegrityMetrics,
  type ReconciliationSummary,
  type IntegrityMetrics,
} from '../../api/unifiedLoad'

export default function AttributionIntegrityDashboard() {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null)
  const [metrics, setMetrics] = useState<IntegrityMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true); setError(null)
    try {
      const [s, m] = await Promise.all([getReconciliationSummary(), getIntegrityMetrics()])
      setSummary(s); setMetrics(m)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al cargar')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="text-xs text-gray-400 p-4">Cargando dashboard...</div>

  if (!summary) return <div className="text-xs text-red-500 p-4">{error || 'Sin datos'}</div>

  const integrityColor = (pct: number) =>
    pct >= 90 ? 'text-green-600' : pct >= 70 ? 'text-amber-600' : 'text-red-600'

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Integridad de Atribucion</h2>
        <p className="text-xs text-gray-500 mt-1">
          Reconciliacion entre atribuciones oficiales, observadas y operacion real.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{error}</div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-white border rounded-lg p-3 text-center">
          <div className="text-[10px] text-gray-400">Integridad</div>
          <div className={`text-2xl font-bold ${integrityColor(summary.attribution_integrity_pct)}`}>
            {summary.attribution_integrity_pct}%
          </div>
        </div>
        <div className="bg-white border rounded-lg p-3 text-center">
          <div className="text-[10px] text-gray-400">Sin Atribucion</div>
          <div className={`text-2xl font-bold ${summary.missing_attribution_rate !== undefined ? integrityColor(100 - (summary.missing_attribution_rate || 0)) : 'text-gray-700'}`}>
            {metrics?.missing_attribution_rate ?? '-'}%
          </div>
        </div>
        <div className="bg-white border rounded-lg p-3 text-center">
          <div className="text-[10px] text-gray-400">Observed Only</div>
          <div className="text-2xl font-bold text-amber-600">{summary.official_missing}</div>
        </div>
        <div className="bg-white border rounded-lg p-3 text-center">
          <div className="text-[10px] text-gray-400">Operational Gaps</div>
          <div className="text-2xl font-bold text-red-600">{summary.operational_gaps}</div>
        </div>
      </div>

      {/* Detailed stats */}
      <div className="grid grid-cols-2 gap-4">
        {/* Left: Summary */}
        <div className="bg-white border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Resumen de Atribuciones</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Stat label="Pendientes" value={summary.total_pending} color="amber" />
            <Stat label="Validadas" value={summary.total_validated} color="green" />
            <Stat label="Rechazadas" value={summary.total_rejected} color="red" />
            <Stat label="Conflictos" value={summary.active_conflicts} color="red" />
            <Stat label="Auto-detectables" value={summary.auto_detectable_reconciliations} color="blue" />
            <Stat label="Drivers fuente" value={summary.total_source_drivers} color="gray" />
          </div>
        </div>

        {/* Right: Confidence Distribution */}
        <div className="bg-white border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Distribucion Confidence</h3>
          <div className="space-y-2 text-xs">
            <ConfBar label="HIGH" value={summary.matched_high} total={summary.total_observed} color="green" />
            <ConfBar label="MEDIUM" value={summary.matched_medium} total={summary.total_observed} color="blue" />
            <ConfBar label="MANUAL REVIEW" value={summary.manual_review} total={summary.total_observed} color="amber" />
            <ConfBar label="UNMATCHED / BLOCKED" value={summary.unmatched} total={summary.total_observed} color="red" />
          </div>
        </div>
      </div>

      {/* Aging */}
      <div className="bg-white border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Aging de Pendientes</h3>
        <div className="flex gap-4 text-xs">
          <AgeBadge label="< 24h" value={summary.aging?.pending_24h ?? 0} color="green" />
          <AgeBadge label="1-3d" value={summary.aging?.pending_1_3d ?? 0} color="amber" />
          <AgeBadge label="> 3d" value={summary.aging?.pending_gt_3d ?? 0} color="red" />
        </div>
      </div>

      {/* Scouts with conflicts */}
      {summary.scouts_with_most_conflicts?.length > 0 && (
        <div className="bg-white border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Scouts con mas discrepancias</h3>
          <div className="space-y-1">
            {summary.scouts_with_most_conflicts.map((s, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-gray-600">{s.scout}</span>
                <span className="font-medium text-red-600">{s.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  const m: Record<string, string> = {
    green: 'text-green-700', red: 'text-red-600', blue: 'text-blue-700',
    amber: 'text-amber-600', gray: 'text-gray-600',
  }
  return (
    <div className="bg-gray-50 rounded p-2 flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className={`font-bold ${m[color] || 'text-gray-700'}`}>{value}</span>
    </div>
  )
}

function ConfBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0
  const m: Record<string, string> = {
    green: 'bg-green-500', blue: 'bg-blue-500', amber: 'bg-amber-500', red: 'bg-red-500',
  }
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between">
        <span className="text-gray-500">{label}</span>
        <span className="font-medium">{value} ({pct.toFixed(0)}%)</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${m[color] || 'bg-gray-400'}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function AgeBadge({ label, value, color }: { label: string; value: number; color: string }) {
  const m: Record<string, string> = {
    green: 'bg-green-100 text-green-700 border-green-200',
    amber: 'bg-amber-100 text-amber-700 border-amber-200',
    red: 'bg-red-100 text-red-700 border-red-200',
  }
  return (
    <div className={`flex-1 border rounded-lg p-3 text-center ${m[color] || ''}`}>
      <div className="text-[10px] opacity-70">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  )
}
