<template>
  <div class="participant-list">
    <p v-for="item in unique" :key="item.key">{{ item.label }}</p>
    <span v-if="!unique.length" class="muted">—</span>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { participantLabels } from '../editor'
import type { ParticipantSummary } from '../types'
const props = withDefaults(defineProps<{ participants: ParticipantSummary[]; wildcard?: boolean }>(), { wildcard: false })
const unique = computed(() => {
  const seen = new Set<string>()
  return props.participants.flatMap(item => {
    const key = `${item.participant_type}:${item.company?.id ?? 'unassigned'}`
    if (seen.has(key)) return []
    seen.add(key)
    const label = item.participant_type === 'platform' ? participantLabels.platform
      : item.company ? `${participantLabels[item.participant_type]} — ${item.company.name}`
      : props.wildcard && item.participant_type === 'dealer' ? 'Любой дилер'
      : props.wildcard && item.participant_type === 'distributor' ? 'Любой дистрибьютор'
      : participantLabels[item.participant_type]
    return [{ key, label }]
  })
})
</script>
<style scoped>
.participant-list { min-width:170px; overflow-wrap:anywhere; }
.participant-list p { margin:0 0 6px; }
</style>
