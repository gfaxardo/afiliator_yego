import { useEffect, useState } from 'react'
import {
  getSourceDrivers,
  getUnassignedDrivers,
  getAssignments,
  getScouts,
  getSourceSummary,
  createAssignment,
  deactivateAssignment,
  uploadAssignments,
  SourceDriver,
  Assignment,
  ScoutResponse,
  AssignmentUploadResult,
  SourceSummary,
} from '../../api/scoutLiq'

export default function AtribucionView() {
  const [tab, setTab] = useState<'drivers' | 'unassigned' | 'assignments' | 'upload'>('drivers')
  const [drivers, setDrivers] = useState<SourceDriver[]>([])
  const [driversTotal, setDriversTotal] = useState(0)
  const [unassigned, setUnassigned] = useState<SourceDriver[]>([])
  const [unassignedTotal, setUnassignedTotal] = useState(0)
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [scouts, setScouts] = useState<ScoutResponse[]>([])
  const [summary, setSummary] = useState<SourceSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<AssignmentUploadResult | null>(null)

  // Assign modal state
  const [assignDriverId, setAssignDriverId] = useState('')
  const [assignScoutId, setAssignScoutId] = useState('')
  const [assignNotes, setAssignNotes] = useState('')
  const [assignResult, setAssignResult] = useState<any>(null)

  const [driverSearch, setDriverSearch] = useState('')

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([
      getSourceDrivers({ limit: 50 }),
      getUnassignedDrivers({ limit: 50 }),
      getAssignments({ status: 'active' }),
      getScouts({ status: 'active' }),
      getSourceSummary(),
    ])
      .then(([d, u, a, s, sum]) => {
        setDrivers(d.drivers)
        setDriversTotal(d.total)
        setUnassigned(u.drivers)
        setUnassignedTotal(u.total)
        setAssignments(a)
        setScouts(s)
        setSummary(sum)
      })
      .catch((err) => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleAssign = async () => {
    if (!assignDriverId || !assignScoutId) return
    setLoading(true)
    try {
      const r = await createAssignment({
        driver_id: assignDriverId,
        scout_id: parseInt(assignScoutId),
        notes: assignNotes || undefined,
      })
      setAssignResult(r)
      setAssignDriverId('')
      setAssignNotes('')
      load()
    } catch (err: any) {
      setAssignResult({ error: err.response?.data?.detail || err.message })
    } finally {
      setLoading(false)
    }
  }

  const handleDeactivate = async (id: number) => {
    if (!confirm('Desactivar esta asignacion?')) return
    try {
      await deactivateAssignment(id)
      load()
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    try {
      const r = await uploadAssignments(file)
      setUploadResult(r)
      load()
    } catch (err: any) {
      setUploadResult({ 
        total_rows: 0, created: 0, skipped_duplicates: 0, 
        invalid_driver: 0, invalid_scout: 0, missing_hire_date_warnings: 0,
        errors: [err.response?.data?.detail || err.message], warnings: []
      })
    } finally {
      setLoading(false)
    }
  }

  const filteredDrivers = driverSearch
    ? drivers.filter((d) => d.driver_id?.includes(driverSearch) || d.driver_nombre?.toLowerCase().includes(driverSearch.toLowerCase()))
    : drivers

  if (loading && drivers.length === 0) return <div className="text-gray-500">Cargando...</div>

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">{error}</div>
      )}

      {/* Warning alert */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-800 text-sm">
        <strong>Advertencia:</strong> viajes_0_7 es booleano. Antes de cerrar el motor de pago debe confirmarse si este flag representa 5 viajes en 7 dias o solo actividad en los primeros 7 dias.
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white border rounded p-4 text-center">
            <div className="text-2xl font-bold text-blue-700">{summary.total_rows}</div>
            <div className="text-xs text-gray-500 mt-1">Total Drivers Fuente</div>
          </div>
          <div className="bg-white border rounded p-4 text-center">
            <div className="text-2xl font-bold text-green-700">{summary.assigned_drivers}</div>
            <div className="text-xs text-gray-500 mt-1">Asignados</div>
          </div>
          <div className="bg-white border rounded p-4 text-center">
            <div className="text-2xl font-bold text-orange-700">{summary.unassigned_drivers}</div>
            <div className="text-xs text-gray-500 mt-1">Sin Asignar</div>
          </div>
          <div className="bg-white border rounded p-4 text-center">
            <div className="text-2xl font-bold text-gray-700">{summary.with_trips_0_7}</div>
            <div className="text-xs text-gray-500 mt-1">Con viajes 0-7d</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {(['drivers', 'unassigned', 'assignments'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              tab === t ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t === 'drivers' && `Drivers Fuente (${driversTotal})`}
            {t === 'unassigned' && `Sin Scout (${unassignedTotal})`}
            {t === 'assignments' && `Asignaciones (${assignments.length})`}
          </button>
        ))}
      </div>

      {/* Tab: Drivers */}
      {tab === 'drivers' && (
        <div>
          <div className="flex gap-2 mb-4">
            <input
              placeholder="Buscar por driver_id o nombre..."
              value={driverSearch}
              onChange={(e) => setDriverSearch(e.target.value)}
              className="border rounded px-3 py-2 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="bg-white border rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left p-2">driver_id</th>
                  <th className="text-left p-2">Nombre</th>
                  <th className="text-left p-2">Origen</th>
                  <th className="text-left p-2">hire_date</th>
                  <th className="text-left p-2">7d</th>
                  <th className="text-left p-2">14d</th>
                  <th className="text-left p-2">Orders</th>
                  <th className="text-left p-2">Estado</th>
                  <th className="text-left p-2">Accion</th>
                </tr>
              </thead>
              <tbody>
                {filteredDrivers.map((d) => (
                  <tr key={d.driver_id} className="border-t hover:bg-gray-50">
                    <td className="p-2 font-mono text-xs">{d.driver_id?.substring(0, 8)}...</td>
                    <td className="p-2">{[d.driver_nombre, d.driver_apellido].filter(Boolean).join(' ') || '-'}</td>
                    <td className="p-2">{d.origin || '-'}</td>
                    <td className="p-2">{d.hire_date_parsed || d.hire_date_raw || '-'}</td>
                    <td className="p-2">{d.has_trips_0_7_flag ? <span className="text-green-600">Si</span> : <span className="text-gray-400">No</span>}</td>
                    <td className="p-2">{d.has_trips_8_14_flag ? <span className="text-green-600">Si</span> : <span className="text-gray-400">No</span>}</td>
                    <td className="p-2">{d.total_orders ?? '-'}</td>
                    <td className="p-2">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        d.source_status === 'ok' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                      }`}>
                        {d.source_status}
                      </span>
                    </td>
                    <td className="p-2">
                      <button
                        onClick={() => { setAssignDriverId(d.driver_id || ''); setAssignScoutId('') }}
                        className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
                      >
                        Asignar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredDrivers.length === 0 && (
              <div className="p-8 text-center text-gray-400">No se encontraron drivers</div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Unassigned */}
      {tab === 'unassigned' && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left p-2">driver_id</th>
                <th className="text-left p-2">Nombre</th>
                <th className="text-left p-2">Origen</th>
                <th className="text-left p-2">hire_date</th>
                <th className="text-left p-2">Orders</th>
                <th className="text-left p-2">Accion</th>
              </tr>
            </thead>
            <tbody>
              {unassigned.map((d) => (
                <tr key={d.driver_id} className="border-t hover:bg-gray-50">
                  <td className="p-2 font-mono text-xs">{d.driver_id?.substring(0, 8)}...</td>
                  <td className="p-2">{[d.driver_nombre, d.driver_apellido].filter(Boolean).join(' ') || '-'}</td>
                  <td className="p-2">{d.origin || '-'}</td>
                  <td className="p-2">{d.hire_date_parsed || d.hire_date_raw || '-'}</td>
                  <td className="p-2">{d.total_orders ?? '-'}</td>
                  <td className="p-2">
                    <button
                      onClick={() => { setAssignDriverId(d.driver_id || ''); setAssignScoutId('') }}
                      className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
                    >
                      Asignar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {unassigned.length === 0 && (
            <div className="p-8 text-center text-gray-400">Todos los drivers tienen scout asignado</div>
          )}
        </div>
      )}

      {/* Tab: Assignments */}
      {tab === 'assignments' && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left p-2">ID</th>
                <th className="text-left p-2">driver_id</th>
                <th className="text-left p-2">Scout</th>
                <th className="text-left p-2">Origen</th>
                <th className="text-left p-2">hire_date</th>
                <th className="text-left p-2">Estado</th>
                <th className="text-left p-2">Accion</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.id} className="border-t hover:bg-gray-50">
                  <td className="p-2 font-mono">{a.id}</td>
                  <td className="p-2 font-mono text-xs">{a.driver_id?.substring(0, 8)}...</td>
                  <td className="p-2 font-medium">{a.scout_name || `#${a.scout_id}`}</td>
                  <td className="p-2">{a.source_origin || a.origin || '-'}</td>
                  <td className="p-2">{a.source_hire_date_raw || a.hire_date || '-'}</td>
                  <td className="p-2">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      a.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>{a.status}</span>
                  </td>
                  <td className="p-2">
                    {a.status === 'active' && (
                      <button
                        onClick={() => handleDeactivate(a.id)}
                        className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200"
                      >
                        Desactivar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {assignments.length === 0 && (
            <div className="p-8 text-center text-gray-400">No hay asignaciones</div>
          )}
        </div>
      )}

      {/* Assign Modal (inline) */}
      {(assignDriverId) && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md shadow-xl">
            <h3 className="font-semibold mb-4">Asignar Driver a Scout</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Driver ID</label>
                <input value={assignDriverId} disabled className="w-full border rounded px-3 py-2 text-sm bg-gray-50" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Scout</label>
                <select
                  value={assignScoutId}
                  onChange={(e) => setAssignScoutId(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Seleccionar scout...</option>
                  {scouts.filter((s) => s.status === 'active').map((s) => (
                    <option key={s.id} value={s.id}>{s.scout_name} (ID: {s.id})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Notas</label>
                <input
                  value={assignNotes}
                  onChange={(e) => setAssignNotes(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            {assignResult && (
              <div className={`mt-3 p-2 rounded text-sm ${
                assignResult.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
              }`}>
                {assignResult.error || `Asignacion creada: ID ${assignResult.id}`}
              </div>
            )}
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => { setAssignDriverId(''); setAssignResult(null) }} className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
                Cancelar
              </button>
              <button onClick={handleAssign} disabled={!assignScoutId} className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                Asignar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
