import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/auth';
import EmptyState from '../components/Common/EmptyState';
import { AlertOctagon, CheckCircle, TrendingUp, TrendingDown, Volume2 } from 'lucide-react';
import clsx from 'clsx';

interface Anomaly {
  id: string;
  connector_id: string;
  connector_type: string;
  anomaly_type: string;
  severity: string;
  title: string;
  description: string;
  baseline_value: number;
  observed_value: number;
  z_score: number;
  acknowledged: boolean;
  acknowledged_by: string;
  created_at: string;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'badge-red',
  high: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400',
  medium: 'badge-yellow',
  low: 'badge-blue',
};

const TYPE_ICONS: Record<string, React.ElementType> = {
  volume_spike: TrendingUp,
  volume_drop: TrendingDown,
  silence: Volume2,
};

export default function AnomalyPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const can = useAuthStore(s => s.can);

  const { data: anomalies = [], isLoading } = useQuery<Anomaly[]>({
    queryKey: ['anomalies'],
    queryFn: () => api.get('/anomalies?acknowledged=false').then(r => r.data),
    refetchInterval: 15000,
  });

  const { data: stats } = useQuery({
    queryKey: ['anomaly-stats'],
    queryFn: () => api.get('/anomalies/stats').then(r => r.data),
    refetchInterval: 15000,
  });

  const ackMutation = useMutation({
    mutationFn: (id: string) => api.post(`/anomalies/${id}/acknowledge`),
    onSuccess: () => { toast.success('Anomaly acknowledged'); qc.invalidateQueries({ queryKey: ['anomalies'] }); },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <AlertOctagon className="w-6 h-6 text-orange-400" /> Anomaly Detection
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">ML-based detection of unusual patterns in your pipeline</p>
        </div>
        {stats && (
          <div className="flex gap-3">
            <div className="stat-card p-3 min-w-[80px] text-center">
              <p className="text-xl font-bold text-red-500">{stats.critical_unacknowledged}</p>
              <p className="text-xs text-gray-500">Critical</p>
            </div>
            <div className="stat-card p-3 min-w-[80px] text-center">
              <p className="text-xl font-bold text-gray-900 dark:text-white">{stats.unacknowledged}</p>
              <p className="text-xs text-gray-500">Unacked</p>
            </div>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="card h-20 animate-pulse bg-gray-100 dark:bg-gray-800" />)}</div>
      ) : anomalies.length === 0 ? (
        <EmptyState icon={CheckCircle} title="No anomalies detected" description="The pipeline is operating within normal parameters. Anomalies will appear here when detected." />
      ) : (
        <div className="space-y-3">
          {anomalies.map(anomaly => {
            const Icon = TYPE_ICONS[anomaly.anomaly_type] || AlertOctagon;
            return (
              <div key={anomaly.id} className="card p-4">
                <div className="flex items-start gap-3">
                  <div className={clsx(
                    'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
                    anomaly.severity === 'critical' ? 'bg-red-100 dark:bg-red-900/30' : 'bg-orange-100 dark:bg-orange-900/30'
                  )}>
                    <Icon className={clsx('w-4 h-4', anomaly.severity === 'critical' ? 'text-red-500' : 'text-orange-500')} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-sm text-gray-900 dark:text-white">{anomaly.title}</p>
                      <span className={clsx('badge', SEVERITY_STYLES[anomaly.severity] || 'badge-gray')}>{anomaly.severity}</span>
                      <span className="badge badge-gray">{anomaly.anomaly_type.replace('_', ' ')}</span>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{anomaly.description}</p>
                    {anomaly.baseline_value !== null && (
                      <div className="flex gap-4 mt-2 text-xs text-gray-500">
                        <span>Baseline: <span className="font-medium">{anomaly.baseline_value?.toFixed(1)}</span></span>
                        <span>Observed: <span className="font-medium">{anomaly.observed_value?.toFixed(1)}</span></span>
                        {anomaly.z_score && <span>Z-score: <span className="font-medium">{anomaly.z_score?.toFixed(2)}</span></span>}
                      </div>
                    )}
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <p className="text-xs text-gray-400">{new Date(anomaly.created_at).toLocaleString()}</p>
                    {can('approve') && !anomaly.acknowledged && (
                      <button onClick={() => ackMutation.mutate(anomaly.id)} className="btn-ghost text-xs mt-1">
                        <CheckCircle className="w-3.5 h-3.5" /> Acknowledge
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
