<template>
  <div class="dash-grid">
    <!-- Table 1: Заявки в ДЦ -->
    <WidgetCard title="Заявки в ДЦ" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Месяц</th>
              <th class="text-left py-2 px-3">ДЦ</th>
              <th class="text-right py-2 px-3">Новых заявок</th>
              <th class="text-right py-2 px-3">Новых клиентов</th>
              <th class="text-right py-2 px-3">Одобренных заявок</th>
              <th class="text-right py-2 px-3">Одобренных клиентов</th>
              <th class="text-right py-2 px-3">Профинансированных заявок</th>
              <th class="text-right py-2 px-3">Профинансированных клиентов</th>
              <th class="text-right py-2 px-3">Уровень одобрения</th>
              <th class="text-right py-2 px-3">Уровень финансирования</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in applicationsItems" :key="`${item.month}-${item.dealer_name}`" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.month }}</td>
              <td class="py-2 px-3">{{ item.dealer_name }}</td>
              <td class="py-2 px-3 text-right">{{ item.new_applications }}</td>
              <td class="py-2 px-3 text-right">{{ item.new_clients }}</td>
              <td class="py-2 px-3 text-right">{{ item.approved_applications }}</td>
              <td class="py-2 px-3 text-right">{{ item.approved_clients }}</td>
              <td class="py-2 px-3 text-right">{{ item.financed_applications }}</td>
              <td class="py-2 px-3 text-right">{{ item.financed_clients }}</td>
              <td class="py-2 px-3 text-right">{{ item.approval_rate.toFixed(2) }}%</td>
              <td class="py-2 px-3 text-right">{{ item.financing_rate.toFixed(2) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="applicationsPagination"
        :total="applicationsPagination.total"
        :limit="applicationsPagination.limit"
        :offset="(applicationsPagination.page - 1) * applicationsPagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>

    <!-- Table 2: Продажи в ДЦ -->
    <WidgetCard title="Продажи в ДЦ" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Месяц</th>
              <th class="text-left py-2 px-3">ДЦ</th>
              <th class="text-right py-2 px-3">Средняя стоимость авто</th>
              <th class="text-right py-2 px-3">Средняя цена договора</th>
              <th class="text-right py-2 px-3">Средний Аванс, %</th>
              <th class="text-right py-2 px-3">Средний Аванс, руб.</th>
              <th class="text-right py-2 px-3">Средний срок</th>
              <th class="text-right py-2 px-3">Средняя ставка</th>
              <th class="text-right py-2 px-3">Стоимость доп продуктов, руб.</th>
              <th class="text-right py-2 px-3">Стоимость доп продуктов, %</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in salesItems" :key="`${item.month}-${item.dealer_name}`" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.month }}</td>
              <td class="py-2 px-3">{{ item.dealer_name }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.avg_vehicle_cost) }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.avg_contract_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ item.avg_down_payment_percent.toFixed(2) }}%</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.avg_down_payment_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ item.avg_lease_term }}</td>
              <td class="py-2 px-3 text-right">{{ item.avg_rate.toFixed(2) }}%</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.accessories_total) }}</td>
              <td class="py-2 px-3 text-right">{{ item.accessories_percent.toFixed(2) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="salesPagination"
        :total="salesPagination.total"
        :limit="salesPagination.limit"
        :offset="(salesPagination.page - 1) * salesPagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SalesDcTabResponse } from '../../api/analytics'
import { getWidgetTable, getWidgetPagination } from '../../api/analytics'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: SalesDcTabResponse | null
  loading: boolean
}>()

const { formatPrice: formatSharedPrice } = useFormatPrice()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const applicationsItems = computed(() =>
  getWidgetTable<{
    month: string
    dealer_name: string
    new_applications: number
    new_clients: number
    approved_applications: number
    approved_clients: number
    financed_applications: number
    financed_clients: number
    approval_rate: number
    financing_rate: number
  }>(props.data?.widgets || {}, 'W-SDC-01'),
)

const applicationsPagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-SDC-01'))

const salesItems = computed(() =>
  getWidgetTable<{
    month: string
    dealer_name: string
    avg_vehicle_cost: number
    avg_contract_amount: number
    avg_down_payment_percent: number
    avg_down_payment_amount: number
    avg_lease_term: number
    avg_rate: number
    accessories_total: number
    accessories_percent: number
  }>(props.data?.widgets || {}, 'W-SDC-02'),
)

const salesPagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-SDC-02'))

function formatPrice(v: number) {
  if (!v) return '—'
  return formatSharedPrice(v)
}
</script>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
  align-items: start;
}

.chart-wide {
  grid-column: span 12;
}
</style>
