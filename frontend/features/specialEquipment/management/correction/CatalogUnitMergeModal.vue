<template>
  <Modal
    :show="show"
    title="Объединение единицы измерения"
    size="lg"
    :closable="!merging"
    :close-on-overlay="!merging"
    :show-header="true"
    :show-footer="true"
    @close="handleClose"
  >
    <div class="space-y-4 text-gray-900">
      <div v-if="errorMessage" class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800" role="alert">
        <div class="flex items-center gap-2 font-semibold">
          <ExclamationTriangleIcon class="w-5 h-5 text-red-600 flex-shrink-0" aria-hidden="true" />
          <span>Не удалось объединить единицу измерения</span>
        </div>
        <p class="mt-1 text-red-700">{{ errorMessage }}</p>
      </div>

      <div class="flex items-start gap-3 p-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg">
        <ExclamationTriangleIcon class="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <strong>Действие необратимо.</strong>
          Все характеристики (<span class="font-bold">{{ sourceUnit?.attribute_count ?? 0 }}</span>),
          использующие единицу «<span class="font-medium">{{ sourceUnit?.name }}</span>» ({{ sourceUnit?.code }}),
          будут перепривязаны к целевой единице. Исходная запись будет удалена.
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">
          Целевая активная единица измерения <b class="text-red-500">*</b>
        </label>
        <CatalogSearchableSelect
          :model-value="targetUnitId"
          :options="targetOptions"
          label="Целевая единица измерения"
          placeholder="Выберите единицу измерения для объединения"
          @change="targetUnitId = $event ?? ''"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          :disabled="merging"
          @click="handleClose"
        >
          Отмена
        </button>
        <button
          type="button"
          class="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!canConfirm"
          @click="handleConfirm"
        >
          <ArrowPathIcon v-if="merging" class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
          {{ merging ? 'Объединение…' : 'Объединить' }}
        </button>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { CatalogNamedRef, CatalogUnit } from './types'
import CatalogSearchableSelect from './CatalogSearchableSelect.vue'

const props = defineProps<{
  show: boolean
  sourceUnit: CatalogUnit | null
  units: CatalogUnit[]
  etag: string
}>()

const emit = defineEmits<{
  close: []
  confirm: [targetUnitId: UUID]
}>()

const targetUnitId = ref<string>('')
const merging = ref(false)
const errorMessage = ref('')

watch(() => props.show, (isOpen) => {
  if (isOpen) {
    targetUnitId.value = ''
    errorMessage.value = ''
    merging.value = false
  }
})

const targetOptions = computed<CatalogNamedRef[]>(() => {
  if (!props.sourceUnit) return []
  return props.units
    .filter(u => u.is_active && u.id !== props.sourceUnit?.id)
    .map(u => ({
      id: u.id,
      name: `${u.name} (${u.code})`,
      code: u.code,
    }))
})

const canConfirm = computed(() =>
  Boolean(targetUnitId.value) && !merging.value && Boolean(props.sourceUnit)
)

const handleClose = () => {
  if (!merging.value) {
    emit('close')
  }
}

const handleConfirm = () => {
  if (!canConfirm.value || !targetUnitId.value) return
  emit('confirm', targetUnitId.value as UUID)
}
</script>
