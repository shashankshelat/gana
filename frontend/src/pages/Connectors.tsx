import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Search, Plug, AlertTriangle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { connectorApi, forwarderApi } from '../api/client';
import { Connector, ConnectorType, Forwarder } from '../types';
import ConnectorCatalog from '../components/Connectors/ConnectorCatalog';
import ConnectorTable from '../components/Connectors/ConnectorTable';
import SetupWizard from '../components/Connectors/SetupWizard';
import { HEALTH, Health, categoryOf, errorText } from '../components/Connectors/catalog';

type StatusFilter = 'all' | 'receiving' | 'quiet' | 'problem' | 'disabled';

const STATUS_GROUPS: { id: StatusFilter; label: string; health: Health[] }[] = [
  { id: 'all', label: 'All', health: [] },
  { id: 'receiving', label: 'Receiving', health: ['receiving'] },
  { id: 'quiet', label: 'Waiting / idle', health: ['waiting', 'idle'] },
  { id: 'problem', label: 'Needs attention', health: ['error', 'attention'] },
  { id: 'disabled', label: 'Disabled', health: ['disabled'] },
];

type SortKey = 'name' | 'recent' | 'events';

export default function Connectors() {
  const [params, setParams] = useSearchParams();
  const view = params.get('view') === 'catalog' ? 'catalog' : 'connected';
  const setView = (v: 'catalog' | 'connected') => setParams(v === 'catalog' ? { view: 'catalog' } : {});

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<SortKey>('name');
  const [setupType, setSetupType] = useState<ConnectorType | null>(null);
  const navigate = useNavigate();

  const connectorsQ = useQuery<Connector[]>({ queryKey: ['connectors'], queryFn: connectorApi.list, refetchInterval: 15000 });
  const typesQ = useQuery<ConnectorType[]>({ queryKey: ['connector-types'], queryFn: connectorApi.getTypes });
  const forwardersQ = useQuery<Forwarder[]>({ queryKey: ['forwarders'], queryFn: forwarderApi.list });

  const connectors = connectorsQ.data ?? [];
  const types = typesQ.data ?? [];
  // Connectors need a destination; the backend rejects creation without one too
  const hasForwarder = (forwardersQ.data ?? []).some(f => f.enabled);
  const blocked = !forwardersQ.isPending && !hasForwarder;

  const typesById = useMemo(() => Object.fromEntries(types.map(t => [t.type_id, t])), [types]);
  const connectedCounts = useMemo(() => {
    const c: Record<string, number> = {};
    connectors.forEach(x => { c[x.connector_type] = (c[x.connector_type] ?? 0) + 1; });
    return c;
  }, [connectors]);

  const healthOf = (c: Connector): Health => c.health ?? (c.enabled ? 'waiting' : 'disabled');
  const statusCount = (g: typeof STATUS_GROUPS[number]) =>
    g.id === 'all' ? connectors.length : connectors.filter(c => g.health.includes(healthOf(c))).length;

  const usedCategories = useMemo(
    () => [...new Set(connectors.map(c => typesById[c.connector_type]?.category).filter(Boolean) as string[])],
    [connectors, typesById],
  );

  const visible = useMemo(() => {
    const group = STATUS_GROUPS.find(g => g.id === status)!;
    const q = search.toLowerCase();
    return connectors
      .filter(c => status === 'all' || group.health.includes(healthOf(c)))
      .filter(c => category === 'all' || typesById[c.connector_type]?.category === category)
      .filter(c => !q || `${c.name} ${c.connector_type} ${typesById[c.connector_type]?.display_name ?? ''}`.toLowerCase().includes(q))
      .sort((a, b) => sort === 'events' ? b.events_processed - a.events_processed
        : sort === 'recent' ? (b.last_event_at ?? '').localeCompare(a.last_event_at ?? '')
        : a.name.localeCompare(b.name));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectors, status, category, search, sort, typesById]);

  const startSetup = (t: ConnectorType) => {
    if (blocked) return;
    setSetupType(t);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Connectors</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {connectors.length} connected · {types.length} sources available
          </p>
        </div>
        <button onClick={() => setView('catalog')} disabled={blocked} title={blocked ? 'Add a forwarder first' : undefined} className="btn-primary">
          <Plus className="w-4 h-4" /> Add connector
        </button>
      </div>

      {blocked && (
        <div className="flex items-start gap-3 p-4 rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-amber-800 dark:text-amber-300">Add a forwarder first</p>
            <p className="text-amber-700 dark:text-amber-400 mt-0.5">
              Connectors send their OCSF events to a forwarder (e.g. Splunk). Configure and enable one before adding a connector.{' '}
              <Link to="/forwarders" className="underline font-medium">Go to Forwarders →</Link>
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-6 border-b border-gray-200 dark:border-gray-800" role="tablist">
        {([['connected', `My connectors (${connectors.length})`], ['catalog', `Catalog (${types.length})`]] as const).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={view === id}
            onClick={() => setView(id)}
            className={clsx('pb-2.5 -mb-px text-sm font-medium border-b-2 transition-colors',
              view === id ? 'border-brand-600 text-brand-700 dark:text-brand-300' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200')}
          >
            {label}
          </button>
        ))}
      </div>

      {view === 'catalog' ? (
        typesQ.isPending ? <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />
        : typesQ.isError ? <ErrorBox message={errorText(typesQ.error)} onRetry={() => typesQ.refetch()} />
        : <ConnectorCatalog types={types} connectedCounts={connectedCounts} onSelect={startSetup} />
      ) : connectorsQ.isPending ? (
        <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />
      ) : connectorsQ.isError ? (
        <ErrorBox message={errorText(connectorsQ.error)} onRetry={() => connectorsQ.refetch()} />
      ) : connectors.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center mb-4">
            <Plug className="w-6 h-6 text-brand-600" />
          </div>
          <p className="text-lg font-medium text-gray-900 dark:text-white">No connectors yet</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-sm">
            Pick a source from the catalog. Setup takes about a minute, and GANA maps its events to OCSF automatically.
          </p>
          <button onClick={() => setView('catalog')} disabled={blocked} className="btn-primary mt-5">Browse {types.length} connectors</button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Status summary doubles as the status filter */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {STATUS_GROUPS.map(g => {
              const n = statusCount(g);
              const dot = g.health[0] ? HEALTH[g.health[0]].dot : 'bg-brand-500';
              return (
                <button
                  key={g.id}
                  onClick={() => setStatus(g.id)}
                  aria-pressed={status === g.id}
                  className={clsx('card p-3 text-left transition-all',
                    status === g.id ? 'ring-2 ring-brand-500 border-transparent' : 'hover:border-gray-300 dark:hover:border-gray-600')}
                >
                  <p className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                    <span className={clsx('w-2 h-2 rounded-full', dot)} />{g.label}
                  </p>
                  <p className={clsx('text-2xl font-semibold mt-0.5', g.id === 'problem' && n > 0 ? 'text-red-600' : 'text-gray-900 dark:text-white')}>{n}</p>
                </button>
              );
            })}
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[14rem] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input className="input pl-9" placeholder="Search by name or source…" value={search} onChange={e => setSearch(e.target.value)} aria-label="Search connectors" />
            </div>
            <select className="input w-auto" value={category} onChange={e => setCategory(e.target.value)} aria-label="Category">
              <option value="all">All categories</option>
              {usedCategories.map(id => <option key={id} value={id}>{categoryOf(id).label}</option>)}
            </select>
            <select className="input w-auto" value={sort} onChange={e => setSort(e.target.value as SortKey)} aria-label="Sort by">
              <option value="name">Sort: Name</option>
              <option value="recent">Sort: Last event</option>
              <option value="events">Sort: Most events</option>
            </select>
            <button onClick={() => connectorsQ.refetch()} className="btn-ghost p-2" title="Refresh" aria-label="Refresh">
              <RefreshCw className={clsx('w-4 h-4', connectorsQ.isFetching && 'animate-spin')} />
            </button>
          </div>

          {visible.length === 0 ? (
            <div className="card p-10 text-center text-sm text-gray-500">
              No connectors match these filters.{' '}
              <button className="text-brand-600 underline" onClick={() => { setSearch(''); setStatus('all'); setCategory('all'); }}>Clear filters</button>
            </div>
          ) : (
            <ConnectorTable connectors={visible} typesById={typesById} onEdit={c => navigate(`/connectors/${c.id}?tab=settings`)} onOpen={c => navigate(`/connectors/${c.id}`)} />
          )}
        </div>
      )}

      <SetupWizard type={setupType} onClose={() => setSetupType(null)} onDone={() => { setSetupType(null); setView('connected'); }} />
    </div>
  );
}

function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card p-6 flex items-center justify-between gap-4 border-red-200 dark:border-red-900">
      <p className="text-sm text-red-600 dark:text-red-400">Could not load connectors: {message}</p>
      <button onClick={onRetry} className="btn-secondary">Retry</button>
    </div>
  );
}
