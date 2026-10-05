<template>
  <div data-storefront-block="client.order" class="overflow-hidden rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
    <ul class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
      <li v-for="line in items" :key="`${line.item.ref.type}:${line.item.ref.id}`" class="flex gap-4 p-4">
        <div class="grid h-16 w-20 shrink-0 place-items-center overflow-hidden rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]">
          <img v-if="safeImageUrl(line.item.image_url)" :src="safeImageUrl(line.item.image_url) ?? undefined" :alt="line.item.title" class="h-full w-full object-contain" width="160" height="128">
          <PhotoIcon v-else class="h-7 w-7 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="font-semibold leading-snug text-[color:var(--storefront-text,#030712)]">{{ line.item.title }}</p>
          <p v-if="line.item.subtitle" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ line.item.subtitle }}</p>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ line.quantity }} шт.</p>
          <p class="mt-2 text-sm font-semibold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(multiplyMoney(line.item.price, line.quantity), line.item.currency_code) }}</p>
        </div>
      </li>
    </ul>
    <div class="flex items-center justify-between gap-4 border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-4 py-3">
      <span class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">К оплате</span>
      <span class="text-lg font-bold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(amount) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PhotoIcon } from '@heroicons/vue/24/outline'
import { formatCommerceMoney, multiplyMoney } from '../money'
import type { CommerceMoney, CommercePurchaseLine } from '../types'

defineProps<{
  items: CommercePurchaseLine[]
  amount: CommerceMoney | null
}>()

const safeImageUrl = (value: string | null): string | null =>
  value?.startsWith('/api/v1/') ? value : null
</script>
