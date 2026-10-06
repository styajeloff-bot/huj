<template>
  <Modal
    :show="true"
    title="Опции позиции"
    :subtitle="`${vehicleTitle(vehicle)} · ${vehicle.vin}`"
    size="3xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-options-form" class="space-y-6" novalidate @submit.prevent="submit">
      <p class="text-sm text-gray-600">
        Сохраняется полный набор опций: он заменяет прежний целиком. Удалённые значения попадут в историю сделки.
      </p>
      <p v-if="lookupFailed" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        Не удалось загрузить справочники.
        <button type="button" class="underline" @click="loadLookups">Повторить</button>
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <FastDealVehicleOptionRows
          v-model:rows="equipments"
          title="Оборудование"
          add-label="Выберите оборудование"
          :catalog="equipmentCatalog"
          :loading="loadingLookups"
          :disabled="ctx.busy.value"
          :error="fieldError('equipments')"
        />
        <FastDealVehicleOptionRows
          v-model:rows="services"
          title="Услуги"
          add-label="Выберите услугу"
          :catalog="serviceCatalog"
          :loading="loadingLookups"
          :disabled="ctx.busy.value"
          :error="fieldError('services')"
        />
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <FastDealVehicleOptionChecklist
          v-model:selected="purposes"
          title="Назначения"
          :catalog="purposeCatalog"
          :loading="loadingLookups"
          :disabled="ctx.busy.value"
          :error="fieldError('purposes')"
        />
        <FastDealVehicleOptionChecklist
          v-model:selected="regions"
          title="Регионы"
          searchable
          :catalog="regionCatalog"
          :loading="loadingLookups"
          :disabled="ctx.busy.value"
          :error="fieldError('regions')"
        />
      </div>

      <p v-if="rowsError" role="alert" class="text-sm text-red-600">{{ rowsError }}</p>
      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button
        type="submit"
        form="fast-deal-options-form"
        class="btn-primary"
        :disabled="ctx.busy.value || loadingLookups"
        :aria-busy="ctx.busy.value"
      >
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить опции' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { lookupCode, lookupName, parseMoneyInput, vehicleTitle, type ChecklistEntry, type OptionRow } from '../composables/fastDealCardFormat'
import type { LookupItem } from '../api/fastDealsApi'
import type { FastDealVehicle, OptionItem, OptionsBody } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealVehicleOptionChecklist from './FastDealVehicleOptionChecklist.vue'
import FastDealVehicleOptionRows from './FastDealVehicleOptionRows.vue'

const props = defineProps<{ vehicle: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()

const toRows = (items: OptionItem[]): OptionRow[] =>
  items.map(item => ({ code: item.code, name: item.name ?? item.code, price: item.price, comment: item.comment ?? '' }))

const equipments = ref<OptionRow[]>(toRows(props.vehicle.equipments))
const services = ref<OptionRow[]>(toRows(props.vehicle.services))
const purposes = ref<string[]>([...props.vehicle.purposes])
const regions = ref<string[]>([...props.vehicle.regions])

const equipmentCatalog = ref<LookupItem[]>([])
const serviceCatalog = ref<LookupItem[]>([])
const purposeCatalog = ref<ChecklistEntry[]>([])
const regionCatalog = ref<ChecklistEntry[]>([])
const loadingLookups = ref(true)
const lookupFailed = ref(false)

const rowsError = ref('')
const serverError = ref<ActionFailure | null>(null)

const OPTION_FIELDS = ['equipments', 'services', 'purposes', 'regions']
const fieldError = (field: string) => (serverError.value?.field === field ? serverError.value.detail : null)
const generalError = computed(() =>
  serverError.value && !(serverError.value.field && OPTION_FIELDS.includes(serverError.value.field)) ? serverError.value : null,
)

/** Purposes and regions are stored by their directory code and shown by the display name. */
const toEntry = (item: LookupItem): ChecklistEntry => ({ value: lookupCode(item), label: lookupName(item) })

async function loadLookups() {
  loadingLookups.value = true
  lookupFailed.value = false
  try {
    const [equipmentResponse, serviceResponse, purposeResponse, regionResponse] = await Promise.all([
      ctx.api.lookup('equipments'),
      ctx.api.lookup('services'),
      ctx.api.lookup('purposes'),
      ctx.api.lookup('regions'),
    ])
    equipmentCatalog.value = equipmentResponse.items
    serviceCatalog.value = serviceResponse.items
    purposeCatalog.value = purposeResponse.items.map(toEntry)
    regionCatalog.value = regionResponse.items.map(toEntry)
  } catch {
    lookupFailed.value = true
  } finally {
    loadingLookups.value = false
  }
}

function toBody(): OptionsBody | null {
  const convert = (rows: OptionRow[]) => {
    const converted: OptionsBody['equipments'] = []
    for (const row of rows) {
      const price = parseMoneyInput(row.price)
      if (price === null) return null
      converted.push({ code: row.code, price, comment: row.comment.trim() || null })
    }
    return converted
  }
  const equipmentItems = convert(equipments.value)
  const serviceItems = convert(services.value)
  if (!equipmentItems || !serviceItems) return null
  return { equipments: equipmentItems, services: serviceItems, purposes: purposes.value, regions: regions.value }
}

async function submit() {
  serverError.value = null
  rowsError.value = ''
  const body = toBody()
  if (!body) {
    rowsError.value = 'У каждой выбранной опции должна быть корректная цена (например, 15000.00)'
    return
  }
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.options(card.id, props.vehicle.id, etag, body))
  if (result.ok) emit('close')
  else serverError.value = result.error
}

onMounted(loadLookups)
</script>
