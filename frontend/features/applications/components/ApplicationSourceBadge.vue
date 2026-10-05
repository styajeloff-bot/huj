<template>
  <span
    v-if="presentation"
    data-testid="application-source"
    class="inline-flex items-center gap-1.5 text-sm text-[color:var(--storefront-text-muted,#4b5563)]"
  >
    <svg aria-hidden="true" class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <template v-if="presentation.icon === 'platform'">
        <circle cx="12" cy="12" r="9" stroke-width="1.5" />
        <path d="M3 12h18M12 3c4 4 4 14 0 18M12 3c-4 4-4 14 0 18" stroke-width="1.5" />
      </template>
      <path v-else-if="presentation.icon === 'dealer'" d="M4 10v11h16V10M3 10l2-7h14l2 7M8 21v-7h8v7M3 10h18" stroke-width="1.5" stroke-linejoin="round" />
      <path v-else d="M3 21V9l9-6 9 6v12H3Zm4 0V11h10v10M7 15h10M7 18h10" stroke-width="1.5" stroke-linejoin="round" />
    </svg>
    {{ presentation.label }}
  </span>
</template>

<script setup lang="ts">
import { applicationSourcePresentation, type ApplicationSourceType } from '../sourceType'

const props = defineProps<{ source?: ApplicationSourceType | null }>()
const presentation = computed(() => applicationSourcePresentation(props.source))
</script>
