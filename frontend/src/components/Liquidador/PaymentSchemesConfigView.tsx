import { useState, useEffect, useCallback } from 'react'
import {
  listPaymentSchemes, getPaymentSchemeDetail,
  createPaymentSchemeVersion, activatePaymentSchemeVersion,
  getPaymentSchemesHistory,
  type PaymentSchemeListItem, type PaymentSchemeDetail,
  type SchemeVersionDetail, type HistoryItem,
} from '../../api/scoutLiq'

// ── Label helpers ──

const RULE_LABELS: Record<string, string> = {
  '1V7D': '1 viaje en 7 dias',
  '5V7D': '5 viajes en 7 dias',
  '50V30D': '50 viajes en 30 dias',
}

const FORMULA_LABELS: Record<string, string> = {
  'ACTIVATED_X_TIER': 'Activados x Tier',
  'QUALITY_X_FIXED': 'Calidad x Fijo',
}

const PAYS_ON_LABELS: Record<string, string> = {
  'ACTIVATED_BASE': 'Base activada (volumen)',
  'QUALITY_HIT': 'Hito de calidad',
  'FIXED': 'Monto fijo',
}

const SCHEME_TYPE_LABELS: Record<string, string> = {
  cabinet: 'Cabinet',
  fleet: 'Fleet',
  custom: 'Custom',
}

const PAYS_ON_COLORS: Record<string, string> = {
  'ACTIVATED_BASE': 'bg-blue-100 text-blue-700 border-blue-200',
  'QUALITY_HIT': 'bg-purple-100 text-purple-700 border-purple-200',
  'FIXED': 'bg-gray-100 text-gray-700 border-gray-200',
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700 border-green-200',
  closed: 'bg-blue-100 text-blue-700 border-blue-200',
  draft: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  archived: 'bg-gray-100 text-gray-500 border-gray-200',
}

function statusLabel(v: SchemeVersionDetail): string {
  if (v.status === 'draft') return 'Borrador'
  if (v.status === 'archived') return 'Archivada'
  if (v.status === 'active' && !v.valid_to_cohort_iso_week) return 'Activa vigente'
  if (v.status === 'active' && v.valid_to_cohort_iso_week) return 'Cerrada'
  return v.status
}

function versionTypeLabel(v: SchemeVersionDetail): string | null {
  const name = (v.version_name || '').toLowerCase()
  if (name.includes('transition')) return 'TRANSICIÓN'
  if (name.includes('standard')) return 'ESTÁNDAR'
  return null
}

function versionTypeColor(v: SchemeVersionDetail): string {
  const label = versionTypeLabel(v)
  if (label === 'TRANSICIÓN') return 'bg-amber-100 text-amber-700 border-amber-200'
  if (label === 'ESTÁNDAR') return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  return ''
}

function versionTypeFromName(name: string | null): string | null {
  if (!name) return null
  const n = name.toLowerCase()
  if (n.includes('transition')) return 'TRANSICIÓN'
  if (n.includes('standard')) return 'ESTÁNDAR'
  return null
}

function versionTypeColorFromName(name: string | null): string {
  const label = versionTypeFromName(name)
  if (label === 'TRANSICIÓN') return 'bg-amber-100 text-amber-700 border-amber-200'
  if (label === 'ESTÁNDAR') return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  return ''
}

function statusColor(v: SchemeVersionDetail): string {
  if (v.status === 'draft') return STATUS_COLORS.draft
  if (v.status === 'archived') return STATUS_COLORS.archived
  if (v.status === 'active' && !v.valid_to_cohort_iso_week) return STATUS_COLORS.active
  if (v.status === 'active' && v.valid_to_cohort_iso_week) return STATUS_COLORS.closed
  return 'bg-gray-100 text-gray-600 border-gray-200'
}

