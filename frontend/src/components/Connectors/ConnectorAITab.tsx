import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Sparkles, AlertTriangle, Loader2, ChevronDown, ChevronRight, Bot, User, ClipboardList } from 'lucide-react';
import clsx from 'clsx';
import { connectorAiApi, ConnectorAISettings, AIProposalResult } from '../../api/client';
import { useAuthStore } from '../../store/auth';
import { useToast } from '../../hooks/useToast';
import { errorText, relativeTime } from './catalog';

const SOURCE_LABEL: Record<string, { label: string; icon: typeof Bot }> = {
  dlq_auto: { label: 'Automatic · from failed events', icon: Bot },
  auto_ai: { label: 'Automatic', icon: Bot },
  dlq_ai: { label: 'Analyst · from failed events', icon: User },
  samples_ai: { label: 'Analyst · from samples', icon: ClipboardList },
  doc_update: { label: 'Vendor docs changed', icon: Bot },
  manual: { label: 'Manual', icon: User },
  ai: { label: 'AI Mapping', icon: User },
};

const STATUS_BADGE: Record<string, string> = { pending: 'badge-yellow', approved: 'badge-green', rejected: 'badge-red' };

export default function ConnectorAITab({ connectorId }: { connectorId: string }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const canEdit = useAuthStore(s => s.can('approve'));
  const [draft, setDraft] = useState<Partial<ConnectorAISettings>>({});
  const [samples, setSamples] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const q = useQuery({ queryKey: ['connector-ai', connectorId], queryFn: () => connectorAiApi.get(connectorId), refetchInterval: 30000 });
  useEffect(() => { setDraft({}); }, [connectorId]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['connector-ai', connectorId] });
    qc.invalidateQueries({ queryKey: ['approvals'] });
  };
  const announce = (r: AIProposalResult) =>
    r.status === 'proposed' ? toast.success(r.message, 'Sent to Approvals') : toast.info(r.message, 'Nothing proposed');

  const save = useMutation({
    mutationFn: () => connectorAiApi.update(connectorId, draft),
    onSuccess: () => { setDraft({}); refresh(); toast.success('AI mapping settings saved'); },
    onError: e => toast.error(errorText(e), 'Could not save'),
  });
  const run = useMutation({
    mutationFn: () => connectorAiApi.run(connectorId),
    onSuccess: r => { refresh(); announce(r); },
    onError: e => toast.error(errorText(e), 'AI proposal failed'),
  });
  const fromSamples = useMutation({
    mutationFn: () => connectorAiApi.fromSamples(connectorId, samples),
    onSuccess: r => { refresh(); announce(r); if (r.status === 'proposed') setSamples(''); },
    onError: e => toast.error(errorText(e), 'AI proposal failed'),
  });

  if (q.isPending) return <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />;
  if (q.isError) return <div className="card p-6 text-sm text-red-600">Could not load AI mapping: {errorText(q.error)}</div>;

  const d = q.data;
  const s = { ...d.settings, ...draft };
  const dirty = Object.keys(draft).length > 0;
  const pending = d.proposals.find(p => p.status === 'pending');
  const runBlocked = !d.key_configured ? 'Add an AI key first' : d.failed_events_uncovered === 0 ? 'No failed events to learn from' : '';

  const num = (key: keyof ConnectorAISettings, label: string, hint: string, min: number) => (
    <div>
      <label className="label">{label}</label>
      <input type="number" min={min} className="input" value={Number(s[key])} disabled={!canEdit}
        onChange={e => setDraft(x => ({ ...x, [key]: Math.max(min, Number(e.target.value)) }))} />
      <p className="text-xs text-gray-400 mt-1">{hint}</p>
    </div>
  );

  return (
    <div className="space-y-6">
      {!d.key_configured && (
        <div className="flex gap-3 p-4 rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 text-sm">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
          <p className="text-amber-800 dark:text-amber-300">
            AI mapping needs an API key. <Link to="/settings" className="underline font-medium">Add one in Settings → AI Providers</Link>, then use “Test Claude connection”.
          </p>
        </div>
      )}

      {/* Automatic mode */}
      <section className="card p-5 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2"><Bot className="w-4 h-4 text-brand-500" /> Automatic mapping from failed events</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-2xl">
              Every 5 minutes, if this connector has failed events that no pending proposal covers, GANA asks {d.model || 'the AI model'} for a
              corrected mapping (grouping events by type and picking the OCSF class for each) and sends it to <b>Approvals</b> for an analyst.
              Approving it applies the mapping and replays this connector’s failed events.
            </p>
          </div>
          <button
            type="button" role="switch" aria-checked={s.auto_enabled} disabled={!canEdit}
            onClick={() => setDraft(x => ({ ...x, auto_enabled: !s.auto_enabled }))}
            className={clsx('relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors', s.auto_enabled ? 'bg-brand-600' : 'bg-gray-200 dark:bg-gray-700')}
          >
            <span className={clsx('inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform', s.auto_enabled ? 'translate-x-5' : 'translate-x-0')} />
          </button>
        </div>

        <div className={clsx('grid sm:grid-cols-2 lg:grid-cols-4 gap-4', !s.auto_enabled && 'opacity-50')}>
          {num('min_events', 'Minimum failed events', 'Wait for this many before running', 1)}
          {num('cooldown_minutes', 'Cooldown (minutes)', 'Minimum gap between automatic runs', 5)}
          {num('daily_limit', 'Daily run limit', 'Caps AI cost for this connector', 0)}
          {num('max_samples', 'Events sent per run', 'Samples shown to the model (all are linked)', 1)}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-gray-100 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Last automatic run: {s.last_run_at ? relativeTime(s.last_run_at) : 'never'}
            {s.last_status && <> · <span className={clsx(s.last_status === 'error' && 'text-red-600')}>{s.last_message || s.last_status}</span></>}
            {' '}· {s.runs_day === new Date().toISOString().slice(0, 10) ? s.runs_today : 0}/{s.daily_limit} runs today
          </p>
          {canEdit && (
            <div className="flex gap-2">
              {dirty && <button className="btn-ghost text-sm" onClick={() => setDraft({})}>Discard</button>}
              <button className="btn-primary text-sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Manual runs */}
      <div className="grid lg:grid-cols-2 gap-6">
        <section className="card p-5 space-y-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Generate a proposal now</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            <b className="text-gray-900 dark:text-white">{d.failed_events_uncovered}</b> failed {d.failed_events_uncovered === 1 ? 'event is' : 'events are'} not covered by a pending proposal.
            {pending && <> A proposal from {relativeTime(pending.created_at)} is already <Link to="/approvals" className="underline">waiting for review</Link>.</>}
          </p>
          <button className="btn-primary" disabled={!canEdit || !!runBlocked || run.isPending} onClick={() => run.mutate()} title={runBlocked || undefined}>
            {run.isPending ? <><Loader2 className="w-4 h-4 animate-spin" /> Asking {d.model}…</> : <><Sparkles className="w-4 h-4" /> Generate from failed events</>}
          </button>
          {runBlocked && <p className="text-xs text-gray-400">{runBlocked}</p>}
        </section>

        <section className="card p-5 space-y-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Generate from sample events</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">Paste events you expect from this source (JSON array, one object, or one per line) to extend the mapping before they arrive.</p>
          <textarea className="input font-mono text-xs" rows={5} value={samples} onChange={e => setSamples(e.target.value)} disabled={!canEdit}
            placeholder='{"eventType": "user.session.start", "actor": {"alternateId": "a@b.com"}, ...}' />
          <button className="btn-secondary" disabled={!canEdit || !d.key_configured || !samples.trim() || fromSamples.isPending} onClick={() => fromSamples.mutate()}>
            {fromSamples.isPending ? <><Loader2 className="w-4 h-4 animate-spin" /> Asking {d.model}…</> : <><Sparkles className="w-4 h-4" /> Propose mapping</>}
          </button>
        </section>
      </div>

      {/* History */}
      <section className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Proposals for this connector</h3>
          <Link to="/approvals" className="text-sm text-brand-600 dark:text-brand-400 font-medium">Open Approvals →</Link>
        </div>
        {d.proposals.length === 0 ? (
          <p className="px-5 pb-5 text-sm text-gray-500">No proposals yet. They appear here when failed events are analyzed or samples are submitted.</p>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {d.proposals.map(p => {
              const src = SOURCE_LABEL[p.source] ?? { label: p.source, icon: Bot };
              const Icon = src.icon;
              return (
                <div key={p.id} className="px-5 py-3">
                  <button className="w-full flex items-center gap-3 text-left text-sm" onClick={() => setOpen(open === p.id ? null : p.id)}>
                    {open === p.id ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                    <span className={clsx('badge', STATUS_BADGE[p.status] ?? 'badge-gray')}>{p.status}</span>
                    <span className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300"><Icon className="w-3.5 h-3.5" />{src.label}</span>
                    <span className="text-gray-500">{p.routes} routes · {p.rules} rules{p.failed_events ? ` · ${p.failed_events} failed events` : ''}</span>
                    <span className="ml-auto text-xs text-gray-400 whitespace-nowrap">
                      {relativeTime(p.created_at)}{p.reviewed_by ? ` · ${p.status} by ${p.reviewed_by}` : ''}
                    </span>
                  </button>
                  {open === p.id && (
                    <div className="mt-2 ml-7 space-y-2">
                      <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line">{p.explanation || 'No explanation provided.'}</p>
                      {p.status === 'pending' && <Link to="/approvals" className="btn-primary text-xs inline-flex">Review in Approvals</Link>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
