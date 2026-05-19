import { useState, useEffect, useCallback } from 'react'
import {
  getOperationSummary, getOperationFilters, getAffiliations, getAffiliationDetail,
  type OperationSummary, type OperationFilters, type AffiliationRow, type AffiliationsResponse
} from '../../api/scoutLiq'

const STATUS_COLORS: Record<string, string> = {
  attribution_ready: 'bg-green-100 text-green-700',
  attribution_manual_review: 'bg-yellow-100 text-yellow-700',
  attribution_rejected_missing_scout_and_driver: 'bg-red-100 text-red-700',
  payment_financial_ready: 'bg-blue-100 text-blue-700',
  payment_financial_not_applicable_no_amount: 'bg-gray-100 text-gray-500',
  payment_financial_manual_review_no_scout: 'bg-yellow-100 text-yellow-700',
  payment_blocking_ready: 'bg-purple-100 text-purple-700',
  payment_blocking_manual_review_no_driver: 'bg-yellow-100 text-yellow-700',
  payment_blocking_manual_review_no_scout: 'bg-yellow-100 text-yellow-700',
  payment_blocking_duplicate: 'bg-blue-100 text-blue-700',
  payment_blocking_not_applicable_no_amount: 'bg-gray-100 text-gray-500',
}

const BLOCKING_COLORS: Record<string, string> = {
  'Bloquea': 'bg-purple-100 text-purple-700',
  'No bloquea': 'bg-yellow-100 text-yellow-700',
  'Ya registrado': 'bg-blue-100 text-blue-700',
  'Duplicado': 'bg-red-100 text-red-700',
  'Sin driver': 'bg-yellow-100 text-yellow-700',
  'Sin scout': 'bg-yellow-100 text-yellow-700',
  'N/A': 'bg-gray-100 text-gray-400',
  'Pendiente': 'bg-gray-100 text-gray-500',
}

const ALERT_BADGE: Record<string, string> = {
  ok: 'bg-green-100 text-green-700',
  warning: 'bg-yellow-100 text-yellow-700',
  critical: 'bg-red-100 text-red-700',
}

function shortAttr(s: string | null): string {
  if (!s) return '-'
  if (s === 'attribution_ready') return 'OK'
  if (s === 'attribution_manual_review') return 'Review'
  if (s.includes('rejected')) return 'Rechazado'
  return s.replace('attribution_', '').slice(0, 8)
}

function shortFin(s: string | null): string {
  if (!s) return '-'
  if (s === 'payment_financial_ready') return 'Pago'
  if (s.includes('not_applicable')) return 'N/A'
  if (s.includes('manual_review')) return 'Review'
  return s.replace('payment_financial_', '').slice(0, 8)
}

