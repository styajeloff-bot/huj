<template>
  <fieldset class="border-t border-gray-100 pt-6" :disabled="disabled">
    <legend class="pr-3 text-sm font-semibold text-gray-900">Цвета блоков и элементов</legend>
    <p class="mt-2 text-sm leading-6 text-gray-600">
      Выберите область и элемент. Свой цвет заменяет наследуемый только в этой области.
      Сброс действует в черновике до сохранения оформления.
    </p>
    <div class="mt-4 grid grid-cols-3 gap-4">
      <label class="text-sm font-medium text-gray-800">
        Область интерфейса
        <select v-model="selectedBlock" class="select-field mt-1.5 min-h-11">
          <option v-for="(block, key) in registry.blocks" :key="key" :value="key">{{ block.label }}</option>
        </select>
      </label>
      <label class="text-sm font-medium text-gray-800">
        Элемент
        <select v-model="selectedElement" class="select-field mt-1.5 min-h-11">
          <option v-for="element in elements" :key="element" :value="element">{{ element }}</option>
        </select>
      </label>
      <label class="text-sm font-medium text-gray-800">
        Состояние
        <select v-model="selectedState" class="select-field mt-1.5 min-h-11">
          <option v-for="state in states" :key="state" :value="state">{{ STATE_LABELS[state] ?? state }}</option>
        </select>
      </label>
    </div>
    <div class="mt-5 grid grid-cols-2 items-start gap-6">
      <div class="flex flex-col gap-5">
        <div v-for="field in fields" :key="field.key">
          <label :for="fieldId(field.key)" class="mb-1.5 block text-sm font-medium text-gray-800">{{ field.definition.label }}</label>
          <div class="flex items-center gap-2">
            <input type="color" :value="effective(field.key)" :aria-label="`Выбрать цвет: ${field.definition.label}`"
              class="h-11 w-14 shrink-0 cursor-pointer rounded-lg border border-gray-300 bg-white p-1"
              @input="updateFromEvent(field.key, $event, true)">
            <input :id="fieldId(field.key)" :value="modelValue[field.key] ?? effective(field.key)" type="text" maxlength="7"
              autocomplete="off" spellcheck="false" class="input-field min-h-11 min-w-0 font-mono uppercase"
              :aria-invalid="Boolean(fieldError(field.key))" :aria-describedby="`${fieldId(field.key)}-source${fieldError(field.key) ? ` ${fieldId(field.key)}-error` : ''}`"
              @input="updateFromEvent(field.key, $event)" @blur="normalize(field.key)">
            <button type="button" class="shrink-0 rounded px-2 py-2 text-sm text-gray-600 underline underline-offset-2 focus-visible:ring-2 focus-visible:ring-blue-600"
              :disabled="!Object.hasOwn(modelValue, field.key)" :aria-label="`Сбросить цвет: ${field.definition.label}`" @click="resetField(field.key)">Сбросить</button>
          </div>
          <p :id="`${fieldId(field.key)}-source`" class="mt-1.5 text-sm text-gray-500">
            {{ source(field.key) }} · {{ effective(field.key) }}
          </p>
          <p v-if="fieldError(field.key)" :id="`${fieldId(field.key)}-error`" class="mt-1 text-sm text-red-700" role="alert">{{ fieldError(field.key) }}</p>
        </div>
        <button type="button" class="self-start rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus-visible:ring-2 focus-visible:ring-blue-600"
          :disabled="!hasGroupOverrides" @click="resetGroup">Сбросить цвета этой области</button>
      </div>
      <aside class="rounded-xl border border-gray-200 p-4" aria-label="Локальный образец оформления">
        <p class="mb-3 text-sm font-semibold text-gray-800">{{ registry.blocks[selectedBlock]?.label }} · {{ selectedElement }}</p>
        <label v-if="previewContexts.length > 1" class="mb-4 block text-sm font-medium text-gray-700">
          Контекст образца
          <select v-model="selectedContext" class="select-field mt-1 min-h-10" aria-label="Контекст образца">
            <option v-for="context in previewContexts" :key="context" :value="context">{{ registry.blocks[context]?.label }}</option>
          </select>
          <span class="mt-1 block text-sm font-normal text-gray-500">Этот элемент используется в нескольких областях. Контекст меняет только образец и не сохраняется.</span>
        </label>
        <div class="min-h-52 rounded-lg border p-5" :style="previewStyle">
          <div class="mb-4 flex items-center gap-3">
            <svg class="h-7 w-7" :style="{ color: sampleColor('icon') }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
            <p class="text-lg font-semibold" :style="{ color: sampleColor('title') }">Образец элемента</p>
          </div>
          <p class="mb-4 text-sm leading-6" :style="{ color: sampleColor('text') }">Текст, фон и иконки меняются независимо.</p>
          <div v-if="isAction" class="inline-flex min-h-11 items-center gap-2 rounded-lg border px-4 py-2" :style="actionStyle">
            <svg class="h-5 w-5" :style="{ color: sampleColor(actionToken('icon')) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5" /></svg>
            {{ STATE_LABELS[selectedState] ?? 'Обычное' }}
          </div>
          <div v-else class="flex min-h-12 items-center gap-3 rounded-lg border px-4 py-3" :style="elementStyle">
            <svg class="h-5 w-5" :style="{ color: sampleColor(selectedIconToken) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 8v5m0 3v.01" /></svg>
            {{ selectedElement }}
          </div>
        </div>
        <p class="mt-3 text-sm leading-5 text-gray-500">Локальный образец выбранного элемента и состояния. Публичная витрина изменится после сохранения и нового открытия страницы.</p>
      </aside>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  buildStorefrontTheme, STOREFRONT_COLOR_REGISTRY, storefrontColorKey,
  normalizeStorefrontHex, isStorefrontHexColor,
  type PublicStorefrontAppearance,
} from '~/features/storefront'

