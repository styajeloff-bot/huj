<template>
  <div class="kpi-card">
    <div class="kpi-title">{{ title }}</div>
    <div class="kpi-value" :style="{ color: color || 'var(--storefront-text, #111827)' }" :title="fullValueTitle">
      {{ formattedValue }}
    </div>
    <div v-if="delta !== undefined" class="kpi-delta">
      <span
        :class="[
          delta >= 0 ? 'text-[color:var(--storefront-success-text,#16a34a)]' : 'text-[color:var(--storefront-error-text,#dc2626)]',
          'flex items-center font-medium'
        ]"
      >
        <template v-if="delta >= 0">↑</template>
        <template v-else>↓</template>
        {{ Math.abs(delta).toLocaleString('ru-RU') }}
        <template v-if="deltaPercent !== undefined">
          ({{ deltaPercent >= 0 ? '+' : '' }}{{ deltaPercent.toFixed(1) }}%)
        </template>
      </span>
      <span v-if="comparison" class="text-[color:var(--storefront-text-muted,#9ca3af)] ml-1">{{ comparison }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  value?: number
  color?: string
  delta?: number
  deltaPercent?: number
  comparison?: string
  prefix?: string
  suffix?: string
}>()

const { formatMoneyCompact, formatPrice, formatNumber } = useFormatPrice()

const isMoneyValue = computed(() => props.prefix === '₽' || props.suffix === '₽')

const formattedValue = computed(() => {
  if (props.value === undefined || props.value === null) return '—'
  if (isMoneyValue.value) return formatMoneyCompact(props.value)

  const formatted = formatNumber(props.value)
  return `${props.prefix || ''}${formatted}${props.suffix || ''}`
})

const fullValueTitle = computed(() => {
  if (props.value === undefined || props.value === null) return undefined
  if (isMoneyValue.value) return formatPrice(props.value)
  return undefined
})
</script>

<style scoped>
.kpi-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-title {
  font-size: 13px;
  color: var(--storefront-text-muted, #6b7280);
  line-height: 1.3;
  min-height: 34px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.kpi-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-delta {
  display: flex;
  align-items: center;
  font-size: 12px;
  margin-top: 2px;
}
</style>
