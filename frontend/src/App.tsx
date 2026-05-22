import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LiquidadorLayout from './components/Liquidador/LiquidadorLayout'
import HealthCheck from './components/Liquidador/HealthCheck'
import ScoutsList from './components/Liquidador/ScoutsList'
import CreateScout from './components/Liquidador/CreateScout'
import AtribucionView from './components/Liquidador/AtribucionView'
import ConfigView from './components/Liquidador/ConfigView'
import LiquidadorView from './components/Liquidador/LiquidadorView'
import HistoricalImportView from './components/Liquidador/HistoricalImportView'
import BulkScoutView from './components/Liquidador/BulkScoutView'
import SchemeVersionsView from './components/Liquidador/SchemeVersionsView'
import ManualPaymentView from './components/Liquidador/ManualPaymentView'
import SupervisorBonusView from './components/Liquidador/SupervisorBonusView'
import PaidHistoryView from './components/Liquidador/PaidHistoryView'
import AttributionImportView from './components/Liquidador/AttributionImportView'
import WorkbookImportView from './components/Liquidador/WorkbookImportView'
import OperationView from './components/Liquidador/OperationView'
import DashboardView from './components/Liquidador/DashboardView'
import PaymentSchemesConfigView from './components/Liquidador/PaymentSchemesConfigView'
import ReconciliationView from './components/Liquidador/ReconciliationView'
import UnifiedLoadView from './components/Liquidador/UnifiedLoadView'
import CentroCargaView from './components/Liquidador/CentroCargaView'
import HealthDashboardView from './components/Liquidador/HealthDashboardView'
import LegacyRedirectView from './components/Liquidador/LegacyRedirectView'
import PaymentView from './components/Liquidador/PaymentView'

const LEGACY_ENABLED = import.meta.env.VITE_ENABLE_LEGACY_IMPORTS === 'true'

function legacyRoute(name: string, RealComponent: React.ComponentType) {
  if (LEGACY_ENABLED) {
    return <Route path="" element={<RealComponent />} />
  }
  return <Route path="" element={<LegacyRedirectView name={name} />} />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/scout-liq" element={<LiquidadorLayout />}>
          <Route index element={<Navigate to="operation" replace />} />

          {/* ── Main visible routes ── */}
          <Route path="operation" element={<OperationView />} />
          <Route path="liquidador" element={<LiquidadorView />} />
          <Route path="centro-carga" element={<CentroCargaView />} />
          <Route path="configuracion" element={<PaymentSchemesConfigView />} />
          <Route path="pagos" element={<PaymentView />} />
          <Route path="dashboard" element={<DashboardView />} />

          {/* ── Redirects: unified-load y reconciliation al Centro de Carga ── */}
          <Route path="unified-load" element={<Navigate to="/scout-liq/centro-carga" replace />} />
          <Route path="reconciliation" element={<Navigate to="/scout-liq/centro-carga" replace />} />

          {/* ── Always-visible advanced routes ── */}
          <Route path="supervisor-bonus" element={<SupervisorBonusView />} />
          <Route path="paid-history" element={<PaidHistoryView />} />
          <Route path="historial" element={<PaidHistoryView />} />
          <Route path="scouts" element={<ScoutsList />} />
          <Route path="scouts/new" element={<CreateScout />} />
          <Route path="config" element={<ConfigView />} />

          {/* ── Legacy upload routes (ocultas sin flag) ── */}
          <Route path="historical">
            {legacyRoute('Historico (Carga Historica de Pagos)', HistoricalImportView)}
          </Route>
          <Route path="workbook">
            {legacyRoute('Import Integral (Workbook)', WorkbookImportView)}
          </Route>
          <Route path="attributions">
            {legacyRoute('Atribuciones Historicas', AttributionImportView)}
          </Route>
          <Route path="atribucion">
            {legacyRoute('Atribucion', AtribucionView)}
          </Route>
          <Route path="manual-payments">
            {legacyRoute('Pagos Manuales', ManualPaymentView)}
          </Route>
          <Route path="bulk-scouts">
            {legacyRoute('Carga Masiva de Scouts', BulkScoutView)}
          </Route>
          <Route path="schemes">
            {legacyRoute('Esquemas (Import XLSX)', SchemeVersionsView)}
          </Route>

          {/* Health */}
          <Route path="health" element={<HealthCheck />} />
          <Route path="salud" element={<HealthDashboardView />} />
        </Route>
        <Route path="*" element={<Navigate to="/scout-liq" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
