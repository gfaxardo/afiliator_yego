import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  listCutoffs,
  createCutoffFromCohort, createSweepCutoff,
  getCutoffSummary, getCutoffLines,
  reviewPayment, approvePayment, markPaymentPaid, cancelPayment,
  getPaymentExportCsvUrl, getPaymentExportXlsxUrl,
  getPaidHistory, getCutoffExportFinancialUrl,
  getOperationFilters, listPaymentSchemes,
} from '../../api/scoutLiq'

const GREEN  = { bg: 'bg-emerald-50', border: 'border-emerald-300', text: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-800' }
const YELLOW = { bg: 'bg-amber-50',   border: 'border-amber-300',   text: 'text-amber-700',   badge: 'bg-amber-100 text-amber-800' }
const RED    = { bg: 'bg-red-50',     border: 'border-red-300',     text: 'text-red-700',     badge: 'bg-red-100 text-red-800' }
const BLUE   = { bg: 'bg-blue-50',    border: 'border-blue-300',    text: 'text-blue-700',    badge: 'bg-blue-100 text-blue-800' }
const GRAY   = { bg: 'bg-gray-50',    border: 'border-gray-200',   text: 'text-gray-500',   badge: 'bg-gray-100 text-gray-600' }

const STATUS_COLORS: Record<string, string> = {
  draft:      'bg-gray-100 text-gray-600',
  calculated: 'bg-blue-100 text-blue-700',
  reviewed:   'bg-yellow-100 text-yellow-700',
  approved:   'bg-emerald-100 text-emerald-700',
  paid:       'bg-teal-100 text-teal-700',
  cancelled:  'bg-red-100 text-red-600',
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', calculated: 'Calculado', reviewed: 'Revisado',
  approved: 'Aprobado', paid: 'Pagado', cancelled: 'Cancelado',
}

const LINE_STATUS_COLORS: Record<string, string> = {
  payable: GREEN.text,
  paid: 'text-teal-700',
  blocked_invalid_hire_date: RED.text,
  blocked_no_official_source: RED.text,
  blocked_already_paid: 'text-purple-700',
  blocked_min_activated: 'text-orange-700',
  blocked_missing_official_anchor: RED.text,
  activated_no_tier: 'text-amber-600',
  no_trip: 'text-gray-400',
  below_pay_threshold: 'text-gray-400',
}

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${color}`}>{label}</span>
}

export default function LiquidacionesView() {
  const [loadingInitial, setLoadingInitial] = useState(true)

  const [schemes, setSchemes] = useState<{ scheme_id: number; name: string; scheme_type: string }[]>([])
  const [cutoffs, setCutoffs] = useState<any[]>([])
  const [selectedCutoff, setSelectedCutoff] = useState<any>(null)
  const [cutoffSummaries, setCutoffSummaries] = useState<any[]>([])
  const [cutoffLines, setCutoffLines] = useState<any[]>([])
  const [linesTotal, setLinesTotal] = useState(0)
  const [cutoffLoading, setCutoffLoading] = useState(false)
  const [linesLoading, setLinesLoading] = useState(false)

  const [cohortWeek, setCohortWeek] = useState('')
  const [originFilter, setOriginFilter] = useState('')
  const [cutoffMode, setCutoffMode] = useState<'cohort' | 'sweep'>('cohort')
  const [creatingCutoff, setCreatingCutoff] = useState(false)
  const [approving, setApproving] = useState(false)
  const [paying, setPaying] = useState(false)
  const [cancelReason, setCancelReason] = useState('')

  const [paidHistory, setPaidHistory] = useState<any[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [historyPage, setHistoryPage] = useState(0)

  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Confirmation modals
  const [showApproveConfirm, setShowApproveConfirm] = useState(false)
  const [showPayConfirm, setShowPayConfirm] = useState(false)

  // Driver lines filter
  const [linesScoutFilter, setLinesScoutFilter] = useState<number | null>(null)
  const [linesStatusFilter, setLinesStatusFilter] = useState('')
  const [linesSearch, setLinesSearch] = useState('')
  const [showLinesPanel, setShowLinesPanel] = useState(false)

  const showMsg = useCallback((msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 4000) }, [])
  const showErr = useCallback((msg: string) => { setError(msg); setTimeout(() => setError(null), 8000) }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      listPaymentSchemes(), listCutoffs(), getOperationFilters().catch(() => null),
    ]).then(([s, c, f]) => {
      if (cancelled) return
      setSchemes(s)
      setCutoffs(c)
      if (f) setCohortWeek(f.current_iso_week || '')
    }).catch((err: any) => { if (!cancelled) setError(err?.response?.data?.detail || err.message) })
      .finally(() => { if (!cancelled) setLoadingInitial(false) })
    return () => { cancelled = true }
  }, [])

  const refreshCutoffs = useCallback(async () => {
    try { const c = await listCutoffs(); setCutoffs(c) } catch (e: any) { showErr(e?.message || e) }
  }, [showErr])

  const loadCutoffDetail = useCallback(async (c: any) => {
    setCutoffLoading(true)
    try {
      const [sums, linesData] = await Promise.all([
        getCutoffSummary(c.id),
        getCutoffLines(c.id)
      ])
      setCutoffSummaries(sums)
      setCutoffLines(linesData.lines || [])
      setLinesTotal(linesData.total || 0)
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setCutoffLoading(false) }
  }, [showErr])

  const loadCutoffLines = useCallback(async (scoutId?: number | null, status?: string) => {
    if (!selectedCutoff) return
    setLinesLoading(true)
    try {
      const linesData = await getCutoffLines(selectedCutoff.id, scoutId || undefined, linesSearch || undefined)
      let filtered = linesData.lines || []
      if (status) filtered = filtered.filter((l: any) => l.line_status === status || l.payment_status === status)
      setCutoffLines(filtered)
      setLinesTotal(linesData.total || 0)
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setLinesLoading(false) }
  }, [selectedCutoff, linesSearch, showErr])

  const selectCutoff = useCallback((c: any) => {
    setSelectedCutoff(c)
    setLinesScoutFilter(null)
    setLinesStatusFilter('')
    setLinesSearch('')
    setShowLinesPanel(false)
    loadCutoffDetail(c)
  }, [loadCutoffDetail])

  const selectScoutForLines = useCallback((scoutId: number | null) => {
    setLinesScoutFilter(scoutId)
    setShowLinesPanel(true)
    loadCutoffLines(scoutId, linesStatusFilter)
  }, [loadCutoffLines, linesStatusFilter])

  const handleCreateCutoff = useCallback(async () => {
    setCreatingCutoff(true)
    setError(null)
    try {
      let result: any
      if (cutoffMode === 'cohort') {
        if (!cohortWeek) { showErr('Selecciona una cohorte ISO (ej: 2026-W22)'); return }
        result = await createCutoffFromCohort({ cohort_iso_week: cohortWeek, scheme_type: originFilter || undefined })
      } else {
        result = await createSweepCutoff({ scheme_type: originFilter || undefined })
      }
      showMsg('Corte creado: ' + (result.cutoff_name || result.id))
      const updated = await listCutoffs(); setCutoffs(updated)
      if (result.cutoff_run_id) {
        const c = updated.find((x: any) => x.id === result.cutoff_run_id)
        if (c) selectCutoff(c)
      }
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setCreatingCutoff(false) }
  }, [cutoffMode, cohortWeek, originFilter, showMsg, showErr, selectCutoff])

  const handleReview = useCallback(async () => {
    if (!selectedCutoff) return; setApproving(true)
    try {
      await reviewPayment(selectedCutoff.id); showMsg('Corte revisado')
      await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u)
      const r = u.find(x => x.id === selectedCutoff.id); if (r) setSelectedCutoff(r)
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setApproving(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs])

  const handleApprove = useCallback(async () => {
    if (!selectedCutoff) return; setApproving(true); setShowApproveConfirm(false)
    try {
      await approvePayment(selectedCutoff.id); showMsg('Corte aprobado. Montos congelados.')
      await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u)
      const r = u.find(x => x.id === selectedCutoff.id); if (r) setSelectedCutoff(r)
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setApproving(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs])

  const handleCancel = useCallback(async () => {
    if (!selectedCutoff || !cancelReason) return
    try {
      await cancelPayment(selectedCutoff.id, cancelReason); showMsg('Corte cancelado')
      setCancelReason(''); await refreshCutoffs(); setSelectedCutoff(null)
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
  }, [selectedCutoff, cancelReason, showMsg, showErr, refreshCutoffs])

  const handleMarkPaid = useCallback(async () => {
    if (!selectedCutoff) return; setPaying(true); setShowPayConfirm(false)
    try {
      await markPaymentPaid(selectedCutoff.id); showMsg('Marcado como pagado. Drivers bloqueados para futuros cortes.')
      await refreshCutoffs(); const u = await listCutoffs(); setCutoffs(u)
      const r = u.find(x => x.id === selectedCutoff.id); if (r) { setSelectedCutoff(r); loadCutoffDetail(r) }
    } catch (e: any) { showErr(e?.response?.data?.detail || e.message) }
    finally { setPaying(false) }
  }, [selectedCutoff, showMsg, showErr, refreshCutoffs, loadCutoffDetail])

  const openExport = useCallback((urlFn: (id: number) => string) => {
    if (!selectedCutoff) return
    const a = document.createElement('a')
    a.href = urlFn(selectedCutoff.id)
    a.download = `corte_${selectedCutoff.id}.csv`
    a.target = '_blank'
    a.click()
  }, [selectedCutoff])

  const loadHistory = useCallback(async (page: number) => {
    setLoadingHistory(true)
    try {
      const hist = await getPaidHistory({ limit: 20, offset: page * 20 })
      if (page === 0) setPaidHistory(hist.items || [])
      else setPaidHistory(prev => [...prev, ...(hist.items || [])])
      setHistoryPage(page)
    } catch (e: any) { showErr(e?.message || e) }
    finally { setLoadingHistory(false) }
  }, [showErr])

  useEffect(() => { if (!loadingInitial) loadHistory(0) }, [loadingInitial])

  const origins = useMemo(() => [...new Set(schemes.map(s => s.scheme_type).filter(Boolean))] as string[], [schemes])

  const cutoffKpis = useMemo(() => ({
    total: cutoffs.length,
    draft: cutoffs.filter(c => c.status === 'draft' || c.status === 'calculated').length,
    reviewed: cutoffs.filter(c => c.status === 'reviewed').length,
    approved: cutoffs.filter(c => c.status === 'approved').length,
    paid: cutoffs.filter(c => c.status === 'paid').length,
    totalPayable: cutoffSummaries.reduce((sum, s) => sum + (s.amount_calculated || s.total_payable || 0), 0),
    totalPaidHistory: paidHistory.reduce((sum, p) => sum + (p.amount_paid || 0), 0),
    lastCutoff: cutoffs[0],
  }), [cutoffs, cutoffSummaries, paidHistory])

  const blockerCounts = useMemo(() => {
    const counts: Record<string, { label: string; count: number; color: string }> = {
      already_paid: { label: 'Ya pagado', count: 0, color: 'text-purple-700 bg-purple-50' },
      no_scout: { label: 'Sin scout', count: 0, color: 'text-yellow-700 bg-yellow-50' },
      min_not_reached: { label: 'Min. afiliaciones', count: 0, color: 'text-orange-700 bg-orange-50' },
      no_tier: { label: 'No tier', count: 0, color: 'text-amber-600 bg-amber-50' },
      no_activation: { label: 'Sin activacion', count: 0, color: 'text-gray-600 bg-gray-50' },
      anchor_missing: { label: 'Anchor faltante', count: 0, color: 'text-red-700 bg-red-50' },
    }
    for (const s of cutoffSummaries) {
      if (s.status === 'blocked') {
        const reason = s.blocked_reason || ''
        if (reason.includes('already_paid')) counts.already_paid.count++
        else if (reason.includes('min_activated') || reason.includes('min_affiliation')) counts.min_not_reached.count++
        else if (reason.includes('no_tier')) counts.no_tier.count++
        else if (reason.includes('no_activation')) counts.no_activation.count++
        else if (reason.includes('anchor') || s.blocked_reason === 'blocked_missing_official_anchor') counts.anchor_missing.count++
      }
    }
    for (const l of cutoffLines) {
      if (l.blocked_reason === 'already_paid' || l.already_paid) counts.already_paid.count++
      if (l.attribution_status === 'unassigned' || !l.scout_id) counts.no_scout.count++
    }
    return Object.entries(counts).filter(([_, v]) => v.count > 0)
  }, [cutoffSummaries, cutoffLines])

  const stepStatus: Record<string, boolean> = useMemo(() => {
    const s = selectedCutoff?.status
    return {
      draft: s === 'draft' || s === 'calculated',
      calculated: s === 'calculated' || s === 'reviewed' || s === 'approved' || s === 'paid',
      reviewed: s === 'reviewed' || s === 'approved' || s === 'paid',
      approved: s === 'approved' || s === 'paid',
      paid: s === 'paid',
    }
  }, [selectedCutoff])

  if (loadingInitial) {
    return (
      <div className="max-w-6xl mx-auto space-y-4 p-4">
        <div className="bg-gray-200 rounded animate-pulse h-7 w-48" />
        <div className="bg-gray-200 rounded animate-pulse h-12 w-full" />
        <div className="bg-gray-200 rounded animate-pulse h-48 w-full" />
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto">
      {error && (
        <div className="mb-2 px-4 py-2.5 bg-red-50 border border-red-300 rounded-lg text-sm text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-3 text-red-400 hover:text-red-600 font-bold text-lg leading-none">&times;</button>
        </div>
      )}
      {success && (
        <div className="mb-2 px-4 py-2.5 bg-emerald-50 border border-emerald-300 rounded-lg text-sm text-emerald-700">{success}</div>
      )}

      {/* ── Header ── */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-gray-200 -mx-4 px-4 py-2 mb-3 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="text-lg font-bold text-gray-800">Liquidaciones</h2>
            <p className="text-[10px] text-gray-400">Crear cortes, revisar preliquidaciones, aprobar pagos y exportar sustento.</p>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
            <span className="font-bold text-gray-700">{cutoffKpis.total} cortes</span>
            {cutoffKpis.draft > 0 && <Badge label={`${cutoffKpis.draft} draft`} color={BLUE.badge} />}
            {cutoffKpis.reviewed > 0 && <Badge label={`${cutoffKpis.reviewed} revisados`} color={YELLOW.badge} />}
            {cutoffKpis.approved > 0 && <Badge label={`${cutoffKpis.approved} aprobados`} color={GREEN.badge} />}
            {cutoffKpis.paid > 0 && <Badge label={`${cutoffKpis.paid} pagados`} color="bg-teal-100 text-teal-700" />}
            {cutoffKpis.totalPayable > 0 && <span className="text-green-600 font-semibold">Pagable S/ {cutoffKpis.totalPayable.toLocaleString()}</span>}
          </div>
        </div>
      </div>

      {/* ── Crear corte ── */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-gray-500">Nuevo corte:</span>
            <button onClick={() => setCutoffMode('cohort')}
              className={`px-3 py-1 text-[11px] rounded font-medium ${cutoffMode === 'cohort' ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-500'}`}>Cohorte ISO</button>
            <button onClick={() => setCutoffMode('sweep')}
              className={`px-3 py-1 text-[11px] rounded font-medium ${cutoffMode === 'sweep' ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-500'}`}>Barrido</button>
          </div>
          {cutoffMode === 'cohort' && (
            <input type="text" value={cohortWeek} onChange={e => setCohortWeek(e.target.value)}
              placeholder="Ej: 2026-W22" className="border rounded px-2 py-1 text-xs w-28" />
          )}
          {origins.length > 0 && (
            <select value={originFilter} onChange={e => setOriginFilter(e.target.value)}
              className="border rounded px-2 py-1 text-xs">
              <option value="">Todos origenes</option>
              {origins.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
          <button onClick={handleCreateCutoff} disabled={creatingCutoff}
            className="px-4 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 disabled:opacity-50">
            {creatingCutoff ? 'Creando...' : 'Crear corte y previsualizar'}
          </button>
        </div>
      </div>

      {/* ── Cutoff list table ── */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden mb-3">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left text-[10px] text-gray-400 uppercase bg-gray-50 border-b">
              <th className="px-3 py-1.5 font-medium">Corte</th>
              <th className="px-3 py-1.5 font-medium">Ventana</th>
              <th className="px-3 py-1.5 font-medium">Modo</th>
              <th className="px-3 py-1.5 font-medium">Estado</th>
              <th className="px-3 py-1.5 font-medium">Scouts</th>
              <th className="px-3 py-1.5 font-medium text-right">Calculado</th>
              <th className="px-3 py-1.5 font-medium text-right">Aprobado</th>
              <th className="px-3 py-1.5 font-medium w-10"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {cutoffs.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-gray-400 text-xs">No hay cortes. Crea uno arriba para empezar.</td></tr>
            ) : (
              cutoffs.map(c => (
                <tr key={c.id}
                  onClick={() => selectCutoff(c)}
                  className={`cursor-pointer hover:bg-blue-50/40 transition-colors ${selectedCutoff?.id === c.id ? 'bg-blue-50/60 ring-1 ring-blue-200' : ''}`}>
                  <td className="px-3 py-2">
                    <div className="font-semibold text-gray-800 truncate max-w-[180px]">{c.cutoff_name}</div>
                    {c.cohort_iso_week && <div className="text-[9px] text-gray-400">{c.cohort_iso_week}</div>}
                  </td>
                  <td className="px-3 py-2 text-gray-500 font-mono whitespace-nowrap">{c.hire_date_from || '—'} → {c.hire_date_to || '—'}</td>
                  <td className="px-3 py-2 text-[10px] text-gray-400">{c.cutoff_mode || 'COHORT'}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${STATUS_COLORS[c.status] || 'bg-gray-100'}`}>
                      {STATUS_LABEL[c.status] || c.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{c.total_scouts ?? c.summary_count ?? '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-gray-700">{c.total_payable ? `S/ ${Number(c.total_payable).toLocaleString()}` : '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-emerald-700">{c.total_approved ? `S/ ${Number(c.total_approved).toLocaleString()}` : '—'}</td>
                  <td className="px-3 py-2 text-right text-gray-300">&rsaquo;</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* ── Selected cutoff detail ── */}
      {!selectedCutoff ? (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-8 text-center mb-3">
          <p className="text-sm text-gray-400">Selecciona un corte de la lista para ver su detalle y operar.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Workflow stepper */}
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex items-center gap-1 flex-wrap">
              {[
                { key: 'calculated', label: '1. Calculado', done: stepStatus.calculated, active: stepStatus.draft },
                { key: 'reviewed', label: '2. Revisado', done: stepStatus.reviewed, active: !stepStatus.calculated && !stepStatus.reviewed },
                { key: 'approved', label: '3. Aprobado', done: stepStatus.approved, active: stepStatus.reviewed && !stepStatus.approved },
                { key: 'paid', label: '4. Pagado', done: stepStatus.paid, active: stepStatus.approved && !stepStatus.paid },
              ].map((s, i) => (
                <span key={s.key} className="flex items-center gap-1">
                  <span className={`px-2 py-1 rounded text-[10px] font-semibold ${
                    s.done ? 'bg-emerald-100 text-emerald-700' : s.active ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-400'
                  }`}>
                    {s.done ? '✓' : s.active ? '●' : '○'} {s.label}
                  </span>
                  {i < 3 && <span className="text-gray-300 text-xs">→</span>}
                </span>
              ))}
              <div className="ml-auto flex gap-1.5">
                {selectedCutoff.status === 'calculated' && (
                  <button onClick={handleReview} disabled={approving}
                    className="px-3 py-1 bg-yellow-600 text-white rounded text-[10px] font-semibold hover:bg-yellow-700 disabled:opacity-50">
                    {approving ? '...' : 'Revisar'}
                  </button>
                )}
                {selectedCutoff.status === 'reviewed' && (
                  <button onClick={() => setShowApproveConfirm(true)}
                    className="px-3 py-1 bg-emerald-600 text-white rounded text-[10px] font-semibold hover:bg-emerald-700">
                    Aprobar
                  </button>
                )}
                {selectedCutoff.status === 'approved' && (
                  <>
                    <button onClick={() => openExport(getPaymentExportCsvUrl)}
                      className="px-2 py-1 border border-gray-200 text-gray-600 rounded text-[10px] hover:bg-gray-50">CSV</button>
                    <button onClick={() => openExport(getCutoffExportFinancialUrl)}
                      className="px-2 py-1 border border-gray-200 text-gray-600 rounded text-[10px] hover:bg-gray-50">Financiero</button>
                    <button onClick={() => setShowPayConfirm(true)}
                      className="px-3 py-1 bg-teal-600 text-white rounded text-[10px] font-semibold hover:bg-teal-700">
                      Marcar pagado
                    </button>
                  </>
                )}
                {(selectedCutoff.status !== 'paid' && selectedCutoff.status !== 'cancelled') && (
                  <button onClick={handleCancel} disabled={!cancelReason}
                    className="px-2 py-1 bg-red-50 text-red-600 rounded text-[10px] hover:bg-red-100 disabled:opacity-40"
                    title="Requiere razon de cancelacion">
                    Cancelar
                  </button>
                )}
              </div>
            </div>
            {selectedCutoff.status !== 'paid' && (
              <input type="text" value={cancelReason} onChange={e => setCancelReason(e.target.value)}
                placeholder="Razon de cancelacion (necesaria)"
                className="mt-2 border rounded px-2 py-1 text-[10px] w-60 text-gray-500" />
            )}
          </div>

          {/* Scout summary + blockers */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="lg:col-span-2">
              {cutoffLoading ? (
                <div className="space-y-2">{Array.from({length:4}).map((_,i)=><div key={i} className="bg-gray-200 rounded animate-pulse h-10 w-full" />)}</div>
              ) : cutoffSummaries.length > 0 ? (
                <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-gray-50 border-b text-[11px] font-semibold text-gray-500 uppercase flex justify-between">
                    <span>Resumen por scout ({cutoffSummaries.length})</span>
                    <button onClick={() => selectScoutForLines(null)}
                      className="text-[10px] text-blue-600 hover:text-blue-800 font-normal normal-case">Ver todos los conductores</button>
                  </div>
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-left text-[9px] text-gray-400 uppercase bg-gray-50/50 border-b">
                        <th className="px-2 py-1">Scout</th>
                        <th className="px-2 py-1 text-center">Afiliados</th>
                        <th className="px-2 py-1 text-center">5V/7D</th>
                        <th className="px-2 py-1 text-center">No conv.</th>
                        <th className="px-2 py-1 text-center">Conv %</th>
                        <th className="px-2 py-1 text-center">Tier</th>
                        <th className="px-2 py-1 text-right">Pago x conv</th>
                        <th className="px-2 py-1 text-right">Total calc.</th>
                        <th className="px-2 py-1">Estado</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {cutoffSummaries.map((s: any, i: number) => {
                        const isBlocked = s.status === 'blocked'
                        return (
                          <tr key={i}
                            onClick={() => selectScoutForLines(s.scout_id)}
                            className="cursor-pointer hover:bg-blue-50/30 transition-colors">
                            <td className="px-2 py-1.5 font-medium text-gray-800">{s.scout_name}</td>
                            <td className="px-2 py-1.5 text-center text-gray-600">{s.total_affiliations || s.total_activated || 0}</td>
                            <td className="px-2 py-1.5 text-center font-semibold text-blue-600">{s.converted_5trips_7d || 0}</td>
                            <td className="px-2 py-1.5 text-center text-gray-400">{s.not_converted || 0}</td>
                            <td className="px-2 py-1.5 text-center font-mono font-semibold">{((s.conversion_rate || s.conversion_rate_5v7d || 0) * 100).toFixed(0)}%</td>
                            <td className="px-2 py-1.5 text-center font-mono text-gray-700">{s.tier_reached != null ? `T${Math.round(s.tier_reached * 100)}` : '—'}</td>
                            <td className="px-2 py-1.5 text-right font-mono">S/ {Number(s.payment_per_converted_driver || 0).toFixed(0)}</td>
                            <td className="px-2 py-1.5 text-right font-mono font-semibold">{isBlocked ? '—' : `S/ ${Number(s.amount_calculated || s.total_payable || 0).toLocaleString()}`}</td>
                            <td className="px-2 py-1.5">
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${isBlocked ? RED.badge : GREEN.badge}`}>
                                {isBlocked ? 'BLOQUEADO' : 'OK'}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="bg-white border border-dashed border-gray-300 rounded-lg p-6 text-center text-xs text-gray-400">
                  {selectedCutoff.status === 'draft' ? 'El corte esta en draft. Recalcula para generar el resumen.' : 'Sin datos de resumen.'}
                </div>
              )}
            </div>

            {/* Blockers panel */}
            <div>
              {blockerCounts.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-lg p-3">
                  <h4 className="text-[11px] font-semibold text-gray-500 uppercase mb-2">Bloqueos detectados</h4>
                  <div className="space-y-1">
                    {blockerCounts.map(([key, v]) => (
                      <div key={key} className="flex items-center justify-between px-2 py-1 rounded text-[10px]">
                        <span className={`font-medium ${v.color.split(' ')[0]}`}>{v.label}</span>
                        <Badge label={String(v.count)} color={v.color.split(' ').slice(1).join(' ')} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedCutoff && (
                <div className="bg-white border border-gray-200 rounded-lg p-3 mt-3">
                  <h4 className="text-[11px] font-semibold text-gray-500 uppercase mb-2">Info del corte</h4>
                  <div className="space-y-1 text-[10px] text-gray-500">
                    <div>ID: {selectedCutoff.id}</div>
                    <div>Base fecha: {selectedCutoff.date_basis || 'acquisition_anchor'}</div>
                    <div>Origen: {selectedCutoff.origin_filter || 'todos'}</div>
                    <div>Creado: {selectedCutoff.created_at ? selectedCutoff.created_at.substring(0, 10) : '—'}</div>
                    {selectedCutoff.approved_at && <div>Aprobado: {selectedCutoff.approved_at.substring(0, 10)}</div>}
                    {selectedCutoff.paid_at && <div>Pagado: {selectedCutoff.paid_at.substring(0, 10)}</div>}
                    {selectedCutoff.config_snapshot && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-gray-400 hover:text-gray-600">Ver snapshot config</summary>
                        <pre className="mt-1 text-[9px] bg-gray-50 p-1 rounded max-h-32 overflow-auto">{typeof selectedCutoff.config_snapshot === 'string' ? selectedCutoff.config_snapshot : JSON.stringify(selectedCutoff.config_snapshot, null, 2)}</pre>
                      </details>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Driver lines panel */}
          {showLinesPanel && selectedCutoff && (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div className="px-3 py-2 bg-gray-50 border-b flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-semibold text-gray-500 uppercase">
                  Conductores {linesScoutFilter ? `(scout #${linesScoutFilter})` : ''}
                </span>
                <input type="text" value={linesSearch} onChange={e => setLinesSearch(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && loadCutoffLines(linesScoutFilter, linesStatusFilter)}
                  placeholder="Buscar driver..." className="border rounded px-2 py-1 text-[10px] w-40" />
                <select value={linesStatusFilter} onChange={e => { setLinesStatusFilter(e.target.value); loadCutoffLines(linesScoutFilter, e.target.value) }}
                  className="border rounded px-2 py-1 text-[10px]">
                  <option value="">Todos estados</option>
                  <option value="payable">Pagables</option>
                  <option value="paid">Pagados</option>
                  <option value="blocked_already_paid">Ya pagados</option>
                  <option value="blocked_min_activated">Min activ.</option>
                  <option value="blocked_missing_official_anchor">Anchor faltante</option>
                  <option value="activated_no_tier">No tier</option>
                  <option value="no_trip">Sin viajes</option>
                </select>
                <span className="text-[10px] text-gray-400 ml-auto">{linesTotal > 0 ? `${cutoffLines.length} de ${linesTotal} lineas` : ''}</span>
                <button onClick={() => setShowLinesPanel(false)} className="text-xs text-gray-400 hover:text-gray-600">&times;</button>
              </div>
              {linesLoading ? (
                <div className="p-4 space-y-2">{Array.from({length:3}).map((_,i)=><div key={i} className="bg-gray-200 rounded animate-pulse h-8 w-full" />)}</div>
              ) : cutoffLines.length === 0 ? (
                <div className="p-6 text-center text-xs text-gray-400">Sin lineas para este filtro.</div>
              ) : (
                <div className="overflow-x-auto max-h-96 overflow-y-auto">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-left text-[9px] text-gray-400 uppercase bg-gray-50/50 border-b sticky top-0">
                        <th className="px-2 py-1">Driver</th>
                        <th className="px-2 py-1">Scout</th>
                        <th className="px-2 py-1">Trips 7D</th>
                        <th className="px-2 py-1">5V/7D</th>
                        <th className="px-2 py-1">Estado</th>
                        <th className="px-2 py-1">Motivo</th>
                        <th className="px-2 py-1 text-right">Monto</th>
                        <th className="px-2 py-1">Explicacion</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {cutoffLines.map((l: any, i: number) => (
                        <tr key={i} className={l.line_status === 'payable' ? 'bg-emerald-50/20' : l.line_status?.startsWith('blocked') ? 'bg-red-50/20' : ''}>
                          <td className="px-2 py-1.5">
                            <span className="font-medium text-gray-800">{l.driver_id || '—'}</span>
                            {l.hire_date && <div className="text-[9px] text-gray-400">{l.hire_date}</div>}
                          </td>
                          <td className="px-2 py-1.5 text-gray-600">{l.scout_name || l.scout_id || '—'}</td>
                          <td className="px-2 py-1.5 text-center font-mono">{l.trips_7d ?? l.trips_0_7_count ?? '—'}</td>
                          <td className="px-2 py-1.5 text-center font-mono">{l.is_converted_5trips_7d || l.converted_5v7d ? 'Si' : '—'}</td>
                          <td className="px-2 py-1.5">
                            <span className={`text-[9px] font-semibold ${LINE_STATUS_COLORS[l.line_status || l.payment_status] || 'text-gray-500'}`}>
                              {l.line_status || l.payment_status || '—'}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 text-[9px] text-gray-500">
                            {l.blocked_reason === 'already_paid' ? 'Ya pagado' :
                             l.blocked_reason === 'blocked_min_activated' ? 'Min activ.' :
                             l.blocked_reason === 'blocked_missing_official_anchor' ? 'Anchor faltante' :
                             l.already_paid ? 'Ya pagado' : l.blocked_reason || '—'}
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono font-semibold">
                            {l.calculated_amount ? `S/ ${Number(l.calculated_amount).toFixed(0)}` : '—'}
                          </td>
                          <td className="px-2 py-1.5">
                            {l.payment_formula_explanation ? (
                              <span className="text-[9px] text-gray-500 max-w-[200px] truncate block" title={l.payment_formula_explanation}>
                                {l.payment_formula_explanation.substring(0, 60)}{l.payment_formula_explanation.length > 60 ? '...' : ''}
                              </span>
                            ) : (
                              <span className="text-[9px] text-gray-300">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Historial ── */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mt-3">
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Historial de pagos</h3>
        {paidHistory.length === 0 && !loadingHistory ? (
          <p className="text-xs text-gray-400 py-2">No hay pagos registrados.</p>
        ) : (
          <div className="space-y-0.5 max-h-60 overflow-y-auto">
            {paidHistory.map((item: any, i: number) => (
              <div key={i} className="flex justify-between items-center text-[10px] border-b border-gray-50 py-1">
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-gray-700">{item.scout_name_raw || 'Scout #' + item.scout_id}</span>
                  <span className="text-gray-400 ml-2">Driver: {item.driver_id || item.driver_license_raw || '—'}</span>
                  {item.cutoff_name && <span className="text-gray-300 ml-1">· {item.cutoff_name}</span>}
                  {item.import_source && <span className={`ml-1 px-1 py-0.5 rounded text-[8px] ${item.import_source === 'cutoff_engine' ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-500'}`}>{item.import_source}</span>}
                </div>
                <span className="font-semibold text-emerald-700 ml-2 flex-shrink-0">S/ {item.amount_paid?.toLocaleString()} {item.currency}</span>
              </div>
            ))}
          </div>
        )}
        {paidHistory.length >= 20 && (
          <button onClick={() => loadHistory(historyPage + 1)} disabled={loadingHistory}
            className="mt-2 px-3 py-1 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200 disabled:opacity-50">
            {loadingHistory ? 'Cargando...' : 'Cargar mas'}
          </button>
        )}
        <a href="/scout-liq/paid-history" className="inline-block mt-2 px-3 py-1 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200">
          Historial completo
        </a>
      </div>

      {/* ── Approve confirmation modal ── */}
      {showApproveConfirm && selectedCutoff && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowApproveConfirm(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-5">
            <h4 className="text-sm font-bold text-gray-800 mb-3">Confirmar aprobacion</h4>
            <div className="text-xs text-gray-600 space-y-2 mb-4">
              <p>Corte: <strong>{selectedCutoff.cutoff_name}</strong></p>
              <p>Scouts en corte: {cutoffSummaries.length}</p>
              <p>Lineas totales: {linesTotal}</p>
              <p className="text-amber-600 font-medium">Al aprobar se congelan los montos aprobados y el snapshot de reglas usado. Esta accion no se puede deshacer facilmente.</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowApproveConfirm(false)}
                className="flex-1 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 rounded-lg border border-gray-200">Cancelar</button>
              <button onClick={handleApprove} disabled={approving}
                className="flex-1 px-3 py-2 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 font-semibold disabled:opacity-50">
                {approving ? 'Aprobando...' : 'Confirmar aprobacion'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Pay confirmation modal ── */}
      {showPayConfirm && selectedCutoff && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowPayConfirm(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-5">
            <h4 className="text-sm font-bold text-gray-800 mb-3">Confirmar pago</h4>
            <div className="text-xs text-gray-600 space-y-2 mb-4">
              <p>Corte: <strong>{selectedCutoff.cutoff_name}</strong></p>
              <p className="text-red-600 font-medium">Esta accion registrara el historial de pago y bloqueara estos drivers para futuros cortes. Es irreversible.</p>
              <p className="text-gray-400">Se crearan registros en paid_history con blocks_future_payment=true para cada driver pagable.</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowPayConfirm(false)}
                className="flex-1 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 rounded-lg border border-gray-200">Cancelar</button>
              <button onClick={handleMarkPaid} disabled={paying}
                className="flex-1 px-3 py-2 text-xs bg-teal-600 text-white rounded-lg hover:bg-teal-700 font-semibold disabled:opacity-50">
                {paying ? 'Pagando...' : 'Confirmar pago'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
