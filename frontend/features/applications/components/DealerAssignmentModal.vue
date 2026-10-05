<template>
  <Teleport to="body">
    <div data-storefront-block="client.application" class="fixed inset-0 z-[70] flex items-center justify-center bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] p-4" @keydown="onKeydown" @click.self="close">
      <form ref="dialog" role="dialog" aria-modal="true" aria-labelledby="dealer-distribution-title" tabindex="-1" class="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#111827)] shadow-xl" @submit.prevent="submitAssignment">
        <header class="flex items-start justify-between gap-4 border-b border-[color:var(--storefront-border,#e5e7eb)] p-5">
          <div>
            <h3 id="dealer-distribution-title" class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Назначить дилера</h3>
            <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Выберите дилера, автомобили и количество со своего склада.</p>
          </div>
          <button type="button" class="storefront-action-ghost rounded-lg px-3 py-2 text-sm" :disabled="submitting" @click="close">Закрыть</button>
        </header>
        <div class="grid gap-5 overflow-y-auto p-5">
          <p v-if="loading" role="status" class="py-6 text-center text-sm">Загружаем доступных дилеров...</p>
          <div v-else-if="loadError" role="alert" class="text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
            <p>{{ loadError }}</p>
            <button type="button" class="storefront-action-ghost mt-2 underline" @click="fetchDealers">Попробовать снова</button>
          </div>
          <p v-else-if="!dealers.length" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">У дистрибьютора нет доступных дилеров.</p>
          <fieldset v-else :disabled="submitting" class="min-w-0">
            <legend class="mb-2 text-sm font-semibold">Дилер</legend>
            <div class="max-h-48 overflow-y-auto rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
              <label v-for="dealer in dealers" :key="dealer.id" class="flex cursor-pointer items-center gap-3 border-b border-[color:var(--storefront-border,#e5e7eb)] px-4 py-3 text-sm last:border-b-0">
                <input v-model="selectedDealerCompanyId" type="radio" name="assigned-dealer" :value="dealer.id" class="h-4 w-4" />
                <span class="break-words">{{ dealer.name || 'Без названия' }}</span>
              </label>
            </div>
          </fieldset>
          <fieldset :disabled="submitting || refreshing" class="min-w-0">
            <legend class="mb-2 text-sm font-semibold">Автомобили</legend>
            <p v-if="!availablePositions.length" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Все доступные автомобили уже распределены.</p>
            <div v-for="position in availablePositions" :key="position.application_vehicle_id" class="flex items-center justify-between gap-4 border-b border-[color:var(--storefront-border,#e5e7eb)] py-3 last:border-b-0">
              <label class="flex min-w-0 cursor-pointer items-start gap-3 text-sm">
                <input v-model="selectedIds" type="checkbox" :value="position.application_vehicle_id" class="mt-1 h-4 w-4 shrink-0" />
                <span class="break-words">{{ position.title }}<span class="mt-1 block text-[color:var(--storefront-text-muted,#6b7280)]">Доступно: {{ position.unassigned_quantity }} шт.</span></span>
              </label>
              <label class="grid shrink-0 gap-1 text-sm">
                <span>Количество</span>
                <input v-model.number="quantities[position.application_vehicle_id]" type="number" min="1" :max="position.unassigned_quantity" step="1" :disabled="!selectedIds.includes(position.application_vehicle_id)" :aria-label="`Количество: ${position.title}`" class="storefront-control input-field w-28" />
              </label>
            </div>
          </fieldset>
          <div v-if="submitError" role="alert" class="text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
            <p>{{ submitError }}</p>
            <button v-if="conflict" type="button" :disabled="refreshing" class="storefront-action-ghost mt-2 underline" @click="refreshPositions">{{ refreshing ? 'Обновляем...' : 'Обновить остатки' }}</button>
          </div>
        </div>
        <footer class="flex justify-end gap-3 border-t border-[color:var(--storefront-border,#e5e7eb)] p-5">
          <button type="button" class="btn-secondary text-sm" :disabled="submitting" @click="close">Отмена</button>
          <button type="submit" class="btn-primary text-sm" :disabled="loading || submitting || refreshing || !dealers.length || !availablePositions.length">{{ submitting ? 'Сохраняем...' : 'Назначить дилера' }}</button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useNotificationCompanyContext } from '~/features/notifications'
