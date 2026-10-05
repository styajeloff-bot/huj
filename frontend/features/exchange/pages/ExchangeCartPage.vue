<template>
  <div class="min-h-screen bg-gray-50 py-8">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-gray-900">Корзина биржи ТС</h1>
        <p class="mt-2 text-gray-600">Настройте параметры заявок и отправьте их дилерам</p>
      </div>

      <!-- Loading -->
      <div v-if="cartStore.loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>

      <!-- Empty cart -->
      <div v-else-if="cartStore.isEmpty" class="text-center py-12">
        <div class="max-w-md mx-auto">
          <svg class="h-24 w-24 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6h13.5l-1.5 9H8.5L6 6z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6L4 4H2" />
            <circle cx="9" cy="20" r="1.5" stroke-width="2" />
            <circle cx="18" cy="20" r="1.5" stroke-width="2" />
          </svg>
          <h3 class="text-lg font-medium text-gray-900 mb-2">Корзина биржи пуста</h3>
          <p class="text-gray-600 mb-6">Добавьте спецтехнику из каталога для создания заявок на бирже</p>
          <NuxtLink :to="publicRoute('/special-equipment')" class="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">
            Перейти к каталогу
          </NuxtLink>
        </div>
      </div>

      <!-- Cart content -->
      <div v-else>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Cart items -->
          <div class="lg:col-span-2 space-y-4">
            <div class="flex items-center justify-between mb-2">
              <h2 class="text-lg font-medium text-gray-900">
                Автомобили ({{ cartStore.totalItems }})
              </h2>
              <button @click="handleClear" class="text-sm text-red-600 hover:text-red-700">
                Очистить
              </button>
            </div>

            <ExchangeCartItemCard
              v-for="item in cartStore.items"
              :key="item.id"
              :item="item"
              @remove="handleRemove"
            />
          </div>

          <!-- Summary sidebar -->
          <div class="lg:col-span-1">
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sticky top-6">
              <h3 class="text-lg font-semibold text-gray-900 mb-4">Итого</h3>

              <div class="space-y-2 mb-6">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Позиций:</span>
                  <span class="font-medium">{{ cartStore.totalItems }}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Итого (базовая):</span>
                  <span class="font-medium">{{ formatPrice(cartStore.totalAmount) }}</span>
                </div>
              </div>

              <!-- Validation message -->
              <div v-if="!cartStore.isValid" class="text-xs text-red-600 mb-4">
                Для каждого автомобиля необходимо выбрать хотя бы один склад
              </div>

              <button
                @click="handleSubmit"
                :disabled="!cartStore.isValid || cartStore.submitting"
                class="w-full py-3 px-4 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {{ cartStore.submitting ? 'Отправка...' : 'Отправить заявку' }}
              </button>

              <p class="text-xs text-gray-400 mt-3 text-center">
                Будут созданы заявки на бирже для выбранных дилеров
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Success modal -->
    <div v-if="submitResult" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-sm mx-4 text-center">
        <svg class="w-16 h-16 text-green-500 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <h3 class="text-lg font-semibold mb-2">Заявки отправлены!</h3>
        <p class="text-sm text-gray-600 mb-4">Создано {{ submitResult.count }} заявок. Дилеры получат уведомления.</p>
        <div class="flex gap-2 justify-center">
          <NuxtLink to="/workspace/exchange" class="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700">
            Перейти к заявкам
          </NuxtLink>
          <NuxtLink :to="publicRoute('/special-equipment')" class="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50">
            Продолжить выбор
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { ref, onMounted } from 'vue'
import ExchangeCartItemCard from '../components/ExchangeCartItemCard.vue'
import { useExchangeCartStore } from '../store/exchangeCart'
import type { UUID } from '~/types/ids'

const cartStore = useExchangeCartStore()
const { publicRoute } = useStorefront()
const submitResult = ref<{ count: number; request_ids: UUID[] } | null>(null)
const { formatPrice: formatSharedPrice } = useFormatPrice()

function formatPrice(price: number) {
  return formatSharedPrice(price)
}

function handleRemove(itemId: UUID) {
  cartStore.removeItem(itemId)
}

function handleClear() {
  if (confirm('Очистить корзину биржи?')) {
    cartStore.clearCart()
  }
}

async function handleSubmit() {
  try {
    const result = await cartStore.submitCart()
    submitResult.value = result
  } catch (error) {
    console.error('Submit failed:', error)
  }
}

onMounted(() => {
  cartStore.fetchCart()
})
</script>
