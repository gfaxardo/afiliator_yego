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
import CentroOperativoView from './components/Liquidador/CentroOperativoView'
import HealthDashboardView from './components/Liquidador/HealthDashboardView'
import AcquisitionAnchorView from './components/Liquidador/AcquisitionAnchorView'
import AnchorReviewQueueView from './components/Liquidador/AnchorReviewQueueView'
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
          {/* ── Centro Operativo: ruta principal e indice ── */}
          <Route index element={<Navigate to="centro-operativo" replace />} />
          <Route path="centro-operativo" element={<CentroOperativoView />} />

          {/* ── Redirects: flujos duplicados → Centro Operativo ── */}
          <Route path="liquidador" element={<Navigate to="/scout-liq/centro-operativo" replace />} />
          <Route path="pagos" element={<Navigate to="/scout-liq/centro-operativo" replace />} />
          <Route path="centro-carga" element={<Navigate to="/scout-liq/centro-operativo" replace />} />
          <Route path="unified-load" element={<Navigate to="/scout-liq/centro-operativo" replace />} />
          <Route path="reconciliation" element={<Navigate to="/scout-liq/centro-operativo" replace />} />

          {/* ── Vistas de detalle / solo lectura (sin CTA de flujo) ── */}
          <Route path="operation" element={<OperationView />} />
          <Route path="configuracion" element={<PaymentSchemesConfigView />} />
          <Route path="dashboard" element={<DashboardView />} />

          {/* ── Always-visible advanced routes (admin / auxiliares) ── */}
          <Route path="supervisor-bonus" element={<SupervisorBonusView />} />
          <Route path="paid-history" element={<PaidHistoryView />} />
          <Route path="historial" element={<Navigate to="/scout-liq/paid-history" replace />} />
          <Route path="scouts" element={<ScoutsList />} />
          <Route path="scouts/new" element={<CreateScout />} />
          <Route path="config" element={<ConfigView />} />

          {/* ── Legacy upload routes (ocultas sin flag, redirigen a Centro Operativo si no habilitadas) ── */}
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

          {/* Acquisition Anchor (detail / solo lectura) */}
          <Route path="anchor" element={<AcquisitionAnchorView />} />

          {/* Anchor Review Queue (herramienta de detalle) */}
          <Route path="review-queue" element={<AnchorReviewQueueView />} />
        </Route>
        <Route path="*" element={<Navigate to="/scout-liq" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
