import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../api/client';
import { Activity, Zap, AlertOctagon, TrendingUp, Server } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import clsx from 'clsx';
import { usePipelineHistory } from '../hooks/usePipelineHistory';
import { useThemeColors } from '../hooks/useThemeColors';

export default function PipelinePage() {
  const { data: history = [] } = usePipelineHistory(60);
  const colors = useThemeColors();
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);

  const { data: stats } = useQuery({
    queryKey: ['pipeline-stats'],
    queryFn: pipelineApi.getStats,
    refetchInterval: 2000,
  });

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/pipeline/stream`;
    setWsStatus('connecting');

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus('connected');
    ws.onclose = () => setWsStatus('disconnected');
    ws.onerror = () => setWsStatus('disconnected');

    return () => ws.close();
  }, []);

  const formatNum = (n: number | null | undefined) =>
    n != null ? n.toLocaleString() : '—';

  const metricsCards = [
    { icon: TrendingUp, label: 'Events/sec', value: `${stats?.throughput_per_second ?? 0}`, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20' },
    { icon: Activity, label: 'Total Received', value: formatNum(stats?.events_received), color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
    { icon: Zap, label: 'Total Mapped', value: formatNum(stats?.events_mapped), color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-900/20' },
    { icon: AlertOctagon, label: 'Total Failed', to: '/dlq', value: formatNum(stats?.events_failed), color: stats?.events_failed ? 'text-red-500' : 'text-gray-400', bg: stats?.events_failed ? 'bg-red-50 dark:bg-red-900/20' : 'bg-gray-50 dark:bg-gray-800' },
    { icon: Server, label: 'Total Forwarded', value: formatNum(stats?.events_forwarded), color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Pipeline Monitor</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Real-time OCSF processing pipeline metrics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx(
            'flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
            wsStatus === 'connected'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
              : wsStatus === 'connecting'
              ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
          )}>
            <span className={clsx(
              'w-1.5 h-1.5 rounded-full',
              wsStatus === 'connected' ? 'bg-green-500 animate-pulse' : wsStatus === 'connecting' ? 'bg-yellow-500' : 'bg-gray-400'
            )} />
            {wsStatus === 'connected' ? 'Live' : wsStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {metricsCards.map(m => {
          const body = (
            <>
              <div className={`w-9 h-9 rounded-lg ${m.bg} flex items-center justify-center`}>
                <m.icon className={`w-4 h-4 ${m.color}`} />
              </div>
              <p className="text-xl font-bold text-gray-900 dark:text-white">{m.value}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{m.label}{'to' in m && ' →'}</p>
            </>
          );
          return 'to' in m && m.to ? (
            <Link key={m.label} to={m.to} className="stat-card hover:ring-2 hover:ring-red-300 dark:hover:ring-red-800 transition" title="Open the dead-letter queue">
              {body}
            </Link>
          ) : (
            <div key={m.label} className="stat-card">{body}</div>
          );
        })}
      </div>

      {/* Chart */}
      <div className="card p-5">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-4">Events per minute (last hour)</h2>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.06} />
            <XAxis dataKey="ts" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{
                ...colors.tooltip,
                borderRadius: '8px',
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="events_received" name="Received" stroke={colors.blue} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="events_mapped" name="Mapped" stroke={colors.green} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="events_forwarded" name="Forwarded" stroke={colors.purple} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="events_failed" name="Failed" stroke={colors.red} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Architecture diagram */}
      <div className="card p-5">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-4">Pipeline Architecture</h2>
        <div className="flex items-center justify-center gap-2 overflow-x-auto py-4">
          {[
            { label: 'Sources', sub: 'SaaS / Webhooks / Syslog', color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800' },
            { label: '→', sub: '', color: 'text-gray-400 text-xl font-bold' },
            { label: 'Kafka', sub: 'Raw Events Topic', color: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800' },
            { label: '→', sub: '', color: 'text-gray-400 text-xl font-bold' },
            { label: 'OCSF Mapper', sub: 'Field Normalization', color: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-800' },
            { label: '→', sub: '', color: 'text-gray-400 text-xl font-bold' },
            { label: 'Kafka', sub: 'Mapped Events Topic', color: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800' },
            { label: '→', sub: '', color: 'text-gray-400 text-xl font-bold' },
            { label: 'Forwarders', sub: 'Splunk / Databricks / ES', color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800' },
          ].map((step, i) =>
            step.sub ? (
              <div key={i} className={`flex-shrink-0 px-4 py-3 rounded-xl border text-center min-w-[110px] ${step.color}`}>
                <p className="text-sm font-semibold">{step.label}</p>
                <p className="text-xs mt-0.5 opacity-80">{step.sub}</p>
              </div>
            ) : (
              <span key={i} className={step.color}>{step.label}</span>
            )
          )}
        </div>
      </div>
    </div>
  );
}
