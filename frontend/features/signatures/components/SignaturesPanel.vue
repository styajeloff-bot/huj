<template>
  <div data-storefront-block="client.cabinet" class="space-y-4">
    <!-- Header -->
    <div>
      <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Документы на подпись</h2>
      <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">Согласия и заявления, направленные вам на подпись.</p>
    </div>

    <!-- Sub-tabs -->
    <div class="border-b border-[color:var(--storefront-border,#e5e7eb)]">
      <nav class="flex gap-4 sm:gap-6 overflow-x-auto">
        <button
          v-for="f in filters"
          :key="f.id"
          type="button"
          class="storefront-action-ghost py-2 px-1 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
          :class="filter === f.id
            ? 'border-[color:var(--storefront-secondary-border,#2563eb)] text-[color:var(--storefront-secondary-foreground,#1d4ed8)]'
            : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'"
          @click="filter = f.id"
        >
          {{ f.label }}
          <span v-if="counts[f.id] !== undefined" class="ml-1 inline-flex items-center justify-center px-1.5 py-0.5 rounded-full bg-[color:rgb(var(--storefront-secondary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#374151)] text-xs">
            {{ counts[f.id] }}
          </span>
        </button>
      </nav>
    </div>

    <!-- Loading / empty states -->
    <div v-if="loading" class="py-10 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
      <span class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></span>
      <p class="mt-2">Загрузка…</p>
    </div>
    <div v-else-if="filteredItems.length === 0" class="py-10 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg border border-dashed border-[color:var(--storefront-border,#d1d5db)]">
      В этом разделе пока ничего нет.
    </div>

    <!-- List -->
    <ul v-else class="space-y-2">
      <li
        v-for="item in filteredItems"
        :key="item.id"
        class="p-3 sm:p-4 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg space-y-3"
      >
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)] truncate">{{ docTypeLabel(item.document_type) }}</h3>
              <StatusBadge :status="item.status" />
              <span
                v-if="hasPartialRevoke(item)"
                class="inline-flex items-center rounded-full border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-xs font-medium text-[color:var(--storefront-warning-text,#92400e)]"
              >
                Частично отозван
              </span>
            </div>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-0.5">
              <span>Подписант: {{ item.subject_snapshot.full_name || '—' }}</span>
              <span v-if="item.subject_snapshot.company_name"> · {{ item.subject_snapshot.company_name }}</span>
            </p>
            <p class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)] mt-0.5">
              <template v-if="item.status === 'revoked' && item.revoked_at">Отозвано {{ formatDate(item.revoked_at) }}</template>
              <template v-else-if="item.signed_at">Подписано {{ formatDate(item.signed_at) }} · {{ item.signature_method === 'electronic' ? 'электронно' : 'бумажно' }}</template>
              <template v-else-if="item.cancelled_at">Отменено {{ formatDate(item.cancelled_at) }}</template>
              <template v-else-if="item.sent_at">Получено {{ formatDate(item.sent_at) }}</template>
              <template v-else>Создано {{ formatDate(item.created_at) }}</template>
            </p>
          </div>

          <div class="flex gap-2 shrink-0 flex-wrap">
            <button
              v-if="item.status === 'pending'"
              type="button"
              class="storefront-action-ghost px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#1d4ed8)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-primary-border,#bfdbfe)] rounded-md hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))]"
              @click="openSignModal(item)"
            >
              Открыть и подписать
            </button>
            <a
              v-else-if="canDownloadDocument(item)"
              :href="downloadHref(item)"
              target="_blank"
              rel="noopener"
              class="px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-link,#374151)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#d1d5db)] rounded-md hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
            >
              {{ downloadLabel(item) }}
            </a>
            <button
              v-if="canFullRevoke(item)"
              type="button"
              class="storefront-action-destructive px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-destructive-foreground,#ffffff)] bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-destructive-border,#dc2626)] rounded-md hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="isRevoking && revokeTarget?.id === item.id"
              @click="openRevokeConfirm(item, { selectAll: true })"
            >
              Отозвать всё
            </button>
          </div>
        </div>

        <div
          v-if="item.sopd_operators?.length"
          class="rounded-md border border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
        >
          <div class="flex flex-col gap-2 border-b border-[color:var(--storefront-border,#f3f4f6)] px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <span class="text-xs font-medium uppercase text-[color:var(--storefront-text-muted,#6b7280)]">
              Компании по СОПД
            </span>
            <button
              v-if="selectedRevokeCount(item) > 0"
              type="button"
              class="storefront-action-destructive self-start rounded-md border border-[color:var(--storefront-destructive-border,#dc2626)] bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-destructive-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
              :disabled="isRevoking && revokeTarget?.id === item.id"
              @click="openRevokeConfirm(item, { selectedIds: selectedRevokeIds(item) })"
            >
              Отозвать выбранное ({{ selectedRevokeCount(item) }})
            </button>
          </div>
          <div class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
            <div
              v-for="operator in item.sopd_operators"
              :key="`${operator.operator_type}-${operator.id}`"
              class="flex flex-col gap-2 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div class="flex min-w-0 items-start gap-2">
                <input
                  v-if="canRevokeOperator(item, operator)"
                  type="checkbox"
                  class="storefront-control mt-1 h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-error-text,#dc2626)] focus:ring-[color:var(--storefront-focus,#ef4444)]"
                  :checked="isOperatorSelectedForRevoke(item, operator.id)"
                  :disabled="isRevoking && revokeTarget?.id === item.id"
                  @change="onRevokeOperatorCheck(item, operator, $event)"
                >
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ operator.name || 'Оператор' }}</span>
                    <span class="rounded bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-1.5 py-0.5 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ operatorTypeLabel(operator.operator_type) }}</span>
                  </div>
                  <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
                    <span v-if="operator.inn">ИНН: {{ operator.inn }}</span>
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
      </li>
    </ul>

    <!-- Sign modal -->
    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] p-3 sm:p-6">
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] w-full max-w-3xl  rounded-lg shadow-xl flex flex-col overflow-hidden" style="height: 60vh">
        <!-- Header -->
        <div class="p-4 border-b border-[color:var(--storefront-border,#e5e7eb)] flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">{{ docTypeLabel(active.document_type) }}</h3>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-0.5 truncate">{{ active.subject_snapshot.full_name || '' }}</p>
          </div>
          <button type="button" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] shrink-0" @click="closeSignModal">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <!-- PDF preview -->
        <div class="flex-1 min-h-0 bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]">
          <div v-if="previewLoading" class="h-full flex items-center justify-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            <span class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-[color:var(--storefront-border,#2563eb)] mr-2"></span>
            {{ previewPending ? 'Документ готовится, подождите…' : 'Загрузка документа…' }}
          </div>
          <div v-else-if="previewError" class="h-full flex flex-col items-center justify-center text-sm text-[color:var(--storefront-error-text,#dc2626)] px-4 text-center">
            <p>{{ previewError }}</p>
            <button type="button" class="storefront-action-ghost mt-3 px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#1d4ed8)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-primary-border,#bfdbfe)] rounded-md hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))]" @click="loadPreview(active.id)">
              Повторить
            </button>
          </div>
          <object
            v-else-if="previewUrl"
            :data="previewUrl"
            type="application/pdf"
            class="w-full h-full"
            aria-label="Предпросмотр документа"
          >
            <p class="p-4 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
              Браузер не смог открыть PDF.
              <a :href="previewUrl" target="_blank" rel="noopener" class="text-[color:var(--storefront-link,#2563eb)] underline">Открыть в новой вкладке</a>
            </p>
          </object>
        </div>

        <!-- Actions -->
        <div class="p-4 border-t border-[color:var(--storefront-border,#e5e7eb)] space-y-3">
          <label class="flex items-start gap-2 text-sm text-[color:var(--storefront-label,#374151)]">
            <input type="checkbox" v-model="consentAccepted" class="storefront-control mt-1" />
            <span>
              Я ознакомлен(а) с содержанием документа и согласен(а) подписать его
              простой электронной подписью. Достоверность моих ФИО, паспортных
              данных и номера телефона подтверждаю.
            </span>
          </label>
          <div v-if="actionError" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">{{ actionError }}</div>
          <div class="flex flex-col sm:flex-row gap-2 sm:justify-end">
            <label class="inline-flex items-center justify-center gap-2 cursor-pointer px-3 py-2 text-sm font-medium text-[color:var(--storefront-label,#374151)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#d1d5db)] rounded-md hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              <svg class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
              <span>{{ uploadingPhysical ? 'Загрузка…' : 'Загрузить скан подписанного' }}</span>
              <input type="file" accept="application/pdf,image/*" class="storefront-control hidden" :disabled="uploadingPhysical" @change="onUploadPhysical" />
            </label>
            <button
              type="button"
              :disabled="!consentAccepted || signingElectronic"
              class="storefront-action-primary inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-md hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:opacity-50"
              @click="onSignElectronic"
            >
              <svg v-if="signingElectronic" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" /></svg>
              Подписать электронно
            </button>
          </div>
        </div>
      </div>
    </div>

    <Modal
      :show="showRevokeConfirmModal"
      :title="revokeConfirmTitle"
      :subtitle="revokeConfirmSubtitle"
      size="md"
      :show-footer="true"
      cancel-text="Отмена"
      :confirm-text="revokeConfirmText"
      :confirm-disabled="isRevoking || selectedRevokeLeasingCompanyIds.length === 0"
      @close="closeRevokeConfirm"
      @cancel="closeRevokeConfirm"
      @confirm="onConfirmRevoke"
    >
      <div class="space-y-3">
        <div v-if="selectedRevokeLeasingCompanies.length" class="space-y-2">
          <div
            v-for="company in selectedRevokeLeasingCompanies"
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
        <p v-if="revokeError" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ revokeError }}</p>
      </div>
    </Modal>

    <Modal
      :show="showRevokeCodeModal"
      title="Подтверждение отзыва"
      :subtitle="`Введите 4-значный код, отправленный на ${phoneMasked}`"
      size="sm"
      :closable="true"
      :close-on-overlay="false"
      :show-footer="true"
      cancel-text="Отмена"
      confirm-text="Подтвердить"
      :confirm-disabled="!isRevokeCodeComplete || isVerifying"
      @close="showRevokeCodeModal = false"
      @cancel="showRevokeCodeModal = false"
      @confirm="onVerifyRevokeCode"
    >
      <div class="space-y-4 py-2">
        <div class="flex justify-center gap-3">
          <input
            v-for="(_, index) in revokeCodeDigits"
            :key="index"
            :ref="(el) => setRevokeCodeInputRef(el, index)"
            v-model="revokeCodeDigits[index]"
            type="text"
            inputmode="numeric"
            maxlength="1"
            class="storefront-control h-12 w-12 rounded-lg border-2 border-[color:var(--storefront-border,#d1d5db)] text-center text-xl font-semibold transition-all focus:border-[color:var(--storefront-border,#3b82f6)] focus:ring-2 focus:ring-[color:var(--storefront-focus,#bfdbfe)] sm:h-14 sm:w-14 sm:text-2xl"
            @input="onRevokeCodeInput(index)"
            @keydown.backspace="onRevokeCodeBackspace(index)"
            @keydown.enter.prevent="onVerifyRevokeCode"
            @paste="onRevokeCodePaste"
          >
        </div>

        <p v-if="revokeError" class="text-center text-sm text-[color:var(--storefront-error-text,#dc2626)]">
          {{ revokeError }}
        </p>

        <div class="text-center">
          <button
            type="button"
            :disabled="!canResend"
            class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] transition-colors hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:cursor-not-allowed disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
            @click="onResendRevokeCode"
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

    <MobileIdVerificationModal
      :show="showIdentityVerificationModal"
      title="Перед подписанием нужна верификация"
      intro-text="Мы подтвердим ваши данные через Mobile ID. Это займёт пару минут и требуется для подписания СОПД."
      primary-text="Перейти к верификации"
      :phone="currentUserPhone"
      :birth-date="currentUserBirthDate"
      @close="showIdentityVerificationModal = false"
      @verified="onIdentityVerified"
    />
  </div>
