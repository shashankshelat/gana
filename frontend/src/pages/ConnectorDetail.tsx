import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Copy, Play, TestTube, Loader2, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import { connectorApi, connectorAiApi, ingestionApi } from '../api/client';
import { Connector, ConnectorType } from '../types';
import ConfigForm from '../components/Common/ConfigForm';
import MappingEditor from '../components/Common/MappingEditor';
import ConnectorLogo from '../components/Connectors/ConnectorLogo';
import ConnectorAITab from '../components/Connectors/ConnectorAITab';
import { HEALTH, categoryOf, errorText, ingestionModes, relativeTime } from '../components/Connectors/catalog';
import { useAuthStore } from '../store/auth';
import { useToast } from '../hooks/useToast';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'settings', label: 'Settings' },
  { id: 'mapping', label: 'Mapping' },
  { id: 'ai', label: 'AI mapping' },
  { id: 'unmapped', label: 'Unmapped fields' },
] as const;
type TabId = typeof TABS[number]['id'];

export default function ConnectorDetail() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find(t => t.id === params.get('tab'))?.id ?? 'overview') as TabId;
  const setTab = (t: TabId) => setParams(t === 'overview' ? {} : { tab: t }, { replace: true });

  const cq = useQuery<Connector>({ queryKey: ['connectors', id], queryFn: () => connectorApi.get(id), refetchInterval: 15000 });
  const tq = useQuery<ConnectorType[]>({ queryKey: ['connector-types'], queryFn: connectorApi.getTypes });
  // Failed-event count for the AI tab badge, so pending work is visible from any tab
  const aq = useQuery({ queryKey: ['connector-ai', id], queryFn: () => connectorAiApi.get(id), refetchInterval: 30000 });

  if (cq.isPending) return <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />;
  if (cq.isError) {
    return (
      <div className="card p-6 space-y-3">
        <p className="text-sm text-red-600">Could not load this connector: {errorText(cq.error)}</p>
        <Link to="/connectors" className="btn-secondary inline-flex">Back to connectors</Link>
      </div>
    );
  }
  const c = cq.data;
  const type = tq.data?.find(t => t.type_id === c.connector_type);
  const health = HEALTH[c.health ?? (c.enabled ? 'waiting' : 'disabled')];
  const failed = aq.data?.failed_events_uncovered ?? 0;

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/connectors')} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 dark:hover:text-gray-200">
        <ArrowLeft className="w-4 h-4" /> Connectors
      </button>

      <div className="flex flex-wrap items-center gap-4">
        <ConnectorLogo typeId={c.connector_type} name={type?.display_name ?? c.name} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">{c.name}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {type?.display_name ?? c.connector_type} · {type ? categoryOf(type.category).label : ''}
          </p>
        </div>
        <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium', health.pill)} title={c.poll_error || c.health_detail}>
          <span className={clsx('w-2 h-2 rounded-full', health.dot)} />{health.label}
        </span>
      </div>

      <div className="flex gap-6 border-b border-gray-200 dark:border-gray-800 overflow-x-auto" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={clsx('pb-2.5 -mb-px text-sm font-medium border-b-2 whitespace-nowrap flex items-center gap-1.5',
              tab === t.id ? 'border-brand-600 text-brand-700 dark:text-brand-300' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200')}>
            {t.id === 'ai' && <Sparkles className="w-3.5 h-3.5" />}
            {t.label}
            {t.id === 'ai' && failed > 0 && <span className="badge badge-red">{failed}</span>}
          </button>
        ))}
      </div>

      {tab === 'overview' && <Overview connector={c} type={type} onGo={setTab} failed={failed} />}
      {tab === 'settings' && <SettingsTab connector={c} type={type} />}
      {tab === 'mapping' && <MappingTab connector={c} />}
      {tab === 'ai' && <ConnectorAITab connectorId={c.id} />}
      {tab === 'unmapped' && <UnmappedTab connectorId={c.id} onGo={setTab} />}
    </div>
  );
}

