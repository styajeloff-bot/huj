<template>
  <Teleport to="body"><dialog ref="dialog" :aria-labelledby="titleId" class="dr-modal" :class="{ 'dr-modal-wide': wide }" @cancel.prevent="close" @close="emit('close')">
    <div class="dr-modal-heading"><h2 :id="titleId">{{ title }}</h2><button type="button" class="dr-icon-button" aria-label="Закрыть" :disabled="busy" @click="close">×</button></div>
    <slot />
  </dialog></Teleport>
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, useId } from 'vue'
const props = defineProps<{ title: string; busy?: boolean; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const titleId = useId()
const dialog = ref<HTMLDialogElement | null>(null)
function close() { if (!props.busy) dialog.value?.close() }
onMounted(() => dialog.value?.showModal())
onBeforeUnmount(() => dialog.value?.close())
</script>