</template>

<script setup lang="ts">
import { defineComponent, h } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import type { UUID } from '~/types/ids'
import { useAuthStore } from '~/features/auth/store/auth'
import { useSignatureRevoke } from '~/features/signatures/composables/useSignatureRevoke'
import MobileIdVerificationModal from '~/features/identity-verification/components/MobileIdVerificationModal.vue'
import { useIdentityVerification } from '~/features/identity-verification/composables/useIdentityVerification'

type Status = 'pending' | 'signed_electronic' | 'signed_physical' | 'cancelled' | 'revoked'
type FilterId = 'pending' | 'signed' | 'revoked' | 'cancelled' | 'all'

interface SignatureItem {
  id: UUID
  user_id: UUID
  application_id: UUID | null
  document_type: 'sopd' | string
  status: Status
  signature_method: 'electronic' | 'physical' | null
  subject_snapshot: {
    full_name?: string | null
    inn?: string | null
    passport?: string | null
    company_name?: string | null
    company_inn?: string | null
  }
  signed_pdf_s3_key: string | null
  sent_at: string | null
  signed_at: string | null
  revoked_at?: string | null
  revoke_requested_at?: string | null
  cancelled_at: string | null
  created_at: string
  sopd_operators?: SopdOperatorStatus[]
  sopd_revoke_summary?: SopdRevokeSummary | null
}

