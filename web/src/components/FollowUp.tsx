import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import * as outbox from '../offline/outbox'
import { useOffline } from '../offline/OfflineContext'
import type { FollowUp as FollowUpEntry, FollowUpList, FollowUpQuestion } from '../types'
import { ErrorPanel } from './ErrorPanel'

const GRADE_VAR: Record<string, string> = {
  no_flag: 'var(--grade-no_flag)',
  monitor: 'var(--grade-monitor)',
  review: 'var(--grade-review)',
  urgent: 'var(--grade-urgent)',
}

type Answers = Record<string, string | number>

function GradePill({ grade }: { grade: string }) {
  return (
    <span className="pill" style={{ background: GRADE_VAR[grade] }}>
      {grade.replace('_', ' ')}
    </span>
  )
}

/**
 * One question. Choice questions render as radio buttons rather than a select:
 * a select hides its options until opened, and "not tested" being invisible is
 * how a form ends up full of answers to tests nobody performed.
 */
function QuestionRow({
  question, value, onChange,
}: {
  question: FollowUpQuestion
  value: string | number | undefined
  onChange: (v: string | number | undefined) => void
}) {
  const { t } = useI18n()
  const label = (option: string) => {
    const key = `followUp.opt.${option}`
    const translated = t(key)
    return translated === key ? option.replace(/_/g, ' ') : translated
  }

  return (
    <div className="followup-question">
      <p className="followup-text">{question.text}</p>

      {question.kind === 'number' ? (
        <div className="followup-number">
          <input
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            dir="ltr"
            value={value ?? ''}
            onChange={(e) => onChange(
              e.target.value === '' ? undefined : Number(e.target.value),
            )}
            aria-label={question.text}
          />
          {question.unit && <span className="followup-unit">{question.unit}</span>}
        </div>
      ) : (
        <div className="followup-options" role="radiogroup" aria-label={question.text}>
          {question.options.map((option) => (
            <label
              key={option}
              className={`followup-option${value === option ? ' selected' : ''}`}
            >
              <input
                type="radio"
                name={question.id}
                checked={value === option}
                onChange={() => onChange(option)}
              />
              {label(option)}
            </label>
          ))}
          {value !== undefined && (
            <button
              type="button"
              className="linkish"
              onClick={() => onChange(undefined)}
            >
              {t('followUp.blank')}
            </button>
          )}
        </div>
      )}

      <details className="followup-why">
        <summary>{t('followUp.why')}</summary>
        <p className="hint">{question.why}</p>
      </details>
    </div>
  )
}

