<template>
  <CommerceOrderPage item-type="special_equipment" />
</template>

<script setup lang="ts">
import CommerceOrderPage from '~/features/commerce/components/CommerceOrderPage.vue'

definePageMeta({ middleware: ['auth'] })
</script>
