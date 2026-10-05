export const getMonthWord = (months: number): string => {
  if (months % 10 === 1 && months % 100 !== 11) return 'месяц'
  if ([2, 3, 4].includes(months % 10) && ![12, 13, 14].includes(months % 100)) return 'месяца'
  return 'месяцев'
}

/**
 * Канонический формат номера лизинговой заявки: `{ИНН}-{ДДММ}-{N}`.
 * Никогда не показываем UUID пользователю — если `display_number` не пришёл,
 * возвращаем `—`. UUID-фоллбэк запрещён по продуктовому требованию.
 */
export interface ApplicationNumberSource {
  display_number?: string | null
}

export const formatApplicationNumber = (
  source: ApplicationNumberSource | null | undefined,
  placeholder = '—',
): string => {
  const value = source?.display_number
  if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  return placeholder
}
