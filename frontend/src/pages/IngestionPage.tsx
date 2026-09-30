import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Database, ArrowDownToLine, ArrowUpFromLine, SearchX, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import clsx from 'clsx';
import { ingestionApi } from '../api/client';
import { useAuthStore } from '../store/auth';
import EmptyState from '../components/Common/EmptyState';
import { useThemeColors } from '../hooks/useThemeColors';

interface EntityStat {
  id: string;
  name: string;
  type: string | null;
  events_today: number;
  bytes_today: number;
  events_period: number;
  bytes_period: number;
  avg_event_bytes: number;
}

interface Summary {
  days: number;
  totals: Record<string, number>;
  connectors: EntityStat[];
  forwarders: EntityStat[];
  daily: { day: string; in_events: number; in_bytes: number; out_events: number; out_bytes: number }[];
}

interface UnmappedConnector {
  id: string;
  name: string;
  connector_type: string;
  mapping_rule_count: number;
  events_scanned: number;
  unmapped_field_count: number;
  unmapped_event_count: number;
}

interface UnmappedField {
  id: string;
  field_path: string;
  occurrences: number;
  coverage_pct: number | null;
  sample_values: unknown[];
  first_seen: string | null;
  last_seen: string | null;
}

interface UnmappedEvent {
  id: string;
  error_type: string;
  error_message: string;
  raw_event: unknown;
  created_at: string;
}

interface UnmappedResponse {
  connectors: UnmappedConnector[];
  fields: UnmappedField[];
  unmapped_events: UnmappedEvent[];
}

const TABS = ['Volume', 'Unmapped Samples'] as const;

export function formatBytes(n: number): string {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function IngestionPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Volume');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Ingestion</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          How much log data flows through the pipeline, and which parts of it aren't mapped to OCSF yet
        </p>
      </div>

      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'px-4 py-1.5 text-sm font-medium rounded-md transition-colors duration-150',
              tab === t
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Volume' ? <VolumeTab /> : <UnmappedTab />}
    </div>
  );
}

// ── Volume ───────────────────────────────────────────────────────────────────

