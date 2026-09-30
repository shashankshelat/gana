import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-4">
        <Icon className="w-7 h-7 text-gray-400 dark:text-gray-500" />
      </div>
      <p className="text-lg font-semibold text-gray-900 dark:text-white">{title}</p>
      {description && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-xs">{description}</p>
      )}
      {action && (
        <button onClick={action.onClick} className="btn-primary mt-5">
          {action.label}
        </button>
      )}
    </div>
  );
}
