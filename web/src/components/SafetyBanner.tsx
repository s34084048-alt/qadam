import { useI18n } from '../i18n'

/**
 * Persistent, non-dismissible. The boundary has to be on screen whenever a
 * result is, including on a screenshot of any part of the app.
 */
export function SafetyBanner() {
  const { t } = useI18n()
  return (
    <div className="safety-banner" role="note" aria-live="polite">
      <strong>{t('banner.device')}</strong>
      <span className="sub">
        {t('banner.disclaimer')} {t('banner.human')}
      </span>
    </div>
  )
}
