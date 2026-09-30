import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore, applyTheme } from './store';
import Layout from './components/Layout/Layout';
import ProtectedRoute from './components/Common/ProtectedRoute';
import CommandPalette from './components/Common/CommandPalette';
import OnboardingWizard from './pages/OnboardingWizard';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Connectors from './pages/Connectors';
import Forwarders from './pages/Forwarders';
import SchemaPage from './pages/SchemaPage';
import PipelinePage from './pages/PipelinePage';
import ConnectorDetail from './pages/ConnectorDetail';
import ApprovalsPage from './pages/ApprovalsPage';
import SettingsPage from './pages/SettingsPage';
import ActivityLogPage from './pages/ActivityLogPage';
import DLQPage from './pages/DLQPage';
import AnomalyPage from './pages/AnomalyPage';
import SchedulePage from './pages/SchedulePage';
import UsersPage from './pages/UsersPage';
import IngestionPage from './pages/IngestionPage';
import { useAuthStore } from './store/auth';

export default function App() {
  const theme = useAppStore(s => s.theme);
  const isAuthenticated = useAuthStore(s => s.isAuthenticated());
  const [cmdOpen, setCmdOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => { applyTheme(theme); }, [theme]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdOpen(v => !v);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    if (isAuthenticated && !localStorage.getItem('onboarding_dismissed')) {
      setTimeout(() => setShowOnboarding(true), 500);
    }
  }, [isAuthenticated]);

  const dismissOnboarding = () => {
    localStorage.setItem('onboarding_dismissed', '1');
    setShowOnboarding(false);
  };

  return (
    <BrowserRouter>
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
      {showOnboarding && isAuthenticated && (
        <OnboardingWizard onDismiss={dismissOnboarding} />
      )}

      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="connectors" element={<Connectors />} />
          <Route path="forwarders" element={<Forwarders />} />
          <Route path="connectors/:id" element={<ConnectorDetail />} />
          <Route path="ai-mapping" element={<Navigate to="/connectors" replace />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="schema" element={<SchemaPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="ingestion" element={<IngestionPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="activity" element={<ActivityLogPage />} />
          <Route path="dlq" element={<DLQPage />} />
          <Route path="anomalies" element={<AnomalyPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="settings/users" element={<UsersPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
