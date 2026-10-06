<template>
  <Modal
    :show="true"
    title="Ответственные сотрудники"
    :subtitle="ctx.companyName(ctx.partyCompanyId.value) || undefined"
    size="lg"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-assignees-form" class="space-y-4" novalidate @submit.prevent="submit">
      <p class="text-sm text-gray-600">
        Один основной и не более одного дополнительного ответственного из активных сотрудников вашей компании.
        Переназначение доступно в любом статусе сделки, в том числе подтверждённой; оно попадёт в историю.
      </p>
      <p v-if="loading" class="text-sm text-gray-500">Загрузка сотрудников…</p>
      <p v-else-if="loadError" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        {{ loadError }}
        <button type="button" class="underline ml-1" @click="load">Повторить</button>
      </p>
      <template v-else>
        <FastDealCardField label="Основной ответственный" required for-id="fast-deal-primary" :error="primaryError">
          <select id="fast-deal-primary" v-model="primaryId" class="select-field" :disabled="ctx.busy.value">
            <option value="">Выберите сотрудника</option>
            <option v-for="item in employees" :key="item.id" :value="item.id">{{ label(item) }}</option>
          </select>
        </FastDealCardField>
        <FastDealCardField label="Дополнительный ответственный" for-id="fast-deal-additional" :error="additionalError">
          <select id="fast-deal-additional" v-model="additionalId" class="select-field" :disabled="ctx.busy.value">
            <option value="">Не назначать</option>
            <option v-for="item in employees" :key="item.id" :value="item.id" :disabled="item.id === primaryId">{{ label(item) }}</option>
          </select>
        </FastDealCardField>
      </template>
      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-assignees-form" class="btn-primary" :disabled="ctx.busy.value || loading || !!loadError" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { parseFastDealError } from '../api/fastDealsApi'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import type { FastDealCard } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

interface Employee {
  id: string
  name: string | null
  email: string | null
  sub_role: string
}

const props = defineProps<{ deal: FastDealCard }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const employees = ref<Employee[]>([])
const loading = ref(true)
const loadError = ref('')
const serverError = ref<ActionFailure | null>(null)
const localPrimaryError = ref('')

const current = props.deal.assignees.filter(item => item.company_id === ctx.partyCompanyId.value)
const primaryId = ref(current.find(item => item.role === 'primary')?.user_id ?? '')
const additionalId = ref(current.find(item => item.role === 'additional')?.user_id ?? '')

const SUB_ROLES: Record<string, string> = { administrator: 'администратор', manager: 'менеджер', employee: 'сотрудник' }
const label = (item: Employee) => [item.name || item.email || 'Без имени', SUB_ROLES[item.sub_role] ?? item.sub_role].filter(Boolean).join(' · ')

const primaryError = computed(() => localPrimaryError.value || (serverError.value?.field === 'primary_user_id' ? serverError.value.detail : ''))
const additionalError = computed(() => (serverError.value?.field === 'additional_user_id' ? serverError.value.detail : ''))
const generalError = computed(() =>
  serverError.value && serverError.value.field !== 'primary_user_id' && serverError.value.field !== 'additional_user_id' ? serverError.value : null,
)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    employees.value = (await ctx.api.assignableEmployees(props.deal.id)).items
  } catch (error) {
    loadError.value = parseFastDealError(error).detail
  } finally {
    loading.value = false
  }
}

async function submit() {
  serverError.value = null
  localPrimaryError.value = ''
  if (!primaryId.value) {
    localPrimaryError.value = 'Выберите основного ответственного'
    return
  }
  if (additionalId.value && additionalId.value === primaryId.value) {
    serverError.value = { detail: 'Основной и дополнительный ответственные должны быть разными сотрудниками', field: 'additional_user_id' }
    return
  }
  const result = await ctx.run((etag, card) =>
    ctx.api.setAssignees(card.id, etag, { primary_user_id: primaryId.value, additional_user_id: additionalId.value || null }),
  )
  if (result.ok) emit('close')
  else serverError.value = result.error
}

onMounted(load)
</script>
