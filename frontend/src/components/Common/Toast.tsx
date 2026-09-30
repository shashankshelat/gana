import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import clsx from 'clsx';

export interface ToastItem {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  title?: string;
}

const CONFIG = {
  success: { icon: CheckCircle, bg: 'bg-green-50 dark:bg-green-900/30', border: 'border-green-200 dark:border-green-800', icon_class: 'text-green-500', title_class: 'text-green-800 dark:text-green-300', msg_class: 'text-green-700 dark:text-green-400' },
  error:   { icon: XCircle,      bg: 'bg-red-50 dark:bg-red-900/30',     border: 'border-red-200 dark:border-red-800',     icon_class: 'text-red-500',   title_class: 'text-red-800 dark:text-red-300',   msg_class: 'text-red-700 dark:text-red-400'   },
  warning: { icon: AlertTriangle, bg: 'bg-yellow-50 dark:bg-yellow-900/30', border: 'border-yellow-200 dark:border-yellow-800', icon_class: 'text-yellow-500', title_class: 'text-yellow-800 dark:text-yellow-300', msg_class: 'text-yellow-700 dark:text-yellow-400' },
  info:    { icon: Info,          bg: 'bg-blue-50 dark:bg-blue-900/30',   border: 'border-blue-200 dark:border-blue-800',   icon_class: 'text-blue-500',  title_class: 'text-blue-800 dark:text-blue-300',  msg_class: 'text-blue-700 dark:text-blue-400'  },
};

export default function Toast({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const c = CONFIG[item.type];
  const Icon = c.icon;
  return (
    <div className={clsx(
      'pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg max-w-sm w-full animate-fade-in',
      c.bg, c.border
    )}>
      <Icon className={clsx('w-4 h-4 flex-shrink-0 mt-0.5', c.icon_class)} />
      <div className="flex-1 min-w-0">
        {item.title && <p className={clsx('text-sm font-semibold', c.title_class)}>{item.title}</p>}
        <p className={clsx('text-sm', c.msg_class)}>{item.message}</p>
      </div>
      <button onClick={onClose} className={clsx('flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity', c.icon_class)}>
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
