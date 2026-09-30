import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, TestTube, Trash2, Pencil, Copy, Power, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { connectorApi } from '../../api/client';
import { Connector, ConnectorType } from '../../types';
import ConfirmDialog from '../Common/ConfirmDialog';
import { useToast } from '../../hooks/useToast';
import ConnectorLogo from './ConnectorLogo';
import { HEALTH, errorText, ingestionModes, relativeTime } from './catalog';

interface Props {
  connectors: Connector[];
  typesById: Record<string, ConnectorType>;
  onEdit: (c: Connector) => void;
  onOpen: (c: Connector) => void;
}

const PAGE_SIZE = 25;

export default function ConnectorTable({ connectors, typesById, onEdit, onOpen }: Props) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(connectors.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const rows = connectors.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500 dark:text-gray-400">
            <tr>
              <th className="text-left font-medium px-4 py-2.5">Connector</th>
              <th className="text-left font-medium px-3 py-2.5">Status</th>
              <th className="text-left font-medium px-3 py-2.5">Method</th>
              <th className="text-right font-medium px-3 py-2.5">Events</th>
              <th className="text-left font-medium px-3 py-2.5">Last event</th>
              <th className="text-right font-medium px-4 py-2.5"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {rows.map(c => <Row key={c.id} connector={c} type={typesById[c.connector_type]} onEdit={onEdit} onOpen={onOpen} />)}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-800 text-xs text-gray-500">
          <span>{current * PAGE_SIZE + 1}–{Math.min((current + 1) * PAGE_SIZE, connectors.length)} of {connectors.length}</span>
          <div className="flex items-center gap-2">
            <button className="btn-ghost text-xs" disabled={current === 0} onClick={() => setPage(current - 1)}>‹ Prev</button>
            <span>Page {current + 1} / {pageCount}</span>
            <button className="btn-ghost text-xs" disabled={current + 1 >= pageCount} onClick={() => setPage(current + 1)}>Next ›</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ connector: c, type, onEdit, onOpen }: { connector: Connector; type?: ConnectorType; onEdit: (c: Connector) => void; onOpen: (c: Connector) => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ['connectors'] });

  const toggle = useMutation({
    mutationFn: () => connectorApi.update(c.id, { enabled: !c.enabled }),
    onSuccess: () => { refresh(); toast.info(`${c.name} ${c.enabled ? 'disabled' : 'enabled'}`); },
    onError: e => toast.error(errorText(e), 'Could not change status'),
  });
  const remove = useMutation({
    mutationFn: () => connectorApi.delete(c.id),
    onSuccess: () => { refresh(); toast.success(`${c.name} deleted`); },
    onError: e => toast.error(errorText(e), 'Delete failed'),
  });
  const test = useMutation({
    mutationFn: () => connectorApi.test(c.id) as Promise<{ success: boolean; message: string }>,
    onSuccess: d => (d.success ? toast.success(d.message, `${c.name}: test passed`) : toast.error(d.message, `${c.name}: test failed`)),
    onError: e => toast.error(errorText(e), 'Test failed'),
  });
  const poll = useMutation({
    mutationFn: () => connectorApi.poll(c.id) as Promise<{ new_events?: number; queued?: number }>,
    onSuccess: d => { refresh(); toast.success(`${d.new_events ?? d.queued ?? 0} new events`, `${c.name}: polled`); },
    onError: e => toast.error(errorText(e), `${c.name}: poll failed`),
  });

  const health = HEALTH[c.health ?? (c.enabled ? 'waiting' : 'disabled')];
  const name = type?.display_name ?? c.connector_type;
  const modes = type ? ingestionModes(type) : [];

  const iconButton = (label: string, onClick: () => void, Icon: typeof Play, opts: { pending?: boolean; disabled?: boolean; danger?: boolean } = {}) => (
    <button
      onClick={onClick}
      disabled={opts.disabled || opts.pending}
      title={label}
      aria-label={label}
      className={clsx('btn-ghost p-1.5', opts.danger && 'text-red-500 hover:text-red-600')}
    >
      {opts.pending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
    </button>
  );

  return (
    <tr className={clsx('hover:bg-gray-50/60 dark:hover:bg-gray-800/30', !c.enabled && 'opacity-60')}>
      <td className="px-4 py-3">
        <button onClick={() => onOpen(c)} className="flex items-center gap-3 text-left min-w-0 hover:underline">
          <ConnectorLogo typeId={c.connector_type} name={name} size="sm" />
          <span className="min-w-0">
            <span className="block font-medium text-gray-900 dark:text-white truncate max-w-[16rem]">{c.name}</span>
            <span className="block text-xs text-gray-500 truncate">{name}</span>
          </span>
        </button>
      </td>
      <td className="px-3 py-3">
        <span className={clsx('inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium', health.pill)} title={c.poll_error || c.health_detail}>
          <span className={clsx('w-1.5 h-1.5 rounded-full', health.dot)} />{health.label}
        </span>
        {(c.health === 'error' || c.health === 'attention') && (
          <p className="text-xs text-gray-500 mt-1 max-w-[16rem] truncate" title={c.poll_error || c.health_detail}>{c.poll_error || c.health_detail}</p>
        )}
      </td>
      <td className="px-3 py-3 text-xs text-gray-600 dark:text-gray-400">{modes.join(' · ') || '—'}</td>
      <td className="px-3 py-3 text-right tabular-nums">
        <span className="text-gray-900 dark:text-white">{c.events_processed.toLocaleString()}</span>
        {c.events_failed > 0 && <span className="block text-xs text-red-500">{c.events_failed.toLocaleString()} failed</span>}
      </td>
      <td className="px-3 py-3 text-xs text-gray-600 dark:text-gray-400" title={c.last_event_at ?? undefined}>{relativeTime(c.last_event_at)}</td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-0.5">
          {iconButton('Test connection', () => test.mutate(), TestTube, { pending: test.isPending })}
          {type?.supports_polling && iconButton('Poll now', () => poll.mutate(), Play, { pending: poll.isPending, disabled: !c.enabled })}
          {type?.supports_webhook && iconButton('Copy webhook URL', () => {
            navigator.clipboard.writeText(window.location.origin + c.webhook_url);
            toast.info('Webhook URL copied');
          }, Copy)}
          {iconButton('Edit settings', () => onEdit(c), Pencil)}
          {iconButton(c.enabled ? 'Disable' : 'Enable', () => toggle.mutate(), Power, { pending: toggle.isPending })}
          {iconButton('Delete', () => setConfirmDelete(true), Trash2, { danger: true, pending: remove.isPending })}
        </div>
        <ConfirmDialog
          open={confirmDelete}
          title="Delete connector"
          message={`Delete "${c.name}"? Events stop immediately. This cannot be undone.`}
          confirmLabel="Delete"
          danger
          onConfirm={() => { setConfirmDelete(false); remove.mutate(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      </td>
    </tr>
  );
}
