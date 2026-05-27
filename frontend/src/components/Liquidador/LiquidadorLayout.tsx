import { useState, useMemo } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'

const MAIN_TABS = [
  { to: '/scout-liq/centro-operativo', label: 'Centro Operativo' },
  { to: '/scout-liq/liquidaciones', label: 'Liquidaciones' },
]

const LEGACY_UPLOAD_TABS = [
  { to: '/scout-liq/historical', label: 'Historico' },
  { to: '/scout-liq/workbook', label: 'Import Integral' },
  { to: '/scout-liq/attributions', label: 'Atribuciones' },
  { to: '/scout-liq/atribucion', label: 'Atribucion' },
  { to: '/scout-liq/manual-payments', label: 'Pagos Manuales' },
  { to: '/scout-liq/bulk-scouts', label: 'Carga Masiva' },
  { to: '/scout-liq/schemes', label: 'Esquemas' },
  { to: '/scout-liq/liquidador', label: 'Liquidador (legacy)' },
  { to: '/scout-liq/pagos', label: 'Pagos (legacy)' },
  { to: '/scout-liq/centro-carga', label: 'Centro Carga (legacy)' },
]

const ALWAYS_ADVANCED_TABS = [
  { to: '/scout-liq/configuracion', label: 'Reglas de Pago' },
  { to: '/scout-liq/ejecutivo', label: 'Ejecutivo' },
  { to: '/scout-liq/dashboard', label: 'Dashboard' },
  { to: '/scout-liq/anchor', label: 'Anchor / Fechas' },
  { to: '/scout-liq/review-queue', label: 'Review Queue' },
  { to: '/scout-liq/salud', label: 'Salud de Data' },
  { to: '/scout-liq/operation', label: 'Operacion' },
  { to: '/scout-liq/supervisor-bonus', label: 'Sup & Bonos' },
  { to: '/scout-liq/paid-history', label: 'Historial Pagos' },
  { to: '/scout-liq/scouts', label: 'Scouts' },
  { to: '/scout-liq/config', label: 'Config' },
]

const isLegacyEnabled = () =>
  import.meta.env.VITE_ENABLE_LEGACY_IMPORTS === 'true'

export default function LiquidadorLayout() {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const location = useLocation()

  const ADVANCED_TABS = useMemo(() => {
    if (isLegacyEnabled()) {
      return [...LEGACY_UPLOAD_TABS, ...ALWAYS_ADVANCED_TABS]
    }
    return ALWAYS_ADVANCED_TABS
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-2 flex items-center justify-between">
        <h1 className="text-base font-semibold text-gray-800 tracking-tight">
          Liquidador de Calidad Scouts Yego
        </h1>
        <span className="text-xs text-gray-400">v1.0</span>
      </header>

      <nav className="bg-white border-b border-gray-200 px-6 flex items-center gap-0">
        {MAIN_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? 'border-blue-600 text-blue-700 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}

        <div className="relative ml-auto">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              ADVANCED_TABS.some(t => location.pathname === t.to)
                ? 'border-orange-500 text-orange-700'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            Avanzado ▾
          </button>
          {showAdvanced && (
            <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 w-48 py-1">
              {ADVANCED_TABS.map((tab) => (
                <NavLink
                  key={tab.to}
                  to={tab.to}
                  onClick={() => setShowAdvanced(false)}
                  className={({ isActive }) =>
                    `block px-4 py-1.5 text-sm transition-colors ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`
                  }
                >
                  {tab.label}
                </NavLink>
              ))}
            </div>
          )}
        </div>
      </nav>

      <main className="p-4">
        <Outlet />
      </main>
    </div>
  )
}
