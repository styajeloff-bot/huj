<template>
  <form class="space-y-4" novalidate @submit.prevent="submit">
    <p class="text-sm text-gray-600">
      Ручная позиция не создаёт и не изменяет объявление каталога и не резервируется.
      Обязательные поля: категория, марка, модель, VIN и цена.
    </p>

    <!-- Dealer (DD): directory chain -->
    <template v-if="ctx.isDD.value">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FastDealCardField label="Категория" required for-id="fast-deal-manual-category" :error="errorOf('category_id')">
          <FastDealCardLookupSelect
            id="fast-deal-manual-category"
            v-model="categoryId"
            kind="categories"
            placeholder="Выберите категорию"
            :error="!!errorOf('category_id')"
            @select="onCategorySelect"
          />
        </FastDealCardField>
        <div></div>

        <div class="space-y-2">
          <FastDealCardField label="Марка" required for-id="fast-deal-manual-mark" :error="errorOf('mark_id') || errorOf('mark_name')">
            <FastDealCardLookupSelect
              v-if="!noMark"
              id="fast-deal-manual-mark"
              v-model="markId"
              kind="marks"
              placeholder="Выберите марку"
              :error="!!errorOf('mark_id')"
              @select="onMarkSelect"
            />
            <input
              v-else
              id="fast-deal-manual-mark"
              v-model="markName"
              type="text"
              maxlength="255"
              autocomplete="off"
              class="input-field"
              :class="errorOf('mark_name') ? 'border-red-500' : ''"
              placeholder="Название марки"
            />
          </FastDealCardField>
          <label class="inline-flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" class="rounded text-blue-600" :checked="noMark" @change="toggleNoMark" />
            Нет марки
          </label>
        </div>

        <div class="space-y-2">
          <FastDealCardField label="Модель" required for-id="fast-deal-manual-model" :error="errorOf('model_id') || errorOf('model_name')">
            <FastDealCardLookupSelect
              v-if="!noMark && !noModel"
              id="fast-deal-manual-model"
              v-model="modelId"
              kind="models"
              placeholder="Выберите модель"
              :params="{ mark_id: markId || undefined }"
              :requires="['mark_id']"
              :error="!!errorOf('model_id')"
              @select="onModelSelect"
            />
            <input
              v-else
              id="fast-deal-manual-model"
              v-model="modelName"
              type="text"
              maxlength="255"
              autocomplete="off"
              class="input-field"
              :class="errorOf('model_name') ? 'border-red-500' : ''"
              placeholder="Название модели"
            />
          </FastDealCardField>
          <label v-if="!noMark" class="inline-flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" class="rounded text-blue-600" :checked="noModel" :disabled="!markId" @change="toggleNoModel" />
            Нет модели
          </label>
        </div>
      </div>

      <div v-if="(noMark || noModel) && similarModels.length" class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm">
        <p class="font-medium text-blue-900 mb-2">Похожие модели каталога. Выберите, если это ваша техника:</p>
        <ul class="flex flex-wrap gap-2">
          <li v-for="item in similarModels" :key="String(item.id)">
            <button
              type="button"
              class="rounded-lg border border-blue-300 bg-white px-3 py-1 hover:bg-blue-100"
              @click="applySimilar(item)"
            >
              {{ similarLabel(item) }}
            </button>
          </li>
        </ul>
      </div>

      <div v-if="!noMark && !noModel && markId && modelId" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FastDealCardField label="Модификация" for-id="fast-deal-manual-modification" :error="errorOf('modification_id')">
          <FastDealCardLookupSelect
            id="fast-deal-manual-modification"
            v-model="modificationId"
            kind="modifications"
            placeholder="Не выбрана"
            :params="{ model_id: modelId }"
            :requires="['model_id']"
            @select="onModificationSelect"
          />
        </FastDealCardField>
        <FastDealCardField label="Комплектация" for-id="fast-deal-manual-trim" :error="errorOf('trim_id')">
          <FastDealCardLookupSelect
            id="fast-deal-manual-trim"
            v-model="trimId"
            kind="trims"
            placeholder="Не выбрана"
            :params="{ modification_id: modificationId || undefined }"
            :requires="['modification_id']"
          />
        </FastDealCardField>
      </div>

      <FastDealCardField label="Цвет кузова" for-id="fast-deal-manual-color" :error="errorOf('body_color_id')">
        <FastDealCardLookupSelect id="fast-deal-manual-color" v-model="colorId" kind="colors" placeholder="Не выбран" />
      </FastDealCardField>
    </template>

    <!-- Leasing company (DL): free text, directory category, explicit dealer -->
    <template v-else>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FastDealCardField label="Категория" required for-id="fast-deal-manual-category" :error="errorOf('category_id')">
          <FastDealCardLookupSelect
            id="fast-deal-manual-category"
            v-model="categoryId"
            kind="categories"
            placeholder="Выберите категорию"
            :error="!!errorOf('category_id')"
          />
        </FastDealCardField>
        <FastDealCardField label="Цвет" for-id="fast-deal-manual-color-name" :error="errorOf('body_color_name')">
          <input id="fast-deal-manual-color-name" v-model="colorName" type="text" maxlength="255" autocomplete="off" class="input-field" />
        </FastDealCardField>
        <FastDealCardField label="Марка" required for-id="fast-deal-manual-mark-name" :error="errorOf('mark_name')">
          <input
            id="fast-deal-manual-mark-name"
            v-model="markName"
            type="text"
            maxlength="255"
            autocomplete="off"
            class="input-field"
            :class="errorOf('mark_name') ? 'border-red-500' : ''"
          />
        </FastDealCardField>
        <FastDealCardField label="Модель" required for-id="fast-deal-manual-model-name" :error="errorOf('model_name')">
          <input
            id="fast-deal-manual-model-name"
            v-model="modelName"
            type="text"
            maxlength="255"
            autocomplete="off"
            class="input-field"
            :class="errorOf('model_name') ? 'border-red-500' : ''"
          />
        </FastDealCardField>
        <FastDealCardField label="Модификация" for-id="fast-deal-manual-modification-name" :error="errorOf('modification_name')">
          <input
            id="fast-deal-manual-modification-name"
            v-model="modificationName"
            type="text"
            maxlength="255"
            autocomplete="off"
            class="input-field"
          />
        </FastDealCardField>
      </div>

      <FastDealCardField label="Дилер" required :error="errorOf('dealer_company_id')">
        <p v-if="fixedDealer" class="text-sm text-gray-900">
          {{ fixedDealer.name }}
          <span class="block text-xs text-gray-500">После разделения сделки добавлять можно только позиции этого дилера.</span>
        </p>
        <FastDealCardCompanyPicker v-else v-model="dealerIds" kind="dealers" :disabled="busy" placeholder="Поиск дилера по названию или ИНН" />
      </FastDealCardField>
    </template>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <FastDealCardField label="VIN" required for-id="fast-deal-manual-vin" hint="17 символов: латинские буквы (кроме I, O, Q) и цифры" :error="errorOf('vin')">
        <input
          id="fast-deal-manual-vin"
          v-model="vin"
          type="text"
          maxlength="32"
          autocomplete="off"
          class="input-field font-mono uppercase"
          :class="errorOf('vin') ? 'border-red-500' : ''"
        />
      </FastDealCardField>
      <FastDealCardField label="Цена, ₽" required for-id="fast-deal-manual-price" :error="errorOf('price')">
        <input
          id="fast-deal-manual-price"
          v-model="price"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="input-field tabular-nums"
          :class="errorOf('price') ? 'border-red-500' : ''"
        />
      </FastDealCardField>
    </div>

    <FastDealCardError :error="generalError" />
    <div class="flex justify-end">
      <button type="submit" class="btn-primary" :disabled="busy" :aria-busy="busy">
        {{ busy ? 'Добавляем…' : actionLabel }}
      </button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { isPositiveMoney, lookupName, lookupText, parseMoneyInput } from '../composables/fastDealCardFormat'
