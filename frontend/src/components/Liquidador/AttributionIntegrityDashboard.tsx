import { useEffect, useState } from 'react'
import {
  getReconciliationSummary,
  getIntegrityMetrics,
  getReconciliationFreshness,
  getOperationalGapsDiagnostic,
  refreshReconciliationView,
  type ReconciliationSummary,
  type IntegrityMetrics,
  type ReconciliationFreshness,
  type OperationalGapsDiagnostic,
} from '../../api/unifiedLoad'

export default function AttributionIntegrityDashboard() {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null)
  const [metrics, setMetrics] = useState<IntegrityMetrics | null>(null)
  const [freshness, setFreshness] = useState<ReconciliationFreshness | null>(null)
  const [gapsDiag, setGapsDiag] = useState<OperationalGapsDiagnostic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true); setError(null)
    try {
      const [s, m, f, g] = await Promise.all([
        getReconciliationSummary(),
        getIntegrityMetrics(),
        getReconciliationFreshness(),
        getOperationalGapsDiagnostic(),
      ])
      setSummary(s); setMetrics(m); setFreshness(f); setGapsDiag(g)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Error al cargar')
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true); setRefreshError(null)
    try {
      await refreshReconciliationView()
      await loadData()
    } catch (e: any) {
      setRefreshError(e?.response?.data?.detail || e?.message || 'Error al refrescar')
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) return <div className="text-xs text-gray-400 p-4">Cargando dashboard...</div>

  if (!summary) return <div className="text-xs text-red-500 p-4">{error || 'Sin datos'}</div>

  const integrityColor = (pct: number) =>
    pct >= 90 ? 'text-green-600' : pct >= 70 ? 'text-amber-600' : 'text-red-600'

  const freshnessStatusColor = (status: string) => {
    switch (status) {
      case 'fresh': return 'bg-green-100 text-green-700 border-green-200'
      case 'stale': return 'bg-amber-100 text-amber-700 border-amber-200'
      case 'stale_critical': return 'bg-red-100 text-red-700 border-red-200'
      case 'error': return 'bg-red-100 text-red-700 border-red-200'
      default: return 'bg-gray-100 text-gray-500 border-gray-200'
    }
  }

  const freshnessLabel = (status: string) => {
    switch (status) {
      case 'fresh': return 'Actualizado'
      case 'stale': return 'Desactualizado'
      case 'stale_critical': return 'Critico'
      case 'error': return 'Error'
      case 'never_refreshed': return 'Nunca refrescado'
      default: return status
    }
  }

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

      {/* Freshness Bar */}
      {freshness && (
        <div className={`border rounded-lg p-3 flex items-center justify-between ${freshnessStatusColor(freshness.status)}`}>
          <div className="flex items-center gap-3">
            <div>
              <div className="text-xs font-semibold">Estado de datos: {freshnessLabel(freshness.status)}</div>
              <div className="text-[10px] opacity-70 mt-0.5">
                {freshness.last_refreshed_at
                  ? `Ultima actualizacion: ${new Date(freshness.last_refreshed_at).toLocaleString()}`
                  : 'Vista materializada nunca refrescada'}
              </div>
              {freshness.age_minutes !== null && (
                <div className="text-[10px] opacity-70">
                  Edad: {freshness.age_minutes < 1
                    ? `${Math.round(freshness.age_minutes * 60)}s`
                    : freshness.age_minutes < 60
                      ? `${Math.round(freshness.age_minutes)}min`
                      : `${(freshness.age_minutes / 60).toFixed(1)}h`}
                  {freshness.row_count !== null && ` | Filas: ${freshness.row_count}`}
                </div>
              )}
              {freshness.last_error && (
                <div className="text-[10px] text-red-600 mt-0.5">Error: {freshness.last_error}</div>
              )}
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="px-3 py-1.5 bg-white border rounded text-xs font-medium hover:bg-gray-50 disabled:opacity-50 whitespace-nowrap"
          >
            {refreshing ? 'Refrescando...' : 'Refrescar Vista'}
          </button>
        </div>
      )}

      {refreshError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded p-2 text-xs">{refreshError}</div>
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
          <div className={`text-2xl font-bold ${metrics?.missing_attribution_rate !== undefined ? integrityColor(100 - (metrics.missing_attribution_rate || 0)) : 'text-gray-700'}`}>
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

      {/* Operational Gaps Warning */}
      {gapsDiag && gapsDiag.total_operational_gaps > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <p className="text-xs text-amber-800">
            <span className="font-semibold">Atencion:</span> Los {gapsDiag.total_operational_gaps} operational gaps requieren diagnostico por ventana/origen antes de interpretarse como perdida real. Revisa el panel de diagnostico abajo.
          </p>
        </div>
      )}

      {/* Operational Gaps Diagnostic Panel */}
      {gapsDiag && gapsDiag.total_operational_gaps > 0 && (
        <div className="bg-white border rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Diagnostico de Operational Gaps</h3>
          <div className="text-xs text-gray-500 mb-3">{gapsDiag.note}</div>
          <div className="grid grid-cols-2 gap-2 text-xs mb-3">
            <Stat label="Total Gaps" value={gapsDiag.total_operational_gaps} color="red" />
            <Stat label="Drivers en Fuente" value={gapsDiag.total_source_drivers} color="gray" />
          </div>
          <div className="text-[10px] text-gray-400 mb-2">Desglose:</div>
          <div className="space-y-1">
            {gapsDiag.breakdown.map((b, i) => (
              <div key={i} className="flex justify-between items-center text-xs py-1 border-b border-gray-50">
                <span className="text-gray-600 truncate max-w-[70%]" title={b.description}>{b.label.replace(/_/g, ' ')}</span>
                <span className="font-medium text-gray-800">{b.count.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detailed stats */}
      <div className="grid grid-cols-2 gap-4">
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
      <span className={`font-bold ${m[color] || 'text-gray-700'}`}>{value.toLocaleString()}</span>
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
