<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-client-title">
    <h2 id="fast-deal-client-title" class="text-lg font-semibold text-gray-900 mb-4">Клиент и стороны</h2>
    <dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm">
      <div>
        <dt class="text-gray-500">Компания клиента</dt>
        <dd class="font-medium text-gray-900">{{ deal.client.name }}</dd>
      </div>
      <div>
        <dt class="text-gray-500">ИНН</dt>
        <dd class="font-mono text-gray-900">{{ deal.client.inn || '—' }}</dd>
      </div>
      <div v-if="deal.client.kpp">
        <dt class="text-gray-500">КПП</dt>
        <dd class="font-mono text-gray-900">{{ deal.client.kpp }}</dd>
      </div>
      <div>
        <dt class="text-gray-500">Телефон клиента</dt>
        <dd class="text-gray-900">{{ deal.client_phone || '—' }}</dd>
      </div>
      <div>
        <dt class="text-gray-500">{{ initiatorRole }}</dt>
        <dd class="text-gray-900">{{ deal.initiator_company.name }}</dd>
      </div>
      <div v-if="counterparty">
        <dt class="text-gray-500">{{ counterparty.role }}</dt>
        <dd class="text-gray-900">{{ counterparty.name }}</dd>
      </div>
    </dl>
    <p class="mt-4 text-xs text-gray-500">
      Клиент не получает доступ к сделке, SMS или приглашение. Выбранного клиента после создания изменить нельзя.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FastDealCard } from '../types'

const props = defineProps<{ deal: FastDealCard }>()

const isDD = computed(() => props.deal.source_type === 'dealer_to_leasing')
const initiatorRole = computed(() => (isDD.value ? 'Дилер (инициатор)' : 'Лизинговая компания (инициатор)'))

/** The other side: the chosen leasing company (DD, after selection) or the dealer of this part (DL). */
const counterparty = computed(() => {
  const deal = props.deal
  if (isDD.value) {
    if (deal.leasing_company) return { role: 'Выбранная лизинговая компания', name: deal.leasing_company.name }
    const invited = deal.lc_applications.length
    return invited > 0 && deal.party === 'initiator'
      ? { role: 'Приглашены лизинговые компании', name: String(invited) }
      : null
  }
  return deal.dealer_company ? { role: 'Дилер', name: deal.dealer_company.name } : null
})
</script>
