import { useContext } from 'react';
import { ToastContext } from '../components/Common/ToastProvider';

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be inside ToastProvider');
  return ctx;
}
