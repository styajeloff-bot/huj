<template>
  <Modal
    :show="true"
    title="Подтвердить сделку"
    :subtitle="deal.display_number"
    size="2xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <dl class="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
        <dt class="text-gray-500">Клиент</dt>
        <dd class="text-right text-gray-900">{{ deal.client.name }}</dd>
        <dt class="text-gray-500">Позиций</dt>
        <dd class="text-right text-gray-900">{{ ctx.activeVehicles.value.length }}</dd>
        <dt class="text-gray-500">Стоимость техники</dt>
        <dd class="text-right font-medium text-gray-900 tabular-nums">{{ formatMoney(deal.vehicles_total) }}</dd>
        <template v-if="terms.lease_term_months != null">
          <dt class="text-gray-500">Срок лизинга</dt>
          <dd class="text-right text-gray-900">{{ terms.lease_term_months }} мес.</dd>
          <dt class="text-gray-500">Аванс</dt>
          <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(terms.down_payment) }}</dd>
          <dt class="text-gray-500">Ежемесячный платёж</dt>
          <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(terms.monthly_payment) }}</dd>
          <dt class="text-gray-500">Стоимость договора</dt>
          <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(terms.total_cost) }}</dd>
        </template>
      </dl>

      <div class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        После подтверждения сделка станет неизменяемой: техника, цены, условия и файлы закрываются для правок.
        Зарезервированная техника каталога будет отмечена проданной.
      </div>

      <FastDealCardField
        label="Документы (необязательно)"
        for-id="fast-deal-confirm-files"
        :error="filesError"
        :hint="`До ${MAX_FILES} файлов, каждый не более 50 МБ. Документы необязательны для подтверждения.`"
      >
        <input
          id="fast-deal-confirm-files"
          type="file"
          multiple
          class="block w-full text-sm text-gray-700 file:mr-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-gray-200"
          :disabled="ctx.busy.value"
          @change="onFiles"
        />
      </FastDealCardField>
      <ul v-if="files.length" class="space-y-1 text-sm">
        <li v-for="(file, index) in files" :key="`${file.name}-${index}`" class="flex items-center justify-between gap-3">
          <span class="truncate">{{ file.name }} <span class="text-gray-400">· {{ formatFileSize(file.size) }}</span></span>
          <button type="button" class="text-red-600 hover:text-red-700 shrink-0" :disabled="ctx.busy.value" @click="files.splice(index, 1)">Убрать</button>
        </li>
      </ul>
      <p v-if="uploadedIds.length" class="text-sm text-green-700" role="status">Загружено файлов: {{ uploadedIds.length }}.</p>

      <FastDealCardError :error="error" />
    </div>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="button" class="btn-success" :disabled="ctx.busy.value" :aria-busy="ctx.busy.value" @click="submit">
        {{ ctx.busy.value ? 'Подтверждаем…' : 'Подтвердить сделку' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatFileSize, formatMoney } from '../composables/fastDealCardFormat'
import type { FastDealCard } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const MAX_FILES = 20
const MAX_BYTES = 50 * 1024 * 1024

const props = defineProps<{
  deal: FastDealCard
  /** `leasing`: the selected leasing company of a DD; `dealer`: the dealer of a DL. */
  mode: 'leasing' | 'dealer'
}>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const files = ref<File[]>([])
const uploadedIds = ref<string[]>([])
const filesError = ref('')
const error = ref<ActionFailure | null>(null)

/** The terms about to be confirmed: the chosen offer of a DD, the requested terms of a DL. */
const terms = computed(() => {
  const offer = props.mode === 'leasing' ? ctx.ownApplication.value?.offer : null
  if (offer) {
    return {
      lease_term_months: offer.lease_term_months,
      down_payment: offer.down_payment,
      monthly_payment: offer.monthly_payment,
      total_cost: offer.total_cost,
    }
  }
  return props.deal.requested_terms
})

function onFiles(event: Event) {
  const input = event.target as HTMLInputElement
  files.value = [...files.value, ...Array.from(input.files ?? [])]
  input.value = ''
  filesError.value = ''
}

function validateFiles(): boolean {
  if (files.value.length > MAX_FILES) filesError.value = `За один раз можно загрузить не более ${MAX_FILES} файлов`
  else if (files.value.some(file => file.size === 0)) filesError.value = 'Пустые файлы не принимаются'
  else if (files.value.some(file => file.size > MAX_BYTES)) filesError.value = 'Размер файла не должен превышать 50 МБ'
  else filesError.value = ''
  return !filesError.value
}

async function submit() {
  error.value = null
  if (!validateFiles()) return

  // Documents go first and stay attached across retries: a refused confirmation must not re-upload them.
  if (files.value.length) {
    const selected = [...files.value]
    // A leasing company addresses the dealer (the server derives it); the dealer's documents are «основные».
    const kind = props.mode === 'leasing' ? 'deal_additional' : 'deal_main'
    const uploaded = await ctx.run((etag, card) => ctx.api.uploadFiles(card.id, etag, { kind, files: selected }))
    if (!uploaded.ok) {
      error.value = uploaded.error
      return
    }
    uploadedIds.value = [...uploadedIds.value, ...uploaded.value.files.map(file => file.id)]
    files.value = []
  }

  const ids = [...uploadedIds.value]
  const application = ctx.ownApplication.value
  if (props.mode === 'leasing' && !application) {
    error.value = { detail: 'Приглашение вашей компании не найдено' }
    return
  }
  const result = await ctx.run((etag, card) =>
    props.mode === 'leasing' && application
      ? ctx.api.confirmAsLeasing(application.id, etag, ids)
      : ctx.api.confirmAsDealer(card.id, etag, ids),
  )
  if (result.ok) emit('close')
  else error.value = result.error
}
</script>
