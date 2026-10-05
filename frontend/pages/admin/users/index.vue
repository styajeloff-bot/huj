<template>
  <div class="min-h-screen bg-gray-50 py-8">
    <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-gray-900">
          Администрирование пользователей
        </h1>
        <p class="mt-2 text-gray-600">
          Поиск пользователя по ID или телефону для управления сессиями и статусом.
        </p>
      </div>

      <div class="bg-white rounded-lg shadow p-6">
        <form class="flex flex-col sm:flex-row gap-3" @submit.prevent="handleSubmit">
          <input
            v-model="query"
            type="text"
            placeholder="ID пользователя или +7 номер"
            class="input-field flex-1"
            required
          >
          <button
            type="submit"
            :disabled="searching || !query.trim()"
            class="btn-primary whitespace-nowrap disabled:opacity-50"
          >
            {{ searching ? 'Ищем...' : 'Открыть' }}
          </button>
        </form>
        <p class="mt-3 text-xs text-gray-500">
          При вводе численного ID открывается карточка пользователя напрямую.
          Поиск по телефону поддерживается, если backend реализует
          <code>/api/v1/users?phone=...</code>.
        </p>
        <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-admin']
})

useHead({ title: 'Пользователи (админ) — CarCraft Multileasing' })

const router = useRouter()

const query = ref('')
const error = ref('')
const searching = ref(false)

const handleSubmit = async () => {
  error.value = ''
  const raw = query.value.trim()
  if (!raw) return

  // Numeric → direct navigation.
  if (/^\d+$/.test(raw)) {
    searching.value = true
    await router.push(`/admin/users/${raw}`)
    searching.value = false
    return
  }

  // Phone / other string: we don't have a dedicated search endpoint in the
  // provided spec. Surface a clear message so the admin can enter an ID.
  // NOTE: when the backend exposes a lookup endpoint, wire it here.
  error.value =
    'Поиск по телефону пока не поддерживается. Введите численный ID пользователя.'
}
</script>