function Badge({ label, color }: { label: string; color?: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border whitespace-nowrap ${color || 'bg-gray-100 text-gray-600 border-gray-200'}`}>
      {label}
    </span>
  )
}

// ── Main Component ──

export default function PaymentSchemesConfigView() {
  const [schemes, setSchemes] = useState<PaymentSchemeListItem[]>([])
  const [selectedScheme, setSelectedScheme] = useState<PaymentSchemeDetail | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Form state
  const [showCreateVersion, setShowCreateVersion] = useState(false)
  const [form, setForm] = useState({
    version_name: '',
    valid_from_cohort_iso_week: '',
    maturity_days: 7,
    min_activated: 8,
    activation_rule: '1V7D',
    quality_rule: '5V7D',
    formula_type: 'ACTIVATED_X_TIER',
    currency: 'PEN',
    tiers: [{ min_conversion_rate: 0.1, payout_amount: 10 }],
  })
  const [formError, setFormError] = useState<string | null>(null)

  const loadSchemes = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([listPaymentSchemes(), getPaymentSchemesHistory()])
      setSchemes(s)
      setHistory(h)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Error al cargar')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadSchemes() }, [loadSchemes])

  async function selectScheme(id: number) {
    setError(null)
    setSuccess(null)
    try {
      const detail = await getPaymentSchemeDetail(id)
      setSelectedScheme(detail)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  function validateForm(): boolean {
    if (!form.version_name.trim()) { setFormError('Nombre de versión requerido'); return false }
    if (!/^\d{4}-W\d{2}$/.test(form.valid_from_cohort_iso_week)) { setFormError('Formato de cohorte: YYYY-WNN (ej. 2026-W19)'); return false }
    if (form.maturity_days < 1) { setFormError('Días de maduración debe ser > 0'); return false }
    if (form.min_activated < 1) { setFormError('Mínimo de activados debe ser > 0'); return false }
    if (form.tiers.length < 1) { setFormError('Debe incluir al menos 1 tier'); return false }
    for (const t of form.tiers) {
      if (t.min_conversion_rate < 0 || t.min_conversion_rate > 1) { setFormError('Tasa de conversión debe estar entre 0 y 1'); return false }
      if (t.payout_amount < 0) { setFormError('Pago debe ser >= 0'); return false }
    }
    const rates = form.tiers.map(t => t.min_conversion_rate)
    if (new Set(rates).size !== rates.length) { setFormError('No se permiten tasas duplicadas'); return false }
    setFormError(null)
    return true
  }

  async function handleCreateVersion() {
    if (!selectedScheme || !validateForm()) return
    try {
      const result = await createPaymentSchemeVersion(selectedScheme.scheme_id, {
        ...form,
        tiers: form.tiers.map((t, i) => ({ ...t, sort_order: i })),
      })
      setSuccess(`Versión "${result.version_name}" creada como draft (id=${result.version_id})`)
      setShowCreateVersion(false)
      await selectScheme(selectedScheme.scheme_id)
      await loadSchemes()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  async function handleActivate(versionId: number, versionName: string) {
    if (!confirm(`¿Activar versión "${versionName}"?\n\nEsto cerrará automáticamente la versión activa anterior hasta la cohorte previa. Las cohortes ya calculadas o pagadas conservarán su snapshot histórico.`)) return
    try {
      const result = await activatePaymentSchemeVersion(versionId)
      setSuccess(`Versión "${result.version_name}" activada desde ${result.valid_from_cohort_iso_week}. ${result.previous_active_archived ? `"${result.previous_active_archived}" cerrada hasta ${result.previous_active_closed_at}.` : ''}`)
      if (selectedScheme) await selectScheme(selectedScheme.scheme_id)
      await loadSchemes()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  function addTier() {
    const last = form.tiers[form.tiers.length - 1]
    setForm({ ...form, tiers: [...form.tiers, { min_conversion_rate: Math.min(1, (last?.min_conversion_rate || 0.1) + 0.1), payout_amount: (last?.payout_amount || 10) + 10 }] })
  }

  function removeTier(idx: number) {
    if (form.tiers.length <= 1) return
    setForm({ ...form, tiers: form.tiers.filter((_, i) => i !== idx) })
  }

  // ── Active version for quick display ──
  const activeVersion = selectedScheme?.versions.find(v => v.status === 'active')

  if (loading) return <div className="text-gray-500 text-sm p-4">Cargando configuración...</div>

  return (
    <div className="flex gap-4 h-full" style={{ minHeight: 'calc(100vh - 140px)' }}>
      {/* ── LEFT: Schemes list ── */}
      <div className="w-80 flex-shrink-0 bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col">
        <div className="bg-gray-50 border-b border-gray-200 px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Esquemas de Pago
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
          {schemes.map(s => (
            <button
              key={s.scheme_id}
              onClick={() => selectScheme(s.scheme_id)}
              className={`w-full text-left px-3 py-2.5 text-xs hover:bg-blue-50 transition-colors ${
                selectedScheme?.scheme_id === s.scheme_id ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
              }`}
            >
              <div className="font-semibold text-gray-800">{s.name}</div>
              <div className="text-gray-400 mt-0.5 flex gap-2 items-center flex-wrap">
                <Badge label={SCHEME_TYPE_LABELS[s.scheme_type] || s.scheme_type} />
                {versionTypeFromName(s.active_version_name) && (
                  <Badge label={versionTypeFromName(s.active_version_name)!} color={versionTypeColorFromName(s.active_version_name)} />
                )}
                {s.active_version_name && (
                  <span className="text-green-600">{s.active_version_name} desde {s.active_since_cohort}</span>
                )}
              </div>
            </button>
          ))}
        </div>
        {/* ── History sidebar ── */}
        <div className="border-t border-gray-200 bg-gray-50 px-3 py-2">
          <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Histórico</div>
          <div className="max-h-40 overflow-y-auto space-y-0.5">
            {history.slice(0, 20).map((h, i) => (
              <div key={i} className="text-[10px] text-gray-500 flex gap-2">
                <span className="font-medium w-24 truncate">{h.scheme_name}</span>
                <span>{h.version_name}</span>
                <span className="text-gray-300">{h.valid_from_cohort_iso_week}→{h.valid_to_cohort_iso_week || '...'}</span>
                <Badge label={h.status} color={STATUS_COLORS[h.status] || 'bg-gray-100 text-gray-600 border-gray-200'} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── RIGHT: Detail ── */}
      <div className="flex-1 bg-white rounded-lg border border-gray-200 overflow-y-auto p-4 space-y-4">
        {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded px-3 py-2 text-xs">{error}</div>}
        {success && <div className="bg-green-50 border border-green-200 text-green-700 rounded px-3 py-2 text-xs">{success}</div>}

        {!selectedScheme ? (
          <div className="text-gray-400 text-sm text-center py-12">Selecciona un esquema para ver su detalle</div>
        ) : (
          <>
            {/* A. General */}
            <Section title="General">
              <F label="Nombre" value={selectedScheme.name} bold />
              <F label="Tipo" value={SCHEME_TYPE_LABELS[selectedScheme.scheme_type] || selectedScheme.scheme_type} />
              <F label="Descripción" value={selectedScheme.description} />
              <F label="Activo" value={selectedScheme.is_active ? 'Sí' : 'No'} />
            </Section>

            {/* B. Active version */}
            {activeVersion && (
              <Section title="Version Activa">
                <div className="flex items-center gap-2 px-3 py-1.5 text-xs">
                  <span className="text-gray-400 w-36 shrink-0">Version</span>
                  <span className="text-gray-700 font-medium">{activeVersion.version_name}</span>
                  {versionTypeLabel(activeVersion) && (
                    <Badge label={versionTypeLabel(activeVersion)!} color={versionTypeColor(activeVersion)} />
                  )}
                  {activeVersion.pays_on_rule && (
                    <Badge label={PAYS_ON_LABELS[activeVersion.pays_on_rule] || activeVersion.pays_on_rule}
                      color={PAYS_ON_COLORS[activeVersion.pays_on_rule] || 'bg-gray-100 text-gray-600 border-gray-200'} />
                  )}
                </div>
                <F label="Vigencia desde" value={activeVersion.valid_from_cohort_iso_week} mono />
                <F label="Vigencia hasta" value={activeVersion.valid_to_cohort_iso_week || 'Sin limite'} mono />
                <F label="Hito para volumen" value={RULE_LABELS[activeVersion.volume_rule || activeVersion.activation_rule] || activeVersion.volume_rule || activeVersion.activation_rule} mono bold />
                <F label="Hito de calidad" value={RULE_LABELS[activeVersion.counts_quality_rule || activeVersion.quality_rule] || activeVersion.counts_quality_rule || activeVersion.quality_rule} mono bold />
                <F label="Min. volumen" value={activeVersion.min_volume_count || activeVersion.min_activated} bold />
                <F label="Base pagable" value={PAYS_ON_LABELS[activeVersion.pays_on_rule] || activeVersion.pays_on_rule || '—'} />
                <F label="Formula de pago" value={FORMULA_LABELS[activeVersion.payout_formula_type || activeVersion.formula_type] || activeVersion.payout_formula_type || activeVersion.formula_type} bold />
                <F label="Ventana maduracion" value={`${activeVersion.maturity_window_days || activeVersion.maturity_days} dias`} />
                <F label="Moneda" value={activeVersion.currency} />
                <div className="px-3 py-1 text-[10px] text-gray-400">La version activa es de solo lectura. Para cambiar reglas, crea una nueva version.</div>
              </Section>
            )}
            {/* C. Tiers (active version) */}
            {activeVersion && activeVersion.tiers.length > 0 && (
              <Section title={`Tiers (${activeVersion.tiers.length})`}>
                <div className="grid grid-cols-2 gap-1 px-3 py-1 text-[10px] font-semibold text-gray-400 uppercase">
                  <span>Desde %</span><span>Pago</span>
                </div>
                {activeVersion.tiers.map((t, i) => (
                  <div key={i} className="grid grid-cols-2 gap-1 px-3 py-1 text-xs border-t border-gray-100">
                    <span className="font-mono font-semibold text-gray-700">{(t.min_conversion_rate * 100).toFixed(0)}%</span>
                    <span className="font-mono text-gray-700">S/ {t.payout_amount.toFixed(0)}</span>
                  </div>
                ))}
              </Section>
            )}

            {/* D. Historical versions */}
            <Section title={`Histórico de Versiones (${selectedScheme.versions.length})`}>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] text-gray-400 uppercase border-b border-gray-200">
                    <th className="px-2 py-1">Version</th>
                    <th className="px-2 py-1">Desde</th>
                    <th className="px-2 py-1">Hasta</th>
                    <th className="px-2 py-1">Volumen</th>
                    <th className="px-2 py-1">Min Vol</th>
                    <th className="px-2 py-1">Estado</th>
                    <th className="px-2 py-1">Accion</th>
                  </tr>
                </thead>
                <tbody>
                  {[...selectedScheme.versions].reverse().map(v => (
                    <tr key={v.version_id} className="border-t border-gray-50 hover:bg-gray-50">
                      <td className="px-2 py-1 font-medium text-gray-700">
                        <span>{v.version_name}</span>
                        {versionTypeLabel(v) && (
                          <Badge label={versionTypeLabel(v)!} color={versionTypeColor(v)} />
                        )}
                      </td>
                      <td className="px-2 py-1 font-mono text-gray-500">{v.valid_from_cohort_iso_week}</td>
                      <td className="px-2 py-1 font-mono text-gray-400">{v.valid_to_cohort_iso_week || '\u2014'}</td>
                      <td className="px-2 py-1 text-gray-600 font-mono text-[10px]">{(v.volume_rule || v.activation_rule)}</td>
                      <td className="px-2 py-1 text-gray-600">{v.min_volume_count || v.min_activated}</td>
                      <td className="px-2 py-1"><Badge label={statusLabel(v)} color={statusColor(v)} /></td>
                      <td className="px-2 py-1">
                        {v.status === 'draft' && (
                          <button onClick={() => handleActivate(v.version_id, v.version_name)}
                            className="text-[11px] bg-green-600 text-white px-2 py-0.5 rounded hover:bg-green-700 font-semibold">
                            Activar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            {/* Create version button / form */}
            <div className="border-t border-gray-200 pt-3">
              {!showCreateVersion ? (
                <button onClick={() => { setShowCreateVersion(true); setFormError(null); setSuccess(null); setError(null) }}
                  className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-semibold">
                  + Nueva versión desde cohorte
                </button>
              ) : (
                <div className="bg-blue-50/30 border border-blue-200 rounded-lg p-4 space-y-3">
                  <h4 className="text-sm font-semibold text-gray-800">Nueva versión desde cohorte</h4>

                  {formError && <div className="bg-red-50 border border-red-200 text-red-700 rounded px-3 py-1.5 text-xs">{formError}</div>}

                  <div className="grid grid-cols-3 gap-3">
                    <Field label="Nombre versión" value={form.version_name}
                      onChange={v => setForm({ ...form, version_name: v })} placeholder="v2" />
                    <Field label="Cohorte desde (YYYY-WNN)" value={form.valid_from_cohort_iso_week}
                      onChange={v => setForm({ ...form, valid_from_cohort_iso_week: v })} placeholder="2026-W19" mono />
                    <Field label="Maduración (días)" value={form.maturity_days}
                      onChange={v => setForm({ ...form, maturity_days: Number(v) || 0 })} type="number" />
                    <Field label="Mín. Activados" value={form.min_activated}
                      onChange={v => setForm({ ...form, min_activated: Number(v) || 0 })} type="number" />
                    <Field label="Regla activación" value={form.activation_rule}
                      onChange={v => setForm({ ...form, activation_rule: v })} />
                    <Field label="Regla calidad" value={form.quality_rule}
                      onChange={v => setForm({ ...form, quality_rule: v })} />
                    <Field label="Fórmula" value={form.formula_type}
                      onChange={v => setForm({ ...form, formula_type: v })} />
                    <Field label="Moneda" value={form.currency}
                      onChange={v => setForm({ ...form, currency: v })} />
                  </div>

                  {/* Tiers */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-gray-500">Tiers</span>
                      <button onClick={addTier} className="text-xs text-blue-600 hover:text-blue-800 font-medium">+ Agregar tier</button>
                    </div>
                    {form.tiers.map((t, i) => (
                      <div key={i} className="flex gap-2 items-center mb-1">
                        <span className="text-[10px] text-gray-400 w-6">#{i + 1}</span>
                        <input type="number" step="0.01" min="0" max="1" value={t.min_conversion_rate}
                          onChange={e => {
                            const nt = [...form.tiers]
                            nt[i] = { ...nt[i], min_conversion_rate: parseFloat(e.target.value) || 0 }
                            setForm({ ...form, tiers: nt })
                          }}
                          className="w-20 border border-gray-200 rounded px-2 py-1 text-xs font-mono" />
                        <span className="text-xs text-gray-400">→ S/</span>
                        <input type="number" step="1" min="0" value={t.payout_amount}
                          onChange={e => {
                            const nt = [...form.tiers]
                            nt[i] = { ...nt[i], payout_amount: parseFloat(e.target.value) || 0 }
                            setForm({ ...form, tiers: nt })
                          }}
                          className="w-24 border border-gray-200 rounded px-2 py-1 text-xs font-mono" />
                        {form.tiers.length > 1 && (
                          <button onClick={() => removeTier(i)} className="text-red-400 hover:text-red-600 text-xs">✕</button>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-2 pt-2">
                    <button onClick={handleCreateVersion} className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-semibold">
                      Crear versión draft
                    </button>
                    <button onClick={() => setShowCreateVersion(false)}
                      className="px-4 py-1.5 text-sm text-gray-500 hover:text-gray-700 rounded-lg border border-gray-200">
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Helpers ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-3 py-1.5 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
      <div className="divide-y divide-gray-100">{children}</div>
    </div>
  )
}

function F({ label, value, mono, bold }: { label: string; value: string | number | null | undefined; mono?: boolean; bold?: boolean }) {
  return (
    <div className="flex items-center px-3 py-1.5 text-xs">
      <span className="text-gray-400 w-36 shrink-0">{label}</span>
      <span className={`text-gray-700 truncate ${mono ? 'font-mono' : ''} ${bold ? 'font-medium' : ''}`}>
        {value !== null && value !== undefined ? String(value) : '—'}
      </span>
    </div>
  )
}

function Field({ label, value, onChange, type, placeholder, mono }: {
  label: string; value: string | number; onChange: (v: string) => void; type?: string; placeholder?: string; mono?: boolean
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-gray-400 uppercase">{label}</span>
      <input type={type || 'text'} value={value}
        onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className={`border border-gray-200 rounded px-2 py-1.5 text-xs focus:outline-none focus:border-blue-400 ${mono ? 'font-mono' : ''}`} />
    </label>
  )
}