import { createApplicationsApi, parseApplicationsApiError, type DealerDistributionPosition, type DistributorDealerOption } from '../api/applicationsApi'
import { createDistributionRequest, distributablePositions, distributionItems } from '../dealerDistribution'

const props = defineProps<{ applicationId: string; positions: DealerDistributionPosition[] }>()
const emit = defineEmits<{ close: []; assigned: [] }>()
const applicationsApi = createApplicationsApi(useRuntimeConfig(), useNotificationCompanyContext())
const positions = ref(props.positions)
const availablePositions = computed(() => distributablePositions(positions.value))
const dealers = ref<DistributorDealerOption[]>([])
const selectedDealerCompanyId = ref<string | null>(null)
const selectedIds = ref<string[]>([])
const quantities = ref<Record<string, number | string>>(Object.fromEntries(availablePositions.value.map(position => [position.application_vehicle_id, position.unassigned_quantity])))
const loading = ref(true)
const submitting = ref(false)
const refreshing = ref(false)
const loadError = ref('')
const submitError = ref('')
const conflict = ref(false)
const dialog = ref<HTMLFormElement | null>(null)
const requestFor = createDistributionRequest(() => crypto.randomUUID())
let dealersRequestSequence = 0
let previousFocus: HTMLElement | null = null

const close = () => { if (!submitting.value) emit('close') }
const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') { event.stopPropagation(); close() }
  if (event.key !== 'Tab' || !dialog.value) return
  const focusable = [...dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]')].filter(element => !element.closest('fieldset:disabled'))
  const first = focusable[0]
  const last = focusable.at(-1)
  if (!first || !last) { event.preventDefault(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.value)) { event.preventDefault(); first.focus() }
}
const fetchDealers = async () => {
  const sequence = ++dealersRequestSequence
  loading.value = true
  loadError.value = ''
  try {
    const response = await applicationsApi.listDistributorDealers()
    if (sequence === dealersRequestSequence) dealers.value = response.dealers
  } catch (error) {
    if (sequence === dealersRequestSequence) loadError.value = parseApplicationsApiError(error, 'Не удалось загрузить доступных дилеров').message
  } finally {
    if (sequence === dealersRequestSequence) loading.value = false
  }
}
const refreshPositions = async () => {
  refreshing.value = true
  try {
    const response = await applicationsApi.getApplication(props.applicationId)
    positions.value = response.application.dealer_distribution ?? []
    selectedIds.value = selectedIds.value.filter(id => availablePositions.value.some(position => position.application_vehicle_id === id))
    submitError.value = 'Остатки обновлены. Проверьте выбранное количество перед назначением.'
    conflict.value = false
  } catch (error) {
    submitError.value = parseApplicationsApiError(error, 'Не удалось обновить остатки').message
  } finally { refreshing.value = false }
}
const submitAssignment = async () => {
  if (submitting.value || refreshing.value) return
  submitError.value = ''
  conflict.value = false
  try {
    if (!selectedDealerCompanyId.value) throw new Error('Выберите дилера.')
    const items = distributionItems(positions.value, selectedIds.value, quantities.value)
    const body = requestFor(selectedDealerCompanyId.value, items)
    submitting.value = true
    await applicationsApi.distributeDealer(props.applicationId, body)
    emit('assigned')
  } catch (error) {
    const parsed = parseApplicationsApiError(error, 'Не удалось назначить дилера')
    submitError.value = parsed.message
    conflict.value = Boolean(error && typeof error === 'object' && 'statusCode' in error && error.statusCode === 409)
  } finally { submitting.value = false }
}
onMounted(() => {
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  dialog.value?.focus()
  void fetchDealers()
})
onBeforeUnmount(() => {
  dealersRequestSequence += 1
  previousFocus?.focus()
})
</script>
