<template>
  <section data-storefront-block="home.steps" class="bg-storefront-background py-16">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="mb-4 text-3xl font-bold text-storefront-title">
          Как получить автомобиль?
        </h2>
        <p class="mx-auto max-w-3xl text-lg text-storefront-text-muted">
          Простой процесс получения автомобиля в лизинг
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div 
          v-for="step in steps" 
          :key="step.id"
          class="rounded-storefront-surface bg-storefront-surface p-6 text-center transition-shadow duration-200 hover:shadow-md"
        >
          <div>
            <div 
              class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-storefront-inner"
              :class="step.bgColor"
            >
              <component :is="step.icon" :class="['w-7 h-7', step.iconColor]" />
            </div>
            
            <h3 class="mb-2 text-lg font-semibold text-storefront-title">
              {{ step.title }}
            </h3>
            
            <p class="text-sm leading-relaxed text-storefront-text-muted">
              {{ step.description }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { h } from 'vue'

const DocumentIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
  })
])

const SendIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8'
  })
])

const CheckIcon = () => h('svg', {
  fill: 'none',
  stroke: 'currentColor',
  viewBox: '0 0 24 24'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'
  })
])

const CarIcon = () => h('svg', {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '1.5',
    d: 'M2.45,17.73H7.23v2.86a1,1,0,0,1-1,1H3.41a1,1,0,0,1-1-1V17.73Z'
  }),
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '1.5',
    d: 'M16.77,17.73h4.77v2.86a1,1,0,0,1-1,1H17.73a1,1,0,0,1-1-1V17.73Z'
  }),
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '1.5',
    d: 'M5.32,9.14H18.68A3.82,3.82,0,0,1,22.5,13v4.77H1.5V13A3.82,3.82,0,0,1,5.32,9.14Z'
  }),
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '1.5',
    d: 'M16.29,2.45H7.71A1.91,1.91,0,0,0,5.88,3.84L4.36,9.14H19.64l-1.52-5.3A1.91,1.91,0,0,0,16.29,2.45Z'
  }),
  h('circle', {
    cx: '4.84',
    cy: '13.43',
    r: '1.43',
    fill: 'currentColor'
  }),
  h('circle', {
    cx: '19.16',
    cy: '13.43',
    r: '1.43',
    fill: 'currentColor'
  }),
  h('line', {
    x1: '22.5',
    y1: '7.23',
    x2: '19.09',
    y2: '7.23',
    'stroke-linecap': 'round',
    'stroke-width': '1.5'
  }),
  h('line', {
    x1: '4.91',
    y1: '7.23',
    x2: '1.5',
    y2: '7.23',
    'stroke-linecap': 'round',
    'stroke-width': '1.5'
  })
])

const steps = [
  {
    id: 1,
    title: 'Создайте заявку',
    description: 'Заполните онлайн-форму с вашими данными и выберите автомобиль',
    icon: DocumentIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-icon,#2563eb)]'
  },
  {
    id: 2,
    title: 'Отправьте заявку',
    description: 'Мы автоматически отправим вашу заявку в несколько лизинговых компаний',
    icon: SendIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-info-icon,#9333ea)]'
  },
  {
    id: 3,
    title: 'Получите одобрение',
    description: 'Дождитесь решения от лизинговых компаний и выберите лучшие условия',
    icon: CheckIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-success-icon,#16a34a)]'
  },
  {
    id: 4,
    title: 'Заберите автомобиль',
    description: 'Подпишите договор и получите ключи от вашего нового автомобиля',
    icon: CarIcon,
    bgColor: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))]',
    iconColor: 'text-[color:var(--storefront-warning-icon,#d97706)]'
  }
]
</script>
