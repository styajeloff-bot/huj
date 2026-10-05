<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
          Справочник должностей
        </h2>
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">
          Управление должностями сотрудников дилеров и дистрибьюторов
        </p>
      </div>
      <button
        type="button"
        class="btn-primary inline-flex items-center gap-2 text-sm shadow-sm"
        @click="openCreateModal"
      >
        <PlusIcon class="w-4 h-4" />
        Создать должность
      </button>
    </div>

    <!-- Error message -->
    <div
      v-if="error"
      class="p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg text-sm text-[color:var(--storefront-error-text,#b91c1c)]"
    >
      {{ error }}
    </div>

    <!-- Loading spinner -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загрузка списка должностей...</p>
    </div>

    <!-- Table -->
    <div
      v-else
      class="bg-white rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm overflow-hidden"
    >
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <thead class="bg-gray-50">
            <tr>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Название
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Системный код
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Активность
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Дата создания
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                Действия
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="position in positions"
              :key="position.id"
              class="hover:bg-gray-50 transition-colors"
            >
              <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {{ position.name }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                {{ position.code }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">
                <span
                  class="inline-flex px-2.5 py-0.5 text-xs font-semibold rounded-full"
                  :class="position.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                >
                  {{ position.is_active ? 'Активен' : 'Неактивен' }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDate(position.created_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <div class="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    class="text-blue-600 hover:text-blue-900 transition-colors inline-flex items-center gap-1"
                    @click="openEditModal(position)"
                  >
                    <PencilSquareIcon class="w-4 h-4" />
                    Редактировать
                  </button>
                  <button
                    type="button"
                    class="text-red-600 hover:text-red-900 disabled:opacity-40 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
                    :disabled="!position.is_active || deactivatingId === position.id"
                    :title="!position.is_active ? 'Должность уже отключена' : 'Отключить должность'"
                    @click="handleDeactivate(position)"
                  >
                    <NoSymbolIcon class="w-4 h-4" />
                    Отключить
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="positions.length === 0">
              <td
                colspan="5"
                class="px-6 py-12 text-center text-sm text-gray-500"
              >
                Должности пока не добавлены
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal -->
    <PositionFormModal
      v-if="showModal"
      :show="showModal"
      :position="editingPosition"
      @close="showModal = false"
      @saved="onPositionSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { PlusIcon, PencilSquareIcon, NoSymbolIcon } from '@heroicons/vue/24/outline'
import {
  listPositions,
  deactivatePosition,
  type PositionItem,
} from '../api/employeesApi'
import PositionFormModal from './PositionFormModal.vue'

const config = useRuntimeConfig()

const positions = ref<PositionItem[]>([])
const loading = ref(true)
const error = ref('')
const deactivatingId = ref<string | null>(null)

const showModal = ref(false)
const editingPosition = ref<PositionItem | null>(null)

const formatDate = (isoStr?: string | null): string => {
  if (!isoStr) return '—'
  try {
    const d = new Date(isoStr)
    return d.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return isoStr
  }
}

const fetchPositions = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await listPositions(config)
    positions.value = res.items || []
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Не удалось загрузить список должностей'
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  editingPosition.value = null
  showModal.value = true
}

const openEditModal = (position: PositionItem) => {
  editingPosition.value = { ...position }
  showModal.value = true
}

const onPositionSaved = async () => {
  await fetchPositions()
}

const handleDeactivate = async (pos: PositionItem) => {
  if (!pos.is_active || deactivatingId.value) return
  if (!window.confirm(`Отключить должность «${pos.name}»?`)) return

  deactivatingId.value = pos.id
  error.value = ''
  try {
    await deactivatePosition(config, pos.id)
    pos.is_active = false
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Не удалось отключить должность'
  } finally {
    deactivatingId.value = null
  }
}

onMounted(() => {
  fetchPositions()
})
</script>
