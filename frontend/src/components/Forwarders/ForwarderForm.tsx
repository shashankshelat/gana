import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { forwarderApi } from '../../api/client';
import { Forwarder, ForwarderType } from '../../types';
import Modal from '../Common/Modal';
import ConfigForm from '../Common/ConfigForm';
import clsx from 'clsx';

interface ForwarderFormProps {
  open: boolean;
  onClose: () => void;
  editingForwarder?: Forwarder | null;
}

const TABS = ['General', 'Configuration', 'Filters'];

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
  return err instanceof Error ? err.message : String(err);
}

export default function ForwarderForm({ open, onClose, editingForwarder }: ForwarderFormProps) {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [selectedType, setSelectedType] = useState<ForwarderType | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    forwarder_type: '',
    description: '',
    enabled: true,
    batch_size: 100,
    flush_interval_ms: 1000,
    config: {} as Record<string, unknown>,
    filter_rules: {} as Record<string, unknown>,
  });

  const { data: forwarderTypes = [] } = useQuery<ForwarderType[]>({
    queryKey: ['forwarder-types'],
    queryFn: forwarderApi.getTypes,
  });

  useEffect(() => {
    if (editingForwarder) {
      setFormData({
        name: editingForwarder.name,
        forwarder_type: editingForwarder.forwarder_type,
        description: editingForwarder.description || '',
        enabled: editingForwarder.enabled,
        batch_size: editingForwarder.batch_size,
        flush_interval_ms: editingForwarder.flush_interval_ms,
        config: editingForwarder.config || {},
        filter_rules: editingForwarder.filter_rules || {},
      });
      const t = forwarderTypes.find(ft => ft.type_id === editingForwarder.forwarder_type);
      setSelectedType(t || null);
    } else {
      setFormData({ name: '', forwarder_type: '', description: '', enabled: true, batch_size: 100, flush_interval_ms: 1000, config: {}, filter_rules: {} });
      setSelectedType(null);
    }
    setTab(0);
    saveMutation.reset();
  }, [editingForwarder, open]);

  const saveMutation = useMutation({
    mutationFn: () =>
      editingForwarder
        ? forwarderApi.update(editingForwarder.id, formData)
        : forwarderApi.create(formData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['forwarders'] });
      onClose();
    },
  });

  const missing = [
    !formData.name.trim() && 'Name (General tab)',
    !formData.forwarder_type && 'Forwarder Type (General tab)',
    ...(selectedType?.config_schema.required ?? [])
      .filter(k => {
        const v = formData.config[k];
        // Editing keeps the masked "***" secret, which the backend preserves
        return v === undefined || v === null || String(v).trim() === '';
      })
      .map(k => `${selectedType?.config_schema.properties?.[k]?.title ?? k} (Configuration tab)`),
  ].filter(Boolean) as string[];

  const grouped = forwarderTypes.reduce<Record<string, ForwarderType[]>>((acc, t) => {
    acc[t.category] = [...(acc[t.category] || []), t];
    return acc;
  }, {});

  const categoryLabel: Record<string, string> = {
    siem: 'SIEM',
    data_lake: 'Data Lake',
    storage: 'Object Storage',
    streaming: 'Streaming',
    observability: 'Observability & Log Platforms',
    cloud: 'Cloud Logging',
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingForwarder ? 'Edit Forwarder' : 'New Forwarder'}
      size="xl"
    >
      <div className="flex gap-1 mb-6 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        {TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={clsx(
              'flex-1 py-1.5 text-sm font-medium rounded-md transition-colors duration-150',
              tab === i
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 0 && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Forwarder Name *</label>
              <input
                className="input"
                value={formData.name}
                onChange={e => setFormData(f => ({ ...f, name: e.target.value }))}
                placeholder="My Splunk Forwarder"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label">Batch Size</label>
                <input
                  type="number"
                  className="input"
                  value={formData.batch_size}
                  onChange={e => setFormData(f => ({ ...f, batch_size: Number(e.target.value) }))}
                />
              </div>
              <div>
                <label className="label">Flush ms</label>
                <input
                  type="number"
                  className="input"
                  value={formData.flush_interval_ms}
                  onChange={e => setFormData(f => ({ ...f, flush_interval_ms: Number(e.target.value) }))}
                />
              </div>
            </div>
          </div>

          <div>
            <label className="label">Forwarder Type *</label>
            <div className="space-y-3 mt-2">
              {Object.entries(grouped).map(([cat, types]) => (
                <div key={cat}>
                  <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
                    {categoryLabel[cat] || cat}
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {types.map(type => (
                      <button
                        key={type.type_id}
                        onClick={() => {
                          setSelectedType(type);
                          setFormData(f => ({ ...f, forwarder_type: type.type_id, batch_size: Math.min(f.batch_size, type.max_batch_size), config: {} }));
                        }}
                        className={clsx(
                          'p-3 rounded-lg border-2 text-left transition-all duration-150',
                          selectedType?.type_id === type.type_id
                            ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                        )}
                      >
                        <p className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1.5">
                          {type.display_name}
                          {type.maturity === 'beta' && <span className="badge badge-yellow" title={type.maturity_note}>Beta</span>}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{type.description}</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Max batch: {type.max_batch_size.toLocaleString()}</p>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 1 && (
        <div>
          {selectedType ? (
            <ConfigForm
              schema={selectedType.config_schema}
              values={formData.config}
              onChange={(k, v) => setFormData(f => ({ ...f, config: { ...f.config, [k]: v } }))}
            />
          ) : (
            <div className="text-center py-10 text-gray-400 dark:text-gray-500">Select a forwarder type first</div>
          )}
        </div>
      )}

      {tab === 2 && (
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Filter which OCSF events are forwarded to this destination.
          </p>
          <div>
            <label className="label">Min Severity (0=all, 1=Info, 2=Low, 3=Med, 4=High, 5=Critical)</label>
            <input
              type="number"
              min={0}
              max={5}
              className="input w-32"
              value={Number((formData.filter_rules as Record<string, unknown>).severity_min ?? 0)}
              onChange={e => setFormData(f => ({ ...f, filter_rules: { ...f.filter_rules, severity_min: Number(e.target.value) } }))}
            />
          </div>
        </div>
      )}

      {saveMutation.isError && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          Save failed: {errorText(saveMutation.error)}
        </p>
      )}

      <div className="flex items-center justify-end gap-3 pt-5 mt-5 border-t border-gray-200 dark:border-gray-800">
        {missing.length > 0 && (
          <p className="mr-auto text-xs text-amber-600 dark:text-amber-400">
            Required: {missing.join(', ')}
          </p>
        )}
        <button onClick={onClose} className="btn-secondary">Cancel</button>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || missing.length > 0}
          className="btn-primary"
        >
          {saveMutation.isPending ? 'Saving...' : editingForwarder ? 'Update Forwarder' : 'Create Forwarder'}
        </button>
      </div>
    </Modal>
  );
}
