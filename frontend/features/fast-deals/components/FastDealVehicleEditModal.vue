<template>
  <Modal
    :show="true"
    title="Изменить данные позиции"
    :subtitle="`${vehicleTitle(vehicle)} · ${vehicle.vin}`"
    size="2xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-vehicle-edit-form" class="space-y-4" novalidate @submit.prevent="submit">
      <p v-if="ctx.party.value === 'dealer'" class="text-sm text-gray-600">
        Изменения не применяются сразу к условиям лизинговой компании: они попадут в список правок, который вы отправите ей на согласование.
      </p>
      <p v-if="!hasEditableFields" class="text-sm text-gray-600">
        Данные каталожной позиции в сделке не редактируются. Цену можно скорректировать скидкой или наценкой.
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FastDealCardField v-if="canEditVin" label="VIN" required for-id="fast-deal-edit-vin" :error="errorOf('vin')">
          <input
            id="fast-deal-edit-vin"
            v-model="vin"
            type="text"
            maxlength="32"
            autocomplete="off"
            class="input-field font-mono uppercase"
            :class="errorOf('vin') ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
          />
        </FastDealCardField>
        <FastDealCardField v-if="canEditPrice" label="Цена, ₽" required for-id="fast-deal-edit-price" :error="errorOf('price')">
          <input
            id="fast-deal-edit-price"
            v-model="price"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            class="input-field tabular-nums"
            :class="errorOf('price') ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
          />
        </FastDealCardField>
        <template v-if="canEditText">
          <FastDealCardField label="Марка" required for-id="fast-deal-edit-mark" :error="errorOf('mark_name')">
            <input id="fast-deal-edit-mark" v-model="markName" type="text" maxlength="255" class="input-field" :disabled="ctx.busy.value" />
          </FastDealCardField>
          <FastDealCardField label="Модель" required for-id="fast-deal-edit-model" :error="errorOf('model_name')">
            <input id="fast-deal-edit-model" v-model="modelName" type="text" maxlength="255" class="input-field" :disabled="ctx.busy.value" />
          </FastDealCardField>
          <FastDealCardField label="Модификация" for-id="fast-deal-edit-modification" :error="errorOf('modification_name')">
            <input id="fast-deal-edit-modification" v-model="modificationName" type="text" maxlength="255" class="input-field" :disabled="ctx.busy.value" />
          </FastDealCardField>
          <FastDealCardField label="Цвет" for-id="fast-deal-edit-color" :error="errorOf('body_color_name')">
            <input id="fast-deal-edit-color" v-model="colorName" type="text" maxlength="255" class="input-field" :disabled="ctx.busy.value" />
          </FastDealCardField>
        </template>
      </div>

      <template v-if="canEditClassification">
        <FastDealCardField
          label="Категория"
          for-id="fast-deal-edit-category"
          hint="Оставьте пустым, чтобы не менять"
          :error="errorOf('category_id')"
        >
          <FastDealCardLookupSelect id="fast-deal-edit-category" v-model="categoryId" kind="categories" placeholder="Не менять" />
        </FastDealCardField>
        <FastDealCardField label="Дилер" :error="errorOf('dealer_company_id')">
          <p v-if="fixedDealer" class="text-sm text-gray-900">{{ fixedDealer.name }}</p>
          <FastDealCardCompanyPicker v-else v-model="dealerIds" kind="dealers" :disabled="ctx.busy.value" />
        </FastDealCardField>
      </template>

      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button
        type="submit"
        form="fast-deal-vehicle-edit-form"
        class="btn-primary"
        :disabled="ctx.busy.value || !hasEditableFields"
        :aria-busy="ctx.busy.value"
      >
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { isPositiveMoney, parseMoneyInput, sameDecimal, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealCard, FastDealVehicle, PatchVehicleBody } from '../types'
import FastDealCardCompanyPicker from './FastDealCardCompanyPicker.vue'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'
import FastDealCardLookupSelect from './FastDealCardLookupSelect.vue'

const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/
const KNOWN_FIELDS = ['vin', 'price', 'mark_name', 'model_name', 'modification_name', 'body_color_name', 'category_id', 'dealer_company_id']

const props = defineProps<{ deal: FastDealCard; vehicle: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const manual = props.vehicle.vehicle_source_type === 'manual'

// What may be edited: a manual position (VIN, price; free text in DL), the VIN typed for a listing without one.
const canEditVin = manual || props.vehicle.vin_entered_manually
const canEditPrice = manual
const canEditText = manual && !ctx.isDD.value
const canEditClassification = manual && !ctx.isDD.value && ctx.party.value === 'initiator'
const hasEditableFields = canEditVin || canEditPrice || canEditText || canEditClassification
const fixedDealer = computed(() => props.deal.dealer_company ?? null)

const vin = ref(props.vehicle.vin)
const price = ref(props.vehicle.base_price ?? '')
const markName = ref(props.vehicle.mark_name)
const modelName = ref(props.vehicle.model_name)
const modificationName = ref(props.vehicle.modification_name ?? '')
const colorName = ref(props.vehicle.body_color_name ?? '')
const categoryId = ref('')
const dealerIds = ref<string[]>(props.vehicle.dealer_company_id ? [props.vehicle.dealer_company_id] : [])

const local = reactive<Record<string, string>>({})
const serverError = ref<ActionFailure | null>(null)

const errorOf = (field: string): string => local[field] || (serverError.value?.field === field ? serverError.value.detail : '')
const generalError = computed(() =>
  serverError.value && !(serverError.value.field && KNOWN_FIELDS.includes(serverError.value.field)) ? serverError.value : null,
)

async function submit() {
  serverError.value = null
  for (const key of Object.keys(local)) delete local[key]
  const body: PatchVehicleBody = {}

  if (canEditVin) {
    const typed = vin.value.trim().toUpperCase()
    if (!VIN_PATTERN.test(typed)) local.vin = 'VIN — 17 символов: латинские буквы (кроме I, O, Q) и цифры'
    else if (typed !== props.vehicle.vin) body.vin = typed
  }
  if (canEditPrice) {
    const parsed = parseMoneyInput(price.value)
    if (parsed === null || !isPositiveMoney(parsed)) local.price = 'Укажите цену, например 2500000.00'
    else if (!sameDecimal(parsed, props.vehicle.base_price)) body.price = parsed
  }
  if (canEditText) {
    if (!markName.value.trim()) local.mark_name = 'Укажите марку'
    else if (markName.value.trim() !== props.vehicle.mark_name) body.mark_name = markName.value.trim()
    if (!modelName.value.trim()) local.model_name = 'Укажите модель'
    else if (modelName.value.trim() !== props.vehicle.model_name) body.model_name = modelName.value.trim()
    if (modificationName.value.trim() !== (props.vehicle.modification_name ?? '')) body.modification_name = modificationName.value.trim()
    if (colorName.value.trim() !== (props.vehicle.body_color_name ?? '')) body.body_color_name = colorName.value.trim()
  }
  if (canEditClassification) {
    if (categoryId.value) body.category_id = categoryId.value
    const dealerId = fixedDealer.value?.id ?? dealerIds.value[0]
    if (dealerId && dealerId !== props.vehicle.dealer_company_id) body.dealer_company_id = dealerId
  }

  if (Object.keys(local).length > 0) return
  if (Object.keys(body).length === 0) {
    serverError.value = { detail: 'Ничего не изменено' }
    return
  }
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.patchVehicle(card.id, props.vehicle.id, etag, body))
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
