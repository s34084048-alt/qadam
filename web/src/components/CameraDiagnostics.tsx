import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../i18n'

interface Report {
  origin: string
  secureContext: boolean
  apiPresent: boolean
  permission: string
  videoInputs: number
  labels: string[]
  lastTest: string | null
}

/**
 * Why this exists.
 *
 * "The camera doesn't work" has at least five distinct causes — insecure
 * origin, denied permission, no device, device busy, over-constrained request
 * — and they need completely different fixes. Guessing wastes the user's time,
 * so the app reports what the browser actually says and names the fix for that
 * specific state.
 */
export function CameraDiagnostics() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [testing, setTesting] = useState(false)

  const gather = useCallback(async (lastTest: string | null = null) => {
    const next: Report = {
      origin: window.location.origin,
      secureContext: window.isSecureContext,
      apiPresent: Boolean(navigator.mediaDevices?.getUserMedia),
      permission: 'unknown',
      videoInputs: 0,
      labels: [],
      lastTest,
    }
    try {
      const status = await navigator.permissions.query(
        { name: 'camera' as PermissionName })
      next.permission = status.state
    } catch { next.permission = 'not reportable by this browser' }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const cams = devices.filter((d) => d.kind === 'videoinput')
      next.videoInputs = cams.length
      // Labels stay empty until permission is granted; that is itself a signal.
      next.labels = cams.map((d) => d.label).filter(Boolean)
    } catch { /* enumerateDevices unavailable */ }
    setReport(next)
    return next
  }, [])

  useEffect(() => { if (open) void gather() }, [open, gather])

  async function testCamera() {
    setTesting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true, audio: false,
      })
      const label = stream.getVideoTracks()[0]?.label || 'unnamed device'
      stream.getTracks().forEach((track) => track.stop())
      await gather(`OK — ${label}`)
    } catch (err) {
      const name = (err as DOMException)?.name ?? 'Error'
      const message = (err as Error)?.message ?? ''
      await gather(`${name}: ${message}`)
    } finally {
      setTesting(false)
    }
  }

  /** The one sentence that matters, chosen from the actual state. */
  function verdict(r: Report): { key: string; bad: boolean } {
    if (!r.secureContext) return { key: 'diag.fixInsecure', bad: true }
    if (!r.apiPresent) return { key: 'diag.fixNoApi', bad: true }
    if (r.permission === 'denied') return { key: 'diag.fixDenied', bad: true }
    if (r.videoInputs === 0) return { key: 'diag.fixNoDevice', bad: true }
    if (r.lastTest && !r.lastTest.startsWith('OK')) {
      if (r.lastTest.startsWith('NotReadableError')
          || r.lastTest.startsWith('TrackStartError')) {
        return { key: 'diag.fixBusy', bad: true }
      }
      if (r.lastTest.startsWith('NotAllowedError')) {
        return { key: 'diag.fixDenied', bad: true }
      }
      return { key: 'diag.fixUnknown', bad: true }
    }
    if (r.permission === 'prompt') return { key: 'diag.fixPrompt', bad: false }
    return { key: 'diag.fixNone', bad: false }
  }

  return (
    <div className="diagnostics">
      <button type="button" className="link" onClick={() => setOpen(!open)}>
        {open ? t('common.close') : t('diag.open')}
      </button>

      {open && report && (
        <div className="diagnostics-body">
          <p className={verdict(report).bad ? 'diag-verdict bad' : 'diag-verdict'}>
            {t(verdict(report).key)}
          </p>

          <table>
            <tbody>
              <tr>
                <td>{t('diag.origin')}</td>
                <td className="mono">{report.origin}</td>
              </tr>
              <tr>
                <td>{t('diag.secure')}</td>
                <td className={report.secureContext ? 'ok' : 'bad'}>
                  {String(report.secureContext)}
                </td>
              </tr>
              <tr>
                <td>{t('diag.api')}</td>
                <td className={report.apiPresent ? 'ok' : 'bad'}>
                  {String(report.apiPresent)}
                </td>
              </tr>
              <tr>
                <td>{t('diag.permission')}</td>
                <td className={report.permission === 'denied' ? 'bad' : ''}>
                  {report.permission}
                </td>
              </tr>
              <tr>
                <td>{t('diag.devices')}</td>
                <td className={report.videoInputs === 0 ? 'bad' : ''}>
                  {report.videoInputs}
                  {report.labels.length > 0 && ` — ${report.labels.join(', ')}`}
                </td>
              </tr>
              {report.lastTest && (
                <tr>
                  <td>{t('diag.lastTest')}</td>
                  <td className={report.lastTest.startsWith('OK') ? 'ok mono' : 'bad mono'}>
                    {report.lastTest}
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <div className="actions">
            <button type="button" onClick={testCamera} disabled={testing}>
              {testing ? t('diag.testing') : t('diag.test')}
            </button>
            <button type="button" className="ghost"
                    onClick={() => void navigator.clipboard?.writeText(
                      JSON.stringify(report, null, 2))}>
              {t('diag.copy')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
