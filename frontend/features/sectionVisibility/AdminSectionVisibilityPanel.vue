<template>
  <section v-if="authStore.isCarCraftEmployee" class="flex w-full flex-col gap-6" aria-labelledby="visibility-heading">
    <header class="flex flex-col gap-2">
      <div class="flex items-center gap-3">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
          <AdjustmentsHorizontalIcon class="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h2 id="visibility-heading" class="text-xl font-semibold leading-7 text-gray-900">Доступ к разделам</h2>
          <p class="mt-1 max-w-2xl text-sm leading-6 text-gray-600">
            Управляйте видимостью разделов публичного сайта и рабочих кабинетов.
          </p>
        </div>
      </div>
    </header>

    <div
      v-if="loadError"
      class="flex flex-col gap-4 rounded-lg border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <div class="flex items-start gap-3">
        <ExclamationCircleIcon class="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
        <div>
          <p class="text-sm font-semibold text-red-800">Не удалось загрузить настройки</p>
          <p class="mt-1 text-sm leading-5 text-red-700">{{ loadError }}</p>
        </div>
      </div>
      <button
        type="button"
        class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 transition-colors duration-200 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
        @click="loadMatrices"
      >
        <ArrowPathIcon class="h-4 w-4" aria-hidden="true" />
        Повторить
      </button>
    </div>

    <div v-else class="overflow-hidden rounded-xl border border-gray-200 bg-white">
      <div class="border-b border-gray-200 p-6">
        <div class="flex flex-wrap gap-2" role="tablist" aria-label="Область интерфейса">
          <button
            v-for="option in SCOPE_OPTIONS"
            :id="`scope-tab-${option.value}`"
            :key="option.value"
            type="button"
            role="tab"
            :aria-selected="selectedScope === option.value"
            aria-controls="visibility-section-list"
            :tabindex="selectedScope === option.value ? 0 : -1"
            :disabled="loading || saving"
            :class="[
              'relative min-h-11 rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60',
              selectedScope === option.value
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
            ]"
            @click="selectScope(option.value)"
            @keydown.left.prevent="selectAdjacentScope(option.value, -1)"
            @keydown.right.prevent="selectAdjacentScope(option.value, 1)"
          >
            {{ option.label }}
            <span
              v-if="isScopeDirty(option.value)"
              class="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-amber-500"
              aria-hidden="true"
            />
            <span v-if="isScopeDirty(option.value)" class="sr-only">Есть несохраненные изменения</span>
          </button>
        </div>

        <div v-if="selectedScope !== 'carcraft_employee'" class="mt-5 max-w-2xl border-t border-gray-100 pt-5">
          <p class="text-sm font-medium text-gray-800">{{ storefrontLabel(selectedStorefront) }}</p>
          <p class="mt-1 text-sm leading-5 text-gray-600">
            Настройки относятся к выбранной витрине и сохраняются отдельно для каждой области.
          </p>
          <p v-if="selectedStorefrontDirty" class="mt-2 text-sm font-medium text-amber-700" role="status">
            У выбранной витрины есть несохраненные изменения.
          </p>
        </div>
        <div v-else class="mt-5 max-w-2xl rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
          <p class="text-sm font-semibold text-blue-900">Единая для всех витрин</p>
          <p class="mt-1 text-sm leading-5 text-blue-800">Настройка разделов администратора глобальна и не зависит от выбранной витрины.</p>
        </div>
      </div>

      <div v-if="loading || loadingStorefront" class="flex flex-col gap-3 p-4 sm:p-6" aria-busy="true" aria-label="Загрузка разделов">
        <div v-for="index in 5" :key="index" class="flex animate-pulse items-center gap-4 rounded-lg bg-gray-50 p-4 motion-reduce:animate-none">
          <div class="flex-1">
            <div class="h-4 w-40 rounded bg-gray-200" />
            <div class="mt-2 h-3 w-64 max-w-full rounded bg-gray-200" />
          </div>
          <div class="h-6 w-11 rounded-full bg-gray-200" />
        </div>
      </div>

      <div v-else-if="selectedLoadError" class="flex flex-col items-start gap-4 p-6" role="alert">
        <div class="flex items-start gap-3 text-red-800">
          <ExclamationCircleIcon class="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <div>
            <p class="text-sm font-semibold">Не удалось загрузить настройки витрины</p>
            <p class="mt-1 text-sm leading-5">{{ selectedLoadError }}</p>
          </div>
        </div>
        <button type="button" class="btn-secondary min-h-11" @click="retrySelectedStorefrontMatrices">
          Повторить
        </button>
      </div>

      <form v-else class="flex flex-col" @submit.prevent="saveChanges">
        <fieldset
          id="visibility-section-list"
          role="tabpanel"
          :aria-label="`Разделы области ${selectedScopeLabel}`"
          class="flex flex-col"
        >
          <legend class="sr-only">Разделы области {{ selectedScopeLabel }}</legend>

          <div v-if="scopeSections.length" class="divide-y divide-gray-100">
            <label
              v-for="section in scopeSections"
              :key="section.key"
              :for="switchId(section.key)"
              class="flex min-h-20 cursor-pointer items-center gap-4 px-4 py-4 transition-colors duration-200 hover:bg-gray-50 sm:px-6"
            >
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium leading-5 text-gray-900">{{ section.label }}</span>
                <span :id="`${switchId(section.key)}-description`" class="mt-1 block text-sm leading-5 text-gray-500">
                  {{ isCurrentHomePage(section.key) ? 'Текущую главную страницу нельзя скрыть' : (section.isVisible ? 'Раздел отображается пользователям' : 'Раздел скрыт из интерфейса') }}
                </span>
              </span>
              <span class="flex shrink-0 items-center gap-3">
                <span class="hidden text-sm font-medium sm:inline" :class="section.isVisible ? 'text-blue-700' : 'text-gray-500'">
                  {{ section.isVisible ? 'Видим' : 'Скрыт' }}
                </span>
                <span class="relative inline-flex">
                  <input
                    :id="switchId(section.key)"
                    type="checkbox"
                    role="switch"
                    class="peer sr-only"
                    :checked="section.isVisible"
                    :disabled="saving || isCurrentHomePage(section.key)"
                    :aria-describedby="`${switchId(section.key)}-description`"
                    @change="handleToggle(section.key, $event)"
                  >
                  <span
                    aria-hidden="true"
                    class="h-6 w-11 rounded-full bg-gray-300 transition-colors duration-200 after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow-sm after:transition-transform after:duration-200 peer-checked:bg-blue-600 peer-checked:after:translate-x-5 peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-blue-500 peer-focus-visible:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-60 motion-reduce:transition-none motion-reduce:after:transition-none"
                  />
                </span>
              </span>
            </label>
          </div>

          <div v-else class="flex flex-col items-center px-4 py-12 text-center sm:px-6">
            <EyeSlashIcon class="h-10 w-10 text-gray-400" aria-hidden="true" />
            <p class="mt-4 text-base font-semibold text-gray-900">Нет настраиваемых разделов</p>
            <p class="mt-1 max-w-md text-sm leading-6 text-gray-500">
              Для выбранной области пока не добавлены разделы, видимость которых можно изменить.
            </p>
          </div>
        </fieldset>

        <footer class="flex flex-col gap-4 border-t border-gray-200 bg-gray-50 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div class="min-h-10" aria-live="polite" aria-atomic="true">
            <div v-if="saveError" class="flex items-start gap-2 text-sm leading-5 text-red-700" role="alert">
              <ExclamationCircleIcon class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{{ saveError }}</span>
            </div>
            <div v-else-if="successMessage" class="flex items-start gap-2 text-sm leading-5 text-green-700">
              <CheckCircleIcon class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{{ successMessage }}</span>
            </div>
            <p v-else class="text-sm leading-5 text-gray-500">
              {{ isDirty ? 'Есть несохраненные изменения' : 'Все изменения сохранены' }}
            </p>
          </div>

          <button
            type="submit"
            class="btn-primary min-h-11 w-full gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            :disabled="saving || !isDirty"
          >
            <ArrowPathIcon v-if="saving" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            <CheckIcon v-else class="h-4 w-4" aria-hidden="true" />
            {{ saving ? 'Сохраняем…' : 'Сохранить изменения' }}
          </button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  CheckIcon,
  ExclamationCircleIcon,
  EyeSlashIcon,
} from '@heroicons/vue/24/outline'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  SECTION_VISIBILITY_CATALOG,
  STOREFRONT_VISIBILITY_SCOPES,
  isStorefrontVisibilityScope,
  type GlobalVisibilityScope,
  type StorefrontVisibilityScope,
  type VisibilityScope,
} from '~/features/sectionVisibility/config'
import {
  buildAdminVisibilityUpdates,
  createAdminVisibilityDraftState,
  getAdminVisibilityDraft,
  isAdminVisibilityScopeDirty,
  isAdminVisibilityTargetDirty,
  replaceAdminGlobalVisibilityDraft,
  replaceAdminStorefrontVisibilityDraft,
  refreshAdminStorefrontVisibilityDraft,
  setAdminVisibilityDraftValue,
} from '~/features/sectionVisibility/adminDraftState'
import {
  adminStorefrontVisibilityTargetKey,
  beginAdminStorefrontVisibilityBatch,
  completeAdminStorefrontVisibilityBatch,
  createAdminStorefrontVisibilityLoadState,
  failAdminStorefrontVisibilityBatch,
  getAdminStorefrontVisibilityLoadStatus,
  validateAdminStorefrontVisibilityBatch,
} from '~/features/sectionVisibility/adminLoadState'
import { createSectionVisibilityApi } from '~/features/sectionVisibility/api/sectionVisibilityApi'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { createStorefrontBuilderApi } from '~/features/storefrontBuilder/api/storefrontBuilderApi'
import type { StorefrontPageListItem } from '~/features/storefrontBuilder/types'
import type {
  SectionVisibilityTarget,
  SectionVisibilityMatrix,
  VisibilityMatrix,
} from '~/features/sectionVisibility/types'
import type {
  StorefrontPublicPageKey,
  StorefrontPublicPages,
} from '~/features/storefront/types'
import type { UUID } from '~/types/ids'

