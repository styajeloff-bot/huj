import type { UUID } from '~/types/ids'

export type CategoryAttributeGroupKey = UUID | 'ungrouped' | ''
export type CategoryAttributePickerFocus = 'group' | 'search' | 'retry' | null

export interface CategoryAttributePickerState {
  selectedGroupKey: CategoryAttributeGroupKey
  search: string
  selectedIds: UUID[]
  restoreFocusAfterReload: boolean
  requestedFocus: CategoryAttributePickerFocus
}

export const createCategoryAttributePickerState = (): CategoryAttributePickerState => ({
  selectedGroupKey: '',
  search: '',
  selectedIds: [],
  restoreFocusAfterReload: false,
  requestedFocus: null,
})

export const selectCategoryAttributeGroup = (
  state: CategoryAttributePickerState,
  selectedGroupKey: CategoryAttributeGroupKey,
): CategoryAttributePickerState => ({
  ...state,
  selectedGroupKey,
  search: '',
  selectedIds: [],
  requestedFocus: selectedGroupKey ? 'search' : 'group',
})

export const setCategoryAttributeSearch = (
  state: CategoryAttributePickerState,
  search: string,
): CategoryAttributePickerState => ({ ...state, search })

export const toggleCategoryAttribute = (
  state: CategoryAttributePickerState,
  attributeId: UUID,
): CategoryAttributePickerState => ({
  ...state,
  selectedIds: state.selectedIds.includes(attributeId)
    ? state.selectedIds.filter(id => id !== attributeId)
    : [...state.selectedIds, attributeId],
})

export const applyCategoryAttributeSelection = (
  state: CategoryAttributePickerState,
): { state: CategoryAttributePickerState; attributeIds: UUID[] } => ({
  attributeIds: [...state.selectedIds],
  state: {
    ...state,
    selectedGroupKey: '',
    search: '',
    selectedIds: [],
    requestedFocus: 'group',
  },
})

export const beginCategoryAttributeRetry = (
  state: CategoryAttributePickerState,
): CategoryAttributePickerState => ({
  ...state,
  restoreFocusAfterReload: true,
  requestedFocus: null,
})

export const settleCategoryAttributeRetry = (
  state: CategoryAttributePickerState,
  errorMessage: string,
): CategoryAttributePickerState => state.restoreFocusAfterReload
  ? {
      ...state,
      restoreFocusAfterReload: false,
      requestedFocus: errorMessage ? 'retry' : 'group',
    }
  : state

export const pruneLinkedCategoryAttributes = (
  state: CategoryAttributePickerState,
  linkedAttributeIds: readonly UUID[],
): CategoryAttributePickerState => {
  const linkedIds = new Set(linkedAttributeIds)
  return {
    ...state,
    selectedIds: state.selectedIds.filter(id => !linkedIds.has(id)),
  }
}
