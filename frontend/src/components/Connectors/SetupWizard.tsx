import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, CheckCircle, XCircle, Copy, Loader2, ArrowDownToLine, Webhook, Sparkles, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import { connectorApi } from '../../api/client';
import { Connector, ConnectorType } from '../../types';
import Modal from '../Common/Modal';
import ConfigForm from '../Common/ConfigForm';
import ConnectorLogo from './ConnectorLogo';
import { categoryOf, errorText } from './catalog';
import { useToast } from '../../hooks/useToast';

interface Props {
  type: ConnectorType | null;
  onClose: () => void;
  onDone: () => void;
}

const STEPS = ['Name', 'Connect', 'Test'];

export default function SetupWizard({ type, onClose, onDone }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [showMissing, setShowMissing] = useState(false);
  const [created, setCreated] = useState<Connector | null>(null);

  useEffect(() => {
    if (type) {
      setStep(0);
      setName(`${type.display_name}`);
      setDescription('');
      setConfig({});
      setShowMissing(false);
      setCreated(null);
      createMutation.reset();
      testMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);

  const testMutation = useMutation({
    mutationFn: (id: string) => connectorApi.test(id) as Promise<{ success: boolean; message: string }>,
  });

  const createMutation = useMutation({
    mutationFn: () => connectorApi.create({
      name: name.trim(), connector_type: type!.type_id, description: description || null,
      enabled: true, config, mapping_rules: type!.default_mapping,
    }) as Promise<Connector>,
    onSuccess: (c) => {
      setCreated(c);
      qc.invalidateQueries({ queryKey: ['connectors'] });
      toast.success(`${c.name} created`);
      testMutation.mutate(c.id);
    },
  });

  if (!type) return null;

  const props = type.config_schema.properties ?? {};
  const required = type.config_schema.required ?? [];
  const missing = required.filter(k => {
    const v = config[k];
    return v === undefined || v === null || String(v).trim() === '';
  });
  const routes = Array.isArray(type.default_mapping?._routes) ? (type.default_mapping._routes as unknown[]).length : 0;
  const webhookUrl = created ? `${window.location.origin}${created.webhook_url}` : '';

  const next = () => {
    if (step === 0 && !name.trim()) return setShowMissing(true);
    if (step === 1 && missing.length) return setShowMissing(true);
    setShowMissing(false);
    setStep(s => s + 1);
  };

  return (
    <Modal open={!!type} onClose={onClose} title={`Add ${type.display_name}`} size="xl">
      {/* Stepper */}
      <ol className="flex items-center gap-2 mb-6" aria-label="Setup steps">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-2 flex-1">
            <span className={clsx(
              'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0',
              i < step || (i === 2 && created) ? 'bg-green-500 text-white' : i === step ? 'bg-brand-600 text-white' : 'bg-gray-200 text-gray-500 dark:bg-gray-700',
            )}>
              {i < step ? <Check className="w-3.5 h-3.5" /> : i + 1}
            </span>
            <span className={clsx('text-sm', i === step ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-500')}>{label}</span>
            {i < STEPS.length - 1 && <span className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="space-y-5">
          <div className="flex items-start gap-4 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50">
            <ConnectorLogo typeId={type.type_id} name={type.display_name} size="lg" />
            <div className="min-w-0 space-y-1">
              <p className="font-semibold text-gray-900 dark:text-white">{type.display_name}</p>
              <p className="text-sm text-gray-600 dark:text-gray-400">{type.description}</p>
              <p className="text-xs text-gray-500">{categoryOf(type.category).label}</p>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div className="flex gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              {type.supports_webhook ? <Webhook className="w-5 h-5 text-brand-500 flex-shrink-0" /> : <ArrowDownToLine className="w-5 h-5 text-brand-500 flex-shrink-0" />}
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {type.supports_polling && type.supports_webhook
                  ? 'GANA pulls from the API every minute, and can also receive pushed events on a webhook.'
                  : type.supports_webhook ? 'The source pushes events to a GANA webhook URL you get at the end.'
                  : 'GANA pulls new events from the API every minute.'}
              </p>
            </div>
            <div className="flex gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              <Sparkles className="w-5 h-5 text-brand-500 flex-shrink-0" />
              <p className="text-sm text-gray-600 dark:text-gray-300">
                OCSF class assigned automatically per event{routes ? ` (${routes} event-type routes)` : ''}. Unknown event types are flagged for review.
              </p>
            </div>
          </div>

          {type.maturity === 'beta' && (
            <p className="flex gap-2 text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" /> Beta: {type.maturity_note}
            </p>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="wiz-name">Connector name *</label>
              <input id="wiz-name" className="input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Okta production" />
              {showMissing && !name.trim() && <p className="mt-1 text-xs text-red-600">Give the connector a name.</p>}
            </div>
            <div>
              <label className="label" htmlFor="wiz-desc">Description</label>
              <input id="wiz-desc" className="input" value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional" />
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          {Object.keys(props).length === 0 ? (
            <p className="text-sm text-gray-500">Nothing to configure — continue to create and test.</p>
          ) : (
            <ConfigForm schema={type.config_schema} values={config} onChange={(k, v) => setConfig(c => ({ ...c, [k]: v }))} />
          )}
          {showMissing && missing.length > 0 && (
            <p className="text-sm text-red-600 dark:text-red-400">
              Required: {missing.map(k => props[k]?.title ?? k).join(', ')}
            </p>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          {!created && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Create <b>{name}</b> and run a connection test. Polling starts within a minute once it passes.
              </p>
              {createMutation.isError && (
                <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
                  Could not create the connector: {errorText(createMutation.error)}
                </p>
              )}
            </div>
          )}

          {created && (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
                <CheckCircle className="w-4 h-4" /> {created.name} created
              </p>
              {testMutation.isPending && (
                <p className="flex items-center gap-2 text-sm text-gray-600"><Loader2 className="w-4 h-4 animate-spin" /> Testing the connection…</p>
              )}
              {testMutation.data && (
                <p className={clsx('flex items-start gap-2 text-sm rounded-lg p-3',
                  testMutation.data.success ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400' : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400')}>
                  {testMutation.data.success ? <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                  <span>{testMutation.data.success ? 'Connection test passed: ' : 'Connection test failed: '}{testMutation.data.message}
                    {!testMutation.data.success && ' You can fix the settings from the connector list (Edit).'}</span>
                </p>
              )}
              {testMutation.isError && (
                <p className="text-sm text-red-600">Connection test errored: {errorText(testMutation.error)}</p>
              )}
              {type.supports_webhook && (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">Webhook URL</p>
                  <div className="flex gap-2">
                    <code className="input font-mono text-xs flex-1 truncate">{webhookUrl}</code>
                    <button className="btn-secondary" onClick={() => { navigator.clipboard.writeText(webhookUrl); toast.info('Webhook URL copied'); }}>
                      <Copy className="w-4 h-4" /> Copy
                    </button>
                  </div>
                  <p className="text-xs text-gray-500">Paste it into {type.display_name}. To reach it from the internet, expose only the webhook port (3001).</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-3 pt-5 mt-6 border-t border-gray-200 dark:border-gray-800">
        <button onClick={step === 0 || created ? onClose : () => setStep(s => s - 1)} className="btn-secondary">
          {created ? 'Close' : step === 0 ? 'Cancel' : 'Back'}
        </button>
        {step < 2 && <button onClick={next} className="btn-primary">Continue</button>}
        {step === 2 && !created && (
          <button onClick={() => createMutation.mutate()} disabled={createMutation.isPending} className="btn-primary">
            {createMutation.isPending ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating…</> : 'Create & test'}
          </button>
        )}
        {created && <button onClick={onDone} className="btn-primary">Go to my connectors</button>}
      </div>
    </Modal>
  );
}
