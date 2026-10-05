<template>
  <section data-storefront-block="home.advantages" class="bg-storefront-surface py-16">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="mb-4 text-3xl font-bold text-storefront-title">
          Преимущества мультилизинга
        </h2>
        <p class="mx-auto max-w-3xl text-lg text-storefront-text-muted">
          Получите максимальную выгоду от сотрудничества с ведущими лизинговыми компаниями
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div 
          v-for="advantage in advantages" 
          :key="advantage.id"
          class="rounded-storefront-surface bg-storefront-surface-muted p-6 text-center transition-shadow duration-200 hover:shadow-md"
        >
          <div 
            class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-storefront-inner"
            :class="advantage.bgColor"
          >
            <component :is="advantage.icon" :class="['w-7 h-7', advantage.iconColor]" />
          </div>
          <h3 class="mb-2 text-lg font-semibold text-storefront-title">{{ advantage.title }}</h3>
          <p class="text-sm leading-relaxed text-storefront-text-muted">
            {{ advantage.description }}
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { h } from 'vue'

const MoneyIcon = () => h('span', {
  class: 'inline-flex items-center justify-center font-bold leading-none',
  'aria-hidden': 'true'
}, '₽')

const LightningIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M13 10V3L4 14h7v7l9-11h-7z'
  })
])

const ShieldIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z'
  })
])

const DocumentIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'
  })
])

const HeartIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z'
  })
])

const CloudIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z'
  })
])

const advantages = [
  {
    id: 1,
    title: 'Выгодные условия',
    description: 'Гибкие предложения от лизинговых компаний',
    icon: MoneyIcon,
    bgColor: 'bg-storefront-conditions-accent',
    iconColor: 'text-storefront-conditions-accent-icon'
  },
  {
    id: 2,
    title: 'Быстрое решение',
    description: 'Рассмотрение заявки в течение 1 рабочего дня',
    icon: LightningIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-success-icon,#16a34a)]'
  },
  {
    id: 3,
    title: 'Надежность',
    description: 'Работаем только с проверенными лизинговыми компаниями',
    icon: ShieldIcon,
    bgColor: 'bg-storefront-reliability-accent',
    iconColor: 'text-storefront-reliability-accent-icon'
  },
  {
    id: 4,
    title: 'Минимум документов',
    description: 'Упрощенный пакет документов для оформления лизинга',
    icon: DocumentIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-warning-icon,#d97706)]'
  },
  {
    id: 5,
    title: 'Персональный сервис',
    description: 'Индивидуальный подход к каждому клиенту',
    icon: HeartIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-error-rgb,255_228_230)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-error-icon,#e11d48)]'
  },
  {
    id: 6,
    title: 'Онлайн платформа',
    description: 'Удобное управление заявками через личный кабинет',
    icon: CloudIcon,
    bgColor: 'bg-storefront-platform-accent',
    iconColor: 'text-storefront-platform-accent-icon'
  }
]
</script>
