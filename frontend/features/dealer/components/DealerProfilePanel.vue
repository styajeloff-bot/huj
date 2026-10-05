<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Профиль дилера
      </h2>
      <button @click="editMode = !editMode" class="btn-primary">
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
                Название дилерского центра
              </label>
              <input
                v-model="profileForm.dealership_name"
                type="text"
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Контактное лицо
              </label>
              <input
                v-model="profileForm.contact_person"
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
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                ИНН
              </label>
              <input
                v-model="profileForm.inn"
                type="text"
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">
                КПП
              </label>
              <input
                v-model="profileForm.kpp"
                type="text"
                :disabled="!editMode"
                class="input-field"
                :class="{ 'bg-gray-50': !editMode }"
              >
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Адрес
            </label>
            <textarea
              v-model="profileForm.address"
              rows="3"
              :disabled="!editMode"
              class="input-field"
              :class="{ 'bg-gray-50': !editMode }"
            ></textarea>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Описание деятельности
            </label>
            <textarea
              v-model="profileForm.description"
              rows="4"
              :disabled="!editMode"
              class="input-field"
              :class="{ 'bg-gray-50': !editMode }"
              placeholder="Краткое описание вашего дилерского центра, специализации, преимуществ"
            ></textarea>
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

      <!-- Настройки уведомлений -->
      <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Настройки уведомлений</h3>
        </div>
        
        <div class="p-6 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-900">Новые заявки</div>
              <div class="text-sm text-gray-500">Уведомления о новых заявках от клиентов</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.new_applications"
                type="checkbox"
                :disabled="!editMode"
                class="sr-only peer"
              >
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-900">Изменения статуса заявок</div>
              <div class="text-sm text-gray-500">Уведомления об изменении статуса заявок</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.status_changes"
                type="checkbox"
                :disabled="!editMode"
                class="sr-only peer"
              >
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-900">Новые клиенты</div>
              <div class="text-sm text-gray-500">Уведомления о регистрации новых клиентов</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.new_clients"
                type="checkbox"
                :disabled="!editMode"
                class="sr-only peer"
              >
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-900">Еженедельные отчеты</div>
              <div class="text-sm text-gray-500">Получать еженедельные отчеты по продажам</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.weekly_reports"
                type="checkbox"
                :disabled="!editMode"
                class="sr-only peer"
              >
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>
        </div>
      </div>

      <SecurityPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import SecurityPanel from '~/features/auth/components/SecurityPanel.vue'
import UserCompaniesSection from '~/components/ui/UserCompaniesSection.vue'
import type { DealerProfile } from '~/types/features'

const config = useRuntimeConfig()
const { showToast } = useToast()
const logger = useLogger()

const profile = ref<DealerProfile>({})
const loading = ref(true)
const error = ref('')
const editMode = ref(false)
const saving = ref(false)

const profileForm = ref({
  dealership_name: '',
  contact_person: '',
  email: '',
  phone: '',
  inn: '',
  kpp: '',
  address: '',
  description: ''
})

const workingHours = ref([
  { day: 'monday', label: 'Понедельник', enabled: true, open: '09:00', close: '18:00' },
  { day: 'tuesday', label: 'Вторник', enabled: true, open: '09:00', close: '18:00' },
  { day: 'wednesday', label: 'Среда', enabled: true, open: '09:00', close: '18:00' },
  { day: 'thursday', label: 'Четверг', enabled: true, open: '09:00', close: '18:00' },
  { day: 'friday', label: 'Пятница', enabled: true, open: '09:00', close: '18:00' },
  { day: 'saturday', label: 'Суббота', enabled: true, open: '10:00', close: '16:00' },
  { day: 'sunday', label: 'Воскресенье', enabled: false, open: '10:00', close: '16:00' }
])

const notificationSettings = ref({
  new_applications: true,
  status_changes: true,
  new_clients: true,
  weekly_reports: false
})

const fetchProfile = async () => {
  loading.value = true
  error.value = ''

  try {
    // Phase 13 R13a — unified /users/me response.
    // `role_specific.company` replaces the former `profile` top-level block
    // of /dealer/profile.
    type MeRs = {
      company?: Record<string, unknown> | null
    }
    const response = await $fetch<{
      id: number
      phone?: string
      email?: string
      name?: string
      role?: string
      role_specific: MeRs | null
    }>('/api/v1/users/me', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const rs = (response.role_specific || {}) as MeRs
    const company = (rs.company || {}) as Record<string, unknown>
    profile.value = {
      id: response.id,
      email: response.email,
      name: response.name,
      phone: response.phone,
      dealership_name: company.name as string | undefined,
      inn: company.inn as string | undefined,
      kpp: company.kpp as string | undefined,
      address: company.legal_address as string | undefined,
    } as DealerProfile
    // Заполняем форму данными профиля
    const formKeys = Object.keys(profileForm.value) as Array<keyof typeof profileForm.value>
    formKeys.forEach(key => {
      if ((profile.value as Record<string, unknown>)[key] !== undefined) {
        profileForm.value[key] = (profile.value as Record<string, unknown>)[key] as string
      }
    })
  } catch (err: unknown) {
    logger.error('Error fetching dealer profile', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке профиля'
  } finally {
    loading.value = false
  }
}

const saveProfile = async () => {
  saving.value = true

  try {
    // Map the form split: base-user fields (name/email) → top-level,
    // company fields (dealership_name→name, inn, kpp, address→legal_address,
    // phone) → role_specific.company.
    const body = {
      name: profileForm.value.contact_person || null,
      email: profileForm.value.email || null,
      role_specific: {
        company: {
          name: profileForm.value.dealership_name || null,
          inn: profileForm.value.inn || null,
          kpp: profileForm.value.kpp || null,
          legal_address: profileForm.value.address || null,
          phone: profileForm.value.phone || null,
        },
      },
    }

    await $fetch('/api/v1/users/me', {
      method: 'PATCH',
      body,
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    showToast.success('Профиль обновлен')
    editMode.value = false
    await fetchProfile()
  } catch (err: unknown) {
    logger.error('Error saving dealer profile', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при сохранении профиля')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchProfile()
})
</script>
