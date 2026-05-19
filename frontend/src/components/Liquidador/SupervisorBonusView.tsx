import { useState } from 'react'
import {
  getScouts,
  listCutoffs,
  createBonus,
  getBonuses,
  approveBonus,
  markBonusPaid,
  calculateCommissions,
  getCommissions,
  markCommissionPaid,
  BonusItem,
  CommissionItem,
} from '../../api/scoutLiq'

export default function SupervisorBonusView() {
  const [tab, setTab] = useState<'commission' | 'bonus'>('commission')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Supervisores y Bonos</h2>

      <div className="flex gap-2 border-b border-gray-200 mb-4">
        <button
          onClick={() => setTab('commission')}
          className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
            tab === 'commission' ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Comision Supervisores
        </button>
        <button
          onClick={() => setTab('bonus')}
          className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
            tab === 'bonus' ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Bono Mejor Scout
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}

      {tab === 'commission' && (
        <CommissionPanel setError={setError} setSuccess={setSuccess} />
      )}
      {tab === 'bonus' && (
        <BonusPanel setError={setError} setSuccess={setSuccess} />
      )}
    </div>
  )
}

function CommissionPanel({ setError, setSuccess }: { setError: (e: string | null) => void; setSuccess: (e: string | null) => void }) {
  const [cutoffs, setCutoffs] = useState<any[]>([])
  const [cutoffId, setCutoffId] = useState(0)
  const [rate, setRate] = useState(0.10)
  const [loading, setLoading] = useState(false)
  const [commissions, setCommissions] = useState<CommissionItem[]>([])
  const [calcResult, setCalcResult] = useState<any[] | null>(null)

  async function loadCutoffs() {
    try {
      const data = await listCutoffs()
      setCutoffs(data)
    } catch (e: any) { setError('Error al cargar cortes') }
  }

  async function loadCommissions() {
    try {
      const data = await getCommissions(cutoffId || undefined)
      setCommissions(data)
    } catch (e: any) { setError('Error al cargar comisiones') }
  }

  async function handleCalculate() {
    if (!cutoffId) return
    setLoading(true)
    setError(null)
    try {
      const r = await calculateCommissions(cutoffId, rate)
      setCalcResult(r)
      setSuccess(`Comisiones calculadas: ${r.length} supervisores`)
      await loadCommissions()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Error al calcular')
    } finally { setLoading(false) }
  }

  async function handleMarkPaid(id: number) {
    try {
      await markCommissionPaid(id)
      setSuccess(`Comision #${id} pagada`)
      await loadCommissions()
    } catch (e: any) { setError(e.response?.data?.detail || 'Error') }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h3 className="font-medium">Calcular Comision de Supervisores</h3>
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Corte</label>
            <div className="flex gap-2">
              <input type="number" value={cutoffId || ''} onChange={(e) => setCutoffId(Number(e.target.value))}
                placeholder="ID del corte" className="border border-gray-300 rounded px-3 py-2 text-sm w-32" />
              <button onClick={loadCutoffs} className="bg-gray-100 text-gray-600 px-3 py-2 rounded text-xs hover:bg-gray-200">Cargar</button>
            </div>
            {cutoffs.length > 0 && (
              <select onChange={(e) => setCutoffId(Number(e.target.value))} className="border border-gray-300 rounded px-2 py-1 text-sm mt-1 w-full">
                <option value="">Seleccionar...</option>
                {cutoffs.filter(c => c.status === 'paid').map(c => (
                  <option key={c.id} value={c.id}>{c.id} - {c.cutoff_name} ({c.status})</option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">% Comision</label>
            <input type="number" step="0.01" min="0" max="1" value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-24" />
          </div>
          <button onClick={handleCalculate} disabled={loading || !cutoffId}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Calculando...' : 'Calcular'}
          </button>
          <button onClick={loadCommissions} className="bg-gray-100 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-200">Refrescar</button>
        </div>
      </div>

      {calcResult && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <h4 className="font-medium text-green-800 mb-2">Resultado Calculo</h4>
          {calcResult.map((r: any, i: number) => (
            <div key={i} className="text-sm mb-2">
              <span className="font-medium">Supervisor {r.supervisor_id}:</span> Base S/ {Number(r.base_amount).toFixed(2)} x {Number(r.commission_rate) * 100}% = S/ {Number(r.commission_amount).toFixed(2)}
              <div className="text-xs text-gray-500 ml-4">
                Scouts: {r.scouts?.map((s: any) => `${s.scout_name} (S/ ${Number(s.amount).toFixed(2)})`).join(', ')}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="font-medium mb-3">Comisiones Registradas</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Corte</th>
              <th className="px-3 py-2">Supervisor</th>
              <th className="px-3 py-2">Base</th>
              <th className="px-3 py-2">%</th>
              <th className="px-3 py-2">Comision</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Accion</th>
            </tr>
          </thead>
          <tbody>
            {commissions.map((c) => (
              <tr key={c.id} className="border-t border-gray-100">
                <td className="px-3 py-2">{c.id}</td>
                <td className="px-3 py-2">{c.cutoff_run_id}</td>
                <td className="px-3 py-2">{c.supervisor_id}</td>
                <td className="px-3 py-2">S/ {Number(c.base_amount).toFixed(2)}</td>
                <td className="px-3 py-2">{Number(c.commission_rate) * 100}%</td>
                <td className="px-3 py-2">S/ {Number(c.commission_amount).toFixed(2)}</td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${c.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>{c.status}</span>
                </td>
                <td className="px-3 py-2">
                  {c.status === 'pending' && (
                    <button onClick={() => handleMarkPaid(c.id)} className="text-green-600 hover:underline text-xs">Pagar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BonusPanel({ setError, setSuccess }: { setError: (e: string | null) => void; setSuccess: (e: string | null) => void }) {
  const [bonuses, setBonuses] = useState<BonusItem[]>([])
  const [scouts, setScouts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({ scout_id: 0, amount: 0, reason: '', cutoff_run_id: 0 })

  async function loadData() {
    try {
      const [b, s] = await Promise.all([getBonuses(), getScouts({ status: 'active' })])
      setBonuses(b)
      setScouts(s)
    } catch (e: any) { setError('Error al cargar') }
  }

  async function handleCreate() {
    if (!form.scout_id || !form.amount || !form.reason) {
      setError('Scout, monto y motivo obligatorios')
      return
    }
    setLoading(true)
    try {
      await createBonus({
        scout_id: form.scout_id,
        amount: form.amount,
        reason: form.reason,
        cutoff_run_id: form.cutoff_run_id || undefined,
        bonus_type: 'best_scout',
      })
      setSuccess('Bono creado')
      setForm({ scout_id: 0, amount: 0, reason: '', cutoff_run_id: 0 })
      await loadData()
    } catch (e: any) { setError(e.response?.data?.detail || 'Error') }
    finally { setLoading(false) }
  }

  async function handleApprove(id: number) {
    try { await approveBonus(id); setSuccess(`Bono #${id} aprobado`); await loadData() }
    catch (e: any) { setError(e.response?.data?.detail || 'Error') }
  }

  async function handleMarkPaid(id: number) {
    try { await markBonusPaid(id); setSuccess(`Bono #${id} pagado`); await loadData() }
    catch (e: any) { setError(e.response?.data?.detail || 'Error') }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h3 className="font-medium">Nuevo Bono</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scout *</label>
            <div className="flex gap-2">
              <input type="number" value={form.scout_id || ''} onChange={(e) => setForm({ ...form, scout_id: Number(e.target.value) })}
                className="border border-gray-300 rounded px-3 py-2 text-sm w-28" />
              <button onClick={loadData} className="bg-gray-100 text-gray-600 px-3 py-2 rounded text-xs hover:bg-gray-200">Cargar</button>
            </div>
            {scouts.length > 0 && (
              <select onChange={(e) => setForm({ ...form, scout_id: Number(e.target.value) })}
                className="border border-gray-300 rounded px-2 py-1 text-sm mt-1 w-full">
                <option value="">Seleccionar scout...</option>
                {scouts.map(s => <option key={s.id} value={s.id}>{s.id} - {s.scout_name}</option>)}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Corte (opcional)</label>
            <input type="number" value={form.cutoff_run_id || ''} onChange={(e) => setForm({ ...form, cutoff_run_id: Number(e.target.value) })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monto *</label>
            <input type="number" step="0.01" value={form.amount || ''} onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Motivo *</label>
            <input type="text" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full" />
          </div>
        </div>
        <button onClick={handleCreate} disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          Crear Bono
        </button>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-medium">Bonos Registrados</h3>
          <button onClick={loadData} className="bg-gray-100 text-gray-600 px-3 py-1 rounded text-xs hover:bg-gray-200">Refrescar</button>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Scout</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Monto</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Accion</th>
            </tr>
          </thead>
          <tbody>
            {bonuses.map(b => (
              <tr key={b.id} className="border-t border-gray-100">
                <td className="px-3 py-2">{b.id}</td>
                <td className="px-3 py-2">{b.scout_id}</td>
                <td className="px-3 py-2">{b.bonus_type}</td>
                <td className="px-3 py-2">S/ {Number(b.amount).toFixed(2)}</td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${b.status === 'paid' ? 'bg-green-100 text-green-700' : b.status === 'approved' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'}`}>{b.status}</span>
                </td>
                <td className="px-3 py-2 space-x-1">
                  {b.status === 'draft' && <button onClick={() => handleApprove(b.id)} className="text-blue-600 hover:underline text-xs">Aprobar</button>}
                  {b.status === 'approved' && <button onClick={() => handleMarkPaid(b.id)} className="text-green-600 hover:underline text-xs">Pagar</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
