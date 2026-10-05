<template>
  <Modal
    :show="true"
    title="Запрос дополнительной поддержки"
    :subtitle="`${vehicleTitle(vehicle)} · ${vehicle.vin}`"
    size="lg"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-support-request-form" class="space-y-4" novalidate @submit.prevent="submit">
      <p class="text-sm text-gray-600">
        Запрос уходит вашему дистрибьютору по марке техники. Отправленный запрос нельзя изменить или отозвать;
        у позиции может быть только один открытый запрос.
      </p>
      <FastDealCardField label="Запрашиваемая сумма, ₽" required for-id="fast-deal-support-amount" :error="amountError">
        <input
          id="fast-deal-support-amount"
          v-model="amount"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="input-field tabular-nums"
          :class="amountError ? 'border-red-500' : ''"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>
      <FastDealCardField label="Комментарий" for-id="fast-deal-support-comment" :error="commentError">
        <textarea
          id="fast-deal-support-comment"
          v-model="comment"
          rows="3"
          maxlength="2000"
          class="input-field"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>
      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-support-request-form" class="btn-primary" :disabled="ctx.busy.value" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Отправляем…' : 'Отправить запрос' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { isPositiveMoney, parseMoneyInput, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealVehicle } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{ vehicle: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const amount = ref('')
const comment = ref('')
const localError = ref('')
const serverError = ref<ActionFailure | null>(null)

const amountError = computed(() => localError.value || (serverError.value?.field === 'amount' ? serverError.value.detail : ''))
const commentError = computed(() => (serverError.value?.field === 'comment' ? serverError.value.detail : ''))
const generalError = computed(() =>
  serverError.value && serverError.value.field !== 'amount' && serverError.value.field !== 'comment' ? serverError.value : null,
)

async function submit() {
  serverError.value = null
  localError.value = ''
  const parsed = parseMoneyInput(amount.value)
  if (parsed === null || !isPositiveMoney(parsed)) {
    localError.value = 'Укажите положительную сумму, например 150000.00'
    return
  }
  const text = comment.value.trim()
  const result = await ctx.run((etag, card) =>
    ctx.api.requestSupport(card.id, props.vehicle.id, etag, text ? { amount: parsed, comment: text } : { amount: parsed }),
  )
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
