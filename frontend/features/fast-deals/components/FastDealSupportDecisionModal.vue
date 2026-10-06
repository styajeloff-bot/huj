<template>
  <Modal
    :show="true"
    title="Решение по запросу поддержки"
    :subtitle="`${vehicleTitle(vehicle)} · ${vehicle.vin}`"
    size="lg"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-support-decision-form" class="space-y-4" novalidate @submit.prevent="submit">
      <p class="text-sm text-gray-700">
        Запрошено: <strong class="tabular-nums">{{ formatMoney(request.requested_amount) }}</strong>
        <span v-if="request.comment" class="block text-gray-600 mt-1">Комментарий дилера: {{ request.comment }}</span>
      </p>

      <fieldset class="space-y-2">
        <legend class="text-sm font-medium text-gray-700 mb-1">Решение</legend>
        <label class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="status" type="radio" value="approved" class="text-blue-600" :disabled="ctx.busy.value" />
          Согласовать (сумма может отличаться от запрошенной)
        </label>
        <label v-if="request.status !== 'pre_approved'" class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="status" type="radio" value="pre_approved" class="text-blue-600" :disabled="ctx.busy.value" />
          Предварительно согласовать (цена пока не меняется)
        </label>
        <label class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="status" type="radio" value="cancelled" class="text-blue-600" :disabled="ctx.busy.value" />
          Отклонить
        </label>
      </fieldset>

      <FastDealCardField
        v-if="status === 'approved'"
        label="Согласованная сумма, ₽"
        required
        for-id="fast-deal-support-decided"
        :error="amountError"
      >
        <input
          id="fast-deal-support-decided"
          v-model="decidedAmount"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="input-field tabular-nums"
          :class="amountError ? 'border-red-500' : ''"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>

      <FastDealCardField
        :label="status === 'cancelled' ? 'Причина отказа' : 'Комментарий'"
        for-id="fast-deal-support-decision-comment"
        :error="commentError"
      >
        <textarea
          id="fast-deal-support-decision-comment"
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
      <button
        type="submit"
        form="fast-deal-support-decision-form"
        :class="status === 'cancelled' ? 'btn-danger' : 'btn-primary'"
        :disabled="ctx.busy.value"
        :aria-busy="ctx.busy.value"
      >
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить решение' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatMoney, isPositiveMoney, parseMoneyInput, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealVehicle, SupportRequest } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{ vehicle: FastDealVehicle; request: SupportRequest }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const status = ref<'approved' | 'pre_approved' | 'cancelled'>('approved')
const decidedAmount = ref(props.request.decided_amount ?? props.request.requested_amount)
const comment = ref('')
const localError = ref('')
const serverError = ref<ActionFailure | null>(null)

const amountError = computed(() =>
  localError.value || (serverError.value?.field === 'decided_amount' ? serverError.value.detail : ''),
)
const commentError = computed(() => (serverError.value?.field === 'comment' ? serverError.value.detail : ''))
const generalError = computed(() =>
  serverError.value && serverError.value.field !== 'decided_amount' && serverError.value.field !== 'comment' ? serverError.value : null,
)

async function submit() {
  serverError.value = null
  localError.value = ''
  const body: { status: 'cancelled' | 'pre_approved' | 'approved'; decided_amount?: string; comment?: string } = { status: status.value }
  if (status.value === 'approved') {
    const parsed = parseMoneyInput(decidedAmount.value)
    if (parsed === null || !isPositiveMoney(parsed)) {
      localError.value = 'Укажите положительную согласованную сумму'
      return
    }
    body.decided_amount = parsed
  }
  const text = comment.value.trim()
  if (text) body.comment = text
  const result = await ctx.run((etag) => ctx.api.decideSupport(props.request.id, etag, body))
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
