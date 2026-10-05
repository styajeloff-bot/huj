<template><CalculatorRatesAdminPanel /></template>
<script setup lang="ts">
const CalculatorRatesAdminPanel = defineAsyncComponent(() => import('~/features/admin/calculator-rates/components/CalculatorRatesAdminPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
