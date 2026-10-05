<template>
  <section>
    <div class="heading"><div><h2>Запросы дополнительной комиссии</h2><p class="muted">Внутреннее согласование дилера с лизинговыми компаниями</p></div><button class="btn-secondary" :disabled="loading" @click="load">Обновить</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading" class="card empty" role="status">Загрузка…</div>
    <div v-else-if="!error" class="table-wrap"><table><thead><tr><th>Заявка</th><th>Дилер</th><th>Лизинговая компания</th><th>Комиссия</th><th>Статус</th><th>Действия</th></tr></thead><tbody>
      <tr v-for="item in items" :key="item.id"><td>{{ item.application_number || 'Без номера' }}</td><td>{{ item.dealer_company?.name || '—' }}</td><td>{{ item.leasing_company?.name || '—' }}</td><td>{{ formatRequestCommission(item) }}</td><td><span class="badge" :class="{ active: item.status === 'accepted', inactive: item.status === 'rejected' }">{{ statusLabels[item.status] }}</span></td><td><button class="link" @click="$emit('open', item.application_id)">Открыть обсуждение</button></td></tr>
    </tbody></table><p v-if="!items.length" class="empty">Запросов комиссии нет</p></div>
    <div v-if="total > 0 && !loading && !error" class="pagination"><span class="muted">Всего: {{ total }}</span><button class="btn-secondary" :disabled="page <= 1" @click="page--; load()">Назад</button><span>{{ page }} / {{ totalPages }}</span><button class="btn-secondary" :disabled="page >= totalPages" @click="page++; load()">Далее</button></div>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import type { ConditionRequest } from '../types'
import { formatRequestCommission } from '../commission'
const props = defineProps<{ api: MonetizationApi }>()
defineEmits<{ open: [id: string] }>()
const items = ref<ConditionRequest[]>([])
const loading = ref(false)
const error = ref('')
const page = ref(1)
const total = ref(0)
const totalPages = ref(1)
const statusLabels = { sent: 'Отправлен', accepted: 'Принят', rejected: 'Отклонён', countered: 'Встречное предложение' }
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true; error.value = ''
  try { const result = await props.api.requestsInbox({ page: page.value, page_size: 20 }); if (token === generation) { items.value = result.items; total.value = result.pagination.total; totalPages.value = Math.max(1, result.pagination.total_pages) } }
  catch (failure) { if (token === generation) error.value = errorMessage(failure) }
  finally { if (token === generation) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { ++generation })
</script>
