import { useState } from 'react'
import { getScouts } from '../../api/scoutLiq'
import {
  createManualPayment,
  getManualPayments,
  approveManualPayment,
  markManualPaymentPaid,
  ManualPaymentItem,
} from '../../api/scoutLiq'

export default function ManualPaymentView() {
  const [scouts, setScouts] = useState<any[]>([])
  const [payments, setPayments] = useState<ManualPaymentItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [form, setForm] = useState({
    scout_id: 0,
    driver_id: '',
    driver_license_raw: '',
    payment_rule: '',
    amount: 0,
    reason: '',
  })

  async function loadScouts() {
    try {
      const data = await getScouts({ status: 'active' })
      setScouts(data)
    } catch (e: any) {
      setError('Error al cargar scouts')
    }
  }

  async function loadPayments() {
    try {
      const data = await getManualPayments()
      setPayments(data)
    } catch (e: any) {
      setError('Error al cargar pagos')
    }
  }

  async function handleCreate() {
    if (!form.scout_id || !form.amount || !form.reason) {
      setError('Scout, monto y motivo son obligatorios')
      return
    }
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const r = await createManualPayment({
        scout_id: form.scout_id,
        driver_id: form.driver_id || undefined,
        driver_license_raw: form.driver_license_raw || undefined,
        payment_rule: form.payment_rule || undefined,
        amount: form.amount,
        reason: form.reason,
      })
      setSuccess(`Pago manual #${r.id} creado en estado: ${r.status}`)
      setForm({ scout_id: 0, driver_id: '', driver_license_raw: '', payment_rule: '', amount: 0, reason: '' })
      await loadPayments()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Error al crear')
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(id: number) {
    try {
      await approveManualPayment(id)
      setSuccess(`Pago #${id} aprobado`)
      await loadPayments()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Error al aprobar')
    }
  }

  async function handleMarkPaid(id: number) {
    try {
      await markManualPaymentPaid(id)
      setSuccess(`Pago #${id} marcado como pagado`)
      await loadPayments()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Error al marcar pagado')
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Pagos Manuales</h2>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h3 className="font-medium">Nuevo Pago Manual</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scout *</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={form.scout_id || ''}
                onChange={(e) => setForm({ ...form, scout_id: Number(e.target.value) })}
                placeholder="ID del scout"
                className="border border-gray-300 rounded px-3 py-2 text-sm w-28"
              />
              <button onClick={loadScouts} className="bg-gray-100 text-gray-600 px-3 py-2 rounded text-xs hover:bg-gray-200">
                Cargar Scouts
              </button>
            </div>
            {scouts.length > 0 && (
              <select
                onChange={(e) => setForm({ ...form, scout_id: Number(e.target.value) })}
                className="border border-gray-300 rounded px-2 py-1 text-sm mt-1 w-full"
              >
                <option value="">Seleccionar scout...</option>
                {scouts.map((s) => (
                  <option key={s.id} value={s.id}>{s.id} - {s.scout_name}</option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Driver ID</label>
            <input
              type="text"
              value={form.driver_id}
              onChange={(e) => setForm({ ...form, driver_id: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Licencia Driver</label>
            <input
              type="text"
              value={form.driver_license_raw}
              onChange={(e) => setForm({ ...form, driver_license_raw: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Regla de Pago</label>
            <input
              type="text"
              value={form.payment_rule}
              onChange={(e) => setForm({ ...form, payment_rule: e.target.value })}
              placeholder="ej: conexion, 1_viaje, manual"
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monto *</label>
            <input
              type="number"
              step="0.01"
              value={form.amount || ''}
              onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Motivo *</label>
            <input
              type="text"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            />
          </div>
        </div>
        <button
          onClick={handleCreate}
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Creando...' : 'Crear Pago Manual'}
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm">{success}</div>}

      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-medium">Pagos Manuales Existentes</h3>
          <button onClick={loadPayments} className="bg-gray-100 text-gray-600 px-3 py-1 rounded text-xs hover:bg-gray-200">Refrescar</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Scout</th>
                <th className="px-3 py-2">Driver</th>
                <th className="px-3 py-2">Regla</th>
                <th className="px-3 py-2">Monto</th>
                <th className="px-3 py-2">Estado</th>
                <th className="px-3 py-2">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} className="border-t border-gray-100">
                  <td className="px-3 py-2">{p.id}</td>
                  <td className="px-3 py-2">{p.scout_id}</td>
                  <td className="px-3 py-2">{p.driver_id || p.driver_license_raw || '-'}</td>
                  <td className="px-3 py-2 max-w-[120px] truncate">{p.payment_rule || '-'}</td>
                  <td className="px-3 py-2">S/ {Number(p.amount).toFixed(2)}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      p.status === 'paid' ? 'bg-green-100 text-green-700' :
                      p.status === 'approved' ? 'bg-blue-100 text-blue-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>{p.status}</span>
                  </td>
                  <td className="px-3 py-2 space-x-1">
                    {p.status === 'draft' && (
                      <button onClick={() => handleApprove(p.id)} className="text-blue-600 hover:underline text-xs">Aprobar</button>
                    )}
                    {p.status === 'approved' && (
                      <button onClick={() => handleMarkPaid(p.id)} className="text-green-600 hover:underline text-xs">Pagar</button>
                    )}
                    {p.status === 'paid' && (
                      <span className="text-gray-400 text-xs">Pagado</span>
                    )}
                  </td>
                </tr>
              ))}
              {payments.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-4 text-center text-gray-400">Sin pagos manuales</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
