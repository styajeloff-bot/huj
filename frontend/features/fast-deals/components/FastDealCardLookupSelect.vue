<template>
  <div class="min-w-0">
    <select
      :id="id"
      :value="modelValue"
      class="select-field"
      :class="error ? 'error' : ''"
      :disabled="disabled || loading || blocked"
      @change="onChange"
    >
      <option value="">{{ loading ? 'Загрузка…' : placeholder }}</option>
      <option v-for="item in items" :key="String(item.id)" :value="String(item.id)">{{ lookupName(item) }}</option>
    </select>
    <p v-if="loadFailed" class="mt-1 text-xs text-red-600" role="alert">
      Не удалось загрузить справочник.
      <button type="button" class="underline" @click="load">Повторить</button>
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import { lookupName } from '../composables/fastDealCardFormat'
import type { FastDealsApi, LookupItem } from '../api/fastDealsApi'

type LookupKind = Parameters<FastDealsApi['lookup']>[0]

const props = withDefaults(defineProps<{
  kind: LookupKind
  modelValue: string
  /** Query of the directory (`mark_id`, `model_id`, ...). Empty values are not sent. */
  params?: Record<string, string | undefined>
  /** Params that must be filled before the directory is loaded (the select stays empty until then). */
  requires?: string[]
  placeholder?: string
  disabled?: boolean
  error?: boolean
  id?: string
}>(), {
  params: () => ({}),
  requires: () => [],
  placeholder: 'Выберите',
  disabled: false,
  error: false,
  id: undefined,
})

const emit = defineEmits<{ 'update:modelValue': [value: string]; select: [item: LookupItem | null] }>()

const ctx = useFastDealCardContext()
const items = ref<LookupItem[]>([])
const loading = ref(false)
const loadFailed = ref(false)
let generation = 0

const blocked = computed(() => props.requires.some(key => !props.params?.[key]))

async function load() {
  const current = ++generation
  loadFailed.value = false
  if (blocked.value) {
    items.value = []
    return
  }
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(props.params ?? {})) {
    if (value) query[key] = value
  }
  loading.value = true
  try {
    const response = await ctx.api.lookup(props.kind, query)
    if (current === generation) items.value = response.items
  } catch {
    if (current === generation) {
      items.value = []
      loadFailed.value = true
    }
  } finally {
    if (current === generation) loading.value = false
  }
}

function onChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update:modelValue', value)
  emit('select', items.value.find(item => String(item.id) === value) ?? null)
}

onMounted(load)
watch(() => JSON.stringify([props.kind, props.params]), load)
</script>
