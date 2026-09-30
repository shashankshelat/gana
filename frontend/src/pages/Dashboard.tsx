import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../api/client';
import {
  Activity, Plug, Upload, TrendingUp, AlertTriangle, CheckCircle,
  ArrowUpRight
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import { usePipelineHistory } from '../hooks/usePipelineHistory';
import { useThemeColors } from '../hooks/useThemeColors';

export default function Dashboard() {
  const { data: history = [] } = usePipelineHistory(60);
  const colors = useThemeColors();

  const { data: stats } = useQuery({
    queryKey: ['overview'],
    queryFn: pipelineApi.getOverview,
    refetchInterval: 3000,
  });


  const statCards = [
    {
      label: 'Events Received',
      value: stats?.events_received?.toLocaleString() ?? '—',
      icon: TrendingUp,
      color: 'text-blue-500',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      label: 'Events Mapped',
      value: stats?.events_mapped?.toLocaleString() ?? '—',
      icon: CheckCircle,
      color: 'text-green-500',
      bg: 'bg-green-50 dark:bg-green-900/20',
    },
    {
      label: 'Events Failed',
      to: '/dlq',
      value: stats?.events_failed?.toLocaleString() ?? '—',
      icon: AlertTriangle,
      color: stats?.events_failed ? 'text-red-500' : 'text-gray-400',
      bg: stats?.events_failed ? 'bg-red-50 dark:bg-red-900/20' : 'bg-gray-50 dark:bg-gray-800',
    },
    {
      label: 'Throughput',
      value: `${stats?.throughput_per_second ?? 0} ev/s`,
      icon: Activity,
      color: 'text-purple-500',
      bg: 'bg-purple-50 dark:bg-purple-900/20',
    },
    {
      label: 'Active Connectors',
      value: `${stats?.enabled_connectors ?? 0} / ${stats?.total_connectors ?? 0}`,
      icon: Plug,
      color: 'text-brand-500',
      bg: 'bg-brand-50 dark:bg-brand-900/20',
    },
    {
      label: 'Forwarders',
      value: stats?.total_forwarders?.toString() ?? '—',
      icon: Upload,
      color: 'text-orange-500',
      bg: 'bg-orange-50 dark:bg-orange-900/20',
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Real-time GANA pipeline overview
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {statCards.map(card => {
          const body = (
            <>
              <div className={`w-9 h-9 rounded-lg ${card.bg} flex items-center justify-center`}>
                <card.icon className={`w-4 h-4 ${card.color}`} />
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{card.value}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{card.label}{'to' in card && ' →'}</p>
            </>
          );
          return 'to' in card && card.to ? (
            <Link key={card.label} to={card.to} className="stat-card hover:ring-2 hover:ring-red-300 dark:hover:ring-red-800 transition" title="Open the dead-letter queue">
              {body}
            </Link>
          ) : (
            <div key={card.label} className="stat-card">{body}</div>
          );
        })}
      </div>

      {/* Throughput chart */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-900 dark:text-white">Events per minute (last hour)</h2>
          <span className="flex items-center gap-1.5 text-sm text-green-500">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            Live
          </span>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={history}>
            <defs>
              <linearGradient id="throughput" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.blue} stopOpacity={0.3} />
                <stop offset="95%" stopColor={colors.blue} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="mapped" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.green} stopOpacity={0.3} />
                <stop offset="95%" stopColor={colors.green} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.06} />
            <XAxis dataKey="ts" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{
                ...colors.tooltip,
                borderRadius: '8px',
                fontSize: 12,
              }}
            />
            <Area type="monotone" dataKey="events_received" name="Received" stroke={colors.blue} fill="url(#throughput)" strokeWidth={2} dot={false} />
            <Area type="monotone" dataKey="events_mapped" name="Mapped" stroke={colors.green} fill="url(#mapped)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-3">Quick Start</h2>
          <div className="space-y-2">
            {[
              { icon: Plug, label: 'Add a connector', href: '/connectors', desc: 'Connect a SaaS source' },
              { icon: Upload, label: 'Add a forwarder', href: '/forwarders', desc: 'Configure a SIEM or data lake destination' },
            ].map(({ icon: Icon, label, href, desc }) => (
              <a
                key={href}
                href={href}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-150 group"
              >
                <div className="w-8 h-8 rounded-lg bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-brand-600 dark:text-brand-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{label}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{desc}</p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-gray-400 ml-auto group-hover:text-brand-500 transition-colors" />
              </a>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-3">Pipeline Health</h2>
          <div className="space-y-3">
            {[
              { label: 'Kafka Ingestion', ok: true },
              { label: 'OCSF Mapping', ok: true },
              { label: 'Schema Version', ok: true, note: 'Up to date' },
              { label: 'Forwarders', ok: (stats?.total_forwarders ?? 0) > 0, note: stats?.total_forwarders ? 'Configured' : 'None configured' },
            ].map(({ label, ok, note }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
                <div className="flex items-center gap-1.5">
                  {note && <span className="text-xs text-gray-500 dark:text-gray-400">{note}</span>}
                  <span className={`w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-yellow-500'}`} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