interface SopdOperatorStatus {
  operator_type: 'leasing_company' | 'contractor'
  id: UUID
  name?: string | null
  inn?: string | null
  status: 'active' | 'revoked'
  revoked_at?: string | null
  revoke_document_download_url?: string | null
}

interface RevokeCompanyDraft {
  id: UUID
  name?: string | null
  inn?: string | null
}

interface SopdRevokeSummary {
  has_partial_revoke: boolean
  active_leasing_company_ids: UUID[]
}

interface CurrentUserProfileResponse {
  role_specific?: {
    birth_date?: string | null
  } | null
}

const config = useRuntimeConfig()
const toast = useToast()
const authStore = useAuthStore()

const items = ref<SignatureItem[]>([])
const loading = ref(false)
const filter = ref<FilterId>('pending')

const filters: Array<{ id: FilterId; label: string }> = [
  { id: 'pending', label: 'На подпись' },
  { id: 'signed', label: 'Подписанные' },
  { id: 'revoked', label: 'Отозванные' },
  { id: 'cancelled', label: 'Отменённые' },
  { id: 'all', label: 'Все' },
]

const counts = computed<Record<FilterId, number>>(() => {
  const out: Record<FilterId, number> = {
    pending: 0,
    signed: 0,
    revoked: 0,
    cancelled: 0,
    all: items.value.length,
  }
  for (const it of items.value) {
    if (it.status === 'pending') out.pending++
    else if (it.status === 'signed_electronic' || it.status === 'signed_physical') out.signed++
    else if (it.status === 'revoked') out.revoked++
    else if (it.status === 'cancelled') out.cancelled++
  }
  return out
})

