<template>
  <Modal
    :show="true"
    :title="title"
    :size="size"
    :show-footer="true"
    :closable="!busy"
    :close-on-overlay="!busy"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <p v-if="message" class="text-sm text-gray-700">{{ message }}</p>
      <div
        v-for="warning in warnings"
        :key="warning"
        class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
      >
        {{ warning }}
      </div>
      <slot />
      <FastDealCardField
        v-if="reasonLabel"
        :label="reasonLabel"
        :required="reasonRequired"
        :error="reasonError"
        :for-id="reasonId"
      >
        <textarea
          :id="reasonId"
          v-model="reason"
          rows="3"
          maxlength="2000"
          class="input-field"
          :class="reasonError ? 'border-red-500' : ''"
          :disabled="busy"
        />
      </FastDealCardField>
      <FastDealCardError :error="generalError" />
    </div>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="busy" @click="emit('close')">{{ cancelText }}</button>
      <button
        type="button"
        :class="danger ? 'btn-danger' : 'btn-primary'"
        :disabled="busy || confirmDisabled"
        :aria-busy="busy"
        @click="submit"
      >
        {{ busy ? 'Выполняем…' : confirmText }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import type { ActionFailure } from '../composables/useFastDealCard'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = withDefaults(defineProps<{
  title: string
  message?: string
  warnings?: string[]
  confirmText?: string
  cancelText?: string
  danger?: boolean
  /** When set, a reason textarea is shown. */
  reasonLabel?: string
  reasonRequired?: boolean
  /** Server field name that belongs to the textarea. */
  reasonField?: string
  busy?: boolean
  error?: ActionFailure | null
  confirmDisabled?: boolean
  size?: 'md' | 'lg' | 'xl' | '2xl'
}>(), {
  message: undefined,
  warnings: () => [],
  confirmText: 'Подтвердить',
  cancelText: 'Отмена',
  danger: false,
  reasonLabel: undefined,
  reasonRequired: false,
  reasonField: 'reason',
  busy: false,
  error: null,
  confirmDisabled: false,
  size: 'md',
})

const emit = defineEmits<{ confirm: [reason: string]; close: [] }>()

const reasonId = `fast-deal-reason-${useId()}`
const reason = ref('')
const localError = ref('')

watch(reason, () => {
  localError.value = ''
})

const reasonError = computed(() => {
  if (localError.value) return localError.value
  return props.error && props.error.field === props.reasonField ? props.error.detail : ''
})
const generalError = computed(() => (props.error && props.error.field !== props.reasonField ? props.error : null))

function submit() {
  const value = reason.value.trim()
  if (props.reasonLabel && props.reasonRequired && !value) {
    localError.value = 'Укажите причину'
    return
  }
  localError.value = ''
  emit('confirm', value)
}
</script>
