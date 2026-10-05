<template>
  <div class="dash-grid">
    <WidgetCard class="chart-wide">
      <div class="empty-state">
        <p class="empty-title">Раздел пока не реализован</p>
        <p class="empty-text">Анализ по сотрудникам будет доступен после появления командной витрины данных.</p>
      </div>
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
</script>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
  align-items: start;
}

.chart-wide {
  grid-column: span 12;
}

.empty-state {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 32px 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.empty-text {
  margin-top: 6px;
  max-width: 420px;
  font-size: 13px;
  line-height: 1.5;
  color: #64748b;
}
</style>
