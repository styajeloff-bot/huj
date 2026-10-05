export type PhoneMaskState = {
  value: string
  cursor: number
}

const phoneDigits = (value: string): string => {
  let digits = value.replace(/\D/g, '')
  if (digits.startsWith('8')) {
    digits = `7${digits.slice(1)}`
  }
  if (!digits.startsWith('7')) {
    digits = `7${digits}`
  }
  return digits.slice(0, 11)
}

export const formatRussianPhone = (value: string): string => {
  const digits = phoneDigits(value)
  let formatted = '+7'

  if (digits.length > 1) {
    formatted += ` (${digits.slice(1, 4)}`
  }
  if (digits.length >= 4) {
    formatted += `) ${digits.slice(4, 7)}`
  }
  if (digits.length >= 7) {
    formatted += `-${digits.slice(7, 9)}`
  }
  if (digits.length >= 9) {
    formatted += `-${digits.slice(9, 11)}`
  }

  return formatted
}

const cursorAfterDigits = (value: string, digitCount: number): number => {
  if (digitCount <= 1) return 2

  let seenDigits = 0
  for (let index = 0; index < value.length; index += 1) {
    if (/\d/.test(value[index])) {
      seenDigits += 1
      if (seenDigits === digitCount) return index + 1
    }
  }

  return value.length
}

export const deletePreviousPhoneDigit = ({ value, cursor }: PhoneMaskState): PhoneMaskState => {
  const safeCursor = Math.max(2, Math.min(cursor, value.length))
  let digitIndex = safeCursor - 1

  while (digitIndex >= 2 && !/\d/.test(value[digitIndex])) {
    digitIndex -= 1
  }

  if (digitIndex < 2) {
    return { value: '+7', cursor: 2 }
  }

  const digitsBeforeRemoved = value.slice(0, digitIndex).replace(/\D/g, '').length
  const nextValue = formatRussianPhone(`${value.slice(0, digitIndex)}${value.slice(digitIndex + 1)}`)

  return {
    value: nextValue,
    cursor: cursorAfterDigits(nextValue, digitsBeforeRemoved),
  }
}
