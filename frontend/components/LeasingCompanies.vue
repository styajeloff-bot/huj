<template>
  <section data-storefront-block="home.companies" class="bg-storefront-background py-16">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="mb-4 text-3xl font-bold text-storefront-title">
          Наши партнеры
        </h2>
        <p class="mx-auto max-w-3xl text-lg text-storefront-text-muted">
          Работаем с ведущими лизинговыми компаниями России
        </p>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6">
        <div
          v-for="company in partnersData"
          :key="company.id"
          class="flex items-center justify-center rounded-storefront-surface bg-storefront-surface p-6 shadow-sm transition-shadow duration-200 hover:shadow-md"
        >
          <img
            v-if="company.logo && !imageErrors[company.id]"
            :src="`/images/partners/${company.logo}`"
            :alt="company.name"
            :class="[
              company.logoClass || 'h-12',
              'w-auto max-w-full object-contain grayscale hover:grayscale-0 transition-all duration-200'
            ]"
            @error="() => imageErrors[company.id] = true"
          >
          <div
            v-else
            class="flex h-12 items-center justify-center text-center text-sm font-medium text-storefront-text-muted"
          >
            {{ company.name }}
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const partnersData = [
  {
    id: 1,
    name: 'Альфа Лизинг',
    logo: 'alfa_lizing_logo.svg'
  },
  {
    id: 2,
    name: 'ГазпромАвтолизинг',
    logo: 'gazpromavtolizing_logo.svg'
  },
  {
    id: 3,
    name: 'ИнтерЛизинг',
    logo: 'inter_lizing_logo.svg'
  },
  {
    id: 4,
    name: 'РЕСО Лизинг',
    logo: 'pecolizing_logo.svg'
  },
  {
    id: 5,
    name: 'Сбербанк Лизинг',
    logo: 'sberbank_lizing_logo.svg'
  },
  {
    id: 6,
    name: 'Балтийский лизинг',
    logo: 'baltijskij_lizing_logo.svg'
  },
  {
    id: 7,
    name: 'ВТБ Лизинг',
    logo: 'vtb-leasing-large.png',
    logoClass: 'h-16'
  },
  {
    id: 8,
    name: 'Каркаде',
    logo: 'karkade.png'
  },
  {
    id: 9,
    name: 'Контрол Лизинг',
    logo: 'control-leasing-large.png',
    logoClass: 'h-16'
  },
  {
    id: 10,
    name: 'МСБ Лизинг',
    logo: 'msb-leasing.png'
  },
  {
    id: 11,
    name: 'Директ Лизинг',
    logo: 'direct-leasing.png',
    logoClass: 'h-20'
  }
]

const imageErrors = ref<Record<number, boolean>>({})
</script>
