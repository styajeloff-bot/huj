<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-assignees-title">
    <div class="flex items-center justify-between gap-3 mb-4">
      <h2 id="fast-deal-assignees-title" class="text-lg font-semibold text-gray-900">Ответственные</h2>
      <button v-if="ctx.can('assign_employees')" type="button" class="btn-outline text-sm px-3 py-1.5" @click="editing = true">
        Назначить
      </button>
    </div>

    <p v-if="!rows.length" class="text-sm text-gray-500">
      Ответственные не назначены: сделка доступна администраторам компаний-участников.
    </p>
    <dl v-else class="space-y-4 text-sm">
      <div v-for="row in rows" :key="row.companyId">
        <dt class="font-medium text-gray-900">
          {{ ctx.companyName(row.companyId) || 'Компания' }}
          <span v-if="row.companyId === ctx.partyCompanyId.value" class="text-xs font-normal text-gray-500">(ваша сторона)</span>
        </dt>
        <dd class="mt-1 text-gray-700">
          <p>Основной: {{ row.primary || 'не назначен' }}</p>
          <p>Дополнительный: {{ row.additional || 'не назначен' }}</p>
        </dd>
      </div>
    </dl>

    <FastDealAssigneesModal v-if="editing" :deal="deal" @close="editing = false" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import type { FastDealCard } from '../types'
import FastDealAssigneesModal from './FastDealAssigneesModal.vue'

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const editing = ref(false)

const rows = computed(() => {
  const order: string[] = []
  for (const item of props.deal.assignees) {
    if (!order.includes(item.company_id)) order.push(item.company_id)
  }
  return order.map(companyId => {
    const own = props.deal.assignees.filter(item => item.company_id === companyId)
    return {
      companyId,
      primary: own.find(item => item.role === 'primary')?.user_name ?? '',
      additional: own.find(item => item.role === 'additional')?.user_name ?? '',
    }
  })
})
</script>
