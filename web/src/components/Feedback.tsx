import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { FeedbackList } from '../types'
import { ErrorPanel } from './ErrorPanel'

/**
 * "Was this right?" — the validation dataset, one row at a time.
 *
 * Every real defect this platform has had was found by a person looking at a
 * real photograph, never by its test suite. This is where those reports are
 * meant to land instead of scattering across messages.
 *
 * Two taps to the useful part: the verdict alone is a usable row. Ground truth
 * and a note refine it and are optional, because a form that demands three
 * fields gets abandoned and then the report is lost entirely.
 */
export function Feedback({ caseId, analysisId }: {
  caseId: string
  analysisId: string
}) {
  const { t } = useI18n()
  const [data, setData] = useState<FeedbackList | null>(null)
  const [verdict, setVerdict] = useState<string | null>(null)
  const [truth, setTruth] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    api.listFeedback(caseId)
      .then((next) => { if (!cancelled) setData(next) })
      .catch(() => { if (!cancelled) setData(null) })
    return () => { cancelled = true }
  }, [caseId])

  if (!data) return null

  async function submit() {
    if (!verdict) return
    setBusy(true)
    setError(null)
    try {
      const entry = await api.addFeedback(caseId, {
        analysis_id: analysisId,
        verdict,
        ground_truth: truth,
        note: note.trim() || null,
      })
      setData((c) => (c ? { ...c, entries: [entry, ...c.entries],
                            total: c.total + 1 } : c))
      setDone(true)
      setVerdict(null); setTruth(null); setNote('')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card feedback">
      <h2>{t('feedback.title')}</h2>
      <p className="hint">{t('feedback.intro')}</p>

      {error != null && <ErrorPanel error={error} />}
      {done && <p className="hint" role="status">{t('feedback.thanks')}</p>}

      <div className="followup-options" role="radiogroup"
           aria-label={t('feedback.title')}>
        {Object.entries(data.verdicts).map(([key, label]) => (
          <label key={key}
                 className={`followup-option${verdict === key ? ' selected' : ''}`}>
            <input type="radio" name="verdict" checked={verdict === key}
                   onChange={() => { setVerdict(key); setDone(false) }} />
            {label}
          </label>
        ))}
      </div>

      {verdict && verdict !== 'unusable_image' && (
        <>
          <h3>{t('feedback.groundTruth')}</h3>
          <p className="hint">{t('feedback.groundTruthHint')}</p>
          <div className="followup-options" role="radiogroup"
               aria-label={t('feedback.groundTruth')}>
            {Object.entries(data.ground_truth_options).map(([key, label]) => (
              <label key={key}
                     className={`followup-option${truth === key ? ' selected' : ''}`}>
                <input type="radio" name="truth" checked={truth === key}
                       onChange={() => setTruth(key)} />
                {label}
              </label>
            ))}
          </div>
        </>
      )}

      {verdict && (
        <>
          <textarea
            className="followup-note"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t('feedback.notePlaceholder')}
            maxLength={2000}
          />
          <div className="actions">
            <button type="button" onClick={() => void submit()} disabled={busy}>
              {busy ? t('feedback.sending') : t('feedback.send')}
            </button>
          </div>
        </>
      )}

      <p className="hint">{data.note}</p>

      {data.entries.length > 0 && (
        <details className="scale-block">
          <summary>{t('feedback.previous')} ({data.total})</summary>
          <ul className="plain">
            {data.entries.map((e) => (
              <li key={e.id}>
                {new Date(e.created_at).toLocaleDateString()} —{' '}
                <strong>{e.verdict_label}</strong>
                {e.ground_truth_label ? ` · ${e.ground_truth_label}` : ''}
                {e.note ? ` · ${e.note}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