function Overview({ connector: c, type, onGo, failed }: { connector: Connector; type?: ConnectorType; onGo: (t: TabId) => void; failed: number }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ['connectors'] });
  const test = useMutation({
    mutationFn: () => connectorApi.test(c.id) as Promise<{ success: boolean; message: string }>,
    onSuccess: d => (d.success ? toast.success(d.message, 'Test passed') : toast.error(d.message, 'Test failed')),
    onError: e => toast.error(errorText(e), 'Test failed'),
  });
  const poll = useMutation({
    mutationFn: () => connectorApi.poll(c.id) as Promise<{ new_events?: number }>,
    onSuccess: d => { refresh(); toast.success(`${d.new_events ?? 0} new events`, 'Polled'); },
    onError: e => toast.error(errorText(e), 'Poll failed'),
  });
  const routes = Array.isArray(c.mapping_rules?._routes) ? (c.mapping_rules._routes as unknown[]).length : 0;
  const webhookUrl = `${window.location.origin}${c.webhook_url}`;

  const stat = (label: string, value: ReactNode, sub?: ReactNode) => (
    <div className="card p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-xl font-semibold text-gray-900 dark:text-white mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stat('Events processed', c.events_processed.toLocaleString(), c.events_failed ? <span className="text-red-500">{c.events_failed.toLocaleString()} failed</span> : 'none failed')}
        {stat('Last event', relativeTime(c.last_event_at), c.last_event_at ? new Date(c.last_event_at + 'Z').toLocaleString() : undefined)}
        {stat('Last poll', type?.supports_polling ? relativeTime(c.last_polled_at) : 'Push only', c.poll_error || c.poll_status || undefined)}
        {stat('OCSF classification', routes ? `${routes} routes` : 'Flat mapping', 'class assigned per event')}
      </div>

      {failed > 0 && (
        <button onClick={() => onGo('ai')} className="w-full flex items-center gap-3 p-4 rounded-lg border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-900/20 text-left">
          <Sparkles className="w-5 h-5 text-red-600" />
          <span className="text-sm text-red-800 dark:text-red-300">
            <b>{failed}</b> failed {failed === 1 ? 'event is' : 'events are'} waiting for a mapping fix. Open AI mapping →
          </span>
        </button>
      )}

      <div className="card p-5 space-y-4">
        <h3 className="font-semibold text-gray-900 dark:text-white">How data arrives</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">{c.health_detail}. Method: {type ? ingestionModes(type).join(' + ') : '—'}.</p>
        {type?.supports_webhook && (
          <div className="flex gap-2">
            <code className="input font-mono text-xs flex-1 truncate">{webhookUrl}</code>
            <button className="btn-secondary" onClick={() => { navigator.clipboard.writeText(webhookUrl); toast.info('Webhook URL copied'); }}>
              <Copy className="w-4 h-4" /> Copy
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />} Test connection
          </button>
          {type?.supports_polling && (
            <button className="btn-secondary" onClick={() => poll.mutate()} disabled={poll.isPending || !c.enabled}>
              {poll.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Poll now
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function SettingsTab({ connector: c, type }: { connector: Connector; type?: ConnectorType }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const canEdit = useAuthStore(s => s.can('write'));
  const [name, setName] = useState(c.name);
  const [description, setDescription] = useState(c.description ?? '');
  const [config, setConfig] = useState<Record<string, unknown>>(c.config ?? {});
  useEffect(() => { setName(c.name); setDescription(c.description ?? ''); setConfig(c.config ?? {}); }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    // Secrets come back masked as "***"; the API keeps the stored value when they are unchanged
    mutationFn: () => connectorApi.update(c.id, { name: name.trim(), description, config }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['connectors'] }); toast.success('Settings saved'); },
    onError: e => toast.error(errorText(e), 'Could not save'),
  });
  const toggle = useMutation({
    mutationFn: () => connectorApi.update(c.id, { enabled: !c.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connectors'] }),
    onError: e => toast.error(errorText(e), 'Could not change status'),
  });

  return (
    <div className="card p-5 space-y-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-gray-900 dark:text-white">Enabled</p>
          <p className="text-sm text-gray-500">Disabled connectors stop polling and reject webhooks.</p>
        </div>
        <button type="button" role="switch" aria-checked={c.enabled} disabled={!canEdit || toggle.isPending} onClick={() => toggle.mutate()}
          className={clsx('relative inline-flex h-6 w-11 rounded-full border-2 border-transparent transition-colors', c.enabled ? 'bg-brand-600' : 'bg-gray-200 dark:bg-gray-700')}>
          <span className={clsx('inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform', c.enabled ? 'translate-x-5' : 'translate-x-0')} />
        </button>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div><label className="label">Name</label><input className="input" value={name} onChange={e => setName(e.target.value)} disabled={!canEdit} /></div>
        <div><label className="label">Description</label><input className="input" value={description} onChange={e => setDescription(e.target.value)} disabled={!canEdit} /></div>
      </div>
      {type && Object.keys(type.config_schema.properties ?? {}).length > 0 && (
        <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
          <ConfigForm schema={type.config_schema} values={config} onChange={(k, v) => setConfig(x => ({ ...x, [k]: v }))} />
        </div>
      )}
      {canEdit && (
        <div className="flex justify-end">
          <button className="btn-primary" disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save settings'}</button>
        </div>
      )}
    </div>
  );
}

function MappingTab({ connector: c }: { connector: Connector }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const canEdit = useAuthStore(s => s.can('approve'));
  const [rules, setRules] = useState<Record<string, unknown>>(c.mapping_rules ?? {});
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!dirty) setRules(c.mapping_rules ?? {}); }, [c.mapping_rules]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () => connectorApi.update(c.id, { mapping_rules: rules }),
    onSuccess: () => { setDirty(false); qc.invalidateQueries({ queryKey: ['connectors'] }); toast.success('Mapping saved and live'); },
    onError: e => toast.error(errorText(e), 'Could not save mapping'),
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Direct edits go live immediately. For reviewed changes, use the <b>AI mapping</b> tab: proposals go through Approvals.
      </p>
      <div className="card p-5">
        <MappingEditor mapping={rules} onChange={m => { setRules(m); setDirty(true); }} />
      </div>
      {canEdit && (
        <div className="flex justify-end gap-2">
          {dirty && <button className="btn-ghost" onClick={() => { setRules(c.mapping_rules ?? {}); setDirty(false); }}>Discard</button>}
          <button className="btn-primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save mapping'}</button>
        </div>
      )}
    </div>
  );
}

function UnmappedTab({ connectorId, onGo }: { connectorId: string; onGo: (t: TabId) => void }) {
  const q = useQuery({ queryKey: ['ingestion-unmapped', connectorId], queryFn: () => ingestionApi.unmapped(connectorId), refetchInterval: 30000 });
  if (q.isPending) return <div className="card h-48 animate-pulse bg-gray-100 dark:bg-gray-800" />;
  if (q.isError) return <div className="card p-6 text-sm text-red-600">Could not load unmapped fields: {errorText(q.error)}</div>;
  const fields = (q.data.fields ?? []) as { id: string; field_path: string; occurrences: number; coverage_pct: number | null; sample_values: unknown[] }[];
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Raw fields no mapping rule reads, grouped by event type. To cover them, paste an example event in the{' '}
        <button className="underline text-brand-600" onClick={() => onGo('ai')}>AI mapping</button> tab or edit the mapping.
      </p>
      <div className="card overflow-hidden">
        {fields.length === 0 ? (
          <p className="p-5 text-sm text-gray-500">No unmapped fields recorded for this connector.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500">
              <tr><th className="text-left font-medium px-4 py-2">Field</th><th className="text-right font-medium px-3 py-2">Seen</th><th className="text-right font-medium px-3 py-2">% of events</th><th className="text-left font-medium px-4 py-2">Samples</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {fields.map(f => (
                <tr key={f.id}>
                  <td className="px-4 py-2 font-mono text-xs text-gray-900 dark:text-white">{f.field_path}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{f.occurrences.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{f.coverage_pct != null ? `${f.coverage_pct}%` : '—'}</td>
                  <td className="px-4 py-2"><div className="flex flex-wrap gap-1">{f.sample_values.slice(0, 3).map((v, i) => <span key={i} className="font-mono text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 max-w-[14rem] truncate">{String(v)}</span>)}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
