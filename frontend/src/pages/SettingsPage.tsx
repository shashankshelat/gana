import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/auth';
import { Settings, Key, Bell, Shield, Brain, ChevronDown } from 'lucide-react';
import clsx from 'clsx';

const TABS = [
  { id: 'general', label: 'General', icon: Settings },
  { id: 'ai', label: 'AI Providers', icon: Brain },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'pii', label: 'PII Detection', icon: Shield },
];

const PII_MODES = [
  { value: 'mask', label: 'Mask', description: 'Replace middle characters with ***' },
  { value: 'hash', label: 'Hash', description: 'Replace with SHA-256 hash prefix' },
  { value: 'drop', label: 'Drop', description: 'Replace with [REDACTED]' },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const canEdit = useAuthStore(s => s.can('manage_users'));
  const [tab, setTab] = useState('general');
  const [changes, setChanges] = useState<Record<string, string>>({});

  const { data: settings = {}, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data),
  });

  const { data: piiPatterns = [] } = useQuery({
    queryKey: ['pii-patterns'],
    queryFn: () => api.get('/settings/pii/patterns').then(r => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: () => api.patch('/settings', { settings: changes }),
    onSuccess: () => {
      toast.success('Settings saved', 'All changes applied');
      setChanges({});
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: () => toast.error('Failed to save settings'),
  });

  const getValue = (key: string): string => {
    if (key in changes) return changes[key];
    return String((settings[key] as { value?: string })?.value ?? '');
  };

  const setValue = (key: string, value: string) => setChanges(c => ({ ...c, [key]: value }));

  // Tests the key typed in the box, or the saved one if the box is untouched
  const aiTest = useMutation({
    mutationFn: () => api.post('/settings/ai/test', {
      provider: 'claude',
      api_key: changes['ai.claude_api_key'] || null,
    }).then(r => r.data as { success: boolean; message: string }),
    onError: (e: unknown) => toast.error(
      String((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Request failed'),
      'Connection test failed'),
  });

  const hasChanges = Object.keys(changes).length > 0;

  const renderField = (key: string, label: string, type: 'text' | 'password' | 'number' | 'select' | 'toggle' = 'text', options?: { value: string; label: string }[]) => {
    const meta = settings[key] as { is_secret?: boolean; description?: string } | undefined;
    const isSecret = meta?.is_secret;

    return (
      <div key={key}>
        <label className="label">{label}</label>
        {type === 'toggle' ? (
          <label className="flex items-center gap-3 cursor-pointer">
            <button
              type="button"
              onClick={() => setValue(key, getValue(key) === 'true' ? 'false' : 'true')}
              className={clsx(
                'relative inline-flex h-5 w-9 rounded-full border-2 border-transparent transition-colors',
                getValue(key) === 'true' ? 'bg-brand-600' : 'bg-gray-200 dark:bg-gray-700'
              )}
              disabled={!canEdit}
            >
              <span className={clsx('inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform', getValue(key) === 'true' ? 'translate-x-4' : 'translate-x-0')} />
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400">{getValue(key) === 'true' ? 'Enabled' : 'Disabled'}</span>
          </label>
        ) : type === 'select' && options ? (
          <select className="input" value={getValue(key)} onChange={e => setValue(key, e.target.value)} disabled={!canEdit}>
            {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : (
          <input
            className="input"
            type={isSecret ? 'password' : type === 'number' ? 'number' : 'text'}
            value={getValue(key)}
            onChange={e => setValue(key, e.target.value)}
            placeholder={isSecret ? '••••••••' : ''}
            disabled={!canEdit}
            autoComplete="new-password"
          />
        )}
        {meta?.description && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{meta.description}</p>}
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Configure platform behaviour, AI providers, alerts, and security</p>
      </div>

      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
            tab === t.id ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
          )}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      <div className="card p-6 space-y-5">
        {isLoading ? (
          <div className="space-y-4">{[1,2,3].map(i => <div key={i} className="h-12 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-lg" />)}</div>
        ) : (
          <>
            {tab === 'general' && (
              <>
                <h2 className="font-semibold text-gray-900 dark:text-white">General</h2>
                {renderField('app.name', 'Application Name')}
                {renderField('schema.update_interval_hours', 'Schema Update Interval (hours)', 'number')}
              </>
            )}

            {tab === 'ai' && (
              <>
                <h2 className="font-semibold text-gray-900 dark:text-white">AI Provider Keys</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Save API keys here so you don't have to paste them on every AI analysis. Keys are encrypted at rest and never shown again after saving.</p>
                {renderField('ai.default_provider', 'Default Provider', 'select', [
                  { value: 'claude', label: 'Anthropic Claude' },
                  { value: 'openai', label: 'OpenAI ChatGPT' },
                  { value: 'gemini', label: 'Google Gemini' },
                ])}
                {renderField('ai.claude_api_key', 'Anthropic API Key', 'password')}
                <div className="flex items-center gap-3 -mt-2">
                  <button type="button" onClick={() => aiTest.mutate()} disabled={aiTest.isPending || !canEdit} className="btn-secondary text-sm">
                    {aiTest.isPending ? 'Testing…' : 'Test Claude connection'}
                  </button>
                  {aiTest.data && (
                    <span className={clsx('text-sm', aiTest.data.success ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
                      {aiTest.data.success ? '✓ ' : '✗ '}{aiTest.data.message}
                    </span>
                  )}
                </div>
                {renderField('ai.openai_api_key', 'OpenAI API Key', 'password')}
                {renderField('ai.gemini_api_key', 'Google Gemini API Key', 'password')}
              </>
            )}

            {tab === 'alerts' && (
              <>
                <h2 className="font-semibold text-gray-900 dark:text-white">Alert Destinations</h2>
                {renderField('alerts.connector_stale_minutes', 'Connector Silence Alert (minutes)', 'number')}
                {renderField('alerts.slack_webhook', 'Slack Incoming Webhook URL', 'password')}
                {renderField('alerts.pagerduty_key', 'PagerDuty Integration Key', 'password')}
              </>
            )}

            {tab === 'pii' && (
              <>
                <h2 className="font-semibold text-gray-900 dark:text-white">PII Detection & Masking</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Scan and redact personally identifiable information from events before they are forwarded.</p>
                {renderField('pii.enabled', 'Enable PII Detection', 'toggle')}
                {getValue('pii.enabled') === 'true' && (
                  <>
                    {renderField('pii.mode', 'Redaction Mode', 'select', PII_MODES)}
                    <div>
                      <label className="label">Active Patterns</label>
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        {piiPatterns.map((p: { id: string; name: string; example: string }) => {
                          const active = JSON.parse(getValue('pii.patterns') || '[]') as string[];
                          const checked = active.includes(p.id);
                          return (
                            <label key={p.id} className={clsx('flex items-start gap-2.5 p-3 rounded-lg border cursor-pointer transition-colors', checked ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-gray-200 dark:border-gray-700')}>
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={!canEdit}
                                onChange={e => {
                                  const newActive = e.target.checked ? [...active, p.id] : active.filter(x => x !== p.id);
                                  setValue('pii.patterns', JSON.stringify(newActive));
                                }}
                                className="mt-0.5"
                              />
                              <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">{p.name}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">{p.example}</p>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>

      {canEdit && (
        <div className="flex justify-end gap-3">
          <button onClick={() => setChanges({})} disabled={!hasChanges} className="btn-secondary">Discard</button>
          <button onClick={() => saveMutation.mutate()} disabled={!hasChanges || saveMutation.isPending} className="btn-primary">
            {saveMutation.isPending ? 'Saving...' : `Save${hasChanges ? ` (${Object.keys(changes).length})` : ''}`}
          </button>
        </div>
      )}
    </div>
  );
}
