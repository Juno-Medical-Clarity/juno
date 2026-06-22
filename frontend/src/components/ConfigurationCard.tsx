interface ConfigurationCardProps {
  gradingEnabled: boolean;
  onGradingEnabledChange: (enabled: boolean) => void;
}

export default function ConfigurationCard({ gradingEnabled, onGradingEnabledChange }: ConfigurationCardProps) {
  return (
    <div className="configuration-card glass-card">
      <label className="configuration-label" style={{ marginTop: '0' }}>
        <input
          type="checkbox"
          checked={gradingEnabled}
          onChange={e => onGradingEnabledChange(e.target.checked)}
          style={{ marginRight: '8px' }}
        />
        Enable grading
      </label>
    </div>
  );
}
