import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { Progress } from '../types'

/**
 * Wound area across visits, in cm².
 *
 * The one image-derived number here that corresponds to an established
 * clinical indicator — percentage area reduction of roughly half by about four
 * weeks. It is shown as a measurement with its provenance, and it changes no
 * grade: the outline still comes from the segmentation that proved unreliable
 * at classification, so an exact ruler does not make the area exact.
 */
export function WoundProgress({ caseId, measure }: {
  caseId: string
  /** Fixed for the whole series on purpose — see app/progress.py. */
  measure?: string
}) {
  const { t } = useI18n()
  const [data, setData] = useState<Progress | null>(null)

  useEffect(() => {
    let cancelled = false
    api.caseProgress(caseId, measure)
      .then((next) => { if (!cancelled) setData(next) })
      .catch(() => { if (!cancelled) setData(null) })
    return () => { cancelled = true }
  }, [caseId, measure])

  if (!data) return null

  const change = data.change
  const prompt = data.prompt
  const max = Math.max(...data.points.map((p) => p.area_cm2), 0.0001)

  return (
    <section className="card">
      <h2>{t('progress.title')}</h2>
      <p className="hint">{t('progress.intro')}</p>

      {!data.comparable && (
        <p className="hint">{data.reason ?? t('progress.notEnough')}</p>
      )}

      {data.points.length > 0 && (
        <div className="progress-series">
          {data.points.map((p) => (
            <div className="progress-row" key={p.analysis_id}>
              <span className="progress-date">
                {new Date(p.at).toLocaleDateString()}
              </span>
              <span className="progress-bar" aria-hidden="true">
                <span style={{ width: `${(p.area_cm2 / max) * 100}%` }} />
              </span>
              <span className="progress-value">{p.area_cm2.toFixed(2)} cm²</span>
            </div>
          ))}
        </div>
      )}

      {change && (
        <div className="kv" style={{ marginTop: '.6rem' }}>
          <div>
            <strong>{t('progress.change')}</strong>
            {change.percent_area_reduction !== null
              ? `${change.percent_area_reduction.toFixed(0)}%`
              : '—'}
          </div>
          <div>
            <strong>{t('progress.absolute')}</strong>
            {change.absolute_cm2.toFixed(2)} cm²
          </div>
          <div>
            <strong>{t('progress.over')}</strong>
            {change.days_between.toFixed(0)} {t('progress.days')}
          </div>
        </div>
      )}

      {prompt && (
        <div className={prompt.action === 'reassess' ? 'caveat' : 'limitations'}>
          <p style={{ margin: 0 }}>{prompt.detail}</p>
        </div>
      )}
      {prompt && <p className="hint">{prompt.basis}</p>}

      {data.excluded.length > 0 && (
        <details className="scale-block">
          <summary>
            {t('progress.excluded')} ({data.excluded.length})
          </summary>
          <ul className="plain">
            {data.excluded.map((e) => (
              <li key={e.analysis_id}>
                {new Date(e.at).toLocaleDateString()} — {e.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className="hint">{data.not_a_diagnosis}</p>
    </section>
  )
}
