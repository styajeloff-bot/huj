<template>
  <Modal :show="true" :title="'Сделка ' + formatSourcedApplicationNumber({ display_number: current.application_number, source_type: current.source_type })" :subtitle="subtitle" size="6xl" body-class="monetization monetization-deal-modal" :closable="!busy" :close-on-overlay="!busy && !adjustment" :show-footer="true" @close="close">
    <div class="deal-detail">
      <div class="flex flex-wrap items-center gap-2"><span class="muted">Источник заявки:</span><ApplicationSourceBadge v-if="applicationSourcePresentation(current.source_type)" :source="current.source_type" /><span v-else>{{ sourceLabel(current.source_type) }}</span><NuxtLink v-if="applicationLocation" :to="applicationLocation" class="text-blue-600 underline">Перейти к заявке</NuxtLink></div>
      <div class="deal-state-actions">
        <div class="flex items-center gap-2"><span class="badge" :class="current.status">{{ current.status === 'paid' ? 'Оплачена' : 'Ожидает подтверждения' }}</span><span v-if="current.has_new_conditions" class="badge new-terms-badge">Новые условия</span></div>
        <div class="flex items-center gap-2">
          <button v-if="canAdjust && !adjustment" ref="adjustButton" type="button" class="btn-secondary" :disabled="busy" @click="openAdjustment">Изменить суммы</button>
          <button type="button" class="btn-secondary" :disabled="busy || adjustment" @click="refresh">Обновить</button>
        </div>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="saved" class="deal-terms-success" role="status">Новые условия сохранены. Участникам требуется повторно подтвердить сделку.</p>
      <div class="card deal-facts">
        <h3>{{ current.program_name ? 'Расчёт по условиям «' + current.program_name + '»' : 'Расчёт по условиям монетизации' }}</h3>
        <div class="deal-property-amount"><span>Сумма сделки (стоимость имущества) · <span :title="'Сумма без НДС: ' + formatMoney(current.base_amount, 2)">с учётом НДС</span></span><strong>{{ formatMoney(current.base_amount, 2) }}</strong></div>
        <dl class="details deal-participants">
          <div><dt>Дилер</dt><dd>{{ dealerName }}</dd></div>
          <div><dt>Клиент</dt><dd>{{ current.client_company?.name || '—' }}<small v-if="current.client_company?.inn" class="muted"><br />ИНН {{ current.client_company.inn }}</small></dd></div>
        </dl>
      </div>
      <form id="monetization-deal-terms" @submit.prevent="saveTerms">
        <p v-if="adjustment" class="notice deal-terms-notice">Новые условия применяются только к этой сделке. Новые проценты и суммы округляются до сотых, 5 в третьем знаке — вверх. После сохранения все стороны подтверждают сделку повторно.</p>
        <section class="deal-calculation" aria-label="Расходы и доходы">
          <section v-for="group in amountGroups" :key="group.id" class="calculation-group" :aria-label="group.label">
            <h3>{{ group.label }}</h3>
            <div class="deal-amounts" :class="{ 'unlinked-amounts': !group.expense }">
              <DealAmount v-if="group.expense" :row="group.expense" side="expense" :editing="adjustment ? preview?.rows[group.expense.id] : undefined" :disabled="busy" @change="(mode, value) => changeTerm(group.expense!.id, mode, value)" @normalize="mode => normalizeTerm(group.expense!.id, mode)" />
              <div class="deal-incomes">
                <DealAmount v-for="income in group.incomes" :key="income.id" :row="income" side="income" :company-name="role === 'dealer' && group.expense ? recipientCompanyName(income.participant_type) : undefined" :editing="adjustment ? preview?.rows[income.id] : undefined" :disabled="busy" @change="(mode, value) => changeTerm(income.id, mode, value)" @normalize="mode => normalizeTerm(income.id, mode)" />
                <p v-if="!group.incomes.length" class="muted">Нет доступных доходов</p>
              </div>
            </div>
            <p v-if="adjustment && group.expense && preview?.budgetErrors[group.expense.id]" class="error deal-budget-error" role="alert">{{ preview.budgetErrors[group.expense.id] }}</p>
            <p v-if="adjustment && group.expense && preview?.remainders[group.expense.id]" class="deal-budget-remaining">Осталась не распределенная сумма {{ formatMoney(preview.remainders[group.expense.id], 2) }}</p>
          </section>
          <p v-if="!amountGroups.length" class="muted">Нет доступных расходов и доходов</p>
        </section>
      </form>
      <section class="deal-documents">
        <h3>Документы по сделке</h3>
        <FileList :files="current.documents" :api="api" />
        <p v-if="!current.documents.length" class="deal-documents-empty">Документы не добавлены</p>
        <div v-if="uploadOpen && current.can_upload_documents" class="deal-upload">
          <p class="muted">Документы необязательны для подтверждения сделки.</p>
          <FileDropzone v-model="files" :disabled="busy || adjustment" />
          <div class="flex justify-end gap-3 mt-3">
            <button type="button" class="btn-secondary" :disabled="busy || adjustment" @click="cancelUpload">Отмена</button>
            <button type="button" class="btn-primary" :disabled="busy || adjustment || !files.length" @click="upload">{{ busy ? 'Загрузка…' : 'Загрузить документы' }}</button>
          </div>
        </div>
        <p v-if="uploadSuccess" class="text-sm text-green-700 mt-2" role="status">Документы загружены.</p>
      </section>
      <section class="deal-confirmations">
        <h3>Подтверждения</h3>
        <div v-for="participant in parties" :key="participant" class="confirmation-line">
          <div class="flex items-center justify-between gap-3"><strong>{{ participantLabels[participant] }}</strong><span class="badge" :class="{ active: !!current.confirmations[participant].confirmed_at }">{{ current.confirmations[participant].confirmed_at ? 'Подтверждено' : 'Ожидается' }}</span></div>
          <p v-if="current.confirmations[participant].confirmed_at" class="muted">{{ formatTime(current.confirmations[participant].confirmed_at) }} · {{ current.confirmations[participant].confirmed_by_name || 'Пользователь' }}</p>
        </div>
        <p v-if="admin && pendingParties.length && current.status !== 'paid'" class="notice">Ожидаются подтверждения: {{ pendingParties.map(party => participantLabels[party]).join(', ') }}</p>
        <button v-if="admin && canConfirm" type="button" class="btn-primary mt-4" :disabled="busy || adjustment || pendingParties.length > 0" @click="confirm">{{ busy ? 'Сохранение…' : 'Подтвердить оплату' }}</button>
      </section>
    </div>
    <template #footer>
      <template v-if="adjustment">
        <button type="button" class="btn-secondary" :disabled="busy" @click="cancelAdjustment">Отмена</button>
        <button type="submit" form="monetization-deal-terms" class="btn-primary" :disabled="busy || !canAdjust || !preview?.valid || !preview.items.length">{{ busy ? 'Сохранение…' : 'Сохранить' }}</button>
      </template>
      <template v-else>
        <button type="button" class="btn-secondary" :disabled="busy" @click="close">Закрыть</button>
        <button v-if="!admin && canConfirm" type="button" class="btn-primary" :disabled="busy" @click="confirm">{{ busy ? 'Сохранение…' : 'Подтвердить' }}</button>
        <button v-if="current.can_upload_documents && !uploadOpen" type="button" class="btn-primary" :disabled="busy" @click="openUpload">Приложить документы</button>
      </template>
    </template>
  </Modal>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import type { Deal, Participant, Role, TermsInputMode } from '../types'