const filteredItems = computed(() => {
  if (filter.value === 'all') return items.value
  if (filter.value === 'pending') return items.value.filter((i) => i.status === 'pending')
  if (filter.value === 'signed') return items.value.filter((i) => i.status === 'signed_electronic' || i.status === 'signed_physical')
  if (filter.value === 'revoked') return items.value.filter((i) => i.status === 'revoked')
  return items.value.filter((i) => i.status === 'cancelled')
})

const fetchSignatures = async () => {
  loading.value = true
  try {
    const resp = await $fetch<{ items: SignatureItem[] }>('/api/v1/signatures', {
      baseURL: config.public.apiBase,
      credentials: 'include',
    })
    items.value = resp.items || []
  } catch (err: unknown) {
    const e = err as { data?: { detail?: string } }
    console.error('Failed to load signatures', err)
    toast.error(e?.data?.detail || 'Не удалось загрузить документы')
  } finally {
    loading.value = false
  }
}

// --- Modal state
const active = ref<SignatureItem | null>(null)
const consentAccepted = ref(false)
const signingElectronic = ref(false)
const uploadingPhysical = ref(false)
const actionError = ref('')

const previewUrl = ref<string | null>(null)
const previewLoading = ref(false)
const previewPending = ref(false)
const previewError = ref('')

let previewToken = 0

const {
  currentStatus: identityStatus,
  refreshStatus: refreshIdentityStatus,
  mobileIdRequiredMessage,
} = useIdentityVerification()

const showIdentityVerificationModal = ref(false)
const pendingSopdAfterVerification = ref<SignatureItem | null>(null)
const currentUserPhone = computed(() => {
  const phone = authStore.user?.phone
  return typeof phone === 'string' ? phone : null
})
const currentUserBirthDate = ref<string | null>(null)
let currentUserBirthDatePromise: Promise<void> | null = null
const isIdentityVerified = computed(() =>
  identityStatus.value?.verified === true || identityStatus.value?.status === 'verified',
)

const fetchCurrentUserBirthDate = async () => {
  const response = await $fetch<CurrentUserProfileResponse>('/api/v1/users/me', {
    baseURL: config.public.apiBase,
    credentials: 'include',
  })
  const birthDate = response.role_specific?.birth_date
  currentUserBirthDate.value = typeof birthDate === 'string' && birthDate ? birthDate : null
}

const ensureCurrentUserBirthDate = async () => {
  if (currentUserBirthDate.value) return
  currentUserBirthDatePromise ||= fetchCurrentUserBirthDate().finally(() => {
    currentUserBirthDatePromise = null
  })
  await currentUserBirthDatePromise
}

const releasePreview = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

