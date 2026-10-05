<template>
  <div data-storefront-block="client.cabinet" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
    <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
      <h3 class="flex items-center gap-2 text-lg font-medium text-[color:var(--storefront-title,#111827)]">
        <DocumentTextIcon class="h-5 w-5 text-[color:var(--storefront-icon,#6b7280)]" />
        Согласие на обработку персональных данных
      </h3>
    </div>

    <div class="p-6">
      <div v-if="isLoading" class="animate-pulse space-y-3">
        <div class="h-4 w-1/3 rounded bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]"></div>
        <div class="h-4 w-1/2 rounded bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]"></div>
      </div>

      <div v-else-if="signature" class="space-y-4">
        <div class="flex items-center gap-3">
          <span class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Статус:</span>
          <SignatureStatusBadge :status="signature.status" />
        </div>

        <div v-if="signature.signed_at" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Дата подписания: {{ formatDate(signature.signed_at) }}
        </div>

        <div
          v-if="signature.sopd_revoke_summary?.has_partial_revoke"
          class="inline-flex w-fit items-center rounded-full bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2.5 py-1 text-xs font-medium text-[color:var(--storefront-warning-text,#92400e)]"
        >
          Частично отозвано
        </div>

        <template v-if="signature.status === 'revoked'">
          <div v-if="signature.revoke_requested_at" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Дата подачи заявки: {{ formatDate(signature.revoke_requested_at) }}
          </div>
          <div v-if="signature.revoked_at" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Дата прекращения действия: {{ formatDate(signature.revoked_at) }}
          </div>

          <div class="rounded-lg border border-[color:var(--storefront-error-border,#fee2e2)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4">
            <p class="text-sm text-[color:var(--storefront-error-text,#991b1b)]">
              Ваше согласие на обработку персональных данных отозвано, т.к. вы
              подали заявку на отзыв
              {{ formatDate(signature.revoke_requested_at) }} г.
            </p>
          </div>
        </template>

        <div
          v-if="signature.sopd_operators?.length"
          class="rounded-lg border border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
        >
          <div class="flex flex-col gap-2 border-b border-[color:var(--storefront-border,#f3f4f6)] px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <span class="text-xs font-medium uppercase text-[color:var(--storefront-text-muted,#6b7280)]">
              Компании по СОПД
            </span>
            <button
              v-if="selectedRevokeCount > 0"
              type="button"
              class="storefront-action-destructive inline-flex items-center gap-2 self-start rounded-lg bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] px-4 py-2 text-sm font-medium text-[color:var(--storefront-destructive-foreground,#ffffff)] transition-colors hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
              :disabled="isRevoking"
              @click="openConfirmModal({ selectedIds: selectedRevokeIds })"
            >
              <NoSymbolIcon class="h-4 w-4" />
              Отозвать выбранное ({{ selectedRevokeCount }})
            </button>
          </div>
          <div class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
            <div
              v-for="operator in signature.sopd_operators"
              :key="`${operator.operator_type}-${operator.id}`"
              class="flex flex-col gap-2 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div class="flex min-w-0 items-start gap-2">
                <input
                  v-if="canRevokeOperator(operator)"
                  type="checkbox"
                  class="storefront-control mt-1 h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-error-text,#dc2626)] focus:ring-[color:var(--storefront-focus,#ef4444)]"
                  :checked="isOperatorSelectedForRevoke(operator.id)"
                  :disabled="isRevoking"
                  @change="onRevokeOperatorCheck(operator, $event)"
                >
                <div class="min-w-0">
                  <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ operator.name || 'Оператор' }}</div>
                  <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
                    {{ operator.operator_type === 'leasing_company' ? 'ЛК' : 'Подрядчик' }}
                    <span v-if="operator.inn"> · ИНН: {{ operator.inn }}</span>
                    <span v-if="operator.revoked_at"> · Отозвано {{ formatDate(operator.revoked_at) }}</span>
                  </div>
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="operator.status === 'revoked' ? 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)]' : 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]'"
                >
                  {{ operator.status === 'revoked' ? 'Отозвано' : 'Активно' }}
                </span>
                <a
                  v-if="operator.revoke_document_download_url"
                  :href="operatorDownloadHref(operator.revoke_document_download_url)"
                  target="_blank"
                  rel="noopener"
                  class="text-xs font-medium text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1e40af)]"
                >
                  Отзыв PDF
                </a>
              </div>
            </div>
          </div>
        </div>

        <div v-if="canRevoke" class="flex flex-wrap gap-2">
          <button
            type="button"
            class="storefront-action-destructive inline-flex items-center gap-2 rounded-lg bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] px-4 py-2 text-sm font-medium text-[color:var(--storefront-destructive-foreground,#ffffff)] transition-colors hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="isRevoking"
            @click="openConfirmModal({ selectAll: true })"
          >
            <NoSymbolIcon class="h-4 w-4" />
            Отозвать всё
          </button>
        </div>
      </div>

      <div v-else class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
        У вас пока нет подписанного согласия на обработку персональных данных.
      </div>
    </div>

    <Modal
      :show="showConfirmModal"
      :title="revokeConfirmTitle"
      :subtitle="revokeConfirmSubtitle"
      size="md"
      :show-footer="true"
      cancel-text="Отмена"
      :confirm-text="revokeConfirmText"
      :confirm-disabled="isRevoking || selectedLeasingCompanyIds.length === 0"
      @close="showConfirmModal = false"
      @cancel="showConfirmModal = false"
      @confirm="onConfirmRevoke"
    >
      <div class="space-y-3">
        <div v-if="selectedLeasingCompanies.length" class="space-y-2">
          <div
            v-for="company in selectedLeasingCompanies"
            :key="company.id"
            class="rounded-md border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm text-[color:var(--storefront-text,#1f2937)]"
          >
            <span class="font-medium">{{ company.name || 'Лизинговая компания' }}</span>
            <span v-if="company.inn" class="block text-xs text-[color:var(--storefront-text-muted,#6b7280)]">ИНН: {{ company.inn }}</span>
          </div>
        </div>
        <p v-else class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
          Для этого СОПД не найдено активных лизинговых компаний для отзыва.
        </p>
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          После подтверждения мы отправим SMS-код и сформируем печатную форму отзыва.
        </p>
        <p v-if="error" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>
      </div>
    </Modal>

    <Modal
      :show="showCodeModal"
      title="Подтверждение отзыва"
      :subtitle="`Введите 4-значный код, отправленный на ${phoneMasked}`"
      size="sm"
      :closable="true"
      :close-on-overlay="false"
      :show-footer="true"
      cancel-text="Отмена"
      confirm-text="Подтвердить"
      :confirm-disabled="!isCodeComplete || isVerifying"
      @close="showCodeModal = false"
      @cancel="showCodeModal = false"
      @confirm="onVerifyCode"
    >
      <div class="space-y-4 py-2">
        <div class="flex justify-center gap-3">
          <input
            v-for="(_, index) in codeDigits"
            :key="index"
            :ref="(el) => setCodeInputRef(el, index)"
            v-model="codeDigits[index]"
            type="text"
            inputmode="numeric"
            maxlength="1"
            class="storefront-control h-12 w-12 rounded-lg border-2 border-[color:var(--storefront-border,#d1d5db)] text-center text-xl font-semibold transition-all focus:border-[color:var(--storefront-border,#3b82f6)] focus:ring-2 focus:ring-[color:var(--storefront-focus,#bfdbfe)] sm:h-14 sm:w-14 sm:text-2xl"
            @input="onCodeInput(index)"
            @keydown.backspace="onCodeBackspace(index)"
            @keydown.enter.prevent="onVerifyCode"
            @paste="onCodePaste"
          >
        </div>

        <p v-if="error" class="text-center text-sm text-[color:var(--storefront-error-text,#dc2626)]">
          {{ error }}
        </p>

        <div class="text-center">
          <button
            type="button"
            :disabled="!canResend"
            class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] transition-colors hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:cursor-not-allowed disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
            @click="onResendCode"
          >
            <template v-if="canResend">
              Отправить код повторно
            </template>
            <template v-else>
              Отправить повторно через {{ resendDelay }} сек.
            </template>
          </button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { DocumentTextIcon, NoSymbolIcon } from '@heroicons/vue/24/outline'
