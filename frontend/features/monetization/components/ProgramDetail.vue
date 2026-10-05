<template>
  <div class="program-detail">
    <nav class="program-breadcrumb" aria-label="Путь к условиям"><button type="button" class="link" @click="$emit('close')">Условия монетизации</button><span aria-hidden="true">/</span><span>{{ current.name }}</span></nav>
    <div class="heading"><div><h2>{{ current.name }}</h2><p><span class="badge" :class="current.status">{{ current.status === 'active' ? 'Активна' : 'Неактивна' }}</span></p></div><div class="actions"><button v-if="canManage" class="btn-secondary" :disabled="busy" @click="toggleStatus">{{ current.status === 'active' ? 'Деактивировать' : 'Активировать' }}</button></div></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <section class="card"><h3 class="detail-section-title">Участники, заданные на уровне условий</h3><dl class="details">
      <div><dt>Лизинговая компания</dt><dd>{{ current.leasing_company?.name || '—' }}<small v-if="current.leasing_company?.inn" class="muted"><br />ИНН {{ current.leasing_company?.inn }}</small></dd></div>
      <div><dt>Дилер</dt><dd>{{ current.dealer?.name || 'Все дилеры' }}</dd></div>
      <div><dt>Дистрибьютор</dt><dd>{{ current.distributor?.name || 'Все дистрибьюторы' }}</dd></div>
    </dl></section>
    <section class="card"><h3 class="detail-section-title">Область действия и срок</h3><dl class="details">
      <div><dt>Программа стимулирования</dt><dd>{{ current.support_program?.name || 'Не выбрана' }}</dd></div>
      <div><dt>Период действия</dt><dd>{{ formatDate(current.period_start) }} → {{ current.period_end ? formatDate(current.period_end) : 'бессрочно' }}</dd></div>
      <div><dt>Марка / модель / модификация / комплектация / VIN</dt><dd>{{ [current.brand, current.model, current.modification, current.trim].filter(Boolean).join(' / ') || 'Все автомобили' }}<p v-if="current.vin">VIN {{ current.vin }}</p></dd></div>
    </dl>
      <div v-if="current.support_program" class="support-details">
        <div><h4>Документы программы стимулирования (только просмотр)</h4><FileList :files="current.support_program.documents" :api="api" /><p v-if="!current.support_program.documents.length" class="muted">Документы не добавлены</p></div>
        <div><h4>Совместимые программы (справочно)</h4><div class="actions"><span v-for="item in current.support_program.compatible_programs" :key="item.id" class="badge">{{ item.name }}</span><span v-if="!current.support_program.compatible_programs.length" class="muted">Совместимость не задана</span></div></div>
      </div>
    </section>
    <h3>Источники заявки и расчёт</h3>
    <p class="program-intro">По каждому источнику — кто несёт расход и кто получает доход. Фактические расчёты по сделкам — в карточке сделки.</p>
    <section v-for="block in sources" :key="block.id" class="card">
      <span class="source-badge">{{ sourceLabel(block.source_type) }}</span>
      <p class="muted summary-visibility">Каждый участник видит свои условия расхода и дохода.</p>
      <section v-for="(group, index) in block.groups" :key="group.id" class="calculation-group" :aria-label="group.label">
        <template v-if="group.expense">
          <h4 class="summary-heading">Расход {{ index + 1 }}</h4>
          <ConditionRowSummary :row="group.expense" />
        </template>
        <div :class="{ 'linked-incomes': group.expense }">
          <h4 class="summary-heading">{{ group.expense ? 'Связанные доходы' : group.label }}</h4>
          <div class="condition-columns"><ConditionRowSummary v-for="income in group.incomes" :key="income.id" :row="income" income :base-label="incomeBase(income, group.expense, index)" /></div>
          <p v-if="!group.incomes.length" class="muted">Нет доступных доходов</p>
        </div>
      </section>
      <p v-if="!block.groups.length" class="muted">Нет доступных расходов и доходов</p>
    </section>
    <section class="card"><DocumentRegistryPicker :program-id="current.id" :can-manage="canManage" :preset="documentParticipants" :catalog-names="{ mark: current.brand, model: current.model }" /></section>
    <h3 class="contracts-heading">Ранее приложенные договоры</h3>
    <section class="card"><FileList :files="current.contracts" :api="api" /><p v-if="!current.contracts.length" class="muted">Договоры не добавлены</p>

    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import type { SavedConditionRow, Program } from '../types'
import { participantLabels, sourceLabel } from '../editor'
import { groupIncomes } from '../grouping'
import FileList from './FileList.vue'
import { DocumentRegistryPicker, type Participants } from '~/features/documentRegistry'
import ConditionRowSummary from './ConditionRowSummary.vue'
const props = defineProps<{ api: MonetizationApi; program: Program; admin: boolean }>()
defineEmits<{ close: [] }>()
const current = ref(props.program)
const canManage = computed(() => props.admin && current.value.can_manage)
const sources = computed(() => current.value.sources.map(block => ({ ...block, groups: groupIncomes(block.expenses, block.incomes, row => row.local_id, row => row.expense_ref) })))
const documentParticipants = computed<Participants>(() => ({ platform_ml: current.value.sources.some(block => [...block.expenses, ...block.incomes].some(row => row.participant_type === 'platform')), leasing_company_ids: current.value.leasing_company_id ? [current.value.leasing_company_id] : [], dealer_company_ids: current.value.dealer_company_id ? [current.value.dealer_company_id] : [], distributor_company_ids: current.value.distributor_company_id ? [current.value.distributor_company_id] : [], mark_id: null, model_id: null, companies: [ ...(current.value.dealer ? [{ company_id: current.value.dealer.id, leasing_company_id: null, role: 'dealer' as const, name: current.value.dealer.name, inn: current.value.dealer.inn }] : []), ...(current.value.distributor ? [{ company_id: current.value.distributor.id, leasing_company_id: null, role: 'distributor' as const, name: current.value.distributor.name, inn: current.value.distributor.inn }] : [])] }))
const busy = ref(false)
const error = ref('')
const formatDate = (date: string) => date.split('-').reverse().join('.')
function incomeBase(row: SavedConditionRow, expense: SavedConditionRow | null, index: number): string | undefined {
  if (row.base_type !== 'expense_amount') return undefined
  return expense ? 'Сумма расхода ' + (index + 1) + ' · ' + participantLabels[expense.participant_type] : 'Сумма расхода'
}
async function toggleStatus() {
  if (busy.value || !canManage.value) return
  busy.value = true; error.value = ''
  try { current.value = await props.api.setProgramStatus(current.value.id, current.value.status === 'active' ? 'inactive' : 'active') }
  catch (failure) { error.value = errorMessage(failure) } finally { busy.value = false }
}
</script>