const loadPreview = async (id: UUID) => {
  releasePreview()
  previewToken += 1
  const token = previewToken
  previewError.value = ''
  previewPending.value = false
  previewLoading.value = true

  const maxAttempts = 20
  try {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (token !== previewToken) return
      const resp = await fetch(
        `${config.public.apiBase.replace(/\/$/, '')}/api/v1/signatures/${id}/preview`,
        { credentials: 'include' },
      )
      if (token !== previewToken) return
      if (resp.status === 200) {
        const blob = await resp.blob()
        if (token !== previewToken) return
        previewUrl.value = URL.createObjectURL(blob)
        previewPending.value = false
        return
      }
      if (resp.status === 202) {
        previewPending.value = true
        const retryAfter = Number(resp.headers.get('Retry-After')) || 3
        await sleep(Math.max(1, retryAfter) * 1000)
        continue
      }
      let detail = ''
      try {
        const body = await resp.json()
        detail = body?.detail || ''
      } catch { /* non-JSON error body */ }
      previewError.value = detail || `Не удалось загрузить документ (HTTP ${resp.status})`
      return
    }
    previewError.value = 'Документ всё ещё готовится. Попробуйте обновить позже.'
  } catch (err: unknown) {
    if (token !== previewToken) return
    const e = err as { message?: string }
    previewError.value = e?.message || 'Не удалось загрузить документ'
  } finally {
    if (token === previewToken) {
      previewLoading.value = false
    }
  }
}

const openSignModal = async (
  item: SignatureItem,
  options: { skipIdentityGate?: boolean } = {},
) => {
  if (!options.skipIdentityGate && shouldGateSopd(item)) {
    await refreshIdentityStatus().catch(() => null)
    if (!isIdentityVerified.value) {
      await openIdentityVerificationGate(item)
      return
    }
  }

  active.value = item
  consentAccepted.value = false
  actionError.value = ''
  loadPreview(item.id)
}

const closeSignModal = () => {
  active.value = null
  consentAccepted.value = false
  actionError.value = ''
  previewError.value = ''
  previewPending.value = false
  previewToken += 1
  releasePreview()
}

const onSignElectronic = async () => {
  if (!active.value) return
  if (!consentAccepted.value) {
    actionError.value = 'Подтвердите согласие с текстом документа'
    return
  }
  signingElectronic.value = true
  actionError.value = ''
  try {
    await $fetch(`/api/v1/signatures/${active.value.id}/sign-electronic`, {
      method: 'POST',
      baseURL: config.public.apiBase,
      credentials: 'include',
    })
    toast.success('Документ подписан')
    closeSignModal()
    await fetchSignatures()
    filter.value = 'signed'
  } catch (err: unknown) {
    if (await handleMobileIdGateError(err)) return
    const e = err as { data?: { detail?: string } }
    actionError.value = e?.data?.detail || 'Не удалось подписать'
    toast.error(actionError.value)
  } finally {
    signingElectronic.value = false
  }
}

const onUploadPhysical = async (event: Event) => {
  if (!active.value) return
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  uploadingPhysical.value = true
  actionError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    await $fetch(`/api/v1/signatures/${active.value.id}/upload-physical`, {
      method: 'POST',
      baseURL: config.public.apiBase,
      credentials: 'include',
      body: fd,
    })
    toast.success('Скан загружен')
    closeSignModal()
    await fetchSignatures()
    filter.value = 'signed'
  } catch (err: unknown) {
    if (await handleMobileIdGateError(err)) return
    const e = err as { data?: { detail?: string } }
    actionError.value = e?.data?.detail || 'Не удалось загрузить скан'
    toast.error(actionError.value)
  } finally {
    uploadingPhysical.value = false
    // reset input so the same file can be picked again after a failure
    target.value = ''
  }
}

// --- SOPD revoke flow
const revokeTarget = ref<SignatureItem | null>(null)
const revokeSignatureId = computed(() => revokeTarget.value?.id ?? null)
const {
  isLoading: isRevoking,
  isVerifying,
  error: revokeError,
  phoneMasked,
  resendDelay,
  canResend,
  initiateRevoke,
  verifyCode,
  resendCode,
  clearError: clearRevokeError,
} = useSignatureRevoke(revokeSignatureId)

const showRevokeConfirmModal = ref(false)
const showRevokeCodeModal = ref(false)
const revokeCodeDigits = ref(['', '', '', ''])
const revokeCodeInputs = ref<HTMLInputElement[]>([])
const selectedRevokeOperatorIdsBySignature = ref<Record<UUID, UUID[]>>({})
const selectedRevokeLeasingCompanyIds = ref<UUID[]>([])
const selectedRevokeLeasingCompanies = ref<RevokeCompanyDraft[]>([])
const revokeAllMode = ref(false)

