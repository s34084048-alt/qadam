import { ApiError } from '../api'
import { useI18n } from '../i18n'

export function ErrorPanel({ error }: { error: unknown }) {
  const { t } = useI18n()
  if (!error) return null

  const isApi = error instanceof ApiError
  const message = isApi ? error.message : String((error as Error)?.message ?? error)
  const hint = isApi ? error.hint : null
  const quality = isApi
    ? (error.details?.quality as { checks?: { name: string; passed: boolean; hint: string }[] } | undefined)
    : undefined

  return (
    <div className="error-panel" role="alert">
      <h3>{isApi && error.code === 'image_quality_rejected'
        ? t('quality.rejected')
        : t('common.error')}</h3>
      <p>{message}</p>
      {quality?.checks && (
        <ul className="plain">
          {quality.checks.filter((c) => !c.passed).map((c) => (
            <li key={c.name}>
              <strong>{t(`quality.check.${c.name}`)}:</strong> {c.hint}
            </li>
          ))}
        </ul>
      )}
      {hint && !quality && (
        <p className="hint">
          <strong>{t('common.hint')}: </strong>{hint}
        </p>
      )}
    </div>
  )
}
