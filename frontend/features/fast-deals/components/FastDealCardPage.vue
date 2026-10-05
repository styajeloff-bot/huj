<template>
  <div class="max-w-7xl mx-auto pb-12">
    <NuxtLink to="/workspace/fast-deals" class="text-sm text-blue-600 hover:text-blue-700">← К списку сделок</NuxtLink>

    <div v-if="ctx.busy.value" class="fixed inset-x-0 top-0 z-[300] h-1 animate-pulse bg-blue-500" role="progressbar" aria-label="Выполняется операция" />

    <div v-if="ctx.loadState.value === 'loading'" class="flex justify-center py-16" role="status" aria-label="Загрузка сделки">
      <div class="h-10 w-10 animate-spin rounded-full border-b-2 border-blue-600" />
    </div>

    <div v-else-if="ctx.loadState.value === 'not_found'" class="mt-4 rounded-lg bg-white p-8 text-center shadow-sm" role="alert">
      <h1 class="text-xl font-semibold text-gray-900">Сделка не найдена</h1>
      <p class="mt-2 text-sm text-gray-600">Сделки нет или у вас нет к ней доступа. Проверьте ссылку или вернитесь к списку.</p>
      <NuxtLink to="/workspace/fast-deals" class="btn-primary mt-4 inline-flex">К списку сделок</NuxtLink>
    </div>

    <div v-else-if="ctx.loadState.value === 'forbidden'" class="mt-4 rounded-lg bg-white p-8 text-center shadow-sm" role="alert">
      <h1 class="text-xl font-semibold text-gray-900">Нет доступа</h1>
      <p class="mt-2 text-sm text-gray-600">{{ ctx.loadError.value || 'Для вашей роли эта сделка недоступна.' }}</p>
      <NuxtLink to="/workspace/fast-deals" class="btn-primary mt-4 inline-flex">К списку сделок</NuxtLink>
    </div>

    <div v-else-if="ctx.loadState.value === 'error' || !card" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-6 text-red-800" role="alert">
      <p>{{ ctx.loadError.value || 'Не удалось загрузить сделку.' }}</p>
      <button type="button" class="btn-outline mt-3" @click="ctx.load()">Повторить</button>
    </div>

    <div v-else class="mt-4 space-y-6">
      <div
        v-if="ctx.stale.value"
        class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        role="alert"
      >
        <span>Сделка изменилась: показанные данные устарели. Обновите карточку, чтобы продолжить работу.</span>
        <button type="button" class="btn-primary text-sm" :disabled="refreshing" @click="refresh">
          {{ refreshing ? 'Обновляем…' : 'Обновить карточку' }}
        </button>
      </div>
      <p v-if="ctx.refreshError.value" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
        Не удалось обновить карточку: {{ ctx.refreshError.value }}
      </p>

      <FastDealCardHeader :deal="card" />
      <FastDealActionBar :deal="card" />

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <FastDealCardClient :deal="card" />
        <FastDealTermsPanel :deal="card" />
      </div>

      <FastDealVehicleList :deal="card" />
      <FastDealOffersPanel :deal="card" />
      <FastDealCardChanges :deal="card" />
      <FastDealFilesPanel :deal="card" />
      <FastDealAssigneesPanel :deal="card" />
      <FastDealHistoryPanel :deal="card" />
    </div>

    <FastDealActionDialog
      v-if="ctx.resetPrompt.value"
      title="Вернуть сделку в черновик?"
      message="Это изменение возвращает сделку в черновик."
      :warnings="[
        'Коммерческие предложения лизинговых компаний будут аннулированы, их участие в текущем цикле завершится.',
        'Резервы техники будут сняты. После правок сделку нужно отправить заново.',
      ]"
      confirm-text="Изменить и вернуть в черновик"
      @confirm="ctx.answerResetPrompt(true)"
      @close="ctx.answerResetPrompt(false)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { UUID } from '~/types/ids'
import { provideNotificationCompanyContext } from '~/features/notifications'
import { provideFastDealCard, useFastDealCard } from '../composables/useFastDealCard'
import FastDealActionBar from './FastDealActionBar.vue'
import FastDealActionDialog from './FastDealActionDialog.vue'
import FastDealAssigneesPanel from './FastDealAssigneesPanel.vue'
import FastDealCardChanges from './FastDealCardChanges.vue'
import FastDealCardClient from './FastDealCardClient.vue'
import FastDealCardHeader from './FastDealCardHeader.vue'
import FastDealFilesPanel from './FastDealFilesPanel.vue'
import FastDealHistoryPanel from './FastDealHistoryPanel.vue'
import FastDealOffersPanel from './FastDealOffersPanel.vue'
import FastDealTermsPanel from './FastDealTermsPanel.vue'
import FastDealVehicleList from './FastDealVehicleList.vue'

const props = defineProps<{ dealId: UUID }>()

const route = useRoute()
// Notification links carry the company the screen belongs to; requests of this card keep it.
const companyContext = provideNotificationCompanyContext(() => route.query.notification_company_id)
const ctx = useFastDealCard(props.dealId, companyContext)
provideFastDealCard(ctx)

const card = ctx.card
const refreshing = ref(false)

useHead({
  title: computed(() => (card.value ? `${card.value.display_number} · Регистрация сделки` : 'Регистрация сделки')),
})

async function refresh() {
  refreshing.value = true
  try {
    await ctx.reload()
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  void ctx.load()
  void ctx.loadDirectoryLabels()
})
</script>
