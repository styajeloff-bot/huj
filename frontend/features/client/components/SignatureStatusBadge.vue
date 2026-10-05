<template>
  <span
    :class="badgeConfig[status]?.classes || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]'"
    class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
  >
    {{ badgeConfig[status]?.label || status }}
  </span>
</template>

<script setup lang="ts">
import type { SignatureStatus } from '~/types/signature'

defineProps<{
  status: SignatureStatus
}>()

const badgeConfig: Record<SignatureStatus, { label: string; classes: string }> = {
  pending: {
    label: 'Ожидает подписи',
    classes: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]',
  },
  signed_electronic: {
    label: 'Подписано электронно',
    classes: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]',
  },
  signed_physical: {
    label: 'Подписано физически',
    classes: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]',
  },
  cancelled: {
    label: 'Отменено',
    classes: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#6b7280)]',
  },
  revoked: {
    label: 'Отозвано',
    classes: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)]',
  },
}
</script>
