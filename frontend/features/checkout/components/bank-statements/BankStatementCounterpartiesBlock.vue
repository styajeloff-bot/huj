<template>
  <div data-storefront-block="client.checkout" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
    <BankStatementCounterpartyTopList
      title="Топ клиентов (поступления)"
      :items="topClients"
    />
    <BankStatementCounterpartyTopList
      title="Топ поставщиков (списания)"
      :items="topSuppliers"
    />
  </div>
</template>

<script setup lang="ts">
import BankStatementCounterpartyTopList from './BankStatementCounterpartyTopList.vue'
import type { BankStatementCounterparty } from '../../types/bankStatementAnalytics'

defineProps<{
  topClients: BankStatementCounterparty[]
  topSuppliers: BankStatementCounterparty[]
}>()
</script>
