import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorPanel } from '../components/ErrorPanel'
import { useI18n } from '../i18n'
import type { Fairness as FairnessData } from '../types'

export function Fairness() {
  const { t } = useI18n()
  const [data, setData] = useState<FairnessData | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => { api.fairness().then(setData).catch(setError) }, [])

  if (error) return <ErrorPanel error={error} />
  if (!data) return <p className="hint">{t('common.loading')}</p>

  const coverage = data.coverage.recorded_fraction

  return (
    <div>
      <h1>{t('fairness.title')}</h1>

      <section className="card">
        <div className="limitations">
          <ul className="plain">
            {data.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
      </section>

      <section className="card">
        <p className="hint">
          {t('fairness.coverage')} {data.coverage.skin_tone_recorded}/
          {data.coverage.analyses_total} {t('fairness.ofAnalyses')}
          {coverage !== null ? ` (${(coverage * 100).toFixed(0)}%)` : ''}
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('fairness.group')}</th>
                <th>{t('fairness.analyses')}</th>
                <th>{t('fairness.meanConfidence')}</th>
                <th>{t('fairness.qualityPass')}</th>
                <th>{t('cases.grade')}</th>
              </tr>
            </thead>
            <tbody>
              {data.strata.map((row) => (
                <tr key={row.group}>
                  <td>{row.group}</td>
                  <td>{row.analyses}</td>
                  <td>
                    {row.mean_confidence === null
                      ? '—' : `${(row.mean_confidence * 100).toFixed(0)}%`}
                  </td>
                  <td>
                    {row.quality_pass_rate === null
                      ? '—' : `${(row.quality_pass_rate * 100).toFixed(0)}%`}
                  </td>
                  <td className="hint">
                    {Object.entries(row.by_grade)
                      .map(([grade, count]) => `${grade.replace('_', ' ')} ${count}`)
                      .join(', ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
