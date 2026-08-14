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

  /** The path that cannot fail: the phone's own camera app.
   *
   *  No getUserMedia, so no permission prompt to deny, no secure-context
   *  requirement, no device enumeration, no driver constraints, no autoplay
   *  policy and no black-preview race. Every failure below ends here. */
  const useDeviceCamera = useCallback(() => {
    setCameraError(null)
    captureRef.current?.click()
  }, [])

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
      // Do NOT stop at an error message. The live preview is an optional
      // convenience and it has failed for six different reasons across this
      // project's life -- permission, secure context, driver, another app
      // holding the device, autoplay, enumeration. Every one of them is
      // invisible to the person holding the phone, who only knows "the camera
      // does not work". Hand them the camera app instead and say why
      // afterwards, so a failure costs a sentence rather than the visit.
      setCameraError(describe(err))
      useDeviceCamera()
    } finally {
      setStarting(false)
    }
  }

  function shoot() {
    const video = videoRef.current
    // A silent return here is indistinguishable from a dead button, and this
    // is a real state: the stream is attached but the first frame has not
    // arrived, so videoWidth is still 0. It used to do nothing at all.
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraError(t('camera.notReady'))
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      setCameraError(t('camera.failed'))
      useDeviceCamera()
      return
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      canvas.width = 0
      canvas.height = 0
      if (!blob) {
        setCameraError(t('camera.failed'))
        useDeviceCamera()
        return
      }
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

      {/* Not an error panel. By the time this shows, the camera app has
          already been opened — the message explains why the preview is not
          there, it does not block anything. */}
      {cameraError && (
        <p className="hint" role="status" style={{ marginTop: '.6rem' }}>
          {cameraError} {t('camera.fellBack')}
        </p>
      )}

      <div className="actions">
        {!live && !preview && (
          <>
            {/* PRIMARY, and a <label> rather than a button ON PURPOSE.
                A label activates its input NATIVELY — no JavaScript in the
                path at all. The previous version called .click() on an input
                with `hidden`, and several mobile browsers refuse to open a
                picker for a display:none input from a synthetic click: the
                button does nothing, silently, with no error to report. That is
                indistinguishable from "the camera is broken", and it is the
                one failure mode a user cannot work around.
                The input below is offscreen but RENDERED, so activation works
                everywhere, and `disabled` on it makes this label inert. */}
            <label
              className={`as-button${disabled ? ' is-disabled' : ''}`}
              htmlFor="qadam-device-camera"
            >
              {t('new.capture.deviceCamera')}
            </label>
            {/* Offered only where it can actually work. A disabled button that
                says "Use camera" reads as a broken app; its absence reads as a
                app that simply captures a different way. */}
            {supported && (
              <button
                type="button"
                className="secondary"
                onClick={startCamera}
                disabled={disabled || starting}
              >
                {starting ? t('camera.starting') : t('new.capture.camera')}
              </button>
            )}
            <label
              className={`as-button ghost${disabled ? ' is-disabled' : ''}`}
              htmlFor="qadam-upload"
            >
              {t('new.capture.upload')}
            </label>
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
        {/* `offscreen`, never `hidden`. A display:none file input cannot be
            opened by a synthetic click in several mobile browsers, and a
            label cannot activate it either. Rendered-but-invisible works
            everywhere. `disabled` is what makes the labels above inert —
            labels have no disabled attribute of their own. */}
        <input
          id="qadam-upload"
          ref={fileRef}
          className="offscreen"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={onFile}
          disabled={disabled}
        />
        {/* `capture` makes a phone hand this straight to its camera app.
            Desktop browsers ignore the attribute and show a file picker. */}
        <input
          id="qadam-device-camera"
          ref={captureRef}
          className="offscreen"
          type="file"
          accept="image/*"
          capture="environment"
          onChange={onFile}
          disabled={disabled}
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
