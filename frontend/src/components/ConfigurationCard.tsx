import { VERSIONS } from '../config';

interface ConfigurationCardProps {
  version: string;
  onVersionChange: (id: string) => void;
}

export default function ConfigurationCard({ version, onVersionChange }: ConfigurationCardProps) {
  const latestVersion = VERSIONS[VERSIONS.length - 1];

  return (
    <div className="configuration-card glass-card">
      <label className="configuration-label" htmlFor="simplify-version">
        Version
      </label>
      <select
        id="simplify-version"
        className="configuration-select"
        value={version}
        onChange={event => onVersionChange(event.target.value)}
      >
        {VERSIONS.map(option => {
          const notes = [
            option.id === latestVersion.id ? 'latest' : '',
            option.isDefault ? 'default' : '',
          ].filter(Boolean);
          return (
            <option key={option.id} value={option.id}>
              {option.label}{notes.length > 0 ? ` (${notes.join(', ')})` : ''}
            </option>
          );
        })}
      </select>
    </div>
  );
}
