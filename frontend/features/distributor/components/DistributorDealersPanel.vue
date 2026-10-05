<template>
  <div class="space-y-6">
    <!-- Заголовок -->
    <div class="flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Управление дилерами</h2>
        <p class="text-gray-600 mt-1">Ваша дилерская сеть и партнеры</p>
      </div>
      <div class="flex space-x-3">
        <button
          @click="exportDealers"
          :disabled="exporting"
          class="bg-gray-600 hover:bg-gray-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg transition-colors"
        >
          {{ exporting ? 'Экспорт…' : 'Экспорт данных' }}
        </button>
      </div>
    </div>

    <!-- Статистика -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-gradient-to-r from-blue-500 to-blue-600 p-6 rounded-lg text-white">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-blue-100 text-sm">Всего дилеров</p>
            <p class="text-2xl font-bold">{{ totalDealers }}</p>
          </div>
          <svg class="w-8 h-8 text-blue-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
          </svg>
        </div>
      </div>

      <div class="bg-white p-6 rounded-lg shadow-sm border flex items-center">
        <div class="relative flex-1">
          <input
            v-model="search"
            type="text"
            placeholder="Поиск по названию (на текущей странице)…"
            class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
          <svg class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
        </div>
      </div>
    </div>

    <!-- Загрузка -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем данные о дилерах...</p>
    </div>

    <!-- Список дилеров -->
    <div v-else-if="filteredDealers.length" class="bg-white rounded-lg shadow-sm border overflow-hidden">
      <div class="divide-y divide-gray-200">
        <div
          v-for="dealer in filteredDealers"
          :key="dealer.id"
          class="p-6 hover:bg-gray-50 transition-colors flex items-center space-x-4"
        >
          <!-- Логотип-заглушка -->
          <div class="flex-shrink-0 w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
            <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
            </svg>
          </div>

          <!-- Информация -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center space-x-2">
              <h3 class="text-lg font-semibold text-gray-900 truncate">
                {{ dealer.name || 'Без названия' }}
              </h3>
              <span class="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                Дилер
              </span>
            </div>
            <div class="text-xs text-gray-400 mt-1 truncate">ID: {{ dealer.id }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div v-else class="text-center py-12 bg-white rounded-lg shadow-sm border">
      <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">Дилеров не найдено</h3>
      <p class="text-gray-600">
        {{ search ? 'По вашему запросу ничего не найдено на этой странице.' : 'В вашей сети пока нет дилеров.' }}
      </p>
    </div>

    <!-- Пагинация -->
    <div v-if="pagination && pagination.pages > 1" class="flex justify-between items-center">
      <div class="text-sm text-gray-700">
        Показано {{ (pagination.page - 1) * pagination.limit + 1 }} -
        {{ Math.min(pagination.page * pagination.limit, pagination.total) }}
        из {{ pagination.total }} дилеров
      </div>
      <div class="flex space-x-1">
        <button
          v-for="page in visiblePages"
          :key="page"
          @click="changePage(page)"
          :class="{
            'bg-blue-600 text-white': page === pagination.page,
            'bg-gray-200 text-gray-700 hover:bg-gray-300': page !== pagination.page
          }"
          class="px-3 py-1 rounded transition-colors"
          :disabled="page === pagination.page"
        >
          {{ page }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import type { Dealer, Pagination } from '~/features/distributor/types'

const config = useRuntimeConfig()
const { showToast } = useToast()
const logger = useLogger()

const loading = ref(false)
const exporting = ref(false)
const dealers = ref<Dealer[]>([])
const pagination = ref<Pagination | null>(null)
const search = ref('')

const page = ref(1)
const limit = 20

// Бэкенд не поддерживает серверный поиск по списку дилеров — фильтруем
// загруженную страницу на клиенте.
const filteredDealers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return dealers.value
  return dealers.value.filter((d) => (d.name || '').toLowerCase().includes(q))
})

const totalDealers = computed(() => pagination.value?.total ?? dealers.value.length)

const visiblePages = computed(() => {
  if (!pagination.value || pagination.value.pages <= 1) return []

  const current = pagination.value.page
  const total = pagination.value.pages
  const pages: number[] = []

  let start = Math.max(1, current - 2)
  const end = Math.min(total, start + 4)

  if (end - start < 4) {
    start = Math.max(1, end - 4)
  }

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  return pages
})

const fetchDealers = async () => {
  try {
    loading.value = true

    const params = new URLSearchParams({
      page: String(page.value),
      limit: String(limit),
    })

    const response = await $fetch<{
      dealers: Dealer[]
      pagination: Pagination | null
    }>(`/api/v1/distributor/dealers?${params}`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
    })

    dealers.value = response.dealers || []
    pagination.value = response.pagination || null
  } catch (err) {
    logger.error('Error fetching dealers:', err)
    showToast.error('Ошибка при загрузке дилеров')
  } finally {
    loading.value = false
  }
}

const changePage = (target: number) => {
  page.value = target
  search.value = ''
  fetchDealers()
}

const exportDealers = async () => {
  try {
    exporting.value = true
    const response = await $fetch<Blob>('/api/v1/distributor/dealers?format=xlsx', {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob',
    })

    const blob =
      response instanceof Blob
        ? response
        : new Blob([response as BlobPart], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `dealers_${new Date().toISOString().split('T')[0]}.xlsx`
    link.click()
    URL.revokeObjectURL(url)

    showToast.success('Данные экспортированы')
  } catch (err) {
    logger.error('Error exporting dealers:', err)
    showToast.error('Ошибка при экспорте данных')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  fetchDealers()
})
</script>
