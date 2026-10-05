<template>
  <div class="[overflow-anchor:none] [overflow-wrap:anywhere]">
    <StorefrontPageRenderer :layout="pageLayout">
      <template #fallback>
        <div>
    <!-- Hero Section -->
    <section data-storefront-block="about.hero" class="relative text-[color:var(--storefront-text,#1f2937)]"
      style="background: radial-gradient(circle, var(--storefront-gradient-from,rgb(230, 231, 235)) 0%, var(--storefront-gradient-to,rgb(192, 199, 200)) 100%)">
      <div class="relative max-w-7xl mx-auto py-24 px-4 sm:px-6 lg:px-8">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div>
            <h1 class="mb-6 text-4xl font-bold leading-tight text-storefront-title md:text-5xl">
              {{ pageTitle('about') }}
            </h1>
            <p class="text-xl text-[color:var(--storefront-text,#374151)] mb-8 leading-relaxed">
              Ведущая лизинговая платформа России. Мы объединяем автодилеров и лизинговые компании в
              единую экосистему.
            </p>
            <div class="flex flex-col sm:flex-row gap-4">
              <NuxtLink :to="publicRoute('/special-equipment')"
                class="storefront-action-primary rounded-storefront-control bg-storefront-primary font-semibold text-storefront-primary-foreground transition-colors duration-200 hover:bg-storefront-primary-hover"
                style="padding: 14px 98px;">
                Перейти в каталог
              </NuxtLink>
            </div>
          </div>
          <div class="hidden lg:block">
            <div class="relative">
              <img src="/images/hero-car.png" alt="CarCraft Multileasing" class="w-full h-auto">
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Mission Section -->
    <section data-storefront-block="about.mission" class="py-16 bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">
            Наша миссия
          </h2>
          <p class="text-lg text-[color:var(--storefront-text-muted,#4b5563)] max-w-3xl mx-auto">
            Мы создаём технологичные решения, которые упрощают процесс оформления лизинга и делают его максимально
            прозрачным для всех участников
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div class="card text-center">
            <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-storefront-control bg-storefront-primary-muted">
              <svg class="h-8 w-8 text-storefront-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Скорость</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Быстрое оформление заявок и получение решений от лизинговых компаний
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Надёжность</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Безопасная работа с данными и проверенные лизинговые партнёры
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-info-icon,#9333ea)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Партнёрство</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Долгосрочные отношения с клиентами и лизинговыми компаниями
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Why Choose Us Section -->
    <section data-storefront-block="about.advantages" class="py-16 bg-[color:rgb(var(--storefront-background-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">
            Почему выбирают нас
          </h2>
          <p class="text-lg text-[color:var(--storefront-text-muted,#4b5563)]">
            Преимущества работы с платформой CarCraft Multileasing
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <div class="card text-center">
            <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-storefront-control bg-storefront-primary-muted">
              <svg class="h-8 w-8 text-storefront-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Быстрое оформление</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Подача заявки занимает несколько минут. Решение по лизингу — в течение дня.
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Множество партнёров</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Работаем с ведущими лизинговыми компаниями России для лучших условий.
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-info-icon,#9333ea)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Безопасность данных</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Все данные защищены современными технологиями шифрования.
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-warning-rgb,255_237_213)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-warning-icon,#ea580c)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Минимум документов</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Упрощённый пакет документов для оформления лизинга.
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-error-icon,#dc2626)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Персональный сервис</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Индивидуальный подход к каждому клиенту и партнёру.
            </p>
          </div>

          <div class="card text-center">
            <div class="w-16 h-16 bg-[color:rgb(var(--storefront-info-rgb,224_231_255)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-[color:var(--storefront-info-icon,#4f46e5)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
              </svg>
            </div>
            <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Онлайн платформа</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)]">
              Удобное управление заявками через личный кабинет.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Statistics Section -->
    <section data-storefront-block="about.process" class="py-16 bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">
            CarCraft в цифрах
          </h2>
          <p class="text-lg text-[color:var(--storefront-text-muted,#4b5563)]">
            Наши достижения за время работы платформы
          </p>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-8">
          <div class="text-center">
            <div class="mb-2 text-4xl font-bold text-storefront-primary md:text-5xl">500+</div>
            <div class="text-[color:var(--storefront-text-muted,#4b5563)]">Автодилеров</div>
          </div>
          <div class="text-center">
            <div class="mb-2 text-4xl font-bold text-storefront-primary md:text-5xl">20+</div>
            <div class="text-[color:var(--storefront-text-muted,#4b5563)]">Лизинговых компаний</div>
          </div>
          <div class="text-center">
            <div class="mb-2 text-4xl font-bold text-storefront-primary md:text-5xl">10 000+</div>
            <div class="text-[color:var(--storefront-text-muted,#4b5563)]">Оформленных заявок</div>
          </div>
          <div class="text-center">
            <div class="mb-2 text-4xl font-bold text-storefront-primary md:text-5xl">5 млрд+</div>
            <div class="text-[color:var(--storefront-text-muted,#4b5563)]">Рублей сделок</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Values Section -->
    <section data-storefront-block="about.partners" class="py-16 bg-[color:rgb(var(--storefront-background-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">
            Наши ценности
          </h2>
          <p class="text-lg text-[color:var(--storefront-text-muted,#4b5563)]">
            Принципы, которыми мы руководствуемся в работе
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          <div class="flex items-start">
            <div class="flex-shrink-0 w-12 h-12 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-6 h-6 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Прозрачность</h3>
              <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Честные условия без скрытых комиссий и дополнительных платежей</p>
            </div>
          </div>

          <div class="flex items-start">
            <div class="flex-shrink-0 w-12 h-12 bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-6 h-6 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Технологичность</h3>
              <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Современные IT-решения для автоматизации всех процессов</p>
            </div>
          </div>

          <div class="flex items-start">
            <div class="flex-shrink-0 w-12 h-12 bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-6 h-6 text-[color:var(--storefront-info-icon,#9333ea)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Партнёрство</h3>
              <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Долгосрочные отношения с клиентами и лизинговыми компаниями</p>
            </div>
          </div>

          <div class="flex items-start">
            <div class="flex-shrink-0 w-12 h-12 bg-[color:rgb(var(--storefront-warning-rgb,255_237_213)/var(--tw-bg-opacity,1))] rounded-lg flex items-center justify-center mr-4">
              <svg class="w-6 h-6 text-[color:var(--storefront-warning-icon,#ea580c)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Профессионализм</h3>
              <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Команда экспертов с многолетним опытом в автомобильном лизинге</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Contact Section -->
    <section data-storefront-block="about.contacts" class="py-16 bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
      <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">
            Контактная информация
          </h2>
          <p class="text-lg text-[color:var(--storefront-text-muted,#4b5563)]">
            Свяжитесь с нами для получения дополнительной информации
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div class="card">
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Реквизиты компании</h3>
            <div class="space-y-2 text-[color:var(--storefront-text-muted,#4b5563)]">
              <p>ООО «КАРКРАФТ»</p>
              <p>ИНН: 7730267910</p>
              <p>ОГРН: 1217700442460</p>
            </div>
          </div>

          <div class="card">
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Связаться с нами</h3>
            <div class="space-y-3">
              <a :href="`mailto:${contact_email}`"
                class="flex items-center text-[color:var(--storefront-link,#4b5563)] hover:text-[color:var(--storefront-link-hover,#2563eb)] transition-colors">
                <svg class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                {{ contact_email }}
              </a>
              <a :href="`tel:${contact_phone_href}`" class="flex items-center text-[color:var(--storefront-link,#4b5563)] hover:text-[color:var(--storefront-link-hover,#2563eb)] transition-colors">
                <svg class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                </svg>
                {{ contact_phone }}
              </a>
              <a href="https://carcraft.ru"
                class="flex items-center text-[color:var(--storefront-link,#4b5563)] hover:text-[color:var(--storefront-link-hover,#2563eb)] transition-colors">
                <svg class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
                carcraft.ru
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
        </div>
      </template>
    </StorefrontPageRenderer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useStorefront } from '~/features/storefront'
import { StorefrontPageRenderer } from '~/features/storefrontBuilder'
import { useStorefrontPagesApi } from '~/features/storefrontBuilder/api/storefrontPagesApi'

const { contact_email, contact_phone, contact_phone_href, pageTitle, publicRoute, slug } = useStorefront()
const pagesApi = useStorefrontPagesApi()

const { data: pageData } = await useAsyncData(
  () => `storefront-page-about-${slug.value || 'default'}`,
  async () => {
    try {
      return await pagesApi.getPublicPage(slug.value || '', 'about')
    } catch (_e) {
      return null
    }
  },
  {
    watch: [slug],
  },
)

const pageLayout = computed(() => {
  if (!pageData.value || pageData.value.fallback_layout || !pageData.value.layout) {
    return null
  }
  return pageData.value.layout
})

useHead(() => ({
  title: pageData.value?.layout?.settings?.title || `${pageTitle('about')} - CarCraft Multileasing`,
  meta: [
    {
      name: 'description',
      content:
        pageData.value?.layout?.settings?.description ||
        'CarCraft Multileasing — ведущая лизинговая платформа для автодилеров России. Узнайте о нашей миссии, ценностях и преимуществах работы с нами.',
    },
  ],
}))
</script>