export function FollowUpOutcomeView({ entry }: { entry: FollowUpEntry }) {
  const { t } = useI18n()
  return (
    <div className={`followup-outcome${entry.triggered ? ' escalated' : ''}`}>
      <div className="followup-grades">
        <span>
          <strong>{t('followUp.answerGrade')}: </strong>
          <GradePill grade={entry.answer_grade} /> {entry.answer_label}
        </span>
        {/* Shown last and labelled as an observation. It is recorded beside
            the answers so a reader can see what was photographed; it is not
            part of the decision. */}
        <span className="hint">
          {t('followUp.imageObserved')}: <GradePill grade={entry.image_grade} />
        </span>
      </div>

      {entry.triggered
        ? <p className="caveat" role="alert">{t('followUp.triggered')}</p>
        : <p className="hint">{t('followUp.noTrigger')}</p>}

      {entry.outcome.triggers.length > 0 && (
        <>
          <h4>{t('followUp.triggers')}</h4>
          {entry.outcome.triggers.map((trigger) => (
            <div className="consideration" key={trigger.finding}>
              <p>
                <GradePill grade={trigger.grade} />{' '}
                <strong>{trigger.finding}</strong>
              </p>
              <p className="hint">
                <strong>{t('followUp.because')}: </strong>{trigger.because}
              </p>
              {trigger.consider.length > 0 && (
                <>
                  <p className="hint">{t('followUp.consider')}:</p>
                  <ul className="plain">
                    {trigger.consider.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                </>
              )}
              <p className="discriminator">
                <strong>{t('followUp.distinguishedBy')}: </strong>
                {trigger.distinguished_by}
              </p>
            </div>
          ))}
        </>
      )}

      {entry.note && <pre className="summary">{entry.note}</pre>}
      <p className="hint">{entry.outcome.rule}</p>
      <p className="hint">{entry.outcome.status}</p>
    </div>
  )
}

export function FollowUp({
  caseId, analysisId, onSaved,
}: {
  caseId: string
  analysisId?: string | null
  onSaved?: (entry: FollowUpEntry) => void
}) {
  const { t } = useI18n()
  const { online } = useOffline()
  const [data, setData] = useState<FollowUpList | null>(null)
  const [answers, setAnswers] = useState<Answers>({})
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [queued, setQueued] = useState(false)
  const [saved, setSaved] = useState<FollowUpEntry | null>(null)

  useEffect(() => {
    let cancelled = false
    api.listFollowUp(caseId)
      .then((next) => { if (!cancelled) setData(next) })
      .catch(() => { if (!cancelled) setData(null) })
    return () => { cancelled = true }
  }, [caseId])

  // Modules with no question set (labs) get no panel at all rather than an
  // empty one that looks broken.
  if (!data || data.questions.length === 0) return null

  const answeredCount = Object.keys(answers).length
  const canSave = answeredCount > 0 || note.trim().length > 0

  async function save() {
    setError(null)
    setBusy(true)
    try {
      // A foot examined in a village clinic is exactly the case that has no
      // signal. Queue the answers rather than losing them — the patient is not
      // going to be re-examined once they have walked home. The server
      // re-runs the grading when the entry drains, so the escalation is
      // computed by the same rules either way.
      if (!online) {
        await outbox.enqueue({
          localId: outbox.newLocalId('follow-up'), kind: 'follow-up',
          path: `/cases/${caseId}/follow-up`, method: 'POST',
          body: {
            answers,
            note: note.trim() || null,
            analysis_id: analysisId ?? null,
          },
          label: 'follow-up answers', patientRef: null,
        })
        setQueued(true)
        setAnswers({})
        setNote('')
        return
      }
      const entry = await api.addFollowUp(caseId, {
        answers,
        note: note.trim() || null,
        analysis_id: analysisId ?? null,
      })
      setSaved(entry)
      setData((current) => (
        current ? { ...current, entries: [entry, ...current.entries], total: current.total + 1 }
          : current
      ))
      onSaved?.(entry)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>{t('followUp.title')}</h2>
      <p className="hint">{t('followUp.intro')}</p>
      <div className="caveat">{t('followUp.rule')}</div>

      {error != null && <ErrorPanel error={error} />}

      <div className="followup-form">
        {data.questions.map((question) => (
          <QuestionRow
            key={question.id}
            question={question}
            value={answers[question.id]}
            onChange={(value) => setAnswers((current) => {
              const next = { ...current }
              if (value === undefined) delete next[question.id]
              else next[question.id] = value
              return next
            })}
          />
        ))}
      </div>

      <h3>{t('followUp.notes')}</h3>
      <p className="hint">{t('followUp.notesHint')}</p>
      <textarea
        className="followup-note"
        rows={5}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={t('followUp.notesPlaceholder')}
        maxLength={4000}
      />

      <div className="actions">
        <button type="button" onClick={save} disabled={busy || !canSave}>
          {busy ? t('followUp.saving') : t('followUp.submit')}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || (answeredCount === 0 && note === '')}
          onClick={() => { setAnswers({}); setNote('') }}
        >
          {t('followUp.reset')}
        </button>
        <span className="hint">
          {answeredCount} {t('followUp.answered')}
          {' · '}
          {data.questions.length - answeredCount} {t('followUp.unanswered')}
        </span>
      </div>
      {!canSave && <p className="hint">{t('followUp.emptyAnswers')}</p>}

      {/* Queued, not graded. The re-assessment happens on the server when the
          entry drains, so no grade is shown here that the server has not
          produced. */}
      {queued && <div className="caveat" role="status">{t('followUp.queued')}</div>}

      {saved && <FollowUpOutcomeView entry={saved} />}

      <h3>{t('followUp.history')}</h3>
      {data.entries.length === 0 && <p className="hint">{t('followUp.noEntries')}</p>}
      {data.entries.map((entry) => (
        <details key={entry.id} className="scale-block">
          <summary>
            {new Date(entry.created_at).toLocaleString()}
            {' · '}
            <GradePill grade={entry.answer_grade} />
            {entry.triggered ? ` · ${t('followUp.triggered')}` : ''}
          </summary>
          <FollowUpOutcomeView entry={entry} />
        </details>
      ))}
    </section>
  )
}
