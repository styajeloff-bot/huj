<template>
  <div>
    <div class="mb-6 flex items-end justify-between gap-6">
      <div>
        <h2 class="text-xl font-semibold text-gray-900">Избранные модели на главной</h2>
        <label class="mt-4 block text-sm font-medium text-gray-700" for="featured-storefront">Витрина</label>
        <select id="featured-storefront" v-model="selectedStorefrontId" class="select-field mt-1 min-h-11 min-w-72" :disabled="loadingStorefronts">
          <option v-for="item in storefronts" :key="item.id" :value="item.id">
            {{ item.is_default ? 'Основной сайт' : `/${item.slug}` }}
          </option>
        </select>
      </div>
      <button @click="showAddModal = true" class="btn-primary">
        Добавить модель
      </button>
    </div>

    <p class="text-gray-600 mb-6">
      Выберите модели автомобилей, которые будут отображаться на главной странице сайта в разделе "Каталог автомобилей".
    </p>

    <DataTable
      :data="featured"
      :columns="columns"
      :loading="loading"
      :actions="actions"
      :server-side="false"
      :paginated="false"
      :searchable="false"
      :filterable="false"
      :show-header="false"
      empty-message="Нет избранных моделей"
      empty-action-text="Добавить первую модель"
      @action="handleAction"
      @refresh="fetchFeatured"
      @empty-action="showAddModal = true"
    >
      <!-- Кастомная колонка: Позиция -->
      <template #column-position="{ item }">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium text-gray-900">{{ getPosition(item) }}</span>
          <div class="flex flex-col gap-1">
            <button
              v-if="getPosition(item) > 1"
              @click.stop="moveUp(getPosition(item) - 1)"
              class="text-gray-400 hover:text-gray-600"
              title="Вверх"
            >
              <ChevronUpIcon class="w-4 h-4" />
            </button>
            <button
              v-if="getPosition(item) < featured.length"
              @click.stop="moveDown(getPosition(item) - 1)"
              class="text-gray-400 hover:text-gray-600"
              title="Вниз"
            >
              <ChevronDownIcon class="w-4 h-4" />
            </button>
          </div>
        </div>
      </template>

      <!-- Кастомная колонка: Марка / Модель -->
      <template #column-model="{ item }">
        <div class="text-sm font-medium text-gray-900">{{ item.mark_name }}</div>
        <div class="text-sm text-gray-500">{{ item.model_name }}</div>
        <span
          v-if="!item.is_eligible"
          role="status"
          class="mt-2 inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-1 text-sm font-medium text-amber-800 ring-1 ring-inset ring-amber-200"
        >
          <ExclamationTriangleIcon class="h-4 w-4" aria-hidden="true" />
          Недоступна на выбранной витрине
        </span>
      </template>
    </DataTable>

    <!-- Модальное окно добавления -->
    <div v-if="showAddModal" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex min-h-full items-center justify-center p-4">
        <div class="fixed inset-0 bg-black/50" @click="showAddModal = false"></div>
        
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b">
            <h3 class="text-lg font-semibold text-gray-900">Добавить модель в избранное</h3>
            <button @click="showAddModal = false" class="text-gray-400 hover:text-gray-600">
              <XMarkIcon class="w-6 h-6" />
            </button>
          </div>

          <div class="p-4 border-b">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Марка</label>
                <select v-model="modalFilters.mark_id" class="select-field" @change="fetchModels">
                  <option value="">Все марки</option>
                  <option v-for="mark in availableMarks" :key="mark.id" :value="mark.id">
                    {{ mark.name }}
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Поиск</label>
                <input
                  v-model="modalFilters.search"
                  type="text"
                  placeholder="Название модели"
                  class="input-field"
                  @input="debouncedFetchModels"
                >
              </div>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="loadingModels" class="text-center py-4">
              <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
            </div>

            <div v-else-if="models.length === 0" class="text-center py-4 text-gray-500">
              Модели не найдены
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="model in models"
                :key="model.model_id"
                class="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50"
                :class="{ 'bg-green-50 border-green-200': model.is_featured }"
              >
                <div>
                  <div class="font-medium text-gray-900">{{ model.mark_name }} {{ model.model_name }}</div>
                  <div class="text-sm text-gray-500">
                    Доступно: {{ model.available_count }} авто
                    <span v-if="model.min_price"> | от {{ formatPrice(model.min_price) }}</span>
                  </div>
                </div>
                <div>
                  <span v-if="model.is_featured" class="text-green-600 text-sm font-medium">
                    Уже добавлена
                  </span>
                  <button
                    v-else
                    @click="addFeatured(model)"
                    class="btn-primary text-sm py-1 px-3"
                    :disabled="addingModel === model.model_id"
                  >
                    <span v-if="addingModel === model.model_id">...</span>
                    <span v-else>Добавить</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-end gap-3 p-4 border-t">
            <button @click="showAddModal = false" class="btn-secondary">
              Закрыть
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ChevronDownIcon,
  ChevronUpIcon,
  ExclamationTriangleIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import {
  createFeaturedAdminApi,
  type FeaturedItem,
  type FeaturedMark,
  type FeaturedModel,
} from '~/features/admin/featured/api/featuredAdminApi'
import { createStorefrontsAdminApi, type AdminStorefront } from '~/features/admin/storefronts/api/storefrontsAdminApi'
import type { UUID } from '~/types/ids'

