import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { Analysis, ColourCalibration } from '../types'

const GRADE_VAR: Record<string, string> = {
  no_flag: 'var(--grade-no_flag)',
  monitor: 'var(--grade-monitor)',
  review: 'var(--grade-review)',
  urgent: 'var(--grade-urgent)',
}

export function TriageCard({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const { triage } = analysis
  return (
    <div
      className="triage-card"
      style={{ background: triage.color ?? GRADE_VAR[triage.grade] }}
      role="status"
    >
      <div className="grade">{triage.grade.replace('_', ' ')}</div>
      <div className="label">{triage.label}</div>
      <div className="meta">
        {t('result.confidence')}: {(triage.confidence * 100).toFixed(0)}%
        {' · '}
        {t('result.quality')}: {analysis.quality.passed
          ? t('quality.passed') : t('quality.degraded')}
        {' · '}
        {t('result.model')}: {analysis.model_version}
      </div>
      <div className="confidence-bar" aria-hidden="true">
        <span style={{ width: `${Math.round(triage.confidence * 100)}%` }} />
      </div>
    </div>
  )
}

export function NextStep({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const { triage } = analysis
  return (
    <section className="next-step">
      <h2>{t('result.nextStep')}</h2>
      <div className="kv">
        <div><strong>{t('result.timeframe')}</strong>{triage.urgency}</div>
        <div><strong>{t('result.routeTo')}</strong>{triage.routing_target}</div>
      </div>
      <p>{triage.next_investigation}</p>
    </section>
  )
}

export function QualityReadout({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  return (
    <section className="card">
      <h2>{t('result.quality')}</h2>
      {analysis.quality.checks.map((check) => (
        <div className="quality-row" key={check.name}>
          <span className={`dot ${check.passed ? 'ok' : 'bad'}`} aria-hidden="true" />
          <span>{t(`quality.check.${check.name}`)}</span>
          <span className="nums">
            {check.value.toFixed(1)} / {check.threshold.toFixed(1)}
          </span>
        </div>
      ))}
      {!analysis.quality.passed && (
        <ul className="plain" style={{ marginTop: '.5rem' }}>
          {analysis.quality.hints.map((hint) => <li key={hint}>{hint}</li>)}
        </ul>
      )}
    </section>
  )
}

export function LesionList({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  if (analysis.lesions.length === 0) {
    return (
      <section className="card">
        <h2>{t('result.findings')}</h2>
        <p className="hint">{t('result.noFindings')}</p>
      </section>
    )
  }
  return (
    <section className="card">
      <h2>{t('result.findings')}</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('result.findings')}</th>
              <th>{t('result.area')}</th>
              <th>{t('result.severity')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {analysis.lesions.map((lesion) => (
              <tr key={lesion.id}>
                <td>{lesion.kind.replace(/_/g, ' ')}</td>
                <td>{lesion.area_pct.toFixed(1)}%</td>
                <td>{lesion.severity.toFixed(2)}</td>
                <td className="hint">{lesion.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ClinicalPanel({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const clinical = analysis.clinical
  if (!clinical) return null
  const index = clinical.severity_index

  return (
    <section className="card">
      <h2>{t('clinical.title')}</h2>
      <p className="hint">{clinical.status}</p>

      {index && (
        <div className="severity">
          <div className="severity-value">
            {index.value}<span>{index.unit.startsWith('%') ? '%' : ''}</span>
          </div>
          <div>
            <strong>{index.name} — {index.band}</strong>
            <p className="hint">{index.unit}</p>
            <p className="hint">{index.caveat}</p>
          </div>
        </div>
      )}

      <h3>{t('clinical.considerations')}</h3>
      {clinical.considerations.map((item) => (
        <div className="consideration" key={item.pattern}>
          <p><strong>{item.pattern}</strong></p>
          <p className="hint">{t('clinical.overlapsWith')}</p>
          <ul className="plain">
            {item.overlaps_with.map((option) => <li key={option}>{option}</li>)}
          </ul>
          <p className="discriminator">
            <strong>{t('clinical.distinguishedBy')}: </strong>
            {item.distinguished_by}
          </p>
        </div>
      ))}

      {clinical.immediate_actions.length > 0 && (
        <>
          <h3>{t('clinical.immediateActions')}</h3>
          <p className="hint">{t('clinical.immediateActionsNote')}</p>
          <ul className="plain">
            {clinical.immediate_actions.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </>
      )}

      {clinical.ask_and_check.length > 0 && (
        <>
          <h3>{t('clinical.askAndCheck')}</h3>
          <p className="hint">{t('clinical.askAndCheckNote')}</p>
          <ul className="plain">
            {clinical.ask_and_check.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </>
      )}

      {clinical.not_assessable.length > 0 && (
        <>
          <h3>{t('clinical.notAssessable')}</h3>
          <div className="limitations">
            <ul className="plain">
              {clinical.not_assessable.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </div>
        </>
      )}

      {Object.entries(clinical.scales).map(([name, body]) => (
        <details key={name} className="scale-block">
          <summary>{name}</summary>
          <pre className="summary">{JSON.stringify(body, null, 2)}</pre>
        </details>
      ))}
    </section>
  )
}

/**
 * Whether the colours this grade rests on were corrected against a reference
 * card. Shown always, including when no card was present — "not calibrated" is
 * the information a clinician needs before comparing today's percentages with
 * last week's.
 */
export function ColourReference({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const cal = analysis.features?.colour_calibration as ColourCalibration | undefined
  if (!cal) return null

  const state = cal.applied ? 'ok' : cal.detected ? 'warn' : 'off'
  const heading = cal.applied
    ? t('calib.applied')
    : cal.detected ? t('calib.unusable') : t('calib.notDetected')

  return (
    <section className="card">
      <h2>{t('calib.title')}</h2>
      <div className="quality-row">
        <span className={`dot ${state === 'ok' ? 'ok' : 'bad'}`} aria-hidden="true" />
        <span><strong>{heading}</strong></span>
        {cal.applied && cal.illuminant_shift_pct !== undefined && (
          <span className="nums">
            {t('calib.shift')}: {cal.illuminant_shift_pct.toFixed(0)}%
          </span>
        )}
      </div>
      <p className="hint">{cal.note}</p>
      {cal.reason && <p className="caveat">{cal.reason}</p>}
      <p className="hint">{t('calib.why')}</p>
      <details className="scale-block">
        <summary>{t('calib.howTo')}</summary>
        <p className="hint">{cal.how_to}</p>
      </details>
    </section>
  )
}

export function Limitations({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const { safety } = analysis
  return (
    <section className="card">
      <h2>{t('result.limitations')}</h2>
      <div className="limitations">
        <ul className="plain">
          {(safety.module_limitations ?? []).map((line) => <li key={line}>{line}</li>)}
        </ul>
      </div>
      {safety.no_flag_caveat && (
        <div className="caveat" role="alert">{safety.no_flag_caveat}</div>
      )}
      <p className="hint" style={{ marginTop: '.7rem' }}>
        <strong>{safety.device_notice}</strong> {safety.disclaimer}{' '}
        {safety.human_in_the_loop} {safety.no_treatment}
      </p>
    </section>
  )
}

export function OverlayImage({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const [url, setUrl] = useState<string | null>(
    analysis.overlay_png_base64
      ? `data:image/png;base64,${analysis.overlay_png_base64}`
      : null,
  )

  useEffect(() => {
    if (analysis.overlay_png_base64) return
    let objectUrl: string | null = null
    let cancelled = false
    api.overlayUrl(analysis.case_id, analysis.id)
      .then((next) => {
        if (cancelled) { URL.revokeObjectURL(next); return }
        objectUrl = next
        setUrl(next)
      })
      .catch(() => setUrl(null))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [analysis.case_id, analysis.id, analysis.overlay_png_base64])

  if (!url) return null
  return (
    <section className="card">
      <h2>{t('result.overlay')}</h2>
      <img className="overlay-img" src={url} alt={t('result.overlay')} />
    </section>
  )
}

export function ResultView({ analysis, caseId }: { analysis: Analysis; caseId: string }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)

  async function downloadPdf() {
    setBusy(true)
    try {
      const blob = await api.summaryPdf(caseId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `qadam-${analysis.module}-${caseId}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <TriageCard analysis={analysis} />
      <NextStep analysis={analysis} />
      <OverlayImage analysis={analysis} />
      <LesionList analysis={analysis} />

      <section className="card">
        <h2>{t('result.rationale')}</h2>
        <ul className="plain">
          {analysis.triage.rationale.map((line) => <li key={line}>{line}</li>)}
        </ul>
      </section>

      <ClinicalPanel analysis={analysis} />
      <QualityReadout analysis={analysis} />
      <ColourReference analysis={analysis} />
      <Limitations analysis={analysis} />

      <section className="card">
        <h2>{t('result.summary')}</h2>
        <pre className="summary">{analysis.summary}</pre>
        <div className="actions">
          <button onClick={downloadPdf} disabled={busy}>{t('result.pdf')}</button>
        </div>
      </section>
    </div>
  )
}