import { dealApplicationLocation } from '../routes'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import { participantLabels, sourceLabel } from '../editor'
import { applicationSourcePresentation, formatSourcedApplicationNumber } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import { formatMoney } from '../money'
import { groupIncomes } from '../grouping'
import { createTermsDraft, normalizeTermDraft, previewDealTerms, type TermDraft } from '../dealTerms'
import FileList from './FileList.vue'
import FileDropzone from './FileDropzone.vue'
import DealAmount from './DealAmount.vue'
const props = defineProps<{ api: MonetizationApi; deal: Deal; role: Role }>()
const emit = defineEmits<{ close: []; updated: [deal: Deal] }>()
const current = ref(props.deal)
const route = useRoute()
const applicationLocation = computed(() => dealApplicationLocation(current.value, props.role, route.query))
function recipientCompanyName(party: Participant): string | undefined {
  if (party === 'leasing') return current.value.leasing_company?.name
  if (party === 'dealer') return current.value.dealer_company?.name
  if (party === 'distributor') return current.value.distributor_company?.name
}
// Strip only a repeated role before a quoted company name in this card.
const dealerName = computed(() => current.value.dealer_company?.name.replace(/^Дилер\s+(?=[«"„“])/iu, '') || '—')
const amountGroups = computed(() => groupIncomes(current.value.expenses, current.value.incomes, row => row.id, row => row.expense_ref_amount_id))
const error = ref('')
const busy = ref(false)
const saved = ref(false)
const adjustment = ref(false)
const drafts = ref<Record<string, TermDraft>>({})
const preview = computed(() => adjustment.value ? previewDealTerms(current.value, drafts.value) : null)
const adjustButton = ref<HTMLButtonElement | null>(null)
const uploadOpen = ref(false)
const uploadSuccess = ref(false)
const files = ref<File[]>([])
const admin = computed(() => props.role === 'carcraft_employee')
const canAdjust = computed(() => admin.value && current.value.can_adjust && current.value.status !== 'paid')
const parties = computed(() => (['leasing', 'dealer', 'distributor'] as const).filter(party => current.value.confirmations[party].applicable))
const pendingParties = computed(() => parties.value.filter(party => !current.value.confirmations[party].confirmed_at))
const canConfirm = computed(() => current.value.can_confirm)
const formatTime = (value: string | null) => value ? new Date(value).toLocaleString('ru-RU') : ''
const subtitle = computed(() => [current.value.created_at ? new Date(current.value.created_at).toLocaleDateString('ru-RU') : null, current.value.leasing_company?.name, current.value.brand].filter(Boolean).join(' · '))
watch(() => props.deal, deal => {
  if (adjustment.value && deal.revision !== current.value.revision && deal.can_adjust && deal.status !== 'paid') {
    error.value = 'Условия сделки изменились. Отмените черновик и обновите карточку.'
    return
  }
  current.value = deal
})
watch(canAdjust, available => { if (!available) { adjustment.value = false; drafts.value = {} } })
function close() {
  if (busy.value) return

  emit('close')
}
function replaceDeal(deal: Deal) { current.value = deal; emit('updated', deal) }
async function cancelAdjustment() {
  if (busy.value) return
  adjustment.value = false; drafts.value = {}; error.value = ''
  current.value = props.deal
  await nextTick()
  adjustButton.value?.focus()
}
async function openAdjustment() {
  if (!canAdjust.value || busy.value) return
  error.value = ''; saved.value = false
  drafts.value = createTermsDraft(current.value)
  adjustment.value = true
  await nextTick()
  document.getElementById('monetization-deal-terms')?.querySelector<HTMLInputElement>('input:not(:disabled)')?.focus()
}
function changeTerm(id: string, inputMode: TermsInputMode, value: string) {
  if (!adjustment.value || busy.value || !canAdjust.value) return
  drafts.value[id] = { inputMode, value, dirty: true }
}
function normalizeTerm(id: string, mode: TermsInputMode) {
  const draft = drafts.value[id]
  if (!adjustment.value || busy.value || !canAdjust.value || !draft || draft.inputMode !== mode) return
  drafts.value[id] = normalizeTermDraft(draft)
}
async function saveTerms() {
  if (busy.value || !canAdjust.value || !preview.value?.valid || !preview.value.items.length) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api.adjust(current.value.id, current.value.revision, preview.value.items)
    adjustment.value = false; drafts.value = {}; saved.value = result.revision !== current.value.revision
    replaceDeal(result)
  } catch (failure) {
    const status = (failure as { statusCode?: number; status?: number })?.statusCode ?? (failure as { status?: number })?.status
    error.value = errorMessage(failure) + (status === 409 ? ' Отмените черновик и обновите карточку.' : '')
  } finally {
    busy.value = false
    if (!adjustment.value) {
      await nextTick()
      adjustButton.value?.focus()
    }
  }
}
function openUpload() { if (!current.value.can_upload_documents || busy.value || adjustment.value) return; uploadSuccess.value = false; uploadOpen.value = true }
function cancelUpload() { files.value = []; uploadOpen.value = false }
async function action(operation: () => Promise<Deal>) {
  if (busy.value || adjustment.value) return
  busy.value = true; error.value = ''; saved.value = false
  try { replaceDeal(await operation()) } catch (failure) { error.value = errorMessage(failure) } finally { busy.value = false }
}
const refresh = () => action(() => props.api.deal(current.value.id))
const confirm = () => { if (canConfirm.value && (!admin.value || !pendingParties.value.length)) return action(() => props.api.confirm(current.value.id, current.value.revision, admin.value)) }
async function upload() {
  if (busy.value || adjustment.value || !current.value.can_upload_documents || !files.value.length) return
  await action(async () => {
    await props.api.uploadDocuments(current.value.id, files.value, current.value.revision)
    files.value = []; uploadOpen.value = false; uploadSuccess.value = true
    return props.api.deal(current.value.id)
  })
}
</script>
<style scoped>
.deal-state-actions { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
.deal-property-amount { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; font-size:13px; }
.deal-property-amount strong { white-space:nowrap; }
.deal-participants { border-top:1px solid #eef0f4; padding-top:14px; margin-top:14px; }
.deal-documents { margin:20px 0; }
.deal-documents-empty { border:1px dashed #dfe3ea; border-radius:6px; padding:10px 12px; font-size:13px; color:#8b93a3; }
.deal-budget-remaining { margin-top:12px; color:#526174; font-size:13px; }
.deal-upload { margin-top:12px; }
.deal-upload>p { margin-bottom:10px; }
</style>
