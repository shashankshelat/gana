import { createContext, useState, useCallback, ReactNode } from 'react';
import Toast, { ToastItem } from './Toast';

interface ToastContextValue {
  toast: {
    success: (msg: string, title?: string) => void;
    error: (msg: string, title?: string) => void;
    warning: (msg: string, title?: string) => void;
    info: (msg: string, title?: string) => void;
  };
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const add = useCallback((type: ToastItem['type'], message: string, title?: string) => {
    const id = Date.now().toString();
    setToasts(t => [...t, { id, type, message, title }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4500);
  }, []);

  const remove = useCallback((id: string) => setToasts(t => t.filter(x => x.id !== id)), []);

  const toast = {
    success: (msg: string, title?: string) => add('success', msg, title),
    error: (msg: string, title?: string) => add('error', msg, title),
    warning: (msg: string, title?: string) => add('warning', msg, title),
    info: (msg: string, title?: string) => add('info', msg, title),
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => <Toast key={t.id} item={t} onClose={() => remove(t.id)} />)}
      </div>
    </ToastContext.Provider>
  );
}
