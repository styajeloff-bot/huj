import type { UUID } from '~/types/ids'
import type { CatalogCorrectionApi } from './api'
import type { CatalogModel, CatalogModification } from './types'

export const useDependentCatalogDirectories = (api: CatalogCorrectionApi) => {
  const models = ref<CatalogModel[]>([])
  const modifications = ref<CatalogModification[]>([])
  const modelsLoading = ref(false)
  const modificationsLoading = ref(false)
  let modelSequence = 0
  let modificationSequence = 0
  let modelController: AbortController | null = null
  let modificationController: AbortController | null = null

  const clearModels = () => {
    modelController?.abort()
    modelSequence += 1
    models.value = []
  }
  const clearModifications = () => {
    modificationController?.abort()
    modificationSequence += 1
    modifications.value = []
  }
  const loadModels = async (markId: UUID | null) => {
    clearModels()
    clearModifications()
    if (!markId) return
    const sequence = modelSequence
    const controller = new AbortController()
    modelController = controller
    modelsLoading.value = true
    try {
      const items = await api.listAll<CatalogModel>(
        'models',
        { mark_id: markId },
        controller.signal,
      )
      if (sequence === modelSequence) models.value = items
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) throw error
    } finally {
      if (sequence === modelSequence) modelsLoading.value = false
    }
  }
  const loadModifications = async (modelId: UUID | null) => {
    clearModifications()
    if (!modelId) return
    const sequence = modificationSequence
    const controller = new AbortController()
    modificationController = controller
    modificationsLoading.value = true
    try {
      const items = await api.listAll<CatalogModification>(
        'modifications',
        { model_id: modelId },
        controller.signal,
      )
      if (sequence === modificationSequence) modifications.value = items
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) throw error
    } finally {
      if (sequence === modificationSequence) modificationsLoading.value = false
    }
  }

  onBeforeUnmount(() => {
    modelController?.abort()
    modificationController?.abort()
  })

  return {
    models,
    modifications,
    modelsLoading,
    modificationsLoading,
    loadModels,
    loadModifications,
    clearModels,
    clearModifications,
  }
}
