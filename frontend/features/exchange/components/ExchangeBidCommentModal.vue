<template>
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
    @click.self="$emit('close')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div>
            <h3 class="text-lg font-semibold text-gray-900">Комментарий к ставке</h3>
            <p class="text-xs text-gray-500">Виден дилеру этой ставки</p>
          </div>
        </div>
        <button
          @click="$emit('close')"
          class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-500"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <form @submit.prevent="handleSubmit" class="p-6 space-y-3">
        <textarea
          v-model="comment"
          rows="5"
          required
          autofocus
          class="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
          placeholder="Например: можете ли добавить подогрев сидений? Нужен ли доп. платёж?"
        />
        <div class="flex items-center justify-between text-xs text-gray-500">
          <span>{{ comment.length }} / 1000</span>
          <span v-if="comment.length > 1000" class="text-red-600">Слишком длинный</span>
        </div>
        <div v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-2.5">
          {{ error }}
        </div>
      </form>

      <!-- Footer -->
      <div class="flex justify-end gap-2 px-6 py-4 bg-gray-50 border-t border-gray-100">
        <button
          type="button"
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-white"
        >
          Отмена
        </button>
        <button
          type="button"
          @click="handleSubmit"
          :disabled="submitting || !comment.trim() || comment.length > 1000"
          class="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <svg v-if="submitting" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
          </svg>
          {{ submitting ? 'Отправка...' : 'Отправить' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import { useNotificationCompanyContext } from '~/features/notifications'
import type { ExchangeRequestId } from '../types'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  requestId: ExchangeRequestId
  bidId: UUID
}>()

const emit = defineEmits<{ close: []; submitted: [] }>()

const api = createExchangeApi(useRuntimeConfig(), useNotificationCompanyContext())
const comment = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)

async function handleSubmit() {
  const text = comment.value.trim()
  if (!text || text.length > 1000) return
  error.value = null
  submitting.value = true
  try {
    await api.commentOnBid(props.requestId, props.bidId, text)
    emit('submitted')
  } catch (e: any) {
    error.value = e?.data?.message || e?.message || 'Ошибка отправки'
  } finally {
    submitting.value = false
  }
}
</script>
