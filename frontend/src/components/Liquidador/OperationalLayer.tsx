/**
 * Operational Layer — Classification, Next Actions, Summary & Quick Filters.
 *
 * Derivado 100% de campos existentes. No modifica backend ni logica de pago.
 *
 * Reglas de severidad:
 *   CRITICAL — bloquea operacion/pago inmediato
 *   WARNING  — requiere revision pero no bloquea
 *   OK       — operacion normal
 */
import React from 'react'

// ── Types ──────────────────────────────────────────────────────────

export type SeverityLevel = 'CRITICAL' | 'WARNING' | 'OK'

export interface ClassifiedLine {
  severity: SeverityLevel
  severityLabel: string
  nextAction: string
}

export interface LineBasics {
  line_status?: string
  payment_status?: string
  blocked_reason?: string | null
  already_paid?: boolean
  payout_eligible_flag?: boolean
  eligible?: boolean
  attribution_source?: string
  operational_source_universe?: string | null
  anchor_confidence?: string | null
  anchor_source?: string | null
  acquisition_type?: string | null
  reactivation_flag?: boolean
  is_auto_payable_anchor?: boolean
  payment_anchor_status?: string | null
  driver_lifecycle_status?: string
  source_quality_status?: string
  origin?: string
  trips_0_7_count?: number
  anchor_warning?: string | null
  blocked_reason_secondary?: string | null
}

// ── Severity Classifier ─────────────────────────────────────────────

export function classifyOperationalSeverity(line: LineBasics): ClassifiedLine {
  const ls = line.line_status || ''
  const ps = line.payment_status || ''
  const bl = line.blocked_reason || ''
  const ac = line.anchor_confidence || ''
  const op = line.operational_source_universe || ''
  const sc = line.source_quality_status || ''

  // ── CRITICAL — bloquea operacion ──
  if (line.already_paid) {
    return { severity: 'WARNING', severityLabel: 'Ya pagado', nextAction: 'Verificar historial de pagos' }
  }
  if (ls === 'blocked_already_paid') {
    return { severity: 'WARNING', severityLabel: 'Ya pagado', nextAction: 'Revisar si corresponde doble pago autorizado' }
  }
  if (ls === 'blocked_invalid_hire_date' || sc === 'invalid_hire_date') {
    return { severity: 'CRITICAL', severityLabel: 'Sin hire date', nextAction: 'Corregir hire date en fuente de datos' }
  }
  if (op === 'observed_no_official_source' || ls === 'blocked_no_official_source') {
    return { severity: 'CRITICAL', severityLabel: 'Sin fuente oficial', nextAction: 'Verificar si conductor existe en sistema oficial' }
  }
  if (ls === 'blocked_missing_official_anchor') {
    return { severity: 'CRITICAL', severityLabel: 'Bloqueo ancla', nextAction: 'Revisar fecha de adquisicion en Anchor Review' }
  }
  if (ac === 'weak' && ps === 'blocked') {
    return { severity: 'CRITICAL', severityLabel: 'Ancla debil', nextAction: 'Verificar fecha de adquisicion manualmente' }
  }
  if (bl.includes('Minimo') || ls === 'blocked_min_activated') {
    return { severity: 'WARNING', severityLabel: 'Minimo no alcanzado', nextAction: 'Esperar mas volumen o asignar mas conductores' }
  }
  if (ls === 'blocked_no_tier' || bl.includes('no_conversion_tier')) {
    return { severity: 'WARNING', severityLabel: 'Sin tier', nextAction: 'Esperar mejora de conversion' }
  }
  if (bl.includes('sin scout') || bl.includes('no_scout') || ls === 'no_scout') {
    return { severity: 'CRITICAL', severityLabel: 'Sin scout', nextAction: 'Asignar scout al conductor' }
  }

  // ── WARNING — requiere revision ──
  if (ac === 'medium' && line.acquisition_type !== 'fleet_migration') {
    return { severity: 'WARNING', severityLabel: 'Fecha aproximada', nextAction: 'Validar fecha de adquisicion' }
  }
  if (line.reactivation_flag) {
    return { severity: 'WARNING', severityLabel: 'Reactivado', nextAction: 'Verificar que no sea doble conteo' }
  }
  if (line.attribution_source === 'observed') {
    return { severity: 'WARNING', severityLabel: 'Observado', nextAction: 'Revisar en cola de reconciliacion' }
  }
  if (!line.is_auto_payable_anchor && (line.payout_eligible_flag || line.eligible)) {
    return { severity: 'WARNING', severityLabel: 'Pendiente revision', nextAction: 'Revisar en Anchor Review antes de aprobar' }
  }
  if (line.anchor_warning) {
    return { severity: 'WARNING', severityLabel: 'Warning ancla', nextAction: 'Revisar advertencia de fecha ancla' }
  }
  if (line.driver_lifecycle_status === 'no_trip' && line.origin !== 'fleet') {
    return { severity: 'WARNING', severityLabel: 'Sin viajes', nextAction: 'Esperar actividad del conductor' }
  }
  if (line.anchor_source === 'cabinet_drivers.hire_date' && line.acquisition_type === 'cabinet_unknown_no_lca') {
    return { severity: 'WARNING', severityLabel: 'Sin fecha lead', nextAction: 'Completar lead_created_at en fuente' }
  }

  // ── OK — operacion normal ──
  if (line.payout_eligible_flag || ps === 'payable') {
    return { severity: 'OK', severityLabel: 'Pagable', nextAction: 'Listo para aprobar' }
  }
  if (ls === 'payable' || ps === 'payable') {
    return { severity: 'OK', severityLabel: 'Pagable', nextAction: 'Listo para aprobar' }
  }
  if (ps === 'paid') {
    return { severity: 'OK', severityLabel: 'Pagado', nextAction: 'Registrado en historial' }
  }
  if (line.driver_lifecycle_status === 'converted_5v7d' || line.driver_lifecycle_status === 'converted_5v14d') {
    return { severity: 'OK', severityLabel: 'Convertido', nextAction: 'Monitorear proximo corte' }
  }

  return { severity: 'OK', severityLabel: 'Normal', nextAction: 'Monitorear' }
}

