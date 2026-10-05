/** Date-time controls display browser-local time; the API always receives an instant. */
export function toDeadlineInput(value: string | null | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function fromDeadlineInput(value: string): string | null {
  if (!value) return null
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('Укажите дату и время окончания')
  const date = new Date(value)
  if (!Number.isFinite(date.getTime()) || toDeadlineInput(date.toISOString()) !== value) {
    throw new Error('Такое время не существует в вашем часовом поясе')
  }
  return date.toISOString()
}

export function formatExchangeDeadline(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  }).format(new Date(value))
}
