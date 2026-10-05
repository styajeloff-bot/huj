<template>
  <form
    class="flex flex-col gap-6 p-6"
    :aria-busy="saving"
    @submit.prevent="saveAppearance"
  >
    <header>
      <h3 class="text-lg font-semibold text-gray-950">Оформление витрины</h3>
      <p class="mt-1 max-w-3xl text-sm leading-6 text-gray-600">
        Цвета, скругления и шрифт применяются только к публичным страницам этой витрины.
      </p>
    </header>

    <div class="min-h-12" aria-live="polite" aria-atomic="true">
      <p v-if="statusMessage" class="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        {{ statusMessage }}
      </p>
      <p v-else-if="errorMessage" class="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
        <ExclamationCircleIcon class="h-5 w-5 shrink-0" aria-hidden="true" />
        {{ errorMessage }}
      </p>
    </div>

    <fieldset>
      <legend class="text-sm font-semibold text-gray-900">Цвета</legend>
      <p class="mt-1 text-sm leading-5 text-gray-500">
        Укажите шестизначный HEX в формате #RRGGBB.
      </p>
      <div class="mt-4 grid grid-cols-2 gap-5">
        <div v-for="color in COLOR_FIELDS" :key="color.key">
          <label :for="colorInputId(color.key)" class="mb-1.5 block text-sm font-medium text-gray-800">
            {{ color.label }}
          </label>
          <div class="flex gap-3">
            <input
              :id="colorPickerId(color.key)"
              :value="pickerValue(color.key)"
              type="color"
              class="h-11 w-14 shrink-0 cursor-pointer rounded-lg border border-gray-300 bg-white p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
              :aria-label="`Выбрать цвет: ${color.label}`"
              :disabled="saving"
              @input="updateFromPicker(color.key, $event)"
            >
            <input
              :id="colorInputId(color.key)"
              v-model="appearance.colors[color.key]"
              type="text"
              inputmode="text"
              maxlength="7"
              autocomplete="off"
              spellcheck="false"
              class="input-field min-h-11 font-mono uppercase"
              :class="colorErrors[color.key] ? 'border-red-400 focus:ring-red-500' : ''"
              :aria-invalid="Boolean(colorErrors[color.key])"
              :aria-describedby="`${colorHelpId(color.key)}${colorErrors[color.key] ? ` ${colorErrorId(color.key)}` : ''}`"
              :disabled="saving"
              @blur="normalizeAndValidate(color.key)"
              @input="clearFeedback"
            >
          </div>
          <p :id="colorHelpId(color.key)" class="mt-1.5 text-sm leading-5 text-gray-500">{{ color.help }}</p>
          <p v-if="colorErrors[color.key]" :id="colorErrorId(color.key)" class="mt-1 flex items-start gap-1.5 text-sm leading-5 text-red-700" role="alert">
            <ExclamationCircleIcon class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {{ colorErrors[color.key] }}
          </p>
        </div>
      </div>
    </fieldset>

    <StorefrontColorOverrideEditor
      :model-value="appearance.color_overrides ?? {}"
      :appearance="previewAppearance"
      :disabled="saving"
      :errors="overrideErrors"
      @update:model-value="updateOverrides"
    />

    <div class="grid grid-cols-2 gap-5 border-t border-gray-100 pt-6">
      <label class="block">
        <span class="mb-1.5 block text-sm font-medium text-gray-800">Скругление</span>
        <select v-model="appearance.border_radius" class="select-field min-h-11 w-full" :disabled="saving">
          <option v-for="preset in RADIUS_PRESETS" :key="preset.key" :value="preset.key">
            {{ preset.label }}
          </option>
        </select>
        <span class="mt-1.5 block text-sm leading-5 text-gray-500">{{ selectedRadiusDescription }}</span>
      </label>

      <div>
        <label for="storefront-appearance-font" class="mb-1.5 block text-sm font-medium text-gray-800">Шрифт</label>
        <div v-if="loadingFonts" class="h-11 animate-pulse rounded-lg bg-gray-100 motion-reduce:animate-none" aria-label="Загрузка списка шрифтов" aria-busy="true" />
        <template v-else>
          <select
            id="storefront-appearance-font"
            v-model="appearance.font_id"
            class="select-field min-h-11 w-full"
            :disabled="saving || Boolean(fontsError)"
          >
            <option :value="null">По умолчанию — Mulish</option>
            <option v-if="appearance.font_id && !selectedFont" :value="appearance.font_id" disabled>Недоступный шрифт</option>
            <option v-for="font in sortedFonts" :key="font.id" :value="font.id">{{ font.name }}</option>
          </select>
          <div v-if="fontsError" class="mt-2 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
            <span>{{ fontsError }}</span>
            <button type="button" class="font-semibold underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600" @click="loadFonts">
              Повторить
            </button>
          </div>
          <p v-else class="mt-1.5 text-sm leading-5 text-gray-500">
            {{ selectedFontDescription }}
          </p>
        </template>
      </div>
    </div>

    <footer class="flex items-center justify-between gap-4 border-t border-gray-100 pt-5">
      <p class="text-sm text-gray-500">Все параметры сохраняются одной операцией.</p>
      <button type="submit" class="btn-primary min-h-11 min-w-52" :disabled="saving">
        <ArrowPathIcon v-if="saving" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {{ saving ? 'Сохраняем…' : 'Сохранить оформление' }}
      </button>
    </footer>
  </form>
