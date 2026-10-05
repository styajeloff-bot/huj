/**
 * Конвертирует Blob изображения в data URL, пригодный для pdfmake.
 * pdfmake поддерживает только JPEG и PNG; WebP и другие форматы конвертируются в PNG через canvas.
 */
export async function imageBlobToPdfSafeDataUrl(blob: Blob): Promise<string | null> {
  if (typeof document === 'undefined' || typeof Image === 'undefined') return null
  const mime = (blob.type || '').toLowerCase()
  if (mime === 'image/jpeg' || mime === 'image/png') {
    return await new Promise<string | null>((resolve) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(typeof reader.result === 'string' ? reader.result : null)
      reader.onerror = () => resolve(null)
      reader.readAsDataURL(blob)
    })
  }
  // WebP и другие форматы — конвертация в PNG через canvas
  return new Promise<string | null>((resolve) => {
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = img.naturalWidth
        canvas.height = img.naturalHeight
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          URL.revokeObjectURL(url)
          resolve(null)
          return
        }
        ctx.drawImage(img, 0, 0)
        resolve(canvas.toDataURL('image/png'))
      } finally {
        URL.revokeObjectURL(url)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(null)
    }
    img.src = url
  })
}
