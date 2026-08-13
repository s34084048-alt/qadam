import { useCallback, useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'

interface Props {
  src: string
  onCancel: () => void
  onCropped: (blob: Blob) => void
}

interface Rect { x: number; y: number; w: number; h: number }

/**
 * Drag-to-crop before analysis.
 *
 * This is not cosmetic. Every measurement in the pipeline is made INSIDE the
 * segmented subject and expressed as a percentage of it, so what else is in
 * frame changes the numbers: background that leaks into the mask shifts the
 * skin median that every threshold is relative to, and a lesion that occupies
 * 4% of a wide shot occupies 30% of a tight one. Cropping to the area actually
 * being assessed is the single most effective thing a user can do to make the
 * result mean something.
 */
export function CropBox({ src, onCancel, onCropped }: Props) {
  const { t } = useI18n()
  const imgRef = useRef<HTMLImageElement | null>(null)
  const boxRef = useRef<HTMLDivElement | null>(null)
  const [rect, setRect] = useState<Rect | null>(null)
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null)
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toLocal = useCallback((event: React.PointerEvent) => {
    const bounds = boxRef.current?.getBoundingClientRect()
    if (!bounds) return { x: 0, y: 0 }
    return {
      x: Math.min(Math.max(event.clientX - bounds.left, 0), bounds.width),
      y: Math.min(Math.max(event.clientY - bounds.top, 0), bounds.height),
    }
  }, [])

  function onDown(event: React.PointerEvent) {
    ;(event.target as Element).setPointerCapture?.(event.pointerId)
    const point = toLocal(event)
    setDrag(point)
    setRect({ x: point.x, y: point.y, w: 0, h: 0 })
  }

  function onMove(event: React.PointerEvent) {
    if (!drag) return
    const point = toLocal(event)
    setRect({
      x: Math.min(drag.x, point.x),
      y: Math.min(drag.y, point.y),
      w: Math.abs(point.x - drag.x),
      h: Math.abs(point.y - drag.y),
    })
  }

  const MIN_BOX = 24

  function defaultBox(): Rect | null {
    const bounds = boxRef.current?.getBoundingClientRect()
    if (!bounds) return null
    return {
      x: bounds.width * 0.15, y: bounds.height * 0.15,
      w: bounds.width * 0.70, h: bounds.height * 0.70,
    }
  }

  function onUp() {
    setDrag(null)
    // A tap, or a drag that barely moved, leaves a box a few pixels across.
    // Treating that as a selection gives a button that silently does nothing,
    // so fall back to the default frame instead.
    setRect((current) => (
      current && (current.w < MIN_BOX || current.h < MIN_BOX)
        ? defaultBox() : current
    ))
  }

  // Default to a generous centre box so the control is usable without a drag.
  useEffect(() => {
    const bounds = boxRef.current?.getBoundingClientRect()
    if (!bounds || rect || !natural) return
    setRect({
      x: bounds.width * 0.15, y: bounds.height * 0.15,
      w: bounds.width * 0.70, h: bounds.height * 0.70,
    })
  }, [natural, rect])

  async function apply() {
    const image = imgRef.current
    const bounds = boxRef.current?.getBoundingClientRect()
    if (!image || !bounds || !rect || rect.w < MIN_BOX || rect.h < MIN_BOX) return

    // The displayed image is letterboxed inside the box by object-fit:contain,
    // so map through the rendered geometry rather than the element's own size.
    const scale = Math.min(bounds.width / image.naturalWidth,
                           bounds.height / image.naturalHeight)
    const shownW = image.naturalWidth * scale
    const shownH = image.naturalHeight * scale
    const offsetX = (bounds.width - shownW) / 2
    const offsetY = (bounds.height - shownH) / 2

    const sx = Math.max(0, (rect.x - offsetX) / scale)
    const sy = Math.max(0, (rect.y - offsetY) / scale)
    const sw = Math.min(image.naturalWidth - sx, rect.w / scale)
    const sh = Math.min(image.naturalHeight - sy, rect.h / scale)
    if (sw < 16 || sh < 16) {
      setError(t('crop.tooSmall'))
      return
    }

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(sw)
    canvas.height = Math.round(sh)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(image, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.92))
    canvas.width = 0
    canvas.height = 0
    if (blob) {
      onCropped(blob)
    } else {
      setError(t('crop.failed'))
    }
  }

  const tooSmall = Boolean(rect && (rect.w < MIN_BOX || rect.h < MIN_BOX))

  return (
    <div className="crop">
      <p className="hint">{t('crop.help')}</p>
      <div
        ref={boxRef}
        className="crop-stage"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        <img
          ref={imgRef}
          src={src}
          alt={t('crop.title')}
          draggable={false}
          onLoad={(e) => setNatural({
            w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight,
          })}
        />
        {rect && (
          <>
            <div className="crop-shade" style={{
              clipPath: `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0,
                ${rect.x}px ${rect.y}px,
                ${rect.x}px ${rect.y + rect.h}px,
                ${rect.x + rect.w}px ${rect.y + rect.h}px,
                ${rect.x + rect.w}px ${rect.y}px,
                ${rect.x}px ${rect.y}px)`,
            }} />
            <div className="crop-rect" style={{
              left: rect.x, top: rect.y, width: rect.w, height: rect.h,
            }} />
          </>
        )}
      </div>

      {error && <p className="hint" role="alert">{error}</p>}
      {tooSmall && <p className="hint">{t('crop.tooSmall')}</p>}

      <div className="actions">
        <button type="button" onClick={apply} disabled={tooSmall}>
          {t('crop.apply')}
        </button>
        <button type="button" className="ghost" onClick={onCancel}>
          {t('crop.skip')}
        </button>
      </div>
      <p className="hint">{t('crop.why')}</p>
    </div>
  )
}
