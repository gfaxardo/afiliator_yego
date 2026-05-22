import { useEffect, useState, useCallback } from 'react'
import {
  getHealthSummary,
  getHealthCohorts,
  getHealthSources,
  getHealthJobs,
  refreshHealthRegistry,
  type HealthSummary,
  type CohortHealthResponse,
  type SourceHealthResponse,
  type JobsHealthResponse,
} from '../../api/scoutLiq'

const DEFAULT_WEEKS = 4

interface PanelState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

function usePanel<T>(fetcher: () => Promise<T>, deps: any[] = []): PanelState<T> & { reload: () => void } {
  const [state, setState] = useState<PanelState<T>>({ data: null, loading: true, error: null })
  const [trigger, setTrigger] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState(prev => ({ ...prev, loading: true, error: null }))
    fetcher()
      .then(data => { if (!cancelled) setState({ data, loading: false, error: null }) })
      .catch((err: any) => {
        if (!cancelled) setState({ data: null, loading: false, error: (err as any)?.message || String(err) })
      })
    return () => { cancelled = true }
  }, [...deps, trigger])

  return { ...state, reload: () => setTrigger(t => t + 1) }
}

export default function HealthDashboardView() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [weeksLimit, setWeeksLimit] = useState<number>(DEFAULT_WEEKS)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null)
  const [refreshOk, setRefreshOk] = useState<boolean | null>(null)

  const summary = usePanel(() => getHealthSummary(), [])
  const cohorts = usePanel(() => getHealthCohorts(weeksLimit, statusFilter || undefined), [weeksLimit, statusFilter])
  const sources = usePanel(() => getHealthSources(), [])
  const jobs = usePanel(() => getHealthJobs(), [])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    setRefreshMsg(null)
    setRefreshOk(null)
    try {
      const result = await refreshHealthRegistry()
      const score = result.score?.score ?? '?'
      const newEvents = result.events_detected?.new_events ?? 0
      const resolved = result.events_resolved?.resolved_count ?? 0
      setRefreshMsg(`Score: ${score} | Eventos nuevos: ${newEvents} | Resueltos: ${resolved}`)
      setRefreshOk(true)
    } catch (err: any) {
      setRefreshMsg((err as any)?.message || String(err))
      setRefreshOk(false)
    } finally {
      setRefreshing(false)
      summary.reload()
      sources.reload()
      jobs.reload()
      cohorts.reload()
    }
  }, [summary, sources, jobs, cohorts])

  if (summary.loading && !summary.data) return <div className="p-6 text-gray-400 text-sm">Cargando salud de datos...</div>

  const hasAnyError = summary.error || cohorts.error || sources.error || jobs.error

  return (
    <div className="space-y-4">
      {hasAnyError && (
        <div className="bg-amber-50 border border-amber-200 rounded p-3 text-amber-700 text-xs">
          Algunos paneles no estan disponibles. El dashboard sigue funcionando con los datos disponibles.
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">Salud de Data</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">
            Evaluado: {summary.data?.evaluated_at || '—'}
          </span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-xs px-3 py-1 rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50 disabled:cursor-wait"
          >
            {refreshing ? 'Actualizando...' : 'Actualizar diagnostico'}
          </button>
        </div>
      </div>

      {refreshMsg && (
        <div className={`text-xs px-3 py-1.5 rounded border ${
          refreshOk ? 'border-green-200 bg-green-50 text-green-700' : 'border-red-200 bg-red-50 text-red-700'
        }`}>
          {refreshOk ? 'Diagnostico actualizado:' : 'Error al actualizar:'} {refreshMsg}
        </div>
      )}

      {/* ── A. RESUMEN EJECUTIVO ── */}
      {summary.error ? (
        <ErrorCard title="Resumen Ejecutivo" message={summary.error} />
      ) : summary.data && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <StatusCard
            label="Fuente Operativa"
            status={summary.data.sections.source.status}
            detail={summary.data.sections.source.reason_text}
            lag={summary.data.sections.source.data_lag_days}
          />
          <StatusCard
            label="Carga Scouts"
            status={summary.data.sections.scouts.status}
            detail={summary.data.sections.scouts.reason_text}
            metric={summary.data.sections.scouts.coverage_pct != null ? `${summary.data.sections.scouts.coverage_pct}%` : undefined}
          />
          <StatusCard
            label="Cohortes 7D"
            status={summary.data.sections.cohorts.status}
            detail={summary.data.sections.cohorts.reason_text}
            metric={`W:${summary.data.sections.cohorts.warning_count ?? 0} B:${summary.data.sections.cohorts.blocked_count ?? 0}`}
          />
          <StatusCard
            label="Jobs"
            status={summary.data.sections.jobs.status}
            detail={summary.data.sections.jobs.reason_text}
          />
          <StatusCard
            label="Estado Global"
            status={summary.data.global_status}
            detail={(summary.data.alerts?.length ?? 0) > 0 ? `${summary.data.alerts.length} alertas` : 'Sin alertas'}
          />
        </div>
      )}

      {/* ── ALERTAS ── */}
      {summary.data && (summary.data.alerts?.length ?? 0) > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Alertas Activas ({summary.data.alerts.length})
          </h3>
          <div className="space-y-1">
            {summary.data.alerts.map((a, i) => (
              <div
                key={i}
                className={`text-xs px-2 py-1 rounded border ${
                  a.severity === 'BLOCKED'
                    ? 'border-red-200 bg-red-50 text-red-700'
                    : 'border-yellow-200 bg-yellow-50 text-yellow-700'
                }`}
              >
                <span className="font-mono text-[10px] opacity-60 mr-1">[{a.source}]</span>
                {a.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── COHORTES ── */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Cohortes ({cohorts.data?.total_cohorts_visible ?? 0})
          </h3>
          <div className="flex items-center gap-2">
            <select
              value={weeksLimit}
              onChange={e => setWeeksLimit(Number(e.target.value))}
              className="border border-gray-200 rounded px-2 py-0.5 text-xs bg-white"
              title="Semanas a mostrar"
            >
              <option value={4}>4 semanas</option>
              <option value={8}>8 semanas</option>
              <option value={12}>12 semanas</option>
            </select>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="border border-gray-200 rounded px-2 py-0.5 text-xs bg-white"
            >
              <option value="">Todas</option>
              <option value="BLOCKED">Criticas</option>
              <option value="WARNING">Advertencias</option>
              <option value="OK">Saludables</option>
            </select>
          </div>
        </div>
        {weeksLimit >= 12 && (
          <div className="px-4 py-1 text-[10px] text-amber-600 bg-amber-50 border-b border-amber-100">
            Vista extendida: puede tardar mas con 12 semanas
          </div>
        )}
        {cohorts.error ? (
          <div className="p-4 text-xs text-red-600 bg-red-50">Cohortes no disponibles: {cohorts.error}</div>
        ) : cohorts.loading ? (
          <div className="p-4 text-xs text-gray-400">Cargando cohortes...</div>
        ) : cohorts.data && (cohorts.data.cohorts?.length ?? 0) > 0 ? (
          <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1.5">Cohorte</th>
                  <th className="text-left px-2 py-1.5">Rango</th>
                  <th className="text-right px-2 py-1.5">Total</th>
                  <th className="text-right px-2 py-1.5">C/Scout</th>
                  <th className="text-right px-2 py-1.5">S/Scout</th>
                  <th className="text-right px-2 py-1.5">Activ</th>
                  <th className="text-right px-2 py-1.5">5V/7D</th>
                  <th className="text-right px-2 py-1.5">5V/14D</th>
                  <th className="text-right px-2 py-1.5">Pag</th>
                  <th className="text-center px-2 py-1.5">7D Mad</th>
                  <th className="text-center px-2 py-1.5">14D Mad</th>
                  <th className="text-center px-2 py-1.5">Estado</th>
                  <th className="text-left px-2 py-1.5">Motivo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {cohorts.data.cohorts.map(c => (
                  <tr key={c.cohort_key} className="hover:bg-blue-50/30">
                    <td className="px-2 py-1 font-medium text-gray-800">{c.cohort_label}</td>
                    <td className="px-2 py-1 text-gray-500 font-mono text-[10px]">
                      {c.hire_date_from ?? '—'} → {c.hire_date_to ?? '—'}
                    </td>
                    <td className="px-2 py-1 text-right font-mono">{c.total_drivers ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono text-green-700">{c.with_scout ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono text-red-600">{c.without_scout ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono">{c.activated_1_trip ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono font-bold text-blue-700">{c.converted_5v7d ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono">{c.converted_5v14d ?? 0}</td>
                    <td className="px-2 py-1 text-right font-mono text-teal-600">{c.paid ?? 0}</td>
                    <td className="px-2 py-1 text-center">
                      {c.expected_7d_matured ? (
                        <span className="text-green-600 font-bold">SI</span>
                      ) : (
                        <span className="text-gray-300">·</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-center">
                      {c.expected_14d_matured ? (
                        <span className="text-blue-600 font-bold">SI</span>
                      ) : (
                        <span className="text-gray-300">·</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-center">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-2 py-1 text-gray-500 max-w-[200px] truncate" title={c.reason_text ?? ''}>
                      {c.reason_text ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-4 text-xs text-gray-400">Sin cohortes detectadas</div>
        )}
      </div>

      {/* ── FUENTE DETALLE ── */}
      {sources.error ? (
        <ErrorCard title="Detalle Fuente Operativa" message={sources.error} />
      ) : sources.data && (
        <details className="bg-white border border-gray-200 rounded-lg p-4">
          <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer">
            Detalle Fuente Operativa
          </summary>
          <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <MetricItem label="Total drivers" value={sources.data.metrics?.total_drivers ?? null} />
            <MetricItem label="Max hire_date" value={sources.data.metrics?.max_hire_date ?? null} />
            <MetricItem label="Min hire_date" value={sources.data.metrics?.min_hire_date ?? null} />
            <MetricItem label="Data Lag" value={sources.data.data_lag_days != null ? `${sources.data.data_lag_days} dias` : '—'} />
            <MetricItem label="Ultima carga (1d)" value={sources.data.metrics?.drivers_last_1d ?? null} />
            <MetricItem label="Ultima carga (3d)" value={sources.data.metrics?.drivers_last_3d ?? null} />
            <MetricItem label="Ultima carga (7d)" value={sources.data.metrics?.drivers_last_7d ?? null} />
            <MetricItem label="Last updated_at" value={sources.data.metrics?.last_updated_at || '—'} />
          </div>
        </details>
      )}

      {/* ── JOBS DETALLE ── */}
      {jobs.error ? (
        <ErrorCard title="Jobs / Procesos" message={jobs.error} />
      ) : jobs.data && (jobs.data.jobs?.length ?? 0) > 0 && (
        <details className="bg-white border border-gray-200 rounded-lg p-4">
          <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer">
            Jobs / Procesos
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-gray-400 uppercase">
                  <th className="text-left pb-1 pr-2">Job</th>
                  <th className="text-left pb-1 px-2">Tipo</th>
                  <th className="text-left pb-1 px-2">Ultima ejecucion</th>
                  <th className="text-center pb-1 px-2">Gap (h)</th>
                  <th className="text-center pb-1 pl-2">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {jobs.data.jobs.map((j, i) => (
                  <tr key={i}>
                    <td className="py-1 pr-2 font-medium text-gray-800">{j.job_name}</td>
                    <td className="py-1 px-2 text-gray-500">{j.type}</td>
                    <td className="py-1 px-2 font-mono text-[10px] text-gray-500">{j.last_run || '—'}</td>
                    <td className="py-1 px-2 text-center font-mono">{j.gap_hours != null ? Math.round(j.gap_hours) : '—'}</td>
                    <td className="py-1 pl-2 text-center"><StatusBadge status={j.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {jobs.data.note && <div className="mt-2 text-[10px] text-gray-400 italic">{jobs.data.note}</div>}
        </details>
      )}
    </div>
  )
}

function ErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-3">
      <div className="text-xs font-semibold text-red-700 mb-1">{title} no disponible</div>
      <div className="text-[11px] text-red-500 font-mono truncate" title={message}>{message}</div>
    </div>
  )
}

function StatusCard({
  label,
  status,
  detail,
  lag,
  metric,
}: {
  label: string
  status: string
  detail: string
  lag?: number | null
  metric?: string
}) {
  const colorMap: Record<string, string> = {
    OK: 'border-green-300 bg-green-50',
    WARNING: 'border-yellow-300 bg-yellow-50',
    BLOCKED: 'border-red-300 bg-red-50',
    INFO: 'border-blue-300 bg-blue-50',
    UNKNOWN: 'border-gray-300 bg-gray-50',
    ERROR: 'border-red-300 bg-red-50',
  }
  const borderColor = colorMap[status] || 'border-gray-200 bg-white'
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${borderColor}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</span>
        <StatusBadge status={status} />
      </div>
      <div className="text-[11px] text-gray-600 leading-tight line-clamp-2" title={detail || ''}>
        {detail || '—'}
      </div>
      {lag != null && (
        <div className="mt-1 text-[10px] font-mono text-gray-400" title={`${lag * 1440} minutos`}>
          Lag: {lag} dias
        </div>
      )}
      {metric && (
        <div className="mt-1 text-[10px] font-mono text-gray-400">{metric}</div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    OK: 'bg-green-100 text-green-700',
    WARNING: 'bg-yellow-100 text-yellow-700',
    BLOCKED: 'bg-red-100 text-red-700',
    INFO: 'bg-blue-100 text-blue-700',
    UNKNOWN: 'bg-gray-100 text-gray-500',
    ERROR: 'bg-red-100 text-red-700',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${colorMap[status] || 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}

function MetricItem({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <span className="text-[10px] text-gray-400">{label}</span>
      <div className="font-mono text-xs text-gray-700">{value ?? '—'}</div>
    </div>
  )
}