const canRevoke = (item: SignatureItem): boolean => {
  return item.document_type === 'sopd'
    && ['signed_electronic', 'signed_physical'].includes(item.status)
    && Boolean(item.sopd_revoke_summary?.active_leasing_company_ids?.length)
}

const canFullRevoke = (item: SignatureItem): boolean => {
  return canRevoke(item)
}

const canRevokeOperator = (
  item: SignatureItem,
  operator: SopdOperatorStatus,
): boolean => {
  return canRevoke(item)
    && operator.operator_type === 'leasing_company'
    && operator.status === 'active'
    && Boolean(operator.id)
}

const activeRevokeOperatorIds = (item: SignatureItem): UUID[] => {
  return (item.sopd_operators || [])
    .filter(operator => canRevokeOperator(item, operator))
    .map(operator => operator.id)
}

const normalizeRevokeSelection = (
  item: SignatureItem,
  ids: UUID[],
): UUID[] => {
  const activeIds = new Set(activeRevokeOperatorIds(item))
  return Array.from(new Set(ids)).filter(id => activeIds.has(id))
}

const selectedRevokeIds = (item: SignatureItem): UUID[] => {
  const key = item.id
  const selectedIds = selectedRevokeOperatorIdsBySignature.value[key] || []
  return normalizeRevokeSelection(item, selectedIds)
}

const selectedRevokeCount = (item: SignatureItem): number => {
  return selectedRevokeIds(item).length
}

const setSelectedRevokeIds = (
  item: SignatureItem,
  ids: UUID[],
) => {
  const key = item.id
  const normalizedIds = normalizeRevokeSelection(item, ids)
  const nextSelections = { ...selectedRevokeOperatorIdsBySignature.value }

  if (normalizedIds.length) {
    nextSelections[key] = normalizedIds
  } else {
    delete nextSelections[key]
  }

  selectedRevokeOperatorIdsBySignature.value = nextSelections
}

const clearSelectedRevokeIds = (item: SignatureItem | null) => {
  if (!item) return
  setSelectedRevokeIds(item, [])
}

const isOperatorSelectedForRevoke = (
  item: SignatureItem,
  operatorId: UUID,
): boolean => {
  return selectedRevokeIds(item).includes(operatorId)
}

const onRevokeOperatorCheck = (
  item: SignatureItem,
  operator: SopdOperatorStatus,
  event: Event,
) => {
  if (!canRevokeOperator(item, operator)) return

  const checked = (event.target as HTMLInputElement | null)?.checked ?? false
  const currentIds = selectedRevokeIds(item)
  const nextIds = checked
    ? [...currentIds, operator.id]
    : currentIds.filter(id => id !== operator.id)

  setSelectedRevokeIds(item, nextIds)
}

const selectedRevokeCompaniesByIds = (
  item: SignatureItem,
  ids: UUID[],
): RevokeCompanyDraft[] => {
  const activeOperators = (item.sopd_operators || [])
    .filter((operator): operator is SopdOperatorStatus => (
      operator.operator_type === 'leasing_company'
      && operator.status === 'active'
      && ids.includes(operator.id)
    ))

  return activeOperators.length
    ? activeOperators
    : ids.map(id => ({ id }))
}

const hasPartialRevoke = (item: SignatureItem): boolean => {
  return Boolean(item.sopd_revoke_summary?.has_partial_revoke)
}

const isRevokeCodeComplete = computed(() => {
  return revokeCodeDigits.value.every((digit) => /^\d$/.test(digit))
})

const revokeConfirmTitle = computed(() => {
  if (revokeAllMode.value) return 'Отозвать СОПД полностью'
  return selectedRevokeLeasingCompanyIds.value.length > 1
    ? 'Отозвать СОПД у выбранных компаний'
    : 'Отозвать СОПД у компании'
})

const revokeConfirmSubtitle = computed(() => {
  if (revokeAllMode.value) {
    return 'Будет отозвана обработка персональных данных у всех активных лизинговых компаний этого СОПД.'
  }

  return selectedRevokeLeasingCompanyIds.value.length > 1
    ? 'Будет отозвана обработка персональных данных у выбранных лизинговых компаний.'
    : 'Будет отозвана обработка персональных данных у выбранной лизинговой компании.'
})

