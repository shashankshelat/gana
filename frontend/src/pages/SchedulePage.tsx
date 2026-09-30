import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, connectorApi } from '../api/client';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/auth';
import Modal from '../components/Common/Modal';
import EmptyState from '../components/Common/EmptyState';
import ConfirmDialog from '../components/Common/ConfirmDialog';
import { Connector } from '../types';
import { Clock, Plus, Play, Trash2, CheckCircle, XCircle, Pause } from 'lucide-react';
import clsx from 'clsx';

interface CronJob {
  id: string;
  connector_id: string;
  connector_name: string;
  cron_expression: string;
  description: string;
  enabled: boolean;
  last_run_at: string | null;
  last_events_fetched: number;
  last_result: string | null;
  last_error: string | null;
  created_at: string;
}

const PRESETS = [
  { label: 'Every 5 min', value: '*/5 * * * *' },
  { label: 'Every 15 min', value: '*/15 * * * *' },
  { label: 'Every 30 min', value: '*/30 * * * *' },
  { label: 'Hourly', value: '0 * * * *' },
  { label: 'Every 4 hours', value: '0 */4 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
];

export default function SchedulePage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const can = useAuthStore(s => s.can);
  const [formOpen, setFormOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({ connector_id: '', cron_expression: '*/15 * * * *', description: '' });

  const { data: jobs = [], isLoading } = useQuery<CronJob[]>({
    queryKey: ['cron-jobs'],
    queryFn: () => api.get('/cron').then(r => r.data),
    refetchInterval: 15000,
  });

  const { data: connectors = [] } = useQuery<Connector[]>({
    queryKey: ['connectors'],
    queryFn: connectorApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () => api.post('/cron', form),
    onSuccess: () => { toast.success('Schedule created'); setFormOpen(false); qc.invalidateQueries({ queryKey: ['cron-jobs'] }); },
    onError: () => toast.error('Failed to create schedule'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.patch(`/cron/${id}`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cron-jobs'] }),
  });

  const runNowMutation = useMutation({
    mutationFn: (id: string) => api.post(`/cron/${id}/run`),
    onSuccess: (res) => toast.success(`Fetched ${res.data.events_fetched ?? 0} events`),
    onError: () => toast.error('Manual run failed'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/cron/${id}`),
    onSuccess: () => { toast.success('Schedule deleted'); setDeleteId(null); qc.invalidateQueries({ queryKey: ['cron-jobs'] }); },
  });

  const RESULT_STYLES: Record<string, string> = {
    success: 'badge-green',
    error: 'badge-red',
    partial: 'badge-yellow',
    empty: 'badge-gray',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Clock className="w-6 h-6 text-gray-400" /> Schedules
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Automate connector polling with cron expressions</p>
        </div>
        {can('write') && (
          <button onClick={() => setFormOpen(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Add Schedule
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : jobs.length === 0 ? (
        <EmptyState icon={Clock} title="No schedules configured" description="Create a schedule to automatically poll your connectors on a recurring basis." action={can('write') ? { label: 'Add Schedule', onClick: () => setFormOpen(true) } : undefined} />
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <div key={job.id} className={clsx('card p-4 flex items-center gap-4', !job.enabled && 'opacity-60')}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-gray-900 dark:text-white truncate">{job.connector_name}</p>
                  <code className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded font-mono">{job.cron_expression}</code>
                  {job.last_result && <span className={clsx('badge', RESULT_STYLES[job.last_result])}>{job.last_result}</span>}
                </div>
                <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
                  {job.last_run_at && <span>Last run: {new Date(job.last_run_at).toLocaleString()}</span>}
                  {job.last_events_fetched > 0 && <span>{job.last_events_fetched} events</span>}
                  {job.last_error && <span className="text-red-500 truncate max-w-xs">{job.last_error}</span>}
                </div>
              </div>
              {can('write') && (
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button onClick={() => runNowMutation.mutate(job.id)} disabled={runNowMutation.isPending} className="btn-ghost text-xs p-2" title="Run now">
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => toggleMutation.mutate({ id: job.id, enabled: !job.enabled })} className="btn-ghost text-xs p-2" title={job.enabled ? 'Pause' : 'Enable'}>
                    {job.enabled ? <Pause className="w-3.5 h-3.5" /> : <CheckCircle className="w-3.5 h-3.5" />}
                  </button>
                  <button onClick={() => setDeleteId(job.id)} className="btn-ghost text-xs p-2 text-red-500" title="Delete">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title="New Schedule" size="md">
        <div className="space-y-4">
          <div>
            <label className="label">Connector *</label>
            <select className="input" value={form.connector_id} onChange={e => setForm(f => ({ ...f, connector_id: e.target.value }))}>
              <option value="">Select connector...</option>
              {connectors.map(c => <option key={c.id} value={c.id}>{c.name} ({c.connector_type})</option>)}
            </select>
          </div>

          <div>
            <label className="label">Cron Expression *</label>
            <input className="input font-mono" value={form.cron_expression} onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))} placeholder="*/15 * * * *" />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {PRESETS.map(p => (
                <button key={p.value} onClick={() => setForm(f => ({ ...f, cron_expression: p.value }))} className={clsx('text-xs px-2 py-1 rounded-md border transition-colors', form.cron_expression === p.value ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400' : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400')}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="label">Description (optional)</label>
            <input className="input" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setFormOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={() => createMutation.mutate()} disabled={!form.connector_id || !form.cron_expression || createMutation.isPending} className="btn-primary">
              {createMutation.isPending ? 'Creating...' : 'Create Schedule'}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog open={Boolean(deleteId)} title="Delete Schedule" message="This schedule will be permanently removed. The connector will no longer be polled automatically." confirmLabel="Delete" danger onConfirm={() => deleteId && deleteMutation.mutate(deleteId)} onCancel={() => setDeleteId(null)} />
    </div>
  );
}
