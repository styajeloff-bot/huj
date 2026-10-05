<template>
  <span v-if="regionLabels.length <= 1">
    {{ regionLabels[0] || emptyLabel }}
  </span>
  <span v-else>
    <template v-if="expanded">
      {{ regionLabels.join(', ') }}
      <button
        type="button"
        class="storefront-action-ghost ml-1 text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#3b82f6)] focus-visible:ring-offset-1 rounded"
        @click.prevent.stop="expanded = false"
      >
        Скрыть
      </button>
    </template>
    <template v-else>
      {{ regionLabels[0] }},
      <button
        type="button"
        class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#3b82f6)] focus-visible:ring-offset-1 rounded"
        @click.prevent.stop="expanded = true"
      >
        + ещё {{ hiddenCount }} {{ hiddenCountLabel }}
      </button>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getVehicleRegionLabels, type PurposeRegionVehicleLike } from '~/features/applications/utils/applicationVehicleDisplay'

const props = withDefaults(defineProps<{
  vehicle?: PurposeRegionVehicleLike | null
  regions?: unknown
  emptyLabel?: string
}>(), {
  vehicle: null,
  regions: undefined,
  emptyLabel: 'Не указано',
})

const expanded = ref(false)

const regionLabels = computed(() => {
  if (props.vehicle) return getVehicleRegionLabels(props.vehicle)
  return getVehicleRegionLabels({ regions: props.regions })
})

const hiddenCount = computed(() => Math.max(regionLabels.value.length - 1, 0))

const hiddenCountLabel = computed(() => {
  const count = hiddenCount.value
  const lastTwo = count % 100
  const lastOne = count % 10

  if (lastTwo >= 11 && lastTwo <= 14) return 'регионов'
  if (lastOne === 1) return 'регион'
  if (lastOne >= 2 && lastOne <= 4) return 'региона'
  return 'регионов'
})
</script>