// ── ReviewQueueItem classifier ──────────────────────────────────────

export interface ReviewLineBasics {
  payment_anchor_status?: string | null
  anchor_confidence?: string | null
  anchor_source?: string | null
  anchor_warning?: string | null
  acquisition_type?: string | null
  reactivation_flag?: boolean
  payout_eligible_flag?: boolean
  line_status?: string
  payment_status?: string
  blocked_reason?: string | null
  is_auto_payable_anchor?: boolean
  anchor_review_status?: string
}

export function classifyReviewSeverity(line: ReviewLineBasics): ClassifiedLine {
  const status = line.payment_anchor_status || ''
  const conf = line.anchor_confidence || ''
  const review = line.anchor_review_status || ''

  if (status === 'blocked_missing_official_anchor') {
    return { severity: 'CRITICAL', severityLabel: 'Bloqueo ancla', nextAction: 'Aprobar o rechazar en revision' }
  }
  if (status === 'reported_pending_validation') {
    return { severity: 'WARNING', severityLabel: 'Pendiente validacion', nextAction: 'Validar fecha reportada por scout' }
  }
  if (conf === 'weak') {
    return { severity: 'CRITICAL', severityLabel: 'Ancla debil', nextAction: 'Verificar fecha manualmente' }
  }
  if (line.reactivation_flag) {
    return { severity: 'WARNING', severityLabel: 'Reactivado', nextAction: 'Verificar que no sea doble conteo' }
  }
  if (conf === 'medium' && line.acquisition_type !== 'fleet_migration') {
    return { severity: 'WARNING', severityLabel: 'Fecha aproximada', nextAction: 'Revisar fecha de adquisicion' }
  }
  if (review === 'pending_review') {
    return { severity: 'WARNING', severityLabel: 'Pendiente revision', nextAction: 'Revisar en cola de anchor review' }
  }
  if (review === 'requires_supervisor_review') {
    return { severity: 'WARNING', severityLabel: 'Requiere supervisor', nextAction: 'Asignar a supervisor para revision' }
  }
  if (line.is_auto_payable_anchor) {
    return { severity: 'OK', severityLabel: 'Auto-pagable', nextAction: 'Listo para aprobar' }
  }
  if (review === 'approved_manual' || review === 'resolved_by_refresh') {
    return { severity: 'OK', severityLabel: 'Aprobado', nextAction: 'Revisado y aprobado' }
  }

  return { severity: 'OK', severityLabel: 'Pendiente', nextAction: 'Revisar' }
}

// ── Severity Colors ──────────────────────────────────────────────────

export const SEVERITY_COLORS: Record<SeverityLevel, { bg: string; border: string; text: string; dot: string }> = {
  CRITICAL: { bg: 'bg-red-100', border: 'border-red-300', text: 'text-red-800', dot: 'bg-red-500' },
  WARNING:  { bg: 'bg-amber-100', border: 'border-amber-300', text: 'text-amber-800', dot: 'bg-amber-500' },
  OK:       { bg: 'bg-green-100', border: 'border-green-300', text: 'text-green-800', dot: 'bg-green-500' },
}

// ── Severity Badge ───────────────────────────────────────────────────

