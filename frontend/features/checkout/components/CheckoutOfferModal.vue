<template>
  <Modal
    :show="show"
    :show-footer="false"
    size="full"
    body-class="p-0"
    @close="$emit('close')"
  >
    <div data-storefront-block="client.checkout" class="mx-auto max-h-[88vh] max-w-[1920px] overflow-y-auto">
      <div class="sticky top-0 z-10 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-5 py-4 sm:px-6">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Заявка {{ applicationNumber }}</h3>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <span
                class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium"
                :class="statusClass(item.status)"
              >
                {{ statusText(item.status) }}
              </span>
              <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                {{ leasingCompanyName }}
              </span>
            </div>
          </div>
          <button
            type="button"
            class="storefront-action-primary inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] transition-colors hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:cursor-wait disabled:border-[color:var(--storefront-primary-disabled-border,#93c5fd)] disabled:bg-[color:rgb(var(--storefront-primary-disabled-rgb,147_197_253)/var(--tw-bg-opacity,1))]"
            :disabled="downloadingPdf"
            @click="downloadApplicationPdf"
          >
            <ArrowDownTrayIcon class="h-4 w-4" aria-hidden="true" />
            {{ downloadingPdf ? 'Формируем PDF...' : 'Скачать PDF' }}
          </button>
        </div>
      </div>

      <div class="space-y-6 px-5 py-5 sm:px-6">
        <section class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Статус заявки</h4>
            <span
              class="inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium"
              :class="statusClass(item.status)"
            >
              {{ statusText(item.status) }}
            </span>
          </div>
          <div class="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <div
              v-for="stage in statusStages"
              :key="stage.id"
              class="rounded-lg border p-3"
              :class="statusStageClass(stage)"
            >
              <div class="flex items-center gap-2">
                <span
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                  :class="statusStageMarkerClass(stage)"
                >
                  {{ stage.index }}
                </span>
                <div class="text-sm font-semibold leading-tight">{{ stage.label }}</div>
              </div>
              <div class="mt-2 text-xs leading-5" :class="statusStageTextClass(stage)">
                {{ stage.description }}
              </div>
            </div>
          </div>
        </section>

        <section class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
          <div class="border-b border-[color:var(--storefront-border,#e5e7eb)] px-4 py-3">
            <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Условия по заявке</h4>
            <p v-if="responsesLoading" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Загружаем условия КП...</p>
            <p v-else-if="responsesError" class="mt-1 text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ responsesError }}</p>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-[980px] w-full border-collapse text-sm">
              <thead>
                <tr class="bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-left text-xs font-semibold uppercase tracking-wide text-[color:var(--storefront-text-muted,#4b5563)]">
                  <th class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2">Тип КП</th>
                  <th v-for="column in conditionColumns" :key="column.key" class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right">
                    {{ column.label }}
                  </th>
                  <th class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in conditionRows"
                  :key="row.id"
                  :class="row.id === 'requested' ? 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]'"
                >
                  <th class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-left font-semibold text-[color:var(--storefront-text,#111827)]">
                    {{ row.label }}
                  </th>
                  <td
                    v-for="column in conditionColumns"
                    :key="column.key"
                    class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right"
                    :class="conditionCellClass(row, column.key)"
                  >
                    {{ formatConditionValue(row.values[column.key], column.format) }}
                  </td>
                  <td class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right">
                    <div v-if="row.hasProposal" class="flex justify-end gap-2">
                      <button
                        type="button"
                        class="storefront-action-ghost rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
                        :disabled="isConditionActionDisabled(row)"
                        @click="submitConditionAction(row)"
                      >
                        {{ decisionLoadingRowId === row.id ? 'Сохраняем...' : conditionActionLabel(row) }}
                      </button>
                      <button
                        type="button"
                        class="storefront-action-ghost rounded-md border border-[color:var(--storefront-primary-border,#2563eb)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#1d4ed8)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:border-[color:var(--storefront-primary-disabled-border,#bfdbfe)] disabled:text-[color:var(--storefront-primary-disabled-foreground,#93c5fd)]"
                        :disabled="downloadingResponsePdfRowId === row.id"
                        @click="downloadConditionPdf(row)"
                      >
                        {{ downloadingResponsePdfRowId === row.id ? 'Скачиваем...' : 'Скачать PDF' }}
                      </button>
                      <button
                        type="button"
                        class="storefront-action-ghost inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
                        @click="selectedScheduleKind = row.id"
                      >
                        <CalendarDaysIcon class="h-3.5 w-3.5" aria-hidden="true" />
                        График платежей
                      </button>
                    </div>
                    <span v-else class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section class="space-y-4">
            <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Техника в заявке</h4>
            <div v-if="applicationItems.length > 0" class="space-y-3">
              <component
                v-for="applicationItem in applicationItems"
                :key="applicationItemKey(applicationItem)"
                :is="applicationItemHref(applicationItem) ? NuxtLink : 'article'"
                :to="applicationItemHref(applicationItem) ?? undefined"
                class="text-[color:var(--storefront-icon,inherit)] group block overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] transition-colors"
                :class="applicationItemHref(applicationItem) ? 'hover:border-[color:var(--storefront-border,#93c5fd)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/0.4)]' : ''"
              >
                <div class="flex flex-col sm:flex-row">
                  <div class="grid h-36 w-full shrink-0 place-items-center overflow-hidden bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] sm:h-auto sm:w-40">
                    <img
                      v-if="applicationItemImageSrc(applicationItem)"
                      :src="applicationItemImageSrc(applicationItem) ?? undefined"
                      :alt="applicationItemTitle(applicationItem)"
                      class="h-full w-full object-contain"
                      loading="lazy"
                    >
                    <PhotoIcon v-else class="h-10 w-10 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
                  </div>
                  <div class="min-w-0 flex-1 p-4">
                    <div class="flex items-start justify-between gap-4">
                      <div class="min-w-0">
                        <h5 class="truncate font-semibold text-[color:var(--storefront-title,#111827)]" :class="applicationItemHref(applicationItem) ? 'group-hover:text-[color:var(--storefront-title,#1d4ed8)]' : ''">{{ applicationItemTitle(applicationItem) }}</h5>
                        <p class="mt-1 line-clamp-2 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ applicationItemSubtitle(applicationItem) }}</p>
                      </div>
                      <div class="shrink-0 text-right text-base font-semibold text-[color:var(--storefront-text-muted,#2563eb)]">
                        {{ formatPriceLike(applicationItemPrice(applicationItem)) }}
                      </div>
                    </div>
                    <CommerceApplicationItemComment :comment="stringField(applicationItem, 'comment')" />
                    <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                      <div v-if="field(applicationItem, 'year') || field(applicationItem, 'vehicle_year')">
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Год</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ textValue(field(applicationItem, 'year') || field(applicationItem, 'vehicle_year')) }}</dd>
                      </div>
                      <div>
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Количество</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ textValue(field(applicationItem, 'quantity') || 1) }}</dd>
                      </div>
                      <div v-if="field(applicationItem, 'color')">
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Цвет</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ textValue(field(applicationItem, 'color')) }}</dd>
                      </div>
                      <div v-if="applicationItemType(applicationItem) === 'vehicle'">
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Цель приобретения</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ vehicleLeasingPurpose(applicationItem) }}</dd>
                      </div>
                      <div v-if="applicationItemType(applicationItem) === 'vehicle'">
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Регион</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">
                          <VehicleRegionsDisplay :regions="vehicleRegionValues(applicationItem)" />
                        </dd>
                      </div>
                      <div>
                        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Итого</dt>
                        <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ formatPriceLike(applicationItemTotal(applicationItem)) }}</dd>
                      </div>
                    </dl>
                  </div>
                </div>
              </component>
            </div>
            <p v-else class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              Техника в заявке не найдена.
            </p>
          </section>

          <aside class="space-y-4">
            <section class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
              <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Лизингодатель</h4>
              <dl class="mt-3 space-y-3 text-sm">
                <div>
                  <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Название</dt>
                  <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ leasingCompanyName }}</dd>
                </div>
                <div>
                  <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН</dt>
                  <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ leasingCompanyInn }}</dd>
                </div>
              </dl>
            </section>

            <section class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
              <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Компания-заявитель</h4>
              <dl class="mt-3 space-y-3 text-sm">
                <div>
                  <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Название</dt>
                  <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ companyName }}</dd>
                </div>
                <div>
                  <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН</dt>
                  <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ companyInn }}</dd>
                </div>
                <div>
                  <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Адрес</dt>
                  <dd class="font-medium text-[color:var(--storefront-value,#111827)]">{{ companyAddress }}</dd>
                </div>
              </dl>
            </section>

            <section v-if="item.decision_comment || item.review_notes" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
              <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Комментарий</h4>
              <p v-if="item.decision_comment" class="mt-3 text-sm text-[color:var(--storefront-text,#374151)]">{{ item.decision_comment }}</p>
              <p v-if="item.review_notes" class="mt-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ item.review_notes }}</p>
            </section>
          </aside>
        </div>
      </div>
    </div>
  </Modal>

  <CheckoutPaymentScheduleModal
    v-if="selectedScheduleKind"
    :show="Boolean(selectedScheduleKind)"
    :item="item"
    :application="application"
    :source-kind="selectedScheduleKind"
    @close="selectedScheduleKind = null"
  />
