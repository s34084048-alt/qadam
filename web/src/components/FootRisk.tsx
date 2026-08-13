import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { FootRiskAssessment, Finding } from '../types'
import { ClinicalPanel } from './ResultView'
import { ErrorPanel } from './ErrorPanel'
import type { Analysis } from '../types'

const FINDINGS: { key: FindingKey; labelKey: string; required: boolean }[] = [
  { key: 'lops', labelKey: 'foot.lops', required: true },
  { key: 'pad', labelKey: 'foot.pad', required: true },
  { key: 'deformity', labelKey: 'foot.deformity', required: false },
  { key: 'previous_ulcer', labelKey: 'foot.previousUlcer', required: false },
  { key: 'previous_amputation', labelKey: 'foot.previousAmputation', required: false },
  { key: 'end_stage_renal_disease', labelKey: 'foot.esrd', required: false },
]

type FindingKey =
  | 'lops' | 'pad' | 'deformity'
  | 'previous_ulcer' | 'previous_amputation' | 'end_stage_renal_disease'

const CATEGORY_COLOR: Record<number, string> = {
  0: 'var(--grade-no_flag)',
  1: 'var(--grade-monitor)',
  2: 'var(--grade-review)',
  3: 'var(--grade-urgent)',
}

export function FootRiskView({ assessment }: { assessment: FootRiskAssessment }) {
  const { t } = useI18n()
  const complete = assessment.complete
  const colour = complete && assessment.category !== null
    ? CATEGORY_COLOR[assessment.category] : 'var(--grade-review)'

  return (
    <div>
      <div className="triage-card" style={{ background: colour }} role="status">
        <div className="grade">
          {complete && assessment.category !== null
            ? `${t('foot.category')} ${assessment.category}`
            : t('foot.notStratified')}
        </div>
        <div className="label">{assessment.label}</div>
        <div className="meta">
          {assessment.foot ? `${assessment.foot} · ` : ''}
          {assessment.screening_interval}
          {assessment.created_at
            ? ` · ${new Date(assessment.created_at).toLocaleString()}` : ''}
        </div>
      </div>

      {!complete && (
        <div className="caveat" role="alert">
          <strong>{t('foot.incompleteTitle')}</strong>
          <ul className="plain">
            {assessment.missing_tests.map((m) => <li key={m}>{m}</li>)}
          </ul>
        </div>
      )}

      {complete && (
        <section className="next-step">
          <h2>{t('foot.nextScreening')}</h2>
          <div className="kv">
            <div><strong>{t('foot.interval')}</strong>{assessment.screening_interval}</div>
            <div><strong>{t('result.routeTo')}</strong>{assessment.routing_target}</div>
          </div>
          {assessment.criteria && <p>{assessment.criteria}</p>}
        </section>
      )}

      <section className="card">
        <h2>{t('result.rationale')}</h2>
        <ul className="plain">
          {assessment.rationale.map((line) => <li key={line}>{line}</li>)}
        </ul>
        <p className="hint">{assessment.source}</p>
      </section>

      {assessment.clinical && (
        <ClinicalPanel
          analysis={{ clinical: assessment.clinical } as unknown as Analysis}
        />
      )}
    </div>
  )
}

export function FootRisk({ caseId }: { caseId: string }) {
  const { t } = useI18n()
  const [assessments, setAssessments] = useState<FootRiskAssessment[]>([])
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [foot, setFoot] = useState('both')

  // Everything defaults to "not tested". Defaulting to "absent" would let a
  // screener produce a low-risk category without touching the patient, which
  // is the failure this module exists to prevent.
  const [findings, setFindings] = useState<Record<FindingKey, Finding>>({
    lops: 'not_tested', pad: 'not_tested', deformity: 'not_tested',
    previous_ulcer: 'not_tested', previous_amputation: 'not_tested',
    end_stage_renal_disease: 'not_tested',
  })

  useEffect(() => {
    api.listFootRisk(caseId)
      .then((r) => setAssessments(r.assessments))
      .catch(() => setAssessments([]))
  }, [caseId])

  const untestedRequired = FINDINGS
    .filter((f) => f.required && findings[f.key] === 'not_tested')
    .map((f) => t(f.labelKey))

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api.addFootRisk(caseId, { foot, ...findings })
      setAssessments((current) => [created, ...current])
      setAdding(false)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>{t('foot.title')}</h2>
      <p className="hint">{t('foot.intro')}</p>
      <ErrorPanel error={error} />

      {assessments.length === 0 && !adding && (
        <p className="hint">{t('foot.none')}</p>
      )}

      {!adding && (
        <div className="actions">
          <button type="button" onClick={() => setAdding(true)}>
            {t('foot.record')}
          </button>
        </div>
      )}

      {adding && (
        <form onSubmit={submit}>
          <div className="field" style={{ maxWidth: 200 }}>
            <label htmlFor="foot-side">{t('foot.side')}</label>
            <select id="foot-side" value={foot}
                    onChange={(e) => setFoot(e.target.value)}>
              <option value="both">both</option>
              <option value="left">left</option>
              <option value="right">right</option>
            </select>
          </div>

          {FINDINGS.map(({ key, labelKey, required }) => (
            <fieldset className="finding" key={key}>
              <legend>
                {t(labelKey)}
                {required && <span className="required-mark"> · {t('foot.requiredTest')}</span>}
              </legend>
              <div className="finding-options">
                {(['present', 'absent', 'not_tested'] as Finding[]).map((value) => (
                  <label key={value} className="radio">
                    <input
                      type="radio" name={key} value={value}
                      checked={findings[key] === value}
                      onChange={() => setFindings((c) => ({ ...c, [key]: value }))}
                    />
                    {t(`foot.finding.${value}`)}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          {untestedRequired.length > 0 && (
            <div className="caveat" role="alert">
              {t('foot.willNotStratify')} {untestedRequired.join(', ')}.
            </div>
          )}

          <div className="actions">
            <button type="submit" disabled={busy}>
              {busy ? t('foot.saving') : t('foot.save')}
            </button>
            <button type="button" className="ghost" onClick={() => setAdding(false)}>
              {t('common.close')}
            </button>
          </div>
        </form>
      )}

      {assessments.map((a) => (
        <div key={a.id ?? a.created_at} style={{ marginTop: '1rem' }}>
          <FootRiskView assessment={a} />
        </div>
      ))}
    </section>
  )
}
