import { ClinicalPanel } from './ResultView'
import { useI18n } from '../i18n'
import type { Analysis, LabPanel } from '../types'

function formatRange(low: number | null, high: number | null): string {
  if (low === null && high === null) return '—'
  if (low === null) return `< ${high}`
  if (high === null) return `> ${low}`
  return `${low} – ${high}`
}

export function LabPanelView({ panel }: { panel: LabPanel }) {
  const { t } = useI18n()

  return (
    <div>
      <div className="triage-card" style={{ background: panel.triage.color }}
           role="status">
        <div className="grade">{panel.triage.grade.replace('_', ' ')}</div>
        <div className="label">{panel.triage.label}</div>
        <div className="meta">
          {panel.panel_name ? `${panel.panel_name} · ` : ''}
          {panel.results.length} {t('lab.analytes')}
          {' · '}
          {panel.results.filter((r) => r.flag !== 'normal').length} {t('lab.flagged')}
          {panel.created_at
            ? ` · ${new Date(panel.created_at).toLocaleString()}` : ''}
        </div>
      </div>

      <section className="next-step">
        <h2>{t('result.nextStep')}</h2>
        <div className="kv">
          <div><strong>{t('result.timeframe')}</strong>{panel.triage.urgency}</div>
          <div><strong>{t('result.routeTo')}</strong>{panel.triage.routing_target}</div>
        </div>
        <p>{panel.triage.next_investigation}</p>
      </section>

      <section className="card">
        <h2>{t('lab.results')}</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('lab.analyte')}</th>
                <th>{t('lab.value')}</th>
                <th>{t('lab.reference')}</th>
                <th>{t('lab.flag')}</th>
                <th>{t('lab.asEntered')}</th>
              </tr>
            </thead>
            <tbody>
              {panel.results.map((r) => (
                <tr key={r.code} className={r.critical ? 'lab-critical' : ''}>
                  <td>{r.name}</td>
                  <td className="lab-value">{r.value} {r.unit}</td>
                  <td className="hint">
                    {formatRange(r.reference.low, r.reference.high)}
                  </td>
                  <td>
                    {r.critical ? (
                      <span className="pill" style={{ background: 'var(--grade-urgent)' }}>
                        {t('lab.critical')}
                      </span>
                    ) : r.flag === 'normal' ? (
                      <span className="hint">{t('lab.notFlagged')}</span>
                    ) : (
                      <span className="pill"
                            style={{ background: 'var(--grade-review)' }}>
                        {r.flag}
                      </span>
                    )}
                  </td>
                  <td className="hint">
                    {r.converted
                      ? `${r.submitted.value} ${r.submitted.unit}`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {panel.unrecognised.length > 0 && (
          <p className="hint">
            {t('lab.unrecognised')}: {panel.unrecognised.map((u) => u.code).join(', ')}
          </p>
        )}
      </section>

      {panel.derived.length > 0 && (
        <section className="card">
          <h2>{t('lab.derived')}</h2>
          {panel.derived.map((d) => (
            <div className="consideration" key={d.code}>
              <p>
                <strong>{d.name}: {d.value} {d.unit}</strong> — {d.interpretation}
              </p>
              <p className="hint">{d.caveat}</p>
            </div>
          ))}
        </section>
      )}

      <section className="card">
        <h2>{t('result.rationale')}</h2>
        <ul className="plain">
          {panel.triage.rationale.map((line) => <li key={line}>{line}</li>)}
        </ul>
      </section>

      {panel.clinical && (
        <ClinicalPanel
          analysis={{ clinical: panel.clinical } as unknown as Analysis}
        />
      )}
    </div>
  )
}
