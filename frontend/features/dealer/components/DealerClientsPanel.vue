<template>
  <div class="card p-6">
    <div class="flex justify-between items-center mb-6">
      <h3 class="text-xl font-semibold text-gray-900">Мои клиенты</h3>
      <button
        @click="showInviteModal = true"
        class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
      >
        Пригласить клиента
      </button>
    </div>

    <!-- Статистика -->
    <div v-if="stats" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-gradient-to-r from-blue-50 to-blue-100 p-4 rounded-lg">
        <div class="text-2xl font-bold text-blue-600">{{ stats.total_clients }}</div>
        <div class="text-sm text-gray-600">Всего клиентов</div>
      </div>
      <div class="bg-gradient-to-r from-green-50 to-green-100 p-4 rounded-lg">
        <div class="text-2xl font-bold text-green-600">{{ stats.active_clients }}</div>
        <div class="text-sm text-gray-600">Активные</div>
      </div>
      <div class="bg-gradient-to-r from-purple-50 to-purple-100 p-4 rounded-lg">
        <div class="text-2xl font-bold text-purple-600">{{ stats.monthly_applications }}</div>
        <div class="text-sm text-gray-600">Заявки за месяц</div>
      </div>
      <div class="bg-gradient-to-r from-orange-50 to-orange-100 p-4 rounded-lg">
        <div class="text-2xl font-bold text-orange-600">{{ formatPrice(stats.average_deal) }}</div>
        <div class="text-sm text-gray-600">Средняя сделка</div>
      </div>
    </div>

    <DataTable
      :data="clients"
      :columns="columns"
      :loading="loading"
      :filters="tableFilters"
      :server-side="true"
      :total-items="pagination?.total || 0"
      :current-server-page="pagination?.page || 1"
      :total-server-pages="pagination?.pages || 1"
      :page-size="pagination?.limit || 20"
      :searchable="true"
      :show-header="false"
      :paginated="true"
      empty-message="У вас пока нет клиентов"
      empty-action-text="Пригласить первого клиента"
      @page-change="changePage"
      @filter="handleFilter"
      @search="handleSearch"
      @refresh="fetchClients"
      @empty-action="showInviteModal = true"
    >
      <!-- Кастомная колонка: Клиент -->
      <template #column-name="{ item }">
        <div class="flex items-center cursor-pointer" @click="selectClient(item)">
          <div class="flex-shrink-0 h-10 w-10">
            <div class="h-10 w-10 rounded-full bg-gray-300 flex items-center justify-center">
              <span class="text-sm font-medium text-gray-700">
                {{ String(item.name).charAt(0).toUpperCase() }}
              </span>
            </div>
          </div>
          <div class="ml-4">
            <div class="text-sm font-medium text-gray-900">{{ item.name }}</div>
            <div v-if="item.company_name" class="text-sm text-gray-500">
              {{ item.company_name }}
            </div>
          </div>
        </div>
      </template>

      <!-- Кастомная колонка: Контакты -->
      <template #column-contacts="{ item }">
        <div class="text-sm text-gray-900">{{ item.email }}</div>
        <div v-if="item.phone" class="text-sm text-gray-500">{{ item.phone }}</div>
      </template>

      <!-- Кастомная колонка: Заявки -->
      <template #column-applications="{ item }">
        <div class="flex space-x-2">
          <span class="text-blue-600 font-medium">{{ item.applications_count }}</span>
          <span class="text-gray-400">/</span>
          <span class="text-green-600 font-medium">{{ item.approved_applications_count }}</span>
        </div>
      </template>

      <!-- Кастомная колонка: Сумма сделок -->
      <template #column-total_amount="{ item }">
        <span class="text-sm font-medium text-gray-900">{{ formatPrice(Number(item.total_amount)) }}</span>
      </template>

      <!-- Кастомная колонка: Последняя активность -->
      <template #column-last_activity_at="{ item }">
        <span class="text-sm text-gray-500">{{ formatDate(String(item.last_activity_at ?? '')) }}</span>
      </template>

      <!-- Кастомная колонка: Статус -->
      <template #column-is_active="{ item }">
        <span
          :class="{
            'bg-green-100 text-green-800': item.is_active,
            'bg-gray-100 text-gray-800': !item.is_active
          }"
          class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full"
        >
          {{ item.is_active ? 'Активен' : 'Неактивен' }}
        </span>
      </template>
    </DataTable>

    <!-- Модальное окно приглашения клиента -->
    <div v-if="showInviteModal" class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50" @click="showInviteModal = false">
      <div class="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white" @click.stop>
        <div class="p-6">
          <h3 class="text-lg font-medium text-gray-900 mb-4">Пригласить клиента</h3>
          <form @submit.prevent="inviteClient">
            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-700">Email</label>
                <input
                  v-model="inviteForm.email"
                  type="email"
                  required
                  class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500 px-3 py-2 border"
                  placeholder="client@example.com"
                >
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700">Имя</label>
                <input
                  v-model="inviteForm.name"
                  type="text"
                  required
                  class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500 px-3 py-2 border"
                  placeholder="Иван Иванов"
                >
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700">Сообщение (необязательно)</label>
                <textarea
                  v-model="inviteForm.message"
                  rows="3"
                  class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500 px-3 py-2 border"
                  placeholder="Персональное сообщение для клиента..."
                ></textarea>
              </div>
            </div>
            <div class="mt-6 flex justify-end space-x-3">
              <button
                type="button"
                @click="showInviteModal = false"
                class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
              >
                Отмена
              </button>
              <button
                type="submit"
                :disabled="inviteLoading"
                class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {{ inviteLoading ? 'Отправка...' : 'Отправить приглашение' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useFormatPrice } from '@/composables/useFormatPrice'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import type { DataTableFilter } from '~/types/index'
import type { DealerClientStats, DealerClient, Pagination } from '~/types/features'

const { formatPrice } = useFormatPrice()
const { showToast } = useToast()
const logger = useLogger()

// Реактивные данные
const loading = ref(false)
const clients = ref<DealerClient[]>([])
const stats = ref<DealerClientStats | null>(null)
const pagination = ref<Pagination | null>(null)

// Фильтры
const currentFilters = ref({
  search: '',
  status: '',
  period: ''
})

// Модальное окно приглашения
const showInviteModal = ref(false)
const inviteLoading = ref(false)
const inviteForm = ref({
  email: '',
  name: '',
  message: ''
})

const columns = [
  { key: 'name', label: 'Клиент' },
  { key: 'contacts', label: 'Контакты' },
  { key: 'applications', label: 'Заявки' },
  { key: 'total_amount', label: 'Сумма сделок' },
  { key: 'last_activity_at', label: 'Последняя активность' },
  { key: 'is_active', label: 'Статус' }
]

const tableFilters: DataTableFilter[] = [
  {
    key: 'status',
    label: 'Статус',
    type: 'select',
    options: [
      { value: 'active', label: 'Активные' },
      { value: 'inactive', label: 'Неактивные' }
    ]
  },
  {
    key: 'period',
    label: 'Период',
    type: 'select',
    options: [
      { value: 'week', label: 'За неделю' },
      { value: 'month', label: 'За месяц' },
      { value: 'quarter', label: 'За квартал' }
    ]
  }
]

// Методы
const fetchClients = async () => {
  try {
    loading.value = true
    
    const params = new URLSearchParams({
      page: (pagination.value?.page || 1).toString(),
      limit: (pagination.value?.limit || 20).toString()
    })
    
    if (currentFilters.value.search) params.append('search', currentFilters.value.search)
    if (currentFilters.value.status) params.append('status', currentFilters.value.status)
    if (currentFilters.value.period) params.append('period', currentFilters.value.period)
    
    const response = await $fetch<{ clients: DealerClient[]; stats: DealerClientStats; pagination: Pagination }>(`/api/v1/dealer/clients?${params}`)

    clients.value = response.clients
    stats.value = response.stats
    pagination.value = response.pagination
    
  } catch (err) {
    logger.error('Error fetching clients:', err)
  } finally {
    loading.value = false
  }
}

const changePage = (page: number) => {
  pagination.value = { ...(pagination.value as Pagination), page }
  fetchClients()
}

const handleFilter = (filterValues: Record<string, string>) => {
  currentFilters.value = { ...currentFilters.value, ...filterValues }
  pagination.value = { ...(pagination.value as Pagination), page: 1 }
  fetchClients()
}

const handleSearch = (query: string) => {
  currentFilters.value.search = query
  pagination.value = { ...(pagination.value as Pagination), page: 1 }
  fetchClients()
}

const selectClient = (client: Record<string, unknown>) => {
  logger.info('Selected client:', client)
}

const inviteClient = async () => {
  try {
    inviteLoading.value = true
    
    await $fetch('/api/v1/dealer/invite-client', {
      method: 'POST',
      body: inviteForm.value
    })
    
    showToast.success('Приглашение отправлено!')
    showInviteModal.value = false
    
    inviteForm.value = { email: '', name: '', message: '' }
    fetchClients()
    
  } catch (err: unknown) {
    logger.error('Error inviting client:', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при отправке приглашения')
  } finally {
    inviteLoading.value = false
  }
}

const formatDate = (dateString: string | undefined | null): string => {
  if (!dateString) return 'Никогда'

  const date = new Date(dateString)
  const now = new Date()
  const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / 60000)
  
  if (diffInMinutes < 60) {
    return `${diffInMinutes} мин назад`
  } else if (diffInMinutes < 1440) {
    return `${Math.floor(diffInMinutes / 60)} ч назад`
  } else if (diffInMinutes < 10080) {
    return `${Math.floor(diffInMinutes / 1440)} дн назад`
  } else {
    return date.toLocaleDateString('ru-RU')
  }
}

// Жизненный цикл
onMounted(() => {
  fetchClients()
})
</script>
