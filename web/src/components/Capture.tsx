import { useCallback, useEffect, useRef, useState } from 'react'
import { prepareForUpload } from '../capture-image'
import type { Prepared } from '../capture-image'
import { useI18n } from '../i18n'
import { CameraDiagnostics } from './CameraDiagnostics'
import { CropBox } from './CropBox'

interface Props {
  onAnalyze: (blob: Blob, filename: string) => void
  busy: boolean
  disabled?: boolean
}

/** getUserMedia only exists in a secure context: HTTPS, or localhost. Opening
 *  the app by LAN IP from a phone silently removes the camera entirely, which
 *  is worth saying out loud rather than failing at the button. */
function cameraSupported(): boolean {
  return Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia)
}

/**
 * Device camera capture plus file upload. Capture guidance is shown alongside,
 * because most quality-gate rejections are fixed by distance, framing and light.
 */
export function Capture({ onAnalyze, busy, disabled }: Props) {
  const { t } = useI18n()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const captureRef = useRef<HTMLInputElement | null>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [preview, setPreview] = useState<{ url: string; blob: Blob; name: string } | null>(null)
  const [prepared, setPrepared] = useState<Prepared | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [cropping, setCropping] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const supported = cameraSupported()
  const live = stream !== null

  // Attach the stream only after React has committed the <video> element.
  // Doing it inline after setState races the commit: the ref can still be null,
  // the stream is never attached, and the preview stays black while the camera
  // light is on.
  useEffect(() => {
    const video = videoRef.current
    if (!video || !stream) return
    video.srcObject = stream
    void video.play().catch(() => { /* autoplay rejection is not fatal */ })
  }, [stream])

  const stopCamera = useCallback(() => {
    setStream((current) => {
      current?.getTracks().forEach((track) => track.stop())
      return null
    })
  }, [])

  useEffect(() => () => stopCamera(), [stopCamera])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url) }, [preview])

  function describe(err: unknown): string {
    const name = (err as DOMException)?.name ?? 'Error'
    switch (name) {
      case 'NotAllowedError':
      case 'PermissionDeniedError':
        return t('camera.denied')
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return t('camera.notFound')
      case 'NotReadableError':
      case 'TrackStartError':
        return t('camera.busy')
      case 'SecurityError':
        return t('camera.insecure')
      default:
        return `${t('camera.failed')} (${name})`
    }
  }

  async function startCamera() {
    setCameraError(null)
    setStarting(true)
    try {
      let media: MediaStream
      try {
        media = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } },
          audio: false,
        })
      } catch (err) {
        // A laptop with only a front webcam, or a driver that rejects the size
        // hint, fails the preferred constraints. Retry with the plain request
        // before telling the user the camera does not work.
        if ((err as DOMException)?.name === 'OverconstrainedError'
            || (err as DOMException)?.name === 'NotFoundError') {
          media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        } else {
          throw err
        }
      }
      setStream(media)
    } catch (err) {
      setCameraError(describe(err))
    } finally {
      setStarting(false)
    }
  }

  function shoot() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      canvas.width = 0
      canvas.height = 0
      if (!blob) return
      stopCamera()
      void accept(blob, 'capture.jpg')
    }, 'image/jpeg', 0.92)
  }

  /** Shrink before anything else touches it, then show the preview. */
  async function accept(blob: Blob, filename: string) {
    setPreparing(true)
    try {
      const result = await prepareForUpload(blob, filename)
      if (preview) URL.revokeObjectURL(preview.url)
      setPreview({
        url: URL.createObjectURL(result.blob),
        blob: result.blob,
        name: result.filename,
      })
      setPrepared(result)
      setCropping(true)
    } finally {
      setPreparing(false)
    }
  }

  /** Re-run preparation on the cropped region so the upload stays small. */
  async function applyCrop(blob: Blob) {
    setCropping(false)
    await accept(blob, preview?.name ?? 'capture.jpg')
    setCropping(false)
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    stopCamera()
    void accept(file, file.name)
  }

  function retake() {
    if (preview) URL.revokeObjectURL(preview.url)
    setPreview(null)
    setPrepared(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div>
      <div className="capture-frame">
        {live && <><video ref={videoRef} playsInline muted /><span className="guide" /></>}
        {!live && preview && !cropping && (
          <img src={preview.url} alt="capture preview" />
        )}
        {!live && preview && cropping && (
          <p className="placeholder">{t('crop.title')}</p>
        )}
        {!live && !preview && (
          <p className="placeholder">
            {t('new.guidance.framing')}<br />{t('new.guidance.light')}
          </p>
        )}
      </div>

      {disabled && (
        <div className="caveat" role="note" style={{ marginTop: '.6rem' }}>
          {t('capture.blocked')}
        </div>
      )}

      {preparing && <p className="hint">{t('capture.preparing')}</p>}
      {prepared?.finalDimensions && (
        <p className="hint">
          {t('capture.prepared')}: {prepared.originalDimensions} →{' '}
          {prepared.finalDimensions},{' '}
          {Math.round(prepared.originalBytes / 1024)} KB →{' '}
          {Math.round(prepared.blob.size / 1024)} KB
        </p>
      )}

      {preview && cropping && (
        <CropBox
          src={preview.url}
          onCancel={() => setCropping(false)}
          onCropped={(blob) => void applyCrop(blob)}
        />
      )}

      {!supported && (
        <p className="hint" role="note">{t('camera.insecure')}</p>
      )}
      {cameraError && (
        <div className="error-panel" role="alert" style={{ marginTop: '.6rem' }}>
          <p>{cameraError}</p>
          <p className="hint">{t('camera.uploadInstead')}</p>
          <div className="actions">
            <button type="button" onClick={() => captureRef.current?.click()}>
              {t('new.capture.deviceCamera')}
            </button>
          </div>
        </div>
      )}

      <div className="actions">
        {!live && !preview && (
          <>
            <button
              type="button"
              onClick={startCamera}
              disabled={disabled || starting || !supported}
            >
              {starting ? t('camera.starting') : t('new.capture.camera')}
            </button>
            {/* Opens the phone's own camera app. It needs no getUserMedia
                permission and no secure context, so it keeps working when the
                in-app camera is blocked -- which is the common case. */}
            <button
              type="button"
              className="secondary"
              onClick={() => captureRef.current?.click()}
              disabled={disabled}
            >
              {t('new.capture.deviceCamera')}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
            >
              {t('new.capture.upload')}
            </button>
          </>
        )}
        {live && (
          <>
            <button type="button" onClick={shoot}>{t('new.capture.shoot')}</button>
            <button type="button" className="ghost" onClick={stopCamera}>
              {t('new.capture.stop')}
            </button>
          </>
        )}
        {preview && !cropping && (
          <>
            <button
              type="button"
              onClick={() => onAnalyze(preview.blob, preview.name)}
              disabled={busy || disabled || preparing}
            >
              {busy ? t('new.capture.analysing') : t('new.capture.analyze')}
            </button>
            <button type="button" className="secondary"
                    onClick={() => setCropping(true)} disabled={busy}>
              {t('crop.reopen')}
            </button>
            <button type="button" className="ghost" onClick={retake} disabled={busy}>
              {t('new.capture.retake')}
            </button>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={onFile}
          hidden
        />
        {/* `capture` makes a phone hand this straight to its camera app.
            Desktop browsers ignore the attribute and show a file picker. */}
        <input
          ref={captureRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={onFile}
          hidden
        />
      </div>

      <CameraDiagnostics />

      <div style={{ marginTop: '.9rem' }}>
        <h3>{t('new.guidance.title')}</h3>
        <ul className="plain">
          <li>{t('new.guidance.distance')}</li>
          <li>{t('new.guidance.framing')}</li>
          <li>{t('new.guidance.light')}</li>
          <li>{t('new.guidance.background')}</li>
          <li>{t('new.guidance.scale')}</li>
        </ul>
      </div>
    </div>
  )
}
