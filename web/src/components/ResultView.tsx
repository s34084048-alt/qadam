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

/**
 * What the PHOTOGRAPH showed. Deliberately no longer styled or worded as a
 * verdict: the case's decision is RoutingCard, and this is one piece of
 * evidence under it. The grade is kept because it is what the image
 * measurement produced and a reader should be able to see it — but it is
 * labelled as an observation, and it routes nothing.
 */
export function TriageCard({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const { triage } = analysis
  return (
    <div
      className="triage-card observation"
      style={{ background: triage.color ?? GRADE_VAR[triage.grade] }}
      role="status"
    >
      <div className="observed-tag">{t('result.observationOnly')}</div>
      <div className="grade">{triage.grade.replace('_', ' ')}</div>
      <div className="label">{triage.label}</div>
      <div className="meta">
        {/* NO CONFIDENCE FIGURE ON A NO-FLAG. The number is a
            distance-from-threshold measure, and on a clean foot it always sits
            at its ceiling — so the result where over-confidence is most
            dangerous displayed the highest number the system can express, and
            "85%" reads as "85% sure this foot is fine". A photograph cannot
            support that: it does not see perfusion, sensation or depth. What
            replaces it is the sentence that is actually true. */}
        {triage.grade !== 'no_flag' && (
          <>
            {t('result.distance')}: {(triage.confidence * 100).toFixed(0)}%
            {' · '}
          </>
        )}
        {t('result.quality')}: {analysis.quality.passed
          ? t('quality.passed') : t('quality.degraded')}
        {' · '}
        {t('result.model')}: {analysis.model_version}
      </div>
      {triage.grade !== 'no_flag' && (
        <details className="meta evidence-strength-hint">
          <summary>{t('result.aboutScore')}</summary>
          {t('result.evidenceStrengthHint')}
        </details>
      )}
      {triage.grade === 'no_flag' && (
        <div className="meta no-flag-meaning">{t('result.noFlagMeaning')}</div>
      )}
      {triage.grade !== 'no_flag' && (
        <div className="confidence-bar" aria-hidden="true">
          <span style={{ width: `${Math.round(triage.confidence * 100)}%` }} />
        </div>
      )}
    </div>
  )
}

type EvidenceFinding = {
  kind: string
  observed: string
  ceiling: string
  sufficient_for_urgent: boolean
  limits: string[]
  measurements: { area_pct?: number }
}

type EvidenceReport = {
  appearance: string
  appearance_meaning: string
  ceiling: string
  ceiling_meaning: string
  findings: EvidenceFinding[]
  notes: string[]
  cannot_be_determined_from_a_photograph: string[]
  parameter_status: string
}

/**
 * Observation, limit, and meaning — kept apart on the page because they are
 * apart in the code.
 *
 * The failure this answers: a healthy foot was shown "URGENT" beside a large
 * confidence figure, and nothing on screen distinguished "these pixels are
 * darker than those pixels" from "this tissue is dying". A reader had no way
 * to see that the first was all the system ever had.
 *
 * So each finding states what was OBSERVED in the image in terms of pixels,
 * and — when the grade was lowered — why the evidence did not carry further.
 * Nothing here is phrased as a diagnosis; test_evidence_gate.py asserts that
 * the disease vocabulary never appears in these strings.
 */
export function EvidencePanel({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const report = analysis.features?.evidence as EvidenceReport | undefined
  if (!report) return null
  const capped = Boolean(analysis.features?.grade_capped_by_evidence)
  // Only findings that were actually measured. Filtered on the NUMBER, not on
  // the wording of `observed` — prose changes, and a filter that reads English
  // would silently show every empty finding the first time a string is
  // reworded or translated.
  const live = report.findings.filter((f) => (f.measurements?.area_pct ?? 0) > 0)

  return (
    <section className="card evidence">
      <h2>{t('evidence.title')}</h2>

      <div className={`appearance ${report.appearance}`}>
        <strong>
          {t(`evidence.appearance.${report.appearance}`)}
        </strong>
        <p className="hint">{report.appearance_meaning}</p>
      </div>

      {capped && <div className="caveat" role="alert">{t('evidence.capped')}</div>}

      <h3>{t('evidence.observed')}</h3>
      <p className="hint">{t('evidence.observedHint')}</p>
      {live.length === 0 && <p className="hint">—</p>}
      <ul className="plain">
        {live.map((f) => <li key={f.kind}>{f.observed}</li>)}
      </ul>

      {live.some((f) => f.limits.length > 0) && (
        <>
          <h3>{t('evidence.limits')}</h3>
          <ul className="plain">
            {live.flatMap((f) => f.limits).map((line) => <li key={line}>{line}</li>)}
          </ul>
        </>
      )}

      <h3>{t('evidence.cannot')}</h3>
      <p className="hint">{t('evidence.cannotHint')}</p>
      <div className="limitations">
        <ul className="plain">
          {report.cannot_be_determined_from_a_photograph.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      <h3>{t('evidence.means')}</h3>
      <p className="hint">
        <strong>{t('evidence.ceiling')}: </strong>
        {report.ceiling.replace('_', ' ')} — {report.ceiling_meaning}
      </p>
      {report.notes.map((line) => <p className="hint" key={line}>{line}</p>)}
      <p className="caveat">{report.parameter_status}</p>
    </section>
  )
}

/** Removed from the result view: the routing decision is RoutingCard, built
 *  from the examination and the answers. Two "next steps" on one page, one of
 *  them derived from pixels, is how a reader ends up acting on the wrong one. */
export function NextStep({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  return (
    <section className="card">
      <h2>{t('result.imageOnly')}</h2>
      <p className="hint">{t('result.imageOnlyHint')}</p>
      <p className="hint">{analysis.triage.next_investigation}</p>
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
            {(() => {
              // The same long description repeated on every row of a kind is
              // noise. Show it once — on the first row of each kind — and leave
              // the rest of that kind's rows to the numbers.
              const describedKinds = new Set<string>()
              return analysis.lesions.map((lesion) => {
                const firstOfKind = !describedKinds.has(lesion.kind)
                describedKinds.add(lesion.kind)
                return (
                  <tr key={lesion.id}>
                    <td>{lesion.kind.replace(/_/g, ' ')}</td>
                    <td>{lesion.area_pct.toFixed(1)}%</td>
                    <td>{lesion.severity.toFixed(2)}</td>
                    <td className="hint">{firstOfKind ? lesion.description : ''}</td>
                  </tr>
                )
              })
            })()}
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

      {/* Protective steps stay visible: they are the one thing here a reader
          should act on now, while the referral is arranged. */}
      {clinical.immediate_actions.length > 0 && (
        <>
          <h3>{t('clinical.immediateActions')}</h3>
          <p className="hint">{t('clinical.immediateActionsNote')}</p>
          <ul className="plain">
            {clinical.immediate_actions.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </>
      )}

      {/* The long reference material — differentials, what to ask and examine —
          is collapsed by default. Nothing is removed; it is one tap away. The
          "not assessable" list is dropped here because the evidence panel above
          already carries the authoritative "not determinable from a photograph"
          block, and repeating it three times on one page buries it. */}
      {clinical.considerations.length > 0 || clinical.ask_and_check.length > 0 ? (
        <details className="clinical-detail">
          <summary>{t('clinical.moreDetail')}</summary>
          {clinical.considerations.length > 0 && (
            <>
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
        </details>
      ) : null}

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

/**
 * The one or two questions that would change this answer.
 *
 * Placed high on purpose: on a photograph the most valuable thing the platform
 * can offer is usually not its own measurement but the ten-second experiment
 * that tests whether the measurement means anything.
 */
export function ClarifyingQuestions({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const questions = analysis.features?.clarifying_questions as
    { ask: string; settles: string; because: string }[] | undefined
  if (!questions || questions.length === 0) return null

  return (
    <section className="card clarify">
      <h2>{t('clarify.title')}</h2>
      <p className="hint">{t('clarify.intro')}</p>
      {questions.map((q) => (
        <div className="consideration" key={q.ask}>
          <p><strong>{q.ask}</strong></p>
          <p className="discriminator">
            <strong>{t('clarify.settles')}: </strong>{q.settles}
          </p>
          {q.because && <p className="hint">{q.because}</p>}
        </div>
      ))}
    </section>
  )
}

export function Limitations({ analysis }: { analysis: Analysis }) {
  const { t } = useI18n()
  const { safety } = analysis
  return (
    <section className="card">
      <h2>{t('result.limitations')}</h2>
      {/* The device notice, disclaimer and human-in-the-loop line stay visible
          — they are the required safety statement and are never collapsed. */}
      {safety.no_flag_caveat && (
        <div className="caveat" role="alert">{safety.no_flag_caveat}</div>
      )}
      <p className="hint">
        <strong>{safety.device_notice}</strong> {safety.disclaimer}{' '}
        {safety.human_in_the_loop} {safety.no_treatment}
      </p>
      {/* The detailed per-item list repeats the evidence panel's "not
          determinable" block, so it is collapsed rather than shown a third
          time. Kept, not removed. */}
      {(safety.module_limitations ?? []).length > 0 && (
        <details className="limitations" style={{ marginTop: '.7rem' }}>
          <summary>{t('result.moreLimits')}</summary>
          <ul className="plain">
            {(safety.module_limitations ?? []).map((line) => <li key={line}>{line}</li>)}
          </ul>
        </details>
      )}
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
      {/* Directly under the grade: what the grade is made of, and what it is
          not. Placing it lower would let the coloured card be read alone. */}
      <EvidencePanel analysis={analysis} />
      <NextStep analysis={analysis} />
      <OverlayImage analysis={analysis} />
      <LesionList analysis={analysis} />

      <section className="card">
        <h2>{t('result.rationale')}</h2>
        <ul className="plain">
          {analysis.triage.rationale.map((line) => <li key={line}>{line}</li>)}
        </ul>
      </section>

      <ClarifyingQuestions analysis={analysis} />
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
