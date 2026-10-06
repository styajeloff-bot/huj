<template>
  <div
    v-if="error && !dismissed"
    role="alert"
    class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
  >
    <p>{{ error.detail }}</p>
    <p v-if="error.vin" class="mt-1">
      VIN: <span class="font-mono font-medium">{{ error.vin }}</span>
    </p>
    <p v-if="error.sourceNumber" class="mt-1">
      Конкурирующая сделка: <span class="font-medium">{{ error.sourceNumber }}</span>
    </p>
    <button
      v-if="error.status === 412"
      type="button"
      class="mt-2 btn-outline text-sm px-3 py-1.5"
      :disabled="refreshing"
      @click="refresh"
    >
      {{ refreshing ? 'Обновляем…' : 'Обновить карточку' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'

const props = defineProps<{ error: ActionFailure | null | undefined }>()

const ctx = useFastDealCardContext()
const refreshing = ref(false)
const dismissed = ref(false)

// A new failure always shows again, even after the previous one was dismissed by a reload.
watch(() => props.error, () => {
  dismissed.value = false
})

async function refresh() {
  refreshing.value = true
  try {
    await ctx.reload()
    dismissed.value = true
  } finally {
    refreshing.value = false
  }
}
</script>
