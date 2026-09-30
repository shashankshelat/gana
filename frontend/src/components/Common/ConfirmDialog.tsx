import { AlertTriangle } from 'lucide-react';
import Modal from './Modal';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open, title, message, confirmLabel = 'Confirm', danger = false, onConfirm, onCancel
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onCancel} title={title} size="sm">
      <div className="flex items-start gap-3 mb-5">
        <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${danger ? 'bg-red-100 dark:bg-red-900/30' : 'bg-yellow-100 dark:bg-yellow-900/30'}`}>
          <AlertTriangle className={`w-4 h-4 ${danger ? 'text-red-500' : 'text-yellow-500'}`} />
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300 pt-1">{message}</p>
      </div>
      <div className="flex justify-end gap-3">
        <button onClick={onCancel} className="btn-secondary">Cancel</button>
        <button onClick={onConfirm} className={danger ? 'btn-danger' : 'btn-primary'}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