const config = useRuntimeConfig()
const storefrontsApi = createStorefrontsAdminApi(config)
const storefronts = ref<AdminStorefront[]>([])
const selectedStorefrontId = ref<UUID>('')
const loadingStorefronts = ref(true)
const api = () => createFeaturedAdminApi(config, selectedStorefrontId.value)

const featured = ref<FeaturedItem[]>([])
const loading = ref(true)

const showAddModal = ref(false)
const models = ref<FeaturedModel[]>([])
const loadingModels = ref(false)
const availableMarks = ref<FeaturedMark[]>([])
const addingModel = ref<string | null>(null)

const modalFilters = ref({
  mark_id: '',
  search: ''
})

const columns = [
  { key: 'position', label: 'Позиция' },
  { key: 'model', label: 'Марка / Модель' },
]

const actions = [
  { key: 'delete', label: 'Удалить', icon: TrashIcon, className: 'text-red-600 hover:text-red-900' }
]

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const debouncedFetchModels = () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    fetchModels()
  }, 300)
}

const formatPrice = (price: number) => {
  return new Intl.NumberFormat('ru-RU').format(price) + ' ₽'
}

const getPosition = (item: FeaturedItem | Record<string, unknown>) => {
  return featured.value.findIndex(f => f.id === item.id) + 1
}

const fetchFeatured = async () => {
  if (!selectedStorefrontId.value) return
  loading.value = true

  try {
    const response = await api().getFeatured()
    featured.value = response.featured || []
  } catch (err: unknown) {
    console.error('Error fetching featured:', err)
  } finally {
    loading.value = false
  }
}

const fetchMarks = async () => {
  if (!selectedStorefrontId.value) return
  try {
    const response = await api().getMarks()
    availableMarks.value = response.marks || []
  } catch (err: unknown) {
    console.error('Error fetching marks:', err)
  }
}

const fetchModels = async () => {
  loadingModels.value = true

  try {
    const response = await api().getModels({
      mark_id: modalFilters.value.mark_id || undefined,
      search: modalFilters.value.search || undefined,
      limit: '50',
    })
    models.value = response.models || []
  } catch (err: unknown) {
    console.error('Error fetching models:', err)
  } finally {
    loadingModels.value = false
  }
}

const addFeatured = async (model: FeaturedModel) => {
  addingModel.value = model.model_id

  try {
    await api().addFeatured(model.model_id)

    model.is_featured = true
    await fetchFeatured()
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    alert(e.data?.error || 'Ошибка добавления')
  } finally {
    addingModel.value = null
  }
}

const handleAction = ({ action, item }: { action: string; item: Record<string, unknown> }) => {
  if (action === 'delete') {
    removeFeatured(item as unknown as FeaturedItem)
  }
}

const removeFeatured = async (item: FeaturedItem) => {
  if (!confirm(`Удалить "${item.mark_name} ${item.model_name}" из избранного?`)) return

  try {
    await api().removeFeatured(item.id)

    await fetchFeatured()
    if (showAddModal.value) {
      await fetchModels()
    }
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    alert(e.data?.error || 'Ошибка удаления')
  }
}

const toggleActive = async (item: FeaturedItem) => {
  try {
    const response = await api().toggleActive(item.id, !item.is_active)

    item.is_active = (response as { featured: { is_active: boolean } }).featured.is_active
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    alert(e.data?.error || 'Ошибка')
  }
}

const moveUp = (index: number) => {
  if (index <= 0) return
  const temp = featured.value[index]
  featured.value[index] = featured.value[index - 1]
  featured.value[index - 1] = temp
  saveOrder()
}

const moveDown = (index: number) => {
  if (index >= featured.value.length - 1) return
  const temp = featured.value[index]
  featured.value[index] = featured.value[index + 1]
  featured.value[index + 1] = temp
  saveOrder()
}

const saveOrder = async () => {
  try {
    const orderedIds = featured.value.map(item => item.id)
    await api().reorder(orderedIds)
  } catch (err: unknown) {
    console.error('Error saving order:', err)
  }
}

watch(showAddModal, (val) => {
  if (val) {
    fetchMarks()
    fetchModels()
  }
})

onMounted(() => {
  void (async () => {
    try {
      const response = await storefrontsApi.list()
      storefronts.value = response.items
      selectedStorefrontId.value = response.items[0]?.id ?? ''
      await fetchFeatured()
    } finally {
      loadingStorefronts.value = false
    }
  })()
})

watch(selectedStorefrontId, async (current, previous) => {
  if (!current || current === previous) return
  showAddModal.value = false
  availableMarks.value = []
  models.value = []
  await fetchFeatured()
})
</script>
