import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api'
import { Capture } from '../components/Capture'
import { ErrorPanel } from '../components/ErrorPanel'
import { LabPanelForm } from '../components/LabPanelForm'
import { LabPanelView } from '../components/LabPanelView'
import { ResultView } from '../components/ResultView'
import { useI18n } from '../i18n'
import { useOffline } from '../offline/OfflineContext'
import * as outbox from '../offline/outbox'
import type { Analysis, LabPanel, ModuleInfo } from '../types'

export function NewCase() {
  const { t, lang } = useI18n()
  const { online } = useOffline()
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [selected, setSelected] = useState<ModuleInfo | null>(null)

  const [patientRef, setPatientRef] = useState('')
  const [bodySite, setBodySite] = useState('')
  const [skinTone, setSkinTone] = useState<string>('')
  const [consent, setConsent] = useState(false)
  const [patientReady, setPatientReady] = useState(false)

  const [caseId, setCaseId] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [labPanel, setLabPanel] = useState<LabPanel | null>(null)
  const [queued, setQueued] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    api.modules().then((data) => setModules(data.modules)).catch(setError)
  }, [])

  function chooseModule(module: ModuleInfo) {
    setSelected(module)
    setBodySite(module.body_sites[0] ?? '')
    setCaseId(null)
    setAnalysis(null)
    setLabPanel(null)
    setError(null)
  }

  async function preparePatient(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const payload = {
        skin_tone_monk: skinTone ? Number(skinTone) : null,
        consent_flag: consent,
      }
      if (!online) {
        await outbox.enqueue({
          localId: outbox.newLocalId('patient'), kind: 'patient',
          path: '/patients', method: 'POST',
          body: { external_ref: patientRef, ...payload },
          label: 'patient record', patientRef,
        })
      } else {
        try {
          await api.getPatient(patientRef)
          await api.updatePatient(patientRef, payload)
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            await api.createPatient({ external_ref: patientRef, ...payload })
          } else {
            throw err
          }
        }
      }
      setPatientReady(true)
      // A numeric module posts straight to /cases/{id}/labs, so the case has
      // to exist before the form is usable. Image modules create it lazily on
      // first analyse instead.
      if (online && selected?.input_kind === 'numeric' && !caseId) {
        const created = await api.createCase({
          module: selected.id, patient_ref: patientRef, body_site: null,
        })
        setCaseId(created.id)
      }
    } catch (err) {
      setError(err)
      setPatientReady(false)
    } finally {
      setBusy(false)
    }
  }

  async function analyze(blob: Blob, filename: string) {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      if (!online) {
        // Queue the case and the capture together. The analysis runs on the
        // server, so nothing here produces a grade -- and the UI must not
        // pretend otherwise.
        const localCaseId = outbox.newLocalId('case')
        await outbox.enqueue({
          localId: localCaseId, kind: 'case', path: '/cases', method: 'POST',
          body: { module: selected.id, patient_ref: patientRef,
                  body_site: bodySite || null },
          label: `${selected.id} case`, patientRef,
        })
        await outbox.enqueue({
          localId: outbox.newLocalId('analyze'), kind: 'analyze',
          path: `/cases/{$ref:${localCaseId}}/analyze`, method: 'POST',
          blob, blobFieldName: 'file', blobFileName: filename,
          label: `${selected.id} image`, patientRef,
        })
        setQueued(true)
        return
      }

      let id = caseId
      if (!id) {
        const created = await api.createCase({
          module: selected.id,
          patient_ref: patientRef,
          body_site: bodySite || null,
        })
        id = created.id
        setCaseId(id)
      }

      // Hold a durable copy while the upload is in flight. A phone that
      // discards the tab mid-analysis — or a dev-server reload — would
      // otherwise take the capture with it, and the patient is no longer in
      // front of the health worker to photograph again. It targets the case
      // that already exists, so a resumed send adds an analysis rather than a
      // duplicate case.
      const safetyCopy = await outbox.enqueue({
        localId: outbox.newLocalId('analyze'), kind: 'analyze',
        path: `/cases/${id}/analyze`, method: 'POST',
        blob, blobFieldName: 'file', blobFileName: filename,
        label: `${selected.id} image`, patientRef,
      })

      try {
        setAnalysis(await api.analyze(id, blob, filename))
      } finally {
        // Sent (or definitively rejected): the queue no longer needs it.
        await outbox.discard(safetyCopy)
      }
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setSelected(null)
    setPatientReady(false)
    setPatientRef('')
    setSkinTone('')
    setConsent(false)
    setCaseId(null)
    setAnalysis(null)
    setLabPanel(null)
    setQueued(false)
    setError(null)
  }

  if (queued) {
    return (
      <div>
        <div className="step-label">{t('new.step.result')}</div>
        <section className="card">
          <div className="caveat" role="alert">
            <strong>{t('offline.queuedCapture')}</strong>
            <p style={{ marginTop: '.4rem' }}>{t('offline.notAnalysed')}</p>
          </div>
          <div className="actions">
            <button className="secondary" onClick={reset}>
              {t('result.newCase')}
            </button>
          </div>
        </section>
      </div>
    )
  }

  if (labPanel && caseId) {
    return (
      <div>
        <div className="step-label">{t('new.step.result')}</div>
        <LabPanelView panel={labPanel} />
        <div className="actions">
          <button className="secondary" onClick={reset}>{t('result.newCase')}</button>
          <Link to={`/cases/${caseId}`}>
            <button className="ghost" type="button">{t('result.openCase')}</button>
          </Link>
        </div>
      </div>
    )
  }

  if (analysis && caseId) {
    return (
      <div>
        <div className="step-label">{t('new.step.result')}</div>
        <ResultView analysis={analysis} caseId={caseId} />
        <div className="actions">
          <button className="secondary" onClick={reset}>{t('result.newCase')}</button>
          <Link to={`/cases/${caseId}`}>
            <button className="ghost" type="button">{t('result.openCase')}</button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div>
      <ErrorPanel error={error} />

      <section className="card">
        <div className="step-label">{t('new.step.module')}</div>
        <div className="module-grid">
          {modules.map((module) => (
            <button
              key={module.id}
              type="button"
              className="module-card"
              aria-pressed={selected?.id === module.id}
              onClick={() => chooseModule(module)}
            >
              <h3>{module.label[lang]}</h3>
              <p>{module.description[lang]}</p>
              {module.routing_only && (
                <span className="routing-only">ROUTING ONLY — NO DIAGNOSIS</span>
              )}
            </button>
          ))}
        </div>
      </section>

      {selected && (
        <>
          <section className="card">
            <div className="step-label">{t('new.step.patient')}</div>
            <form onSubmit={preparePatient}>
              <div className="field">
                <label htmlFor="ref">{t('new.patient.ref')}</label>
                <input
                  id="ref" type="text" className="code" value={patientRef} required
                  onChange={(e) => { setPatientRef(e.target.value); setPatientReady(false) }}
                  placeholder="e.g. CLINIC-2418"
                />
                <p className="hint">{t('new.patient.refHint')}</p>
              </div>

              <div className="field">
                <label htmlFor="site">{t('new.patient.site')}</label>
                <select id="site" value={bodySite} onChange={(e) => setBodySite(e.target.value)}>
                  {selected.body_sites.map((site) => (
                    <option key={site} value={site}>{site}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label htmlFor="tone">{t('new.patient.tone')}</label>
                <select id="tone" value={skinTone} onChange={(e) => setSkinTone(e.target.value)}>
                  <option value="">{t('common.notRecorded')}</option>
                  {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
                <p className="hint">{t('new.patient.toneHint')}</p>
              </div>

              <div className="checkbox field">
                <input
                  id="consent" type="checkbox" checked={consent}
                  onChange={(e) => { setConsent(e.target.checked); setPatientReady(false) }}
                />
                <label htmlFor="consent">
                  {t('new.patient.consent')}
                  <span className="hint"> {t('new.patient.consentRequired')}</span>
                </label>
              </div>

              <button type="submit" disabled={busy || !patientRef || !consent}>
                {t('new.patient.create')}
              </button>
              {patientReady && <span className="hint"> ✓ {t('new.patient.ready')}</span>}
            </form>
          </section>

          <section className="card">
            <div className="step-label">
              {selected.input_kind === 'numeric'
                ? t('lab.addPanel') : t('new.step.capture')}
            </div>
            {selected.input_kind === 'numeric' ? (
              patientReady && caseId ? (
                <LabPanelForm
                  caseId={caseId}
                  defaultSex={null}
                  onSaved={setLabPanel}
                />
              ) : (
                <p className="hint">{t('lab.needCase')}</p>
              )
            ) : (
              <Capture onAnalyze={analyze} busy={busy} disabled={!patientReady} />
            )}
          </section>

          <section className="card">
            <h2>{t('result.limitations')}</h2>
            <div className="limitations">
              <ul className="plain">
                {selected.limitations.map((line) => <li key={line}>{line}</li>)}
              </ul>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
