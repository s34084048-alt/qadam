/**
 * Prepare a capture for upload.
 *
 * A phone photograph is 12 megapixels or more. Held as a full-resolution PNG
 * it is tens of megabytes of canvas plus tens of megabytes of blob, and a
 * mid-range phone under that pressure discards the tab — which the user sees
 * as the app "jumping back to the start" in the middle of an analysis, losing
 * the capture with it.
 *
 * Nothing in the analysis needs that resolution. The quality gate measures
 * focus at a normalised 480 px short side, subject segmentation works at 720 px,
 * and the exported PDF caps the image at 1800 px. 2000 px on the longest side
 * is comfortably above all of them.
 */

export const MAX_UPLOAD_DIMENSION = 2000
export const JPEG_QUALITY = 0.92

export interface Prepared {
  blob: Blob
  filename: string
  originalBytes: number
  originalDimensions: string | null
  finalDimensions: string | null
  resized: boolean
}

async function decode(blob: Blob): Promise<ImageBitmap | HTMLImageElement> {
  if ('createImageBitmap' in window) {
    return createImageBitmap(blob)
  }
  // Safari fallback.
  const url = URL.createObjectURL(blob)
  try {
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('could not decode image'))
      img.src = url
    })
    return img
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function prepareForUpload(
  input: Blob, filename = 'capture.jpg',
): Promise<Prepared> {
  const originalBytes = input.size
  let source: ImageBitmap | HTMLImageElement
  try {
    source = await decode(input)
  } catch {
    // If it cannot be decoded here the server will reject it with a clear
    // message; do not swallow the capture.
    return {
      blob: input, filename, originalBytes,
      originalDimensions: null, finalDimensions: null, resized: false,
    }
  }

  const width = 'width' in source ? source.width : 0
  const height = 'height' in source ? source.height : 0
  const longest = Math.max(width, height)
  const scale = longest > MAX_UPLOAD_DIMENSION
    ? MAX_UPLOAD_DIMENSION / longest : 1

  const targetW = Math.round(width * scale)
  const targetH = Math.round(height * scale)

  const canvas = document.createElement('canvas')
  canvas.width = targetW
  canvas.height = targetH
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return {
      blob: input, filename, originalBytes,
      originalDimensions: `${width}×${height}`, finalDimensions: null,
      resized: false,
    }
  }
  ctx.drawImage(source as CanvasImageSource, 0, 0, targetW, targetH)
  if ('close' in source) source.close()

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))

  // Release the backing store promptly rather than waiting for collection.
  canvas.width = 0
  canvas.height = 0

  if (!blob) {
    return {
      blob: input, filename, originalBytes,
      originalDimensions: `${width}×${height}`, finalDimensions: null,
      resized: false,
    }
  }
  return {
    blob,
    filename: filename.replace(/\.(png|webp|jpeg|jpg)$/i, '') + '.jpg',
    originalBytes,
    originalDimensions: `${width}×${height}`,
    finalDimensions: `${targetW}×${targetH}`,
    resized: scale < 1 || input.type !== 'image/jpeg',
  }
}
