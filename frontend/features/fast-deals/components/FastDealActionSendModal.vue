<template>
  <Modal
    :show="true"
    title="Отправить в лизинговые компании"
    size="2xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <p class="text-sm text-gray-700">
        Выберите одну или несколько лизинговых компаний. Каждая даст одно коммерческое предложение или откажется;
        вы выберете одно из них, а выбранная компания окончательно подтвердит сделку.
      </p>
      <div v-if="!termsReady" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
        Условия лизинга не заполнены. Задайте аванс, срок и платёж, затем отправляйте сделку.
      </div>
      <div v-if="reservableCount > 0" class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
        При отправке будут зарезервированы единицы каталога: {{ reservableCount }}. Если хотя бы одну зарезервировать не удастся,
        отправка не произойдёт, а ошибка покажет VIN.
      </div>

      <FastDealCardField label="Лизинговые компании" required :error="localError">
        <FastDealCardCompanyPicker v-model="selectedIds" kind="leasing-companies" multiple :disabled="ctx.busy.value" />
      </FastDealCardField>

      <FastDealCardError :error="error" />
    </div>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="button" class="btn-primary" :disabled="ctx.busy.value || !termsReady" :aria-busy="ctx.busy.value" @click="submit">
        {{ ctx.busy.value ? 'Отправляем…' : `Отправить (${selectedIds.length})` }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { termsAreComplete } from '../composables/fastDealCardFormat'
import type { FastDealCard } from '../types'
import FastDealCardCompanyPicker from './FastDealCardCompanyPicker.vue'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{ deal: FastDealCard }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const selectedIds = ref<string[]>([])
const localError = ref('')
const error = ref<ActionFailure | null>(null)

const termsReady = computed(() => termsAreComplete(props.deal))
const reservableCount = computed(() => ctx.activeVehicles.value.filter(item => item.is_reservable === true).length)

watch(selectedIds, () => {
  localError.value = ''
})

async function submit() {
  error.value = null
  if (!selectedIds.value.length) {
    localError.value = 'Выберите хотя бы одну лизинговую компанию'
    return
  }
  const ids = [...selectedIds.value]
  const result = await ctx.run((etag, card) => ctx.api.sendToLeasingCompanies(card.id, etag, ids))
  if (result.ok) emit('close')
  else error.value = result.error
}
</script>
