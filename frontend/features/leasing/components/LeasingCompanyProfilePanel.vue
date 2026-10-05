<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Мой профиль
      </h2>
      <button @click="toggleEditMode" class="btn-primary">
        {{ editMode ? 'Отменить' : 'Редактировать' }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем профиль...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button @click="fetchProfile" class="btn-primary">
        Попробовать снова
      </button>
    </div>

    <div v-else class="space-y-6">
      <UserCompaniesSection />

      <!-- Основная информация -->
      <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Основная информация</h3>
        </div>

        <form @submit.prevent="saveProfile" class="p-6 space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Полное имя
              </label>
              <input
                v-model="profileForm.name"
                type="text"
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Email
              </label>
              <input
                v-model="profileForm.email"
                type="email"
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Телефон
              </label>
              <input
                v-model="profileForm.phone"
                type="tel"
                disabled
                class="input-field bg-gray-50"
              >
            </div>
            <div v-if="authStore.userCompany">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Компания
              </label>
              <input
                :value="authStore.userCompany"
                type="text"
                disabled
                class="input-field bg-gray-50"
              >
            </div>
          </div>

          <div v-if="editMode" class="flex justify-end space-x-3">
            <button
              type="button"
              @click="editMode = false"
              class="btn-secondary"
            >
              Отмена
            </button>
            <button
              type="submit"
              :disabled="saving"
              class="btn-primary"
            >
              <div v-if="saving" class="flex items-center">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Сохранение...
              </div>
              <span v-else>Сохранить</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import UserCompaniesSection from '~/components/ui/UserCompaniesSection.vue'
import { useRuntimeConfig } from '#app'
import { useLogger } from '~/composables/useLogger'
import { useToast } from '~/composables/useToast'

const config = useRuntimeConfig()
const authStore = useAuthStore()
const logger = useLogger()
const showToast = useToast()

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const editMode = ref(false)

const profileForm = ref({
  name: '',
  email: '',
  phone: '',
})

const fetchProfile = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await $fetch<{
      id: number
      name?: string | null
      email?: string | null
      phone?: string | null
    }>('/api/v1/users/me', {
      baseURL: config.public.apiBase,
      credentials: 'include',
    })

    profileForm.value.name = response.name || ''
    profileForm.value.email = response.email || ''
    profileForm.value.phone = response.phone || ''
  } catch (err: unknown) {
    logger.error('Error fetching leasing company profile', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке профиля'
  } finally {
    loading.value = false
  }
}

const saveProfile = async () => {
  saving.value = true

  try {
    const body: Record<string, unknown> = {}
    const coerce = (value: unknown) => (value === '' ? null : value)

    if (profileForm.value.name !== undefined) {
      body.name = coerce(profileForm.value.name)
    }
    if (profileForm.value.email !== undefined) {
      body.email = coerce(profileForm.value.email)
    }

    await $fetch('/api/v1/users/me', {
      method: 'PATCH',
      body,
      baseURL: config.public.apiBase,
      credentials: 'include',
    })

    showToast.success('Профиль обновлен')
    editMode.value = false
    await fetchProfile()
  } catch (err: unknown) {
    logger.error('Error saving leasing company profile', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при сохранении профиля')
  } finally {
    saving.value = false
  }
}

const toggleEditMode = () => {
  editMode.value = !editMode.value
}

onMounted(() => {
  fetchProfile()
})
</script>
