import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorPanel } from '../components/ErrorPanel'
import { useI18n } from '../i18n'
import type { EmergencyReference } from '../types'

/**
 * A fixed reference card. It takes no image and shows nothing patient-specific
 * — that is deliberate, and the page says so, because a responder needs to
 * know this is not an assessment of the casualty in front of them.
 */
export function Emergency() {
  const { t } = useI18n()
  const [data, setData] = useState<EmergencyReference | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => { api.emergency().then(setData).catch(setError) }, [])

  if (error) return <ErrorPanel error={error} />
  if (!data) return <p className="hint">{t('common.loading')}</p>

  return (
    <div>
      <h1>{data.title}</h1>

      <div className="error-panel" role="note">
        <p><strong>{data.disclaimer}</strong></p>
      </div>

      <section className="card">
        <h2>{t('emergency.whyStatic')}</h2>
        <p className="hint">{data.why_static}</p>
      </section>

      {data.topics.map((topic) => (
        <section className="card" key={topic.id}>
          <h2>{topic.title}</h2>

          {topic.diagram && data.diagrams[topic.diagram] && (
            <div
              className="diagram"
              // Fixed, server-side constant SVG from our own reference module;
              // it contains no script, no href and no external asset, and the
              // test suite asserts that.
              dangerouslySetInnerHTML={{ __html: data.diagrams[topic.diagram] }}
            />
          )}

          <ol className="steps">
            {topic.steps.map((step) => <li key={step}>{step}</li>)}
          </ol>

          {topic.move_only_if && (
            <>
              <h3>{t('emergency.moveOnlyIf')}</h3>
              <ul className="plain">
                {topic.move_only_if.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </>
          )}

          {topic.warnings && topic.warnings.length > 0 && (
            <div className="caveat" role="alert">
              <ul className="plain">
                {topic.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
          )}
        </section>
      ))}
    </div>
  )
}
