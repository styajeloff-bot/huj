<template>
  <div class="min-w-0">
    <label v-if="label" :for="forId" class="block text-sm font-medium text-gray-700 mb-1">
      {{ label }}<span v-if="required" class="text-red-500"> *</span>
    </label>
    <slot />
    <p v-if="error" role="alert" class="mt-1 text-xs text-red-600">{{ error }}</p>
    <p v-else-if="hint" class="mt-1 text-xs text-gray-500">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
/** Label, control slot and the server/validation message of one form field. */
defineProps<{
  label?: string
  error?: string | null
  hint?: string
  required?: boolean
  forId?: string
}>()
</script>
