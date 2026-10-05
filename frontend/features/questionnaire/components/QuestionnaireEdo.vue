<template>
  <section class="space-y-3 rounded-lg border p-4">
    <h5 class="font-medium">Используемые системы электронного документооборота</h5>
    <div class="flex flex-wrap gap-5"><label v-for="item in options" :key="item.key" class="flex items-center gap-2 text-sm"><input :checked="data[item.key]" :name="`edo.${item.key}`" type="checkbox" @change="toggle(item.key, ($event.target as HTMLInputElement).checked)">{{ item.label }}</label></div>
    <label v-if="data.other" class="block text-sm">Название другой системы ЭДО <span class="text-red-700">*</span><input :value="data.other_name" name="edo.other_name" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2" @input="update({ ...data, other_name: ($event.target as HTMLInputElement).value })"></label>
    <p v-if="data.other && !data.other_name.trim()" class="text-sm text-red-700">Укажите название другой системы ЭДО</p>
  </section>
</template>
<script setup lang="ts">
import type { ElectronicDocumentSystems } from '~/features/questionnaire/types'
const props = defineProps<{ modelValue?: ElectronicDocumentSystems }>()
const emit = defineEmits<{ 'update:modelValue': [data: ElectronicDocumentSystems] }>()
const empty = (): ElectronicDocumentSystems => ({ sbis: false, diadoc: false, kontur: false, other: false, other_name: '', not_used: false })
const data = computed(() => ({ ...empty(), ...props.modelValue, other_name: props.modelValue?.other_name || '' }))
type SystemKey = 'sbis' | 'diadoc' | 'kontur' | 'other' | 'not_used'
const options: Array<{ key: SystemKey; label: string }> = [{ key: 'sbis', label: 'СБИС' }, { key: 'diadoc', label: 'Диадок' }, { key: 'kontur', label: 'Контур' }, { key: 'other', label: 'Другая система ЭДО' }, { key: 'not_used', label: 'Системы ЭДО не используются' }]
const update = (value: ElectronicDocumentSystems) => emit('update:modelValue', value)
const toggle = (key: SystemKey, checked: boolean) => { const next = { ...data.value, [key]: checked }; if (key === 'not_used' && checked) { update({ ...empty(), not_used: true }); return }; if (key !== 'not_used' && checked) next.not_used = false; if (!next.other) next.other_name = ''; update(next) }
const validate = () => !data.value.other || Boolean(data.value.other_name.trim())
defineExpose({ validate })
</script>