interface ScopeOption {
  value: VisibilityScope
  label: string
}

interface ScopeSectionRow {
  key: string
  label: string
  isVisible: boolean
}

interface SectionVisibilityStorefrontOption {
  id: UUID
  slug: string | null
  is_default: boolean
  is_active: boolean
}

const SCOPE_OPTIONS: readonly ScopeOption[] = [
  { value: 'public', label: 'Публичный сайт' },
  { value: 'carcraft_employee', label: 'Администратор' },
  { value: 'leasing_company', label: 'Лизинговая компания' },
  { value: 'dealer', label: 'Дилер' },
  { value: 'distributor', label: 'Дистрибьютор' },
]
const config = useRuntimeConfig()
const api = createSectionVisibilityApi(config)
const builderApi = createStorefrontBuilderApi(config)
const authStore = useAuthStore()
const visibilityStore = useSectionVisibilityStore()
const props = withDefaults(
  defineProps<{
    storefrontId: UUID
    storefrontSlug: string | null
    storefrontIsDefault: boolean
    storefrontIsActive: boolean
    homePageKey: StorefrontPublicPageKey
    publicPages: StorefrontPublicPages
    storefrontPages?: StorefrontPageListItem[]
  }>(),
  {
    storefrontPages: () => [],
  },
)
const selectedScope = ref<VisibilityScope>('public')
const selectedStorefrontId = computed<UUID>(() => props.storefrontId)
const draftState = reactive(createAdminVisibilityDraftState())
const storefrontLoadState = reactive(createAdminStorefrontVisibilityLoadState())
const pendingStorefrontLoads: Partial<Record<string, Promise<void>>> = {}
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const saveError = ref('')
const successMessage = ref('')