import SignatureStatusBadge from '~/features/client/components/SignatureStatusBadge.vue'
import { useSignatureRevoke } from '~/features/signatures/composables/useSignatureRevoke'
import type { ComponentPublicInstance } from 'vue'
import type { SignatureRequest } from '~/types/signature'

const props = defineProps<{
  signature: SignatureRequest | null
  isLoading?: boolean
}>()

const config = useRuntimeConfig()

const emit = defineEmits<{
  (event: 'revoked'): void
}>()

const signatureId = computed(() => props.signature?.id || null)
const {
  isLoading: isRevoking,
  isVerifying,
  error,
  phoneMasked,
  resendDelay,
  canResend,
  initiateRevoke,
  verifyCode,
  resendCode,
  clearError,
} = useSignatureRevoke(signatureId)

const showConfirmModal = ref(false)
const showCodeModal = ref(false)
const codeDigits = ref(['', '', '', ''])
const codeInputs = ref<HTMLInputElement[]>([])
const selectedOperatorIds = ref<string[]>([])
const selectedLeasingCompanyIds = ref<string[]>([])
const selectedLeasingCompanies = ref<RevokeCompanyDraft[]>([])
const revokeAllMode = ref(false)

const canRevoke = computed(() => {
  return ['signed_electronic', 'signed_physical'].includes(
    props.signature?.status || '',
  ) && Boolean(props.signature?.sopd_revoke_summary?.active_leasing_company_ids?.length)
})

