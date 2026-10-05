<template>
  <div data-storefront-block="client.application" class="card hover:shadow-lg transition-shadow duration-200">
    <div class="flex items-start justify-between mb-4">
      <div>
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
          Заявка {{ formatSourcedApplicationNumber(application, canViewApplicationSource(authStore.userRole)) }}
        </h3>
        <ApplicationSourceBadge v-if="canViewApplicationSource(authStore.userRole)" :source="application.source_type" class="mt-1" />
        <p v-if="application.group_number || application.group_id" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
          Группа заявок: {{ application.group_number || application.group_id }}
        </p>
      </div>
      <div class="text-right">
        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium" :class="statusClasses">
          {{ statusText }}
        </span>
      </div>
    </div>

    <RotatingSupportBadge
      v-if="applicationSupportPrograms.length"
      class="mb-4"
      :programs="applicationSupportPrograms"
    />

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Компания-заявитель</div>
        <div class="font-medium">{{ companyName }}</div>
        <div v-if="companyInn" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">ИНН {{ companyInn }}</div>
      </div>
      <div>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Общая стоимость</div>
        <div class="font-medium">{{ formatApplicationAmount(applicationTotalAmount) }}</div>
      </div>
      <div>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ equipmentAmountLabel }}</div>
        <div class="font-medium">{{ formatApplicationAmount(actionMode === 'details' ? (vehicleOnlyAmount || clientEquipmentAmount || applicationTotalAmount) : clientEquipmentAmount) }}</div>
      </div>
      <div>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Количество единиц</div>
        <div class="font-medium">{{ itemsCount }}</div>
      </div>
      <div>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Дата подачи</div>
        <div class="font-medium">{{ formatDate(application.created_at) }}</div>
      </div>
    </div>

    <ApplicationDealerDistribution
      v-if="authStore.isDistributor"
      class="mb-4"
      :application-id="application.id"
      :positions="application.dealer_distribution ?? []"
      @updated="emit('updated')"
    />

    <ul v-if="normalizedItems.length" class="mb-4 grid gap-2 sm:grid-cols-2">
      <li v-for="item in normalizedItems" :key="`${item.type}:${item.id}`" class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm" :class="isHistoricalItem(item.status) ? 'opacity-70' : ''">
        <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ item.title }}</span>
        <CommerceApplicationItemComment :comment="item.comment" />
        <span class="mt-1 block text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ item.type === 'vehicle' ? 'Автомобиль' : 'Спецтехника' }}</span>
        <span v-if="isHistoricalItem(item.status)" class="mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="historicalItemStatusPresentation(item).badgeClass">{{ historicalItemStatusPresentation(item).label }}</span>
      </li>
    </ul>

    <div v-if="application.down_payment_percent || application.monthly_payment" class="mt-2 space-y-1">
      <div v-if="application.down_payment_percent" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        <span class="font-medium">Условия:</span> {{ application.down_payment_percent }}% аванс, {{
          application.lease_term_months }} мес.
      </div>
      <div v-if="application.monthly_payment" class="text-sm text-[color:var(--storefront-text,#111827)]">
        <span class="font-medium">Ежемесячный платеж:</span> {{ formatPrice(application.monthly_payment) }}
      </div>
      <div v-if="application.rate" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        <span class="font-medium">Ставка:</span> {{ application.rate }}%
      </div>
    </div>

    <div class="flex items-center justify-end pt-4 border-t border-[color:var(--storefront-border,#e5e7eb)]">
      <NuxtLink
        v-if="actionMode === 'continue'"
        :to="checkoutPath"
        class="btn-primary text-sm"
      >
        Продолжить
      </NuxtLink>
      <button
        v-else
        type="button"
        class="btn-primary text-sm"
        @click="emit('open-details', application)"
      >
        Открыть заявку
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import ApplicationDealerDistribution from './ApplicationDealerDistribution.vue'
import CommerceApplicationItemComment from '~/features/commerce/components/CommerceApplicationItemComment.vue'
import { canViewApplicationSource, formatSourcedApplicationNumber } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import type { Application } from '~/features/applications/api/applicationsApi'
import { calculateApplicationVehicleAmount } from '~/features/applications/applicationVehicleAmount'
import { formatCommerceMoney } from '~/features/commerce/money'
import { applicationVehicleStatusPresentation } from '~/features/commerce/applicationVehicleStatusPresentation'
import RotatingSupportBadge from '~/components/support/RotatingSupportBadge.vue'
import { normalizeSupportPrograms, supportProgramsFromSnapshot } from '~/types/support'

const props = defineProps<{
  application: Application
  actionMode?: 'continue' | 'details'
}>()

const emit = defineEmits<{
  'open-details': [application: Application]
  updated: []
}>()

const authStore = useAuthStore()
const { formatPrice } = useFormatPrice()

