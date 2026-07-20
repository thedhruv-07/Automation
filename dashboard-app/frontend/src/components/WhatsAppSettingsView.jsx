import { useEffect, useState } from "react";

export default function WhatsAppSettingsView({ fetchInfo }) {
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    fetchInfo()
      .then((data) => {
        setInfo(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message));
  }, [fetchInfo]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-ink-primary">WhatsApp Settings</h2>
        <p className="text-ink-secondary text-sm mt-1">
          Read-only view of the current automation configuration.
        </p>
      </div>

      {loadError && (
        <div
          className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2"
          data-testid="settings-info-error"
        >
          Could not load settings info: {loadError}.
        </div>
      )}

      {info && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-surface border border-line rounded-xl p-6 space-y-3">
            <h3 className="font-semibold text-ink-primary">Message Template</h3>
            <dl className="text-sm space-y-2">
              <div className="flex justify-between">
                <dt className="text-ink-secondary">Template name</dt>
                <dd className="text-ink-primary font-medium">{info.template_name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-secondary">Language</dt>
                <dd className="text-ink-primary font-medium">{info.template_lang}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-secondary">Phone number ID</dt>
                <dd className="text-ink-primary font-medium">{info.phone_number_id}</dd>
              </div>
            </dl>
            <p className="text-xs text-ink-muted pt-2 border-t border-line">
              The template body can only be edited in Meta Business Manager, and changes require re-approval before they take effect.
            </p>
          </div>

          <div className="bg-surface border border-line rounded-xl p-6 space-y-3">
            <h3 className="font-semibold text-ink-primary">Alert Thresholds</h3>
            <dl className="text-sm space-y-2">
              <div className="flex items-center justify-between">
                <dt className="flex items-center gap-2 text-ink-secondary">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-critical" aria-hidden="true" />
                  Critical
                </dt>
                <dd className="text-ink-primary font-medium">≤ {info.critical_days} days</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="flex items-center gap-2 text-ink-secondary">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-serious" aria-hidden="true" />
                  Urgent
                </dt>
                <dd className="text-ink-primary font-medium">≤ {info.urgent_days} days</dd>
              </div>
            </dl>
            <p className="text-xs text-ink-muted pt-2 border-t border-line">
              These cutoffs are hardcoded in cert_automation.py and aren't editable from this dashboard.
            </p>
          </div>

          <div className="bg-surface border border-line rounded-xl p-6 space-y-3">
            <h3 className="font-semibold text-ink-primary">Schedule</h3>
            <dl className="text-sm space-y-2">
              <div className="flex justify-between">
                <dt className="text-ink-secondary">Daily run time</dt>
                <dd className="text-ink-primary font-medium">{info.scheduled_run_time}</dd>
              </div>
            </dl>
            <p className="text-xs text-ink-muted pt-2 border-t border-line">
              Configured in Windows Task Scheduler, not editable from this dashboard.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
