<template>
  <div class="contract-upload" @dragover.prevent="dragging = !disabled" @dragleave.prevent="dragging = false" @drop.prevent="drop">
    <input ref="input" class="contract-file-input" type="file" multiple :disabled="disabled" @change="choose" />
    <button type="button" class="contract-dropzone" :class="{ dragging }" :disabled="disabled" @click="input?.click()">Перетащите файлы или нажмите, чтобы выбрать (можно несколько)</button>
    <ul v-if="modelValue.length" class="pending-files">
      <li v-for="(file, index) in modelValue" :key="index"><span>{{ file.name }}</span><button type="button" class="link" :disabled="disabled" :aria-label="'Удалить файл ' + file.name" @click="remove(index)">Удалить</button></li>
    </ul>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
const props = withDefaults(defineProps<{ modelValue: File[]; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ 'update:modelValue': [files: File[]] }>()
const input = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
function append(files: File[]) {
  if (props.disabled) return
  const next = [...props.modelValue]
  for (const file of files) if (!next.some(existing => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) next.push(file)
  emit('update:modelValue', next)
}
function choose(event: Event) {
  const target = event.target as HTMLInputElement
  append(Array.from(target.files ?? []))
  target.value = ''
}
function drop(event: DragEvent) { dragging.value = false; append(Array.from(event.dataTransfer?.files ?? [])) }
function remove(index: number) { emit('update:modelValue', props.modelValue.filter((_, fileIndex) => fileIndex !== index)) }
</script>
