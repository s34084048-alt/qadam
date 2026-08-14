import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { ErrorPanel } from './ErrorPanel'

/**
 * File the laboratory's own report — the printout or PDF — against the case.
 *
 * STORED, NEVER READ. Nothing extracts values from this document and no grade
 * comes out of it. The interpretation above works on values a person typed,
 * with the unit stated, because reading 2.4 mg/dL as 2.4 µmol/L calls a patient
 * in kidney failure normal and no OCR of a printout can be trusted not to.
 *
 * The document is here so the referral has its source attached, and so a
 * reviewer can check the typed numbers against the original.
 */
export function LabReportUpload({ caseId, onFiled }: {
  caseId: string
  onFiled?: () => void
}) {
  const { t } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [service, setService] = useState('')
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<unknown>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!file || !ack) return
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('category', 'laboratory')
      form.append('identifiers_removed', 'true')
      form.append('file', file, file.name)
      if (service.trim()) form.append('reporting_service', service.trim())
      await api.addInvestigation(caseId, form)
      setDone(true)
      setFile(null)
      setAck(false)
      onFiled?.()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h3>{t('labUpload.title')}</h3>
      <p className="hint">{t('labUpload.storedNotRead')}</p>

      <ErrorPanel error={error} />
      {done && <p className="hint" role="status">{t('labUpload.filed')}</p>}

      <div className="field">
        <label className="as-button ghost" htmlFor="lab-report-file">
          {file ? file.name : t('labUpload.choose')}
        </label>
        <input
          id="lab-report-file"
          className="offscreen"
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setDone(false) }}
        />
      </div>

      <div className="field">
        <label htmlFor="lab-service">{t('labUpload.service')}</label>
        <input
          id="lab-service"
          value={service}
          onChange={(e) => setService(e.target.value)}
          placeholder={t('labUpload.servicePlaceholder')}
        />
        <p className="hint">{t('labUpload.serviceHint')}</p>
      </div>

      {/* The same acknowledgement every filed document carries: a lab printout
          normally has the patient's name and date of birth across the top, and
          this record is pseudonymous. */}
      <div className="checkbox">
        <input id="lab-ack" type="checkbox" checked={ack}
               onChange={(e) => setAck(e.target.checked)} />
        <label htmlFor="lab-ack">{t('labUpload.ack')}</label>
      </div>

      <div className="actions">
        <button type="submit" disabled={!file || !ack || busy}>
          {busy ? t('labUpload.filing') : t('labUpload.file')}
        </button>
      </div>
    </form>
  )
}