export function SeverityBadge({ severity, label, className = '' }: {
  severity: SeverityLevel
  label?: string
  className?: string
}) {
  const c = SEVERITY_COLORS[severity]
  const displayLabel = label || severity
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${c.bg} ${c.border} ${c.text} ${className}`}>
      {displayLabel}
    </span>
  )
}

// ── Severity Dot ─────────────────────────────────────────────────────

export function SeverityDot({ severity, className = '' }: { severity: SeverityLevel; className?: string }) {
  const c = SEVERITY_COLORS[severity]
  return <span className={`inline-block w-2 h-2 rounded-full ${c.dot} ${className}`} title={severity} />
}

// ── Operational Summary Bar ──────────────────────────────────────────

export interface SummaryCounts {
  critical: number
  warning: number
  ok: number
  total: number
  paid: number
  noScout: number
  noLeadDate: number
  blockedAnchor: number
  observed: number
}

export function OperationalSummaryBar({
  counts,
  activeFilter,
  onFilterClick,
}: {
  counts: SummaryCounts
  activeFilter: string | null
  onFilterClick: (key: string | null) => void
}) {
  const items: { key: string; label: string; count: number; color: string }[] = [
    { key: 'CRITICAL', label: 'Criticos', count: counts.critical, color: 'border-l-red-500 bg-red-50 hover:bg-red-100' },
    { key: 'WARNING', label: 'Warnings', count: counts.warning, color: 'border-l-amber-500 bg-amber-50 hover:bg-amber-100' },
    { key: 'OK', label: 'OK', count: counts.ok, color: 'border-l-green-500 bg-green-50 hover:bg-green-100' },
    { key: 'PAID', label: 'Pagados', count: counts.paid, color: 'border-l-blue-500 bg-blue-50 hover:bg-blue-100' },
    { key: 'NO_SCOUT', label: 'Sin scout', count: counts.noScout, color: 'border-l-gray-400 bg-gray-50 hover:bg-gray-100' },
    { key: 'NO_LEAD', label: 'Sin fecha lead', count: counts.noLeadDate, color: 'border-l-orange-400 bg-orange-50 hover:bg-orange-100' },
    { key: 'BLOCKED_ANCHOR', label: 'Bloqueo ancla', count: counts.blockedAnchor, color: 'border-l-purple-400 bg-purple-50 hover:bg-purple-100' },
  ]

  return (
    <div className="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-gray-200 -mx-1 px-3 py-2 mb-2 flex items-center gap-1.5 overflow-x-auto shadow-sm">
      <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mr-1 whitespace-nowrap">
        Resumen
        <span className="ml-1 text-gray-400 font-normal">({counts.total})</span>
      </span>
      {items.filter(i => i.count > 0 || i.key === 'OK').map(item => (
        <button
          key={item.key}
          onClick={() => onFilterClick(activeFilter === item.key ? null : item.key)}
          className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border-l-2 border-r border-t border-b transition-colors whitespace-nowrap ${item.color} ${activeFilter === item.key ? 'ring-2 ring-blue-300' : ''}`}
        >
          <span className="font-mono font-bold text-[11px]">{item.count}</span>
          <span className="text-[10px] text-gray-500">{item.label}</span>
        </button>
      ))}
    </div>
  )
}

// ── Quick Filter Pills ──────────────────────────────────────────────

export interface QuickFilterOption {
  key: string
  label: string
  count?: number
}

export function QuickFilterPills({
  options,
  activeFilter,
  onFilterClick,
}: {
  options: QuickFilterOption[]
  activeFilter: string | null
  onFilterClick: (key: string | null) => void
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap mb-2">
      <span className="text-[10px] text-gray-400 uppercase tracking-wider mr-1">Filtros:</span>
      {options.map(opt => (
        <button
          key={opt.key}
          onClick={() => onFilterClick(activeFilter === opt.key ? null : opt.key)}
          className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors whitespace-nowrap ${
            activeFilter === opt.key
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-100'
          }`}
        >
          {opt.label}
          {opt.count !== undefined && opt.count > 0 && (
            <span className={`ml-1 px-1 rounded text-[9px] ${activeFilter === opt.key ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-500'}`}>
              {opt.count}
            </span>
          )}
        </button>
      ))}
      {activeFilter && (
        <button
          onClick={() => onFilterClick(null)}
          className="px-2 py-0.5 rounded text-[10px] font-medium border border-gray-300 text-gray-400 hover:text-red-500 hover:border-red-300 whitespace-nowrap"
        >
          Limpiar
        </button>
      )}
    </div>
  )
}

// ── Next Action Badge ────────────────────────────────────────────────

export function NextActionBadge({ action }: { action: string }) {
  return (
    <span className="text-[10px] text-gray-500 truncate max-w-[140px] block" title={action}>
      {action}
    </span>
  )
}
