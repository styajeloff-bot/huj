<template>
  <div data-storefront-block="client.application"
    class="fixed inset-0 z-[70] flex items-center justify-center bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] p-6"
    role="presentation"
    @click.self="close"
    @keydown.esc="close"
  >
    <section
      ref="dialogRef"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dealer-price-title"
      aria-describedby="dealer-price-description"
      tabindex="-1"
      class="w-full max-w-lg rounded-xl bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 shadow-xl focus:outline-none"
      @keydown.tab="trapFocus"
    >
      <div class="flex items-start justify-between gap-6">
        <div>
          <h2 id="dealer-price-title" class="text-xl font-semibold text-[color:var(--storefront-title,#030712)]">
            {{ item.price_status === 'set' ? 'Изменить стоимость' : 'Выставить стоимость' }}
          </h2>
          <p id="dealer-price-description" class="mt-2 text-sm leading-relaxed text-[color:var(--storefront-text-muted,#4b5563)]">
            {{ item.title }} · {{ item.quantity }} шт. Цена обновит общую сумму заявки.
          </p>
        </div>
        <button
          type="button"
          class="storefront-action-ghost min-h-11 rounded-lg px-3 text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#4b5563)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
          :disabled="submitting"
          @click="close"
        >
          Закрыть
        </button>
      </div>

      <p class="mt-5 rounded-lg bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-text,#172554)]">
        {{ item.price_status === 'set' ? 'Текущая согласованная цена' : 'Предварительная цена' }}:
        <strong class="tabular-nums">{{ item.unit_price === null ? 'Не указана' : formatCommerceMoney(item.unit_price, item.currency_code) }}</strong>
      </p>

      <form class="mt-5" @submit.prevent="submit">
        <label for="dealer-agreed-price" class="block text-sm font-semibold text-[color:var(--storefront-label,#1f2937)]">
          Точная стоимость за единицу, ₽
        </label>
        <input
          id="dealer-agreed-price"
          ref="inputRef"
          v-model.trim="agreedPrice"
          type="number"
          min="0.01"
          step="0.01"
          inputmode="decimal"
          required
          aria-required="true"
          :aria-invalid="Boolean(errorMessage)"
          :aria-describedby="errorMessage ? 'dealer-price-error' : 'dealer-price-help'"
          class="storefront-control mt-2 w-full rounded-lg border border-[color:var(--storefront-border,#d1d5db)] px-3 py-2.5 text-base tabular-nums text-[color:var(--storefront-text,#030712)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
          @input="errorMessage = ''"
        >
        <p id="dealer-price-help" class="mt-2 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Значение должно быть больше нуля.</p>
        <p v-if="errorMessage" id="dealer-price-error" class="mt-2 text-sm font-medium text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">
          {{ errorMessage }}
        </p>

        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            class="storefront-action-ghost min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-4 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="submitting"
            @click="close"
          >
            Отмена
          </button>
          <button
            type="submit"
            class="storefront-action-primary inline-flex min-h-11 min-w-44 items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,29_78_216)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,30_64_175)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
            :disabled="submitting"
          >
            {{ submitting ? 'Сохраняем…' : 'Сохранить стоимость' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useNotificationCompanyContext } from '~/features/notifications'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import { formatCommerceMoney } from '~/features/commerce/money'
import type { UUID } from '~/types/ids'
import {
  createApplicationsApi,
  parseApplicationsApiError,
} from '../api/applicationsApi'

const props = defineProps<{
  applicationId: UUID
  item: CommerceApplicationItem
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const applicationsApi = createApplicationsApi(useRuntimeConfig(), useNotificationCompanyContext())
const toast = useToast()
const dialogRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const agreedPrice = ref(props.item.unit_price ?? '')
const submitting = ref(false)
const errorMessage = ref('')
let returnFocusTarget: HTMLElement | null = null

const focusableElements = (): HTMLElement[] => {
  if (!dialogRef.value) return []
  return [...dialogRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
  )].filter(element => element.getAttribute('aria-hidden') !== 'true')
}

const trapFocus = (event: KeyboardEvent): void => {
  const elements = focusableElements()
  if (!elements.length) {
    event.preventDefault()
    dialogRef.value?.focus()
    return
  }
  const first = elements[0]!
  const last = elements[elements.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

const close = (): void => {
  if (!submitting.value) emit('close')
}

const positivePrice = (): string | null => {
  const value = Number(agreedPrice.value)
  return Number.isFinite(value) && value > 0 ? value.toFixed(2) : null
}

const submit = async (): Promise<void> => {
  const normalized = positivePrice()
  if (!normalized) {
    errorMessage.value = 'Укажите стоимость больше нуля.'
    inputRef.value?.focus()
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    await applicationsApi.setSpecialEquipmentPrice(
      props.applicationId,
      props.item.id,
      normalized,
    )
    toast.success('Стоимость позиции обновлена')
    emit('saved')
  } catch (error: unknown) {
    const parsed = parseApplicationsApiError(error, 'Не удалось сохранить стоимость позиции')
    errorMessage.value = parsed.message
    toast.error(parsed.message)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  returnFocusTarget = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null
  await nextTick()
  dialogRef.value?.focus()
  inputRef.value?.select()
})

onBeforeUnmount(() => {
  returnFocusTarget?.focus()
})
</script>
