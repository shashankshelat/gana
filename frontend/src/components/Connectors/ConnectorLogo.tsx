import clsx from 'clsx';

// Monogram tiles: distinct, stable colors per connector type without shipping vendor logos
const PALETTE = [
  'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
  'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
  'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
];

function initials(name: string): string {
  const words = name.replace(/[()/]/g, ' ').split(/\s+/).filter(w => /^[A-Za-z0-9]/.test(w));
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? '?').slice(0, 2).toUpperCase();
}

export default function ConnectorLogo({ typeId, name, size = 'md' }: { typeId: string; name: string; size?: 'sm' | 'md' | 'lg' }) {
  const hash = [...typeId].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  return (
    <div
      aria-hidden
      className={clsx(
        'flex-shrink-0 rounded-lg flex items-center justify-center font-semibold',
        PALETTE[hash % PALETTE.length],
        size === 'sm' && 'w-8 h-8 text-xs',
        size === 'md' && 'w-10 h-10 text-sm',
        size === 'lg' && 'w-12 h-12 text-base',
      )}
    >
      {initials(name)}
    </div>
  );
}
