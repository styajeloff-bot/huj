<template>
  <section v-if="positions.length" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-4" aria-label="Дилеры заявки">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h3 class="font-semibold text-[color:var(--storefront-title,#111827)]">Дилеры заявки</h3>
      <button v-if="availablePositions.length" type="button" class="btn-primary text-sm" @click="assignmentOpen = true">
        Назначить дилера
      </button>
    </div>
    <ul class="grid gap-4 text-sm">
      <li v-for="group in groups" :key="group.dealer.id">
        <p class="font-medium text-[color:var(--storefront-text,#111827)]">{{ group.dealer.name }}</p>
        <p v-if="group.dealer.inn" class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН {{ group.dealer.inn }}</p>
        <ul class="mt-1 grid gap-1">
          <li v-for="item in group.items" :key="item.id" class="flex justify-between gap-4">
            <span class="min-w-0 break-words">{{ item.title }}</span>
            <span class="shrink-0 tabular-nums">{{ item.quantity }} шт.</span>
          </li>
        </ul>
      </li>
      <li v-if="unassigned.length">
        <p class="font-medium">Дилер не назначен</p>
        <ul class="mt-1 grid gap-1 text-[color:var(--storefront-text-muted,#6b7280)]">
          <li v-for="position in unassigned" :key="position.application_vehicle_id" class="flex justify-between gap-4">
            <span class="min-w-0 break-words">{{ position.title }}</span>
            <span class="shrink-0 tabular-nums">{{ position.unassigned_quantity }} шт.</span>
          </li>
        </ul>
      </li>
    </ul>
    <DealerAssignmentModal
      v-if="assignmentOpen"
      :application-id="applicationId"
      :positions="positions"
      @close="assignmentOpen = false"
      @assigned="onAssigned"
    />
  </section>
</template>

<script setup lang="ts">
import type { DealerDistributionPosition } from '../api/applicationsApi'
import { distributablePositions, groupDealerDistribution } from '../dealerDistribution'
import DealerAssignmentModal from './DealerAssignmentModal.vue'

const props = defineProps<{ applicationId: string; positions: DealerDistributionPosition[] }>()
const emit = defineEmits<{ updated: [] }>()
const assignmentOpen = ref(false)
const groups = computed(() => groupDealerDistribution(props.positions))
const availablePositions = computed(() => distributablePositions(props.positions))
const unassigned = computed(() => props.positions.filter(position => !position.stock_dealer && position.unassigned_quantity > 0))
const onAssigned = () => {
  assignmentOpen.value = false
  emit('updated')
}
</script>