</template>

<script setup lang="ts">
import { useNotificationCompanyRequest } from '~/features/notifications'
const { request: notificationRequest, url: notificationUrl } = useNotificationCompanyRequest()
import { NuxtLink } from '#components'
import { computed, ref, watch } from 'vue'
import { ArrowDownTrayIcon, CalendarDaysIcon, PhotoIcon } from '@heroicons/vue/24/outline'
import Modal from '~/components/ui/Modal.vue'
import CheckoutPaymentScheduleModal from '~/features/checkout/components/CheckoutPaymentScheduleModal.vue'
import VehicleRegionsDisplay from '~/features/applications/components/VehicleRegionsDisplay.vue'
import { formatApplicationVehicleTitle, formatLeasingPurpose } from '~/features/applications/utils/applicationVehicleDisplay'
import CommerceApplicationItemComment from '~/features/commerce/components/CommerceApplicationItemComment.vue'
import { specialEquipmentApplicationItemRoleLabel } from '~/features/commerce/applicationItemPresentation'
import { formatCommerceMoney } from '~/features/commerce/money'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import { useStorefront } from '~/features/storefront'
import type { Application } from '@/types'
import type { ClientLeasingResponsesResponse, LeasingProposal } from '~/features/leasing/api/leasingApi'
import { toStorefrontInternalRoute } from '~/utils/storefrontRoute'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

