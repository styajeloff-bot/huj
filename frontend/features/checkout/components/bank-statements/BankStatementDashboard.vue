<template>
  <div data-storefront-block="client.checkout" class="space-y-4 sm:space-y-5" style="color: var(--storefront-text,#000);">
    <div v-if="status === 'loading'" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] py-10 text-center">
      <div class="inline-block h-8 w-8 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем финансовые показатели…</p>
    </div>

    <div v-else-if="status === 'error'" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p class="text-sm text-[color:var(--storefront-error-text,#991b1b)]">{{ errorMessage }}</p>
        <button
          type="button"
          class="storefront-action-secondary rounded-md border border-[color:var(--storefront-destructive-border,#fecaca)] bg-[color:rgb(var(--storefront-destructive-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-1.5 text-xs font-medium text-[color:var(--storefront-destructive-foreground,#b91c1c)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))]"
          @click="refresh"
        >
          Повторить
        </button>
      </div>
    </div>

    <div v-else-if="!companyId" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
      Данные компании ещё не загружены. Вы можете продолжить — на следующих шагах их можно заполнить вручную.
    </div>

    <div v-else-if="analytics?.empty" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
      Загрузите банковские выписки на шаге «Анкета», чтобы увидеть финансовые показатели
    </div>

    <template v-else-if="analytics">
      <BankStatementDashboardHeader :analytics="analytics" />

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.9fr)]">
        <BankStatementKpiGrid :kpi="analytics.kpi" />
        <BankStatementCashflowBlock :points="analytics.cashflow" />
      </div>

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(360px,0.75fr)_minmax(0,1.25fr)]">
        <BankStatementExpenseStructureBlock :items="analytics.expense_structure" />
        <BankStatementCounterpartiesBlock
          :top-clients="analytics.top_clients"
          :top-suppliers="analytics.top_suppliers"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { UUID } from '~/types/ids'
import BankStatementCashflowBlock from './BankStatementCashflowBlock.vue'
import BankStatementCounterpartiesBlock from './BankStatementCounterpartiesBlock.vue'
import BankStatementDashboardHeader from './BankStatementDashboardHeader.vue'
import BankStatementExpenseStructureBlock from './BankStatementExpenseStructureBlock.vue'
import BankStatementKpiGrid from './BankStatementKpiGrid.vue'
import { useBankStatementAnalytics } from '../../composables/useBankStatementAnalytics'

const props = defineProps<{
  companyId: UUID | null
}>()

const companyId = computed(() => props.companyId)
const { status, data, errorMessage, refresh } = useBankStatementAnalytics(companyId)
const analytics = computed(() => data.value)
</script>
