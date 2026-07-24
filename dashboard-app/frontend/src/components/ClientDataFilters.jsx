import { isoDateMonthsFromToday } from "../sortUtils";

const DURATION_PRESETS = [
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "1 year", months: 12 },
];

export default function ClientDataFilters({
  certOptions, certType, onCertTypeChange,
  schemeOptions = [], scheme = "ALL", onSchemeChange = () => {},
  expiryBefore, onExpiryBeforeChange, onClearAll,
}) {
  const hasFilters = certType !== "ALL" || scheme !== "ALL" || expiryBefore !== "";

  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-wrap gap-4 items-center">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
        Filter by
      </span>
      <select
        value={scheme}
        onChange={(e) => onSchemeChange(e.target.value)}
        aria-label="Filter by scheme"
        className="min-w-[150px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Schemes</option>
        {schemeOptions.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <select
        value={certType}
        onChange={(e) => onCertTypeChange(e.target.value)}
        aria-label="Filter by certification type"
        className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Cert Types</option>
        {certOptions.map((cert) => (
          <option key={cert} value={cert}>{cert}</option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        Expiry before
        <input
          type="date"
          value={expiryBefore}
          onChange={(e) => onExpiryBeforeChange(e.target.value)}
          aria-label="Filter by expiry before date"
          className="bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </label>
      <div className="flex items-center gap-1.5">
        {DURATION_PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => onExpiryBeforeChange(isoDateMonthsFromToday(preset.months))}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
          >
            {preset.label}
          </button>
        ))}
      </div>
      {hasFilters && (
        <button
          type="button"
          onClick={onClearAll}
          className="ml-auto text-sm font-semibold text-accent hover:underline"
        >
          Clear All
        </button>
      )}
    </div>
  );
}
