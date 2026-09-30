export interface Connector {
  id: string;
  name: string;
  connector_type: string;
  description?: string;
  enabled: boolean;
  config: Record<string, unknown>;
  mapping_rules: Record<string, unknown>;
  ocsf_class_uid: number;
  events_processed: number;
  events_failed: number;
  last_event_at: string | null;
  created_at: string;
  updated_at: string;
  webhook_url: string;
  // Computed by the API from poll state and recent events
  health?: 'receiving' | 'waiting' | 'idle' | 'attention' | 'error' | 'disabled';
  health_detail?: string;
  poll_status?: string | null;
  poll_error?: string | null;
  last_polled_at?: string | null;
}

export interface ConnectorType {
  type_id: string;
  display_name: string;
  description: string;
  icon: string;
  category: string;
  auth_methods: string[];
  supports_webhook: boolean;
  supports_polling: boolean;
  supports_streaming: boolean;
  default_ocsf_class_uid: number;
  config_schema: ConfigSchema;
  default_mapping: Record<string, unknown>;
  // "beta": built from vendor API docs, not yet verified against a live tenant
  maturity?: 'stable' | 'beta';
  maturity_note?: string;
}

export interface ConfigSchema {
  properties: Record<string, ConfigField>;
  required?: string[];
}

export interface ConfigField {
  type: string;
  title: string;
  description?: string;
  placeholder?: string;
  default?: unknown;
  secret?: boolean;
  multiline?: boolean;
  enum?: string[];
  items?: { type: string; enum?: string[] };
}

export interface Forwarder {
  id: string;
  name: string;
  forwarder_type: string;
  description?: string;
  enabled: boolean;
  config: Record<string, unknown>;
  filter_rules: Record<string, unknown>;
  batch_size: number;
  flush_interval_ms: number;
  events_forwarded: number;
  events_failed: number;
  last_forwarded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ForwarderType {
  type_id: string;
  display_name: string;
  description: string;
  icon: string;
  category: string;
  config_schema: ConfigSchema;
  supports_batch: boolean;
  max_batch_size: number;
  maturity?: 'stable' | 'beta';
  maturity_note?: string;
}

export interface PipelineStats {
  events_received: number;
  events_mapped: number;
  events_failed: number;
  events_forwarded: number;
  throughput_per_second: number;
  last_event_at: number | null;
  started_at: number | null;
  total_connectors?: number;
  enabled_connectors?: number;
  total_forwarders?: number;
}

export interface SchemaVersion {
  version: string;
  updated_at: string | null;
  release_url?: string;
  release_notes?: string;
}

export interface OCSFClass {
  uid: number;
  name: string;
  caption: string;
  description: string;
  category_uid: number;
  category: string;
  deprecated?: boolean;
}

export interface OCSFCategory {
  uid: number;
  name: string;
  description: string;
}
