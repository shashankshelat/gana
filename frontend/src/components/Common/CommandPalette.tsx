import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, LayoutDashboard, Plug, Upload, Sparkles, ClipboardCheck, FileCode, Activity, Settings, BookOpen, AlertOctagon, Clock } from 'lucide-react';
import clsx from 'clsx';

interface Command {
  id: string;
  label: string;
  description?: string;
  icon: React.ElementType;
  action: () => void;
  category: string;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const nav = (to: string) => { navigate(to); onClose(); };

  const commands: Command[] = [
    { id: 'dashboard', label: 'Go to Dashboard', icon: LayoutDashboard, action: () => nav('/dashboard'), category: 'Navigation' },
    { id: 'connectors', label: 'Go to Connectors', description: 'Manage data sources', icon: Plug, action: () => nav('/connectors'), category: 'Navigation' },
    { id: 'forwarders', label: 'Go to Forwarders', description: 'Manage destinations', icon: Upload, action: () => nav('/forwarders'), category: 'Navigation' },
    { id: 'ai-mapping', label: 'AI mapping', description: 'Open a connector → AI mapping tab', icon: Sparkles, action: () => nav('/connectors'), category: 'Navigation' },
    { id: 'approvals', label: 'Approvals', description: 'Review pending mappings', icon: ClipboardCheck, action: () => nav('/approvals'), category: 'Navigation' },
    { id: 'schema', label: 'OCSF Schema', description: 'Browse event classes', icon: FileCode, action: () => nav('/schema'), category: 'Navigation' },
    { id: 'pipeline', label: 'Pipeline Monitor', description: 'Live throughput stats', icon: Activity, action: () => nav('/pipeline'), category: 'Navigation' },
    { id: 'settings', label: 'Settings', description: 'Configure AI keys, PII, alerts', icon: Settings, action: () => nav('/settings'), category: 'Navigation' },
    { id: 'activity', label: 'Activity Log', description: 'Audit trail', icon: BookOpen, action: () => nav('/activity'), category: 'Navigation' },
    { id: 'dlq', label: 'Dead-Letter Queue', description: 'Inspect & retry failed events', icon: AlertOctagon, action: () => nav('/dlq'), category: 'Navigation' },
    { id: 'anomalies', label: 'Anomalies', description: 'Detected pipeline anomalies', icon: AlertOctagon, action: () => nav('/anomalies'), category: 'Navigation' },
    { id: 'schedule', label: 'Schedules', description: 'Connector cron jobs', icon: Clock, action: () => nav('/schedule'), category: 'Navigation' },
  ];

  const filtered = query
    ? commands.filter(c =>
        c.label.toLowerCase().includes(query.toLowerCase()) ||
        c.description?.toLowerCase().includes(query.toLowerCase())
      )
    : commands;

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => setSelected(0), [query]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === 'Enter') { e.preventDefault(); filtered[selected]?.action(); }
    if (e.key === 'Escape') onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center pt-[15vh] px-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg card shadow-2xl overflow-hidden animate-fade-in">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-800">
          <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none"
            placeholder="Search pages, actions..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
          />
          <kbd className="hidden sm:flex items-center gap-1 text-xs text-gray-400 border border-gray-200 dark:border-gray-700 rounded px-1.5 py-0.5">Esc</kbd>
        </div>

        <div className="max-h-72 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <p className="text-center text-sm text-gray-400 py-8">No results for "{query}"</p>
          ) : (
            filtered.map((cmd, i) => (
              <button
                key={cmd.id}
                onClick={cmd.action}
                onMouseEnter={() => setSelected(i)}
                className={clsx(
                  'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors',
                  i === selected ? 'bg-brand-50 dark:bg-brand-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                )}
              >
                <cmd.icon className={clsx('w-4 h-4 flex-shrink-0', i === selected ? 'text-brand-500' : 'text-gray-400')} />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{cmd.label}</p>
                  {cmd.description && <p className="text-xs text-gray-500 dark:text-gray-400">{cmd.description}</p>}
                </div>
                <span className="ml-auto text-xs text-gray-400">{cmd.category}</span>
              </button>
            ))
          )}
        </div>

        <div className="flex items-center gap-4 px-4 py-2 border-t border-gray-100 dark:border-gray-800 text-xs text-gray-400">
          <span className="flex items-center gap-1"><kbd className="border border-gray-200 dark:border-gray-700 rounded px-1">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="border border-gray-200 dark:border-gray-700 rounded px-1">↵</kbd> open</span>
        </div>
      </div>
    </div>
  );
}
