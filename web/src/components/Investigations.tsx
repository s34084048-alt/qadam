import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { InvestigationResult } from '../types'
import { ErrorPanel } from './ErrorPanel'

const CATEGORIES = ['radiology', 'endoscopy', 'histopathology', 'physiology', 'other']
const MODALITIES = ['x-ray', 'ultrasound', 'ct', 'mri', 'nuclear', 'other']

/**
 * Filing cabinet for results QADAM routed the patient to. Nothing here asks
 * the platform to read the document — the UI says so as plainly as the API
 * does, because a user who believes the app checked the scan is in more danger
 * than one who knows it did not.
 */
export function Investigations({ caseId }: { caseId: string }) {
  const { t } = useI18n()
  const [results, setResults] = useState<InvestigationResult[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const [category, setCategory] = useState('radiology')
  const [modality, setModality] = useState('x-ray')
  const [bodySite, setBodySite] = useState('')
  const [service, setService] = useState('')
  const [reportText, setReportText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [ack, setAck] = useState(false)

  useEffect(() => {
    api.listInvestigations(caseId)
      .then((r) => setResults(r.results))
      .catch(() => setResults([]))
  }, [caseId])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('category', category)
      form.append('identifiers_removed', String(ack))
      if (modality) form.append('modality', modality)
      if (bodySite) form.append('body_site', bodySite)
      if (service) form.append('reporting_service', service)
      if (reportText) form.append('report_text', reportText)
      if (file) form.append('file', file, file.name)

      const created = await api.addInvestigation(caseId, form)
      setResults((current) => [created, ...current])
      setAdding(false)
      setReportText(''); setBodySite(''); setService('')
      setFile(null); setAck(false)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  async function openFile(result: InvestigationResult) {
    try {
      const url = await api.investigationFileUrl(caseId, result.id)
      window.open(url, '_blank', 'noopener')
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card">
      <h2>{t('inv.title')}</h2>
      <div className="caveat" role="note">{t('inv.notInterpreted')}</div>
      <p className="hint">{t('inv.closesLoop')}</p>

      <ErrorPanel error={error} />

      {results.length === 0 && !adding && (
        <p className="hint">{t('inv.none')}</p>
      )}

      {results.map((r) => (
        <div className="consideration" key={r.id}>
          <p>
            <strong>
              {r.category}{r.modality ? ` · ${r.modality}` : ''}
              {r.body_site ? ` · ${r.body_site}` : ''}
            </strong>
            <span className="hint">
              {' '}— {new Date(r.created_at).toLocaleString()}
              {r.reporting_service ? ` · ${r.reporting_service}` : ''}
            </span>
          </p>
          {r.report_text && <p className="report-text">{r.report_text}</p>}
          {r.has_file && (
            <div className="actions">
              <button type="button" className="ghost" onClick={() => openFile(r)}>
                {t('inv.openFile')} ({r.content_type})
              </button>
            </div>
          )}
        </div>
      ))}

      {!adding && (
        <div className="actions">
          <button type="button" onClick={() => setAdding(true)}>
            {t('inv.add')}
          </button>
        </div>
      )}

      {adding && (
        <form onSubmit={submit}>
          <div className="filters">
            <div className="field">
              <label htmlFor="inv-cat">{t('inv.category')}</label>
              <select id="inv-cat" value={category}
                      onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="inv-mod">{t('inv.modality')}</label>
              <select id="inv-mod" value={modality}
                      onChange={(e) => setModality(e.target.value)}>
                <option value="">—</option>
                {MODALITIES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="inv-site">{t('inv.bodySite')}</label>
              <input id="inv-site" type="text" value={bodySite}
                     onChange={(e) => setBodySite(e.target.value)} />
            </div>
          </div>

          <div className="field">
            <label htmlFor="inv-service">{t('inv.service')}</label>
            <input id="inv-service" type="text" value={service}
                   placeholder="City Hospital Radiology"
                   onChange={(e) => setService(e.target.value)} />
            <p className="hint">{t('inv.serviceHint')}</p>
          </div>

          <div className="field">
            <label htmlFor="inv-report">{t('inv.reportText')}</label>
            <textarea id="inv-report" rows={5} value={reportText}
                      onChange={(e) => setReportText(e.target.value)} />
          </div>

          <div className="field">
            <label htmlFor="inv-file">{t('inv.file')}</label>
            <input
              id="inv-file" type="file"
              accept="application/pdf,image/jpeg,image/png,image/webp,text/plain"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <p className="hint">{t('inv.fileHint')}</p>
          </div>

          <div className="checkbox field">
            <input id="inv-ack" type="checkbox" checked={ack}
                   onChange={(e) => setAck(e.target.checked)} />
            <label htmlFor="inv-ack">{t('inv.ack')}</label>
          </div>

          <div className="actions">
            <button type="submit"
                    disabled={busy || !ack || (!reportText && !file)}>
              {busy ? t('inv.saving') : t('inv.save')}
            </button>
            <button type="button" className="ghost" onClick={() => setAdding(false)}>
              {t('common.close')}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
