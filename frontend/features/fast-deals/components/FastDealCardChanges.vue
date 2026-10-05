<template>
  <section v-if="visible" class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-changes-title">
    <h2 id="fast-deal-changes-title" class="text-lg font-semibold text-gray-900">{{ title }}</h2>
    <p class="mt-1 mb-4 text-sm text-gray-600">{{ description }}</p>

    <p v-if="!groups.length" class="text-sm text-gray-500">Изменений относительно отправленной версии нет.</p>
    <div v-else class="space-y-4">
      <section v-for="group in groups" :key="group.vehicleId" class="rounded-lg border border-gray-200">
        <h3 class="border-b border-gray-200 bg-gray-50 px-3 py-2 text-sm font-semibold text-gray-900">{{ group.title }}</h3>
        <table class="min-w-full text-sm">
          <thead class="text-left text-gray-500">
            <tr>
              <th scope="col" class="px-3 py-2 font-medium">Показатель</th>
              <th scope="col" class="px-3 py-2 font-medium">Было</th>
              <th scope="col" class="px-3 py-2 font-medium">Стало</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="line in group.lines" :key="line.field">
              <th scope="row" class="px-3 py-2 text-left font-normal text-gray-600">{{ line.label }}</th>
              <td class="px-3 py-2 text-gray-500 line-through decoration-gray-300 tabular-nums">{{ line.before }}</td>
              <td class="px-3 py-2 font-medium text-gray-900 tabular-nums">{{ line.after }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import { formatChangeValue, vehicleFieldLabel, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealCard, PendingChange } from '../types'

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()

/** DL only: the dealer's changes against the version the leasing company sent. */
const visible = computed(
  () => ctx.isDL.value && (
    props.deal.pending_changes.length > 0
    || props.deal.status === 'pending_lc_changes_confirmation'
    || (props.deal.party === 'dealer' && props.deal.status === 'pending_dealer_confirmation')
  ),
)

const title = computed(() => {
  if (props.deal.party === 'dealer') {
    return props.deal.status === 'pending_lc_changes_confirmation' ? 'Отправленные изменения' : 'Ваши изменения'
  }
  return 'Изменения дилера'
})

const description = computed(() => {
  const { party, status, has_pending_changes: pending } = props.deal
  if (party === 'dealer' && status === 'pending_dealer_confirmation') {
    return pending
      ? 'Сделку нельзя подтвердить без согласования изменений: отправьте их лизинговой компании. Принять изменения частично нельзя — решение принимается по всей сделке.'
      : 'Изменений нет: сделку можно подтвердить как есть либо изменить цену и разрешённые данные позиции.'
  }
  if (party === 'dealer') return 'Лизинговая компания принимает или отклоняет изменения целиком.'
  if (party === 'initiator') return 'Примите изменения целиком или отклоните их с указанием причины. Частичного принятия нет.'
  return ''
})

function valueText(field: string, value: unknown): string {
  if ((field === 'purposes' || field === 'regions') && Array.isArray(value)) {
    return value.length ? value.map(code => ctx.directoryLabel(field, String(code))).join(', ') : 'Не выбрано'
  }
  return formatChangeValue(field, value)
}

const groups = computed(() => {
  const order: string[] = []
  const byVehicle = new Map<string, PendingChange[]>()
  for (const change of props.deal.pending_changes) {
    if (!byVehicle.has(change.vehicle_id)) {
      byVehicle.set(change.vehicle_id, [])
      order.push(change.vehicle_id)
    }
    byVehicle.get(change.vehicle_id)?.push(change)
  }
  return order.map(vehicleId => {
    const changes = byVehicle.get(vehicleId) ?? []
    const vehicle = props.deal.vehicles.find(item => item.id === vehicleId)
    const vin = vehicle?.vin ?? changes[0]?.vin ?? ''
    return {
      vehicleId,
      title: [vehicle ? vehicleTitle(vehicle) : 'Позиция', vin ? `VIN ${vin}` : ''].filter(Boolean).join(' · '),
      lines: changes.map(change => ({
        field: change.field,
        label: vehicleFieldLabel(change.field),
        before: valueText(change.field, change.before),
        after: valueText(change.field, change.after),
      })),
    }
  })
})
</script>
