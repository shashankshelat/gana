import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Theme = 'light' | 'dark' | 'sepia' | 'solarized' | 'colorblind';

export const THEMES: { id: Theme; label: string; description: string; swatch: [string, string, string] }[] = [
  { id: 'light', label: 'Light', description: 'Default light', swatch: ['#f9fafb', '#111827', '#2563eb'] },
  { id: 'dark', label: 'Dark', description: 'Default dark', swatch: ['#030712', '#f3f4f6', '#3b82f6'] },
  { id: 'sepia', label: 'Sepia / Warm', description: 'Paper tones, easy on the eyes', swatch: ['#f4ecd8', '#3e3122', '#b5652b'] },
  { id: 'solarized', label: 'Solarized', description: 'Solarized dark palette', swatch: ['#002b36', '#93a1a1', '#268bd2'] },
  { id: 'colorblind', label: 'Colorblind friendly', description: 'Okabe–Ito colours, no red/green pairs', swatch: ['#f9fafb', '#0072b2', '#d55e00'] },
];

// Themes built on Tailwind's dark variants
const DARK_THEMES: Theme[] = ['dark', 'solarized'];

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle('dark', DARK_THEMES.includes(theme));
  root.dataset.theme = theme;
}

interface AppState {
  theme: Theme;
  sidebarCollapsed: boolean;
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'dark',
      sidebarCollapsed: false,
      // Apply before the state change so components reading theme colours during render see the new palette
      setTheme: (theme) => { applyTheme(theme); set({ theme }); },
      toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: 'ocsf-app' }
  )
);
