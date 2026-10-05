<template>
  <CommercePurchaseModal
    :show="show"
    :items="itemRefs"
    @close="emit('close')"
    @success="emit('success')"
  />
</template>

<script setup lang="ts">
import CommercePurchaseModal from '~/features/commerce/components/CommercePurchaseModal.vue'
import type { CommercePurchaseSelection } from '~/features/commerce/types'
import type { PurchaseVehicleItem } from '~/types/domains'

const props = withDefaults(defineProps<{
  show?: boolean
  vehicles: PurchaseVehicleItem[]
}>(), {
  show: false,
})

const emit = defineEmits<{
  close: []
  success: []
}>()

const itemRefs = computed<CommercePurchaseSelection[]>(() => props.vehicles.map((vehicle) => ({
  item: { type: 'vehicle', id: vehicle.vehicle_id },
  quantity: vehicle.quantity,
})))
</script>