</template>

<script setup lang="ts">
import { ArrowPathIcon, ExclamationCircleIcon } from '@heroicons/vue/24/outline'
import {
  createStorefrontsAdminApi,
  type AdminStorefront,
  type AdminStorefrontAppearance,
  type AdminStorefrontFont,
  type StorefrontBorderRadius,
} from '~/features/admin/storefronts/api/storefrontsAdminApi'
import {
  normalizeStorefrontColor,
  type StorefrontColorErrors,
  type StorefrontColorKey,
  validateStorefrontColors,
} from '~/features/admin/storefronts/appearanceValidation'
import { storefrontAdminErrorMessage } from '~/features/admin/storefronts/errorMessage'
import StorefrontColorOverrideEditor from './StorefrontColorOverrideEditor.vue'
import { validateStorefrontColorOverrides, type PublicStorefrontAppearance } from '~/features/storefront'

const props = defineProps<{ storefront: AdminStorefront }>()
const emit = defineEmits<{
  updated: [storefront: AdminStorefront]
  dirtyChange: [isDirty: boolean]
}>()

const COLOR_FIELDS: ReadonlyArray<{ key: StorefrontColorKey; label: string; help: string }> = [
  { key: 'primary', label: 'Основной цвет', help: 'Кнопки, ссылки и брендовые акценты.' },
  { key: 'background', label: 'Фон страницы', help: 'Общий фон публичной части.' },
  { key: 'surface', label: 'Фон поверхностей', help: 'Карточки, формы, меню и модальные окна.' },
  { key: 'text', label: 'Основной текст', help: 'Заголовки и основной текст.' },
]
const RADIUS_PRESETS: ReadonlyArray<{ key: StorefrontBorderRadius; label: string; description: string }> = [
  { key: 'none', label: 'Без скругления', description: 'Контролы 0 px, поверхности 0 px.' },
  { key: 'small', label: 'Небольшое', description: 'Контролы 4 px, поверхности 8 px.' },
  { key: 'medium', label: 'Стандартное', description: 'Контролы 8 px, поверхности 12 px.' },
  { key: 'large', label: 'Крупное', description: 'Контролы 12 px, поверхности 16 px.' },
]
const HEX_COLOR = /^#[0-9A-F]{6}$/i

const config = useRuntimeConfig()
const storefrontApi = createStorefrontsAdminApi(config)
const appearance = reactive<AdminStorefrontAppearance>({
  colors: { ...props.storefront.appearance.colors },
  color_overrides: { ...props.storefront.appearance.color_overrides },
  border_radius: props.storefront.appearance.border_radius,
  font_id: props.storefront.appearance.font_id,
})
const snapshot = (): string => JSON.stringify({
  ...appearance,
  color_overrides: Object.fromEntries(Object.entries(appearance.color_overrides ?? {}).sort(([first], [second]) => first.localeCompare(second))),
})
const baseline = ref(snapshot())
const fonts = ref<AdminStorefrontFont[]>([])
const loadingFonts = ref(true)
const fontsError = ref('')
const saving = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const colorErrors = reactive<StorefrontColorErrors>({})
const overrideErrors = ref<Record<string, string>>({})
const previewAppearance = computed<PublicStorefrontAppearance>(() => ({
  colors: appearance.colors,
  color_overrides: appearance.color_overrides,
  border_radius: appearance.border_radius,
  font: { id: null, family: 'Mulish', url: null },
}))

