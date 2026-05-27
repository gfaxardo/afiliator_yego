import { useState, useEffect, useCallback } from 'react'
import type { CanonicalDriver, ScoutResponse } from '../../api/scoutLiq'
import { getScouts, createAssignment } from '../../api/scoutLiq'

interface DriverDetailDrawerProps {
  driver: CanonicalDriver
  onClose: () => void
  onDriverUpdated: () => void
}

const GREEN  = 'bg-emerald-100 text-emerald-700'
const YELLOW = 'bg-amber-100 text-amber-700'
const RED    = 'bg-red-100 text-red-700'
const BLUE   = 'bg-blue-100 text-blue-700'
const GRAY   = 'bg-gray-100 text-gray-500'

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${color}`}>{label}</span>
}

function F({ label, value, mono }: { label: string; value: string | number | null | undefined; mono?: boolean }) {
  return (
    <div className="flex items-center px-3 py-1.5 text-xs">
      <span className="text-gray-400 w-28 shrink-0">{label}</span>
      <span className={`text-gray-700 truncate ${mono ? 'font-mono' : ''}`}>
        {value !== null && value !== undefined ? String(value) : '\u2014'}
      </span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-3 py-1.5 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
      <div className="divide-y divide-gray-100">{children}</div>
    </div>
  )
}

function deriveLifecycle(row: CanonicalDriver): string {
  if (row.attribution_status === 'unassigned') return 'sin_scout'
  if (row.converted_5v14d) return 'converted_5v14d'
  if (row.converted_5v7d) return 'converted_5v7d'
  if (row.activated_flag) return 'activated'
  if (row.driver_id) return 'no_trips'
  return 'no_driver_id'
}

const LIFECYCLE_LABELS: Record<string, string> = {
  no_driver_id: 'Sin ID', no_trips: 'Sin viajes', sin_scout: 'Sin scout',
  activated: 'Activado', converted_5v7d: '5V/7D', converted_5v14d: '5V/14D',
}

const PAYMENT_LABELS: Record<string, string> = {
  payable: 'Pagable', paid: 'Pagado', no_payable: 'No pagable', revisar: 'Revisar',
}

const REASON_LABELS: Record<string, string> = {
  no_scout: 'Sin scout', no_activation: 'Sin activacion',
  already_paid: 'Ya pagado', min_activated_not_reached: 'Minimo no alcanzado',
  tier_not_reached: 'No alcanzo tier', manual_review: 'Revision manual',
  ok: 'Pagable',
}

const PAYMENT_ORIGIN_LABELS: Record<string, string> = {
  cutoff: 'Corte', historical_upload: 'Historico', manual: 'Manual', none: '\u2014',
}

export default function DriverDetailDrawer({ driver, onClose, onDriverUpdated }: DriverDetailDrawerProps) {
  const lifecycle = deriveLifecycle(driver)
  const paymentOrigin = driver.payment_origin || 'none'
  const payStatus = driver.payment_status || 'no_payable'
  const payLabel = PAYMENT_LABELS[payStatus] || payStatus

  const [showAssignModal, setShowAssignModal] = useState(false)
  const [scouts, setScouts] = useState<ScoutResponse[]>([])
  const [scoutSearch, setScoutSearch] = useState('')
  const [selectedScoutId, setSelectedScoutId] = useState<number | null>(null)
  const [assignNotes, setAssignNotes] = useState('')
  const [assigning, setAssigning] = useState(false)
  const [assignError, setAssignError] = useState<string | null>(null)
  const [assignSuccess, setAssignSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (showAssignModal) {
      getScouts({ status: 'active' }).then(setScouts).catch(() => setScouts([]))
    }
  }, [showAssignModal])

  useEffect(() => {
    setAssignError(null)
    setAssignSuccess(null)
    setSelectedScoutId(null)
    setAssignNotes('')
    setScoutSearch('')
  }, [showAssignModal])

  const filteredScouts = scouts.filter(s =>
    !scoutSearch || s.scout_name.toLowerCase().includes(scoutSearch.toLowerCase())
  )

  const handleAssign = useCallback(async () => {
    if (!selectedScoutId || !driver.driver_id) return
    setAssigning(true)
    setAssignError(null)
    try {
      const result = await createAssignment({
        driver_id: driver.driver_id,
        scout_id: selectedScoutId,
        notes: assignNotes || 'Asignado desde Centro Operativo',
      })
      if (result.status === 'skipped_duplicate') {
        setAssignError('El conductor ya tiene un scout asignado activamente.')
        return
      }
      if (result.status === 'created') {
        setAssignSuccess(`Scout asignado correctamente (id=${result.id})`)
        onDriverUpdated()
        setTimeout(() => setShowAssignModal(false), 1200)
        return
      }
      setAssignError(result.detail || 'Error inesperado al asignar.')
    } catch (e: any) {
      setAssignError(e?.response?.data?.detail || e.message || 'Error al asignar scout.')
    } finally {
      setAssigning(false)
    }
  }, [selectedScoutId, driver.driver_id, assignNotes, onDriverUpdated])

  function buildBlockingReasons(): { label: string; active: boolean }[] {
    return [
      { label: 'Sin scout', active: driver.attribution_status === 'unassigned' },
      { label: 'Duplicado', active: driver.payment_status === 'paid' },
      { label: 'Ya pagado', active: driver.payment_status === 'paid' },
      { label: 'Fuente debil', active: driver.source_driver_status === 'weak' },
      { label: 'Revision manual', active: driver.reason === 'manual_review' },
    ]
  }

  const hasAssignableDriver = !!driver.driver_id
  const isUnassigned = driver.attribution_status === 'unassigned' && driver.scout_id == null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white shadow-xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-800">{driver.driver_name || driver.driver_id || 'Sin nombre'}</h3>
            <p className="text-[10px] text-gray-400 font-mono">{driver.driver_id || 'Sin ID'}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none px-2">&times;</button>
        </div>

        <div className="p-4 space-y-4">
          <Section title="Identidad">
            <F label="Driver ID" value={driver.driver_id} mono />
            <F label="Nombre" value={driver.driver_name} />
            <F label="Licencia" value={driver.license} mono />
            <F label="Origen" value={driver.origin} />
            <F label="Ciudad" value={driver.city} />
            <F label="Estado lifecycle" value={LIFECYCLE_LABELS[lifecycle] || lifecycle} />
          </Section>

          <Section title="Fechas">
            <F label="Fecha ancla" value={driver.anchor_date ? driver.anchor_date.substring(0, 10) : null} />
            <F label="Fuente ancla" value={driver.anchor_source} />
            <F label="Confianza" value={driver.anchor_confidence} />
            <F label="Warning" value={driver.anchor_warning} />
            <F label="Anchor type" value={driver.anchor_type} />
            <F label="Date basis" value={driver.date_basis} />
            <F label="Gap dias" value={driver.anchor_gap_days != null ? `${driver.anchor_gap_days}d` : null} />
            <F label="Hire date ref" value={driver.hire_date_reference ? driver.hire_date_reference.substring(0, 10) : null} />
            <F label="Hire date" value={driver.hire_date} />
            <F label="Semana ISO" value={driver.iso_week_label} />
            <F label="Lead cab." value={driver.lead_created_at_cabinet ? driver.lead_created_at_cabinet.substring(0, 10) : null} />
            <F label="Lead fleet" value={driver.lead_created_at_fleet ? driver.lead_created_at_fleet.substring(0, 10) : null} />
            <F label="Actualizado" value={driver.source_updated_at} />
            <F label="Fuente oper." value={'module_ct_cabinet_drivers'} />
          </Section>

          <Section title="Scout">
            <F label="Scout" value={driver.scout_name || 'Sin scout'} />
            <F label="Supervisor" value={driver.supervisor_name} />
            <F label="Estado asig." value={driver.attribution_status} />
          </Section>

          <Section title="Progreso">
            <F label="Viajes 7D" value={driver.trips_7d} />
            <F label="Viajes 14D" value={driver.trips_14d} />
            <F label="Activado (1+)" value={driver.activated_flag ? 'Si' : 'No'} />
            <F label="5V/7D" value={driver.converted_5v7d ? 'Si' : 'No'} />
            <F label="5V/14D" value={driver.converted_5v14d ? 'Si' : 'No'} />
          </Section>

          <Section title="Pago">
            <F label="Estado" value={payLabel} />
            <F label="Monto" value={driver.amount ? `S/ ${driver.amount.toLocaleString()}` : '\u2014'} />
            <F label="Origen" value={PAYMENT_ORIGIN_LABELS[paymentOrigin] || paymentOrigin} />
            <F label="Motivo" value={REASON_LABELS[driver.reason] || driver.reason || '\u2014'} />
            <F label="Base activada" value={driver.counts_as_activated_base ? 'Si' : 'No'} />
            <F label="Calidad 5V/7D" value={driver.counts_as_quality_5v7d ? 'Si' : 'No'} />
            <F label="Cuenta para pago" value={driver.counts_for_payment ? 'Si' : 'No'} />
            {driver.scout_tier_amount > 0 && (
              <>
                <F label="Scout: base" value={driver.scout_activated_base} />
                <F label="Scout: calidad" value={driver.scout_quality_5v7d} />
                <F label="Scout: conv %" value={`${(driver.scout_conversion_rate_5v7d * 100).toFixed(0)}%`} />
                <F label="Scout: tier S/" value={driver.scout_tier_amount.toFixed(0)} />
              </>
            )}
          </Section>

          <Section title="Bloqueos / Flags">
            {buildBlockingReasons().map((b, i) => (
              <div key={i} className="flex items-center px-3 py-1.5 text-xs">
                <span className="text-gray-400 w-28 shrink-0">{b.label}</span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${b.active ? RED : 'bg-gray-50 text-gray-300'}`}>
                  {b.active ? 'ACTIVO' : 'OK'}
                </span>
              </div>
            ))}
            {driver.reason && driver.reason !== 'ok' && (
              <div className="flex items-center px-3 py-1.5 text-xs">
                <span className="text-gray-400 w-28 shrink-0">Motivo pago</span>
                <span className="text-amber-600 text-[11px]">{REASON_LABELS[driver.reason] || driver.reason}</span>
              </div>
            )}
          </Section>

          <Section title="Acciones">
            <div className="px-3 py-2 space-y-1.5">
              <a href={`/scout-liq/operation`}
                className="block w-full text-center px-3 py-1.5 bg-blue-50 text-blue-700 rounded text-xs hover:bg-blue-100 font-medium">
                Ver en Operacion
              </a>
              {isUnassigned && hasAssignableDriver ? (
                <button onClick={() => setShowAssignModal(true)}
                  className="block w-full text-center px-3 py-1.5 bg-emerald-600 text-white rounded text-xs hover:bg-emerald-700 font-semibold">
                  Asignar scout
                </button>
              ) : !hasAssignableDriver ? (
                <button disabled
                  className="block w-full text-center px-3 py-1.5 bg-gray-50 text-gray-400 rounded text-xs font-medium cursor-not-allowed"
                  title="No se puede asignar sin driver_id">
                  Asignar scout (sin driver_id)
                </button>
              ) : (
                <button disabled
                  className="block w-full text-center px-3 py-1.5 bg-gray-50 text-gray-400 rounded text-xs font-medium cursor-not-allowed"
                  title="El conductor ya tiene scout asignado">
                  Scout ya asignado
                </button>
              )}
              <a href="/scout-liq/anchor"
                className="block w-full text-center px-3 py-1.5 bg-amber-50 text-amber-700 rounded text-xs hover:bg-amber-100 font-medium">
                Ver en Anchor / Diagnostico
              </a>
              <a href="/scout-liq/review-queue"
                className="block w-full text-center px-3 py-1.5 bg-purple-50 text-purple-700 rounded text-xs hover:bg-purple-100 font-medium">
                Ver en Review Queue
              </a>
              <a href={`/scout-liq/paid-history`}
                className="block w-full text-center px-3 py-1.5 bg-gray-50 text-gray-600 rounded text-xs hover:bg-gray-100 font-medium">
                Ver historial de pagos
              </a>
            </div>
          </Section>

          <Section title="Fuente">
            <F label="Source status" value={driver.source_driver_status} />
            <F label="Origen source" value={driver.origin} />
            <F label="Form. pago" value={driver.payment_formula_label} />
            <F label="Regla pago" value={driver.payment_rule_label} />
          </Section>
        </div>

        {/* ── Asignar Scout Modal ── */}
        {showAssignModal && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center">
            <div className="absolute inset-0 bg-black/40" onClick={() => setShowAssignModal(false)} />
            <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm mx-4 max-h-[80vh] flex flex-col">
              <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <h4 className="text-sm font-bold text-gray-800">Asignar scout</h4>
                <button onClick={() => setShowAssignModal(false)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
              </div>
              <div className="px-4 py-3 space-y-3 overflow-y-auto">
                <div className="bg-gray-50 rounded-lg p-2.5 text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Driver:</span>
                    <span className="font-medium">{driver.driver_name || driver.driver_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">ID:</span>
                    <span className="font-mono text-gray-600">{driver.driver_id}</span>
                  </div>
                  {driver.license && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">Licencia:</span>
                      <span className="font-mono text-gray-600">{driver.license}</span>
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-[10px] text-gray-400 uppercase mb-1">Buscar scout activo</label>
                  <input type="text" value={scoutSearch} onChange={e => setScoutSearch(e.target.value)}
                    placeholder="Nombre del scout..."
                    className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:border-blue-400" />
                </div>

                <div className="max-h-40 overflow-y-auto border rounded divide-y divide-gray-100">
                  {filteredScouts.length === 0 ? (
                    <div className="px-3 py-4 text-xs text-gray-400 text-center">No se encontraron scouts activos.</div>
                  ) : (
                    filteredScouts.map(s => (
                      <button key={s.id}
                        onClick={() => setSelectedScoutId(s.id === selectedScoutId ? null : s.id)}
                        className={`w-full text-left px-3 py-2 text-xs hover:bg-blue-50 transition-colors ${
                          s.id === selectedScoutId ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                        }`}>
                        <div className="font-semibold text-gray-800">{s.scout_name}</div>
                        <div className="text-gray-400">{s.scout_type || 'General'} {s.city ? `· ${s.city}` : ''}</div>
                      </button>
                    ))
                  )}
                </div>

                <div>
                  <label className="block text-[10px] text-gray-400 uppercase mb-1">Notas (opcional)</label>
                  <input type="text" value={assignNotes} onChange={e => setAssignNotes(e.target.value)}
                    placeholder="Ej: Asignado desde Centro Operativo"
                    className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:border-blue-400" />
                </div>

                {assignError && (
                  <div className="bg-red-50 border border-red-200 text-red-700 rounded px-3 py-1.5 text-xs">{assignError}</div>
                )}
                {assignSuccess && (
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded px-3 py-1.5 text-xs">{assignSuccess}</div>
                )}
              </div>
              <div className="px-4 py-3 border-t border-gray-200 flex gap-2">
                <button onClick={() => setShowAssignModal(false)}
                  className="flex-1 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 rounded-lg border border-gray-200">
                  Cancelar
                </button>
                <button onClick={handleAssign}
                  disabled={!selectedScoutId || assigning}
                  className="flex-1 px-3 py-2 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 font-semibold disabled:opacity-50">
                  {assigning ? 'Asignando...' : 'Confirmar asignacion'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