const actionMode = computed(() => props.actionMode || 'continue')
const applicationSupportPrograms = computed(() => normalizeSupportPrograms([
  ...normalizeSupportPrograms(props.application.calculation?.support_program_details),
  ...(props.application.items ?? []).flatMap((item) => {
    const direct = normalizeSupportPrograms(item.support_program_details)
    return direct.length ? direct : supportProgramsFromSnapshot(item.snapshot)
  }),
]))
const checkoutPath = computed(() => `/application/${props.application.id}`)
const companyName = computed(() => props.application.company?.name || props.application.company_name || 'Не указана')
const companyInn = computed(() => props.application.company?.inn || props.application.company_inn || '')
const historicalItemStatuses = new Set(['removed', 'replaced', 'rejected'])
const isHistoricalItem = (status: string | null): boolean => Boolean(status && historicalItemStatuses.has(status))
const normalizedItems = computed(() => props.application.items ?? [])
const liveNormalizedItems = computed(() => normalizedItems.value.filter((item) => !isHistoricalItem(item.status)))
type HistoricalItemStatusPresentation = Readonly<{
  label: string
  badgeClass: string
}>
const historicalItemStatusPresentation = (
  item: NonNullable<Application['items']>[number],
): HistoricalItemStatusPresentation => {
  if (item.type === 'vehicle' && item.status === 'rejected') {
    return applicationVehicleStatusPresentation(item.status)
  }
  return {
    label: ({ removed: 'Удалена', replaced: 'Заменена', rejected: 'Отклонена' })[item.status ?? ''] ?? 'История',
    badgeClass: 'bg-[color:rgb(var(--storefront-neutral-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-neutral-text,#374151)]',
  }
}

const hasSpecialEquipment = computed(() =>
  (props.application.items ?? []).some(item => item.type === 'special_equipment')
)
const hasVehicles = computed(() =>
  Boolean((props.application.vehicles && props.application.vehicles.length > 0)
  || (props.application.items ?? []).some(item => item.type === 'vehicle'))
)
const equipmentAmountLabel = computed(() => {
  if (hasSpecialEquipment.value || !hasVehicles.value) {
    return 'Стоимость техники'
  }
  return 'Стоимость ТС'
})

const vehicleOnlyAmount = computed(() => calculateApplicationVehicleAmount(props.application))
const clientEquipmentAmount = computed(() =>
  props.application.total_items_price
  ?? props.application.total_vehicles_price
  ?? vehicleOnlyAmount.value
)
const applicationTotalAmount = computed(() =>
  props.application.total_amount
  ?? props.application.total_cost
  ?? props.application.total_items_price
  ?? vehicleOnlyAmount.value
)
const formatApplicationAmount = (value: string | number | null | undefined): string =>
  typeof value === 'string' ? formatCommerceMoney(value) : formatPrice(value ?? 0)
const vehicleQuantity = (vehicle: Application['vehicles'][number]) => {
  const quantity = Number(vehicle.quantity)
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1
}
const fallbackVehicleCount = computed(() => {
  const summaryCount = Number(props.application.vehicles_count ?? props.application.vehicle_count)
  if (Number.isFinite(summaryCount) && summaryCount > 0) return summaryCount
  return 0
})
const vehiclesCount = computed(() => {
  const countFromVehicles = (props.application.vehicles || []).reduce((sum, vehicle) => sum + vehicleQuantity(vehicle), 0)
  return countFromVehicles > 0 ? countFromVehicles : fallbackVehicleCount.value
})
const itemsCount = computed(() => {
  const reportedCount = Number(props.application.items_count)
  if (Number.isFinite(reportedCount) && reportedCount > 0) return reportedCount

  const countFromItems = liveNormalizedItems.value.reduce(
    (sum, item) => sum + vehicleQuantity(item as Application['vehicles'][number]),
    0,
  )
  return countFromItems > 0 ? countFromItems : vehiclesCount.value
})
const normalizedStatus = computed(() => props.application.group_status || props.application.application_status || props.application.status)

const statusClasses = computed(() => {
  switch (normalizedStatus.value) {
    case 'deal':
    case 'issued':
      return 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]'
    case 'closed':
    case 'rejected':
      return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
    default:
      return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]'
  }
})

const statusText = computed(() => {
  if (props.application.group_status_label) return props.application.group_status_label
  if (props.application.application_status_label) return props.application.application_status_label
  switch (normalizedStatus.value) {
    case 'deal':
    case 'issued':
      return 'Сделка'
    case 'closed':
      return 'Закрыта'
    case 'rejected':
      return 'Отклонена'
    default:
      return 'Активна'
  }
})

const formatDate = (dateString: string | undefined) => {
  if (!dateString) return 'Не указано'

  try {
    const date = new Date(dateString)
    if (Number.isNaN(date.getTime())) {
      return 'Неверная дата'
    }

    return date.toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch (error) {
    console.error('Error formatting date:', error)
    return 'Ошибка даты'
  }
}
</script>
