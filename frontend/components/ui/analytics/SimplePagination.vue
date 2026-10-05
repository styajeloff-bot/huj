<template>
  <div class="flex justify-between items-center mt-4">
    <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
      {{ offset + 1 }} – {{ Math.min(offset + limit, total) }} из {{ total }}
    </span>
    <div class="flex gap-2">
      <button
        class="storefront-action-secondary px-3 py-1 rounded border text-sm disabled:opacity-50"
        :disabled="offset === 0"
        @click="emit('change', offset - limit)"
      >
        Назад
      </button>
      <button
        class="storefront-action-secondary px-3 py-1 rounded border text-sm disabled:opacity-50"
        :disabled="offset + limit >= total"
        @click="emit('change', offset + limit)"
      >
        Вперёд
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  total: number
  limit: number
  offset: number
}>()

const emit = defineEmits<{
  change: [offset: number]
}>()
</script>
