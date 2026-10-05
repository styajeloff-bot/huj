<template>
  <div v-if="visible" class="mb-6 rounded-lg border p-4"
    :class="status === 'failed'
      ? 'bg-red-50 border-red-200'
      : status === 'done'
        ? 'bg-green-50 border-green-200'
        : 'bg-blue-50 border-blue-200'">
    <!-- Header -->
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <svg v-if="uploading" class="animate-spin h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <svg v-else-if="status === 'done'" class="h-4 w-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <svg v-else-if="status === 'failed'" class="h-4 w-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span class="text-sm font-medium"
          :class="status === 'failed' ? 'text-red-900' : status === 'done' ? 'text-green-900' : 'text-blue-900'">
          {{ statusLabel }}
          <span v-if="filename" class="text-gray-500 font-normal">— {{ filename }}</span>
        </span>
      </div>
      <span class="text-sm text-gray-600">{{ progress }}%</span>
    </div>

    <!-- Progress bar -->
    <div class="w-full bg-gray-200 rounded-full h-2">
      <div class="h-2 rounded-full transition-all duration-300"
        :class="status === 'failed' ? 'bg-red-500' : status === 'done' ? 'bg-green-500' : 'bg-blue-600'"
        :style="{ width: progress + '%' }"></div>
    </div>

    <!-- Counters -->
    <div class="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs text-gray-600">
      <span v-if="rowsTotal > 0">Строк: {{ rowsDone }} / {{ rowsTotal }}</span>
      <span v-if="errorsCount > 0" class="text-red-600 font-medium">Ошибок: {{ errorsCount }}</span>
    </div>

    <!-- Final error message -->
    <p v-if="status === 'failed' && errorMessage" class="mt-2 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <!-- Expandable error sample -->
    <div v-if="errorSample && errorSample.length > 0" class="mt-3">
      <button
        type="button"
        class="text-xs font-medium text-red-700 hover:text-red-900 inline-flex items-center gap-1"
        @click="showErrors = !showErrors"
      >
        <svg class="w-3.5 h-3.5 transition-transform" :class="showErrors ? 'rotate-90' : ''"
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
        Показать ошибки ({{ errorSample.length }})
      </button>
      <ul v-if="showErrors" class="list-disc list-inside space-y-1 mt-2 text-xs text-red-700">
        <li v-for="(err, index) in errorSample" :key="index">{{ err }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ImportStatus } from '../composables/useCsvImport'

const props = defineProps<{
  uploading: boolean
  finished: boolean
  status: ImportStatus | null
  filename: string
  progress: number
  rowsTotal: number
  rowsDone: number
  errorsCount: number
  errorSample: string[]
  errorMessage: string
}>()

const showErrors = ref(false)

const visible = computed(() => props.uploading || props.finished)

const statusLabel = computed(() => {
  switch (props.status) {
    case 'queued': return 'В очереди...'
    case 'parsing': return 'Парсинг файла...'
    case 'ingesting': return 'Импорт данных...'
    case 'publishing': return 'Публикация в DWH...'
    case 'done': return 'Импорт завершён'
    case 'failed': return 'Ошибка импорта'
    default: return 'Загрузка...'
  }
})
</script>
