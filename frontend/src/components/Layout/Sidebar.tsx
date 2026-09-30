import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Plug, Upload, FileCode, Activity,
  ChevronLeft, ChevronRight, Shield, ClipboardCheck,
  Settings, BookOpen, AlertOctagon, Clock, TrendingDown, Database
} from 'lucide-react';
import { useAppStore } from '../../store';
import { useAuthStore } from '../../store/auth';
import clsx from 'clsx';

const NAV_GROUPS = [
  {
    label: 'Pipeline',
    items: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/connectors', icon: Plug, label: 'Connectors' },
      { to: '/forwarders', icon: Upload, label: 'Forwarders' },
      { to: '/pipeline', icon: Activity, label: 'Pipeline' },
      { to: '/ingestion', icon: Database, label: 'Ingestion' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/approvals', icon: ClipboardCheck, label: 'Approvals' },
      { to: '/anomalies', icon: TrendingDown, label: 'Anomalies' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/schedule', icon: Clock, label: 'Schedules' },
      { to: '/dlq', icon: AlertOctagon, label: 'DLQ' },
      { to: '/activity', icon: BookOpen, label: 'Activity Log' },
    ],
  },
  {
    label: 'Config',
    items: [
      { to: '/schema', icon: FileCode, label: 'OCSF Schema' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

export default function Sidebar() {
  const { collapsed, toggle } = useAppStore(s => ({
    collapsed: s.sidebarCollapsed,
    toggle: s.toggleSidebar,
  }));

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 left-0 z-30 flex flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 transition-all duration-300',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-bold text-gray-900 dark:text-white truncate">GANA</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">Map. Normalize. Understand.</p>
            </div>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-4 overflow-y-auto">
        {NAV_GROUPS.map(group => (
          <div key={group.label}>
            {!collapsed && (
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-150',
                      isActive
                        ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-400'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  <Icon className="flex-shrink-0 w-4 h-4" />
                  {!collapsed && <span className="truncate">{label}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Cmd+K hint */}
      {!collapsed && (
        <div className="px-3 pb-2">
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
            <span className="flex-1">Search</span>
            <kbd className="font-mono">⌘K</kbd>
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-800">
        <button
          onClick={toggle}
          className="btn-ghost w-full justify-center"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
