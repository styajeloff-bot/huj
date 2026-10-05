<template>
  <span :class="['inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium', statusConfig.class]">
    <span v-if="statusConfig.dot" class="w-1.5 h-1.5 rounded-full mr-1.5" :class="statusConfig.dotClass"></span>
    {{ statusConfig.text }}
  </span>
</template>

<script setup lang="ts">
const props = defineProps({
  status: { type: String, required: true }
})

const STATUS_MAP: Record<string, { text: string; class: string; dot: boolean; dotClass: string }> = {
  reserved: {
    text: 'Зарезервировано',
    class: 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    dot: true,
    dotClass: 'bg-[color:rgb(var(--storefront-warning-rgb,234_179_8)/var(--tw-bg-opacity,1))]'
  },
  purchased: {
    text: 'Куплено',
    class: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    dot: true,
    dotClass: 'bg-[color:rgb(var(--storefront-success-rgb,34_197_94)/var(--tw-bg-opacity,1))]'
  },
  leasing_pending: {
    text: 'Ждет одобрения на лизинг',
    class: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]',
    dot: true,
    dotClass: 'bg-[color:rgb(var(--storefront-primary-rgb,59_130_246)/var(--tw-bg-opacity,1))]'
  },
  leasing_active: {
    text: 'Взято в лизинг',
    class: 'bg-[color:rgb(var(--storefront-info-rgb,224_231_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-info-text,#3730a3)]',
    dot: true,
    dotClass: 'bg-[color:rgb(var(--storefront-info-rgb,99_102_241)/var(--tw-bg-opacity,1))]'
  },
  cancellation_requested: {
    text: 'Запрос на отмену',
    class: 'bg-[color:rgb(var(--storefront-warning-rgb,255_237_213)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#9a3412)]',
    dot: true,
    dotClass: 'bg-[color:rgb(var(--storefront-warning-rgb,249_115_22)/var(--tw-bg-opacity,1))]'
  },
  cancelled: {
    text: 'Отменено',
    class: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]',
    dot: false,
    dotClass: ''
  }
}

const statusConfig = computed(() => STATUS_MAP[props.status] || {
  text: props.status,
  class: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]',
  dot: false,
  dotClass: ''
})
</script>
