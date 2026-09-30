import { useMemo } from 'react';
import { useAppStore } from '../store';

const css = (name: string) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--c-${name}`).trim();
  return v ? `rgb(${v.split(/\s+/).join(', ')})` : '';
};

/** Chart colours from the active theme (SVG attributes can't read CSS variables directly). */
export function useThemeColors() {
  const theme = useAppStore(s => s.theme);
  return useMemo(() => ({
    blue: css('blue-500'),
    green: css('emerald-500'),
    purple: css('purple-500'),
    red: css('red-500'),
    tooltip: { backgroundColor: css('gray-800'), border: `1px solid ${css('gray-700')}`, color: css('gray-100') },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [theme]);
}
