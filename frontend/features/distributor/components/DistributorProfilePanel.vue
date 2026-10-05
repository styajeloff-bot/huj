<template>
  <div class="space-y-6">
    <!-- Заголовок -->
    <div class="flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Профиль дистрибьютора</h2>
        <p class="text-gray-600 mt-1">Управление профилем и настройками</p>
      </div>
      <div class="flex space-x-3">
        <button
          @click="editMode = !editMode"
          class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
        >
          {{ editMode ? 'Отменить' : 'Редактировать' }}
        </button>
        <button
          v-if="editMode"
          @click="saveProfile"
          :disabled="saving"
          class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
        >
          {{ saving ? 'Сохранение...' : 'Сохранить' }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Основная информация -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Информация о компании -->
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Информация о компании</h3>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Название компании</label>
              <input
                v-model="profile.company_name"
                :disabled="!editMode"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">ИНН</label>
              <input
                v-model="profile.inn"
                :disabled="!editMode"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">КПП</label>
              <input
                v-model="profile.kpp"
                :disabled="!editMode"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">ОГРН</label>
              <input
                v-model="profile.ogrn"
                :disabled="!editMode"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
          </div>
          
          <div class="mt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">Юридический адрес</label>
            <textarea
              v-model="profile.legal_address"
              :disabled="!editMode"
              rows="2"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
            ></textarea>
          </div>
          
          <div class="mt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">Фактический адрес</label>
            <textarea
              v-model="profile.actual_address"
              :disabled="!editMode"
              rows="2"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
            ></textarea>
          </div>
        </div>

        <!-- Контактная информация -->
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Контактная информация</h3>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Телефон</label>
              <input
                v-model="profile.phone"
                :disabled="!editMode"
                type="tel"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Email</label>
              <input
                v-model="profile.email"
                :disabled="!editMode"
                type="email"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Веб-сайт</label>
              <input
                v-model="profile.website"
                :disabled="!editMode"
                type="url"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
            
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Факс</label>
              <input
                v-model="profile.fax"
                :disabled="!editMode"
                type="tel"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50"
              >
            </div>
          </div>
        </div>

        <!-- Настройки уведомлений -->
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Настройки уведомлений</h3>
          
          <div class="space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <div class="font-medium text-gray-900">Email уведомления</div>
                <div class="text-sm text-gray-600">Получать уведомления на email</div>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input
                  v-model="profile.notifications.email"
                  :disabled="!editMode"
                  type="checkbox"
                  class="sr-only peer"
                >
                <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
            
            <div class="flex items-center justify-between">
              <div>
                <div class="font-medium text-gray-900">SMS уведомления</div>
                <div class="text-sm text-gray-600">Получать уведомления по SMS</div>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input
                  v-model="profile.notifications.sms"
                  :disabled="!editMode"
                  type="checkbox"
                  class="sr-only peer"
                >
                <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
            
            <div class="flex items-center justify-between">
              <div>
                <div class="font-medium text-gray-900">Push уведомления</div>
                <div class="text-sm text-gray-600">Получать push уведомления в браузере</div>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input
                  v-model="profile.notifications.push"
                  :disabled="!editMode"
                  type="checkbox"
                  class="sr-only peer"
                >
                <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Боковая панель -->
      <div class="space-y-6">
        <!-- Логотип -->
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Логотип компании</h3>
          
          <div class="text-center">
            <div class="w-32 h-32 mx-auto bg-gray-200 rounded-lg overflow-hidden mb-4">
              <img
                v-if="profile.logo"
                :src="profile.logo"
                :alt="profile.company_name"
                class="w-full h-full object-cover"
              >
              <div v-else class="w-full h-full flex items-center justify-center">
                <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                </svg>
              </div>
            </div>
            
            <input
              ref="logoInput"
              type="file"
              accept="image/*"
              @change="handleLogoUpload"
              class="hidden"
            >
            
            <button
              v-if="editMode"
              @click="logoInput?.click()"
              class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Загрузить логотип
            </button>
          </div>
        </div>

        <!-- Статистика -->
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Статистика</h3>
          
          <div class="space-y-4">
            <div class="flex justify-between">
              <span class="text-gray-600">Дата регистрации:</span>
              <span class="font-medium">{{ formatDate(profile.created_at) }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Последняя активность:</span>
              <span class="font-medium">{{ formatDate(profile.last_activity) }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Всего дилеров:</span>
              <span class="font-medium">{{ profile.stats.total_dealers }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Автомобилей на складе:</span>
              <span class="font-medium">{{ profile.stats.total_vehicles }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Продаж в месяц:</span>
              <span class="font-medium">{{ profile.stats.monthly_sales }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Оборот в месяц:</span>
              <span class="font-medium">{{ formatPrice(profile.stats.monthly_revenue) }}</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Мои компании -->
    <UserCompaniesSection />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import UserCompaniesSection from '~/components/ui/UserCompaniesSection.vue'
import { useFormatPrice } from '@/composables/useFormatPrice'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import type { DistributorProfile, DistributorDocument } from '~/features/distributor/types'
import type { UUID } from '~/types/ids'

const { formatPrice } = useFormatPrice()
const { showToast } = useToast()
const logger = useLogger()

// Реактивные данные
const editMode = ref(false)
const saving = ref(false)
const profile = ref<DistributorProfile>({
  company_name: '',
  inn: '',
  kpp: '',
  ogrn: '',
  legal_address: '',
  actual_address: '',
  phone: '',
  email: '',
  website: '',
  fax: '',
  bank_account: '',
  bik: '',
  bank_name: '',
  logo: null,
  notifications: {
    email: true,
    sms: false,
    push: true
  },
  created_at: null,
  last_activity: null,
  stats: {
    total_dealers: 0,
    total_vehicles: 0,
    monthly_sales: 0,
    monthly_revenue: 0
  },
  verification: {
    documents: false,
    bank: false,
    contacts: false,
    status: 'pending'
  },
  documents: []
})

// Ссылки на элементы
const logoInput = ref<HTMLInputElement | null>(null)
const documentInput = ref<HTMLInputElement | null>(null)

// Методы
const fetchProfile = async () => {
  try {
    // Phase 13 R13a — unified /users/me response.
    // role_specific.company + role_specific.distributor replace the former
    // top-level `profile` block of /distributor/profile.
    type MeRs = {
      company?: Record<string, unknown> | null
      distributor?: Record<string, unknown> | null
    }
    const response = await $fetch<{
      id: UUID
      phone?: string
      email?: string
      name?: string
      role?: string
      role_specific: MeRs | null
    }>('/api/v1/users/me')

    const rs = (response.role_specific || {}) as MeRs
    const company = (rs.company || {}) as Record<string, unknown>
    profile.value = {
      ...profile.value,
      company_name: (company.name as string | undefined) || profile.value.company_name,
      inn: (company.inn as string | undefined) || profile.value.inn,
      kpp: (company.kpp as string | undefined) || profile.value.kpp,
      legal_address: (company.legal_address as string | undefined) || profile.value.legal_address,
      actual_address: (company.actual_address as string | undefined) || profile.value.actual_address,
      phone: (company.phone as string | undefined) || profile.value.phone,
      email: (company.email as string | undefined) || profile.value.email,
      website: (company.website as string | undefined) || profile.value.website,
    }
  } catch (err) {
    logger.error('Error fetching profile:', err)
    showToast.error('Ошибка при загрузке профиля')
  }
}

const saveProfile = async () => {
  // Distributor self-update via /users/me is intentionally not supported
  // (see Phase 13 R13a — legacy /distributor/profile had no PUT). The UI
  // retains an edit mode because logo/document uploads live on separate
  // endpoints; base field edits are read-only until a PATCH path is added.
  saving.value = true
  try {
    showToast.info('Редактирование профиля выполняется через менеджера. Обратитесь в поддержку для внесения изменений.')
    editMode.value = false
  } finally {
    saving.value = false
  }
}

const handleLogoUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  // Проверка размера файла (максимум 5MB)
  if (file.size > 5 * 1024 * 1024) {
    showToast.error('Файл слишком большой. Максимальный размер: 5MB')
    return
  }

  // Проверка типа файла
  if (!file.type.startsWith('image/')) {
    showToast.error('Можно загружать только изображения')
    return
  }
  
  try {
    const formData = new FormData()
    formData.append('logo', file)
    
    const response = await $fetch<{ logo_url: string }>('/api/v1/distributor/profile/logo', {
      method: 'POST',
      body: formData
    })

    profile.value.logo = response.logo_url
    showToast.success('Логотип загружен')

  } catch (err) {
    logger.error('Error uploading logo:', err)
    showToast.error('Ошибка при загрузке логотипа')
  }
}

const handleDocumentUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length === 0) return

  try {
    const formData = new FormData()
    files.forEach(file => {
      formData.append('documents', file)
    })

    const response = await $fetch<{ documents: DistributorDocument[] }>('/api/v1/distributor/profile/documents', {
      method: 'POST',
      body: formData
    })

    profile.value.documents.push(...response.documents)
    showToast.success(`Загружено ${files.length} документов`)

  } catch (err) {
    logger.error('Error uploading documents:', err)
    showToast.error('Ошибка при загрузке документов')
  }
}

const downloadDocument = async (doc: DistributorDocument) => {
  try {
    const response = await $fetch<BlobPart>(`/api/v1/distributor/profile/documents/${doc.id}/download`)

    const blob = new Blob([response], { type: doc.mime_type })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = doc.file_name
    link.click()
    URL.revokeObjectURL(url)
    
  } catch (err) {
    logger.error('Error downloading document:', err)
    showToast.error('Ошибка при скачивании документа')
  }
}

// Вспомогательные функции
const formatDate = (dateString: string | null) => {
  if (!dateString) return 'Не указано'
  return new Date(dateString).toLocaleDateString('ru-RU')
}

const getVerificationClass = (status: string) => {
  const classes: Record<string, string> = {
    verified: 'bg-green-100 text-green-800',
    pending: 'bg-yellow-100 text-yellow-800',
    rejected: 'bg-red-100 text-red-800'
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

const getVerificationText = (status: string) => {
  const texts: Record<string, string> = {
    verified: 'Верифицирован',
    pending: 'На проверке',
    rejected: 'Отклонен'
  }
  return texts[status] || status
}

const getDocumentStatusClass = (status: string) => {
  const classes: Record<string, string> = {
    approved: 'bg-green-100 text-green-800',
    pending: 'bg-yellow-100 text-yellow-800',
    rejected: 'bg-red-100 text-red-800'
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

const getDocumentStatusText = (status: string) => {
  const texts: Record<string, string> = {
    approved: 'Одобрен',
    pending: 'На проверке',
    rejected: 'Отклонен'
  }
  return texts[status] || status
}

// Инициализация
onMounted(() => {
  fetchProfile()
})
</script>
