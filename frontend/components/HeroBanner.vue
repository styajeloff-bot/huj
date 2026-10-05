<template>
  <section data-storefront-block="home.hero" class="relative bg-storefront-background text-storefront-text">

    <div class="relative max-w-7xl mx-auto py-24 px-4 sm:px-6 lg:px-8">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        <div>
          <h1 class="mb-6 text-4xl font-bold leading-tight text-storefront-title md:text-5xl">
            Мы — больше, чем лизинг
          </h1>
          <p class="mb-8 text-xl leading-relaxed text-storefront-text-muted">
            Подай одну заявку — получи несколько одобрений на особых условиях для юридических лиц
          </p>
          <div class="flex flex-col sm:flex-row gap-4">
            <NuxtLink 
              :to="publicRoute('/special-equipment')"
              class="btn-primary px-[98px] py-3.5 font-semibold"
            >
            Оформить заявку
            </NuxtLink>
          </div>
        </div>

        <div class="hidden lg:block">
          <div class="relative">
            <img 
              src="/images/hero-car.png" 
              alt="Автомобиль в лизинг" 
              class="w-full h-auto"
            >
          </div>
        </div>
      </div>
    </div>

  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'

const { publicRoute } = useStorefront()
</script>