const revokeConfirmText = computed(() => {
  if (revokeAllMode.value) return 'Отозвать всё'
  return selectedRevokeLeasingCompanyIds.value.length > 1
    ? 'Отозвать выбранное'
    : 'Отозвать компанию'
})

const setRevokeCodeInputRef = (
  el: Element | ComponentPublicInstance | null,
  index: number,
) => {
  if (el instanceof HTMLInputElement) {
    revokeCodeInputs.value[index] = el
  }
}

const openRevokeConfirm = async (
  item: SignatureItem,
  options: { selectAll?: boolean; selectedIds?: string[] } = {},
) => {
  revokeTarget.value = item
  selectedRevokeLeasingCompanyIds.value = []
  selectedRevokeLeasingCompanies.value = []
  revokeAllMode.value = Boolean(options.selectAll)
  clearRevokeError()

  if (options.selectedIds?.length) {
    const selectedIds = normalizeRevokeSelection(item, options.selectedIds)
    selectedRevokeLeasingCompanyIds.value = selectedIds
    selectedRevokeLeasingCompanies.value = selectedRevokeCompaniesByIds(item, selectedIds)
  } else if (options.selectAll) {
    const activeIds = item.sopd_revoke_summary?.active_leasing_company_ids || []
    selectedRevokeLeasingCompanyIds.value = activeIds
    selectedRevokeLeasingCompanies.value = selectedRevokeCompaniesByIds(item, activeIds)
  }

  showRevokeConfirmModal.value = true
}

const closeRevokeConfirm = () => {
  showRevokeConfirmModal.value = false
  revokeAllMode.value = false
  selectedRevokeLeasingCompanyIds.value = []
  selectedRevokeLeasingCompanies.value = []
}

const resetRevokeCodeInputs = () => {
  revokeCodeDigits.value = ['', '', '', '']
}

const onConfirmRevoke = async () => {
  clearRevokeError()
  const leasingCompanyIds = [...selectedRevokeLeasingCompanyIds.value]
  try {
    await initiateRevoke(leasingCompanyIds)
    showRevokeConfirmModal.value = false
    resetRevokeCodeInputs()
    showRevokeCodeModal.value = true
    await nextTick()
    revokeCodeInputs.value[0]?.focus()
  } catch {
    // User-facing error is owned by the composable.
  }
}

const onRevokeCodeInput = async (index: number) => {
  const digit = revokeCodeDigits.value[index]
  if (!/^\d?$/.test(digit)) {
    revokeCodeDigits.value[index] = ''
    return
  }
  clearRevokeError()
  if (digit && index < 3) {
    await nextTick()
    revokeCodeInputs.value[index + 1]?.focus()
  }
  if (isRevokeCodeComplete.value) {
    await nextTick()
    await onVerifyRevokeCode()
  }
}

const onRevokeCodeBackspace = async (index: number) => {
  if (!revokeCodeDigits.value[index] && index > 0) {
    revokeCodeDigits.value[index - 1] = ''
    await nextTick()
    revokeCodeInputs.value[index - 1]?.focus()
  }
}

const onRevokeCodePaste = async (event: ClipboardEvent) => {
  event.preventDefault()
  const digits = (event.clipboardData?.getData('text') || '')
    .replace(/\D/g, '')
    .slice(0, 4)

  digits.split('').forEach((digit, index) => {
    revokeCodeDigits.value[index] = digit
  })

  await nextTick()
  revokeCodeInputs.value[Math.min(digits.length, 3)]?.focus()
  if (digits.length === 4) {
    await onVerifyRevokeCode()
  }
}

const onVerifyRevokeCode = async () => {
  if (!isRevokeCodeComplete.value || isVerifying.value) return
  try {
    const verifiedTarget = revokeTarget.value
    const result = await verifyCode(revokeCodeDigits.value.join(''))
    showRevokeCodeModal.value = false
    clearSelectedRevokeIds(verifiedTarget)
    await fetchSignatures()
    filter.value = result?.is_full_revoke ? 'revoked' : 'signed'
  } catch {
    resetRevokeCodeInputs()
    await nextTick()
    revokeCodeInputs.value[0]?.focus()
  }
}

const onResendRevokeCode = async () => {
  if (!canResend.value) return
  clearRevokeError()
  try {
    await resendCode()
    resetRevokeCodeInputs()
    await nextTick()
    revokeCodeInputs.value[0]?.focus()
  } catch {
    // User-facing error is owned by the composable.
  }
}