function VolumeTab() {
  const [days, setDays] = useState(7);
  const colors = useThemeColors();
  const { data, isLoading } = useQuery<Summary>({
    queryKey: ['ingestion-summary', days],
    queryFn: () => ingestionApi.summary(days),
    refetchInterval: 15000,
  });

  if (isLoading || !data) {
    return <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />;
  }

  const t = data.totals;
  const chartData = data.daily.map(d => ({
    day: d.day.slice(5),
    Received: d.in_bytes,
    Forwarded: d.out_bytes,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Received = raw vendor logs as collected. Forwarded = OCSF events as delivered to destinations. Days are UTC.
        </p>
        <select className="input w-36" value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={1}>Today</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={ArrowDownToLine} label="Received today" bytes={t.in_bytes_today} events={t.in_events_today} />
        <StatTile icon={ArrowUpFromLine} label="Forwarded today" bytes={t.out_bytes_today} events={t.out_events_today} />
        <StatTile icon={ArrowDownToLine} label={`Received (${days}d)`} bytes={t.in_bytes_period} events={t.in_events_period} />
        <StatTile icon={ArrowUpFromLine} label={`Forwarded (${days}d)`} bytes={t.out_bytes_period} events={t.out_events_period} />
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Daily volume</h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.06} />
            <XAxis dataKey="day" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => formatBytes(Number(v))} width={70} />
            <Tooltip formatter={(v: number) => formatBytes(v)} contentStyle={{ ...colors.tooltip, borderRadius: '8px', fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Received" fill={colors.blue} radius={[3, 3, 0, 0]} />
            <Bar dataKey="Forwarded" fill={colors.green} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <EntityTable title="By connector (received)" rows={data.connectors} days={days} />
      <EntityTable title="By forwarder (delivered)" rows={data.forwarders} days={days} />
    </div>
  );
}

function StatTile({ icon: Icon, label, bytes, events }: {
  icon: typeof Database; label: string; bytes: number; events: number;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{formatBytes(bytes)}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400">{events.toLocaleString()} events</p>
    </div>
  );
}

function EntityTable({ title, rows, days }: { title: string; rows: EntityStat[]; days: number }) {
  return (
    <div className="card overflow-hidden">
      <h2 className="text-sm font-semibold text-gray-900 dark:text-white px-5 pt-4 pb-3">{title}</h2>
      {rows.length === 0 ? (
        <p className="px-5 pb-4 text-sm text-gray-500 dark:text-gray-400">Nothing yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500 dark:text-gray-400">
            <tr>
              <th className="text-left font-medium px-5 py-2">Name</th>
              <th className="text-left font-medium px-3 py-2">Type</th>
              <th className="text-right font-medium px-3 py-2">Today</th>
              <th className="text-right font-medium px-3 py-2">{days}d size</th>
              <th className="text-right font-medium px-3 py-2">{days}d events</th>
              <th className="text-right font-medium px-5 py-2">Avg event</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {rows.map(r => (
              <tr key={r.id} className="text-gray-700 dark:text-gray-300">
                <td className="px-5 py-2 font-medium text-gray-900 dark:text-white">{r.name}</td>
                <td className="px-3 py-2">{r.type ?? '—'}</td>
                <td className="px-3 py-2 text-right">{formatBytes(r.bytes_today)}</td>
                <td className="px-3 py-2 text-right">{formatBytes(r.bytes_period)}</td>
                <td className="px-3 py-2 text-right">{r.events_period.toLocaleString()}</td>
                <td className="px-5 py-2 text-right">{formatBytes(r.avg_event_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Unmapped samples ─────────────────────────────────────────────────────────

function UnmappedTab() {
  const qc = useQueryClient();
  const can = useAuthStore(s => s.can);
  const [connectorId, setConnectorId] = useState<string>('');
  const [openField, setOpenField] = useState<string | null>(null);
  const [openEvent, setOpenEvent] = useState<string | null>(null);

  const { data, isLoading } = useQuery<UnmappedResponse>({
    queryKey: ['ingestion-unmapped', connectorId],
    queryFn: () => ingestionApi.unmapped(connectorId || undefined),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (!connectorId && data?.connectors.length) setConnectorId(data.connectors[0].id);
  }, [data, connectorId]);

  const resetMutation = useMutation({
    mutationFn: () => ingestionApi.resetUnmapped(connectorId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ingestion-unmapped'] }),
  });

  if (isLoading || !data) {
    return <div className="card h-64 animate-pulse bg-gray-100 dark:bg-gray-800" />;
  }
  if (data.connectors.length === 0) {
    return <EmptyState icon={SearchX} title="No connectors yet" description="Unmapped samples appear once a connector is sending logs." />;
  }

  const current = data.connectors.find(c => c.id === connectorId);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="label">Connector</label>
          <select className="input w-72" value={connectorId} onChange={e => { setConnectorId(e.target.value); setOpenField(null); }}>
            {data.connectors.map(c => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.connector_type}) — {c.unmapped_field_count} fields, {c.unmapped_event_count} events
              </option>
            ))}
          </select>
        </div>
        {current && (
          <p className="text-xs text-gray-500 dark:text-gray-400 pb-2">
            {current.mapping_rule_count} mapping rules · {current.events_scanned.toLocaleString()} events sampled
          </p>
        )}
        {can('approve') && connectorId && (
          <button
            onClick={() => { if (confirm('Clear recorded unmapped fields for this connector?')) resetMutation.mutate(); }}
            className="btn-secondary ml-auto"
          >
            <RotateCcw className="w-4 h-4" /> Reset samples
          </button>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 pt-4 pb-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Unmapped fields</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Fields present in the raw logs that no mapping rule reads, so they don't reach the OCSF event. Fields drop off this list once a rule covers them.
          </p>
        </div>
        {data.fields.length === 0 ? (
          <p className="px-5 pb-4 text-sm text-gray-500 dark:text-gray-400">
            No unmapped fields recorded{current?.events_scanned ? ' — every field seen is mapped.' : ' yet. Samples appear as events are processed.'}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500 dark:text-gray-400">
              <tr>
                <th className="w-8" />
                <th className="text-left font-medium px-3 py-2">Field path</th>
                <th className="text-right font-medium px-3 py-2">Seen</th>
                <th className="text-right font-medium px-3 py-2">% of events</th>
                <th className="text-left font-medium px-5 py-2">Sample values</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {data.fields.map(f => (
                <FieldRow key={f.id} field={f} open={openField === f.id} onToggle={() => setOpenField(openField === f.id ? null : f.id)} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 pt-4 pb-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Unmapped events</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Whole events that couldn't be mapped (no mapping rules, or a mapping error). These are held in the DLQ and were not forwarded.
          </p>
        </div>
        {data.unmapped_events.length === 0 ? (
          <p className="px-5 pb-4 text-sm text-gray-500 dark:text-gray-400">None — every event from this connector was mapped.</p>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {data.unmapped_events.map(e => (
              <div key={e.id} className="px-5 py-2">
                <button className="flex items-center gap-2 w-full text-left text-sm" onClick={() => setOpenEvent(openEvent === e.id ? null : e.id)}>
                  {openEvent === e.id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400">{e.error_type}</span>
                  <span className="text-gray-700 dark:text-gray-300 truncate">{e.error_message}</span>
                  <span className="ml-auto text-xs text-gray-400 whitespace-nowrap">{new Date(e.created_at + 'Z').toLocaleString()}</span>
                </button>
                {openEvent === e.id && <JsonBlock value={e.raw_event} />}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FieldRow({ field, open, onToggle }: { field: UnmappedField; open: boolean; onToggle: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['unmapped-sample-event', field.id],
    queryFn: () => ingestionApi.sampleEvent(field.id),
    enabled: open,
  });

  return (
    <>
      <tr className="text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/40" onClick={onToggle}>
        <td className="pl-4">{open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</td>
        <td className="px-3 py-2 font-mono text-xs text-gray-900 dark:text-white">{field.field_path}</td>
        <td className="px-3 py-2 text-right">{field.occurrences.toLocaleString()}</td>
        <td className="px-3 py-2 text-right">{field.coverage_pct != null ? `${field.coverage_pct}%` : '—'}</td>
        <td className="px-5 py-2">
          <div className="flex flex-wrap gap-1">
            {field.sample_values.map((v, i) => (
              <span key={i} className="font-mono text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 max-w-[16rem] truncate" title={String(v)}>
                {String(v)}
              </span>
            ))}
          </div>
        </td>
      </tr>
      {open && (
        <tr>
          <td />
          <td colSpan={4} className="px-3 pb-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Sample raw event containing <code>{field.field_path}</code>:</p>
            {isLoading ? <p className="text-xs text-gray-400">Loading…</p> : <JsonBlock value={data?.sample_event ?? null} />}
          </td>
        </tr>
      )}
    </>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-gray-50 dark:bg-gray-900 p-3 text-xs font-mono text-gray-800 dark:text-gray-200">
      {value == null ? 'No sample stored (event too large).' : JSON.stringify(value, null, 2)}
    </pre>
  );
}
