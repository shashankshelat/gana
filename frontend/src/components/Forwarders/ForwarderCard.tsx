import { useState } from 'react';
import { Upload, TestTube, Trash2, Pencil, CheckCircle, XCircle } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { forwarderApi } from '../../api/client';
import { Forwarder } from '../../types';
import clsx from 'clsx';

interface ForwarderCardProps {
  forwarder: Forwarder;
  onEdit: (forwarder: Forwarder) => void;
}

export default function ForwarderCard({ forwarder, onEdit }: ForwarderCardProps) {
  const qc = useQueryClient();
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const toggleMutation = useMutation({
    mutationFn: () => forwarderApi.update(forwarder.id, { enabled: !forwarder.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['forwarders'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => forwarderApi.delete(forwarder.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['forwarders'] }),
  });

  const testMutation = useMutation({
    mutationFn: () => forwarderApi.test(forwarder.id),
    onSuccess: (data) => {
      setTestResult(data);
      setTimeout(() => setTestResult(null), 5000);
    },
  });

  const categoryColors: Record<string, string> = {
    siem: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400',
    data_lake: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
    storage: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
    streaming: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400',
  };

  return (
    <div className={clsx('card p-5 flex flex-col gap-4', !forwarder.enabled && 'opacity-60')}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0">
            <Upload className="w-4 h-4 text-brand-600 dark:text-brand-400" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-gray-900 dark:text-white truncate">{forwarder.name}</h3>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <span className="badge badge-blue">{forwarder.forwarder_type}</span>
              <span className={clsx('badge', forwarder.enabled ? 'badge-green' : 'badge-gray')}>
                {forwarder.enabled ? 'Active' : 'Disabled'}
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={() => toggleMutation.mutate()}
          className={clsx(
            'relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
            forwarder.enabled ? 'bg-brand-600' : 'bg-gray-200 dark:bg-gray-700'
          )}
        >
          <span className={clsx(
            'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform duration-200',
            forwarder.enabled ? 'translate-x-4' : 'translate-x-0'
          )} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          { label: 'Forwarded', value: forwarder.events_forwarded.toLocaleString() },
          { label: 'Failed', value: forwarder.events_failed.toLocaleString(), danger: forwarder.events_failed > 0 },
          { label: 'Batch Size', value: forwarder.batch_size },
        ].map(s => (
          <div key={s.label} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
            <p className={clsx('text-sm font-semibold', s.danger ? 'text-red-500' : 'text-gray-900 dark:text-white')}>
              {s.value}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{s.label}</p>
          </div>
        ))}
      </div>

      {testResult && (
        <div className={clsx(
          'flex items-center gap-2 text-xs p-2.5 rounded-lg',
          testResult.success
            ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
        )}>
          {testResult.success ? <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" /> : <XCircle className="w-3.5 h-3.5 flex-shrink-0" />}
          <span>{testResult.message}</span>
        </div>
      )}

      <div className="flex items-center gap-1.5 pt-1 border-t border-gray-100 dark:border-gray-800">
        <button onClick={() => onEdit(forwarder)} className="btn-ghost flex-1 justify-center text-xs">
          <Pencil className="w-3.5 h-3.5" /> Edit
        </button>
        <button
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
          className="btn-ghost flex-1 justify-center text-xs"
        >
          <TestTube className="w-3.5 h-3.5" />
          {testMutation.isPending ? 'Testing...' : 'Test'}
        </button>
        <button
          onClick={() => { if (confirm('Delete this forwarder?')) deleteMutation.mutate(); }}
          className="btn-ghost text-red-500 hover:text-red-600 p-2"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
