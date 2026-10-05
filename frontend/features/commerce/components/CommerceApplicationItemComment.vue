<template>
  <div v-if="comment?.trim()" class="mt-2 min-w-0 text-sm text-[color:var(--storefront-text,#374151)]">
    <p class="font-medium">Комментарий клиента</p>
    <p class="whitespace-pre-wrap [overflow-wrap:anywhere]">{{ comment }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ comment?: string | null }>()
</script>
