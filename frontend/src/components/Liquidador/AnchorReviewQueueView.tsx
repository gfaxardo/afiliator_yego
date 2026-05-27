/**
 * Anchor Review Queue — Fase 2B
 * Cola operacional para revision manual de acquisition anchors.
 */
import { useEffect, useState } from 'react'
import {
  getAnchorReviewQueue,
  getAnchorReviewSummary,
  getAnchorReviewAudit,
  performAnchorReview,
  type ReviewQueueItem,
  type ReviewSummary,
  type ReviewAuditEntry,
} from '../../api/scoutLiq'
import { AcquisitionBadge, AnchorBadgeStack } from './AcquisitionBadges'
import { classifyReviewSeverity, SeverityDot, OperationalSummaryBar, type SummaryCounts } from './OperationalLayer'

export default function AnchorReviewQueueView() {
  const [items, setItems] = useState<ReviewQueueItem[]>([])
  const [summary, setSummary] = useState<ReviewSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [originFilter, setOriginFilter] = useState('')
  const [auditLineId, setAuditLineId] = useState<number | null>(null)
  const [auditEntries, setAuditEntries] = useState<ReviewAuditEntry[]>([])
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [searchQ, setSearchQ] = useState('')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagCounts, setTagCounts] = useState<Record<string, number>>({})
  const [total, setTotal] = useState(0)
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const s = await getAnchorReviewSummary()
      setSummary(s)
      const q = await getAnchorReviewQueue({
        status_filter: statusFilter || undefined,
        origin: originFilter || undefined,
        q: searchQ || undefined,
        tags: selectedTags.length > 0 ? selectedTags.join(',') : undefined,
        limit: 100,
      })
      setItems(q.items)
      setTotal(q.total)
      setTagCounts(q.tag_counts || {})
    } catch (err: any) {
      setError(err?.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [statusFilter, originFilter])

  // Debounced search
  const handleSearch = (value: string) => {
    setSearchQ(value)
    if (debounceTimer) clearTimeout(debounceTimer)
    const timer = setTimeout(() => load(), 300)
    setDebounceTimer(timer)
  }

  const toggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    )
  }

  // Load when tags change
  useEffect(() => { load() }, [selectedTags])

  const handleAction = async (lineId: number, action: string) => {
    try {
      const reason = prompt(`Motivo para ${action}:`)
      if (reason === null) return
      setActionMsg(`Ejecutando ${action}...`)
      await performAnchorReview(lineId, { action, reason, actor: 'reviewer' })
      setActionMsg(`${action} completado para linea ${lineId}`)
      load()
      setTimeout(() => setActionMsg(null), 3000)
    } catch (err: any) {
      setActionMsg(`Error: ${err?.message || String(err)}`)
    }
  }

  const handleAudit = async (lineId: number) => {
    if (auditLineId === lineId) { setAuditLineId(null); setAuditEntries([]); return }
    try {
      const result = await getAnchorReviewAudit(lineId)
      setAuditLineId(lineId)
      setAuditEntries(result.audit_entries)
    } catch (err: any) {
      setAuditEntries([])
    }
  }

  const presets = [
    { key: '', label: 'Todos', color: 'border-gray-300 text-gray-600' },
    { key: 'blocked', label: 'Block Anchor', color: 'border-red-300 text-red-600' },
    { key: 'weak', label: 'Weak', color: 'border-red-200 text-red-500' },
    { key: 'reactivated', label: 'Reactivados', color: 'border-orange-300 text-orange-600' },
    { key: 'fallback', label: 'Fallback', color: 'border-yellow-300 text-yellow-600' },
    { key: 'manual_override', label: 'Approved Manual', color: 'border-green-300 text-green-600' },
  ]

  if (loading && !summary) return <div className="p-6 text-gray-400 text-sm">Cargando cola de revision...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">Anchor Review Queue</h2>
        <button onClick={load} disabled={loading}
          className="text-xs px-3 py-1 rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50">
          {loading ? 'Cargando...' : 'Refrescar'}
        </button>
      </div>

      {actionMsg && (
        <div className={`text-xs px-3 py-1.5 rounded border ${actionMsg.startsWith('Error') ? 'border-red-200 bg-red-50 text-red-700' : 'border-green-200 bg-green-50 text-green-700'}`}>
          {actionMsg}
        </div>
      )}

      {error && <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-xs">{error}</div>}

      {/* Operational Summary */}
      {items.length > 0 && (
        (() => {
          const severities = items.map(i => classifyReviewSeverity(i))
          const counts: SummaryCounts = {
            critical: severities.filter(s => s.severity === 'CRITICAL').length,
            warning: severities.filter(s => s.severity === 'WARNING').length,
            ok: severities.filter(s => s.severity === 'OK').length,
            total: items.length,
            paid: 0,
            noScout: 0,
            noLeadDate: severities.filter(s => s.severityLabel === 'Ancla debil').length,
            blockedAnchor: items.filter(i => i.payment_anchor_status === 'blocked_missing_official_anchor').length,
            observed: 0,
          }
          return (
            <div className="mb-2">
              <OperationalSummaryBar
                counts={counts}
                activeFilter={null}
                onFilterClick={() => {}}
              />
            </div>
          )
        })()
      )}

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-3 md:grid-cols-9 gap-2">
          <KpiCard label="Pendientes" value={summary.pending_review} color="yellow" />
          <KpiCard label="Block Anchor" value={summary.blocked_anchor} color="red" />
          <KpiCard label="Supervisor" value={summary.supervisor_review} color="orange" />
          <KpiCard label="Approved" value={summary.approved_manual} color="green" />
          <KpiCard label="Rejected" value={summary.rejected} color="red" />
          <KpiCard label="Refresh" value={summary.resolved_by_refresh} color="blue" />
          <KpiCard label="Weak" value={summary.weak_anchors} color="red" />
          <KpiCard label="Reactiv" value={summary.reactivated_pending} color="orange" />
          <KpiCard label="Total" value={summary.total_lines} color="gray" />
        </div>
      )}

      {/* Filters */}
      <div className="space-y-2">
        {/* Search bar */}
        <div className="relative">
          <input
            type="text"
            value={searchQ}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Buscar driver, licencia, placa, scout..."
            className="w-full border border-gray-200 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-blue-300"
          />
          {searchQ && (
            <button onClick={() => handleSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs">
              ✕
            </button>
          )}
        </div>

        {/* Tag chips */}
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(tagCounts).map(([tag, count]) => {
            const isActive = selectedTags.includes(tag)
            const colors: Record<string, string> = {
              REACTIVATED: 'border-orange-300 text-orange-700 bg-orange-50',
              FLEET: 'border-blue-300 text-blue-700 bg-blue-50',
              FALLBACK: 'border-yellow-300 text-yellow-700 bg-yellow-50',
              WEAK: 'border-red-300 text-red-700 bg-red-50',
              BLOCKED: 'border-red-400 text-red-800 bg-red-100',
              PAYABLE: 'border-green-300 text-green-700 bg-green-50',
              MANUAL_REVIEW: 'border-yellow-300 text-yellow-700 bg-yellow-50',
              GAP_30: 'border-amber-300 text-amber-700 bg-amber-50',
              NEW: 'border-emerald-300 text-emerald-700 bg-emerald-50',
              OFFICIAL_ANCHOR: 'border-green-300 text-green-700 bg-green-50',
              REPORTED_PENDING: 'border-yellow-300 text-yellow-700 bg-yellow-50',
            }
            return (
              <button key={tag} onClick={() => toggleTag(tag)}
                className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors ${
                  isActive ? `${colors[tag] || 'border-gray-300'} ring-1` : `bg-white border-gray-300 text-gray-500 hover:bg-gray-50`
                }`}>
                {tag.replace('_', ' ')} <span className="opacity-60">({count})</span>
              </button>
            )
          })}
          {(selectedTags.length > 0 || searchQ) && (
            <button onClick={() => { setSelectedTags([]); setSearchQ(''); load() }}
              className="px-2 py-0.5 text-[10px] text-red-500 hover:underline">
              Limpiar filtros
            </button>
          )}
        </div>
      </div>

      {/* Status presets */}
      <div className="flex flex-wrap gap-2 items-center">
        {presets.map(p => (
          <button key={p.key} onClick={() => setStatusFilter(p.key)}
            className={`px-2.5 py-1 text-[10px] font-medium border rounded transition-colors ${
              statusFilter === p.key ? `${p.color} bg-opacity-20` : `bg-white ${p.color} hover:bg-gray-50`
            }`}>
            {p.label}
          </button>
        ))}
        <span className="text-[10px] text-gray-400 ml-2">{items.length} de {total} resultados</span>
      </div>

      {/* Queue Table */}
      <div className="bg-white border rounded-lg overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 sticky top-0 z-10"><tr>
            <th className="text-left p-2 w-6"></th>
            <th className="text-left p-2">Driver</th>
            <th className="text-left p-2">Anchor Date</th>
            <th className="text-left p-2">Hire Ref</th>
            <th className="text-left p-2">Type / Status</th>
            <th className="text-center p-2">7d</th>
            <th className="text-center p-2">Gap</th>
            <th className="text-left p-2">Review</th>
            <th className="text-left p-2">Actions</th>
          </tr></thead>
          <tbody className="divide-y divide-gray-50">
            {items.map(item => {
              const sv = classifyReviewSeverity(item)
              return (
              <tr key={item.line_id} className={`hover:bg-gray-50 ${sv.severity === 'CRITICAL' ? 'bg-red-50/40' : item.reactivation_flag ? 'bg-orange-50/30' : ''}`}>
                <td className="p-2"><SeverityDot severity={sv.severity} /></td>
                <td className="p-2">
                  <div className="font-mono text-[10px]">{item.driver_id?.slice(0, 14)}...</div>
                  <div className="text-[10px] text-gray-400">{item.origin}</div>
                </td>
                <td className="p-2">
                  <div className="text-[11px] font-mono font-medium">{item.acquisition_anchor_date?.slice(0, 10) || '-'}</div>
                  <AnchorBadgeStack
                    acquisitionType={item.acquisition_type}
                    reactivationFlag={item.reactivation_flag}
                    anchorConfidence={item.anchor_confidence}
                    isAutoPayable={item.is_auto_payable_anchor}
                    paymentAnchorStatus={item.payment_anchor_status}
                    daysHireVsAnchor={item.days_hire_vs_anchor}
                  />
                </td>
                <td className="p-2 text-[10px] text-gray-500 font-mono">
                  {item.hire_date_reference?.slice(0, 10) || '-'}
                </td>
                <td className="p-2">
                  <div className="text-[10px]">{item.acquisition_type || item.payment_anchor_status || '-'}</div>
                  <div className="text-[9px] text-gray-400">{item.anchor_review_status}</div>
                </td>
                <td className="p-2 text-center font-mono font-bold">{item.trips_0_7_count}</td>
                <td className="p-2 text-center font-mono text-[10px]">
                  {item.days_hire_vs_anchor != null ? item.days_hire_vs_anchor : '-'}
                </td>
                <td className="p-2">
                  {item.anchor_reviewed_by && (
                    <div className="text-[9px] text-gray-400">{item.anchor_reviewed_by}</div>
                  )}
                  {item.anchor_review_reason && (
                    <div className="text-[9px] text-gray-500 max-w-[120px] truncate" title={item.anchor_review_reason}>
                      {item.anchor_review_reason}
                    </div>
                  )}
                </td>
                <td className="p-1.5">
                  <div className="flex gap-1 flex-wrap">
                    <button onClick={() => handleAction(item.line_id, 'approve')}
                      className="px-1.5 py-0.5 text-[9px] rounded border border-green-300 bg-green-50 text-green-700 hover:bg-green-100">
                      Approve
                    </button>
                    <button onClick={() => handleAction(item.line_id, 'reject')}
                      className="px-1.5 py-0.5 text-[9px] rounded border border-red-300 bg-red-50 text-red-700 hover:bg-red-100">
                      Reject
                    </button>
                    <button onClick={() => handleAction(item.line_id, 'needs_supervisor')}
                      className="px-1.5 py-0.5 text-[9px] rounded border border-orange-300 bg-orange-50 text-orange-700 hover:bg-orange-100">
                      Sup
                    </button>
                    <button onClick={() => handleAction(item.line_id, 'ignore')}
                      className="px-1.5 py-0.5 text-[9px] rounded border border-gray-300 bg-gray-50 text-gray-500 hover:bg-gray-100">
                      Ignore
                    </button>
                    <button onClick={() => handleAudit(item.line_id)}
                      className={`px-1.5 py-0.5 text-[9px] rounded border ${auditLineId === item.line_id ? 'border-blue-300 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-400 hover:bg-gray-50'}`}>
                      Audit
                    </button>
                  </div>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Audit Panel */}
      {auditLineId && auditEntries.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Audit Trail — Line {auditLineId}
          </h3>
          <div className="space-y-2 max-h-[30vh] overflow-y-auto">
            {auditEntries.map((entry, i) => (
              <div key={i} className="border border-gray-100 rounded p-2 text-[10px]">
                <div className="flex justify-between text-gray-500">
                  <span className="font-medium">{entry.action}</span>
                  <span>{entry.created_at?.slice(0, 19)}</span>
                </div>
                <div className="text-gray-400">Actor: {entry.actor || '-'}</div>
                {entry.reason && <div className="text-gray-600 mt-1">Reason: {entry.reason}</div>}
                {entry.notes && <div className="text-gray-500 mt-0.5">Notes: {entry.notes}</div>}
                {entry.reviewed_anchor_date && (
                  <div className="text-blue-600 mt-0.5">Reviewed anchor: {entry.reviewed_anchor_date}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    green: 'border-green-200 bg-green-50 text-green-800',
    red: 'border-red-200 bg-red-50 text-red-800',
    orange: 'border-orange-200 bg-orange-50 text-orange-800',
    yellow: 'border-yellow-200 bg-yellow-50 text-yellow-800',
    blue: 'border-blue-200 bg-blue-50 text-blue-800',
    gray: 'border-gray-200 bg-white text-gray-700',
  }
  return (
    <div className={`rounded border px-2 py-1.5 text-center ${colors[color] || colors.gray}`}>
      <div className="text-[9px] uppercase tracking-wider opacity-60">{label}</div>
      <div className="text-sm font-bold">{value}</div>
    </div>
  )
}
