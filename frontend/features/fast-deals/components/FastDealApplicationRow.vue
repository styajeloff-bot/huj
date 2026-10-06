<template>
  <article
    data-testid="fast-deal-row"
    class="card transition-shadow duration-200 hover:shadow-lg"
  >
    <div class="mb-4 flex items-start justify-between gap-4">
      <div class="min-w-0">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
          Регистрация сделки {{ deal.display_number }}
        </h3>
        <FastDealKindBadge class="mt-1" />
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          {{ fastDealDirectionLabel(deal.source_type) }}
        </p>
      </div>
      <FastDealStatusBadge :status="deal.status" />
    </div>

    <dl class="mb-4 grid grid-cols-2 gap-4 text-sm">
      <div>
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Клиент</dt>
        <dd class="font-medium text-[color:var(--storefront-text,#111827)]">{{ deal.client.name }}</dd>
        <dd v-if="deal.client.inn" class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН {{ deal.client.inn }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Стороны</dt>
        <dd class="text-[color:var(--storefront-text,#111827)]">Дилер: <span class="font-medium">{{ parties.dealer }}</span></dd>
        <dd class="text-[color:var(--storefront-text,#111827)]">ЛК: <span class="font-medium">{{ parties.leasing }}</span></dd>
      </div>
      <div>
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Единиц техники</dt>
        <dd class="font-medium text-[color:var(--storefront-text,#111827)]">{{ deal.vehicle_count }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Стоимость техники</dt>
        <dd class="font-medium text-[color:var(--storefront-text,#111827)]">{{ formatMoney(deal.vehicles_total) }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Дата создания</dt>
        <dd class="font-medium text-[color:var(--storefront-text,#111827)]">{{ formatDateTime(deal.created_at) }}</dd>
      </div>
      <div v-if="assignees.length">
        <dt class="text-[color:var(--storefront-text-muted,#6b7280)]">Ответственные</dt>
        <dd v-for="assignee in assignees" :key="assignee.key" class="text-[color:var(--storefront-text,#111827)]">
          <span class="text-[color:var(--storefront-text-muted,#6b7280)]">{{ assignee.roleLabel }}:</span> {{ assignee.name }}
        </dd>
      </div>
    </dl>

    <div class="flex items-center justify-end border-t border-[color:var(--storefront-border,#e5e7eb)] pt-4">
      <NuxtLink :to="fastDealRoute(deal.id)" class="btn-primary text-sm">
        Открыть сделку
      </NuxtLink>
    </div>
  </article>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import FastDealKindBadge from '~/features/fast-deals/components/FastDealKindBadge.vue'
import FastDealStatusBadge from '~/features/fast-deals/components/FastDealStatusBadge.vue'
import { assigneeSummaries, fastDealParties } from '~/features/fast-deals/listPresentation'
import { formatMoney } from '~/features/fast-deals/money'
import { fastDealRoute } from '~/features/fast-deals/routes'
import { fastDealDirectionLabel } from '~/features/fast-deals/status'
import type { FastDealListItem } from '~/features/fast-deals/types'

/**
 * A fast deal row inside the merged «Мои заявки» lists. It links to the deal's own card and never
 * pretends to be an ordinary application (no application number prefix, no source badge).
 */
const props = defineProps<{ deal: FastDealListItem }>()

const authStore = useAuthStore()
const { formatDateTime } = useFormatDate()
const parties = computed(() => fastDealParties(props.deal, { viewerIsLeasing: authStore.isLeasingCompany }))
const assignees = computed(() => assigneeSummaries(props.deal))
</script>
