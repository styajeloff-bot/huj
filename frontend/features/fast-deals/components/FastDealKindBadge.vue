<template>
  <span
    data-testid="fast-deal-kind-badge"
    class="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-800"
  >
    <BoltIcon class="h-3.5 w-3.5" aria-hidden="true" />
    {{ FAST_DEAL_KIND_LABEL }}
  </span>
</template>

<script setup lang="ts">
import { BoltIcon } from '@heroicons/vue/24/outline'
import { FAST_DEAL_KIND_LABEL } from '~/features/fast-deals/mergedList'
</script>
