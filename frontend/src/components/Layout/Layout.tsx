import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import { useAppStore } from '../../store';
import clsx from 'clsx';

export default function Layout() {
  const collapsed = useAppStore(s => s.sidebarCollapsed);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <Sidebar />
      <div
        className={clsx(
          'flex flex-col flex-1 min-w-0 transition-all duration-300',
          collapsed ? 'ml-16' : 'ml-64'
        )}
      >
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
