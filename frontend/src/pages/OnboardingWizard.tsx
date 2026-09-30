import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Plug, Upload, Sparkles, ArrowRight, Check, X } from 'lucide-react';
import clsx from 'clsx';

const STEPS = [
  { id: 'welcome', title: 'Welcome to GANA', icon: Shield },
  { id: 'forwarder', title: 'Add your first destination', icon: Upload },
  { id: 'connector', title: 'Add your first connector', icon: Plug },
  { id: 'ai', title: 'Try AI Mapping', icon: Sparkles },
];

interface OnboardingWizardProps {
  onDismiss: () => void;
}

export default function OnboardingWizard({ onDismiss }: OnboardingWizardProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [completed, setCompleted] = useState<Set<number>>(new Set());

  const markDone = (i: number) => setCompleted(s => new Set([...s, i]));

  const handleAction = () => {
    markDone(step);
    if (step === 1) navigate('/forwarders');
    if (step === 2) navigate('/connectors');
    if (step === 3) { navigate('/connectors'); onDismiss(); return; }
    if (step < STEPS.length - 1) setStep(s => s + 1);
    else onDismiss();
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative w-full max-w-2xl card shadow-2xl animate-fade-in">
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-2">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center gap-1">
                <div className={clsx(
                  'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all',
                  completed.has(i) ? 'bg-green-500 text-white' : i === step ? 'bg-brand-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-500'
                )}>
                  {completed.has(i) ? <Check className="w-3.5 h-3.5" /> : i + 1}
                </div>
                {i < STEPS.length - 1 && <div className={clsx('w-8 h-0.5', i < step ? 'bg-brand-600' : 'bg-gray-200 dark:bg-gray-700')} />}
              </div>
            ))}
          </div>
          <button onClick={onDismiss} className="btn-ghost p-1.5"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-8 text-center">
          {step === 0 && (
            <div className="space-y-5">
              <div className="w-16 h-16 rounded-2xl bg-brand-600 flex items-center justify-center mx-auto">
                <Shield className="w-8 h-8 text-white" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Welcome to GANA</h2>
              <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
                Map. Normalize. Understand. Your open-source platform for normalizing security logs to the OCSF standard and routing them to any SIEM or data lake.
              </p>
              <div className="grid grid-cols-3 gap-4 text-left mt-6">
                {[
                  { icon: Plug, title: '19 Connectors', desc: 'Okta, CrowdStrike, AWS, Azure, GCP...' },
                  { icon: Upload, title: '10 Destinations', desc: 'Splunk, Databricks, Elasticsearch...' },
                  { icon: Sparkles, title: 'AI Mapping', desc: 'Auto-generate OCSF mappings' },
                ].map(({ icon: Icon, title, desc }) => (
                  <div key={title} className="card p-4">
                    <Icon className="w-5 h-5 text-brand-500 mb-2" />
                    <p className="font-semibold text-sm text-gray-900 dark:text-white">{title}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{desc}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-xl bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center mx-auto">
                <Upload className="w-6 h-6 text-brand-600 dark:text-brand-400" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">Add a destination</h2>
              <p className="text-gray-500 dark:text-gray-400">Configure where to send your OCSF-normalized events — Splunk, Databricks, Elasticsearch, S3, or any other destination. Every connector sends to it, so set this up first.</p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-xl bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center mx-auto">
                <Plug className="w-6 h-6 text-brand-600 dark:text-brand-400" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">Add your first connector</h2>
              <p className="text-gray-500 dark:text-gray-400">Connect a data source — Okta, AWS CloudTrail, CrowdStrike, or any webhook source. Its logs are pulled automatically, mapped to OCSF, and sent to your destination.</p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-xl bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center mx-auto">
                <Sparkles className="w-6 h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">Try AI-powered mapping</h2>
              <p className="text-gray-500 dark:text-gray-400">Each connector has an AI mapping tab. When events fail to map, GANA automatically asks the AI for a corrected OCSF mapping and sends it to Approvals, so an analyst reviews it before it goes live. You can also paste sample events there.</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-5 border-t border-gray-200 dark:border-gray-800">
          <button onClick={onDismiss} className="btn-ghost text-sm">Skip setup</button>
          <button onClick={handleAction} className="btn-primary">
            {step < STEPS.length - 1 ? (
              <>{step === 0 ? 'Get Started' : `Go to ${STEPS[step].title}`} <ArrowRight className="w-4 h-4" /></>
            ) : (
              <>Open AI Mapping <Sparkles className="w-4 h-4" /></>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
