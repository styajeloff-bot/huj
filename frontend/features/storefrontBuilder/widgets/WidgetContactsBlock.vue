<template>
  <div class="storefront-builder-widget py-6" :style="containerStyle">
    <div
      class="overflow-hidden rounded-2xl border storefront-builder-border storefront-builder-surface shadow-sm"
    >
      <div class="grid grid-cols-1 gap-8 p-6 sm:p-10 lg:grid-cols-2">
        <!-- Contact info -->
        <div>
          <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
            {{ config.title || 'Контакты' }}
          </h2>
          <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
            {{ config.subtitle }}
          </p>

          <dl class="mt-8 space-y-6">
            <!-- Phone -->
            <div v-if="config.show_phone ?? true" class="flex items-start">
              <dt class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg storefront-builder-primary-soft storefront-builder-primary-text">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                </svg>
              </dt>
              <dd class="ml-4">
                <p class="text-xs font-semibold uppercase tracking-wider storefront-builder-text-muted">Телефон</p>
                <a
                  :href="`tel:${cleanPhone(effectivePhone)}`"
                  class="mt-1 text-lg font-semibold storefront-builder-text storefront-builder-hover-primary-text"
                >
                  {{ effectivePhone }}
                </a>
              </dd>
            </div>

            <!-- Email -->
            <div v-if="config.show_email ?? true" class="flex items-start">
              <dt class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg storefront-builder-primary-soft storefront-builder-primary-text">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </dt>
              <dd class="ml-4">
                <p class="text-xs font-semibold uppercase tracking-wider storefront-builder-text-muted">Электронная почта</p>
                <a
                  :href="`mailto:${effectiveEmail}`"
                  class="mt-1 text-base font-medium storefront-builder-text storefront-builder-hover-primary-text"
                >
                  {{ effectiveEmail }}
                </a>
              </dd>
            </div>

            <!-- Address -->
            <div v-if="config.show_address ?? true" class="flex items-start">
              <dt class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg storefront-builder-primary-soft storefront-builder-primary-text">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </dt>
              <dd class="ml-4">
                <p class="text-xs font-semibold uppercase tracking-wider storefront-builder-text-muted">Адрес офиса</p>
                <p class="mt-1 text-base storefront-builder-text">
                  {{ effectiveAddress }}
                </p>
              </dd>
            </div>

            <!-- Working hours -->
            <div v-if="config.working_hours" class="flex items-start">
              <dt class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg storefront-builder-primary-soft storefront-builder-primary-text">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </dt>
              <dd class="ml-4">
                <p class="text-xs font-semibold uppercase tracking-wider storefront-builder-text-muted">График работы</p>
                <p class="mt-1 text-base storefront-builder-text">
                  {{ config.working_hours }}
                </p>
              </dd>
            </div>
          </dl>
        </div>

        <!-- Requisites / Map block -->
        <div class="flex flex-col justify-between rounded-xl storefront-builder-surface-muted p-6">
          <div v-if="config.show_requisites ?? true">
            <h3 class="text-base font-semibold storefront-builder-text">Реквизиты компании</h3>
            <div class="mt-3 whitespace-pre-line text-sm leading-relaxed storefront-builder-text-muted font-mono">
              {{ effectiveRequisites }}
            </div>
          </div>

          <div v-if="config.show_map && config.map_url" class="mt-6 overflow-hidden rounded-lg">
            <iframe
              :src="config.map_url"
              class="h-48 w-full border-0"
              loading="lazy"
              referrerpolicy="no-referrer-when-downgrade"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import { useStorefront } from '~/features/storefront'
import type { ContactsBlockWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: ContactsBlockWidgetProps
  styles?: WidgetStyles
}>()

const storefront = useStorefront()

const config = computed<ContactsBlockWidgetProps>(() => ({
  title: 'Контакты и реквизиты',
  subtitle: 'Свяжитесь с нами удобным способом или посетите наш офис',
  show_phone: true,
  show_email: true,
  show_address: true,
  show_requisites: true,
  working_hours: 'Пн-Пт: 09:00 — 19:00, Сб: 10:00 — 16:00',
  ...props.props,
}))

const effectivePhone = computed(() => {
  return config.value.phone || storefront.contact_phone?.value || '+7 (495) 120-00-00'
})

const effectiveEmail = computed(() => {
  return config.value.email || storefront.contact_email?.value || 'leasing@carcraft.ru'
})

const effectiveAddress = computed(() => {
  return config.value.address || 'г. Москва, ул. Ленинская Слобода, д. 26'
})

const effectiveRequisites = computed(() => {
  return config.value.requisites || `ООО «Каркрафт Мультилизинг»\nИНН: 7725890123 / КПП: 772501001\nОГРН: 1157746123456\nБИК: 044525225\nР/с: 40702810000000012345`
})

const cleanPhone = (phone: string) => phone.replace(/[^\d+]/g, '')

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})
</script>
