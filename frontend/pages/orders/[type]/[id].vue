<template>
  <CommerceOrderPage />
</template>

<script setup lang="ts">
import CommerceOrderPage from '~/features/commerce/components/CommerceOrderPage.vue'

definePageMeta({ middleware: ['auth'] })
</script>