const shouldGateSopd = (item: SignatureItem): boolean => {
  return item.status === 'pending' && item.document_type === 'sopd'
}

const openIdentityVerificationGate = async (item: SignatureItem | null) => {
  pendingSopdAfterVerification.value = active.value ? null : item
  actionError.value = ''
  await ensureCurrentUserBirthDate().catch(() => null)
  showIdentityVerificationModal.value = true
}

const readErrorDetail = (err: unknown): string => {
  const detail = (err as { data?: { detail?: unknown; message?: string } })?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: unknown }).message || '')
  }
  return (err as { data?: { message?: string }; message?: string })?.data?.message
    || (err as { message?: string })?.message
    || ''
}

const handleMobileIdGateError = async (err: unknown): Promise<boolean> => {
  const status = (err as { status?: number; statusCode?: number; response?: { status?: number } })?.status
    || (err as { statusCode?: number })?.statusCode
    || (err as { response?: { status?: number } })?.response?.status
  const detail = readErrorDetail(err)
  const isGateError = status === 403 && (
    detail === mobileIdRequiredMessage
    || detail.includes('Mobile ID')
    || detail.includes('верификаци')
  )

  if (!isGateError || active.value?.document_type !== 'sopd') {
    return false
  }

  await openIdentityVerificationGate(active.value)
  return true
}

const onIdentityVerified = async () => {
  showIdentityVerificationModal.value = false
  await refreshIdentityStatus().catch(() => null)

  const item = pendingSopdAfterVerification.value
  pendingSopdAfterVerification.value = null
  if (item) {
    await openSignModal(item, { skipIdentityGate: true })
  }
}

// --- URLs
const fullRevokeDocumentUrl = (item: SignatureItem): string | null => {
  if (item.document_type !== 'sopd' || item.status !== 'revoked') return null
  const operator = (item.sopd_operators || [])
    .find(row => Boolean(row.revoke_document_download_url))
  return operator?.revoke_document_download_url || null
}

const canDownloadDocument = (item: SignatureItem): boolean => {
  return Boolean(item.signed_pdf_s3_key || fullRevokeDocumentUrl(item))
}

const downloadHref = (item: SignatureItem) => {
  const revokeDocumentUrl = fullRevokeDocumentUrl(item)
  if (revokeDocumentUrl) return operatorDownloadHref(revokeDocumentUrl)
  const nonce = Date.now()
  return `${config.public.apiBase.replace(/\/$/, '')}/api/v1/signatures/${item.id}/download?download_ts=${nonce}`
}
const downloadLabel = (item: SignatureItem): string => {
  return fullRevokeDocumentUrl(item) ? 'Скачать отзыв' : 'Скачать'
}
const operatorDownloadHref = (url: string) => {
  if (/^https?:\/\//.test(url)) return url
  return `${config.public.apiBase.replace(/\/$/, '')}${url}`
}

// --- Formatters
const docTypeLabel = (type: string): string => {
  if (type === 'sopd') return 'Согласие на обработку персональных данных'
  return type
}

const operatorTypeLabel = (type: SopdOperatorStatus['operator_type']): string => {
  return type === 'leasing_company' ? 'ЛК' : 'Подрядчик'
}
const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso || ''
  }
}

onMounted(() => {
  fetchSignatures()
  refreshIdentityStatus().catch(() => null)
  ensureCurrentUserBirthDate().catch(() => null)
})

onBeforeUnmount(() => {
  releasePreview()
})

// --- Inline badge component
const StatusBadge = defineComponent({
  props: { status: { type: String, required: true } },
  setup(props) {
    const map: Record<string, { text: string; cls: string }> = {
      pending: { text: 'Ожидает подписи', cls: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)] border-[color:var(--storefront-warning-border,#fde68a)]' },
      signed_electronic: { text: 'Подписан электронно', cls: 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#065f46)] border-[color:var(--storefront-success-border,#a7f3d0)]' },
      signed_physical: { text: 'Подписан (скан)', cls: 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#065f46)] border-[color:var(--storefront-success-border,#a7f3d0)]' },
      revoked: { text: 'Отозван', cls: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)] border-[color:var(--storefront-error-border,#fecaca)]' },
      cancelled: { text: 'Отменён', cls: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)] border-[color:var(--storefront-error-border,#fecaca)]' },
    }
    return () => {
      const b = map[props.status] || { text: props.status, cls: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)] border-[color:var(--storefront-border,#e5e7eb)]' }
      return h('span', { class: ['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border', b.cls] }, b.text)
    }
  },
})
</script>
