import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorPanel } from '../components/ErrorPanel'
import { useI18n } from '../i18n'
import type { CaseList, Grade } from '../types'

const GRADE_COLOR: Record<Grade, string> = {
  no_flag: 'var(--grade-no_flag)',
  monitor: 'var(--grade-monitor)',
  review: 'var(--grade-review)',
  urgent: 'var(--grade-urgent)',
}

export function Cases() {
  const { t } = useI18n()
  const [module, setModule] = useState('')
  const [grade, setGrade] = useState('')
  const [patientRef, setPatientRef] = useState('')
  const [data, setData] = useState<CaseList | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    api.listCases({ module, grade, patient_ref: patientRef, limit: 50 })
      .then((next) => { if (!cancelled) { setData(next); setError(null) } })
      .catch((err) => { if (!cancelled) setError(err) })
    return () => { cancelled = true }
  }, [module, grade, patientRef])

  return (
    <div>
      <h1>{t('cases.title')}</h1>
      <ErrorPanel error={error} />

      <section className="card">
        <div className="filters">
          <div className="field">
            <label htmlFor="f-module">{t('cases.module')}</label>
            <select id="f-module" value={module} onChange={(e) => setModule(e.target.value)}>
              <option value="">{t('cases.all')}</option>
              <option value="foot">foot</option>
              <option value="skin">skin</option>
              <option value="eye">eye</option>
              <option value="injury">injury</option>
              <option value="face">face</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-grade">{t('cases.grade')}</label>
            <select id="f-grade" value={grade} onChange={(e) => setGrade(e.target.value)}>
              <option value="">{t('cases.all')}</option>
              <option value="no_flag">no_flag</option>
              <option value="monitor">monitor</option>
              <option value="review">review</option>
              <option value="urgent">urgent</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-ref">{t('cases.patient')}</label>
            <input
              id="f-ref" type="text" value={patientRef}
              onChange={(e) => setPatientRef(e.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="card">
        {!data && <p className="hint">{t('common.loading')}</p>}
        {data && data.items.length === 0 && <p className="hint">{t('cases.none')}</p>}
        {data && data.items.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('cases.patient')}</th>
                  <th>{t('cases.module')}</th>
                  <th>{t('cases.grade')}</th>
                  <th>{t('cases.status')}</th>
                  <th>{t('cases.analyses')}</th>
                  <th>{t('cases.created')}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td><Link to={`/cases/${item.id}`}>{item.patient_ref}</Link></td>
                    <td>{item.module}</td>
                    <td>
                      {item.triage_grade ? (
                        <span
                          className="pill"
                          style={{ background: GRADE_COLOR[item.triage_grade] }}
                        >
                          {item.triage_grade.replace('_', ' ')}
                        </span>
                      ) : <span className="hint">—</span>}
                    </td>
                    <td>{item.status}</td>
                    <td>{item.analysis_count}</td>
                    <td>{new Date(item.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
