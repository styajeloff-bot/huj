export default defineEventHandler(async (event) => {
  const document = await useStorage('assets:server').getItemRaw('legal/privacy-policy-2026.pdf')

  if (!document) {
    throw createError({ statusCode: 404, statusMessage: 'Политика ПДн не найдена' })
  }

  setHeader(event, 'Content-Type', 'application/pdf')
  setHeader(event, 'Content-Disposition', 'inline; filename="privacy-policy-2026.pdf"')

  return document
})
