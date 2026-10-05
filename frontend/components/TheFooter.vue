<template>
  <footer data-storefront-block="footer" class="bg-[color:rgb(var(--storefront-background-rgb,17_24_39)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] [overflow-wrap:anywhere]">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <div>
          <div class="flex h-[50px] items-center mb-4">
            <img
              :src="logo_url"
              :alt="storefrontLabel"
              class="max-h-[50px] max-w-full h-auto w-auto object-contain"
              :style="logo_url === '/images/logo.png' ? { filter: 'brightness(0) invert(1)' } : undefined"
            />
          </div>
          <p class="text-[color:var(--storefront-text,#d1d5db)] mb-4">
            Лизинговая платформа для дилеров. Выгодные условия, быстрое
            оформление, надежный сервис.
          </p>

        </div>

        <div>
          <h3 class="text-[color:var(--storefront-title,inherit)] text-lg font-semibold mb-4">Услуги</h3>
          <ul class="space-y-2 text-[color:var(--storefront-text,#d1d5db)]">
            <li v-if="visibilityStore.isSectionVisible('public', 'special_equipment_catalog')">
              <NuxtLink :to="publicRoute('/special-equipment')" class="text-[color:var(--storefront-link,#d1d5db)] hover:text-[color:var(--storefront-link-hover,#ffffff)] transition-colors"
                >{{ pageTitle('special_equipment_catalog') }}</NuxtLink
              >
            </li>
            <li v-if="public_ui.home_page_key === 'home'">
              <NuxtLink
                :to="publicRoute('/#calculator')"
                class="text-[color:var(--storefront-link,#d1d5db)] hover:text-[color:var(--storefront-link-hover,#ffffff)] transition-colors"
                >Лизинговый калькулятор</NuxtLink
              >
            </li>
          </ul>
        </div>

        <div>
          <h3 class="text-[color:var(--storefront-title,inherit)] text-lg font-semibold mb-4">Контакты</h3>
          <div class="space-y-3 text-[color:var(--storefront-text,#d1d5db)]">
            <div class="flex items-center">
              <svg
                class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-2 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                ></path>
              </svg>
              <a
                :href="`mailto:${contact_email}`"
                class="text-[color:var(--storefront-link,#d1d5db)] hover:text-[color:var(--storefront-link-hover,#ffffff)] transition-colors"
              >
                {{ contact_email }}
              </a>
            </div>
            <div class="flex items-center">
              <a
                :href="`tel:${contact_phone_href}`"
                class="flex items-center text-[color:var(--storefront-link,#d1d5db)] hover:text-[color:var(--storefront-link-hover,#ffffff)] transition-colors"
                title="Позвонить"
              >
                <svg
                  class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-2 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
                  ></path>
                </svg>
                <span>{{ contact_phone }}</span>
              </a>
            </div>
            <div class="flex items-start">
              <svg
                class="text-[color:var(--storefront-icon,inherit)] w-5 h-5 mr-2 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                ></path>
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                ></path>
              </svg>
              <div>
                <div>125424, Москва, Сходненский тупик, 16</div>
                <div class="text-sm text-[color:var(--storefront-text-muted,#9ca3af)]">пн-пт 9:00-18:00</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="border-t border-[color:var(--storefront-border,#1f2937)] mt-8 pt-8">
        <div class="flex flex-col md:flex-row justify-between items-center">
          <div class="text-[color:var(--storefront-text-muted,#9ca3af)] text-sm">
            © 2025 CarCraft Multileasing. Все права защищены.
          </div>
          <div class="mt-4 flex w-full min-w-0 flex-col items-center gap-3 text-center sm:w-auto sm:flex-row sm:gap-6 md:mt-0">
            <NuxtLink
              to="/pdp-policy/"
              target="_blank"
              rel="noopener noreferrer"
              class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#ffffff)] text-sm transition-colors"
            >
              Политика конфиденциальности
            </NuxtLink>
            <a
              href="/terms-of-service"
              target="_blank"
              rel="noopener noreferrer"
              class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#ffffff)] text-sm transition-colors"
            >
              Пользовательское соглашение
            </a>
          </div>
        </div>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { useStorefront } from '~/features/storefront'

const visibilityStore = useSectionVisibilityStore()
const {
  contact_email,
  contact_phone,
  contact_phone_href,
  logo_url,
  pageTitle,
  public_ui,
  publicRoute,
  slug,
} = useStorefront()
const storefrontLabel = computed(() => slug.value ? `Логотип витрины ${slug.value}` : 'CarCraft Multileasing')
</script>