const selectedStorefront = computed<SectionVisibilityStorefrontOption>(() => ({
  id: props.storefrontId,
  slug: props.storefrontSlug,
  is_default: props.storefrontIsDefault,
  is_active: props.storefrontIsActive,
}))

const loadedStorefrontPages = ref<StorefrontPageListItem[]>([])
const loadingCustomPages = ref(false)

const allStorefrontPages = computed<StorefrontPageListItem[]>(() => {
  if (props.storefrontPages && props.storefrontPages.length > 0) {
    return props.storefrontPages
  }
  return loadedStorefrontPages.value
})

const customStorefrontPages = computed(() => {
  return allStorefrontPages.value.filter(p => !p.is_system)
})

const customPageKeys = computed<string[]>(() => {
  return customStorefrontPages.value.map(p => p.page_key)
})

const loadStorefrontPagesIfNeeded = async (storefrontId: UUID) => {
  if (props.storefrontPages && props.storefrontPages.length > 0) return
  loadingCustomPages.value = true
  try {
    const res = await builderApi.listPages(storefrontId)
    loadedStorefrontPages.value = res.items || []
  } catch (err) {
    console.warn('Could not load storefront pages for visibility:', err)
  } finally {
    loadingCustomPages.value = false
  }
}

watch(
  () => props.storefrontId,
  (id) => {
    if (id) void loadStorefrontPagesIfNeeded(id)
  },
  { immediate: true },
)

