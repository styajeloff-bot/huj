<template>
  <article class="rounded-xl border border-gray-200 bg-white p-5">
    <form v-if="editing" class="flex flex-col gap-4" :aria-busy="updating" @submit.prevent="submitEdit">
      <div class="grid grid-cols-2 gap-4">
        <label class="block">
          <span class="mb-1.5 block text-sm font-medium text-gray-800">Название шрифта</span>
          <input
            v-model="draft.name"
            type="text"
            required
            maxlength="120"
            autocomplete="off"
            class="input-field min-h-11"
            :aria-invalid="Boolean(nameError)"
            :aria-describedby="nameError ? `font-${font.id}-name-error` : undefined"
            :disabled="updating"
            @blur="validateName"
          >
          <span v-if="nameError" :id="`font-${font.id}-name-error`" class="mt-1 flex items-center gap-1.5 text-sm text-red-700" role="alert">
            <ExclamationCircleIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
            {{ nameError }}
          </span>
        </label>
        <label class="block">
          <span class="mb-1.5 block text-sm font-medium text-gray-800">Описание <span class="font-normal text-gray-500">(необязательно)</span></span>
          <input
            v-model="draft.description"
            type="text"
            maxlength="500"
            autocomplete="off"
            class="input-field min-h-11"
            :disabled="updating"
          >
        </label>
      </div>
      <p class="text-sm text-gray-500">Файл нельзя заменить при редактировании. Для другого файла загрузите новый шрифт.</p>
      <div v-if="error" class="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
        <ExclamationCircleIcon class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {{ error }}
      </div>
      <div class="flex justify-end gap-3">
        <button type="button" class="btn-secondary min-h-11" :disabled="updating" @click="cancelEdit">Отмена</button>
        <button type="submit" class="btn-primary min-h-11 min-w-36" :disabled="updating">
          <ArrowPathIcon v-if="updating" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {{ updating ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>
    </form>

    <template v-else>
      <div class="flex items-start justify-between gap-6">
        <div class="min-w-0">
          <h3 class="break-words text-base font-semibold leading-6 text-gray-950">{{ font.name }}</h3>
          <p class="mt-1 break-words text-sm leading-5 text-gray-600">{{ font.description || 'Без описания' }}</p>
        </div>
        <span class="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 text-sm font-medium text-blue-800">
          {{ usageLabel }}
        </span>
      </div>

      <dl class="mt-4 grid grid-cols-3 gap-4 border-t border-gray-100 pt-4 text-sm">
        <div class="min-w-0">
          <dt class="text-gray-500">Файл</dt>
          <dd class="mt-1 truncate font-medium text-gray-800" :title="font.original_filename">{{ font.original_filename }}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Размер</dt>
          <dd class="mt-1 font-medium tabular-nums text-gray-800">{{ formattedSize }}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Загружен</dt>
          <dd class="mt-1 font-medium tabular-nums text-gray-800">{{ formattedDate }}</dd>
        </div>
      </dl>

      <div v-if="error" class="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
        <ExclamationCircleIcon class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {{ error }}
      </div>

      <div class="mt-5 flex justify-end gap-3">
        <button type="button" class="btn-secondary min-h-11" :disabled="deleting" @click="startEdit">
          Редактировать
        </button>
        <button
          type="button"
          class="inline-flex min-h-11 items-center justify-center rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 transition-colors duration-200 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none"
          :disabled="deleting"
          @click="confirmDelete"
        >
          <ArrowPathIcon v-if="deleting" class="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {{ deleting ? 'Удаляем…' : 'Удалить' }}
        </button>
      </div>
    </template>
  </article>
</template>

<script setup lang="ts">
import { ArrowPathIcon, ExclamationCircleIcon } from '@heroicons/vue/24/outline'
import type {
  AdminStorefrontFont,
  StorefrontFontMetadataWriteRequest,
} from '~/features/admin/storefronts/api/storefrontsAdminApi'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  font: AdminStorefrontFont
  updating: boolean
  deleting: boolean
  error: string
}>()
const emit = defineEmits<{
  save: [fontId: UUID, body: StorefrontFontMetadataWriteRequest]
  remove: [fontId: UUID]
  dirtyChange: [fontId: UUID, isDirty: boolean]
}>()

const editing = ref(false)
const nameError = ref('')
const draft = reactive({ name: props.font.name, description: props.font.description ?? '' })
const initialSnapshot = computed(() => JSON.stringify({
  name: props.font.name,
  description: props.font.description ?? '',
}))
const draftSnapshot = computed(() => JSON.stringify(draft))
const isDirty = computed(() => editing.value && draftSnapshot.value !== initialSnapshot.value)

const usageLabel = computed(() => {
  const count = props.font.storefront_usage_count
  if (count % 10 === 1 && count % 100 !== 11) return `${count} витрина`
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return `${count} витрины`
  return `${count} витрин`
})
const formattedSize = computed(() => {
  if (props.font.size_bytes < 1024) return `${props.font.size_bytes} Б`
  if (props.font.size_bytes < 1024 * 1024) return `${(props.font.size_bytes / 1024).toFixed(1)} КиБ`
  return `${(props.font.size_bytes / (1024 * 1024)).toFixed(1)} МиБ`
})
const formattedDate = computed(() => new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
}).format(new Date(props.font.created_at)))

const resetDraft = () => {
  draft.name = props.font.name
  draft.description = props.font.description ?? ''
  nameError.value = ''
}

const validateName = (): boolean => {
  const name = draft.name.trim()
  nameError.value = name.length === 0 ? 'Укажите название шрифта' : ''
  return !nameError.value
}

const startEdit = () => {
  resetDraft()
  editing.value = true
}

const cancelEdit = () => {
  if (isDirty.value && !window.confirm('Отменить изменения шрифта? Введённые данные будут потеряны.')) return
  editing.value = false
  resetDraft()
}

const submitEdit = () => {
  if (!validateName()) return
  emit('save', props.font.id, {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
  })
}

const confirmDelete = () => {
  const usageWarning = props.font.storefront_usage_count > 0
    ? ` Шрифт используется в витринах: ${props.font.storefront_usage_count}. Они перейдут на Mulish.`
    : ''
  if (!window.confirm(`Удалить шрифт «${props.font.name}»?${usageWarning} Действие нельзя отменить.`)) return
  emit('remove', props.font.id)
}

watch(isDirty, value => emit('dirtyChange', props.font.id, value), { immediate: true })
watch(() => props.font, () => {
  editing.value = false
  resetDraft()
})
</script>
