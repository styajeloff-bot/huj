<template>
  <section class="monetization">
    <div class="card">
      <div class="heading"><div><h2>Дополнительная комиссия</h2><p class="muted">Внутреннее согласование комиссии с лизинговой компанией</p></div><button class="btn-secondary" :disabled="busy" @click="load">Обновить</button></div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <form v-if="role === 'dealer' && allowedToRequest" @submit.prevent="send">
        <CompanyPicker v-model="selected" :api="api" kind="leasing" label="Лизинговая компания" />
        <div class="actions" style="margin:12px 0"><button type="button" class="btn-secondary" :disabled="!selected" @click="addCompany">Добавить адресата</button><span v-for="company in recipients" :key="company.id" class="badge">{{ company.name }} <button type="button" :aria-label="'Удалить ' + company.name" @click="recipients = recipients.filter(item => item.id !== company.id)">×</button></span></div>
        <div class="fields"><label><span>Тип комиссии</span><select class="select-field" v-model="calcType"><option value="percent">Процент</option><option value="amount">Фиксированная сумма</option></select></label><label><span>{{ calcType === 'percent' ? 'Процент, %' : 'Сумма, ₽' }}</span><input class="input-field" v-model="value" inputmode="decimal" required /></label></div>
        <button class="btn-primary" style="margin-top:16px" :disabled="busy || !recipients.length">Отправить запрос</button>
      </form>
      <p v-else-if="loaded && !error && !canNegotiate" class="notice">Доступен только просмотр комиссии.</p>
      <p v-else-if="role === 'dealer' && loaded && !error" class="notice">Запрос комиссии доступен до направления заявки в первую лизинговую компанию.</p>
      <p v-if="loading" class="empty" role="status">Загрузка…</p>
      <p v-else-if="!requests.length" class="empty">Запросов комиссии нет</p>
      <article v-for="item in requests" :key="item.id" class="row-editor">
        <div class="heading"><div><strong>{{ role === 'leasing_company' ? item.dealer_company?.name || 'Дилер' : item.leasing_company?.name || 'ЛК' }}</strong><p class="muted">ИНН {{ role === 'leasing_company' ? item.dealer_company?.inn || '—' : item.leasing_company?.inn || '—' }}</p></div><span class="badge" :class="{ active: item.status === 'accepted', inactive: item.status === 'rejected' }">{{ statusLabels[item.status] }}</span></div>
        <p v-if="item.status === 'accepted'">Согласовано: <strong>{{ formatRequestCommission(item) }}</strong></p>
        <p>Запрошено: <strong>{{ commission(item.requested_value, item.requested_calc_type) }}</strong></p>
        <p v-if="item.counter_value && item.counter_calc_type">Предложение ЛК: <strong>{{ commission(item.counter_value, item.counter_calc_type) }}</strong></p>
        <div v-if="canNegotiate && role === 'leasing_company' && item.status === 'sent'" style="margin-top:16px">
          <div class="actions"><button class="btn-primary" :disabled="busy" @click="respond(item.id, 'accepted')">Принять</button><button class="btn-secondary" :disabled="busy" @click="respond(item.id, 'rejected')">Отклонить</button><button class="btn-secondary" :disabled="busy" @click="counterId = item.id">Предложить условия</button></div>
          <form v-if="counterId === item.id" style="margin-top:16px" @submit.prevent="respond(item.id, 'countered')"><div class="fields"><label><span>Тип комиссии</span><select class="select-field" v-model="counterCalcType"><option value="percent">Процент</option><option value="amount">Сумма</option></select></label><label><span>Значение</span><input class="input-field" v-model="counterValue" inputmode="decimal" required /></label></div><button class="btn-primary" style="margin-top:12px" :disabled="busy">Отправить предложение</button></form>
        </div>
        <div v-if="canNegotiate && role === 'dealer' && item.status === 'countered'" class="actions" style="margin-top:16px"><button class="btn-primary" :disabled="busy" @click="decide(item.id, 'accept_counter')">Принять предложение ЛК</button><button class="btn-secondary" :disabled="busy" @click="decide(item.id, 'reject')">Отклонить</button></div>
      </article>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Company, ConditionRequest } from '../types'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import { formatMoney, formatPercent } from '../money'
import { formatRequestCommission } from '../commission'
import CompanyPicker from './CompanyPicker.vue'
import '../monetization.css'
const props = withDefaults(defineProps<{ api: MonetizationApi; applicationId: string; role: 'dealer' | 'leasing_company'; canRequest?: boolean }>(), { canRequest: true })
const serverCanRequest = ref(false)
const canNegotiate = ref(false)
const loaded = ref(false)
const allowedToRequest = computed(() => serverCanRequest.value && canNegotiate.value && props.canRequest !== false)
const selected = ref<Company | null>(null)
const recipients = ref<Company[]>([])
const requests = ref<ConditionRequest[]>([])
const calcType = ref<'percent' | 'amount'>('percent')
const value = ref('')
const counterId = ref<string | null>(null)
const counterCalcType = ref<'percent' | 'amount'>('percent')
const counterValue = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const statusLabels = { sent: 'Отправлен', accepted: 'Принят', rejected: 'Отклонён', countered: 'Встречное предложение' }
const commission = (amount: string, type: 'percent' | 'amount') => type === 'percent' ? formatPercent(amount) : formatMoney(amount)
function addCompany() { if (selected.value && !recipients.value.some(company => company.id === selected.value?.id)) recipients.value.push(selected.value); selected.value = null }
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true; error.value = ''; serverCanRequest.value = false; canNegotiate.value = false; counterId.value = null
  try { const result = await props.api.requests(props.applicationId); if (token === generation) { requests.value = result.items; serverCanRequest.value = result.can_request; canNegotiate.value = result.can_negotiate; loaded.value = true } } catch (failure) { if (token === generation) error.value = errorMessage(failure) } finally { if (token === generation) loading.value = false }
}
async function act(operation: () => Promise<unknown>) {
  if (busy.value || !canNegotiate.value) return
  busy.value = true; error.value = ''
  try { await operation(); await load() } catch (failure) { error.value = errorMessage(failure) } finally { busy.value = false }
}
const validValue = (amount: string) => /^\d+(\.\d+)?$/.test(amount) && /[1-9]/.test(amount)
async function send() {
  if (!allowedToRequest.value) return
  const amount = value.value.replace(',', '.')
  if (!validValue(amount)) { error.value = 'Укажите положительное значение комиссии'; return }
  await act(async () => { await props.api.requestCommission(props.applicationId, { leasing_company_ids: recipients.value.map(company => company.id), calc_type: calcType.value, value: amount }); recipients.value = []; value.value = '' })
}
async function respond(id: string, decision: 'accepted' | 'rejected' | 'countered') {
  const amount = counterValue.value.replace(',', '.')
  if (decision === 'countered' && !validValue(amount)) { error.value = 'Укажите положительное значение комиссии'; return }
  await act(async () => { await props.api.respond(id, { decision, ...(decision === 'countered' ? { counter_calc_type: counterCalcType.value, counter_value: amount } : {}) }); counterId.value = null })
}
const decide = (id: string, decision: 'accept_counter' | 'reject') => act(() => props.api.decide(id, decision))
watch(() => props.applicationId, () => { requests.value = []; serverCanRequest.value = false; canNegotiate.value = false; loaded.value = false; recipients.value = []; selected.value = null; void load() })
onMounted(load)
onBeforeUnmount(() => { ++generation })
</script>