export default function OperationView() {
  const [summary, setSummary] = useState<OperationSummary | null>(null)
  const [filters, setFilters] = useState<OperationFilters | null>(null)
  const [data, setData] = useState<AffiliationsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [kpiLoading, setKpiLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters — initialized empty, set when filters load
  const [weekIso, setWeekIso] = useState('')
  const [scoutId, setScoutId] = useState('')
  const [origin, setOrigin] = useState('')
  const [alertLevel, setAlertLevel] = useState('')
  const [onlyManualReview, setOnlyManualReview] = useState(false)
  const [onlyWithoutDriver, setOnlyWithoutDriver] = useState(false)
  const [onlyPaid, setOnlyPaid] = useState(false)
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  // Detail drawer
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Load filters first (to get default week)
  useEffect(() => {
    (async () => {
      try {
        const f = await getOperationFilters()
        setFilters(f)
        setWeekIso(f.default_week_iso || '')
      } catch (e: any) {
        setError('Error al cargar filtros')
      }
    })()
  }, [])

  // Load KPI summary (reacts to filter changes)
  const loadSummary = useCallback(async () => {
    setKpiLoading(true)
    try {
      const p: Record<string, any> = {}
      if (weekIso) p.week_iso = weekIso
      if (scoutId) p.scout_id = scoutId
      if (origin) p.origin = origin
      if (onlyManualReview) p.only_manual_review = true
      if (onlyPaid) p.only_paid = true
      if (onlyWithoutDriver) p.only_without_driver = true
      setSummary(await getOperationSummary(Object.keys(p).length ? p : undefined as any))
    } catch { /* ignore */ }
    finally { setKpiLoading(false) }
  }, [weekIso, scoutId, origin, onlyManualReview, onlyPaid, onlyWithoutDriver])

  // Load grid data
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, any> = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
      if (weekIso) params.week_iso = weekIso
      if (scoutId) params.scout_id = scoutId
      if (origin) params.origin = origin
      if (alertLevel) params.alert_level = alertLevel
      if (onlyManualReview) params.only_manual_review = true
      if (onlyWithoutDriver) params.only_without_driver = true
      if (onlyPaid) params.only_paid = true
      const d = await getAffiliations(params)
      setData(d)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Error')
    } finally {
      setLoading(false)
    }
  }, [weekIso, scoutId, origin, alertLevel, onlyManualReview, onlyWithoutDriver, onlyPaid, page])

  useEffect(() => { loadData(); loadSummary() }, [loadData, loadSummary])

  async function openDetail(rowId: number) {
    setSelectedId(rowId)
    setDetailLoading(true)
    try { setDetail(await getAffiliationDetail(rowId)) }
    catch { setDetail(null) }
    finally { setDetailLoading(false) }
  }

  function clearFilters() {
    setWeekIso(filters?.default_week_iso || '')
    setScoutId(''); setOrigin(''); setAlertLevel('')
    setOnlyManualReview(false); setOnlyWithoutDriver(false); setOnlyPaid(false)
    setPage(0)
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const noDataCurrentWeek = filters && !filters.has_data_for_current_week && weekIso === filters.current_iso_week && data && data.total === 0

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Operacion de Afiliaciones</h2>
          {summary && (
            <p className="text-xs text-gray-400 mt-0.5">
              {summary.scope_type === 'selected_week'
                ? `Resumen de ${summary.scope_label}`
                : 'Resumen de todas las semanas'}
              {data ? ` \u00b7 ${data.total} registros` : ''}
            </p>
          )}
        </div>
        {filters && !filters.has_data_for_current_week && (
          <button
            onClick={() => {
              setWeekIso(filters.latest_iso_week_with_data || weekIso)
              setPage(0)
            }}
            className="text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-3 py-1 rounded border border-blue-200"
          >
            Ver ultima semana con data: {filters.latest_iso_week_with_data_label}
          </button>
        )}
      </div>

      {/* KPIs */}
      {summary && (
        <div className="grid grid-cols-9 gap-2">
          <KpiCard label="Afiliaciones" value={summary.total_affiliations} />
          <KpiCard label="Con driver" value={summary.total_with_driver} color="text-green-600" />
          <KpiCard label="Sin driver" value={summary.total_without_driver} color="text-yellow-600" />
          <KpiCard label="Con scout" value={summary.total_with_scout} />
          <KpiCard label="Manual review" value={summary.total_manual_review} color="text-orange-600" />
          <KpiCard label="Pagos" value={summary.total_paid_history} color="text-blue-600" />
          <KpiCard label="Monto" value={`S/ ${summary.total_paid_amount.toLocaleString()}`} color="text-blue-700" />
          <KpiCard label="Bloqueos" value={summary.total_blocks_future} color="text-purple-600" />
          <KpiCard label="Criticas" value={summary.total_alerts_critical} color={summary.total_alerts_critical > 0 ? 'text-red-600' : 'text-green-600'} />
        </div>
      )}

      {/* Empty state for current week */}
      {noDataCurrentWeek && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-700 flex items-center justify-between">
          <span>No hay afiliaciones en la semana actual ({filters?.current_iso_week_label}).</span>
          <button
            onClick={() => {
              setWeekIso(filters?.latest_iso_week_with_data || '')
              setPage(0)
            }}
            className="text-blue-600 hover:text-blue-800 font-medium underline text-xs"
          >
            Ir a {filters?.latest_iso_week_with_data_label}
          </button>
        </div>
      )}

      {/* Filters */}
      {filters && (
        <div className="flex flex-wrap gap-2 items-center bg-white rounded-lg border border-gray-200 px-3 py-2">
          <select value={weekIso} onChange={(e) => { setWeekIso(e.target.value); setPage(0) }}
            className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
            <option value="">Todas las semanas</option>
            {filters.weeks.map((w) => (
              <option key={w.label} value={`${w.year}-W${String(w.week).padStart(2, '0')}`}>{w.label}</option>
            ))}
          </select>

          <select value={scoutId} onChange={(e) => { setScoutId(e.target.value); setPage(0) }}
            className="border border-gray-200 rounded px-2 py-1 text-xs bg-white max-w-[180px]">
            <option value="">Todos los scouts</option>
            {filters.scouts.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>

          <select value={origin} onChange={(e) => { setOrigin(e.target.value); setPage(0) }}
            className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
            <option value="">Todos los origenes</option>
            {filters.origins.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>

          <select value={alertLevel} onChange={(e) => { setAlertLevel(e.target.value); setPage(0) }}
            className="border border-gray-200 rounded px-2 py-1 text-xs bg-white">
            <option value="">Todas las alertas</option>
            {filters.alert_types.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>

          <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
            <input type="checkbox" checked={onlyManualReview} onChange={(e) => { setOnlyManualReview(e.target.checked); setPage(0) }} className="rounded" />
            Manual review
          </label>
          <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
            <input type="checkbox" checked={onlyWithoutDriver} onChange={(e) => { setOnlyWithoutDriver(e.target.checked); setPage(0) }} className="rounded" />
            Sin driver
          </label>
          <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
            <input type="checkbox" checked={onlyPaid} onChange={(e) => { setOnlyPaid(e.target.checked); setPage(0) }} className="rounded" />
            Solo pagados
          </label>

          <button onClick={clearFilters} className="text-xs text-blue-600 hover:text-blue-800 ml-auto">
            Limpiar filtros
          </button>
        </div>
      )}

      {/* Error */}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">{error}</div>}

      {/* Grid */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Cargando...</div>
        ) : data && data.items.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">Sin resultados para los filtros actuales</div>
        ) : data ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">
                    <th className="px-3 py-1.5">Semana</th>
                    <th className="px-3 py-1.5">Hire date</th>
                    <th className="px-3 py-1.5">Driver</th>
                    <th className="px-3 py-1.5">Licencia</th>
                    <th className="px-3 py-1.5">Origen</th>
                    <th className="px-3 py-1.5">Scout</th>
                    <th className="px-3 py-1.5">Supervisor</th>
                    <th className="px-3 py-1.5 text-right">0-7</th>
                    <th className="px-3 py-1.5 text-right">8-14</th>
                    <th className="px-3 py-1.5">Atribucion</th>
                    <th className="px-3 py-1.5">Pago</th>
                    <th className="px-3 py-1.5">Bloqueo</th>
                    <th className="px-3 py-1.5 text-right">Monto</th>
                    <th className="px-3 py-1.5">Alertas</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.items.map((row: AffiliationRow) => (
                    <tr key={row.row_id} onClick={() => openDetail(row.row_id)}
                      className="hover:bg-blue-50/40 cursor-pointer transition-colors">
                      <td className="px-3 py-1 whitespace-nowrap">
                        <div className="font-mono text-[11px] font-medium">{row.iso_week_label}</div>
                        {row.iso_week_start && <div className="text-[10px] text-gray-400">{row.iso_week_start}–{row.iso_week_end}</div>}
                      </td>
                      <td className="px-3 py-1 whitespace-nowrap text-gray-500 font-mono text-[11px]">
                        {row.hire_date ? row.hire_date.slice(0, 10) : '-'}
                      </td>
                      <td className="px-3 py-1 max-w-[150px]">
                        <div className="font-medium text-gray-800 truncate text-[11px]" title={row.driver_display_name}>
                          {row.driver_display_name}
                        </div>
                        <div className="text-[10px] text-gray-400 truncate font-mono" title={row.driver_id || ''}>
                          {row.driver_license_raw || (row.driver_id ? row.driver_id.slice(0, 12) : '-')}
                        </div>
                      </td>
                      <td className="px-3 py-1 font-mono text-[11px] text-gray-500 max-w-[90px] truncate" title={row.driver_license_raw || ''}>
                        {row.driver_license_raw || '-'}
                      </td>
                      <td className="px-3 py-1 whitespace-nowrap text-[11px] text-gray-600">{row.origin || '-'}</td>
                      <td className="px-3 py-1 max-w-[130px] truncate text-[11px]" title={row.scout_name || ''}>
                        {row.scout_name || '-'}
                      </td>
                      <td className="px-3 py-1 max-w-[100px] truncate text-[11px] text-gray-500" title={row.supervisor_name || ''}>
                        {row.supervisor_name || '-'}
                      </td>
                      <td className="px-3 py-1 text-right font-mono text-[11px] text-gray-500">{row.trips_0_7_count || '0'}</td>
                      <td className="px-3 py-1 text-right font-mono text-[11px] text-gray-500">{row.trips_8_14_count || '0'}</td>
                      <td className="px-3 py-1">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${STATUS_COLORS[row.attribution_status || ''] || 'bg-gray-100 text-gray-500'}`}>
                          {shortAttr(row.attribution_status)}
                        </span>
                      </td>
                      <td className="px-3 py-1">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${STATUS_COLORS[row.payment_financial_status || ''] || 'bg-gray-100 text-gray-500'}`}>
                          {shortFin(row.payment_financial_status)}
                        </span>
                      </td>
                      <td className="px-3 py-1">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${BLOCKING_COLORS[row.blocking_display as string] || 'bg-gray-100 text-gray-500'}`}>
                          {row.blocking_display || '-'}
                        </span>
                      </td>
                      <td className="px-3 py-1 text-right font-mono text-[11px] whitespace-nowrap">
                        {row.amount_paid ? <span className="font-medium">S/ {row.amount_paid.toFixed(0)}</span> : <span className="text-gray-300">-</span>}
                      </td>
                      <td className="px-3 py-1">
                        <div className="flex items-center gap-1">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${ALERT_BADGE[row.alert_level] || ''}`}>
                            {row.alert_level}
                          </span>
                          {row.alert_codes && row.alert_codes.length > 0 && (
                            <span className="text-[10px] text-gray-400" title={row.alert_codes.join(', ')}>
                              {row.alert_codes.length > 1 ? `+${row.alert_codes.length - 1}` : ''}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-3 py-1.5 border-t border-gray-200 bg-gray-50 text-xs">
                <span className="text-gray-400">Pag {page + 1}/{totalPages} ({data.total})</span>
                <div className="flex gap-1">
                  <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                    className="px-2 py-0.5 border border-gray-200 rounded text-xs disabled:opacity-30 hover:bg-gray-100">Anterior</button>
                  <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                    className="px-2 py-0.5 border border-gray-200 rounded text-xs disabled:opacity-30 hover:bg-gray-100">Siguiente</button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>

      {/* Detail Drawer */}
      {selectedId && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/20" onClick={() => setSelectedId(null)} />
          <div className="relative w-[520px] bg-white shadow-xl border-l border-gray-200 overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-2.5 flex items-center justify-between z-10">
              <h3 className="font-semibold text-gray-800 text-sm">Detalle #{selectedId}</h3>
              <button onClick={() => setSelectedId(null)} className="text-gray-400 hover:text-gray-600 text-lg">&times;</button>
            </div>
            <div className="p-4 space-y-3">
              {detailLoading ? <div className="text-center text-gray-400 py-8 text-sm">Cargando...</div> : detail ? (
                <>
                  <Section title="Afiliacion">
                    <F label="Row" value={detail.row_id} />
                    <F label="Batch" value={detail.batch_id} />
                    <F label="Sheet / Row" value={`${detail.source_sheet || '-'} / ${detail.source_row || '-'}`} />
                    <F label="ISO Week" value={detail.iso_week_label_full || '-'} />
                    <F label="Hire Date" value={detail.hire_date || detail.source_hire_date || '-'} />
                    <F label="Origen" value={detail.origin_raw || detail.source_origin || '-'} />
                  </Section>
                  <Section title="Driver">
                    <F label="Nombre" value={detail.driver_display_name || 'Sin nombre'} bold />
                    <F label="Driver ID" value={detail.driver_id_resolved || 'No resuelto'} mono />
                    <F label="Licencia" value={detail.driver_license_raw || '-'} mono />
                    <F label="Nombre raw" value={detail.driver_name_raw || '-'} />
                  </Section>
                  <Section title="Scout">
                    <F label="Scout (raw)" value={detail.scout_name_raw || '-'} />
                    <F label="Scout (resuelto)" value={detail.scout_resolved_name || 'No resuelto'} />
                    <F label="Supervisor" value={detail.supervisor_raw || '-'} />
                    <F label="Sup. resuelto" value={detail.supervisor_resolved_name || '-'} />
                  </Section>
                  <Section title="Pago">
                    <F label="Monto" value={detail.amount_paid ? `S/ ${detail.amount_paid}` : '-'} bold />
                    <F label="Regla" value={detail.payment_rule_raw || '-'} />
                    <F label="Estado raw" value={detail.estado_pago_raw || '-'} />
                    <F label="Esquema" value={detail.payment_scheme_raw || '-'} />
                    <F label="Hito" value={detail.milestone_raw || '-'} />
                  </Section>
                  <Section title="Paid History">
                    <F label="PH ID" value={detail.paid_history_id || 'No creado'} />
                    <F label="PH Amount" value={detail.ph_amount_paid ? `S/ ${detail.ph_amount_paid}` : '-'} />
                    <F label="Blocks Future" value={detail.ph_blocks_future === true ? 'Si' : detail.ph_blocks_future === false ? 'No' : '-'} />
                    <F label="Resolution" value={detail.ph_resolution_status || '-'} />
                    <F label="Hash" value={detail.ph_unique_hash ? detail.ph_unique_hash.slice(0, 16) + '...' : '-'} mono />
                  </Section>
                  <Section title="Clasificacion">
                    <F label="Atribucion" value={detail.attribution_status || '-'} />
                    <F label="Attr. Reason" value={detail.attribution_reason || '-'} />
                    <F label="Pago Financiero" value={detail.payment_financial_status || '-'} />
                    <F label="Pago Blocking" value={detail.payment_blocking_status || '-'} />
                    <F label="Blocking Display" value={detail.blocking_display || '-'} />
                    <F label="Blocks Future" value={detail.blocks_future_payment === true ? 'Si' : detail.blocks_future_payment === false ? 'No' : '-'} />
                    <F label="Final Status" value={detail.final_status || '-'} />
                  </Section>
                  <Section title="Alertas">
                    <F label="Alert Level" value={detail.alert_level || '-'} />
                    <F label="Alert Codes" value={detail.alert_codes ? detail.alert_codes.join(', ') : '-'} />
                  </Section>
                </>
              ) : <div className="text-center text-gray-400 py-8 text-sm">Sin datos</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ label, value, color = 'text-gray-700' }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-white rounded border border-gray-200 px-3 py-1.5 text-center">
      <div className={`text-base font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-3 py-1 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
      <div className="divide-y divide-gray-100">{children}</div>
    </div>
  )
}

function F({ label, value, mono, bold }: { label: string; value: string | number | null | undefined; mono?: boolean; bold?: boolean }) {
  return (
    <div className="flex items-center px-3 py-1 text-xs">
      <span className="text-gray-400 w-32 shrink-0">{label}</span>
      <span className={`text-gray-700 truncate ${mono ? 'font-mono' : ''} ${bold ? 'font-medium' : ''}`}>
        {value !== null && value !== undefined ? String(value) : '-'}
      </span>
    </div>
  )
}
