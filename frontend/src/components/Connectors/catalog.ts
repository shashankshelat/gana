import {
  Users, Cloud, Monitor, Globe, Briefcase, ShieldCheck, Mail, Siren, Webhook, LucideIcon,
} from 'lucide-react';
import { ConnectorType, Connector } from '../../types';

export interface CatalogCategory {
  id: string;
  label: string;
  icon: LucideIcon;
}

// Order is the catalog's sidebar order; unknown backend categories fall into "Other"
export const CATEGORIES: CatalogCategory[] = [
  { id: 'identity', label: 'Identity & Access', icon: Users },
  { id: 'cloud', label: 'Cloud Platforms', icon: Cloud },
  { id: 'endpoint', label: 'Endpoint & XDR', icon: Monitor },
  { id: 'network', label: 'Network & Edge', icon: Globe },
  { id: 'saas', label: 'SaaS & Collaboration', icon: Briefcase },
  { id: 'cloud_security', label: 'Cloud Security', icon: ShieldCheck },
  { id: 'email_security', label: 'Email Security', icon: Mail },
  { id: 'alerts', label: 'SIEM & Alert Platforms', icon: Siren },
  { id: 'custom', label: 'Custom Sources', icon: Webhook },
];

export const POPULAR = ['okta', 'microsoft_365', 'aws_cloudtrail', 'crowdstrike', 'google_workspace', 'github', 'slack', 'generic_webhook'];

export function categoryOf(id: string): CatalogCategory {
  return CATEGORIES.find(c => c.id === id) ?? { id, label: id.replace(/_/g, ' '), icon: Webhook };
}

export function ingestionModes(t: Pick<ConnectorType, 'supports_polling' | 'supports_webhook'>): string[] {
  return [t.supports_polling && 'Pull', t.supports_webhook && 'Push'].filter(Boolean) as string[];
}

export function matchesSearch(t: ConnectorType, q: string): boolean {
  if (!q) return true;
  const hay = `${t.display_name} ${t.type_id} ${t.description} ${categoryOf(t.category).label}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).every(term => hay.includes(term));
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  // Backend timestamps are naive UTC
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime();
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export type Health = NonNullable<Connector['health']>;

export const HEALTH: Record<Health, { label: string; dot: string; pill: string }> = {
  receiving: { label: 'Receiving', dot: 'bg-green-500', pill: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400' },
  waiting: { label: 'Waiting', dot: 'bg-blue-400', pill: 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300' },
  idle: { label: 'Idle', dot: 'bg-gray-400', pill: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300' },
  attention: { label: 'Needs setup', dot: 'bg-amber-500', pill: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' },
  error: { label: 'Error', dot: 'bg-red-500', pill: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400' },
  disabled: { label: 'Disabled', dot: 'bg-gray-300', pill: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400' },
};

export function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
  return err instanceof Error ? err.message : String(err);
}
