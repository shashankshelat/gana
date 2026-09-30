import { useState, useRef, useEffect } from 'react';
import { Palette, Check, Bell, User, LogOut, ChevronDown, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAppStore, THEMES } from '../../store';
import { useAuthStore } from '../../store/auth';
import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../../api/client';
import clsx from 'clsx';

const ROLE_BADGE: Record<string, string> = {
  admin: 'badge-red',
  reviewer: 'badge-blue',
  viewer: 'badge-gray',
};

export default function Header() {
  const navigate = useNavigate();
  const { theme, setTheme } = useAppStore(s => ({ theme: s.theme, setTheme: s.setTheme }));
  const { user, logout } = useAuthStore(s => ({ user: s.user, logout: s.logout }));
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [themeOpen, setThemeOpen] = useState(false);
  const themeRef = useRef<HTMLDivElement>(null);

  const { data: stats } = useQuery({
    queryKey: ['overview'],
    queryFn: pipelineApi.getOverview,
    refetchInterval: 5000,
  });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 flex items-center justify-between px-6 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div className="flex items-center gap-6">
        {stats && (
          <div className="flex items-center gap-4 text-sm">
            <span className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="font-medium text-gray-700 dark:text-gray-300">{stats.throughput_per_second ?? 0}</span>
              <span>ev/s</span>
            </span>
            <span className="text-gray-300 dark:text-gray-700">|</span>
            <span className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">{stats.enabled_connectors ?? 0}</span>
              {' '}connectors active
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button className="btn-ghost p-2" title="Notifications">
          <Bell className="w-4 h-4" />
        </button>
        <div className="relative" ref={themeRef}>
          <button
            onClick={() => setThemeOpen(o => !o)}
            className="btn-ghost p-2"
            title="Theme"
            aria-label="Choose theme"
            aria-haspopup="menu"
            aria-expanded={themeOpen}
          >
            <Palette className="w-4 h-4" />
          </button>
          {themeOpen && (
            <div role="menu" className="absolute right-0 mt-1 w-64 card shadow-lg py-1 z-50 animate-fade-in">
              <p className="px-3 pt-1.5 pb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Theme</p>
              {THEMES.map(t => (
                <button
                  key={t.id}
                  role="menuitemradio"
                  aria-checked={theme === t.id}
                  onClick={() => { setTheme(t.id); setThemeOpen(false); }}
                  className={clsx('w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800',
                    theme === t.id && 'bg-gray-50 dark:bg-gray-800')}
                >
                  <span className="flex -space-x-1 flex-shrink-0" aria-hidden>
                    {t.swatch.map(c => <span key={c} className="w-4 h-4 rounded-full ring-1 ring-black/10" style={{ background: c }} />)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm text-gray-900 dark:text-white">{t.label}</span>
                    <span className="block text-xs text-gray-500 dark:text-gray-400 truncate">{t.description}</span>
                  </span>
                  {theme === t.id && <Check className="w-4 h-4 text-brand-600 dark:text-brand-400 flex-shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* User menu */}
        {user && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(v => !v)}
              className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center flex-shrink-0">
                <span className="text-xs font-bold text-white">
                  {user.username[0].toUpperCase()}
                </span>
              </div>
              <div className="text-left hidden sm:block">
                <p className="text-sm font-medium text-gray-900 dark:text-white leading-none">{user.username}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 leading-none mt-0.5 capitalize">{user.role}</p>
              </div>
              <ChevronDown className={clsx('w-3.5 h-3.5 text-gray-400 transition-transform', menuOpen && 'rotate-180')} />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-full mt-2 w-52 card shadow-xl py-1 z-50 animate-fade-in">
                <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{user.full_name || user.username}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{user.email}</p>
                  <span className={clsx('badge mt-1', ROLE_BADGE[user.role] || 'badge-gray')}>
                    {user.role}
                  </span>
                </div>

                <div className="py-1">
                  <button className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <User className="w-4 h-4 text-gray-400" /> Profile
                  </button>
                  {user.role === 'admin' && (
                    <button className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                      <Settings className="w-4 h-4 text-gray-400" /> User Management
                    </button>
                  )}
                </div>

                <div className="border-t border-gray-100 dark:border-gray-800 py-1">
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    <LogOut className="w-4 h-4" /> Sign Out
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
