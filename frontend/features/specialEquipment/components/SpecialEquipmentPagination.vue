<template>
  <nav data-storefront-block="equipment.pagination" v-if="pages > 1" class="flex flex-wrap items-center justify-center gap-2 text-storefront-text" aria-label="Пагинация каталога">
    <button
      type="button"
      class="inline-flex min-h-11 items-center gap-1 rounded-lg border border-storefront-border px-3 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:opacity-40 storefront-action-secondary"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      <ChevronLeftIcon class="h-4 w-4 text-storefront-icon" aria-hidden="true" />
      <span>Назад</span>
    </button>

    <template v-for="item in visiblePages" :key="item.key">
      <span v-if="item.page === null" class="px-1 text-storefront-text-muted" aria-hidden="true">…</span>
      <button
        v-else
        type="button"
        class="grid h-11 min-w-11 place-items-center rounded-lg px-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
        :class="item.page === page ? 'bg-storefront-selected text-storefront-selected-foreground' : 'border border-storefront-border text-storefront-text hover:bg-storefront-secondary-hover'"
        :aria-current="item.page === page ? 'page' : undefined"
        :aria-label="`Страница ${item.page}`"
        @click="emit('change', item.page)"
      >
        {{ item.page }}
      </button>
    </template>

    <button
      type="button"
      class="inline-flex min-h-11 items-center gap-1 rounded-lg border border-storefront-border px-3 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:opacity-40 storefront-action-secondary"
      :disabled="page >= pages"
      @click="emit('change', page + 1)"
    >
      <span>Дальше</span>
      <ChevronRightIcon class="h-4 w-4 text-storefront-icon" aria-hidden="true" />
    </button>
  </nav>
</template>

<script setup lang="ts">
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/vue/24/outline'

const props = defineProps<{
  page: number
  pages: number
}>()

const emit = defineEmits<{
  change: [page: number]
}>()

interface PaginationItem {
  key: string
  page: number | null
}

const visiblePages = computed<PaginationItem[]>(() => {
  if (props.pages <= 7) {
    return Array.from({ length: props.pages }, (_, index) => ({
      key: `page-${index + 1}`,
      page: index + 1,
    }))
  }

  const candidates = new Set([1, props.pages, props.page - 1, props.page, props.page + 1])
  const sorted = [...candidates].filter((value) => value >= 1 && value <= props.pages).sort((a, b) => a - b)
  const result: PaginationItem[] = []
  sorted.forEach((value, index) => {
    const previous = sorted[index - 1]
    if (previous !== undefined && value - previous > 1) {
      result.push({ key: `ellipsis-${previous}`, page: null })
    }
    result.push({ key: `page-${value}`, page: value })
  })
  return result
})
</script>
