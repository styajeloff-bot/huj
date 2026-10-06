<template>
  <span
    data-testid="fast-deal-status"
    class="inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="fastDealStatusClass(status)"
  >
    {{ fastDealStatusLabel(status) }}
  </span>
</template>

<script setup lang="ts">
import { fastDealStatusClass, fastDealStatusLabel } from '~/features/fast-deals/status'

/** Status pill of the fast deal dictionary (own labels and colors, never ordinary application statuses). */
defineProps<{ status?: string | null }>()
</script>
