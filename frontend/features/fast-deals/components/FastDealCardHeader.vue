<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-title">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <h1 id="fast-deal-title" class="text-2xl font-bold text-gray-900 break-all">{{ deal.display_number }}</h1>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span
            class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
            :class="dealStatusTone(deal.status)"
            aria-live="polite"
          >
            {{ dealStatusLabel(deal.status) }}
          </span>
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
            {{ sourceLabel(deal.source_type) }}
          </span>
          <span class="text-gray-500">Ваша роль: {{ partyLabel(deal.party) }}</span>
          <span v-if="deal.review_cycle > 1" class="text-gray-500">Цикл согласования № {{ deal.review_cycle }}</span>
        </div>
      </div>
      <dl class="text-sm text-gray-600 grid grid-cols-[auto_auto] gap-x-4 gap-y-1">
        <dt>Создана</dt>
        <dd class="text-gray-900">{{ formatDateTime(deal.created_at) }}</dd>
        <template v-if="deal.sent_at">
          <dt>Отправлена</dt>
          <dd class="text-gray-900">{{ formatDateTime(deal.sent_at) }}</dd>
        </template>
        <template v-if="deal.confirmed_at">
          <dt>Подтверждена</dt>
          <dd class="text-gray-900">{{ formatDateTime(deal.confirmed_at) }}</dd>
        </template>
      </dl>
    </div>

    <div v-if="deal.status === 'confirmed'" class="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-900" role="status">
      Сделка подтверждена.
      <span v-if="deal.confirmed_amount">Сумма сделки: <strong>{{ formatMoney(deal.confirmed_amount) }}</strong>.</span>
      Техника, цены, условия и файлы закрыты для изменений; ответственных можно переназначить.
    </div>
    <div v-else-if="deal.status === 'cancelled'" class="mt-4 rounded-lg border border-slate-300 bg-slate-100 p-3 text-sm text-slate-800" role="status">
      Сделка отменена. Отмена необратима, повторная отправка невозможна.
      <span v-if="deal.status_reason">Причина: {{ deal.status_reason }}</span>
    </div>
    <div v-else-if="deal.status === 'rejected'" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900" role="status">
      Сделка отклонена.
      <span v-if="deal.status_reason">Причина: {{ deal.status_reason }}</span>
      <span v-if="editWillReopen"> Первое же изменение вернёт её в черновик — после исправлений отправьте сделку снова.</span>
    </div>
    <p v-else-if="hint" class="mt-4 text-sm text-gray-700">{{ hint }}</p>

    <div v-if="editWillReset" class="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      Любое изменение техники, цены, опций или условий вернёт сделку в черновик: коммерческие предложения лизинговых
      компаний будут аннулированы, резервы сняты, и сделку потребуется отправить заново.
    </div>

    <div v-if="deal.group_deals.length > 1" class="mt-4">
      <h2 class="text-sm font-semibold text-gray-900 mb-2">Сделки группы</h2>
      <ul class="flex flex-wrap gap-2">
        <li v-for="item in deal.group_deals" :key="item.id">
          <NuxtLink
            :to="ctx.dealLocation(item.id)"
            class="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50"
            :class="item.id === deal.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200'"
          >
            <span class="font-medium">{{ item.display_number }}</span>
            <span v-if="item.dealer_company" class="text-gray-600">{{ item.dealer_company.name }}</span>
            <span v-if="item.vehicle_count" class="text-gray-500">{{ item.vehicle_count }} поз.</span>
            <span class="rounded-full px-2 py-0.5 text-xs" :class="dealStatusTone(item.status)">{{ dealStatusLabel(item.status) }}</span>
          </NuxtLink>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import {
  dealStatusLabel,
  dealStatusTone,
  formatDateTime,
  formatMoney,
  partyLabel,
  sourceLabel,
} from '../composables/fastDealCardFormat'
import type { FastDealCard } from '../types'

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const { editWillReset, editWillReopen } = ctx

/** What the caller is waiting for or may do next; the buttons themselves come from allowed_actions. */
const hint = computed(() => {
  const deal = props.deal
  const own = ctx.ownApplication.value
  const initiator = deal.party === 'initiator'
  switch (deal.status) {
    case 'draft':
      if (!initiator) return ''
      return deal.sent_at
        ? 'Черновик после изменений. Проверьте данные и отправьте сделку повторно.'
        : 'Заполните технику и условия лизинга, затем отправьте сделку.'
    case 'pending_lc_confirmation':
      if (initiator) return 'Сделка отправлена лизинговым компаниям. Дождитесь их коммерческих предложений и выберите одно из них.'
      if (own?.status === 'pending_review') return 'Дилер ожидает ваше коммерческое предложение либо отказ.'
      if (own?.status === 'offer_sent') return 'Ваше КП отправлено. Ожидаем выбор дилера.'
      if (own?.status === 'rejected') return 'Вы отказались от этой сделки.'
      return 'Сделка отправлена лизинговым компаниям и ожидает коммерческих предложений.'
    case 'pending_lc_final_confirmation':
      if (initiator) return 'Выбрано КП лизинговой компании. Ожидаем её финальное подтверждение; выбор можно снять.'
      if (own?.status === 'selected_by_dealer') return 'Дилер выбрал ваше КП. Подтвердите сделку или откажитесь.'
      if (own?.status === 'closed_not_selected') return 'Дилер выбрал другую лизинговую компанию.'
      return 'Выбрано КП одной из лизинговых компаний; ожидается её финальное подтверждение.'
    case 'pending_dealer_confirmation':
      if (deal.party === 'dealer') {
        return deal.has_pending_changes
          ? 'Вы внесли изменения. Подтвердить сделку без изменений нельзя — отправьте изменения лизинговой компании.'
          : 'Подтвердите сделку, измените цену или разрешённые данные позиции либо откажитесь от сделки.'
      }
      return 'Сделка отправлена дилеру и ожидает его решения.'
    case 'pending_lc_changes_confirmation':
      return initiator
        ? 'Дилер предложил изменения. Примите их или отклоните с указанием причины.'
        : 'Изменения отправлены лизинговой компании и ожидают её решения.'
    default:
      return ''
  }
})
</script>
