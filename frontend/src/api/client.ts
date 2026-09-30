import axios from 'axios';

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

export const connectorApi = {
  getTypes: () => api.get('/connectors/types').then(r => r.data),
  list: () => api.get('/connectors').then(r => r.data),
  get: (id: string) => api.get(`/connectors/${id}`).then(r => r.data),
  create: (data: unknown) => api.post('/connectors', data).then(r => r.data),
  update: (id: string, data: unknown) => api.patch(`/connectors/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/connectors/${id}`),
  test: (id: string) => api.post(`/connectors/${id}/test`).then(r => r.data),
  poll: (id: string) => api.post(`/connectors/${id}/poll`).then(r => r.data),
};

export const forwarderApi = {
  getTypes: () => api.get('/forwarders/types').then(r => r.data),
  list: () => api.get('/forwarders').then(r => r.data),
  get: (id: string) => api.get(`/forwarders/${id}`).then(r => r.data),
  create: (data: unknown) => api.post('/forwarders', data).then(r => r.data),
  update: (id: string, data: unknown) => api.patch(`/forwarders/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/forwarders/${id}`),
  test: (id: string) => api.post(`/forwarders/${id}/test`).then(r => r.data),
};

export const schemaApi = {
  getVersion: () => api.get('/schema/version').then(r => r.data),
  getClasses: () => api.get('/schema/classes').then(r => r.data),
  getCategories: () => api.get('/schema/categories').then(r => r.data),
  update: (force = false) => api.post(`/schema/update?force=${force}`).then(r => r.data),
  validate: (event: unknown) => api.post('/schema/validate', event).then(r => r.data),
};

export const pipelineApi = {
  getStats: () => api.get('/pipeline/stats').then(r => r.data),
  getHistory: (minutes = 60) => api.get(`/pipeline/history?minutes=${minutes}`).then(r => r.data),
  getOverview: () => api.get('/stats/overview').then(r => r.data),
};

export const ingestionApi = {
  summary: (days: number) => api.get(`/ingestion/summary?days=${days}`).then(r => r.data),
  unmapped: (connectorId?: string) =>
    api.get('/ingestion/unmapped', { params: connectorId ? { connector_id: connectorId } : {} }).then(r => r.data),
  sampleEvent: (fieldId: string) =>
    api.get('/ingestion/unmapped/sample-event', { params: { field_id: fieldId } }).then(r => r.data),
  resetUnmapped: (connectorId: string) => api.delete(`/ingestion/unmapped/${connectorId}`),
};

export interface ConnectorAISettings {
  auto_enabled: boolean;
  min_events: number;
  cooldown_minutes: number;
  daily_limit: number;
  max_samples: number;
  last_run_at: string | null;
  last_status: string | null;
  last_message: string | null;
  runs_today: number;
  runs_day: string | null;
}

export interface ConnectorAIProposal {
  id: string;
  status: 'pending' | 'approved' | 'rejected';
  source: string;
  created_by: string;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  routes: number;
  rules: number;
  failed_events: number;
  explanation: string;
}

export interface ConnectorAIState {
  settings: ConnectorAISettings;
  provider: string;
  model: string;
  key_configured: boolean;
  failed_events_uncovered: number;
  proposals: ConnectorAIProposal[];
}

export interface AIProposalResult {
  status: 'proposed' | 'skipped' | 'error';
  message: string;
  approval_id?: string;
  events?: number;
  routes_proposed?: number;
}

// AI mapping lives under each connector: automatic proposals from DLQ events, plus manual runs
export const connectorAiApi = {
  get: (id: string) => api.get<ConnectorAIState>(`/connectors/${id}/ai`).then(r => r.data),
  update: (id: string, data: Partial<ConnectorAISettings>) => api.put(`/connectors/${id}/ai`, data).then(r => r.data),
  run: (id: string) => api.post<AIProposalResult>(`/connectors/${id}/ai/run`).then(r => r.data),
  fromSamples: (id: string, sample_logs: string) =>
    api.post<AIProposalResult>(`/connectors/${id}/ai/samples`, { sample_logs }).then(r => r.data),
};
