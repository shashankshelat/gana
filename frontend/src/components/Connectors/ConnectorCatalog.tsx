import { useMemo, useState } from 'react';
import { Search, Star, LayoutGrid, X } from 'lucide-react';
import clsx from 'clsx';
import { ConnectorType } from '../../types';
import ConnectorLogo from './ConnectorLogo';
import { CATEGORIES, POPULAR, categoryOf, ingestionModes, matchesSearch } from './catalog';

interface Props {
  types: ConnectorType[];
  connectedCounts: Record<string, number>;
  onSelect: (type: ConnectorType) => void;
}

type ModeFilter = 'all' | 'pull' | 'push';

export default function ConnectorCatalog({ types, connectedCounts, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string>('all');
  const [mode, setMode] = useState<ModeFilter>('all');
  const [stableOnly, setStableOnly] = useState(false);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    types.forEach(t => { c[t.category] = (c[t.category] ?? 0) + 1; });
    return c;
  }, [types]);

  const categories = useMemo(() => {
    const known = CATEGORIES.filter(c => counts[c.id]);
    const extra = Object.keys(counts).filter(id => !CATEGORIES.some(c => c.id === id)).map(categoryOf);
    return [...known, ...extra];
  }, [counts]);

  const filtered = useMemo(() => types
    .filter(t => matchesSearch(t, query))
    .filter(t => category === 'all' || (category === 'popular' ? POPULAR.includes(t.type_id) : t.category === category))
    .filter(t => mode === 'all' || (mode === 'pull' ? t.supports_polling : t.supports_webhook))
    .filter(t => !stableOnly || t.maturity !== 'beta')
    .sort((a, b) => a.display_name.localeCompare(b.display_name)),
  [types, query, category, mode, stableOnly]);

  const showPopularStrip = !query && category === 'all' && mode === 'all' && !stableOnly;
  const popular = POPULAR.map(id => types.find(t => t.type_id === id)).filter(Boolean) as ConnectorType[];

  const railItem = (id: string, label: string, count: number, Icon: typeof Star) => (
    <button
      key={id}
      onClick={() => setCategory(id)}
      className={clsx(
        'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left',
        category === id
          ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300 font-medium'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
      )}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      <span className="text-xs text-gray-400">{count}</span>
    </button>
  );

  return (
    <div className="flex gap-6">
      {/* Category rail */}
      <nav aria-label="Connector categories" className="hidden md:block w-56 flex-shrink-0 space-y-0.5 sticky top-4 self-start">
        {railItem('all', 'All connectors', types.length, LayoutGrid)}
        {railItem('popular', 'Popular', popular.length, Star)}
        <div className="pt-3 pb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-gray-400">Categories</div>
        {categories.map(c => railItem(c.id, c.label, counts[c.id] ?? 0, c.icon))}
      </nav>

      <div className="flex-1 min-w-0 space-y-5">
        {/* Search + filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[16rem]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={`Search ${types.length} connectors — e.g. "okta", "email", "webhook"`}
              className="input pl-9 pr-9"
              aria-label="Search connectors"
            />
            {query && (
              <button onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 btn-ghost p-1" aria-label="Clear search">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <select className="input w-auto md:hidden" value={category} onChange={e => setCategory(e.target.value)} aria-label="Category">
            <option value="all">All categories</option>
            <option value="popular">Popular</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 p-0.5" role="group" aria-label="How data arrives">
            {(['all', 'pull', 'push'] as ModeFilter[]).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                title={m === 'pull' ? 'GANA polls the vendor API' : m === 'push' ? 'The vendor sends events to a GANA webhook' : undefined}
                className={clsx('px-3 py-1 text-xs font-medium rounded-md', mode === m ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900' : 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200')}
              >
                {m === 'all' ? 'Any method' : m === 'pull' ? 'Pull (API)' : 'Push (webhook)'}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
            <input type="checkbox" checked={stableOnly} onChange={e => setStableOnly(e.target.checked)} className="w-3.5 h-3.5" />
            Verified only
          </label>
        </div>

        {showPopularStrip && popular.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Popular</h3>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {popular.map(t => (
                <button key={t.type_id} onClick={() => onSelect(t)}
                  className="flex items-center gap-2 pl-1.5 pr-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 hover:border-brand-400 hover:bg-brand-50/50 dark:hover:bg-brand-900/10 whitespace-nowrap text-sm">
                  <ConnectorLogo typeId={t.type_id} name={t.display_name} size="sm" />
                  {t.display_name}
                </button>
              ))}
            </div>
          </section>
        )}

        <p className="text-xs text-gray-500 dark:text-gray-400">
          {filtered.length} {filtered.length === 1 ? 'connector' : 'connectors'}
          {category !== 'all' && ` in ${category === 'popular' ? 'Popular' : categoryOf(category).label}`}
          {query && ` matching “${query}”`}
        </p>

        {filtered.length === 0 ? (
          <div className="card p-10 text-center space-y-3">
            <p className="font-medium text-gray-900 dark:text-white">No connector matches your filters</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">Any source that can send JSON or syslog still works through a custom source.</p>
            <div className="flex justify-center gap-2">
              {types.filter(t => t.category === 'custom').map(t => (
                <button key={t.type_id} onClick={() => onSelect(t)} className="btn-secondary text-sm">{t.display_name}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
            {filtered.map(t => (
              <button
                key={t.type_id}
                onClick={() => onSelect(t)}
                className="group card p-4 text-left flex flex-col gap-3 hover:border-brand-400 dark:hover:border-brand-600 hover:shadow-md transition-all focus-visible:ring-2 focus-visible:ring-brand-500 outline-none"
              >
                <div className="flex items-start gap-3">
                  <ConnectorLogo typeId={t.type_id} name={t.display_name} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 dark:text-white truncate">{t.display_name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{categoryOf(t.category).label}</p>
                  </div>
                  {connectedCounts[t.type_id] ? (
                    <span className="badge badge-green whitespace-nowrap">{connectedCounts[t.type_id]} connected</span>
                  ) : null}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 flex-1">{t.description}</p>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {ingestionModes(t).map(m => <span key={m} className="badge badge-gray">{m}</span>)}
                  {t.maturity === 'beta' && <span className="badge badge-yellow" title={t.maturity_note}>Beta</span>}
                  <span className="ml-auto text-xs font-medium text-brand-600 dark:text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity">Set up →</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
