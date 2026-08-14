import { useI18n } from '../i18n'
import type { Routing } from '../types'

/**
 * The case's decision, and the only thing on the page presented as one.
 *
 * The photograph's grade used to sit here. It cannot: hand-tuned colour
 * thresholds hit a ceiling this project measured directly, where catching a
 * wound that fills the frame brought back a false alarm on a healthy toe and
 * avoiding that brought back the silent miss. What is left is the examination
 * and the answers, both obtained by a person.
 *
 * NOT ASSESSED IS RENDERED AS AN ABSENCE, NEVER AS A RESULT. No grade colour,
 * no green, no reassuring word — a case nobody has examined must not look like
 * a case that was examined and found well.
 */
export function RoutingCard({ routing }: { routing: Routing }) {
  const { t } = useI18n()

  if (!routing.assessed) {
    return (
      <section className="card routing-card unassessed" role="status">
        <div className="routing-grade">{t('routing.notAssessed')}</div>
        <p className="caveat">{routing.note}</p>
        {routing.missing.length > 0 && (
          <>
            <h3>{t('routing.missing')}</h3>
            <ul className="plain">
              {routing.missing.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </>
        )}
        <p className="hint">{routing.image_note}</p>
      </section>
    )
  }

  return (
    <section className="card routing-card" role="status">
      <div className="routing-head" style={{ background: routing.color }}>
        <div className="routing-grade">
          {String(routing.grade).replace('_', ' ')}
        </div>
        <div className="routing-label">{routing.label}</div>
      </div>

      <div className="kv">
        <div><strong>{t('result.timeframe')}</strong>{routing.urgency}</div>
        <div><strong>{t('result.routeTo')}</strong>{routing.routing_target}</div>
      </div>
      <p>{routing.next_investigation}</p>

      <h3>{t('routing.basis')}</h3>
      <ul className="plain">
        {routing.basis.map((b) => (
          <li key={b.source}>
            <strong>{t(`routing.source.${b.source}`)}</strong> — {b.detail}
            {b.screening_interval ? ` · ${b.screening_interval}` : ''}
            {b.triggers && b.triggers.length > 0 && (
              <ul className="plain">
                {b.triggers.map((x) => <li key={x}>{x}</li>)}
              </ul>
            )}
          </li>
        ))}
      </ul>

      {routing.missing.length > 0 && (
        <>
          <h3>{t('routing.missing')}</h3>
          <div className="limitations">
            <ul className="plain">
              {routing.missing.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </div>
        </>
      )}

      <p className="hint">{routing.image_note}</p>
    </section>
  )
}