const props = defineProps<{
  modelValue: Record<string, string>
  appearance: PublicStorefrontAppearance
  disabled?: boolean
  errors?: Record<string, string>
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, string>] }>()
const registry = STOREFRONT_COLOR_REGISTRY
const STATE_LABELS: Record<string, string> = { normal: 'Обычное', hover: 'Наведение', active: 'Нажатие', focus: 'Фокус с клавиатуры', disabled: 'Недоступно', selected: 'Выбрано', visited: 'Посещённая ссылка' }
const selectedBlock = ref('global')
const selectedElement = ref('Фоны')
const selectedState = ref('normal')
const selectedContext = ref('global')
const previewContexts = computed(() => registry.blocks[selectedBlock.value]?.previewContexts ?? ['global'])
watch([selectedBlock, previewContexts], () => {
  const parent = registry.blocks[selectedBlock.value]?.parent ?? 'global'
  selectedContext.value = previewContexts.value.includes(parent) ? parent : previewContexts.value[0] ?? 'global'
}, { immediate: true })
const touched = ref(new Set<string>())
const theme = computed(() => buildStorefrontTheme({ ...props.appearance, color_overrides: props.modelValue }, { block: selectedBlock.value, parent: selectedContext.value }))
const blockTokens = computed(() => registry.blocks[selectedBlock.value]?.tokens ?? [])
const elements = computed(() => [...new Set(blockTokens.value.map(token => registry.tokens[token]!.element))])
const states = computed(() => [...new Set(blockTokens.value.filter(token => registry.tokens[token]!.element === selectedElement.value).map(token => registry.tokens[token]!.state))])
const fields = computed(() => blockTokens.value.filter(token => {
  const definition = registry.tokens[token]!
  return definition.element === selectedElement.value && definition.state === selectedState.value
}).map(token => ({ token, key: storefrontColorKey(selectedBlock.value, token), definition: registry.tokens[token]! })))
watch(elements, values => { if (!values.includes(selectedElement.value)) selectedElement.value = values[0] ?? '' })
watch(states, values => { if (!values.includes(selectedState.value)) selectedState.value = values[0] ?? 'normal' })
watch(() => props.errors, errors => {
  const key = Object.keys(errors ?? {})[0]
  if (!key) return
  for (const [block, definition] of Object.entries(registry.blocks)) {
    const token = definition.tokens.find(item => storefrontColorKey(block, item) === key)
    if (!token) continue
    selectedBlock.value = block
    selectedElement.value = registry.tokens[token]!.element
    selectedState.value = registry.tokens[token]!.state
    break
  }
})
const fieldId = (key: string) => `storefront-color-${key.replaceAll('.', '-')}`
const effective = (key: string) => theme.value.resolvedColors[key]?.value ?? '#000000'
const source = (key: string) => {
  if (Object.hasOwn(props.modelValue, key)) return 'Свой цвет'
  if (theme.value.resolvedColors[key]?.source === 'system') return 'Системное значение'
  return selectedContext.value !== 'global' ? `Наследуется: ${registry.blocks[selectedContext.value]?.label}` : 'По общей палитре'
}
const fieldError = (key: string) => props.errors?.[key] || (touched.value.has(key) && props.modelValue[key] !== undefined && !isStorefrontHexColor(props.modelValue[key]) ? 'Введите цвет в формате #RRGGBB' : '')
const setColor = (key: string, value: string) => emit('update:modelValue', { ...props.modelValue, [key]: value })
const updateFromEvent = (key: string, event: Event, picker = false) => {
  const value = (event.target as HTMLInputElement).value
  setColor(key, picker ? value.toUpperCase() : value)
}
const normalize = (key: string) => {
  touched.value = new Set([...touched.value, key])
  const value = props.modelValue[key]
  if (value && isStorefrontHexColor(value)) setColor(key, normalizeStorefrontHex(value))
}
const resetField = (key: string) => {
  const next = { ...props.modelValue }
  delete next[key]
  emit('update:modelValue', next)
}
const hasGroupOverrides = computed(() => blockTokens.value.some(token => Object.hasOwn(props.modelValue, storefrontColorKey(selectedBlock.value, token))))
const resetGroup = () => {
  const next = { ...props.modelValue }
  for (const token of blockTokens.value) delete next[storefrontColorKey(selectedBlock.value, token)]
  emit('update:modelValue', next)
}
const sampleColor = (token: string) => theme.value.blocks[selectedBlock.value]?.[`--storefront-${token}`] ?? theme.value.blocks[selectedContext.value]?.[`--storefront-${token}`] ?? theme.value.variables[`--storefront-${token}`]
const previewStyle = computed(() => ({ backgroundColor: sampleColor('background'), color: sampleColor('text'), borderColor: sampleColor('border'), fontFamily: theme.value.variables['--storefront-font-family'] }))
const actionBase = computed(() => fields.value[0]?.token.split('-')[0] ?? 'primary')
const isAction = computed(() => ['primary', 'secondary', 'ghost', 'destructive', 'input'].includes(actionBase.value))
const actionToken = (part: string) => `${actionBase.value}${selectedState.value === 'normal' ? '' : `-${selectedState.value}`}${part ? `-${part}` : ''}`
const actionStyle = computed(() => ({ backgroundColor: sampleColor(actionToken('')), color: sampleColor(actionToken('foreground')), borderColor: sampleColor(actionToken('border')) }))
const selectedIconToken = computed(() => fields.value.find(field => field.token.includes('icon'))?.token ?? 'icon')
const elementStyle = computed(() => {
  const colorField = fields.value.find(field => /text|foreground|title|label|value|price|link|placeholder/.test(field.token))
  const backgroundField = fields.value.find(field => /background|surface|image|overlay|skeleton/.test(field.token) || field.definition.key.endsWith('background'))
  const borderField = fields.value.find(field => /border|focus|indicator/.test(field.token))
  return { backgroundColor: sampleColor(backgroundField?.token ?? 'surface'), color: sampleColor(colorField?.token ?? 'text'), borderColor: sampleColor(borderField?.token ?? 'border'), boxShadow: selectedElement.value === 'Эффекты' ? `0 4px 16px ${sampleColor('shadow')}33` : undefined }
})
</script>
