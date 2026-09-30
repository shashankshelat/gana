import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { schemaApi } from '../api/client';
import { OCSFClass, OCSFCategory, SchemaVersion } from '../types';
import { RefreshCw, FileCode, Search, ChevronDown, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

export default function SchemaPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [expandedCategory, setExpandedCategory] = useState<number | null>(null);

  const { data: version } = useQuery<SchemaVersion>({
    queryKey: ['schema-version'],
    queryFn: schemaApi.getVersion,
  });

  const { data: classes = [], isError: classesError, refetch: refetchClasses } = useQuery<OCSFClass[]>({
    queryKey: ['schema-classes'],
    queryFn: schemaApi.getClasses,
  });

  const { data: categories = [] } = useQuery<OCSFCategory[]>({
    queryKey: ['schema-categories'],
    queryFn: schemaApi.getCategories,
  });

  const updateMutation = useMutation({
    mutationFn: (force: boolean) => schemaApi.update(force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schema-version'] });
      qc.invalidateQueries({ queryKey: ['schema-classes'] });
    },
  });

  const filteredClasses = classes.filter(c =>
    c.name?.toLowerCase().includes(search.toLowerCase()) ||
    c.caption?.toLowerCase().includes(search.toLowerCase()) ||
    String(c.uid).includes(search)
  );

  const classesByCategory = categories.reduce<Record<number, OCSFClass[]>>((acc, cat) => {
    acc[cat.uid] = filteredClasses.filter(c => c.category_uid === cat.uid);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">OCSF Schema</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Open Cybersecurity Schema Framework — auto-updated from GitHub
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => updateMutation.mutate(false)}
            disabled={updateMutation.isPending}
            className="btn-secondary"
          >
            <RefreshCw className={clsx('w-4 h-4', updateMutation.isPending && 'animate-spin')} />
            Check for Updates
          </button>
          <button
            onClick={() => updateMutation.mutate(true)}
            disabled={updateMutation.isPending}
            className="btn-primary"
          >
            Force Update
          </button>
        </div>
      </div>

      {/* Version card */}
      {version && (
        <div className="card p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Schema Version</p>
              <p className="text-lg font-bold text-brand-600 dark:text-brand-400 mt-0.5">
                {version.version || 'Not loaded'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Last Updated</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white mt-0.5">
                {version.updated_at ? new Date(version.updated_at).toLocaleDateString() : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Event Classes</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white mt-0.5">{classes.length}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Categories</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white mt-0.5">{categories.length}</p>
            </div>
          </div>
          {version.release_notes && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Release Notes</p>
              <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">{version.release_notes}</p>
            </div>
          )}
        </div>
      )}

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          className="input pl-9"
          placeholder="Search classes..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {classesError && (
        <div className="card p-4 flex items-center justify-between gap-4 border-red-200 dark:border-red-900">
          <p className="text-sm text-red-600 dark:text-red-400">Could not load OCSF classes from the backend.</p>
          <button onClick={() => refetchClasses()} className="btn-secondary text-sm">Retry</button>
        </div>
      )}

      {/* Classes by category */}
      <div className="space-y-3">
        {categories.map(cat => {
          const catClasses = classesByCategory[cat.uid] || [];
          if (catClasses.length === 0 && search) return null;
          const isExpanded = expandedCategory === cat.uid || search.length > 0;

          return (
            <div key={cat.uid} className="card overflow-hidden">
              <button
                className="w-full flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                onClick={() => setExpandedCategory(isExpanded && !search ? null : cat.uid)}
              >
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-md bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center">
                    <FileCode className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-gray-900 dark:text-white text-sm">
                      Category {cat.uid}: {cat.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{catClasses.length} classes</p>
                  </div>
                </div>
                {!search && (isExpanded
                  ? <ChevronDown className="w-4 h-4 text-gray-400" />
                  : <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
              </button>

              {(isExpanded) && catClasses.length > 0 && (
                <div className="border-t border-gray-100 dark:border-gray-800">
                  <div className="divide-y divide-gray-100 dark:divide-gray-800">
                    {catClasses.map(cls => (
                      <div key={cls.uid} className="flex items-start gap-4 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/30">
                        <span className="flex-shrink-0 badge badge-blue font-mono text-xs">{cls.uid}</span>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
                            {cls.caption || cls.name}
                            <span className="font-mono text-xs font-normal text-gray-400">{cls.name}</span>
                            {cls.deprecated && <span className="badge badge-yellow text-[10px]">deprecated</span>}
                          </p>
                          {cls.description && (
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                              {cls.description}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
