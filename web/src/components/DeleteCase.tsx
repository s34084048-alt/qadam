import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { CaseDeleteResult } from '../types'
import { ErrorPanel } from './ErrorPanel'

/**
 * Permanent case deletion.
 *
 * Two deliberate frictions. The confirm word must be typed rather than clicked,
 * because a second button is one mis-tap away from the first on a phone held
 * over a patient's foot. And the panel states what SURVIVES as well as what
 * goes, so nobody deletes a case believing it also erased the patient.
 */
export function DeleteCase({ caseId, patientRef }: {
  caseId: string
  patientRef: string
}) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [done, setDone] = useState<CaseDeleteResult | null>(null)

  const word = t('delete.confirmWord')
  const armed = typed.trim().toUpperCase() === word

  async function run() {
    setError(null)
    setBusy(true)
    try {
      const result = await api.deleteCase(caseId)
      setDone(result)
      // Back to the list after a beat: staying on a detail page for a case
      // that no longer exists would just 404 on the next refresh.
      setTimeout(() => navigate('/cases'), 1800)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  if (done) {
    return (
      <section className="card danger-zone">
        <h2>{t('delete.done')}</h2>
        <p className="hint">
          {t('delete.removed')}:{' '}
          {Object.entries(done.deleted)
            .filter(([, n]) => n > 0)
            .map(([k, n]) => `${n} ${k.replace(/_/g, ' ')}`)
            .join(', ') || '—'}
        </p>
        <p className="hint">{done.note}</p>
      </section>
    )
  }

  return (
    <section className="card danger-zone">
      <h2>{t('delete.title')}</h2>
      <p className="caveat">{t('delete.warn')}</p>
      <p className="hint">{t('delete.keeps')}</p>

      {error != null && <ErrorPanel error={error} />}

      {!open && (
        <div className="actions">
          <button type="button" className="danger" onClick={() => setOpen(true)}>
            {t('delete.button')}
          </button>
        </div>
      )}

      {open && (
        <>
          <p><strong>{patientRef}</strong> · {caseId}</p>
          <label htmlFor="delete-confirm">{t('delete.confirmPrompt')}</label>
          <input
            id="delete-confirm"
            dir="ltr"
            autoComplete="off"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={word}
          />
          <div className="actions">
            <button
              type="button"
              className="danger"
              disabled={!armed || busy}
              onClick={run}
            >
              {busy ? t('delete.working') : t('delete.confirm')}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => { setOpen(false); setTyped('') }}
            >
              {t('delete.cancel')}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
