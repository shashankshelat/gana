import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../api/client';

export interface HistoryPoint {
  minute: string;
  ts: string;
  events_received: number;
  events_mapped: number;
  events_failed: number;
  events_forwarded: number;
}

// Per-minute counts stored server-side, so charts survive page refreshes and backend restarts
export function usePipelineHistory(minutes = 60) {
  return useQuery<HistoryPoint[]>({
    queryKey: ['pipeline-history', minutes],
    queryFn: async () => {
      const rows: Omit<HistoryPoint, 'ts'>[] = await pipelineApi.getHistory(minutes);
      return rows.map(r => ({
        ...r,
        ts: new Date(r.minute + ':00Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }));
    },
    refetchInterval: 15000,
  });
}
