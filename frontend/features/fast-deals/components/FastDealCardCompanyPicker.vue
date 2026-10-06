<template>
  <div class="space-y-2 min-w-0">
    <ul v-if="modelValue.length" class="flex flex-wrap gap-2" aria-label="Выбранные компании">
      <li
        v-for="id in modelValue"
        :key="id"
        class="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-200 px-3 py-1 text-sm text-blue-900"
      >
        {{ nameOf(id) }}
        <button
          type="button"
          class="text-blue-500 hover:text-red-600"
          :aria-label="`Убрать: ${nameOf(id)}`"
          :disabled="disabled"
          @click="remove(id)"
        >
          ×
        </button>
      </li>
    </ul>

    <input
      v-model="query"
      type="search"
      class="input-field"
      :placeholder="placeholder"
      :disabled="disabled"
      autocomplete="off"
      :aria-label="placeholder"
    />

    <div class="max-h-52 overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-100">
      <p v-if="loading" class="px-3 py-2 text-sm text-gray-500">Поиск…</p>
      <p v-else-if="failed" class="px-3 py-2 text-sm text-red-600" role="alert">
        Не удалось загрузить список.
        <button type="button" class="underline" @click="search">Повторить</button>
      </p>
      <p v-else-if="!results.length" class="px-3 py-2 text-sm text-gray-500">Ничего не найдено</p>
      <label
        v-for="item in results"
        :key="String(item.id)"
        class="flex items-start gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-gray-50"
      >
        <input
          :type="multiple ? 'checkbox' : 'radio'"
          :checked="modelValue.includes(String(item.id))"
          :disabled="disabled"
          class="mt-0.5 text-blue-600"
          @change="toggle(item)"
        />
        <span class="min-w-0">
          <span class="block text-gray-900">{{ lookupName(item) }}</span>
          <span v-if="innOf(item)" class="block text-xs text-gray-500">ИНН {{ innOf(item) }}</span>
        </span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { UUID } from '~/types/ids'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import { lookupName, lookupText } from '../composables/fastDealCardFormat'
import type { LookupItem } from '../api/fastDealsApi'

const props = withDefaults(defineProps<{
  kind: 'dealers' | 'leasing-companies'
  modelValue: UUID[]
  multiple?: boolean
  disabled?: boolean
  placeholder?: string
}>(), {
  multiple: false,
  disabled: false,
  placeholder: 'Поиск по названию или ИНН',
})

const emit = defineEmits<{ 'update:modelValue': [value: UUID[]] }>()

const ctx = useFastDealCardContext()
const query = ref('')
const results = ref<LookupItem[]>([])
const loading = ref(false)
const failed = ref(false)
let generation = 0
let timer: ReturnType<typeof setTimeout> | null = null

const innOf = (item: LookupItem) => lookupText(item, 'inn')
const nameOf = (id: UUID) => ctx.companyName(id) || 'Компания выбрана'

async function search() {
  const current = ++generation
  loading.value = true
  failed.value = false
  try {
    const text = query.value.trim()
    const response = await ctx.api.lookup(props.kind, text ? { q: text } : {})
    if (current !== generation) return
    results.value = response.items
    for (const item of response.items) ctx.rememberCompany(String(item.id), lookupName(item))
  } catch {
    if (current === generation) {
      results.value = []
      failed.value = true
    }
  } finally {
    if (current === generation) loading.value = false
  }
}

function toggle(item: LookupItem) {
  const id = String(item.id)
  ctx.rememberCompany(id, lookupName(item))
  if (!props.multiple) {
    emit('update:modelValue', [id])
    return
  }
  emit('update:modelValue', props.modelValue.includes(id) ? props.modelValue.filter(value => value !== id) : [...props.modelValue, id])
}

function remove(id: UUID) {
  emit('update:modelValue', props.modelValue.filter(value => value !== id))
}

watch(query, () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(search, 300)
})
onMounted(search)
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>
