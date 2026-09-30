import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/auth';
import EmptyState from '../components/Common/EmptyState';
import ConfirmDialog from '../components/Common/ConfirmDialog';
import { SkeletonTable } from '../components/Common/Skeleton';
import { AlertOctagon, RefreshCw, Trash2, ChevronDown, ChevronRight, CheckSquare, Square, Sparkles, Loader2, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';

const PAGE_SIZE = 50;

type DLQState = 'pending' | 'resolved' | 'discarded';

const TABS: { id: DLQState; label: string; empty: string }[] = [
  { id: 'pending', label: 'Pending', empty: 'Nothing is waiting. Every event received so far was mapped and forwarded.' },
  { id: 'resolved', label: 'Resolved', empty: 'No events have been replayed yet.' },
  { id: 'discarded', label: 'Discarded', empty: 'No events have been discarded.' },
];

interface AIFixResult {
  connector_id: string;
  connector_name?: string;
  approval_id?: string;
  events?: number;
  rules_proposed?: number;
  error?: string;
}

interface DLQEvent {
  id: string;
  connector_type: string;
  connector_name: string;
  error_message: string;
  error_type: string;
  retry_count: number;
  max_retries: number;
  discarded: boolean;
  state: DLQState;
  last_retry_at: string | null;
  raw_event: Record<string, unknown>;
  created_at: string;
}

export default function DLQPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const can = useAuthStore(s => s.can);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [tab, setTab] = useState<DLQState>('pending');
  const [bulkAction, setBulkAction] = useState<'retry' | 'discard' | null>(null);
  const [page, setPage] = useState(0);
  const [aiResults, setAiResults] = useState<AIFixResult[] | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['dlq', tab, page],
    queryFn: () => api.get('/dlq', { params: { state: tab, limit: PAGE_SIZE, offset: page * PAGE_SIZE } }).then(r => r.data),
    refetchInterval: 10000,
  });

  const { data: stats } = useQuery<Record<DLQState, number>>({
    queryKey: ['dlq-stats'],
    queryFn: () => api.get('/dlq/stats').then(r => r.data),
    refetchInterval: 10000,
  });

  const refresh = () => { refresh(); qc.invalidateQueries({ queryKey: ['dlq-stats'] }); };
  const items: DLQEvent[] = data?.items || [];
  const total: number = data?.total ?? items.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const aiFixMutation = useMutation({
    mutationFn: () => api.post('/dlq/ai-fix', { ids: [...selected] }).then(r => r.data),
    onSuccess: (res: { results: AIFixResult[] }) => {
      setAiResults(res.results);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['approvals'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'AI request failed');
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.post(`/dlq/${id}/retry`),
    onSuccess: () => { toast.success('Event re-queued for processing'); refresh(); },
    onError: () => toast.error('Failed to retry event'),
  });

  const discardMutation = useMutation({
    mutationFn: (id: string) => api.post(`/dlq/${id}/discard`),
    onSuccess: () => { toast.success('Event discarded'); refresh(); },
  });

  const bulkRetryMutation = useMutation({
    mutationFn: () => api.post('/dlq/bulk/retry', { ids: [...selected] }),
    onSuccess: (res) => {
      toast.success(`Re-queued ${res.data.success} events for processing`);
      setSelected(new Set());
      refresh();
    },
  });

  const bulkDiscardMutation = useMutation({
    mutationFn: () => api.post('/dlq/bulk/discard', { ids: [...selected] }),
    onSuccess: (res) => {
      toast.success(`Discarded ${res.data.discarded} events`);
      setSelected(new Set());
      refresh();
    },
  });

  const toggleSelect = (id: string) => {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const toggleAll = () => {
    setSelected(s => s.size === items.length ? new Set() : new Set(items.map(i => i.id)));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <AlertOctagon className="w-6 h-6 text-red-400" /> Dead-Letter Queue
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {stats?.pending ?? 0} pending · {stats?.resolved ?? 0} resolved · {stats?.discarded ?? 0} discarded
          </p>
        </div>
      </div>

      <div className="flex gap-3 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-sm text-gray-600 dark:text-gray-400">
        <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-gray-400" />
        <p>
          Events land here only when GANA cannot turn them into OCSF at all (no mapping for the source, or the mapper hit an error).
          They are kept instead of dropped, so after the mapping is fixed (by hand or through AI mapping and Approvals) they can be replayed.
          Events that map but match no specific class are <b>not</b> here: they are forwarded as Base Events and routed to the forwarder’s review index when one is set.
        </p>
      </div>

      <div className="flex gap-6 border-b border-gray-200 dark:border-gray-800" role="tablist">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => { setTab(t.id); setPage(0); setSelected(new Set()); setExpanded(null); }}
            className={clsx('pb-2.5 -mb-px text-sm font-medium border-b-2 transition-colors',
              tab === t.id ? 'border-brand-600 text-brand-700 dark:text-brand-300' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200')}
          >
            {t.label} ({(stats?.[t.id] ?? 0).toLocaleString()})
          </button>
        ))}
      </div>

      {selected.size > 0 && can('approve') && tab === 'pending' && (
        <div className="flex items-center gap-3 p-3 bg-brand-50 dark:bg-brand-900/20 rounded-xl border border-brand-200 dark:border-brand-800">
          <span className="text-sm font-medium text-brand-700 dark:text-brand-400">{selected.size} selected</span>
          <button
            onClick={() => aiFixMutation.mutate()}
            disabled={aiFixMutation.isPending}
            className="btn-primary text-xs"
            title="Send these events and their errors to AI; it proposes a corrected mapping for review in Approvals"
          >
            {aiFixMutation.isPending
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Asking AI…</>
              : <><Sparkles className="w-3.5 h-3.5" /> Ask AI to fix mapping</>}
          </button>
          <button onClick={() => setBulkAction('retry')} className="btn-secondary text-xs">
            <RefreshCw className="w-3.5 h-3.5" /> Retry All
          </button>
          <button onClick={() => setBulkAction('discard')} className="btn-danger text-xs">
            <Trash2 className="w-3.5 h-3.5" /> Discard All
          </button>
          <button onClick={() => setSelected(new Set())} className="btn-ghost text-xs">Clear</button>
        </div>
      )}

      {aiResults && (
        <div className="card p-4 space-y-2 border border-brand-200 dark:border-brand-800">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-500" /> AI mapping suggestions
            </p>
            <button onClick={() => setAiResults(null)} className="btn-ghost text-xs">Dismiss</button>
          </div>
          {aiResults.map(r => (
            <div key={r.connector_id} className="text-sm flex items-center gap-2 flex-wrap">
              <span className="font-medium text-gray-900 dark:text-white">{r.connector_name || r.connector_id}</span>
              {r.error ? (
                <span className="text-red-600 dark:text-red-400">— {r.error}</span>
              ) : (
                <>
                  <span className="text-gray-600 dark:text-gray-400">
                    — {r.rules_proposed} rules proposed from {r.events} events. Awaiting review; approving applies it and retries these events.
                  </span>
                  <Link to="/approvals" className="text-brand-600 dark:text-brand-400 underline font-medium">Review in Approvals →</Link>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {isLoading ? <SkeletonTable rows={5} /> : items.length === 0 ? (
        <EmptyState icon={AlertOctagon} title={`No ${tab} events`} description={TABS.find(t => t.id === tab)!.empty} />
      ) : (
        <div className="card overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            {tab === 'pending' && (
              <button onClick={toggleAll} className="btn-ghost p-1">
                {selected.size === items.length ? <CheckSquare className="w-4 h-4 text-brand-500" /> : <Square className="w-4 h-4" />}
              </button>
            )}
            <span className="text-xs text-gray-500">
              {total === 0 ? 0 : page * PAGE_SIZE + 1}–{page * PAGE_SIZE + items.length} of {total} events
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button onClick={() => { setPage(p => p - 1); setSelected(new Set()); }} disabled={page === 0} className="btn-ghost text-xs">‹ Prev</button>
              <span className="text-xs text-gray-500">Page {page + 1} / {pageCount}</span>
              <button onClick={() => { setPage(p => p + 1); setSelected(new Set()); }} disabled={page + 1 >= pageCount} className="btn-ghost text-xs">Next ›</button>
            </div>
          </div>

          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {items.map(event => (
              <div key={event.id}>
                <div className="flex items-center gap-3 px-4 py-3">
                  {tab === 'pending' && (
                    <button onClick={() => toggleSelect(event.id)} className="btn-ghost p-1 flex-shrink-0">
                      {selected.has(event.id) ? <CheckSquare className="w-4 h-4 text-brand-500" /> : <Square className="w-4 h-4" />}
                    </button>
                  )}
                  <button onClick={() => setExpanded(expanded === event.id ? null : event.id)} className="flex-shrink-0">
                    {expanded === event.id ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="badge badge-blue">{event.connector_type}</span>
                      <span className="badge badge-red">{event.error_type || 'Error'}</span>
                      {event.state === 'resolved' && <span className="badge badge-green">Replayed</span>}
                      {event.state === 'discarded' && <span className="badge badge-gray">Discarded</span>}
                      <span className="text-xs text-gray-500">{event.retry_count}/{event.max_retries} retries</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5 truncate">{event.error_message}</p>
                  </div>

                  <span className="text-xs text-gray-400 flex-shrink-0 text-right">
                    Failed {new Date(event.created_at).toLocaleString()}
                    {event.state === 'resolved' && event.last_retry_at && <span className="block">Replayed {new Date(event.last_retry_at).toLocaleString()}</span>}
                  </span>

                  {can('approve') && !event.discarded && (
                    <div className="flex gap-1 flex-shrink-0">
                      <button onClick={() => retryMutation.mutate(event.id)} disabled={event.retry_count >= event.max_retries} className="btn-ghost p-1.5" title="Retry">
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => discardMutation.mutate(event.id)} className="btn-ghost p-1.5 text-red-500" title="Discard">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>

                {expanded === event.id && (
                  <div className="px-12 pb-4">
                    <pre className="text-xs bg-gray-50 dark:bg-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300 max-h-48">
                      {JSON.stringify(event.raw_event, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={bulkAction === 'retry'}
        title={`Retry ${selected.size} events`}
        message="These events will be re-queued to the processing pipeline. Events that fail again will return to the DLQ."
        confirmLabel="Retry All"
        onConfirm={() => { setBulkAction(null); bulkRetryMutation.mutate(); }}
        onCancel={() => setBulkAction(null)}
      />
      <ConfirmDialog
        open={bulkAction === 'discard'}
        title={`Discard ${selected.size} events`}
        message="These events will not be replayed. They stay visible under the Discarded tab."
        confirmLabel="Discard All"
        danger
        onConfirm={() => { setBulkAction(null); bulkDiscardMutation.mutate(); }}
        onCancel={() => setBulkAction(null)}
      />
    </div>
  );
}
