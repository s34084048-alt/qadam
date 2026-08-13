import { useState } from 'react'
import { useI18n } from '../i18n'
import { useOffline } from '../offline/OfflineContext'

/**
 * Connection and queue state, always visible when either is not clean.
 *
 * The wording matters more than the styling here. A queued capture has NOT
 * been analysed — the analysis runs on the server — so the screen must never
 * let a health worker read "queued" as "checked and clear". It says so
 * explicitly, every time.
 */
export function OfflineBar() {
  const { t } = useI18n()
  const { online, pending, failed, syncing, lastReport, queue, syncNow, discardAll } =
    useOffline()
  const [open, setOpen] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)

  const queued = pending + failed
  if (online && queued === 0) return null

  return (
    <div className={`offline-bar ${online ? 'queued' : 'offline'}`} role="status">
      <div className="offline-bar-head">
        <strong>
          {online ? t('offline.online') : t('offline.offline')}
          {queued > 0 && ` · ${queued} ${t('offline.queued')}`}
        </strong>
        {queued > 0 && (
          <>
            <button type="button" className="link" onClick={() => setOpen(!open)}>
              {open ? t('common.close') : t('offline.showQueue')}
            </button>
            <button type="button" className="link" onClick={() => void syncNow()}
                    disabled={syncing || !online}>
              {syncing ? t('offline.syncing') : t('offline.syncNow')}
            </button>
          </>
        )}
      </div>

      {queued > 0 && <p className="offline-warning">{t('offline.notAnalysed')}</p>}
      {failed > 0 && <p className="offline-warning">{t('offline.failed')}</p>}
      {lastReport?.reason && lastReport.stopped && (
        <p className="offline-warning">
          {t('offline.stopped')}: {lastReport.reason}
        </p>
      )}

      {open && (
        <div className="offline-queue">
          <ol>
            {queue.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.label}</strong>
                {entry.patientRef ? ` · ${entry.patientRef}` : ''}
                {' · '}{new Date(entry.createdAt).toLocaleString()}
                {entry.status === 'failed' && (
                  <span className="failed"> · {t('offline.failedItem')}
                    {entry.lastError ? `: ${entry.lastError}` : ''}</span>
                )}
              </li>
            ))}
          </ol>
          {!confirmDiscard ? (
            <button type="button" className="link"
                    onClick={() => setConfirmDiscard(true)}>
              {t('offline.discard')}
            </button>
          ) : (
            <span className="discard-confirm">
              {t('offline.discardConfirm')}
              <button type="button" className="link"
                      onClick={() => { void discardAll(); setConfirmDiscard(false) }}>
                {t('offline.discardYes')}
              </button>
              <button type="button" className="link"
                      onClick={() => setConfirmDiscard(false)}>
                {t('offline.discardNo')}
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
