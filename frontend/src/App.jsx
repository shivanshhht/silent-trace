import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/shell/AppShell.jsx'
import { InvestigationProvider } from './state/InvestigationContext.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import NetworkPage from './pages/NetworkPage.jsx'
import EntitiesPage from './pages/EntitiesPage.jsx'
import EvidencePage from './pages/EvidencePage.jsx'
import TimelinePage from './pages/TimelinePage.jsx'
import AnalyticsPage from './pages/AnalyticsPage.jsx'
import LeadsPage from './pages/LeadsPage.jsx'
import './styles/pages.css'

export default function App() {
  return (
    <InvestigationProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/network" element={<NetworkPage />} />
          <Route path="/entities" element={<EntitiesPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/leads" element={<LeadsPage />} />
          <Route path="*" element={<OverviewPage />} />
        </Routes>
      </AppShell>
    </InvestigationProvider>
  )
}
