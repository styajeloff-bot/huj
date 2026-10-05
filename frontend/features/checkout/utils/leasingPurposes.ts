export interface LeasingPurposeSelection { leasing_purpose?: string | null; leasing_purposes?: string[] | null; leasing_purpose_comment?: string | null }
export const selectedLeasingPurposes = (item: LeasingPurposeSelection): string[] => item.leasing_purposes == null ? (item.leasing_purpose ? [item.leasing_purpose] : []) : [...item.leasing_purposes]
export const persistedLeasingPurposes = (item: LeasingPurposeSelection): string[] => [...new Set(selectedLeasingPurposes(item).map(value => value === 'other' ? (item.leasing_purpose_comment || '').trim() : value.trim()).filter(Boolean))]
export const updateLeasingPurposes = (item: LeasingPurposeSelection, values: unknown): void => {
  item.leasing_purposes = Array.isArray(values) ? values.filter((value): value is string => typeof value === 'string') : []
  item.leasing_purpose = item.leasing_purposes[0] ?? null
}
