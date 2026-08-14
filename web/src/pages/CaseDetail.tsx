import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { DeleteCase } from '../components/DeleteCase'
import { ErrorPanel } from '../components/ErrorPanel'
import { FollowUp } from '../components/FollowUp'
import { FootRisk } from '../components/FootRisk'
import { Investigations } from '../components/Investigations'
import { LabPanelForm } from '../components/LabPanelForm'
import { LabPanelView } from '../components/LabPanelView'
import { OverlayImage, ResultView, TriageCard } from '../components/ResultView'
import { RoutingCard } from '../components/RoutingCard'
import { WoundProgress } from '../components/WoundProgress'
import { useI18n } from '../i18n'
import type { CaseDetail as CaseDetailType, LabPanel } from '../types'

export function CaseDetail() {
  const { t } = useI18n()
  const { caseId = '' } = useParams()
  const [data, setData] = useState<CaseDetailType | null>(null)
  const [panels, setPanels] = useState<LabPanel[]>([])
  const [addingLabs, setAddingLabs] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    api.getCase(caseId).then(setData).catch(setError)
    api.listLabPanels(caseId).then((r) => setPanels(r.panels)).catch(() => {})
  }, [caseId])

  if (error) return <ErrorPanel error={error} />
  if (!data) return <p className="hint">{t('common.loading')}</p>

  const previous = data.history[0] ?? null

  return (
    <div>
      <p><Link to="/cases">← {t('case.back')}</Link></p>
      <h1>
        {t('case.title')} · {data.patient_ref} · {data.module}
      </h1>
      <p className="hint">
        {t('cases.created')}: {new Date(data.created_at).toLocaleString()}
        {data.body_site ? ` · ${data.body_site}` : ''} · {data.status}
      </p>

      {/* The decision, first and alone. Everything below it is evidence. */}
      <RoutingCard routing={data.routing} />

      {!data.latest_analysis && (
        <section className="card"><p className="hint">{t('cases.none')}</p></section>
      )}

      {data.latest_analysis && (
        <>
          <h2>{t('case.photoRecord')}</h2>
          <p className="hint">{t('case.photoRecordHint')}</p>
          <ResultView analysis={data.latest_analysis} caseId={data.id} />
        </>
      )}

      {/* Directly under the decision: whether the wound is closing is the
          question a surveillance programme exists to answer. */}
      <WoundProgress caseId={caseId} />

      {data.latest_analysis && (
        <section className="card">
          <h2>{t('case.compare')}</h2>
          <p className="hint">{t('case.compareHint')}</p>
          {!previous && <p className="hint">{t('case.noHistory')}</p>}
          {previous && (
            <div className="compare-grid">
              <figure style={{ margin: 0 }}>
                <TriageCard analysis={previous} />
                <OverlayImage analysis={previous} />
                <figcaption>
                  {new Date(previous.created_at).toLocaleString()}
                </figcaption>
              </figure>
              <figure style={{ margin: 0 }}>
                <TriageCard analysis={data.latest_analysis} />
                <OverlayImage analysis={data.latest_analysis} />
                <figcaption>
                  {new Date(data.latest_analysis.created_at).toLocaleString()}
                </figcaption>
              </figure>
            </div>
          )}
        </section>
      )}

      {/* Directly under the result, because these answers change the routing
          the result just produced. Placing them below the labs would put the
          most decisive information last. */}
      <FollowUp
        caseId={caseId}
        analysisId={data.latest_analysis?.id ?? null}
      />

      {data.module === 'foot' && <FootRisk caseId={caseId} />}

      <section className="card">
        <h2>{t('lab.panels')}</h2>
        <p className="hint">{t('lab.attachHint')}</p>
        {panels.length === 0 && !addingLabs && (
          <p className="hint">{t('lab.noPanels')}</p>
        )}
        {!addingLabs && (
          <div className="actions">
            <button type="button" onClick={() => setAddingLabs(true)}>
              {t('lab.addPanel')}
            </button>
          </div>
        )}
        {addingLabs && (
          <LabPanelForm
            caseId={caseId}
            onSaved={(panel) => {
              setPanels((current) => [panel, ...current])
              setAddingLabs(false)
            }}
          />
        )}
      </section>

      {panels.map((panel) => (
        <section className="card" key={panel.id ?? panel.created_at}>
          <LabPanelView panel={panel} />
        </section>
      ))}

      <Investigations caseId={caseId} />

      {data.history.length > 0 && (
        <section className="card">
          <h2>{t('case.history')}</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('cases.created')}</th>
                  <th>{t('cases.grade')}</th>
                  <th>{t('result.confidence')}</th>
                  <th>{t('result.model')}</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((item) => (
                  <tr key={item.id}>
                    <td>{new Date(item.created_at).toLocaleString()}</td>
                    <td>
                      <span className="pill" style={{ background: item.triage.color }}>
                        {item.triage.grade.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{(item.triage.confidence * 100).toFixed(0)}%</td>
                    <td>{item.model_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <DeleteCase caseId={caseId} patientRef={data.patient_ref} />
    </div>
  )
}
