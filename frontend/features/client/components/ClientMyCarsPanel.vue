<template>
  <CommerceOrdersPanel :has-companies="userCompanies.length > 0" />
</template>

<script setup lang="ts">
import CommerceOrdersPanel from '~/features/commerce/components/CommerceOrdersPanel.vue'

withDefaults(defineProps<{
  userCompanies?: unknown[]
}>(), {
  userCompanies: () => [],
})
</script>