watch(
  customPageKeys,
  (keys) => {
    if (keys.length === 0 || !selectedStorefrontId.value) return
    const storefrontId = selectedStorefrontId.value
    const publicDraft = draftState.storefrontDrafts.public[storefrontId]
    const publicSaved = draftState.storefrontSaved.public[storefrontId]
    if (publicDraft && publicSaved) {
      for (const key of keys) {
        if (publicDraft[key] === undefined) {
          publicDraft[key] = true
        }
        if (publicSaved[key] === undefined) {
          publicSaved[key] = true
        }
      }
    }
  },
  { immediate: true },
)

const selectedScopeLabel = computed(() =>
  SCOPE_OPTIONS.find((option) => option.value === selectedScope.value)?.label ?? selectedScope.value,
)

const selectedMatrix = computed<VisibilityMatrix | null>(() => getAdminVisibilityDraft(
  draftState,
  selectedScope.value,
  selectedStorefrontId.value,
))

const isCurrentHomePage = (key: string): boolean => (
  selectedScope.value === 'public'
  && props.homePageKey !== 'home'
  && key === props.homePageKey
)

const publicPageLabel = (key: string, fallback: string): string => {
  if (selectedScope.value !== 'public' || key === 'model_brand_selection' || key === 'cars_brand_filter') return fallback
  return (props.publicPages as unknown as Record<string, { title?: string } | undefined>)[key]?.title ?? fallback
}

const scopeSections = computed<ScopeSectionRow[]>(() => {
  const baseItems: ScopeSectionRow[] = SECTION_VISIBILITY_CATALOG[selectedScope.value]
    .map((item) => ({
      key: item.key,
      label: publicPageLabel(item.key, item.label),
      isVisible: isCurrentHomePage(item.key)
        ? true
        : (selectedMatrix.value?.[item.key] ?? item.defaultVisible),
    }))

  if (selectedScope.value === 'public') {
    for (const page of customStorefrontPages.value) {
      const pageKey = page.page_key
      const isHome = isCurrentHomePage(pageKey)
      const isVisible = isHome
        ? true
        : (selectedMatrix.value?.[pageKey] ?? true)

      baseItems.push({
        key: pageKey,
        label: page.title || pageKey,
        isVisible,
      })
    }
  }

  return baseItems
})

const isScopeDirty = (scope: VisibilityScope): boolean =>
  isAdminVisibilityScopeDirty(draftState, scope, customPageKeys.value)

const selectedStorefrontDirty = computed(() => (
  isStorefrontVisibilityScope(selectedScope.value) && selectedStorefrontId.value
    ? isAdminVisibilityTargetDirty(
        draftState,
        selectedScope.value,
        selectedStorefrontId.value,
        customPageKeys.value,
      )
    : false
))
const isDirty = computed(() => isStorefrontVisibilityScope(selectedScope.value)
  ? selectedStorefrontDirty.value
  : isAdminVisibilityTargetDirty(draftState, selectedScope.value, null, customPageKeys.value))
const hasUnsavedChanges = computed(() => SCOPE_OPTIONS.some(option => isScopeDirty(option.value)))
defineExpose({ hasUnsavedChanges, saving })
const selectedStorefrontLoadStatus = computed(() => (
  isStorefrontVisibilityScope(selectedScope.value) && selectedStorefrontId.value
    ? getAdminStorefrontVisibilityLoadStatus(
        storefrontLoadState,
        selectedScope.value,
        selectedStorefrontId.value,
      )
    : null
))
const selectedLoadError = computed(() => selectedStorefrontLoadStatus.value?.error ?? '')
const loadingStorefront = computed(() => selectedStorefrontLoadStatus.value?.pending ?? false)
const extractError = (error: unknown, fallback: string): string => {
  const data = (error as { data?: { detail?: unknown; error?: unknown } }).data
  if (typeof data?.detail === 'string') return data.detail
  if (typeof data?.error === 'string') return data.error
  return fallback
}

