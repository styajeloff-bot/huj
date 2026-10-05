const HEX_COLOR = /^#[0-9A-F]{6}$/

export const normalizeStorefrontHex = (value: string): string => value.trim().toUpperCase()

export const isStorefrontHexColor = (value: string): boolean => (
  HEX_COLOR.test(normalizeStorefrontHex(value))
)

const parseStorefrontHex = (value: string): [number, number, number] => {
  const normalized = normalizeStorefrontHex(value)
  return [
    Number.parseInt(normalized.slice(1, 3), 16),
    Number.parseInt(normalized.slice(3, 5), 16),
    Number.parseInt(normalized.slice(5, 7), 16),
  ]
}

const toStorefrontHex = (channels: [number, number, number]): string => `#${channels
  .map(channel => Math.round(channel).toString(16).padStart(2, '0'))
  .join('')}`.toUpperCase()

const relativeLuminance = (value: string): number => {
  const [red, green, blue] = parseStorefrontHex(value).map(channel => {
    const normalized = channel / 255
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!
}

export const storefrontContrastRatio = (first: string, second: string): number => {
  const firstLuminance = relativeLuminance(first)
  const secondLuminance = relativeLuminance(second)
  const lighter = Math.max(firstLuminance, secondLuminance)
  const darker = Math.min(firstLuminance, secondLuminance)
  return (lighter + 0.05) / (darker + 0.05)
}

export const mixStorefrontColors = (
  foreground: string,
  background: string,
  foregroundRatio: number,
): string => {
  const foregroundChannels = parseStorefrontHex(foreground)
  const backgroundChannels = parseStorefrontHex(background)
  return toStorefrontHex(foregroundChannels.map((channel, index) => (
    channel * foregroundRatio + backgroundChannels[index]! * (1 - foregroundRatio)
  )) as [number, number, number])
}

export const storefrontPrimaryForeground = (primary: string): '#000000' | '#FFFFFF' => (
  storefrontContrastRatio(primary, '#000000') >= storefrontContrastRatio(primary, '#FFFFFF')
    ? '#000000'
    : '#FFFFFF'
)
