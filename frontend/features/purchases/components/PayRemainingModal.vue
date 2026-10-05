<template>
  <Modal
    :show="show"
    :title="modalTitle"
    size="xl"
    @close="handleClose"
  >
    <!-- Step indicator -->
    <div data-storefront-block="client.order" v-if="!success" class="flex items-center justify-center gap-2 mb-6">
      <div v-for="s in 2" :key="s" class="flex items-center gap-2">
        <div
          class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all"
          :class="step >= s ? 'bg-[color:rgb(var(--storefront-success-rgb,22_163_74)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]' : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#6b7280)]'"
        >
          <svg v-if="step > s" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
          </svg>
          <span v-else>{{ s }}</span>
        </div>
        <div v-if="s < 2" class="w-8 sm:w-12 h-0.5 rounded" :class="step > s ? 'bg-[color:rgb(var(--storefront-success-rgb,22_163_74)/var(--tw-bg-opacity,1))]' : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]'"></div>
      </div>
    </div>

    <!-- SUCCESS -->
    <div data-storefront-block="client.order" v-if="success" class="text-center py-8">
      <div class="relative w-20 h-20 mx-auto mb-5">
        <div class="absolute inset-0 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-full animate-ping opacity-30"></div>
        <div class="relative w-20 h-20 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
          <svg class="w-10 h-10 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
      </div>
      <h3 class="text-xl font-bold text-[color:var(--storefront-title,#111827)] mb-2">Оплата прошла успешно!</h3>
      <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-2">Способ оплаты: {{ paymentMethodLabel }}</p>
      <p class="text-2xl font-bold text-[color:var(--storefront-success-text,#16a34a)] mb-4">{{ formatPrice(amount) }}</p>
    </div>

    <!-- STEP 1: Payment method -->
    <div data-storefront-block="client.order" v-else-if="step === 1">
      <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-xl px-4 py-3 mb-5 flex items-center justify-between">
        <span class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Доплата остатка</span>
        <span class="text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(amount) }}</span>
      </div>

      <div class="space-y-3 mb-6">
        <!-- SBP -->
        <button type="button" @click="paymentMethod = 'sbp'"
          class="storefront-action-ghost w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all"
          :class="paymentMethod === 'sbp' ? 'border-[color:var(--storefront-primary-border,#3b82f6)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-primary-border,#e5e7eb)] hover:border-[color:var(--storefront-primary-hover-border,#d1d5db)]'">
          <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-[var(--storefront-gradient-from,#4ade80)] to-[var(--storefront-gradient-to,#3b82f6)] flex items-center justify-center shrink-0">
            <svg class="w-6 h-6 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div class="flex-1">
            <div class="font-semibold text-[color:var(--storefront-text,#111827)]">Система быстрых платежей</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Мгновенный перевод через СБП</div>
          </div>
          <div v-if="paymentMethod === 'sbp'" class="w-5 h-5 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center shrink-0">
            <svg class="w-3 h-3 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </button>

        <!-- Card -->
        <button type="button" @click="paymentMethod = 'card'"
          class="storefront-action-ghost w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all"
          :class="paymentMethod === 'card' ? 'border-[color:var(--storefront-primary-border,#3b82f6)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-primary-border,#e5e7eb)] hover:border-[color:var(--storefront-primary-hover-border,#d1d5db)]'">
          <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-[var(--storefront-gradient-from,#8b5cf6)] to-[var(--storefront-gradient-to,#9333ea)] flex items-center justify-center shrink-0">
            <svg class="w-6 h-6 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
          </div>
          <div class="flex-1">
            <div class="font-semibold text-[color:var(--storefront-text,#111827)]">Банковская карта</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Visa, MasterCard, МИР</div>
          </div>
          <div v-if="paymentMethod === 'card'" class="w-5 h-5 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center shrink-0">
            <svg class="w-3 h-3 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </button>

        <!-- Bank transfer -->
        <button type="button" @click="paymentMethod = 'bank'"
          class="storefront-action-ghost w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all"
          :class="paymentMethod === 'bank' ? 'border-[color:var(--storefront-primary-border,#3b82f6)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-primary-border,#e5e7eb)] hover:border-[color:var(--storefront-primary-hover-border,#d1d5db)]'">
          <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-[var(--storefront-gradient-from,#fbbf24)] to-[var(--storefront-gradient-to,#f97316)] flex items-center justify-center shrink-0">
            <svg class="w-6 h-6 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <div class="flex-1">
            <div class="font-semibold text-[color:var(--storefront-text,#111827)]">По реквизитам</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Банковский перевод по счёту</div>
          </div>
          <div v-if="paymentMethod === 'bank'" class="w-5 h-5 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center shrink-0">
            <svg class="w-3 h-3 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </button>
      </div>

      <button type="button" @click="goToStep2" :disabled="!paymentMethod"
        class="storefront-action-ghost w-full py-3.5 rounded-xl text-[color:var(--storefront-ghost-foreground,#ffffff)] font-semibold bg-[color:rgb(var(--storefront-ghost-rgb,22_163_74)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,21_128_61)/var(--tw-bg-opacity,1))] transition-all disabled:opacity-40 disabled:cursor-not-allowed">
        Продолжить
      </button>
    </div>

    <!-- STEP 2: Confirmation & Payment -->
    <div data-storefront-block="client.order" v-else-if="step === 2">
      <!-- Payment summary card -->
      <div class="rounded-2xl border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden mb-5">
        <div class="bg-gradient-to-r from-[var(--storefront-gradient-from,#16a34a)] to-[var(--storefront-gradient-to,#15803d)] px-5 py-4 text-[color:var(--storefront-text,#ffffff)]">
          <div class="text-sm opacity-80">Доплата остатка</div>
          <div class="text-2xl font-bold mt-0.5">{{ formatPrice(amount) }}</div>
        </div>
        <div class="px-5 py-3 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
          <div class="flex items-center gap-3 text-sm">
            <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Способ оплаты:</span>
            <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ paymentMethodLabel }}</span>
          </div>
        </div>
      </div>

      <!-- SBP Payment (direct API link) -->
      <div v-if="paymentMethod === 'sbp' && sbpData && activePaymentId" class="mb-5">
        <SbpPayment
          :sbp-data="sbpData"
          :payment-id="activePaymentId"
          @completed="onPaymentCompleted"
          @failed="onPaymentFailed"
          @retry="handleRetryPayment"
        />
      </div>

      <!-- Waiting for payment preparation -->
      <div v-else-if="(paymentMethod === 'sbp' || paymentMethod === 'card') && !sbpData && processing" class="mb-5">
        <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-xl p-5 text-center">
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-[color:var(--storefront-success-border,#16a34a)] border-t-transparent mx-auto mb-3"></div>
          <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Подготовка платежа...</p>
        </div>
      </div>

      <!-- Bank transfer — invoice -->
      <div v-if="paymentMethod === 'bank'" class="mb-5">
        <div class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
          <!-- Invoice header -->
          <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,55_65_81)/var(--tw-bg-opacity,1))] px-5 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <img src="/images/logo.png" alt="КарКрафт" class="h-7 object-contain opacity-90" onerror="this.style.display='none'" style="filter: invert()">
              <div class="text-[color:var(--storefront-text,#ffffff)]">
                <div class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)] uppercase tracking-wide">Счёт на оплату</div>
                <div class="font-bold text-sm">№ {{ invoiceNumber }} от {{ invoiceDate }}</div>
              </div>
            </div>
            <button type="button" @click="downloadInvoicePdf"
              class="storefront-action-secondary flex items-center gap-1.5 px-3 py-1.5 bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/0.1)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,255_255_255)/0.2)] rounded-lg text-[color:var(--storefront-secondary-foreground,#ffffff)] text-xs font-medium transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Скачать PDF
            </button>
          </div>

          <!-- QR code -->
          <div class="p-4 border-t border-[color:var(--storefront-border,#e5e7eb)] flex flex-col sm:flex-row items-center gap-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,55_65_81)/var(--tw-bg-opacity,1))]">
            <div class="w-36 h-36 shrink-0 rounded-xl overflow-hidden flex items-center justify-center border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <img v-if="qrDataUrl" :src="qrDataUrl" alt="QR для оплаты" class="w-full h-full object-contain">
              <div v-else class="flex flex-col items-center justify-center gap-1 text-[color:var(--storefront-text-muted,#9ca3af)]">
                <svg class="text-[color:var(--storefront-icon,inherit)] w-16 h-16 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
                </svg>
                <span class="text-[10px]">QR-код</span>
              </div>
            </div>
            <div class="text-center sm:text-left">
              <div class="text-sm text-[color:var(--storefront-text,#ffffff)] leading-relaxed">Отсканируйте QR-код в приложении банка для быстрой оплаты по реквизитам счёта.<br>Стандарт ЦБ РФ ГОСТ Р 56042.</div>
            </div>
          </div>

          <!-- Invoice body -->
          <div class="p-5 space-y-4 text-sm">
            <div>
              <div class="text-[10px] font-semibold text-[color:var(--storefront-text-muted,#9ca3af)] uppercase tracking-wider mb-1.5">Получатель</div>
              <div class="font-semibold text-[color:var(--storefront-text,#111827)]">ООО «КАРКРАФТ»</div>
              <div class="text-[color:var(--storefront-text-muted,#4b5563)] mt-0.5">ИНН 9718036458 / КПП 772101001 / ОГРН 5167746349271</div>
              <div class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs mt-0.5">125424, г. Москва, Сходненский тупик, 16</div>
            </div>

            <div class="grid grid-cols-2 gap-x-4 gap-y-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg p-3">
              <div><span class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs">Р/с</span><div class="font-mono text-[color:var(--storefront-text,#111827)] text-xs mt-0.5">40702810070010010505</div></div>
              <div><span class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs">Банк</span><div class="text-[color:var(--storefront-text,#111827)] text-xs mt-0.5">МФ АО КБ «МОДУЛЬБАНК»</div></div>
              <div><span class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs">БИК</span><div class="font-mono text-[color:var(--storefront-text,#111827)] text-xs mt-0.5">044525092</div></div>
              <div><span class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs">К/с</span><div class="font-mono text-[color:var(--storefront-text,#111827)] text-xs mt-0.5">30101810645250000092</div></div>
            </div>

            <div>
              <div class="text-[10px] font-semibold text-[color:var(--storefront-text-muted,#9ca3af)] uppercase tracking-wider mb-1.5">Товары / услуги</div>
              <table class="w-full text-xs">
                <thead>
                  <tr class="border-b border-[color:var(--storefront-border,#e5e7eb)]">
                    <th class="text-left py-1.5 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Наименование</th>
                    <th class="text-right py-1.5 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Кол-во</th>
                    <th class="text-right py-1.5 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-b border-[color:var(--storefront-border,#f3f4f6)]">
                    <td class="py-1.5 text-[color:var(--storefront-text,#111827)]">Доплата остатка: {{ vehicleTitle }}</td>
                    <td class="py-1.5 text-right text-[color:var(--storefront-text-muted,#4b5563)]">1</td>
                    <td class="py-1.5 text-right font-medium text-[color:var(--storefront-text,#111827)]">{{ formatPrice(amount) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="flex items-center justify-between pt-2 border-t-2 border-[color:var(--storefront-border,#111827)]">
              <span class="font-bold text-[color:var(--storefront-text,#111827)]">Итого к оплате</span>
              <span class="text-xl font-bold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(amount) }}</span>
            </div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              В т.ч. НДС 22%. Оплата в течение 1 банковского дня.
            </div>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="errorMessage" class="mb-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] rounded-xl border border-[color:var(--storefront-error-border,#fecaca)] text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
        {{ errorMessage }}
      </div>

      <div class="flex gap-3">
        <button type="button" @click="handleBack" :disabled="processing"
          class="storefront-action-ghost flex-1 py-3 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-xl text-[color:var(--storefront-secondary-foreground,#374151)] font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors disabled:opacity-50">
          Назад
        </button>
        <button v-if="paymentMethod === 'bank'" type="button" @click="handlePay" :disabled="processing"
          class="storefront-action-ghost flex-1 py-3.5 px-4 rounded-xl text-[color:var(--storefront-ghost-foreground,#ffffff)] font-semibold bg-[color:rgb(var(--storefront-ghost-rgb,22_163_74)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,21_128_61)/var(--tw-bg-opacity,1))] transition-all disabled:opacity-50">
          <span v-if="processing" class="flex items-center justify-center gap-2">
            <div class="animate-spin rounded-full h-4 w-4 border-2 border-[color:var(--storefront-border,#ffffff)] border-t-transparent"></div>
            Обработка платежа...
          </span>
          <span v-else>Оплатить {{ formatPrice(amount) }}</span>
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import SbpPayment from '~/features/purchases/components/SbpPayment.vue'
import type { UUID } from '~/types/ids'

const props = defineProps({
  show: { type: Boolean, default: false },
  order: { type: Object, required: true },
})

const emit = defineEmits(['close', 'success'])

const { formatPrice } = useFormatPrice()
const purchasesStore = usePurchasesStore()
const toast = useToast()

const step = ref(1)
const paymentMethod = ref('sbp')
const processing = ref(false)
const errorMessage = ref('')
const success = ref(false)
const qrDataUrl = ref('')
const sbpData = ref<{ sbpLink: string; amount: number; expiresAt?: string } | null>(null)
const activePaymentId = ref<UUID | null>(null)

const amount = computed(() => parseFloat(props.order.remaining_amount) || 0)
const vehicleTitle = computed(() =>
  `${props.order.mark_name || ''} ${props.order.model_name || ''}`.trim() || 'Автомобиль'
)

const PAYMENT_LABELS: Record<string, string> = { sbp: 'СБП', card: 'Банковская карта', bank: 'По реквизитам' }
const paymentMethodLabel = computed(() => PAYMENT_LABELS[paymentMethod.value] || '')

const modalTitle = computed(() => {
  if (success.value) return ''
  return step.value === 1 ? 'Способ оплаты' : 'Подтверждение оплаты'
})

const COMPANY = {
  name: 'ООО «КАРКРАФТ»',
  inn: '9718036458',
  kpp: '772101001',
  ogrn: '5167746349271',
  bankName: 'МОСКОВСКИЙ ФИЛИАЛ АО КБ «МОДУЛЬБАНК» Г.МОСКВА',
  bik: '044525092',
  corrAccount: '30101810645250000092',
  settlementAccount: '40702810070010010505',
  legalAddress: '109431, г. Москва, ул. Привольная, 70 к1, этаж 2, пом XII, ком 19ж',
  address: '125424, г. Москва, Сходненский тупик, 16',
  director: 'Зеленский Даниэль Викторович',
  phone: '+7 (495) 922-20-20',
  site: 'www.carcraft.ru'
}

const invoiceNumber = computed(() => {
  const d = new Date()
  return `СЧ-${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}-${Math.floor(Math.random() * 900 + 100)}`
})
const invoiceDate = computed(() => {
  return new Date().toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
})

async function generatePaymentQR() {
  if (!process.client) return
  qrDataUrl.value = ''
  try {
    const QRCode = (await import('qrcode')).default
    const sumKopecks = Math.round(amount.value * 100)
    const purpose = `Оплата счёта ${invoiceNumber.value} от ${invoiceDate.value}`
    const qrStr = [
      'ST00012',
      `Name=${COMPANY.name}`,
      `PersonalAcc=${COMPANY.settlementAccount}`,
      `BankName=${COMPANY.bankName}`,
      `BIC=${COMPANY.bik}`,
      `CorrespAcc=${COMPANY.corrAccount}`,
      `PayeeINN=${COMPANY.inn}`,
      `KPP=${COMPANY.kpp}`,
      `Purpose=${purpose}`,
      `Sum=${sumKopecks}`
    ].join('|')

    const encoder = new TextEncoder()
    const bytes = encoder.encode(qrStr)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i])
    }

    qrDataUrl.value = await QRCode.toDataURL([{ data: binary, mode: 'byte' }], {
      errorCorrectionLevel: 'M',
      width: 160,
      margin: 4
    })
  } catch (e) {
    console.error('QR generation error:', e)
    qrDataUrl.value = ''
  }
}

watch([step, paymentMethod], ([s, m]) => {
  if (s === 2 && m === 'bank') generatePaymentQR()
  else qrDataUrl.value = ''
})

function downloadInvoicePdf() {
  const name = `Доплата остатка: ${vehicleTitle.value}`
  const totalFormatted = Number(amount.value).toLocaleString('ru-RU')

  const qrImgHtml = qrDataUrl.value
    ? `<img src="${qrDataUrl.value}" width="120" height="120" style="display:block">`
    : `<div style="width:120px;height:120px;background:#f0f0f0;border:1px dashed #ccc;display:flex;align-items:center;justify-content:center;font-size:11px;color:#999">QR-код</div>`

  const origin = process.client ? window.location.origin : ''

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Счёт ${invoiceNumber.value}</title>
<style>
  body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#1a1a1a;font-size:13px;line-height:1.5}
  .header{border-bottom:3px solid #1a1a1a;padding-bottom:16px;margin-bottom:24px;display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
  .header-left{display:flex;align-items:center;gap:14px}
  .header-logo{height:40px;object-fit:contain}
  .header-title h1{font-size:20px;margin:0 0 3px}
  .header-title .meta{color:#666;font-size:12px}
  .header-contact{text-align:right;font-size:11px;color:#666;line-height:1.8}
  .section{margin-bottom:20px}
  .section-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#888;margin-bottom:6px;font-weight:600}
  .bank-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 20px;background:#f8f8f8;padding:10px 12px;border-radius:6px;font-size:12px}
  .bank-grid .label{color:#888}
  .bank-grid .val{font-family:monospace}
  table{border-collapse:collapse;width:100%;font-size:12px}
  th{border:1px solid #ccc;padding:6px 8px;background:#f0f0f0;text-align:left;font-weight:600}
  .total-row{font-size:18px;font-weight:700;text-align:right;margin-top:12px}
  .footer{margin-top:40px;padding-top:16px;border-top:1px solid #ddd;font-size:11px;color:#888}
  .stamp-row{margin-top:40px;display:flex;align-items:flex-start;gap:60px}
  .stamp{flex:1}
  .stamp-line{border-bottom:1px solid #999;margin-top:30px}
  .stamp-label{font-size:11px;color:#888;margin-top:4px}
  .qr-section{display:flex;align-items:center;gap:16px;margin-top:20px;padding-top:16px;border-top:1px solid #eee}
  .qr-label{font-size:11px;color:#555;line-height:1.6}
  @media print{body{margin:20px}}
</style></head><body>
<div class="header">
  <div class="header-left">
    <img src="${origin}/images/logo.png" class="header-logo" onerror="this.style.display='none'" alt="КарКрафт">
    <div class="header-title">
      <h1>Счёт на оплату № ${invoiceNumber.value}</h1>
      <div class="meta">от ${invoiceDate.value} г.</div>
    </div>
  </div>
  <div class="header-contact">
    <div>${COMPANY.phone}</div>
    <div>${COMPANY.site}</div>
    <div>${COMPANY.address}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Получатель</div>
  <div><strong>${COMPANY.name}</strong></div>
  <div>ИНН ${COMPANY.inn} / КПП ${COMPANY.kpp} / ОГРН ${COMPANY.ogrn}</div>
  <div style="color:#666;font-size:12px">Юр. адрес: ${COMPANY.legalAddress}</div>
</div>

<div class="section">
  <div class="section-title">Банковские реквизиты</div>
  <div class="bank-grid">
    <div><span class="label">Р/с:</span> <span class="val">${COMPANY.settlementAccount}</span></div>
    <div><span class="label">Банк:</span> ${COMPANY.bankName}</div>
    <div><span class="label">БИК:</span> <span class="val">${COMPANY.bik}</span></div>
    <div><span class="label">К/с:</span> <span class="val">${COMPANY.corrAccount}</span></div>
  </div>
</div>

<div class="section">
  <div class="section-title">Товары / услуги</div>
  <table>
    <thead><tr><th style="width:40px;text-align:center">№</th><th>Наименование</th><th style="width:60px;text-align:center">Кол-во</th><th style="width:120px;text-align:right">Сумма</th></tr></thead>
    <tbody>
      <tr>
        <td style="border:1px solid #ccc;padding:6px 8px;text-align:center">1</td>
        <td style="border:1px solid #ccc;padding:6px 8px">${name}</td>
        <td style="border:1px solid #ccc;padding:6px 8px;text-align:center">1</td>
        <td style="border:1px solid #ccc;padding:6px 8px;text-align:right">${totalFormatted} ₽</td>
      </tr>
    </tbody>
  </table>
  <div class="total-row">Итого к оплате: ${totalFormatted} ₽</div>
  <div style="font-size:11px;color:#888;margin-top:4px">В т.ч. НДС 22%</div>
</div>

<div class="section">
  <div class="section-title">Условия оплаты</div>
  <div>Оплата в течение 3 (трёх) банковских дней с момента выставления счёта.</div>
  <div>Назначение платежа: <strong>Оплата по счёту ${invoiceNumber.value} от ${invoiceDate.value}</strong></div>
  <div class="qr-section">
    ${qrImgHtml}
    <div class="qr-label">
      <strong>Оплата по QR-коду</strong><br>
      Отсканируйте код в приложении банка.<br>
      Стандарт ЦБ РФ ГОСТ Р 56042.
    </div>
  </div>
</div>

<div class="stamp-row">
  <div class="stamp"><div class="stamp-line"></div><div class="stamp-label">Генеральный директор &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${COMPANY.director}</div></div>
  <div class="stamp"><div class="stamp-line"></div><div class="stamp-label">Главный бухгалтер</div></div>
</div>

<div class="footer">Документ сформирован автоматически и действителен без подписи и печати.</div>

<script>window.onload=function(){window.print()}<\/script>
</body></html>`

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const w = window.open(url, '_blank')
  if (!w) {
    const a = document.createElement('a')
    a.href = url
    a.download = `Счет_${invoiceNumber.value}.html`
    a.click()
  }
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function goToStep2() {
  step.value = 2
  if (paymentMethod.value === 'sbp' || paymentMethod.value === 'card') {
    handlePay()
  }
}

function submitCardPaymentForm(data: { formUrl: string; formParams: Record<string, unknown> }) {
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = data.formUrl
  form.style.display = 'none'
  for (const [key, value] of Object.entries(data.formParams)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = key
    input.value = String(value)
    form.appendChild(input)
  }
  document.body.appendChild(form)
  form.submit()
}

async function handlePay() {
  processing.value = true
  errorMessage.value = ''
  sbpData.value = null
  try {
    const backendMethod = paymentMethod.value === 'bank' ? 'bank_transfer' as const : paymentMethod.value as 'card' | 'sbp' | 'bank_transfer'
    const result = await purchasesStore.payRemainingBalance(props.order.id, backendMethod)

    if (result.sbpData) {
      sbpData.value = result.sbpData
      activePaymentId.value = result.payment?.id ?? null
      processing.value = false
      return
    }

    if (result.widgetData) {
      activePaymentId.value = result.payment?.id ?? null
      submitCardPaymentForm(result.widgetData)
      return
    }

    success.value = true
    toast.success('Оплата прошла успешно')
    emit('success')
  } catch (err: unknown) {
    const e = err as Record<string, unknown> | null
    const data = e?.data as Record<string, unknown> | undefined
    errorMessage.value = (data?.error || e?.message || 'Произошла ошибка при оплате') as string
  } finally {
    processing.value = false
  }
}

function onPaymentCompleted() {
  success.value = true
  sbpData.value = null
  toast.success('Оплата прошла успешно')
  emit('success')
}

function onPaymentFailed() {
  sbpData.value = null
  errorMessage.value = 'Оплата не прошла. Попробуйте снова.'
}

function handleRetryPayment() {
  sbpData.value = null
  errorMessage.value = ''
}

function handleBack() {
  if (!processing.value) {
    sbpData.value = null
    errorMessage.value = ''
    step.value = 1
  }
}

function handleClose() {
  if (!processing.value) emit('close')
}

watch(() => props.show, (val) => {
  if (val) {
    step.value = 1
    paymentMethod.value = 'sbp'
    processing.value = false
    errorMessage.value = ''
    success.value = false
    sbpData.value = null
    activePaymentId.value = null
    qrDataUrl.value = ''
  }
})
</script>
