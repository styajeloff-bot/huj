<template>
  <Modal
    :show="show"
    :title="isEditing ? 'Редактировать должность' : 'Создать должность'"
    size="md"
    :show-footer="false"
    @close="$emit('close')"
  >
    <div
      v-if="error"
      class="p-3 mb-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg"
    >
      {{ error }}
    </div>

    <form @submit.prevent="handleSubmit">
      <div class="space-y-4">
        <!-- Название -->
        <div>
          <label for="pos-name" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Название <span class="text-red-500">*</span>
          </label>
          <input
            id="pos-name"
            v-model="form.name"
            type="text"
            required
            placeholder="Например, Менеджер отдела продаж"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          />
        </div>

        <!-- Системный код -->
        <div>
          <label for="pos-code" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Системный код <span class="text-red-500">*</span>
          </label>
          <input
            id="pos-code"
            v-model="form.code"
            type="text"
            required
            placeholder="например, manager, supervisor"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm font-mono"
          />
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Уникальный код на английском (например, manager, supervisor, sales_agent)
          </p>
        </div>

        <!-- Активность -->
        <div class="flex items-center justify-between pt-2">
          <div>
            <span class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">Активность</span>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ form.is_active ? 'Должность активна и доступна для выбора' : 'Должность отключена' }}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            :aria-checked="form.is_active"
            :class="[
              form.is_active ? 'bg-blue-600' : 'bg-gray-200',
              'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
            ]"
            @click="form.is_active = !form.is_active"
          >
            <span class="sr-only">Переключить активность должности</span>
            <span
              :class="[
                form.is_active ? 'translate-x-5' : 'translate-x-0',
                'pointer-events-none relative inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
              ]"
            />
          </button>
        </div>
      </div>

      <div class="mt-6 flex justify-end gap-3 border-t border-[color:var(--storefront-border,#e5e7eb)] pt-4">
        <button
          type="button"
          class="btn-secondary"
          :disabled="loading"
          @click="$emit('close')"
        >
          Отмена
        </button>
        <button
          type="submit"
          :disabled="loading || !isValid"
          class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Сохранение...' : 'Сохранить' }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '~/components/ui/Modal.vue'
import {
  createPosition,
  updatePosition,
  type PositionItem,
} from '../api/employeesApi'

const props = withDefaults(
  defineProps<{
    show?: boolean
    position?: PositionItem | null
  }>(),
  {
    show: true,
    position: null,
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', position: PositionItem): void
}>()

const config = useRuntimeConfig()

const isEditing = computed(() => !!props.position?.id)

const form = ref({
  name: '',
  code: '',
  is_active: true,
})

const loading = ref(false)
const error = ref('')

const isValid = computed(() => {
  return form.value.name.trim().length > 0 && form.value.code.trim().length > 0
})

watch(
  () => props.position,
  (val) => {
    if (val) {
      form.value = {
        name: val.name || '',
        code: val.code || '',
        is_active: val.is_active ?? true,
      }
    } else {
      form.value = {
        name: '',
        code: '',
        is_active: true,
      }
    }
    error.value = ''
  },
  { immediate: true },
)

const handleSubmit = async () => {
  if (!isValid.value || loading.value) return
  loading.value = true
  error.value = ''

  try {
    let result: PositionItem
    if (isEditing.value && props.position?.id) {
      result = await updatePosition(config, props.position.id, {
        name: form.value.name.trim(),
        code: form.value.code.trim(),
        is_active: form.value.is_active,
      })
    } else {
      result = await createPosition(config, {
        name: form.value.name.trim(),
        code: form.value.code.trim(),
        is_active: form.value.is_active,
      })
    }

    emit('saved', result)
    emit('close')
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Не удалось сохранить должность'
  } finally {
    loading.value = false
  }
}
</script>
