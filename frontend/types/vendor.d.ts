declare global {
  interface Window {
    ym?: (counterId: number, action: string, goalName: string) => void
  }
}

declare module 'pdfmake/build/pdfmake' {
  const pdfMake: {
    vfs: Record<string, string>
    createPdf(docDefinition: Record<string, unknown>): {
      getBlob(callback: (blob: Blob) => void): void
      download(defaultFileName?: string): void
    }
  }
  export default pdfMake
}

declare module 'pdfmake/build/vfs_fonts' {
  const pdfFontsVfs: Record<string, string>
  export default pdfFontsVfs
  export const pdfMake: { vfs: Record<string, string> }
}

declare module 'qrcode' {
  const QRCode: {
    toDataURL(
      text: string | Array<{ data: string; mode: string }>,
      options?: {
        width?: number
        margin?: number
        errorCorrectionLevel?: string
        [key: string]: unknown
      }
    ): Promise<string>
    [key: string]: unknown
  }
  export default QRCode
}
