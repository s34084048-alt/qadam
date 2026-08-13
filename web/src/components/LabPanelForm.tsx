import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import type { Analyte, LabCatalogue, LabPanel } from '../types'
import { ErrorPanel } from './ErrorPanel'

interface Row {
  code: string
  value: string
  unit: string
}

interface Props {
  caseId: string
  defaultAge?: number | null
  defaultSex?: string | null
  onSaved: (panel: LabPanel) => void
}

/**
 * Value entry for a lab panel.
 *
 * The unit is a SELECT restricted to the units the analyte accepts, never a
 * free-text box. The API rejects an unrecognised unit rather than guessing,
 * but the better place to make a unit error impossible is here, before it is
 * typed.
 */
export function LabPanelForm({ caseId, defaultAge, defaultSex, onSaved }: Props) {
  const { t } = useI18n()
  const [catalogue, setCatalogue] = useState<LabCatalogue | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [panelName, setPanelName] = useState('')
  const [age, setAge] = useState<string>(defaultAge ? String(defaultAge) : '')
  const [sex, setSex] = useState<string>(defaultSex ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => { api.labCatalogue().then(setCatalogue).catch(setError) }, [])

  const byCode = useMemo(() => {
    const map = new Map<string, Analyte>()
    catalogue?.analytes.forEach((a) => map.set(a.code, a))
    return map
  }, [catalogue])

  const grouped = useMemo(() => {
    const out = new Map<string, Analyte[]>()
    catalogue?.analytes.forEach((a) => {
      const list = out.get(a.group_label) ?? []
      list.push(a)
      out.set(a.group_label, list)
    })
    return [...out.entries()]
  }, [catalogue])

  function addRow(code: string) {
    const analyte = byCode.get(code)
    if (!analyte || rows.some((r) => r.code === code)) return
    setRows((current) => [...current, { code, value: '', unit: analyte.unit }])
  }

  function update(code: string, patch: Partial<Row>) {
    setRows((current) =>
      current.map((r) => (r.code === code ? { ...r, ...patch } : r)))
  }

  function reference(analyte: Analyte): string {
    const range = sex === 'female' && analyte.reference_female
      ? analyte.reference_female : analyte.reference
    if (range.low === null && range.high === null) return '—'
    if (range.low === null) return `< ${range.high}`
    if (range.high === null) return `> ${range.low}`
    return `${range.low} – ${range.high}`
  }

  const filled = rows.filter((r) => r.value.trim() !== '')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const panel = await api.addLabPanel(caseId, {
        panel_name: panelName || null,
        age: age ? Number(age) : null,
        sex: sex || null,
        results: filled.map((r) => ({
          code: r.code, value: Number(r.value), unit: r.unit,
        })),
      })
      onSaved(panel)
      setRows([])
      setPanelName('')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (!catalogue) return <p className="hint">{t('common.loading')}</p>

  return (
    <form onSubmit={submit}>
      <ErrorPanel error={error} />

      <div className="filters" style={{ marginBottom: '.9rem' }}>
        <div className="field">
          <label htmlFor="panel-name">{t('lab.panelName')}</label>
          <input id="panel-name" type="text" value={panelName}
                 placeholder="U&E + FBC"
                 onChange={(e) => setPanelName(e.target.value)} />
        </div>
        <div className="field" style={{ maxWidth: 110 }}>
          <label htmlFor="lab-age">{t('lab.age')}</label>
          <input id="lab-age" type="number" min={0} max={120} value={age}
                 onChange={(e) => setAge(e.target.value)} />
        </div>
        <div className="field" style={{ maxWidth: 150 }}>
          <label htmlFor="lab-sex">{t('lab.sex')}</label>
          <select id="lab-sex" value={sex} onChange={(e) => setSex(e.target.value)}>
            <option value="">{t('common.notRecorded')}</option>
            <option value="female">female</option>
            <option value="male">male</option>
            <option value="other">other</option>
          </select>
        </div>
      </div>
      <p className="hint">{t('lab.ageHint')}</p>

      <div className="field">
        <label htmlFor="add-analyte">{t('lab.addAnalyte')}</label>
        <select
          id="add-analyte"
          value=""
          onChange={(e) => { addRow(e.target.value); e.target.value = '' }}
        >
          <option value="">{t('lab.choose')}</option>
          {grouped.map(([label, analytes]) => (
            <optgroup key={label} label={label}>
              {analytes.map((a) => (
                <option key={a.code} value={a.code}
                        disabled={rows.some((r) => r.code === a.code)}>
                  {a.name} ({a.unit})
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {rows.length === 0 && <p className="hint">{t('lab.noRows')}</p>}

      {rows.map((row) => {
        const analyte = byCode.get(row.code)!
        return (
          <div className="lab-row" key={row.code}>
            <div className="lab-row-name">
              <strong>{analyte.name}</strong>
              <span className="hint">
                {t('lab.reference')}: {reference(analyte)} {analyte.unit}
              </span>
            </div>
            <input
              type="number" step="any" inputMode="decimal"
              className="code"
              value={row.value}
              aria-label={`${analyte.name} value`}
              onChange={(e) => update(row.code, { value: e.target.value })}
            />
            <select
              value={row.unit}
              aria-label={`${analyte.name} unit`}
              onChange={(e) => update(row.code, { unit: e.target.value })}
            >
              {analyte.accepted_units.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
            <button
              type="button" className="ghost"
              onClick={() => setRows((c) => c.filter((r) => r.code !== row.code))}
            >
              ✕
            </button>
            {analyte.note && <p className="hint lab-note">{analyte.note}</p>}
          </div>
        )
      })}

      <div className="actions">
        <button type="submit" disabled={busy || filled.length === 0}>
          {busy ? t('lab.saving') : t('lab.save')}
        </button>
      </div>
      <p className="hint">{catalogue.reference_range_caveat}</p>
    </form>
  )
}