import type { LookupItem } from '../api/fastDealsApi'
import type { AddVehicleBody, FastDealCard } from '../types'
import FastDealCardCompanyPicker from './FastDealCardCompanyPicker.vue'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'
import FastDealCardLookupSelect from './FastDealCardLookupSelect.vue'

const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/
const KNOWN_FIELDS = [
  'category_id', 'mark_id', 'mark_name', 'model_id', 'model_name', 'modification_id', 'modification_name',
  'trim_id', 'body_color_id', 'body_color_name', 'vin', 'price', 'dealer_company_id',
]

const props = withDefaults(defineProps<{
  deal: FastDealCard
  initialVin?: string
  busy?: boolean
  error?: ActionFailure | null
  actionLabel?: string
}>(), {
  initialVin: '',
  busy: false,
  error: null,
  actionLabel: 'Добавить в сделку',
})

const emit = defineEmits<{ submit: [body: AddVehicleBody] }>()

const ctx = useFastDealCardContext()

const categoryId = ref('')
const markId = ref('')
const modelId = ref('')
const modificationId = ref('')
const trimId = ref('')
const colorId = ref('')
const noMark = ref(false)
const noModel = ref(false)
const markName = ref('')
const modelName = ref('')
const modificationName = ref('')
const colorName = ref('')
const vin = ref(props.initialVin.trim().toUpperCase())
const price = ref('')
const dealerIds = ref<string[]>([])
const similarModels = ref<LookupItem[]>([])

