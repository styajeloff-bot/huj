<template>
  <div>
    <h2 class="text-xl font-semibold text-gray-900 mb-6">
      Статистика системы
    </h2>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем статистику...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button @click="fetchStats" class="btn-primary">
        Попробовать снова
      </button>
    </div>

    <div v-else class="space-y-6">
      <!-- Общая статистика -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z">
                  </path>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-500">Всего пользователей</p>
              <p class="text-2xl font-semibold text-gray-900">{{ stats.total_users }}</p>
            </div>
          </div>
        </div>

        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4">
                  </path>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-500">Всего компаний</p>
              <p class="text-2xl font-semibold text-gray-900">{{ stats.total_companies }}</p>
            </div>
          </div>
        </div>

        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
                  </path>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-500">Всего заявок</p>
              <p class="text-2xl font-semibold text-gray-900">{{ stats.total_applications }}</p>
            </div>
          </div>
        </div>

        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-yellow-100 rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z">
                  </path>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-500">Общая сумма заявок</p>
              <p class="text-2xl font-semibold text-gray-900">{{ formatMoney(stats.total_application_amount) }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Статистика по пользователям -->
      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Пользователи по ролям</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div class="text-center">
            <div class="text-2xl font-semibold text-blue-600">{{ stats.client_users }}</div>
            <div class="text-sm text-gray-500">Клиенты</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-green-600">{{ stats.dealer_users }}</div>
            <div class="text-sm text-gray-500">Дилеры</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-purple-600">{{ stats.leasing_company_users }}</div>
            <div class="text-sm text-gray-500">Лизинговые компании</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-orange-600">{{ stats.distributor_users }}</div>
            <div class="text-sm text-gray-500">Дистрибьюторы</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-red-600">{{ stats.carcraft_employee_users || 0 }}</div>
            <div class="text-sm text-gray-500">Сотрудники CarCraft</div>
          </div>
        </div>
      </div>

      <!-- Статистика по компаниям -->
      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Компании по типам</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="text-center">
            <div class="text-2xl font-semibold text-green-600">{{ stats.dealer_companies }}</div>
            <div class="text-sm text-gray-500">Дилеры</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-purple-600">{{ stats.leasing_companies }}</div>
            <div class="text-sm text-gray-500">Лизинговые компании</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-orange-600">{{ stats.distributor_companies }}</div>
            <div class="text-sm text-gray-500">Дистрибьюторы</div>
          </div>
        </div>
      </div>

      <!-- Статистика по заявкам -->
      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Заявки</h3>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="text-center">
            <div class="text-2xl font-semibold text-blue-600">{{ stats.total_applications }}</div>
            <div class="text-sm text-gray-500">Всего</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-yellow-600">{{ stats.submitted_applications }}</div>
            <div class="text-sm text-gray-500">Поданные</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-green-600">{{ stats.approved_applications }}</div>
            <div class="text-sm text-gray-500">Одобренные</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-semibold text-purple-600">{{ stats.applications_last_30_days }}</div>
            <div class="text-sm text-gray-500">За последние 30 дней</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AdminStats } from '~/types/admin'

const config = useRuntimeConfig()

const stats = ref<Partial<AdminStats>>({})
const loading = ref(true)
const error = ref('')

const fetchStats = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await $fetch('/api/v1/admin/stats', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    stats.value = (response as { stats: AdminStats }).stats
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    error.value = e.data?.error || 'Ошибка при загрузке статистики'
  } finally {
    loading.value = false
  }
}

const { formatPrice: formatSharedPrice } = useFormatPrice()

const formatMoney = (amount: number | undefined) => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

onMounted(() => {
  fetchStats()
})
</script>
