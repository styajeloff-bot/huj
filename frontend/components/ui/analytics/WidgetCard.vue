<template>
  <div class="widget-card">
    <div v-if="title || $slots.header" class="widget-header">
      <slot name="header">
        <h3 class="widget-title" :title="title">{{ title }}</h3>
        <slot name="actions" />
      </slot>
    </div>
    <div class="widget-body" :class="{ 'widget-body_no-header': !title && !$slots.header }">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
}>()
</script>

<style scoped>
.widget-card {
  background: var(--storefront-surface, #ffffff);
  border-radius: 4px;
  box-shadow: 0 1px 2px rgb(var(--storefront-shadow-rgb, 0 0 0) / 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.widget-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 0;
  flex-shrink: 0;
}

.widget-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--storefront-title, #111827);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.widget-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 12px 16px 16px;
  display: flex;
  flex-direction: column;
}

.widget-body_no-header {
  padding-top: 16px;
}

.widget-card :deep(.overflow-x-auto) {
  max-width: 100%;
}

.widget-card :deep(table) {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  table-layout: auto;
}

.widget-card :deep(th),
.widget-card :deep(td) {
  box-sizing: border-box;
  vertical-align: middle;
}

.widget-card :deep(th) {
  width: 1%;
  min-width: 88px;
  max-width: 148px;
  white-space: normal;
  overflow-wrap: normal;
  line-height: 1.25;
  vertical-align: bottom;
}

.widget-card :deep(td) {
  white-space: nowrap;
}

.widget-card :deep(th.text-right),
.widget-card :deep(td.text-right) {
  font-variant-numeric: tabular-nums;
}
</style>
