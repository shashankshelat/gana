import { ConfigSchema } from '../../types';
import clsx from 'clsx';

interface ConfigFormProps {
  schema: ConfigSchema;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
}

export default function ConfigForm({ schema, values, onChange }: ConfigFormProps) {
  const { properties = {}, required = [] } = schema;

  return (
    <div className="space-y-4">
      {Object.entries(properties).map(([key, field]) => {
        const value = (values[key] ?? field.default ?? '') as string;
        const isRequired = required.includes(key);

        return (
          <div key={key}>
            <label className="label">
              {field.title}
              {isRequired && <span className="text-red-500 ml-1">*</span>}
            </label>

            {field.type === 'boolean' ? (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(values[key] ?? field.default)}
                  onChange={e => onChange(key, e.target.checked)}
                  className="w-4 h-4 text-brand-600 rounded border-gray-300 focus:ring-brand-500"
                />
                <span className="text-sm text-gray-600 dark:text-gray-400">{field.description}</span>
              </label>
            ) : field.enum ? (
              <select
                value={String(value)}
                onChange={e => onChange(key, e.target.value)}
                className="input"
              >
                {field.enum.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : field.type === 'array' ? (
              <div>
                {field.items?.enum ? (
                  <div className="flex flex-wrap gap-2">
                    {field.items.enum.map(opt => {
                      const arr = (values[key] as string[]) || (field.default as string[]) || [];
                      const checked = arr.includes(opt);
                      return (
                        <label key={opt} className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={e => {
                              const arr2 = [...((values[key] as string[]) || (field.default as string[]) || [])];
                              if (e.target.checked) {
                                onChange(key, [...arr2, opt]);
                              } else {
                                onChange(key, arr2.filter(x => x !== opt));
                              }
                            }}
                            className="w-3.5 h-3.5 text-brand-600 rounded border-gray-300 focus:ring-brand-500"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">{opt}</span>
                        </label>
                      );
                    })}
                  </div>
                ) : (
                  <input
                    type="text"
                    value={Array.isArray(values[key]) ? (values[key] as string[]).join(', ') : String(value)}
                    placeholder="Comma separated values"
                    onChange={e => onChange(key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    className="input"
                  />
                )}
              </div>
            ) : field.multiline ? (
              <textarea
                value={String(value)}
                onChange={e => onChange(key, e.target.value)}
                placeholder={field.placeholder}
                rows={4}
                className="input font-mono text-xs"
              />
            ) : (
              <input
                type={field.secret ? 'password' : field.type === 'integer' ? 'number' : 'text'}
                value={String(value)}
                onChange={e => onChange(key, field.type === 'integer' ? Number(e.target.value) : e.target.value)}
                placeholder={field.placeholder ?? (field.secret ? '••••••••' : '')}
                className="input"
                autoComplete={field.secret ? 'new-password' : undefined}
              />
            )}

            {field.description && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{field.description}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
