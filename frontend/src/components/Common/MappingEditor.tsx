import { useState } from 'react';
import { Plus, Trash2, GitBranch } from 'lucide-react';

interface MappingEditorProps {
  mapping: Record<string, unknown>;
  onChange: (mapping: Record<string, unknown>) => void;
  // Routes are top-level only; a route's own mapping is edited without a nested routes section
  allowRoutes?: boolean;
}

// A rule's source is either a path string ("$const:x" for constants) or { path, transform }
type RuleSource = string | { path: string; transform?: string };

interface Route {
  name?: string;
  when?: { field?: string; equals?: unknown; in?: unknown[] };
  class_uid?: number;
  mapping?: Record<string, unknown>;
}

const TRANSFORMS = ['', 'lower', 'upper', 'int', 'str', 'bool', 'epoch_ms'];

function sourcePath(src: unknown): string {
  if (src && typeof src === 'object' && 'path' in src) return String((src as { path: unknown }).path ?? '');
  return String(src ?? '');
}

function sourceTransform(src: unknown): string {
  if (src && typeof src === 'object' && 'transform' in src) return String((src as { transform: unknown }).transform ?? '');
  return '';
}

function makeSource(path: string, transform: string): RuleSource {
  return transform ? { path, transform } : path;
}

export default function MappingEditor({ mapping, onChange, allowRoutes = true }: MappingEditorProps) {
  const [newOcsfField, setNewOcsfField] = useState('');
  const [newSourcePath, setNewSourcePath] = useState('');

  // Keys starting with "_" (e.g. _routes) are structural; the flat list shows only real field rules
  const entries = Object.entries(mapping).filter(([k]) => !k.startsWith('_'));
  const routes: Route[] = Array.isArray(mapping._routes) ? (mapping._routes as Route[]) : [];

  const addRule = () => {
    if (!newOcsfField || !newSourcePath) return;
    onChange({ ...mapping, [newOcsfField]: newSourcePath });
    setNewOcsfField('');
    setNewSourcePath('');
  };

  const removeRule = (key: string) => {
    const next = { ...mapping };
    delete next[key];
    onChange(next);
  };

  const updateRule = (oldKey: string, newKey: string, value: RuleSource) => {
    const next: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(mapping)) {
      if (k === oldKey) {
        next[newKey || oldKey] = value;
      } else {
        next[k] = v;
      }
    }
    onChange(next);
  };

  const setRoutes = (next: Route[]) => {
    const copy = { ...mapping };
    if (next.length) copy._routes = next;
    else delete copy._routes;
    onChange(copy);
  };

  const updateRoute = (i: number, patch: Partial<Route>) => {
    setRoutes(routes.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 px-1">
        <span className="flex-1">OCSF Field Path</span>
        <span className="flex-1">Source Field Path / $const:value</span>
        <span className="w-24">Transform</span>
        <span className="w-8" />
      </div>

      {entries.map(([ocsf, src]) => (
        <div key={ocsf} className="flex items-center gap-2">
          <input
            className="input flex-1 font-mono text-xs"
            value={ocsf}
            onChange={e => updateRule(ocsf, e.target.value, src as RuleSource)}
            placeholder="actor.user.name"
          />
          <input
            className="input flex-1 font-mono text-xs"
            value={sourcePath(src)}
            onChange={e => updateRule(ocsf, ocsf, makeSource(e.target.value, sourceTransform(src)))}
            placeholder="actor.displayName or $const:value"
          />
          <select
            className="input w-24 text-xs"
            value={sourceTransform(src)}
            onChange={e => updateRule(ocsf, ocsf, makeSource(sourcePath(src), e.target.value))}
          >
            {TRANSFORMS.map(t => <option key={t} value={t}>{t || '—'}</option>)}
          </select>
          <button
            onClick={() => removeRule(ocsf)}
            className="btn-ghost p-1.5 text-red-500 hover:text-red-600"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}

      <div className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
        <input
          className="input flex-1 font-mono text-xs"
          value={newOcsfField}
          onChange={e => setNewOcsfField(e.target.value)}
          placeholder="time"
          onKeyDown={e => e.key === 'Enter' && addRule()}
        />
        <input
          className="input flex-1 font-mono text-xs"
          value={newSourcePath}
          onChange={e => setNewSourcePath(e.target.value)}
          placeholder="created_at"
          onKeyDown={e => e.key === 'Enter' && addRule()}
        />
        <span className="w-24" />
        <button onClick={addRule} className="btn-primary p-1.5" title="Add mapping rule">
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500">
        Use dot notation for nested paths (e.g. <code className="font-mono">actor.user.name</code>).
        Prefix with <code className="font-mono">$const:</code> for static values.
        {allowRoutes && routes.length > 0 ? ' These rules apply to events that match no route below.' : ''}
      </p>

      {allowRoutes && <div className="pt-3 border-t border-gray-200 dark:border-gray-800 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5">
            <GitBranch className="w-4 h-4" /> Routes by event type ({routes.length})
          </p>
          <button
            onClick={() => setRoutes([...routes, { name: 'new_route', when: { field: 'type', equals: '' }, class_uid: 3002, mapping: {} }])}
            className="btn-secondary text-xs"
          >
            <Plus className="w-3.5 h-3.5" /> Add route
          </button>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500">
          The first route whose condition matches an event decides its OCSF class and field mapping.
        </p>

        {routes.map((route, i) => {
          const values = route.when?.in ?? (route.when?.equals !== undefined ? [route.when.equals] : []);
          return (
            <details key={i} className="rounded-lg border border-gray-200 dark:border-gray-800">
              <summary className="cursor-pointer px-3 py-2 text-sm flex items-center gap-2">
                <span className="font-medium text-gray-900 dark:text-white">{route.name || `route ${i + 1}`}</span>
                <span className="text-xs text-gray-500 font-mono">
                  {route.when?.field} ∈ [{values.map(String).join(', ')}] → class {route.class_uid}
                </span>
                <span className="text-xs text-gray-400">({Object.keys(route.mapping || {}).length} rules)</span>
              </summary>
              <div className="px-3 pb-3 space-y-3">
                <div className="grid grid-cols-4 gap-2 items-end">
                  <div>
                    <label className="label text-xs">Name</label>
                    <input className="input text-xs" value={route.name ?? ''} onChange={e => updateRoute(i, { name: e.target.value })} />
                  </div>
                  <div>
                    <label className="label text-xs">When field</label>
                    <input
                      className="input font-mono text-xs"
                      value={route.when?.field ?? ''}
                      onChange={e => updateRoute(i, { when: { ...route.when, field: e.target.value } })}
                    />
                  </div>
                  <div>
                    <label className="label text-xs">Equals (comma = any of)</label>
                    <input
                      className="input font-mono text-xs"
                      value={values.map(String).join(', ')}
                      onChange={e => {
                        const vals = e.target.value.split(',').map(v => v.trim()).filter(Boolean);
                        updateRoute(i, { when: vals.length > 1 ? { field: route.when?.field, in: vals } : { field: route.when?.field, equals: vals[0] ?? '' } });
                      }}
                    />
                  </div>
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <label className="label text-xs">OCSF class_uid</label>
                      <input
                        type="number"
                        className="input text-xs"
                        value={route.class_uid ?? ''}
                        onChange={e => updateRoute(i, { class_uid: Number(e.target.value) })}
                      />
                    </div>
                    <button onClick={() => setRoutes(routes.filter((_, j) => j !== i))} className="btn-ghost p-1.5 text-red-500" title="Remove route">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <MappingEditor mapping={route.mapping || {}} onChange={m => updateRoute(i, { mapping: m })} allowRoutes={false} />
              </div>
            </details>
          );
        })}
      </div>}
    </div>
  );
}
