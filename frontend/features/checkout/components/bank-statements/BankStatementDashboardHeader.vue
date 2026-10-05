<template>
  <div data-storefront-block="client.checkout" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-w-0">
        <p class="text-xs font-semibold uppercase tracking-wide text-[color:var(--storefront-text-muted,#6b7280)]">ФИНАНСОВЫЕ ПОКАЗАТЕЛИ</p>
        <h3 class="mt-1 text-lg font-semibold leading-tight text-[color:var(--storefront-title,#111827)]">
          {{ analytics.company.name || 'Компания' }}
        </h3>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          ИНН: <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ analytics.company.inn || '—' }}</span>
        </p>
      </div>

      <div class="w-full space-y-2 text-sm text-[color:var(--storefront-text,#374151)] lg:max-w-xl lg:text-right">
        <p class="font-medium text-[color:var(--storefront-text,#111827)]">
          {{ periodText }}
        </p>
        <div v-if="analytics.accounts.length > 0" class="space-y-1">
          <p
            v-for="account in analytics.accounts"
            :key="`${account.account_number}-${account.bank_name}`"
            class="break-words"
          >
            <span class="font-mono">{{ account.account_number }}</span>
            <span class="text-[color:var(--storefront-text-muted,#9ca3af)]"> — </span>
            <span>{{ account.bank_name }}</span>
          </p>
        </div>
        <p v-else class="text-[color:var(--storefront-text-muted,#6b7280)]">Счета не найдены</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BankStatementAnalytics } from '../../types/bankStatementAnalytics'

const props = defineProps<{
  analytics: BankStatementAnalytics
}>()

const formatDate = (raw: string) => {
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const periodText = computed(() => {
  if (!props.analytics.period) return 'Период анализа: —'
  return `Период анализа: ${formatDate(props.analytics.period.start)} — ${formatDate(props.analytics.period.end)}`
})
</script>
