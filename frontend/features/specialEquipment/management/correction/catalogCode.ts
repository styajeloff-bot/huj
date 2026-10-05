import type {
  CatalogAttributeOption,
  CatalogEntity,
} from './types'

const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh',
  з: 'z', и: 'i', й: 'i', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o',
  п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c',
  ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu',
  я: 'ya',
}

/** Initial admin suggestion only; the backend remains the source of uniqueness. */
export const suggestCatalogCode = (name: string): string => {
  const transliterated = [...name.trim().toLocaleLowerCase('ru-RU')]
    .map(character => CYRILLIC_TO_LATIN[character] ?? character)
    .join('')
  return transliterated
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 80)
    .toUpperCase()
}

interface CatalogCodeSyncInput {
  mode: 'create' | 'edit'
  currentName: string
  currentCode: string
  nextName: string
  codeManuallyEdited: boolean
}

export const syncSuggestedCatalogCode = ({
  mode,
  currentName,
  currentCode,
  nextName,
  codeManuallyEdited,
}: CatalogCodeSyncInput): string => {
  if (mode === 'edit' || codeManuallyEdited) return currentCode
  return currentCode === suggestCatalogCode(currentName)
    ? suggestCatalogCode(nextName)
    : currentCode
}

export const patchCatalogAttributeOption = <T extends CatalogAttributeOption>(
  option: T,
  field: 'name' | 'code',
  value: string,
): T & { codeManuallyEdited: boolean } => {
  if (field === 'code') {
    return {
      ...option,
      code: value,
      codeManuallyEdited: true,
    }
  }

  return {
    ...option,
    name: value,
    code: syncSuggestedCatalogCode({
      mode: option.id === undefined ? 'create' : 'edit',
      currentName: option.name,
      currentCode: option.code,
      nextName: value,
      codeManuallyEdited: option.codeManuallyEdited === true,
    }),
    codeManuallyEdited: option.codeManuallyEdited === true,
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const hasNonEmptyText = (value: unknown): boolean =>
  typeof value === 'string' && value.trim().length > 0

type CatalogAttributeOptionRequiredField = 'code' | 'name'

export const isCatalogAttributeOptionFieldInvalid = (
  option: unknown,
  field: CatalogAttributeOptionRequiredField,
): boolean =>
  !isRecord(option) || !hasNonEmptyText(option[field])

export const isCatalogAttributeOptionInvalid = (option: unknown): boolean =>
  isCatalogAttributeOptionFieldInvalid(option, 'code')
  || isCatalogAttributeOptionFieldInvalid(option, 'name')

interface CatalogAttributeOptionsSaveValidationInput {
  entity: CatalogEntity
  dataType: unknown
  options: unknown
}

export const isCatalogAttributeOptionsSaveInvalid = ({
  entity,
  dataType,
  options,
}: CatalogAttributeOptionsSaveValidationInput): boolean => {
  if (entity !== 'attributes' || dataType !== 'select') return false
  if (!Array.isArray(options)) return true
  return options.some(isCatalogAttributeOptionInvalid)
}
