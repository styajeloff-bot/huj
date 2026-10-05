<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Требования к документам
      </h2>
      <p class="text-sm text-gray-600">
        Настройте, какие документы обязательны для ваших заявок
      </p>
    </div>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем требования...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button @click="fetchRequirements" class="btn-primary">
        Попробовать снова
      </button>
    </div>

    <div v-else class="space-y-6">
      <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Типы документов</h3>
          <p class="text-sm text-gray-600 mt-1">
            Настройте требования для каждого типа документов
          </p>
        </div>

        <div class="divide-y divide-gray-200">
          <div v-for="(requirement, index) in requirements" :key="requirement.id" 
               class="p-6 hover:bg-gray-50">
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="flex items-center space-x-4 mb-3">
                  <div class="flex-1">
                    <label class="block text-sm font-medium text-gray-700 mb-1">
                      Название документа
                    </label>
                    <input
                      v-model="requirement.display_name"
                      type="text"
                      class="input-field"
                      placeholder="Название документа"
                    >
                  </div>
                  <div class="w-32">
                    <label class="block text-sm font-medium text-gray-700 mb-1">
                      Порядок
                    </label>
                    <input
                      v-model.number="requirement.sort_order"
                      type="number"
                      class="input-field"
                      min="0"
                    >
                  </div>
                </div>

                <div class="mb-3">
                  <label class="block text-sm font-medium text-gray-700 mb-1">
                    Описание
                  </label>
                  <textarea
                    v-model="requirement.description"
                    rows="2"
                    class="input-field"
                    placeholder="Описание требований к документу"
                  ></textarea>
                </div>

                <div class="flex items-center space-x-6">
                  <label class="flex items-center">
                    <input
                      v-model="requirement.is_required"
                      type="checkbox"
                      class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    >
                    <span class="ml-2 text-sm text-gray-700">Обязательный</span>
                  </label>

                  <label class="flex items-center">
                    <input
                      v-model="requirement.is_mandatory"
                      type="checkbox"
                      class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    >
                    <span class="ml-2 text-sm text-gray-700">Строго обязательный</span>
                  </label>

                  <label class="flex items-center">
                    <input
                      v-model="requirement.auto_approve"
                      type="checkbox"
                      class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    >
                    <span class="ml-2 text-sm text-gray-700">Автоматическое одобрение</span>
                  </label>
                </div>

                <div class="mt-2 text-xs text-gray-500">
                  <div><strong>Обязательный:</strong> документ запрашивается у клиента</div>
                  <div><strong>Строго обязательный:</strong> без этого документа заявка не может быть одобрена</div>
                  <div><strong>Автоматическое одобрение:</strong> документ одобряется автоматически при загрузке</div>
                </div>
              </div>

              <div class="ml-4 flex-shrink-0">
                <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                      :class="requirement.is_required ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'">
                  {{ requirement.is_required ? 'Активен' : 'Неактивен' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="px-6 py-4 bg-gray-50 border-t border-gray-200">
          <div class="flex justify-end space-x-3">
            <button
              @click="resetChanges"
              class="btn-secondary"
              :disabled="saving"
            >
              Сбросить
            </button>
            <button
              @click="saveRequirements"
              class="btn-primary"
              :disabled="saving"
            >
              {{ saving ? 'Сохранение...' : 'Сохранить изменения' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Информационная панель -->
      <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg class="h-5 w-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-blue-800">
              Информация о настройках
            </h3>
            <div class="mt-2 text-sm text-blue-700">
              <ul class="list-disc list-inside space-y-1">
                <li>Изменения применяются только к новым заявкам</li>
                <li>Существующие заявки сохраняют свои требования к документам</li>
                <li>Порядок определяет последовательность отображения документов клиенту</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DocumentRequirementEditable } from '~/features/leasing/types'

interface RequirementsResponse {
  requirements: DocumentRequirementEditable[]
}

const config = useRuntimeConfig()

const requirements = ref<DocumentRequirementEditable[]>([])
const originalRequirements = ref<DocumentRequirementEditable[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const fetchRequirements = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await $fetch<RequirementsResponse>('/api/v1/leasing/document-requirements', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    requirements.value = response.requirements.map((req: DocumentRequirementEditable) => ({ ...req }))
    originalRequirements.value = response.requirements.map((req: DocumentRequirementEditable) => ({ ...req }))
  } catch (err: unknown) {
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке требований к документам'
  } finally {
    loading.value = false
  }
}

const saveRequirements = async () => {
  saving.value = true
  error.value = ''

  try {
    await $fetch('/api/v1/leasing/document-requirements', {
      method: 'PUT',
      body: { requirements: requirements.value },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    // Обновляем оригинальные данные
    originalRequirements.value = requirements.value.map((req: DocumentRequirementEditable) => ({ ...req }))

    // Показываем уведомление об успехе
    const { showToast } = useToast()
    showToast.success('Требования к документам обновлены')
  } catch (err: unknown) {
    const logger = useLogger()
    logger.error('Error saving document requirements', err)
    const e = err as { data?: { error?: string }; message?: string }
    error.value = e.data?.error || e.message || 'Ошибка при сохранении требований'
  } finally {
    saving.value = false
  }
}

const resetChanges = () => {
  requirements.value = originalRequirements.value.map((req: DocumentRequirementEditable) => ({ ...req }))
}

onMounted(() => {
  fetchRequirements()
})
</script>
