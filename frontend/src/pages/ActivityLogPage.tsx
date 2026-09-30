import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { SkeletonTable } from '../components/Common/Skeleton';
import { BookOpen, Download, CheckCircle, XCircle, Filter } from 'lucide-react';
import clsx from 'clsx';

interface AuditEntry {
  id: string;
  username: string;
  action: string;
  resource_type: string;
  resource_name: string;
  status: string;
  ip_address: string;
  created_at: string;
}

const ACTION_COLORS: Record<string, string> = {
  'auth.login': 'badge-green',
  'auth.login_failed': 'badge-red',
  'connector.create': 'badge-blue',
  'connector.delete': 'badge-red',
  'approval.approved': 'badge-green',
  'approval.rejected': 'badge-red',
  'schema.updated': 'badge-blue',
};

export default function ActivityLogPage() {
  const [filterUsername, setFilterUsername] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const { data, isLoading } = useQuery({
    queryKey: ['audit-log', filterUsername, filterAction, offset],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filterUsername) params.set('username', filterUsername);
      if (filterAction) params.set('action', filterAction);
      params.set('limit', String(LIMIT));
      params.set('offset', String(offset));
      return api.get(`/audit-log?${params}`).then(r => r.data);
    },
    refetchInterval: 30000,
  });

  const items: AuditEntry[] = data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-gray-400" /> Activity Log
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Complete audit trail of all platform actions</p>
        </div>
        <a href="/api/audit-log/export" className="btn-secondary text-sm">
          <Download className="w-4 h-4" /> Export CSV
        </a>
      </div>

      <div className="flex gap-3">
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input className="input pl-9 w-40" placeholder="Filter user..." value={filterUsername} onChange={e => { setFilterUsername(e.target.value); setOffset(0); }} />
        </div>
        <input className="input w-52" placeholder="Filter action..." value={filterAction} onChange={e => { setFilterAction(e.target.value); setOffset(0); }} />
      </div>

      {isLoading ? <SkeletonTable rows={8} /> : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800">
              <tr>
                {['Time', 'User', 'Action', 'Resource', 'Status', 'IP'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {items.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-12 text-gray-400">No activity yet</td></tr>
              ) : items.map(entry => (
                <tr key={entry.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap text-xs">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                    {entry.username || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={clsx('badge', ACTION_COLORS[entry.action] || 'badge-gray')}>
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {entry.resource_name || entry.resource_type || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {entry.status === 'success'
                      ? <CheckCircle className="w-4 h-4 text-green-500" />
                      : <XCircle className="w-4 h-4 text-red-500" />
                    }
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs font-mono">{entry.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 dark:border-gray-800">
            <span className="text-xs text-gray-500">Showing {offset + 1}–{offset + items.length}</span>
            <div className="flex gap-2">
              <button onClick={() => setOffset(o => Math.max(0, o - LIMIT))} disabled={offset === 0} className="btn-ghost text-xs px-2 py-1">Prev</button>
              <button onClick={() => setOffset(o => o + LIMIT)} disabled={items.length < LIMIT} className="btn-ghost text-xs px-2 py-1">Next</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