const isDirty = computed(() => snapshot() !== baseline.value)
const sortedFonts = computed(() => [...fonts.value].sort((first, second) =>
  first.name.localeCompare(second.name, 'ru', { sensitivity: 'base' }),
))
const selectedFont = computed(() => sortedFonts.value.find(font => font.id === appearance.font_id) ?? null)
const selectedFontDescription = computed(() => {
  if (!appearance.font_id) return 'Системный шрифт Mulish с безопасным системным fallback.'
  if (!selectedFont.value) return 'Выбранный шрифт недоступен. После сохранения будет использован Mulish.'
  return selectedFont.value.description || 'Для выбранного шрифта описание не указано.'
})
const selectedRadiusDescription = computed(() =>
  RADIUS_PRESETS.find(preset => preset.key === appearance.border_radius)?.description ?? '',
)

const colorInputId = (key: StorefrontColorKey): string => `storefront-appearance-${key}`
const colorPickerId = (key: StorefrontColorKey): string => `storefront-appearance-${key}-picker`
const colorHelpId = (key: StorefrontColorKey): string => `storefront-appearance-${key}-help`
const colorErrorId = (key: StorefrontColorKey): string => `storefront-appearance-${key}-error`
const pickerValue = (key: StorefrontColorKey): string => {
  const value = normalizeStorefrontColor(appearance.colors[key])
  return HEX_COLOR.test(value) ? value : '#000000'
}

const clearFeedback = () => {
  errorMessage.value = ''
  statusMessage.value = ''
}

const syncAppearance = (storefront: AdminStorefront) => {
  Object.assign(appearance.colors, storefront.appearance.colors)
  appearance.color_overrides = { ...storefront.appearance.color_overrides }
  overrideErrors.value = {}
  appearance.border_radius = storefront.appearance.border_radius
  appearance.font_id = storefront.appearance.font_id
  baseline.value = snapshot()
  Object.keys(colorErrors).forEach(key => delete colorErrors[key as StorefrontColorKey])
  clearFeedback()
}

const updateFromPicker = (key: StorefrontColorKey, event: Event) => {
  appearance.colors[key] = (event.target as HTMLInputElement).value.toUpperCase()
  delete colorErrors[key]
  clearFeedback()
}

const validateColors = (): boolean => {
  const errors = validateStorefrontColors(appearance.colors)
  Object.keys(colorErrors).forEach(key => delete colorErrors[key as StorefrontColorKey])
  Object.assign(colorErrors, errors)
  overrideErrors.value = validateStorefrontColorOverrides(appearance.color_overrides ?? {})
  return Object.keys(errors).length === 0 && Object.keys(overrideErrors.value).length === 0
}

const updateOverrides = (overrides: Record<string, string>) => {
  appearance.color_overrides = overrides
  overrideErrors.value = {}
  clearFeedback()
}

const normalizeAndValidate = (key: StorefrontColorKey) => {
  const normalized = normalizeStorefrontColor(appearance.colors[key])
  if (HEX_COLOR.test(normalized)) appearance.colors[key] = normalized
  validateColors()
}

const loadFonts = async () => {
  loadingFonts.value = true
  fontsError.value = ''
  try {
    fonts.value = (await storefrontApi.listFonts()).items
  } catch (error) {
    fontsError.value = storefrontAdminErrorMessage(error, 'Не удалось загрузить список шрифтов')
  } finally {
    loadingFonts.value = false
  }
}

const saveAppearance = async () => {
  if (saving.value) return
  clearFeedback()
  if (!validateColors()) {
    errorMessage.value = 'Исправьте формат цветов'
    return
  }
  saving.value = true
  try {
    const normalizedColors = {
      primary: normalizeStorefrontColor(appearance.colors.primary),
      background: normalizeStorefrontColor(appearance.colors.background),
      surface: normalizeStorefrontColor(appearance.colors.surface),
      text: normalizeStorefrontColor(appearance.colors.text),
    }
    const saved = await storefrontApi.update(props.storefront.id, {
      appearance: {
        colors: normalizedColors,
        color_overrides: Object.fromEntries(Object.entries(appearance.color_overrides ?? {}).map(([key, value]) => [key, normalizeStorefrontColor(value)])),
        border_radius: appearance.border_radius,
        font_id: appearance.font_id,
      },
    })
    syncAppearance(saved)
    emit('updated', saved)
    statusMessage.value = 'Оформление сохранено'
  } catch (error) {
    errorMessage.value = storefrontAdminErrorMessage(error, 'Не удалось сохранить оформление')
  } finally {
    saving.value = false
  }
}

const discardChanges = () => syncAppearance(props.storefront)

watch(isDirty, (value) => {
  emit('dirtyChange', value)
  if (value) statusMessage.value = ''
}, { immediate: true })
watch(() => props.storefront.id, () => syncAppearance(props.storefront))

onMounted(loadFonts)
defineExpose({ discardChanges, saving })
</script>
