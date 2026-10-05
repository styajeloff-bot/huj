<template>
  <div data-storefront-block="client.checkout" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">{{ title }}</h4>

    <div v-if="items.length === 0" class="mt-4 rounded-md bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
      Нет данных за выбранный период
    </div>

    <div v-else class="mt-3 divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
      <div
        v-for="(item, index) in items"
        :key="`${item.display_name}-${item.inn || index}`"
        class="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="flex min-w-0 items-start gap-3">
          <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-xs font-semibold text-[color:var(--storefront-text-muted,#4b5563)]">
            {{ index + 1 }}
          </span>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <p class="break-words text-sm font-medium text-[color:var(--storefront-text,#111827)]">
                {{ item.display_name }}
              </p>
              <span
                v-if="item.is_self_transfer"
                class="rounded-full border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-[11px] font-medium text-[color:var(--storefront-text-muted,#4b5563)]"
              >
                переводы
              </span>
            </div>
            <p v-if="item.inn" class="mt-0.5 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              ИНН: <span class="font-mono">{{ item.inn }}</span>
            </p>
          </div>
        </div>
        <p class="shrink-0 text-sm font-semibold tabular-nums text-[color:var(--storefront-text,#111827)] sm:text-right">
          {{ formatPrice(item.amount) }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BankStatementCounterparty } from '../../types/bankStatementAnalytics'

defineProps<{
  title: string
  items: BankStatementCounterparty[]
}>()

const { formatPrice } = useFormatPrice()
</script>