interface RevokeCompanyDraft {
  id: string
  name?: string | null
  inn?: string | null
}

type SopdOperator = NonNullable<SignatureRequest['sopd_operators']>[number]

const canRevokeOperator = (operator: SopdOperator): boolean => {
  return canRevoke.value
    && operator.operator_type === 'leasing_company'
    && operator.status === 'active'
    && Boolean(operator.id)
}

const activeRevokeOperatorIds = computed(() => {
  return (props.signature?.sopd_operators || [])
    .filter(operator => canRevokeOperator(operator))
    .map(operator => operator.id)
})

const normalizeRevokeSelection = (ids: string[]): string[] => {
  const activeIds = new Set(activeRevokeOperatorIds.value)
  return Array.from(new Set(ids)).filter(id => activeIds.has(id))
}

const selectedRevokeIds = computed(() => {
  return normalizeRevokeSelection(selectedOperatorIds.value)
})

const selectedRevokeCount = computed(() => selectedRevokeIds.value.length)

const setSelectedRevokeIds = (ids: string[]) => {
  selectedOperatorIds.value = normalizeRevokeSelection(ids)
}

const isOperatorSelectedForRevoke = (operatorId: string): boolean => {
  return selectedRevokeIds.value.includes(operatorId)
}

const onRevokeOperatorCheck = (
  operator: SopdOperator,
  event: Event,
) => {
  if (!canRevokeOperator(operator)) return

  const checked = (event.target as HTMLInputElement | null)?.checked ?? false
  const currentIds = selectedRevokeIds.value
  const nextIds = checked
    ? [...currentIds, operator.id]
    : currentIds.filter(id => id !== operator.id)

  setSelectedRevokeIds(nextIds)
}

const selectedRevokeCompaniesByIds = (ids: string[]): RevokeCompanyDraft[] => {
  const activeOperators = (props.signature?.sopd_operators || [])
    .filter((operator): operator is SopdOperator => (
      operator.operator_type === 'leasing_company'
      && operator.status === 'active'
      && ids.includes(operator.id)
    ))

  return activeOperators.length
    ? activeOperators
    : ids.map(id => ({ id }))
}

const isCodeComplete = computed(() => {
  return codeDigits.value.every((digit) => /^\d$/.test(digit))
})

const revokeConfirmTitle = computed(() => {
  if (revokeAllMode.value) return 'Отозвать СОПД полностью'
  return selectedLeasingCompanyIds.value.length > 1
    ? 'Отозвать СОПД у выбранных компаний'
    : 'Отозвать СОПД у компании'
})

const revokeConfirmSubtitle = computed(() => {
  if (revokeAllMode.value) {
    return 'Будет отозвана обработка персональных данных у всех активных лизинговых компаний этого СОПД.'
  }

  return selectedLeasingCompanyIds.value.length > 1
    ? 'Будет отозвана обработка персональных данных у выбранных лизинговых компаний.'
    : 'Будет отозвана обработка персональных данных у выбранной лизинговой компании.'
})