const local = reactive<Record<string, string>>({})

/** After the split a DL deal belongs to one dealer: new positions can only be his. */
const fixedDealer = computed(() => (ctx.isDD.value ? null : props.deal.dealer_company ?? null))

const errorOf = (field: string): string => local[field] || (props.error?.field === field ? props.error.detail : '')
const generalError = computed(() => (props.error && !(props.error.field && KNOWN_FIELDS.includes(props.error.field)) ? props.error : null))

// ----------------------------------------------------------------------- directory chain

const clearBelow = (...levels: ('model' | 'modification' | 'trim')[]) => {
  if (levels.includes('model')) modelId.value = ''
  if (levels.includes('modification')) modificationId.value = ''
  if (levels.includes('trim')) trimId.value = ''
}

function onCategorySelect() {
  // The chain does not depend on the category: the category only classifies the position.
  local.category_id = ''
}

function onMarkSelect() {
  clearBelow('model', 'modification', 'trim')
  noModel.value = false
  local.mark_id = ''
}

function onModelSelect(item: LookupItem | null) {
  clearBelow('modification', 'trim')
  local.model_id = ''
  const suggested = item ? lookupText(item, 'category_id') : ''
  if (suggested && !categoryId.value) categoryId.value = suggested
}

function onModificationSelect(item: LookupItem | null) {
  clearBelow('trim')
  // The category suggested by the modification replaces the current one; it can be changed again.
  const suggested = item ? lookupText(item, 'category_id') : ''
  if (suggested) categoryId.value = suggested
}

function toggleNoMark(event: Event) {
  noMark.value = (event.target as HTMLInputElement).checked
  markId.value = ''
  noModel.value = false
  clearBelow('model', 'modification', 'trim')
  similarModels.value = []
}

function toggleNoModel(event: Event) {
  noModel.value = (event.target as HTMLInputElement).checked
  clearBelow('model', 'modification', 'trim')
  similarModels.value = []
}

// ------------------------------------------------------------------------ similar models

let similarTimer: ReturnType<typeof setTimeout> | null = null
let similarGeneration = 0

