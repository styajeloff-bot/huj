const COLOR_MAP: Record<string, string> = {
  'белый': '#FFFFFF',
  'черный': '#000000',
  'чёрный': '#000000',
  'серый': '#808080',
  'серебристый': '#C0C0C0',
  'красный': '#FF0000',
  'синий': '#0000FF',
  'зеленый': '#008000',
  'зелёный': '#008000',
  'желтый': '#FFFF00',
  'жёлтый': '#FFFF00',
  'оранжевый': '#FFA500',
  'коричневый': '#A52A2A',
  'бордовый': '#800000',
  'фиолетовый': '#800080',
  'розовый': '#FFC0CB',
  'бежевый': '#F5F5DC',
  'золотистый': '#FFD700',
}

export const getColorCode = (colorName: string | null | undefined): string | null => {
  const normalized = colorName?.trim().toLowerCase()
  if (!normalized) return null
  return COLOR_MAP[normalized] ?? null
}
