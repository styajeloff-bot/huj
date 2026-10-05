export default defineEventHandler(async (event) => {
  const document = await useStorage('assets:server').getItemRaw('legal/terms-of-service-2026.pdf')

  if (!document) {
    throw createError({ statusCode: 404, statusMessage: 'Пользовательское соглашение не найдено' })
  }

  setHeader(event, 'Content-Type', 'application/pdf')
  setHeader(event, 'Content-Disposition', 'inline; filename="terms-of-service-2026.pdf"')

  return document
})