const revokeConfirmText = computed(() => {
  if (revokeAllMode.value) return 'Отозвать всё'
  return selectedLeasingCompanyIds.value.length > 1
    ? 'Отозвать выбранное'
    : 'Отозвать компанию'
})

const setCodeInputRef = (
  el: Element | ComponentPublicInstance | null,
  index: number,
) => {
  if (el instanceof HTMLInputElement) {
    codeInputs.value[index] = el
  }
}

const onConfirmRevoke = async () => {
  clearError()
  const leasingCompanyIds = [...selectedLeasingCompanyIds.value]
  try {
    await initiateRevoke(leasingCompanyIds)
    showConfirmModal.value = false
    resetCodeInputs()
    showCodeModal.value = true
    await nextTick()
    codeInputs.value[0]?.focus()
  } catch {
    // User-facing error is owned by the composable.
  }
}

watch(showConfirmModal, (isShown) => {
  if (isShown) return
  revokeAllMode.value = false
  selectedLeasingCompanyIds.value = []
  selectedLeasingCompanies.value = []
})

watch(() => props.signature?.id, () => {
  selectedOperatorIds.value = []
})

const openConfirmModal = (
  options: { selectAll?: boolean; selectedIds?: string[] } = {},
) => {
  selectedLeasingCompanyIds.value = []
  selectedLeasingCompanies.value = []
  revokeAllMode.value = Boolean(options.selectAll)
  clearError()

  if (options.selectedIds?.length) {
    const selectedIds = normalizeRevokeSelection(options.selectedIds)
    selectedLeasingCompanyIds.value = selectedIds
    selectedLeasingCompanies.value = selectedRevokeCompaniesByIds(selectedIds)
  } else if (options.selectAll && props.signature) {
    const activeIds = props.signature.sopd_revoke_summary?.active_leasing_company_ids || []
    selectedLeasingCompanyIds.value = activeIds
    selectedLeasingCompanies.value = selectedRevokeCompaniesByIds(activeIds)
  }

  showConfirmModal.value = true
}

const onCodeInput = async (index: number) => {
  const digit = codeDigits.value[index]
  if (!/^\d?$/.test(digit)) {
    codeDigits.value[index] = ''
    return
  }
  clearError()
  if (digit && index < 3) {
    await nextTick()
    codeInputs.value[index + 1]?.focus()
  }
  if (isCodeComplete.value) {
    await nextTick()
    await onVerifyCode()
  }
}

const onCodeBackspace = async (index: number) => {
  if (!codeDigits.value[index] && index > 0) {
    codeDigits.value[index - 1] = ''
    await nextTick()
    codeInputs.value[index - 1]?.focus()
  }
}

const onCodePaste = async (event: ClipboardEvent) => {
  event.preventDefault()
  const digits = (event.clipboardData?.getData('text') || '')
    .replace(/\D/g, '')
    .slice(0, 4)

  digits.split('').forEach((digit, index) => {
    codeDigits.value[index] = digit
  })

  await nextTick()
  codeInputs.value[Math.min(digits.length, 3)]?.focus()
  if (digits.length === 4) {
    await onVerifyCode()
  }
}

const onVerifyCode = async () => {
  if (!isCodeComplete.value || isVerifying.value) return
  try {
    await verifyCode(codeDigits.value.join(''))
    showCodeModal.value = false
    selectedOperatorIds.value = []
    emit('revoked')
  } catch {
    resetCodeInputs()
    await nextTick()
    codeInputs.value[0]?.focus()
  }
}

const onResendCode = async () => {
  if (!canResend.value) return
  clearError()
  try {
    await resendCode()
    resetCodeInputs()
    await nextTick()
    codeInputs.value[0]?.focus()
  } catch {
    // User-facing error is owned by the composable.
  }
}

const resetCodeInputs = () => {
  codeDigits.value = ['', '', '', '']
}

const formatDate = (isoDate?: string | null): string => {
  if (!isoDate) return '-'
  return new Date(isoDate).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

const operatorDownloadHref = (url: string) => {
  if (/^https?:\/\//.test(url)) return url
  return `${config.public.apiBase.replace(/\/$/, '')}${url}`
}
</script>
