<template>
  <Modal
    :show="show"
    :title="modalTitle"
    size="2xl"
    max-height="screen"
    :closable="!deleting"
    :close-on-overlay="!deleting"
    :show-header="true"
    :show-footer="true"
    body-class="p-6 max-h-[calc(100vh-16rem)] overflow-y-auto"
    @close="handleClose"
  >
    <!-- Loading state -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-12 gap-3" aria-busy="true">
      <ArrowPathIcon class="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
      <p class="text-sm text-gray-500">Загрузка информации об удалении…</p>
    </div>

    <!-- Loading error state -->
    <div v-else-if="fetchError" class="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800" role="alert">
      <div class="flex items-center gap-2 font-semibold">
        <ExclamationTriangleIcon class="w-5 h-5 text-red-600 flex-shrink-0" aria-hidden="true" />
        <span>Не удалось получить информацию об удалении</span>
      </div>
      <p class="mt-1 text-red-700">{{ fetchError }}</p>
      <button
        type="button"
        class="mt-3 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-100 hover:bg-red-200 rounded"
        @click="loadPreview"
      >
        Повторить запрос
      </button>
    </div>

    <!-- Loaded preview content -->
    <div v-else-if="preview" class="space-y-4 text-gray-900">
      <!-- Stale notice message -->
      <div
        v-if="staleNotice"
        class="flex items-start gap-3 p-3 text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded-lg"
        role="alert"
      >
        <InformationCircleIcon class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div>{{ staleNotice }}</div>
      </div>

      <!-- Irreversible action warning -->
      <div class="flex items-start gap-3 p-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg">
        <ExclamationTriangleIcon class="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <strong>Действие необратимо.</strong> Восстановить данные можно только повторным импортом.
        </div>
      </div>

      <!-- BLOCKERS: Removal not allowed -->
      <div v-if="hasBlockers" class="p-4 bg-red-50 border border-red-200 rounded-lg space-y-4" role="alert">
        <div class="flex items-center gap-2">
          <ExclamationCircleIcon class="w-6 h-6 text-red-600 flex-shrink-0" aria-hidden="true" />
          <h4 class="text-base font-bold text-red-900">Удаление невозможно</h4>
        </div>
        <p class="text-sm text-red-700">
          Обнаружены блокирующие связи. Для продолжения необходимо их устранить.
        </p>

        <!-- Product blockers -->
        <div v-if="preview.blockers.products.length > 0" class="space-y-2">
          <h5 class="text-sm font-semibold text-red-900">
            Объявления участвуют в заявках или заказах ({{ preview.blockers.products.length }}):
          </h5>
          <div class="max-h-48 overflow-y-auto space-y-2 pr-1">
            <div
              v-for="pb in preview.blockers.products"
              :key="pb.product.id"
              class="p-2.5 bg-white border border-red-100 rounded text-xs space-y-1"
            >
              <div class="font-medium text-gray-900 flex items-center justify-between">
                <span>
                  {{ pb.product.name || 'Объявление' }}
                  <span v-if="pb.product.code" class="text-gray-500 font-normal">({{ pb.product.code }})</span>
                </span>
                <span v-if="pb.vin" class="text-gray-500 font-mono">VIN: {{ pb.vin }}</span>
              </div>
              <div class="text-gray-600 pl-2 border-l-2 border-red-200 space-y-0.5">
                <div v-for="doc in pb.documents" :key="doc.id">
                  <span class="font-medium">{{ documentTypeLabel(doc.type) }}</span>
                  <span v-if="doc.number"> № {{ doc.number }}</span>
                  <span class="text-gray-500"> (статус: {{ doc.status }})</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Distributor blockers -->
        <div v-if="preview.blockers.distributors.length > 0" class="space-y-2">
          <h5 class="text-sm font-semibold text-red-900">
            Марка привязана к дистрибьюторам ({{ preview.blockers.distributors.length }}):
          </h5>
          <p class="text-xs text-red-700 font-medium">Сначала отвяжите марку в настройках дистрибьютора.</p>
          <ul class="space-y-1 text-xs">
            <li
              v-for="dist in preview.blockers.distributors"
              :key="dist.company.id"
              class="p-2 bg-white border border-red-100 rounded flex items-center justify-between"
            >
              <span class="font-medium text-gray-900">{{ dist.company.name }}</span>
              <span class="text-gray-500 font-mono">ИНН: {{ dist.company.inn }}</span>
            </li>
          </ul>
        </div>

        <!-- Support program blockers -->
        <div v-if="preview.blockers.support_programs.length > 0" class="space-y-2">
          <h5 class="text-sm font-semibold text-red-900">
            Используется в программах поддержки ({{ preview.blockers.support_programs.length }}):
          </h5>
          <p class="text-xs text-red-700 font-medium">Сначала уберите её из условий программы.</p>
          <div class="space-y-2 text-xs">
            <div
              v-for="(sp, idx) in preview.blockers.support_programs"
              :key="idx"
              class="p-2 bg-white border border-red-100 rounded space-y-1"
            >
              <div class="flex items-center justify-between font-medium text-gray-900">
                <span>{{ sp.program.name }}</span>
                <span
                  :class="sp.program.is_active ? 'text-green-700 bg-green-50' : 'text-gray-600 bg-gray-100'"
                  class="px-1.5 py-0.5 rounded text-[11px]"
                >
                  {{ sp.program.is_active ? 'Активна' : 'Неактивна' }}
                </span>
              </div>
              <div v-if="sp.program.starts_at || sp.program.ends_at" class="text-gray-500 text-[11px]">
                Период: {{ formatDate(sp.program.starts_at) }} — {{ formatDate(sp.program.ends_at) }}
              </div>
              <div v-if="sp.references && sp.references.length > 0" class="text-gray-600 text-[11px]">
                Удаляемые объекты:
                <span class="font-medium">
                  {{ sp.references.map(r => `${getEntityLabel(r.type)} «${r.name || r.code || r.id}»`).join(', ') }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Kit sources blockers -->
        <div v-if="preview.blockers.kit_sources && preview.blockers.kit_sources.length > 0" class="space-y-2">
          <h5 class="text-sm font-semibold text-red-900">
            Используется в комплектах ({{ preview.blockers.kit_sources.length }}):
          </h5>
          <p class="text-xs text-red-700 font-medium">Это объявление является надстройкой для комплектов. Сначала отвяжите или удалите комплекты.</p>
          <div class="space-y-2 text-xs">
            <div
              v-for="ks in preview.blockers.kit_sources"
              :key="ks.product.id"
              class="p-2.5 bg-white border border-red-100 rounded space-y-1.5"
            >
              <div class="font-medium text-gray-900">
                {{ ks.product.title || ks.product.code }}
                <span v-if="ks.product.code" class="text-gray-500 font-normal">({{ ks.product.code }})</span>
              </div>
              <div v-if="ks.kits && ks.kits.length > 0" class="text-gray-600 pl-2 border-l-2 border-red-200 space-y-0.5">
                <div v-for="kit in ks.kits" :key="kit.id">
                  <span>{{ kit.title || kit.code }}</span>
                  <span v-if="kit.code" class="text-gray-500 font-normal"> ({{ kit.code }})</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- NO BLOCKERS: Show cascade details & confirmation -->
      <template v-else>
        <!-- Will be deleted permanently -->
        <div v-if="preview.delete.length > 0" class="space-y-2">
          <h4 class="text-sm font-bold text-gray-900">Будет удалено навсегда:</h4>
          <div class="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
            <div v-for="group in preview.delete" :key="group.type" class="overflow-hidden">
              <button
                type="button"
                class="w-full px-3 py-2.5 flex items-center justify-between text-left text-sm font-medium hover:bg-gray-50 transition-colors"
                @click="toggleGroup(group.type)"
              >
                <span class="font-semibold text-gray-900">{{ formatEntityCount(group.type, group.count) }}</span>
                <ChevronDownIcon
                  class="w-4 h-4 text-gray-400 transition-transform duration-200"
                  :class="{ 'rotate-180': isGroupExpanded(group.type) }"
                />
              </button>
              <div v-if="isGroupExpanded(group.type)" class="px-3 pb-3 pt-1 text-xs bg-gray-50 border-t border-gray-100">
                <ul class="space-y-1 max-h-40 overflow-y-auto pr-1">
                  <li v-for="item in group.items" :key="item.id" class="text-gray-700">
                    <span>{{ item.name || item.code || item.id }}</span>
                    <span v-if="item.name && item.code" class="text-gray-400 ml-1">({{ item.code }})</span>
                  </li>
                </ul>
                <p v-if="group.truncated || group.count > group.items.length" class="mt-2 text-gray-500 italic">
                  и ещё {{ formatEntityCount(group.type, group.count - group.items.length) }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Will be modified -->
        <div v-if="preview.unlink.length > 0 || preview.clear.length > 0" class="space-y-2">
          <h4 class="text-sm font-bold text-gray-900">Будут изменены:</h4>
          <ul class="space-y-1 text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-lg p-3">
            <li v-for="(unlink, idx) in preview.unlink" :key="`unlink-${idx}`" class="flex items-start gap-2">
              <span class="text-amber-500 font-bold">•</span>
              <span>{{ unlink.description }}</span>
            </li>
            <li v-for="(clear, idx) in preview.clear" :key="`clear-${idx}`" class="flex items-start gap-2">
              <span class="text-amber-500 font-bold">•</span>
              <span>{{ clear.description }}</span>
            </li>
          </ul>
        </div>

        <!-- Will impact users -->
        <div
          v-if="preview.user_impact && (preview.user_impact.cart_items > 0 || preview.user_impact.favorites > 0)"
          class="space-y-1 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900"
        >
          <h4 class="font-bold">Затронет пользователей:</h4>
          <p v-if="preview.user_impact.cart_items > 0">
            Товаров в корзинах: <strong>{{ preview.user_impact.cart_items }}</strong>
          </p>
          <p v-if="preview.user_impact.favorites > 0">
            В избранном у пользователей: <strong>{{ preview.user_impact.favorites }}</strong>
          </p>
        </div>

        <!-- Confirmation input -->
        <div class="space-y-1.5 pt-2 border-t border-gray-200">
          <label for="cascade-delete-confirmation" class="block text-sm font-medium text-gray-800">
            Для подтверждения введите <span class="font-bold text-red-600 tracking-wider">УДАЛИТЬ</span>:
          </label>
          <input
            id="cascade-delete-confirmation"
            ref="confirmationInputRef"
            v-model="confirmationText"
            type="text"
            placeholder="УДАЛИТЬ"
            autocomplete="off"
            autocorrect="off"
            spellcheck="false"
            :disabled="deleting"
            class="w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none transition-colors"
            :class="[
              isConfirmationValid
                ? 'border-red-500 focus:ring-2 focus:ring-red-500 focus:border-red-500'
                : 'border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            ]"
            @keydown.enter.prevent="handleEnterPress"
          />
          <p v-if="confirmationText && !isConfirmationValid" class="text-xs text-red-600">
            Слово подтверждения должно быть введено заглавными русскими буквами без пробелов: УДАЛИТЬ
          </p>
        </div>
      </template>

      <!-- Submit error -->
      <div v-if="submitError" class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800" role="alert">
        {{ submitError }}
      </div>
    </div>

    <!-- Modal Footer -->
    <template #footer>
      <div class="flex items-center justify-end gap-3 w-full">
        <button
          ref="cancelButtonRef"
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          :disabled="deleting"
          @click="handleClose"
        >
          {{ hasBlockers ? 'Закрыть' : 'Отмена' }}
        </button>
        <button
          v-if="!hasBlockers && preview"
          type="button"
          class="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          :disabled="!canConfirmDelete"
          @click="executeCascadeDelete"
        >
          <ArrowPathIcon v-if="deleting" class="w-4 h-4 animate-spin" aria-hidden="true" />
          <span>{{ deleting ? 'Удаляем…' : 'Удалить навсегда' }}</span>
        </button>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ChevronDownIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/vue/24/outline'
import Modal from '~/components/ui/Modal.vue'
import type {
  CascadeBlockers,
  CascadeDeleteResult,
  CascadePreviewResource,
  CatalogEntity,
} from './types'
import { createCatalogCorrectionApi, type CatalogCorrectionApi } from './api'
import {
  formatEntityCount,
  getEntityAccusative,
  getEntityLabel,
} from './pluralization'

const props = defineProps<{
  show: boolean
  entity: CatalogEntity | string
  entityId: string
  entityName?: string
  entityCode?: string
  etag?: string
  api?: CatalogCorrectionApi
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'deleted', result: CascadeDeleteResult): void
}>()

const toast = useToast()
const defaultApi = createCatalogCorrectionApi(useRuntimeConfig())
const api = computed(() => props.api ?? defaultApi)

const loading = ref(false)
const deleting = ref(false)
const fetchError = ref('')
const submitError = ref('')
const staleNotice = ref('')
const preview = ref<CascadePreviewResource | null>(null)
const confirmationText = ref('')
const expandedGroups = ref<Set<string>>(new Set())

const confirmationInputRef = ref<HTMLInputElement | null>(null)
const cancelButtonRef = ref<HTMLButtonElement | null>(null)

const modalTitle = computed(() => {
  const entityType = preview.value?.root.type || props.entity
  const accusative = getEntityAccusative(entityType)
  const name = preview.value?.root.name || preview.value?.root.code || props.entityName || props.entityCode || ''
  return name ? `Удалить ${accusative} «${name}»?` : `Удалить ${accusative}?`
})

const hasBlockers = computed(() => {
  if (!preview.value) return false
  const b = preview.value.blockers
  return (
    (b?.products?.length ?? 0) > 0 ||
    (b?.distributors?.length ?? 0) > 0 ||
    (b?.support_programs?.length ?? 0) > 0
  )
})

const isConfirmationValid = computed(() => {
  return confirmationText.value.trim() === 'УДАЛИТЬ'
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

const isGroupExpanded = (type: string) => expandedGroups.value.has(type)

const toggleGroup = (type: string) => {
  const next = new Set(expandedGroups.value)
  if (next.has(type)) {
    next.delete(type)
  } else {
    next.add(type)
  }
  expandedGroups.value = next
}

const documentTypeLabel = (type: string): string => {
  const normalized = type.toLowerCase()
  if (normalized.includes('application')) return 'Заявка'
  if (normalized.includes('order')) return 'Заказ'
  if (normalized.includes('exchange')) return 'Заявка на обмен'
  return type
}

const formatDate = (iso?: string | null): string => {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleDateString('ru-RU')
  } catch {
    return iso
  }
}

const failureMessage = (error: unknown): string => {
  if (!error || typeof error !== 'object') return 'Неизвестная ошибка'
  const failure = error as {
    message?: string
    data?: {
      message?: string
      detail?: unknown
      error?: { message?: string }
    }
  }
  if (failure.data?.error?.message) return failure.data.error.message
  if (typeof failure.data?.detail === 'string') return failure.data.detail
  if (failure.data?.message) return failure.data.message
  return failure.message || 'Ошибка выполнения операции'
}

const loadPreview = async () => {
  if (!props.entity || !props.entityId) return
  loading.value = true
  fetchError.value = ''
  submitError.value = ''
  staleNotice.value = ''
  preview.value = null
  confirmationText.value = ''
  expandedGroups.value = new Set()

  try {
    const result = await api.value.getDeletePreview(props.entity, props.entityId)
    preview.value = result
    // Expand groups by default if only 1 group
    if (result.delete.length === 1) {
      expandedGroups.value = new Set([result.delete[0].type])
    }
    await nextTick()
    if (hasBlockers.value) {
      cancelButtonRef.value?.focus()
    } else {
      confirmationInputRef.value?.focus()
    }
  } catch (error: unknown) {
    fetchError.value = failureMessage(error)
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  if (deleting.value) return
  emit('close')
}

const handleEnterPress = () => {
  if (canConfirmDelete.value) {
    void executeCascadeDelete()
  }
}

const executeCascadeDelete = async () => {
  if (!canConfirmDelete.value || !preview.value) return
  deleting.value = true
  submitError.value = ''
  staleNotice.value = ''

  try {
    const result = await api.value.cascadeDelete(
      props.entity,
      props.entityId,
      {
        confirmation: confirmationText.value.trim(),
        preview_token: preview.value.preview_token,
      },
      props.etag,
    )

    const deletedCounts = result.deleted || {}
    const totalDeleted = Object.values(deletedCounts).reduce((sum, n) => sum + (Number(n) || 0), 0)
    toast.success(`Удалено записей: ${totalDeleted}`)
    emit('deleted', result)
    emit('close')
  } catch (error: unknown) {
    const err = error as {
      status?: number
      statusCode?: number
      data?: {
        code?: string
        message?: string
        detail?: unknown
        preview?: CascadePreviewResource
        blockers?: CascadeBlockers
        error?: { code?: string; message?: string }
      }
      response?: {
        status?: number
        _data?: {
          code?: string
          preview?: CascadePreviewResource
          blockers?: CascadeBlockers
          error?: { code?: string; message?: string }
        }
      }
    }

    const status = err.status || err.statusCode || err.response?.status
    const data = err.data || err.response?._data
    const code = data?.code || data?.error?.code

    if (status === 409 && code === 'CASCADE_PREVIEW_STALE') {
      if (data?.preview) {
        preview.value = data.preview
      } else {
        await loadPreview()
      }
      confirmationText.value = ''
      staleNotice.value = 'Данные изменились, проверьте список ещё раз'
      await nextTick()
      confirmationInputRef.value?.focus()
    } else if (status === 409 && (code === 'CASCADE_DELETE_BLOCKED' || data?.blockers)) {
      if (data?.blockers && preview.value) {
        preview.value.blockers = data.blockers
      } else {
        await loadPreview()
      }
      submitError.value = 'Удаление невозможно: появились блокирующие документы или связи'
      await nextTick()
      cancelButtonRef.value?.focus()
    } else if (status === 400 && code === 'CASCADE_CONFIRMATION_INVALID') {
      submitError.value = 'Неверное слово подтверждения. Введите УДАЛИТЬ'
    } else {
      submitError.value = failureMessage(error)
    }
  } finally {
    deleting.value = false
  }
}

watch(
  () => props.show,
  show => {
    if (show) {
      void loadPreview()
    } else {
      preview.value = null
      confirmationText.value = ''
      submitError.value = ''
      fetchError.value = ''
      staleNotice.value = ''
    }
  },
  { immediate: true },
)
</script>
