import { useEffect, useState, useCallback } from 'react'
import {
  getHealthPipeline,
  recomputeDerived,
  getAlertsDetail,
  getHealthUnassignedDrivers,
  getBlockedCohorts,
  getUnassignedDriversCsvUrl,
  getBlockedCohortsCsvUrl,
  getAlertsCsvUrl,
  type PipelineSummaryResponse,
  type OperationalReadiness,
  type AlertsDetailResponse,
  type UnassignedDriversResponse,
  type BlockedCohortsResponse,
  type RecomputeStep,
} from '../../api/scoutLiq'

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
      .catch((err: any) => { if (!cancelled) setState({ data: null, loading: false, error: (err as any)?.message || String(err) }) })
    return () => { cancelled = true }
  }, [...deps, trigger])
  return { ...state, reload: () => setTrigger(t => t + 1) }
}

export default function HealthDashboardView() {
  const [recomputing, setRecomputing] = useState(false)
  const [recomputeResult, setRecomputeResult] = useState<RecomputeStep[] | null>(null)
  const [recomputeMsg, setRecomputeMsg] = useState<string | null>(null)
  const [recomputeOk, setRecomputeOk] = useState<boolean | null>(null)
  const [recomputeDuration, setRecomputeDuration] = useState<number | null>(null)
  const [expandedAlert, setExpandedAlert] = useState<number | null>(null)
  const [showUnassigned, setShowUnassigned] = useState(false)
  const [showBlockedCohorts, setShowBlockedCohorts] = useState(false)

  const pipeline = usePanel(() => getHealthPipeline(), [])
  const alertsDetail = usePanel(() => getAlertsDetail(), [])
  const unassigned = usePanel(() => showUnassigned ? getHealthUnassignedDrivers(20, 0) : Promise.resolve(null), [showUnassigned])
  const blockedCohorts = usePanel(() => showBlockedCohorts ? getBlockedCohorts() : Promise.resolve(null), [showBlockedCohorts])

  const handleRecompute = useCallback(async () => {
    setRecomputing(true)
    setRecomputeResult(null); setRecomputeMsg(null); setRecomputeOk(null); setRecomputeDuration(null)
    try {
      const result = await recomputeDerived()
      setRecomputeResult(result.steps || [])
      setRecomputeDuration(result.duration_ms)
      setRecomputeOk(result.status !== 'failed')
      setRecomputeMsg(result.status === 'success' ? 'Derivados recalculados correctamente' : `Completado: ${result.status}`)
    } catch (err: any) {
      setRecomputeMsg((err as any)?.message || String(err))
      setRecomputeOk(false)
    } finally {
      setRecomputing(false)
      pipeline.reload()
      alertsDetail.reload()
    }
  }, [pipeline, alertsDetail])

  if (pipeline.loading && !pipeline.data) return <div className="p-6 text-gray-400 text-sm">Cargando salud de datos...</div>

  const d = pipeline.data
  const ad = alertsDetail.data
  const rd = d?.operational_readiness

  return (
    <div className="space-y-4">
      {/* Header + actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Salud de Data</h2>
          <div className="text-[10px] text-gray-400">
            Evaluado: {d?.evaluated_at || '-'}
            {d?.closed_day_expected && <span className="ml-2">| Dia cerrado: <span className="font-mono">{d.closed_day_expected}</span></span>}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          <button onClick={pipeline.reload} disabled={pipeline.loading}
            className="text-[10px] px-2 py-1 rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50">
            Actualizar
          </button>
          <button onClick={handleRecompute} disabled={recomputing}
            className="text-[10px] px-2 py-1 rounded border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">
            {recomputing ? 'Recalculando...' : 'Recalcular'}
          </button>
          <a href={getAlertsCsvUrl()} download
            className="text-[10px] px-2 py-1 rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 no-underline">
            Alertas CSV
          </a>
          <a href={getUnassignedDriversCsvUrl()} download
            className="text-[10px] px-2 py-1 rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 no-underline">
            Sin Scout CSV
          </a>
          <a href={getBlockedCohortsCsvUrl()} download
            className="text-[10px] px-2 py-1 rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 no-underline">
            Cohortes CSV
          </a>
        </div>
      </div>

      {/* Recompute result */}
      {recomputeMsg && (
        <div className={`text-xs px-3 py-1.5 rounded border ${
          recomputeOk ? 'border-green-200 bg-green-50 text-green-700' : 'border-red-200 bg-red-50 text-red-700'
        }`}>
          {recomputeOk ? 'OK:' : 'Error:'} {recomputeMsg}
          {recomputeDuration != null && <span className="ml-2 opacity-60">({recomputeDuration}ms)</span>}
        </div>
      )}

      {/* Operational Readiness */}
      {rd && (
        <div className={`rounded-lg border-2 p-4 ${
          rd.can_approve_payments ? 'border-green-300 bg-green-50' :
          rd.can_create_cutoff ? 'border-yellow-300 bg-yellow-50' :
          'border-red-300 bg-red-50'
        }`}>
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-2 text-gray-600">Readiness Operativo</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
            <ReadinessItem label="Crear corte" ok={rd.can_create_cutoff} />
            <ReadinessItem label="Preview calculo" ok={rd.can_calculate_preview} />
            <ReadinessItem label="Aprobar pagos" ok={rd.can_approve_payments} />
            <ReadinessItem label="Asignar scouts" ok={rd.can_assign_scouts} />
          </div>
          {rd.blocking_domains.length > 0 && (
            <div className="text-[10px] text-red-600 mb-2">
              Dominios bloqueantes: {rd.blocking_domains.join(', ')}
            </div>
          )}
          {!rd.can_approve_payments && (
            <div className="text-xs text-red-700 font-medium bg-red-100 border border-red-200 rounded px-2 py-1">
              Sistema bloqueado para aprobacion de pagos. Preview permitido solo para diagnostico. Causas: {rd.blocking_domains.join(', ')}.
            </div>
          )}
          {rd.can_approve_payments && (
            <div className="text-xs text-green-700 font-medium bg-green-100 border border-green-200 rounded px-2 py-1">
              Sistema listo para operar. Se puede crear cortes, calcular y aprobar pagos.
            </div>
          )}
          {rd.next_actions.length > 0 && (
            <div className="mt-2">
              <h4 className="text-[10px] font-semibold text-gray-500 uppercase mb-1">Proximas acciones</h4>
              <div className="space-y-1">
                {rd.next_actions.map((na, i) => (
                  <div key={i} className={`text-xs border rounded px-2 py-1 flex items-start gap-2 ${
                    na.blocking ? 'border-red-200 bg-red-50/50' : 'border-yellow-200 bg-yellow-50/50'
                  }`}>
                    <span className={`shrink-0 mt-0.5 px-1 rounded text-[10px] font-mono ${
                      na.blocking ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                    }`}>{na.owner}</span>
                    <div>
                      <div className="text-gray-800">{na.action}</div>
                      <div className="text-[10px] text-gray-500">{na.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Status Cards */}
      {d && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          <StatusCard label="Fuente" status={d.source_operational.status} detail={d.source_operational.message}
            lag={d.source_operational.lag_days} />
          <StatusCard label="Derivados" status={d.derived_pipeline.status} detail={d.derived_pipeline.message} />
          <StatusCard label="Matching" status={d.matching.status}
            metric={`${d.matching.assignment_coverage_pct}%`} />
          <StatusCard label="Cohortes" status={d.cohorts_summary.global_status}
            metric={`W:${d.cohorts_summary.warning_count} B:${d.cohorts_summary.blocked_count}`} />
          <StatusCard label="Jobs" status={d.jobs.status}
            detail={d.jobs.missing_jobs?.length ? `${d.jobs.missing_jobs.length} pend` : 'Al dia'} />
          <StatusCard label="Global" status={d.overall_status}
            detail={ad ? `${ad.blocking_count}/${ad.total_alerts} bloqueantes` : `${d.alerts?.length} alertas`} />
        </div>
      )}

      {/* Alerts accordion */}
      {ad && ad.alerts && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Alertas ({ad.total_alerts}) — {ad.blocking_count} bloqueantes
            </h3>
            <div className="flex items-center gap-1 text-[10px] flex-wrap">
              {Object.entries(ad.summary_by_category || {}).map(([cat, info]) => (
                <span key={cat} className={`px-1 py-0.5 rounded ${info.blocking > 0 ? 'bg-red-50 text-red-600' : 'bg-yellow-50 text-yellow-600'}`}>
                  {cat}: {info.count}
                </span>
              ))}
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {ad.alerts.map((a, i) => (
              <div key={i} className={expandedAlert === i ? 'bg-blue-50/30' : ''}>
                <div className="flex items-start gap-2 px-4 py-2 cursor-pointer hover:bg-gray-50"
                  onClick={() => setExpandedAlert(expandedAlert === i ? null : i)}>
                  <span className={`shrink-0 mt-0.5 px-1 rounded text-[10px] font-mono ${
                    a.severity === 'blocked' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                  }`}>{a.severity.toUpperCase()}</span>
                  <span className="shrink-0 px-1 rounded text-[10px] font-mono bg-gray-100 text-gray-500">{a.category}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-gray-800">{a.message}</div>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                      <span className="text-gray-400">{a.owner}</span>
                      {a.is_blocking && <span className="text-red-500 font-medium">BLOQUEANTE</span>}
                    </div>
                  </div>
                  <span className="text-[10px] text-gray-300">{expandedAlert === i ? '▲' : '▼'}</span>
                </div>
                {expandedAlert === i && (
                  <div className="px-4 pb-3 space-y-1.5 text-xs">
                    <div><span className="text-[10px] text-gray-400 font-semibold">CAUSA:</span><span className="text-gray-700 ml-1">{a.root_cause_candidate || '-'}</span></div>
                    <div><span className="text-[10px] text-gray-400 font-semibold">IMPACTO:</span><span className="text-gray-700 ml-1">{a.impact || '-'}</span></div>
                    <div><span className="text-[10px] text-gray-400 font-semibold">ACCION:</span><span className="text-indigo-700 font-medium ml-1">{a.recommended_action || '-'}</span></div>
                    {a.evidence && Object.keys(a.evidence).length > 0 && (
                      <div className="bg-gray-50 rounded p-2 mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] font-mono">
                        {Object.entries(a.evidence).map(([k, v]) => (
                          <div key={k} className="flex justify-between"><span className="text-gray-400">{k}:</span><span className="text-gray-700">{String(v ?? '-')}</span></div>
                        ))}
                      </div>
                    )}
                    {a.category === 'matching_gap' && (
                      <button onClick={() => setShowUnassigned(!showUnassigned)} className="text-[10px] text-indigo-600 underline mt-1">
                        {showUnassigned ? 'Ocultar drivers' : 'Ver drivers sin scout'}
                      </button>
                    )}
                    {a.category === 'workflow_gap' && (
                      <button onClick={() => setShowBlockedCohorts(!showBlockedCohorts)} className="text-[10px] text-indigo-600 underline mt-1">
                        {showBlockedCohorts ? 'Ocultar cohortes' : 'Ver cohortes bloqueadas'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Unassigned drivers */}
      {showUnassigned && unassigned.data && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Drivers sin scout ({unassigned.data.total_unassigned})</h3>
            <button onClick={() => setShowUnassigned(false)} className="text-[10px] text-gray-400">Cerrar</button>
          </div>
          <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1">Driver ID</th>
                  <th className="text-left px-2 py-1">Hire Date</th>
                  <th className="text-left px-2 py-1">Origen</th>
                  <th className="text-left px-2 py-1">LCA Cabinet</th>
                  <th className="text-left px-2 py-1">LCA Fleet</th>
                  <th className="text-left px-2 py-1">Accion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {unassigned.data.items.map((d, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 font-mono text-gray-800">{d.driver_id?.slice(0,12)}</td>
                    <td className="px-2 py-1 font-mono text-gray-500">{d.hire_date}</td>
                    <td className="px-2 py-1 text-gray-500">{d.origen}</td>
                    <td className="px-2 py-1 font-mono text-[10px] text-gray-400">{d.lead_created_at_cabinet?.slice(0,10) || '-'}</td>
                    <td className="px-2 py-1 font-mono text-[10px] text-gray-400">{d.lead_created_at_fleet?.slice(0,10) || '-'}</td>
                    <td className="px-2 py-1 text-[10px] text-indigo-600">{d.suggested_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Blocked cohorts */}
      {showBlockedCohorts && blockedCohorts.data && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Cohortes con problemas ({blockedCohorts.data.total_blocked_or_warning})</h3>
            <button onClick={() => setShowBlockedCohorts(false)} className="text-[10px] text-gray-400">Cerrar</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-2 py-1">Cohorte</th>
                  <th className="text-left px-2 py-1">Rango</th>
                  <th className="text-right px-2 py-1">Total</th>
                  <th className="text-right px-2 py-1">C/Scout</th>
                  <th className="text-right px-2 py-1">5V7D</th>
                  <th className="text-center px-2 py-1">7D Mad</th>
                  <th className="text-center px-2 py-1">Cutoff</th>
                  <th className="text-center px-2 py-1">Estado</th>
                  <th className="text-left px-2 py-1">Problema</th>
                  <th className="text-left px-2 py-1">Accion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {blockedCohorts.data.cohorts.map((c, i) => (
                  <tr key={i} className={c.is_blocking ? 'bg-red-50/30' : 'bg-yellow-50/20'}>
                    <td className="px-2 py-1 font-medium text-gray-800">{c.cohort}</td>
                    <td className="px-2 py-1 font-mono text-[10px] text-gray-500">{c.range}</td>
                    <td className="px-2 py-1 text-right font-mono">{c.total_drivers}</td>
                    <td className="px-2 py-1 text-right font-mono text-green-700">{c.assigned}</td>
                    <td className="px-2 py-1 text-right font-mono text-blue-700">{c.converted_5v_7d}</td>
                    <td className="px-2 py-1 text-center">{c.is_7d_mature ? <span className="text-green-600">SI</span> : '·'}</td>
                    <td className="px-2 py-1 text-center">{c.cutoff_exists ? <span className="text-green-600">{c.cutoff_status}</span> : <span className="text-red-400">NO</span>}</td>
                    <td className="px-2 py-1 text-center"><StatusBadge status={c.status} /></td>
                    <td className="px-2 py-1 text-[10px] text-red-600 font-medium">{c.main_problem}</td>
                    <td className="px-2 py-1 text-[10px] text-indigo-600">{c.suggested_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cohorts summary */}
      {d && d.cohorts && d.cohorts.length > 0 && (
        <details className="bg-white border border-gray-200 rounded-lg p-4">
          <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer">Cohortes ({d.cohorts.length})</summary>
          <div className="mt-2 overflow-x-auto max-h-[50vh] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1.5">Cohorte</th>
                  <th className="text-left px-2 py-1.5">Rango</th>
                  <th className="text-right px-2 py-1.5">Total</th>
                  <th className="text-right px-2 py-1.5">C/Sc</th>
                  <th className="text-right px-2 py-1.5">S/Sc</th>
                  <th className="text-right px-2 py-1.5">5V7D</th>
                  <th className="text-center px-2 py-1.5">Mad</th>
                  <th className="text-center px-2 py-1.5">Cutoff</th>
                  <th className="text-center px-2 py-1.5">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {d.cohorts.map(c => (
                  <tr key={c.cohort_key} className="hover:bg-blue-50/30">
                    <td className="px-2 py-1 font-medium">{c.cohort}</td>
                    <td className="px-2 py-1 font-mono text-[10px] text-gray-500">{c.range}</td>
                    <td className="px-2 py-1 text-right font-mono">{c.total}</td>
                    <td className="px-2 py-1 text-right font-mono text-green-700">{c.assigned}</td>
                    <td className="px-2 py-1 text-right font-mono text-red-600">{c.unassigned}</td>
                    <td className="px-2 py-1 text-right font-mono text-blue-700">{c.converted_5v_7d}</td>
                    <td className="px-2 py-1 text-center">{c.is_7d_mature ? <span className="text-green-600">SI</span> : '·'}</td>
                    <td className="px-2 py-1 text-center">{c.cutoff_exists ? <span className="text-green-600 text-[10px]">{c.cutoff_status || 'SI'}</span> : <span className="text-red-400">NO</span>}</td>
                    <td className="px-2 py-1 text-center"><StatusBadge status={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}

function ReadinessItem({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className={`rounded border px-2 py-1.5 text-center ${ok ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
      <div className={`text-lg ${ok ? '' : 'opacity-50'}`}>{ok ? '✓' : '✗'}</div>
      <div className={`text-[10px] font-medium ${ok ? 'text-green-700' : 'text-red-500'}`}>{label}</div>
    </div>
  )
}

function StatusCard({
  label, status, detail, lag, metric,
}: { label: string; status: string; detail?: string; lag?: number | null; metric?: string }) {
  const cm: Record<string, string> = {
    ok: 'border-green-300 bg-green-50', warning: 'border-yellow-300 bg-yellow-50',
    blocked: 'border-red-300 bg-red-50', OK: 'border-green-300 bg-green-50',
    WARNING: 'border-yellow-300 bg-yellow-50', BLOCKED: 'border-red-300 bg-red-50',
    INFO: 'border-blue-300 bg-blue-50', UNKNOWN: 'border-gray-300 bg-gray-50',
  }
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${cm[status] || 'border-gray-200 bg-white'}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</span>
        <StatusBadge status={status} />
      </div>
      {detail && <div className="text-[11px] text-gray-600 leading-tight line-clamp-2" title={detail}>{detail}</div>}
      {lag != null && <div className="mt-1 text-[10px] font-mono text-gray-400">Lag: {lag}d</div>}
      {metric && <div className="mt-1 text-[10px] font-mono text-gray-400">{metric}</div>}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const cm: Record<string, string> = {
    ok: 'bg-green-100 text-green-700', warning: 'bg-yellow-100 text-yellow-700',
    blocked: 'bg-red-100 text-red-700', OK: 'bg-green-100 text-green-700',
    WARNING: 'bg-yellow-100 text-yellow-700', BLOCKED: 'bg-red-100 text-red-700',
    INFO: 'bg-blue-100 text-blue-700', UNKNOWN: 'bg-gray-100 text-gray-500',
  }
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${cm[status] || 'bg-gray-100 text-gray-500'}`}>{status.toUpperCase()}</span>
}