const storefrontRuntimeTarget = (
  scope: StorefrontVisibilityScope,
  storefront: SectionVisibilityStorefrontOption,
): SectionVisibilityTarget => ({
  scope,
  storefront: {
    id: storefront.id,
    slug: storefront.slug,
  },
})

const replaceStorefrontState = (
  storefront: SectionVisibilityStorefrontOption,
  matrix: SectionVisibilityMatrix,
  preserveDirty = false,
  forcedVisibleKey?: string,
): void => {
  if (!isStorefrontVisibilityScope(matrix.scope)) {
    throw new Error('Backend returned a global matrix for a storefront target')
  }
  if (preserveDirty) {
    refreshAdminStorefrontVisibilityDraft(
      draftState,
      storefront,
      matrix,
      forcedVisibleKey,
      customPageKeys.value,
    )
  } else {
    replaceAdminStorefrontVisibilityDraft(
      draftState,
      storefront,
      matrix,
      customPageKeys.value,
    )
  }
  visibilityStore.cache(storefrontRuntimeTarget(matrix.scope, storefront), matrix)
}

const loadStorefrontMatrices = (
  storefrontId: UUID,
  force = false,
  preserveDirty = false,
  forcedVisibleKey?: string,
): Promise<void> => {
  const storefront = selectedStorefront.value
  if (storefront.id !== storefrontId) return Promise.resolve()
  if (
    !force
    && STOREFRONT_VISIBILITY_SCOPES.every(scope => (
      getAdminStorefrontVisibilityLoadStatus(storefrontLoadState, scope, storefrontId).attempted
    ))
  ) {
    return Promise.resolve()
  }
  const existingPending = STOREFRONT_VISIBILITY_SCOPES
    .map(scope => pendingStorefrontLoads[
      adminStorefrontVisibilityTargetKey(scope, storefrontId)
    ])
    .find((pending): pending is Promise<void> => Boolean(pending))
  if (existingPending) return existingPending

  beginAdminStorefrontVisibilityBatch(storefrontLoadState, storefrontId)
  const pending = (async () => {
    try {
      const response = await api.getAdminStorefrontMatrices(storefrontId)
      const validation = validateAdminStorefrontVisibilityBatch(
        storefrontId,
        response.items,
      )
      for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
        const matrix = validation.matrices[scope]
        if (!matrix) continue
        try {
          replaceStorefrontState(storefront, matrix, preserveDirty, forcedVisibleKey)
        } catch (error: unknown) {
          delete validation.matrices[scope]
          validation.errors[scope] = extractError(
            error,
            `Не удалось применить настройки области «${scope}»`,
          )
        }
      }
      completeAdminStorefrontVisibilityBatch(storefrontLoadState, storefrontId, validation)
    } catch (error: unknown) {
      failAdminStorefrontVisibilityBatch(
        storefrontLoadState,
        storefrontId,
        extractError(
          error,
          'Проверьте подключение и попробуйте загрузить настройки витрины еще раз.',
        ),
      )
    } finally {
      for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
        delete pendingStorefrontLoads[
          adminStorefrontVisibilityTargetKey(scope, storefrontId)
        ]
      }
    }
  })()

  for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
    pendingStorefrontLoads[adminStorefrontVisibilityTargetKey(scope, storefrontId)] = pending
  }
  return pending
}

const loadMatrices = async (): Promise<void> => {
  if (!authStore.isCarCraftEmployee) return

  loading.value = true
  loadError.value = ''
  saveError.value = ''
  successMessage.value = ''

  try {
    const response = await api.getAdminGlobalMatrices()
    const employeeMatrix = response.items.find(item => item.scope === 'carcraft_employee')
    if (!employeeMatrix) throw new Error('Backend omitted global employee visibility matrix')
    replaceAdminGlobalVisibilityDraft(draftState, employeeMatrix)
    visibilityStore.cache({ scope: 'carcraft_employee', storefront: null }, employeeMatrix)
    await loadStorefrontMatrices(selectedStorefrontId.value)
  } catch (error: unknown) {
    loadError.value = extractError(
      error,
      'Проверьте подключение и попробуйте загрузить настройки еще раз.',
    )
  } finally {
    loading.value = false
  }
}

