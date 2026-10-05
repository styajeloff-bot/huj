<template>
  <Modal
    :show="true"
    :title="replaceVehicle ? 'Заменить позицию' : 'Добавить технику'"
    :subtitle="replaceVehicle ? `Заменяется: ${vehicleTitle(replaceVehicle)} · ${replaceVehicle.vin}` : undefined"
    size="4xl"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <p v-if="replaceVehicle" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Новая позиция заменит выбранную. Прежняя останется в истории сделки, её резерв будет снят.
      </p>

      <div role="tablist" aria-label="Способ добавления" class="flex gap-1 border-b border-gray-200">
        <button
          v-for="item in tabs"
          :key="item.key"
          type="button"
          role="tab"
          :aria-selected="tab === item.key"
          class="px-4 py-2 text-sm font-medium -mb-px border-b-2"
          :class="tab === item.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-600 hover:text-gray-900'"
          :disabled="ctx.busy.value"
          @click="switchTab(item.key)"
        >
          {{ item.label }}
        </button>
      </div>

      <div role="tabpanel">
        <FastDealVehicleVinSearch
          v-if="tab === 'vin'"
          :busy="ctx.busy.value"
          :error="error"
          :existing-vins="existingVins"
          :action-label="actionLabel"
          @pick="body => submit([body])"
          @manual="goManual"
        />
        <FastDealVehicleTable
          v-else-if="tab === 'table'"
          :multiple="!replaceVehicle"
          :busy="ctx.busy.value"
          :error="error"
          :existing-vins="existingVins"
          :action-label="actionLabel"
          @pick="submit"
        />
        <FastDealVehicleManualForm
          v-else
          :deal="deal"
          :initial-vin="manualVin"
          :busy="ctx.busy.value"
          :error="error"
          :action-label="actionLabel"
          @submit="body => submit([body])"
        />
      </div>

      <p v-if="progress" class="text-sm text-gray-600" role="status">{{ progress }}</p>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { vehicleTitle } from '../composables/fastDealCardFormat'
import type { AddVehicleBody, FastDealCard, FastDealVehicle } from '../types'
import FastDealVehicleManualForm from './FastDealVehicleManualForm.vue'
import FastDealVehicleTable from './FastDealVehicleTable.vue'
import FastDealVehicleVinSearch from './FastDealVehicleVinSearch.vue'

type Tab = 'vin' | 'table' | 'manual'

const props = defineProps<{ deal: FastDealCard; replaceVehicle?: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const tab = ref<Tab>('vin')
const manualVin = ref('')
const error = ref<ActionFailure | null>(null)
const progress = ref('')

const tabs: { key: Tab; label: string }[] = [
  { key: 'vin', label: 'Поиск по VIN' },
  { key: 'table', label: 'Выбор из таблицы' },
  { key: 'manual', label: 'Добавить вручную' },
]

const actionLabel = computed(() => (props.replaceVehicle ? 'Заменить позицию' : 'Добавить в сделку'))
const existingVins = computed(() => ctx.activeVehicles.value.filter(item => item.id !== props.replaceVehicle?.id).map(item => item.vin))

function switchTab(next: Tab) {
  error.value = null
  progress.value = ''
  tab.value = next
}

/** «Не найдено на ваших складах» → manual form keeping the typed VIN. */
function goManual(vin: string) {
  manualVin.value = vin
  switchTab('manual')
}

/**
 * Units are added one by one: every request carries the etag of the previous answer. A reset
 * confirmation (DD under review) is asked once, before the first change.
 */
async function submit(bodies: AddVehicleBody[]) {
  error.value = null
  progress.value = ''
  if (!(await ctx.confirmEdit())) return
  let done = 0
  for (const body of bodies) {
    const result = await ctx.run((etag, card) =>
      props.replaceVehicle
        ? ctx.api.patchVehicle(card.id, props.replaceVehicle.id, etag, { replace_with: body })
        : ctx.api.addVehicle(card.id, etag, body),
    )
    if (!result.ok) {
      error.value = result.error
      if (bodies.length > 1) progress.value = `Добавлено ${done} из ${bodies.length}. Остальные не добавлены — исправьте ошибку и повторите.`
      return
    }
    done += 1
  }
  emit('close')
}
</script>
