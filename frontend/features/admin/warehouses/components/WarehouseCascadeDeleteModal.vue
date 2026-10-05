<template>
  <div
    class="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto"
    @click.self="onBackdropClick"
    @keydown.esc="onEscKey"
  >
    <div
      class="bg-white rounded-lg shadow-xl max-w-2xl w-full my-8 max-h-[90vh] flex flex-col overflow-hidden text-gray-900"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cascade-modal-title"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <h3 id="cascade-modal-title" class="text-lg font-semibold text-gray-900">
          Удалить склад и связанные данные?
        </h3>
        <button
          type="button"
          class="text-gray-400 hover:text-gray-600 p-1 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="deleting"
          aria-label="Закрыть"
          @click="handleClose"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="px-6 py-5 overflow-y-auto space-y-5 flex-1">
        <!-- Warning Banner -->
        <div class="p-3.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900 leading-relaxed flex items-start gap-3">
          <svg class="w-5 h-5 text-amber-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p>
            Будут удалены склад и все его объявления, а также связанные марки, модели, модификации, характеристики и группы характеристик, которые больше нигде не используются. Действие нельзя отменить.
          </p>
        </div>

        <!-- Warehouse Info Card -->
        <div class="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-2 text-sm">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
            <span class="text-gray-500 font-medium">Название склада:</span>
            <span class="font-semibold text-gray-900 sm:text-right">{{ warehouse.name || '—' }}</span>
          </div>
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
            <span class="text-gray-500 font-medium">Адрес:</span>
            <span class="text-gray-900 sm:text-right">{{ warehouse.address || '—' }}</span>
          </div>
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
            <span class="text-gray-500 font-medium">Владелец:</span>
            <div class="flex items-center gap-1.5 sm:justify-end flex-wrap">
              <span class="font-semibold text-gray-900">
                {{ warehouse.owner_company_name || warehouse.company_name || '—' }}
              </span>
              <span
                v-if="warehouse.owner_company_type"
                :class="warehouse.owner_company_type === 'distributor' ? 'bg-indigo-100 text-indigo-800' : 'bg-purple-100 text-purple-800'"
                class="inline-flex px-1.5 py-0.5 text-xs font-medium rounded"
              >
                {{ warehouse.owner_company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Loading State -->
        <div v-if="loading" class="py-10 flex flex-col items-center justify-center gap-3">
          <svg class="animate-spin h-7 w-7 text-blue-600" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span class="text-sm text-gray-500">Загрузка информации об удалении склада...</span>
        </div>

        <!-- Load Error State -->
        <div
          v-else-if="loadError"
          class="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800 space-y-3"
          role="alert"
        >
          <div class="flex items-center gap-2 font-semibold">
            <svg class="w-5 h-5 text-red-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Не удалось загрузить данные предпросмотра</span>
          </div>
          <p class="text-red-700 leading-relaxed">{{ loadError }}</p>
          <button
            type="button"
            class="btn-secondary text-sm bg-white hover:bg-gray-50 text-red-700 border-red-200"
            @click="fetchPreview"
          >
            Повторить загрузку
          </button>
        </div>

        <!-- Preview Data -->
        <div v-else-if="preview" class="space-y-5">
          <!-- Blockers Warning (if any) -->
          <div
            v-if="hasBlockers"
            class="p-4 bg-red-50 border border-red-200 rounded-lg space-y-3"
            role="alert"
          >
            <div class="flex items-center gap-2">
              <svg class="w-5 h-5 text-red-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              <h4 class="text-sm font-bold text-red-900">Удаление заблокировано</h4>
            </div>
            <p class="text-xs text-red-700 leading-relaxed">
              Обнаружены активные процессы или защищённые связи. Склад нельзя удалить до их завершения или устранения:
            </p>
            <ul class="list-disc list-inside space-y-1 text-xs text-red-800 font-medium">
              <li v-for="(blocker, idx) in normalizedBlockers" :key="idx">
                {{ blocker }}
              </li>
            </ul>
          </div>

          <!-- Main 6 Counters (Always visible, even if 0) -->
          <div>
            <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Удаляемые объекты каталога
            </h4>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div
                v-for="item in mainCounters"
                :key="item.key"
                class="p-3 rounded-lg border border-gray-200 bg-white flex flex-col justify-between"
              >
                <span class="text-xs text-gray-500 font-medium">{{ item.label }}</span>
                <span
                  class="text-xl font-bold mt-1"
                  :class="item.count > 0 ? 'text-red-600' : 'text-gray-400'"
                >
                  {{ item.count }}
                </span>
              </div>
            </div>
          </div>

          <!-- Auxiliary Deletable Records -->
          <div class="rounded-lg border border-gray-200 bg-gray-50 p-3.5 space-y-2">
            <h4 class="text-xs font-semibold text-gray-700 uppercase tracking-wider">
              Вспомогательные удаляемые записи
            </h4>
            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 text-xs">
              <div
                v-for="aux in auxiliaryCounters"
                :key="aux.label"
                class="flex items-center justify-between p-2 rounded bg-white border border-gray-200"
              >
                <span class="text-gray-600 truncate mr-1" :title="aux.label">{{ aux.label }}:</span>
                <span
                  class="font-semibold px-1.5 py-0.5 rounded text-[11px]"
                  :class="aux.count > 0 ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-500'"
                >
                  {{ aux.count }}
                </span>
              </div>
            </div>
          </div>

          <!-- Retained Objects List (if any) -->
          <div v-if="normalizedRetained.length > 0" class="rounded-lg border border-blue-200 bg-blue-50 p-3.5 space-y-2">
            <h4 class="text-xs font-semibold text-blue-900 uppercase tracking-wider">
              Сохраняемые связанные объекты
            </h4>
            <p class="text-xs text-blue-700">
              Эти записи останутся в системе, так как используются другими складами или объектами:
            </p>
            <ul class="space-y-1 text-xs text-blue-900">
              <li
                v-for="(retained, idx) in normalizedRetained"
                :key="idx"
                class="flex items-start gap-1.5"
              >
                <span class="text-blue-500 font-bold">•</span>
                <span>{{ retained }}</span>
              </li>
            </ul>
          </div>

          <!-- Submit / Stale Error Banner -->
          <div
            v-if="submitError"
            class="p-3.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800 space-y-1"
            role="alert"
          >
            <div class="font-semibold flex items-center gap-1.5">
              <svg class="w-4 h-4 text-red-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Ошибка удаления</span>
            </div>
            <p class="text-xs text-red-700 leading-relaxed">{{ submitError }}</p>
          </div>

          <!-- Confirmation Input -->
          <div class="pt-3 border-t border-gray-200 space-y-2">
            <label
              for="warehouse-cascade-delete-confirmation"
              class="block text-sm font-medium"
              :class="hasBlockers ? 'text-gray-400' : 'text-gray-900'"
            >
              Для подтверждения введите слово <span class="font-bold text-red-600 tracking-wider">УДАЛИТЬ</span>:
            </label>
            <input
              id="warehouse-cascade-delete-confirmation"
              v-model="confirmationText"
              type="text"
              class="input-field w-full font-medium"
              :class="{ 'opacity-50 cursor-not-allowed': hasBlockers || deleting }"
              placeholder="УДАЛИТЬ"
              autocomplete="off"
              autocorrect="off"
              spellcheck="false"
              :disabled="hasBlockers || deleting"
              @keydown.enter.prevent="handleEnterPress"
            />
            <p v-if="confirmationText && !isConfirmationValid && !hasBlockers" class="text-xs text-red-600">
              Слово подтверждения должно быть введено точно: «УДАЛИТЬ» (заглавными русскими буквами)
            </p>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end gap-3">
        <button
          type="button"
          class="btn-secondary text-sm"
          :disabled="deleting"
          @click="handleClose"
        >
          Отмена
        </button>
        <button
          type="button"
          class="btn-danger text-sm flex items-center gap-2"
          :disabled="!canConfirmDelete"
          @click="handleDelete"
        >
          <svg
            v-if="deleting"
            class="animate-spin h-4 w-4 text-white"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span>{{ deleting ? 'Удаление...' : 'Удалить склад и связанные данные' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  Warehouse,
  WarehouseDeletePreviewResponse,
  WarehouseDeleteCounts
} from '../types'
import { createWarehousesApi } from '../api/warehousesApi'
import { useToast } from '~/composables/useToast'

const props = defineProps<{
  warehouse: Warehouse
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'success', result?: unknown): void
}>()

const config = useRuntimeConfig()
const toast = useToast()
const api = createWarehousesApi(config)

const loading = ref(true)
const loadError = ref('')
const submitError = ref('')
const deleting = ref(false)
const confirmationText = ref('')
const preview = ref<WarehouseDeletePreviewResponse | null>(null)

const isConfirmationValid = computed(() => confirmationText.value.trim() === 'УДАЛИТЬ')

const mainCounters = computed(() => {
  const c: Partial<WarehouseDeleteCounts> = preview.value?.counts || {}
  return [
    { key: 'products', label: 'Объявления', count: c.products ?? 0 },
    { key: 'marks', label: 'Марки', count: c.marks ?? 0 },
    { key: 'models', label: 'Модели', count: c.models ?? 0 },
    { key: 'modifications', label: 'Модификации', count: c.modifications ?? 0 },
    { key: 'attributes', label: 'Характеристики', count: c.attributes ?? 0 },
    { key: 'attribute_groups', label: 'Группы характеристик', count: c.attribute_groups ?? 0 }
  ]
})

const auxiliaryCounters = computed(() => {
  const c: Record<string, unknown> = (preview.value?.counts as unknown as Record<string, unknown>) || {}
  return [
    { label: 'Комплектации', count: Number(c.trims ?? c.equipment_packages ?? c.kits ?? 0) },
    { label: 'Значения характеристик', count: Number(c.attribute_values ?? 0) },
    { label: 'Изображения', count: Number(c.images ?? c.media ?? 0) },
    { label: 'Корзины', count: Number(c.carts ?? c.cart_items ?? 0) },
    { label: 'Избранное', count: Number(c.favorites ?? 0) },
    { label: 'Правила доступа', count: Number(c.access_rules ?? 0) },
    { label: 'Привязки витрин', count: Number(c.storefront_links ?? c.storefronts ?? 0) }
  ]
})

const normalizedBlockers = computed<string[]>(() => {
  if (!preview.value) return []
  const raw = preview.value.blockers
  if (!raw) return []

  if (Array.isArray(raw)) {
    return raw.map(b => {
      if (typeof b === 'string') return b
      if (typeof b === 'object' && b !== null) {
        const item = b as Record<string, unknown>
        return (item.reason || item.message || item.description || item.type || JSON.stringify(item)) as string
      }
      return String(b)
    })
  }

  if (typeof raw === 'object') {
    const list: string[] = []
    for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
      if (Array.isArray(val) && val.length > 0) {
        val.forEach(item => {
          if (typeof item === 'string') {
            list.push(item)
          } else if (typeof item === 'object' && item !== null) {
            const obj = item as Record<string, unknown>
            list.push((obj.reason || obj.message || obj.description || `${key}: ${obj.name || obj.id || obj.vin || 'блокирующий объект'}`) as string)
          }
        })
      } else if (typeof val === 'string' && val.trim()) {
        list.push(val)
      }
    }
    return list
  }

  return []
})

const hasBlockers = computed(() => {
  if (!preview.value) return false
  if (preview.value.can_delete === false) return true
  return normalizedBlockers.value.length > 0
})

const normalizedRetained = computed<string[]>(() => {
  if (!preview.value?.retained) return []
  return preview.value.retained.map(r => {
    if (typeof r === 'string') return r
    if (typeof r === 'object' && r !== null) {
      const obj = r as Record<string, unknown>
      return (obj.reason || obj.message || (obj.name ? `${obj.entity_type || 'Объект'} «${obj.name}» используется в других записях` : JSON.stringify(obj))) as string
    }
    return String(r)
  })
})

const canConfirmDelete = computed(() => {
  return (
    isConfirmationValid.value &&
    !hasBlockers.value &&
    !deleting.value &&
    !loading.value &&
    Boolean(preview.value)
  )
})

const fetchPreview = async () => {
  loading.value = true
  loadError.value = ''
  submitError.value = ''
  preview.value = null

  try {
    const res = await api.getDeletePreview(props.warehouse.id)
    preview.value = res
  } catch (err: unknown) {
    console.error('Error fetching warehouse delete preview:', err)
    const error = err as {
      data?: { detail?: string; error?: string; message?: string }
      message?: string
    }
    loadError.value = error.data?.detail || error.data?.error || error.data?.message || error.message || 'Ошибка при загрузке информации об удалении склада.'
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  if (deleting.value) return
  emit('close')
}

const onBackdropClick = () => {
  if (deleting.value) return
  handleClose()
}

const onEscKey = () => {
  if (deleting.value) return
  handleClose()
}

const handleEnterPress = () => {
  if (canConfirmDelete.value) {
    void handleDelete()
  }
}

const handleDelete = async () => {
  if (!canConfirmDelete.value || !preview.value || deleting.value) return
  deleting.value = true
  submitError.value = ''

  try {
    const res = await api.cascadeDeleteWarehouse(props.warehouse.id, {
      confirmation: confirmationText.value.trim(),
      preview_token: preview.value.preview_token
    })

    toast.success('Склад и связанные данные успешно удалены')
    emit('success', res)
    emit('close')
  } catch (err: unknown) {
    console.error('Error cascade deleting warehouse:', err)
    const error = err as {
      statusCode?: number
      status?: number
      data?: { message?: string; detail?: string; error?: string; code?: string }
      message?: string
    }
    const status = error.statusCode || error.status
    const message = error.data?.detail || error.data?.message || error.data?.error || error.message || 'Ошибка при каскадном удалении склада.'

    if (status === 409) {
      submitError.value = `План каскадного удаления устарел: ${message}. Данные предпросмотра обновлены, введите подтверждение повторно.`
      confirmationText.value = ''
      await fetchPreview()
    } else {
      submitError.value = message
    }
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  fetchPreview()
})
</script>
