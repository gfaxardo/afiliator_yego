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

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/scout-liq" element={<LiquidadorLayout />}>
          <Route index element={<Navigate to="operation" replace />} />
          <Route path="operation" element={<OperationView />} />
          <Route path="scouts" element={<ScoutsList />} />
          <Route path="scouts/new" element={<CreateScout />} />
          <Route path="config" element={<ConfigView />} />
          <Route path="configuracion" element={<PaymentSchemesConfigView />} />
          <Route path="atribucion" element={<AtribucionView />} />
          <Route path="liquidador" element={<LiquidadorView />} />
          <Route path="historical" element={<HistoricalImportView />} />
          <Route path="bulk-scouts" element={<BulkScoutView />} />
          <Route path="schemes" element={<SchemeVersionsView />} />
          <Route path="manual-payments" element={<ManualPaymentView />} />
          <Route path="supervisor-bonus" element={<SupervisorBonusView />} />
          <Route path="paid-history" element={<PaidHistoryView />} />
          <Route path="attributions" element={<AttributionImportView />} />
          <Route path="workbook" element={<WorkbookImportView />} />
          <Route path="dashboard" element={<DashboardView />} />
          <Route path="historial" element={<PaidHistoryView />} />
        </Route>
        <Route path="*" element={<Navigate to="/scout-liq" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
