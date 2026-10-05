<template>
  <div data-storefront-block="client.checkout" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-4 sm:py-6 md:py-8">
    <div class="mx-auto max-w-5xl px-3 sm:px-6 lg:px-8">
      <nav class="mb-4 flex overflow-x-auto sm:mb-8" aria-label="Breadcrumb">
        <ol class="flex items-center space-x-2 whitespace-nowrap text-xs sm:space-x-4 sm:text-sm">
          <li><NuxtLink :to="publicRoute('/')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">Главная</NuxtLink></li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li><NuxtLink :to="publicRoute('/cart')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">Корзина</NuxtLink></li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li class="text-[color:var(--storefront-text-muted,#6b7280)]">Оформление заявки</li>
        </ol>
      </nav>

      <div class="mb-6 md:mb-8">
        <h1 class="text-xl font-bold text-[color:var(--storefront-title,#111827)] sm:text-2xl md:text-3xl">Оформление заявки на лизинг</h1>
        <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Укажите цель приобретения и регион для каждого транспортного средства
        </p>
      </div>

      <div v-if="loading" class="flex justify-center py-12">
        <div class="h-10 w-10 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
      </div>

      <section v-else class="rounded-lg bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4 shadow-sm sm:p-6 md:p-8" aria-labelledby="application-items-step-title">
        <div v-if="editableItems.length" class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 sm:p-4">
          <h2 id="application-items-step-title" class="mb-2 text-sm font-medium text-[color:var(--storefront-title,#111827)] sm:mb-3">Транспортные средства в заявке</h2>
          <div class="space-y-2 sm:space-y-3">
          <article
            v-for="item in editableItems"
            :key="`${item.type}:${item.id}`"
            class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-2.5 sm:p-3"
          >
            <div class="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-2">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-[color:var(--storefront-text,#111827)] sm:text-base">{{ item.title }}</p>
                <p class="text-xs text-[color:var(--storefront-text-muted,#4b5563)] sm:text-sm">Количество: {{ item.quantity }} шт.</p>
              </div>
              <p v-if="item.total_price" class="shrink-0 text-sm font-bold tabular-nums text-[color:var(--storefront-text-muted,#2563eb)] sm:text-base">
                {{ formatCommerceMoney(item.total_price, item.currency_code) }}
              </p>
            </div>

            <div class="mt-3 grid grid-cols-1 gap-3 border-t border-[color:var(--storefront-border,#f3f4f6)] pt-3 md:grid-cols-2">
              <div>
                <label class="mb-1 block text-xs font-medium text-[color:var(--storefront-label,#374151)]">Цель приобретения</label>
                <SearchableDropdown
                  v-model="item.leasing_purposes"
                  multiple
                  :items="purposesFor(item)"
                  label-key="purpose_display_name"
                  value-key="purpose_name"
                  placeholder="Выберите цель приобретения"
                  :searchable="false"
                  :allow-clear="true"
                  clear-label="Не выбрано"
                />
              </div>

              <div>
                <label class="mb-1 block text-xs font-medium text-[color:var(--storefront-label,#374151)]">Регион</label>
                <SearchableDropdown
                  v-model="item.regions"
                  :items="regionOptions"
                  label-key="region_label"
                  value-key="region_display_name"
                  :search-keys="['region_display_name', 'region_number', 'region_label']"
                  placeholder="Выберите один или несколько регионов"
                  search-placeholder="Найти регион..."
                  searchable
                  multiple
                  show-select-all
                  select-all-label="Выбрать все найденные регионы"
                />
                <div class="mt-2 flex flex-wrap gap-3 text-xs">
                  <button type="button" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]" @click="selectAllRegions(item)">Выбрать все регионы</button>
                  <button type="button" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)]" @click="item.regions = []">Очистить выбор</button>
                </div>
              </div>
            </div>

            <label class="mt-3 block border-t border-[color:var(--storefront-border,#f3f4f6)] pt-3">
              <span class="mb-1 block text-xs font-medium text-[color:var(--storefront-text,#374151)]">
                Комментарий <span class="font-normal text-[color:var(--storefront-text-muted,#6b7280)]">(необязательно)</span>
              </span>
              <textarea
                v-model.trim="item.comment"
                rows="2"
                maxlength="2000"
                class="storefront-control w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
              />
            </label>
          </article>
          </div>
        </div>

        <p v-else class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">В заявке нет транспортных средств.</p>

        <p v-if="error" class="mt-6 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">{{ error }}</p>

        <div class="mt-8 flex items-center justify-between gap-4">
          <button type="button" class="btn-secondary" :disabled="saving" @click="$emit('back')">Назад</button>
          <button type="button" class="btn-primary" :disabled="saving || editableItems.length === 0" @click="save">
            {{ saving ? 'Сохранение…' : 'Создать заявку' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { selectedLeasingPurposes } from '~/features/checkout/utils/leasingPurposes'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { formatCommerceMoney } from '~/features/commerce/money'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import type { EntityId } from '~/features/applications/api/applicationsApi'
import { useStorefront } from '~/features/storefront'

type EditableItem = CommerceApplicationItem & { regions: string[]; leasing_purposes: string[] }
type ItemUpdate = {
  line_id: EntityId
  kind: 'vehicle' | 'special_equipment'
  leasing_purpose: string | null
  leasing_purposes: string[]
  regions: string[]
  region: string | null
  comment: string | null
}
type LeasingPurposeOption = { purpose_name: string; purpose_display_name: string }
type LeasingRegionOption = { region_name: string; region_display_name: string; region_number: string; region_label: string }

const props = defineProps<{
  items: CommerceApplicationItem[]
  loading?: boolean
  saving?: boolean
  error?: string
}>()
const emit = defineEmits<{
  (event: 'save', items: ItemUpdate[]): void
  (event: 'back'): void
}>()

const config = useRuntimeConfig()
const { publicRoute } = useStorefront()
const editableItems = ref<EditableItem[]>([])
const purposeOptions = ref<LeasingPurposeOption[]>([])
const regionOptions = ref<LeasingRegionOption[]>([])

const purposesFor = (item: EditableItem) => [
  ...purposeOptions.value,
  ...item.leasing_purposes.filter(value => !purposeOptions.value.some(option => option.purpose_name === value)).map(value => ({ purpose_name: value, purpose_display_name: value })),
]

watch(
  () => props.items,
  (items) => {
    editableItems.value = items
      .filter(item => !item.status || !['removed', 'replaced', 'rejected'].includes(item.status))
      .map(item => ({
        ...item,
        leasing_purpose: item.leasing_purpose ?? null,
        leasing_purposes: selectedLeasingPurposes(item),
        comment: item.comment ?? null,
        regions: [...(item.regions ?? (item.region ? [item.region] : []))],
      }))
  },
  { immediate: true },
)

const loadDictionaries = async () => {
  const [purposes, regions] = await Promise.all([
    $fetch<{ purposes?: LeasingPurposeOption[] }>('/api/v1/applications/leasing-purposes', {
      baseURL: config.public.apiBase,
      credentials: 'include',
    }),
    $fetch<{ regions?: Array<Omit<LeasingRegionOption, 'region_label'>> }>('/api/v1/applications/leasing-regions', {
      baseURL: config.public.apiBase,
      credentials: 'include',
    }),
  ])
  purposeOptions.value = purposes.purposes ?? []
  regionOptions.value = (regions.regions ?? []).map(region => ({
    ...region,
    region_label: `${region.region_number} — ${region.region_display_name}`,
  }))
}

const selectAllRegions = (item: EditableItem) => {
  item.regions = regionOptions.value.map(region => region.region_display_name)
}

const save = () => {
  emit('save', editableItems.value.map(item => ({
    line_id: item.id,
    kind: item.type,
    leasing_purpose: item.leasing_purposes[0] ?? null,
    leasing_purposes: [...item.leasing_purposes],
    regions: [...item.regions],
    region: item.regions[0] ?? null,
    comment: item.comment?.trim() || null,
  })))
}

onMounted(() => {
  void loadDictionaries()
})
</script>

<style scoped>
.btn-primary {
  @apply rounded-md bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 py-3 font-medium text-[color:var(--storefront-text,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50;
}

.btn-secondary {
  @apply rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-5 py-3 font-medium text-[color:var(--storefront-text,#374151)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
