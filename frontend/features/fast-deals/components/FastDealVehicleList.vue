<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-vehicles-title">
    <div class="flex items-center justify-between gap-3 flex-wrap mb-4">
      <div>
        <h2 id="fast-deal-vehicles-title" class="text-lg font-semibold text-gray-900">Техника</h2>
        <p class="text-sm text-gray-500">
          Позиций: {{ ctx.activeVehicles.value.length }} · стоимость <span class="tabular-nums">{{ formatMoney(deal.vehicles_total) }}</span>
        </p>
      </div>
      <button v-if="ctx.canEditStructure.value" type="button" class="btn-primary text-sm" @click="addOpen = true">
        Добавить технику
      </button>
    </div>

    <div v-if="!ctx.activeVehicles.value.length" class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-600">
      <p>В сделке пока нет техники.</p>
      <p v-if="ctx.canEditStructure.value" class="mt-1">Найдите единицу по VIN, выберите из таблицы или добавьте вручную.</p>
    </div>
    <div v-else class="space-y-4">
      <FastDealVehicleCard v-for="vehicle in ctx.activeVehicles.value" :key="vehicle.id" :deal="deal" :vehicle="vehicle" />
    </div>

    <div v-if="ctx.inactiveVehicles.value.length" class="mt-4">
      <button
        type="button"
        class="text-sm text-gray-600 hover:text-gray-900"
        :aria-expanded="showInactive"
        @click="showInactive = !showInactive"
      >
        {{ showInactive ? 'Скрыть' : 'Показать' }} удалённые и замещённые позиции ({{ ctx.inactiveVehicles.value.length }})
      </button>
      <ul v-if="showInactive" class="mt-2 divide-y divide-gray-100 rounded-lg border border-gray-200 text-sm">
        <li v-for="vehicle in ctx.inactiveVehicles.value" :key="vehicle.id" class="flex items-center justify-between gap-3 px-3 py-2 text-gray-500">
          <span class="min-w-0 truncate">
            {{ vehicleTitle(vehicle) }} · <span class="font-mono">{{ vehicle.vin }}</span>
          </span>
          <span class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs">
            {{ vehicle.item_status === 'replaced' ? 'Заменена' : 'Удалена' }}
          </span>
        </li>
      </ul>
    </div>

    <FastDealVehicleAddModal v-if="addOpen" :deal="deal" @close="addOpen = false" />
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import { formatMoney, lookupName, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealCard } from '../types'
import FastDealVehicleAddModal from './FastDealVehicleAddModal.vue'
import FastDealVehicleCard from './FastDealVehicleCard.vue'

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const addOpen = ref(false)
const showInactive = ref(false)

// DL before the split: positions of several dealers sit in one draft, so the dealer names are looked up once.
onMounted(async () => {
  if (ctx.isDD.value || ctx.party.value !== 'initiator' || props.deal.dealer_company) return
  const unknown = ctx.activeVehicles.value.some(item => item.dealer_company_id && !ctx.companyName(item.dealer_company_id))
  if (!unknown) return
  try {
    const response = await ctx.api.lookup('dealers')
    for (const item of response.items) ctx.rememberCompany(String(item.id), lookupName(item))
  } catch {
    // The positions stay usable without the names.
  }
})
</script>