async function findSimilar() {
  const current = ++similarGeneration
  const typed = modelName.value.trim()
  if (!(noMark.value || noModel.value) || typed.length < 3) {
    similarModels.value = []
    return
  }
  try {
    const response = await ctx.api.lookup('similar-models', { q: typed, mark_id: markId.value || undefined })
    if (current === similarGeneration) similarModels.value = response.items
  } catch {
    if (current === similarGeneration) similarModels.value = []
  }
}

watch([modelName, noMark, noModel], () => {
  if (similarTimer) clearTimeout(similarTimer)
  similarTimer = setTimeout(findSimilar, 400)
})
onBeforeUnmount(() => {
  if (similarTimer) clearTimeout(similarTimer)
})

const similarLabel = (item: LookupItem) => [lookupText(item, 'mark_name'), lookupName(item)].filter(Boolean).join(' ')

/** Choosing a suggestion returns the position to the directory chain with its identifiers restored. */
function applySimilar(item: LookupItem) {
  const itemMark = lookupText(item, 'mark_id')
  noMark.value = false
  noModel.value = false
  if (itemMark) markId.value = itemMark
  modelId.value = String(item.id)
  modificationId.value = ''
  trimId.value = ''
  markName.value = ''
  modelName.value = ''
  const itemCategory = lookupText(item, 'category_id')
  if (itemCategory && !categoryId.value) categoryId.value = itemCategory
  similarModels.value = []
}

// ----------------------------------------------------------------------------- submit

function submit() {
  for (const key of Object.keys(local)) delete local[key]

  if (!categoryId.value) local.category_id = 'Выберите категорию'

  const dd = ctx.isDD.value
  if (dd) {
    if (noMark.value) {
      if (!markName.value.trim()) local.mark_name = 'Укажите марку'
      if (!modelName.value.trim()) local.model_name = 'Укажите модель'
    } else {
      if (!markId.value) local.mark_id = 'Выберите марку'
      if (noModel.value) {
        if (!modelName.value.trim()) local.model_name = 'Укажите модель'
      } else if (!modelId.value) {
        local.model_id = 'Выберите модель'
      }
    }
  } else {
    if (!markName.value.trim()) local.mark_name = 'Укажите марку'
    if (!modelName.value.trim()) local.model_name = 'Укажите модель'
  }

  const typedVin = vin.value.trim().toUpperCase()
  if (!VIN_PATTERN.test(typedVin)) local.vin = 'VIN — 17 символов: латинские буквы (кроме I, O, Q) и цифры'
  const parsedPrice = parseMoneyInput(price.value)
  if (parsedPrice === null || !isPositiveMoney(parsedPrice)) local.price = 'Укажите цену, например 2500000.00'

  const dealerId = fixedDealer.value?.id ?? dealerIds.value[0]
  if (!dd && !dealerId) local.dealer_company_id = 'Выберите дилера'

  if (Object.keys(local).length > 0 || parsedPrice === null) return

  const body: AddVehicleBody = {
    vehicle_source_type: 'manual',
    category_id: categoryId.value,
    vin: typedVin,
    price: parsedPrice,
  }
  if (dd) {
    if (noMark.value) {
      body.mark_name = markName.value.trim()
      body.model_name = modelName.value.trim()
    } else {
      body.mark_id = markId.value
      if (noModel.value) body.model_name = modelName.value.trim()
      else body.model_id = modelId.value
      if (modificationId.value) body.modification_id = modificationId.value
      if (trimId.value) body.trim_id = trimId.value
    }
    if (colorId.value) body.body_color_id = colorId.value
  } else {
    body.mark_name = markName.value.trim()
    body.model_name = modelName.value.trim()
    if (modificationName.value.trim()) body.modification_name = modificationName.value.trim()
    if (colorName.value.trim()) body.body_color_name = colorName.value.trim()
    body.dealer_company_id = dealerId
  }
  emit('submit', body)
}
</script>
