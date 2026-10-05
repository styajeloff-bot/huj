export interface DocumentRequestInput {
  display_name: string
  slug: string
}

const CYRILLIC_TRANSLITERATION: Record<string, string> = {
  а: 'a',
  б: 'b',
  в: 'v',
  г: 'g',
  д: 'd',
  е: 'e',
  ё: 'e',
  ж: 'zh',
  з: 'z',
  и: 'i',
  й: 'i',
  к: 'k',
  л: 'l',
  м: 'm',
  н: 'n',
  о: 'o',
  п: 'p',
  р: 'r',
  с: 's',
  т: 't',
  у: 'u',
  ф: 'f',
  х: 'h',
  ц: 'c',
  ч: 'ch',
  ш: 'sh',
  щ: 'shch',
  ъ: '',
  ы: 'y',
  ь: '',
  э: 'e',
  ю: 'yu',
  я: 'ya',
}

export const DOCUMENT_REQUEST_SLUG_MAX_LENGTH = 100

export const slugifyDocumentName = (
  name: string,
  maxLength = DOCUMENT_REQUEST_SLUG_MAX_LENGTH,
): string => {
  const transliterated = Array.from(name.trim().toLowerCase())
    .map(character => CYRILLIC_TRANSLITERATION[character] ?? character)
    .join('')

  return transliterated
    .replace(/[\s\-/\\–—]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, Math.max(0, maxLength))
    .replace(/_+$/g, '')
}

export const buildDocumentRequestInputs = (names: string[]): DocumentRequestInput[] => {
  const usedSlugs = new Set<string>()

  return names.map((name) => {
    const displayName = name.trim()
    const baseSlug = slugifyDocumentName(displayName)
    if (!baseSlug) {
      throw new Error('Название документа должно содержать буквы или цифры')
    }

    let slug = baseSlug
    let duplicateNumber = 2
    while (usedSlugs.has(slug)) {
      const suffix = `_${duplicateNumber}`
      const truncatedBase = baseSlug
        .slice(0, DOCUMENT_REQUEST_SLUG_MAX_LENGTH - suffix.length)
        .replace(/_+$/g, '')
      slug = `${truncatedBase}${suffix}`
      duplicateNumber += 1
    }

    usedSlugs.add(slug)
    return { display_name: displayName, slug }
  })
}