const selectScope = (scope: VisibilityScope): void => {
  selectedScope.value = scope
  saveError.value = ''
  successMessage.value = ''
}

const selectAdjacentScope = (scope: VisibilityScope, offset: number): void => {
  const currentIndex = SCOPE_OPTIONS.findIndex((option) => option.value === scope)
  const nextIndex = (currentIndex + offset + SCOPE_OPTIONS.length) % SCOPE_OPTIONS.length
  const nextScope = SCOPE_OPTIONS[nextIndex]
  if (!nextScope) return
  selectScope(nextScope.value)
  nextTick(() => document.getElementById(`scope-tab-${nextScope.value}`)?.focus())
}

const switchId = (key: string): string => {
  const context = isStorefrontVisibilityScope(selectedScope.value)
    ? `${selectedScope.value}-${selectedStorefrontId.value ?? 'unselected'}`
    : selectedScope.value
  return `section-visibility-${context}-${key}`
}

const storefrontLabel = (storefront: SectionVisibilityStorefrontOption): string => {
  const name = storefront.is_default ? 'Основная витрина (/)' : `/${storefront.slug}`
  const status = storefront.is_active ? 'Активна' : 'Выключена'
  return `${name} — ${status}`
}

const handleToggle = (key: string, event: Event): void => {
  if (!selectedMatrix.value || isCurrentHomePage(key)) return
  setAdminVisibilityDraftValue(
    draftState,
    selectedScope.value,
    selectedStorefront.value,
    key,
    (event.currentTarget as HTMLInputElement).checked,
    customPageKeys.value,
  )
  saveError.value = ''
  successMessage.value = ''
}

const retrySelectedStorefrontMatrices = (): void => {
  if (selectedStorefrontId.value) void loadStorefrontMatrices(selectedStorefrontId.value, true)
}

const saveChanges = async (): Promise<void> => {
  if (saving.value || !isDirty.value) return

  const scope = selectedScope.value
  const draft = selectedMatrix.value
  if (!draft) return
  const sections = buildAdminVisibilityUpdates(
    draftState,
    scope,
    selectedStorefrontId.value,
    customPageKeys.value,
  )

  if (!sections.length) return

  saving.value = true
  saveError.value = ''
  successMessage.value = ''

  try {
    if (isStorefrontVisibilityScope(scope)) {
      const storefrontId = selectedStorefrontId.value
      const storefront = selectedStorefront.value
      if (!storefrontId || !storefront) return
      const matrix = await api.updateAdminStorefrontMatrix(storefrontId, scope, { sections })
      replaceStorefrontState(storefront, matrix)
      successMessage.value = `Настройки «${selectedScopeLabel.value}» для витрины «${storefrontLabel(storefront)}» сохранены`
    } else {
      const globalScope: GlobalVisibilityScope = scope
      const matrix = await api.updateAdminGlobalMatrix(globalScope, { sections })
      replaceAdminGlobalVisibilityDraft(draftState, matrix)
      visibilityStore.cache({ scope: globalScope, storefront: null }, matrix)
      successMessage.value = `Настройки для области «${selectedScopeLabel.value}» сохранены`
    }
  } catch (error: unknown) {
    saveError.value = extractError(
      error,
      'Не удалось сохранить изменения. Проверьте подключение и попробуйте снова.',
    )
  } finally {
    saving.value = false
  }
}

watch(() => props.storefrontId, (storefrontId, previousId) => {
  if (!storefrontId || storefrontId === previousId) return
  saveError.value = ''
  successMessage.value = ''
  void loadStorefrontMatrices(storefrontId)
})

watch(() => props.homePageKey, (homePageKey, previousKey) => {
  if (homePageKey === previousKey || !selectedStorefrontId.value) return
  void loadStorefrontMatrices(selectedStorefrontId.value, true, true, homePageKey)
})

onMounted(async () => {
  if (!authStore.isCarCraftEmployee) {
    await navigateTo('/workspace')
    return
  }
  await loadMatrices()
})
</script>