type ApplicationCompatible = Application & Record<string, unknown>

interface LcaListItem {
  id: string
  application_id: string
  leasing_company_id: string
  leasing_company_name?: string | null
  leasing_company_inn?: string | null
  company_name?: string | null
  company_inn?: string | null
  display_number?: string | null
  application_status?: string | null
  status: string
  review_notes?: string | null
  decision_comment?: string | null
  response_pdf_s3_key?: string | null
  response_pdf_file_name?: string | null
  response_pdf_size?: number | null
  response_pdf_uploaded_at?: string | null
  submitted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

type ConditionKey = 'monthly_payment' | 'down_payment_percent' | 'down_payment' | 'lease_term_months' | 'total_amount' | 'total_cost' | 'buyout_amount' | 'total_interest'
type ConditionFormat = 'money' | 'percent' | 'months'
type ConditionRowId = 'requested' | 'preliminary' | 'final'

interface ConditionRow {
  id: ConditionRowId
  label: string
  proposal: LeasingProposal | null
  hasProposal: boolean
  values: Record<ConditionKey, number | string | null>
}

const props = defineProps<{
  show: boolean
  item: LcaListItem
  application: ApplicationCompatible | null
}>()

const emit = defineEmits<{ close: []; changed: [] }>()

const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()
const { publicRoute } = useStorefront()
const toast = useToast()

const clientResponses = ref<ClientLeasingResponsesResponse | null>(null)
const responsesLoading = ref(false)
const responsesError = ref('')
const downloadingPdf = ref(false)
const downloadingResponsePdfRowId = ref<ConditionRowId | null>(null)
const decisionLoadingRowId = ref<ConditionRowId | null>(null)
const selectedScheduleKind = ref<ConditionRowId | null>(null)

const conditionColumns: Array<{ key: ConditionKey; label: string; format: ConditionFormat }> = [
  { key: 'monthly_payment', label: 'Ежемесячный платеж, ₽', format: 'money' },
  { key: 'down_payment_percent', label: 'Аванс, %', format: 'percent' },
  { key: 'down_payment', label: 'Аванс, ₽', format: 'money' },
  { key: 'lease_term_months', label: 'Срок, мес.', format: 'months' },
  { key: 'total_amount', label: 'Стоимость договора, ₽', format: 'money' },
  { key: 'total_cost', label: 'Общая стоимость, ₽', format: 'money' },
  { key: 'buyout_amount', label: 'Выкупная стоимость, ₽', format: 'money' },
  { key: 'total_interest', label: 'Проценты, ₽', format: 'money' },
]

const field = (source: Record<string, unknown> | null | undefined, name: string): unknown => source?.[name]

const stringField = (source: Record<string, unknown> | null | undefined, name: string): string => {
  const value = field(source, name)
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}

const numberLikeField = (source: Record<string, unknown> | null | undefined, name: string): number | string | null => {
  const value = field(source, name)
  return typeof value === 'number' || typeof value === 'string' ? value : null
}

const toNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const applicationNumber = computed(() => props.item.display_number || stringField(props.application, 'display_number') || '—')
const leasingCompanyName = computed(() => props.item.leasing_company_name || '—')
const leasingCompanyInn = computed(() => props.item.leasing_company_inn || '—')

const pdfUrl = computed(() => {
  const base = config.public.apiBase.replace(/\/$/, '')
  return `${base}/api/v1/applications/${props.item.application_id}/leasing-responses/${props.item.leasing_company_id}/pdf?lca_id=${props.item.id}`
})

const pdfFileName = computed(() => {
  const number = applicationNumber.value.replace(/[^\wа-яА-Я-]+/g, '-')
  return `leasing-response-lca-${number || 'application'}.pdf`
})

const downloadFile = async (url: string, fileName: string) => {
  const response = await fetch(notificationUrl(url), { credentials: 'include' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName
  link.click()
  URL.revokeObjectURL(objectUrl)
}

const downloadApplicationPdf = async () => {
  if (downloadingPdf.value) return
  downloadingPdf.value = true
  try {
    await downloadFile(pdfUrl.value, pdfFileName.value)
  } catch (err) {
    console.error('Application PDF download failed', err)
    toast.error('Не удалось скачать PDF заявки')
  } finally {
    downloadingPdf.value = false
  }
}

const statusStages = [
  {
    id: 'sent',
    index: 1,
    label: 'Отправлена',
    description: 'Заявка передана лизингодателю.',
    statuses: ['submitted', 'pending_distribution', 'under_review'],
  },
  {
    id: 'preliminary',
    index: 2,
    label: 'Предварительное КП',
    description: 'Получены предварительные условия.',
    statuses: ['approved_scoring', 'approved_scoring_another_cond'],
  },
  {
    id: 'documents',
    index: 3,
    label: 'Запрос дополнительных документов',
    description: 'Лизингодатель запросил доп. материалы.',
    statuses: ['documents_required', 'under_review_with_docs'],
  },
  {
    id: 'final',
    index: 4,
    label: 'Итоговое КП',
    description: 'Получены финальные условия.',
    statuses: ['approved_final', 'approved_final_another_cond'],
  },
  {
    id: 'selected',
    index: 5,
    label: 'Выбор ЛК',
    description: 'Лизингодатель выбран клиентом.',
    statuses: ['selected_lc'],
  },
  {
    id: 'deal',
    index: 6,
    label: 'Сделка',
    description: 'Сделка заключена.',
    statuses: ['deal'],
  },
] as const

type StatusStage = typeof statusStages[number]

const currentStatusStageIndex = computed(() => {
  if (props.item.status === 'closed') return statusStages.length
  if (props.item.status.startsWith('rejected')) return -1
  const stage = statusStages.find(stage => (stage.statuses as readonly string[]).includes(props.item.status))
  return stage?.index || 1
})

const statusStageState = (stage: StatusStage): 'active' | 'done' | 'future' | 'rejected' => {
  if (props.item.status.startsWith('rejected')) return stage.index === 1 ? 'rejected' : 'future'
  if ((stage.statuses as readonly string[]).includes(props.item.status)) return 'active'
  if (stage.index < currentStatusStageIndex.value) return 'done'
  return 'future'
}

const statusStageClass = (stage: StatusStage): string => {
  const state = statusStageState(stage)
  if (state === 'active') return 'border-[color:var(--storefront-border,#93c5fd)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#172554)] shadow-sm'
  if (state === 'done') return 'border-[color:var(--storefront-success-border,#bbf7d0)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#052e16)]'
  if (state === 'rejected') return 'border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#450a0a)]'
  return 'border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#6b7280)]'
}

const statusStageMarkerClass = (stage: StatusStage): string => {
  const state = statusStageState(stage)
  if (state === 'active') return 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]'
  if (state === 'done') return 'bg-[color:rgb(var(--storefront-success-rgb,22_163_74)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]'
  if (state === 'rejected') return 'bg-[color:rgb(var(--storefront-error-rgb,220_38_38)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]'
  return 'bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#6b7280)] ring-1 ring-[color:var(--storefront-border,#d1d5db)]'
}

const statusStageTextClass = (stage: StatusStage): string => {
  const state = statusStageState(stage)
  if (state === 'active') return 'text-[color:var(--storefront-text,#1d4ed8)]'
  if (state === 'done') return 'text-[color:var(--storefront-success-text,#15803d)]'
  if (state === 'rejected') return 'text-[color:var(--storefront-error-text,#b91c1c)]'
  return 'text-[color:var(--storefront-text-muted,#6b7280)]'
}

const matchedResponse = computed(() => {
  const responses = clientResponses.value?.responses || []
  return responses.find(response => String(response.leasing_company?.id || '') === String(props.item.leasing_company_id)) || null
})

const responsePdfUrl = (row: ConditionRow): string => {
  const base = config.public.apiBase.replace(/\/$/, '')
  return `${base}/api/v1/applications/${props.item.application_id}/leasing-responses/${props.item.leasing_company_id}/pdf?proposal_kind=${row.id}&lca_id=${props.item.id}`
}

const responsePdfFileName = (row: ConditionRow): string => {
  const number = applicationNumber.value.replace(/[^\wа-яА-Я-]+/g, '-')
  return `leasing-response-${row.id}-${number || 'application'}.pdf`
}

const downloadConditionPdf = async (row: ConditionRow) => {
  if (!row.hasProposal || downloadingResponsePdfRowId.value) return
  downloadingResponsePdfRowId.value = row.id
  try {
    await downloadFile(responsePdfUrl(row), responsePdfFileName(row))
  } catch (err) {
    console.error('LC response PDF download failed', err)
    toast.error('Не удалось скачать PDF КП')
  } finally {
    downloadingResponsePdfRowId.value = null
  }
}

const proposalByKind = (kind: 'preliminary' | 'final'): LeasingProposal | null => {
  const proposals = matchedResponse.value?.proposals || []
  const matching = proposals.filter(proposal => proposal.kind === kind)
  matching.sort((a, b) => b.position - a.position)
  return matching[0] || null
}

const valuesFromSource = (source: Record<string, unknown> | null | undefined): Record<ConditionKey, number | string | null> => ({
  monthly_payment: numberLikeField(source, 'monthly_payment'),
  down_payment_percent: numberLikeField(source, 'down_payment_percent'),
  down_payment: numberLikeField(source, 'down_payment'),
  lease_term_months: numberLikeField(source, 'lease_term_months'),
  total_amount: numberLikeField(source, 'total_amount'),
  total_cost: numberLikeField(source, 'total_cost'),
  buyout_amount: numberLikeField(source, 'buyout_amount'),
  total_interest: numberLikeField(source, 'total_interest'),
})

const conditionRows = computed<ConditionRow[]>(() => {
  const preliminaryProposal = proposalByKind('preliminary')
  const finalProposal = proposalByKind('final')
  return [
    {
      id: 'requested',
      label: 'Запрошенные условия',
      proposal: null,
      hasProposal: false,
      values: valuesFromSource(props.application),
    },
    {
      id: 'preliminary',
      label: 'Предварительное одобрение',
      proposal: preliminaryProposal,
      hasProposal: Boolean(preliminaryProposal),
      values: valuesFromSource(preliminaryProposal as Record<string, unknown> | null),
    },
    {
      id: 'final',
      label: 'Итоговое одобрение',
      proposal: finalProposal,
      hasProposal: Boolean(finalProposal),
      values: valuesFromSource(finalProposal as Record<string, unknown> | null),
    },
  ]
})

const conditionActionLabel = (row: ConditionRow): string => {
  if (row.id === 'requested') return 'Запрошено'
  if (row.id === 'preliminary' && row.proposal?.client_decision_action === 'accepted') return 'Отменить'
  if (row.id === 'final' && props.item.status === 'selected_lc') return 'Выбрана ЛК'
  if (row.id === 'final' && props.item.status === 'deal') return 'Сделка заключена'
  return row.id === 'preliminary' ? 'Принять КП' : 'Выбрать'
}

const isConditionActionDisabled = (row: ConditionRow): boolean => {
  if (!row.hasProposal || row.id === 'requested') return true
  if (decisionLoadingRowId.value !== null) return true
  return row.id === 'final' && (props.item.status === 'selected_lc' || props.item.status === 'deal')
}

const submitConditionAction = async (row: ConditionRow) => {
  if (isConditionActionDisabled(row) || !row.proposal) return
  decisionLoadingRowId.value = row.id
  try {
    if (row.id === 'preliminary') {
      const action = row.proposal.client_decision_action === 'accepted' ? 'cancelled' : 'accepted'
      await notificationRequest(
        `/api/v1/applications/${props.item.application_id}/proposals/${row.proposal.id}/decision`,
        {
          baseURL: config.public.apiBase,
          credentials: 'include',
          method: 'POST',
          body: { action },
        },
      )
    } else if (row.id === 'final') {
      await notificationRequest(
        `/api/v1/applications/${props.item.application_id}/lca/${props.item.id}/select`,
        {
          baseURL: config.public.apiBase,
          credentials: 'include',
          method: 'POST',
        },
      )
    }
    emit('changed')
    await loadResponses()
  } catch (err) {
    console.error('Condition action failed', err)
    toast.error(row.id === 'preliminary' ? 'Не удалось обновить выбор КП' : 'Не удалось выбрать лизинговую компанию')
  } finally {
    decisionLoadingRowId.value = null
  }
}

const bestOfferValues = computed(() => {
  const result: Partial<Record<ConditionKey, number>> = {}
  for (const column of conditionColumns) {
    const candidates = conditionRows.value
      .filter(row => row.id !== 'requested')
      .map(row => toNumber(row.values[column.key]))
      .filter((value): value is number => value !== null)
    if (candidates.length > 0) result[column.key] = Math.min(...candidates)
  }
  return result
})

const conditionCellClass = (row: ConditionRow, key: ConditionKey): string => {
  if (row.id === 'requested') return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#172554)] font-semibold'
  const value = toNumber(row.values[key])
  if (value === null) return 'text-[color:var(--storefront-text-muted,#9ca3af)]'
  const best = bestOfferValues.value[key]
  if (best !== undefined && value === best) return 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#052e16)] font-semibold'
  const requested = toNumber(conditionRows.value[0]?.values[key])
  if (requested !== null && value > requested) return 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#422006)]'
  return 'text-[color:var(--storefront-text,#111827)]'
}

const formatConditionValue = (value: number | string | null, format: ConditionFormat): string => {
  const numeric = toNumber(value)
  if (numeric === null) return '—'
  if (format === 'money') return formatPrice(numeric)
  if (format === 'percent') return `${numeric}%`
  return `${numeric} мес.`
}

const vehicles = computed<Array<Record<string, unknown>>>(() => {
  const fromVehicles = field(props.application, 'vehicles')
  if (Array.isArray(fromVehicles)) return fromVehicles as Array<Record<string, unknown>>
  const fromDetails = field(props.application, 'vehicle_details')
  return Array.isArray(fromDetails) ? fromDetails as Array<Record<string, unknown>> : []
})

const historicalItemStatuses = new Set(['removed', 'replaced', 'rejected'])
const projectedApplicationItems = computed<Array<Record<string, unknown>>>(() => {
  const items = field(props.application, 'items')
  if (!Array.isArray(items)) return []
  return (items as Array<Record<string, unknown>>).filter((item) => {
    const status = stringField(item, 'status')
    return !status || !historicalItemStatuses.has(status)
  })
})
const applicationItems = computed(() => projectedApplicationItems.value.length > 0
  ? projectedApplicationItems.value
  : vehicles.value)

const isProjectedApplicationItem = (item: Record<string, unknown>): boolean => {
  const type = stringField(item, 'type')
  return type === 'vehicle' || type === 'special_equipment'
}
const applicationItemType = (item: Record<string, unknown>): 'vehicle' | 'special_equipment' =>
  stringField(item, 'type') === 'special_equipment' ? 'special_equipment' : 'vehicle'
const applicationItemKey = (item: Record<string, unknown>): string => {
  if (isProjectedApplicationItem(item)) return `${applicationItemType(item)}:${stringField(item, 'id')}`
  return vehicleKey(item)
}
const applicationItemHref = (item: Record<string, unknown>): string | null => {
  if (!isProjectedApplicationItem(item)) return publicRoute(vehicleHref(item))
  const detailUrl = stringField(item, 'detail_url')
  return detailUrl ? toStorefrontInternalRoute(detailUrl, publicRoute) : null
}
const applicationItemImageSrc = (item: Record<string, unknown>): string | null => {
  if (!isProjectedApplicationItem(item)) return vehicleImageSrc(item)
  const imageUrl = stringField(item, 'image_url')
  return imageUrl.startsWith('/api/v1/') ? imageUrl : null
}
const applicationItemTitle = (item: Record<string, unknown>): string =>
  stringField(item, 'title') || vehicleTitle(item)
const applicationItemRole = (
  item: Record<string, unknown>,
): CommerceApplicationItem['item_role'] => {
  const role = stringField(item, 'item_role')
  return role === 'attachment' || role === 'component' ? role : 'offer'
}
const applicationItemStatusLabel = (item: Record<string, unknown>): string => ({
  active: 'Активна',
  reserved: 'Зарезервирована',
  pending: 'Ожидает обработки',
  approved: 'Подтверждена',
  removed: 'Удалена',
  replaced: 'Заменена',
  rejected: 'Отклонена',
})[stringField(item, 'status')] ?? stringField(item, 'status')
const applicationItemSubtitle = (item: Record<string, unknown>): string => {
  if (!isProjectedApplicationItem(item)) return vehicleSubtitle(item)
  if (applicationItemType(item) === 'vehicle') return 'Автомобиль'
  return [
    'Спецтехника',
    specialEquipmentApplicationItemRoleLabel(applicationItemRole(item)),
    applicationItemStatusLabel(item),
  ].filter(Boolean).join(' · ')
}
const applicationItemPrice = (item: Record<string, unknown>): number | string | null => (
  numberLikeField(item, 'unit_price')
  ?? numberLikeField(item, 'price')
  ?? vehiclePrice(item)
)
const applicationItemTotal = (item: Record<string, unknown>): number | string | null => (
  numberLikeField(item, 'total_price')
  ?? numberLikeField(item, 'total_amount')
  ?? vehicleTotal(item)
)

const vehicleKey = (vehicle: Record<string, unknown>) => stringField(vehicle, 'id')
const vehicleRouteValue = (vehicle: Record<string, unknown>, name: string): string => {
  const value = field(vehicle, name)
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'string' && value.trim()) return value.trim()
  return ''
}
const vehicleHref = (vehicle: Record<string, unknown>) => {
  if (typeof vehicle.detail_url === 'string' && vehicle.detail_url) return vehicle.detail_url
  return '/special-equipment'
}
const normalizeVehicleImageSrc = (value: unknown): string => {
  if (typeof value !== 'string' || !value.trim()) return ''
  const image = value.trim()
  if (image.startsWith('/api/v1/') || image.startsWith('/images/')) return image
  if (image.startsWith('/') || image.includes('/') || image.includes('\\')) return ''
  return vehicleImageUrl(image)
}
const vehicleImageSrc = (vehicle: Record<string, unknown>) => {
  const images = field(vehicle, 'images')
  if (Array.isArray(images) && images.length > 0) {
    const image = normalizeVehicleImageSrc(images[0])
    if (image) return image
  }
  for (const fieldName of ['image_url', 'image', 'main_image', 'photo_url', 'photo']) {
    const image = normalizeVehicleImageSrc(field(vehicle, fieldName))
    if (image) return image
  }
  return '/images/car-placeholder.png'
}
const vehicleTitle = (vehicle: Record<string, unknown>) => formatApplicationVehicleTitle(vehicle, 'Автомобиль', false)
const vehicleSubtitle = (vehicle: Record<string, unknown>) => {
  return [
    stringField(vehicle, 'generation_name'),
    stringField(vehicle, 'configuration_name'),
    stringField(vehicle, 'modification_name'),
  ].filter(Boolean).join(' · ') || 'Комплектация не указана'
}
const vehiclePrice = (vehicle: Record<string, unknown>) => (
  numberLikeField(vehicle, 'price')
  ?? numberLikeField(vehicle, 'unit_price')
  ?? numberLikeField(vehicle, 'vehicle_price')
)
const vehicleTotal = (vehicle: Record<string, unknown>) => {
  const total = numberLikeField(vehicle, 'total_price') ?? numberLikeField(vehicle, 'total_amount')
  if (total !== null) return total
  const price = toNumber(vehiclePrice(vehicle))
  const quantity = toNumber(numberLikeField(vehicle, 'quantity')) || 1
  return price === null ? null : price * quantity
}

const formatPriceLike = (value: number | string | null) => {
  if (typeof value === 'string') return formatCommerceMoney(value)
  const numeric = toNumber(value)
  return numeric === null ? '—' : formatPrice(numeric)
}

const textValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

const vehicleLeasingPurpose = (vehicle: Record<string, unknown>): string => {
  const purposeName = stringField(vehicle, 'leasing_purpose_name') || stringField(vehicle, 'purpose_name')
  if (purposeName) return purposeName

  const vehiclePurpose = formatLeasingPurpose({
    leasing_purpose: stringField(vehicle, 'leasing_purpose'),
    leasing_purpose_comment: stringField(vehicle, 'leasing_purpose_comment'),
  }, '')
  if (vehiclePurpose) return vehiclePurpose

  return formatLeasingPurpose({
    leasing_purpose: stringField(props.application, 'leasing_purpose'),
    leasing_purpose_comment: stringField(props.application, 'leasing_purpose_comment'),
  }, '—')
}

const vehicleRegionValues = (vehicle: Record<string, unknown>): unknown => (
  field(vehicle, 'leasing_regions')
  || field(vehicle, 'regions')
  || field(vehicle, 'region_names')
  || field(vehicle, 'leasing_region_names')
  || field(props.application, 'leasing_regions')
  || field(props.application, 'regions')
  || field(props.application, 'region_names')
  || field(props.application, 'leasing_region_names')
)

const questionnaire = computed(() => {
  const value = field(props.application, 'questionnaire')
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})

const company = computed(() => {
  const value = field(props.application, 'company')
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})
const companyName = computed(() => props.item.company_name || stringField(company.value, 'name') || stringField(props.application, 'company_name') || '—')
const companyInn = computed(() => props.item.company_inn || stringField(company.value, 'inn') || stringField(props.application, 'inn') || stringField(questionnaire.value, 'inn') || '—')
const companyAddress = computed(() => (
  stringField(company.value, 'legal_address')
  || stringField(questionnaire.value, 'legal_address')
  || stringField(props.application, 'legal_address')
  || '—'
))

const statusText = (status: string) => {
  const labels: Record<string, string> = {
    submitted: 'Отправлена',
    pending_distribution: 'На распределении',
    under_review: 'На рассмотрении',
    under_review_with_docs: 'На рассмотрении с доп. документами',
    approved_scoring: 'Предварительное КП',
    approved_scoring_another_cond: 'Предварительное КП на других условиях',
    approved_final: 'Итоговое КП',
    approved_final_another_cond: 'Итоговое КП на других условиях',
    selected_lc: 'Выбрана ЛК',
    deal: 'Сделка заключена',
    rejected_prescoring: 'Отклонена на предварительном рассмотрении',
    rejected_approved: 'Отклонена после предварительного КП',
    rejected_final: 'Отклонена после итогового КП',
    closed: 'Закрыта',
    documents_required: 'Запрос дополнительных документов',
  }
  return labels[status] || status
}

const statusClass = (status: string) => {
  if (status.startsWith('approved') || status === 'selected_lc' || status === 'deal') {
    return 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]'
  }
  if (status.startsWith('rejected')) return 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]'
  if (status === 'documents_required' || status === 'under_review_with_docs') {
    return 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)]'
  }
  if (status === 'closed') return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]'
  return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]'
}

const loadResponses = async () => {
  if (!props.show || !props.item.application_id) return
  responsesLoading.value = true
  responsesError.value = ''
  try {
    const response = await notificationRequest<ClientLeasingResponsesResponse>(
      `/api/v1/applications/${props.item.application_id}/leasing-responses`,
      { baseURL: config.public.apiBase, credentials: 'include' },
    )
    clientResponses.value = response
  } catch {
    clientResponses.value = null
    responsesError.value = 'Не удалось загрузить условия КП.'
  } finally {
    responsesLoading.value = false
  }
}

watch(
  () => [props.show, props.item.application_id, props.item.leasing_company_id],
  () => {
    if (props.show) void loadResponses()
  },
  { immediate: true },
)
</script>
