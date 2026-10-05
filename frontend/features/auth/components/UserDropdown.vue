<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import type { CompanyInfo } from '@/types'
import { useStorefront } from '~/features/storefront'

const authStore = useAuthStore()
const config = useRuntimeConfig()
const { contact_email, contact_phone, contact_phone_href, publicRoute } = useStorefront()

const isOpen = ref(false)
const dropdownRef = ref<HTMLDivElement>()

const userCompanies = ref<CompanyInfo[]>([])

const companyInfo = computed(() => {
  const companyStr = authStore.user?.companyNameOrInn as string | undefined
  if (!companyStr) {
    return { name: '', inn: '' }
  }

  const innMatch = companyStr.match(/\(([^)]+)\)$/)
  const inn = innMatch ? innMatch[1] : ''
  const name = inn ? companyStr.replace(` (${inn})`, '') : companyStr

  return { name, inn }
})

const fetchUserCompanies = async () => {
  if (!authStore.isClient || authStore.isDealer) return
  try {
    const response = await $fetch('/api/v1/users/me/companies', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    const typedResponse = response as { companies?: CompanyInfo[] }
    userCompanies.value = typedResponse.companies || []
  } catch (err) {
    console.error('Error fetching user companies:', err)
  }
}

const handleLogout = async () => {
  isOpen.value = false
  await authStore.logout()
  await navigateTo(publicRoute('/'))
}

const toggleOpen = () => {
  isOpen.value = !isOpen.value
}

const handleClickOutside = (event: MouseEvent) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  fetchUserCompanies()
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div data-storefront-block="client.auth" class="relative" ref="dropdownRef">
    <button
      @click.stop="toggleOpen"
      class="storefront-action-ghost p-1.5 rounded-lg text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))] transition-colors duration-200 flex items-center gap-1"
      :class="{ 'bg-[color:rgb(var(--storefront-ghost-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#374151)]': isOpen }"
    >
      <div class="w-8 h-8 bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
        <svg class="w-4 h-4 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      </div>
      <svg class="block h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 scale-95"
      enter-to-class="transform opacity-100 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 scale-100"
      leave-to-class="transform opacity-0 scale-95"
    >
      <div
        v-if="isOpen"
        class="absolute right-0 mt-2 w-80 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl shadow-xl border border-[color:var(--storefront-border,#e5e7eb)] py-2 z-50 max-h-[85vh] overflow-y-auto"
      >
        <!-- User header -->
        <div class="px-4 py-3 border-b border-[color:var(--storefront-border,#f3f4f6)]">
          <div class="flex items-center">
            <div class="w-10 h-10 bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center shrink-0">
              <svg class="w-5 h-5 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div class="ml-3 min-w-0">
              <p class="text-sm font-semibold text-[color:var(--storefront-text,#111827)] truncate">
                {{ authStore.user?.name || 'Пользователь' }}
              </p>
              <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] truncate">
                {{ authStore.user?.phone || '8 800 555 35 35' }}
              </p>
            </div>
          </div>
        </div>

        <!-- Contact info -->
        <div class="px-4 py-2 space-y-2">
          <div v-if="authStore.user?.email" class="flex items-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span class="truncate">{{ authStore.user.email }}</span>
          </div>

          <div v-if="companyInfo.name" class="flex items-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            <span class="truncate">{{ companyInfo.name }}</span>
          </div>

          <div v-if="companyInfo.inn" class="flex items-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span>ИНН: {{ companyInfo.inn }}</span>
          </div>
        </div>

        <!-- My companies -->
        <div v-if="authStore.isClient && !authStore.isDealer && userCompanies.length > 0" class="border-t border-[color:var(--storefront-border,#f3f4f6)] px-4 py-2">
          <h4 class="text-xs font-semibold text-[color:var(--storefront-title,#6b7280)] uppercase tracking-wider mb-2">Мои компании</h4>
          <div class="space-y-1.5">
            <div
              v-for="company in userCompanies"
              :key="company.id"
              class="flex items-center text-sm text-[color:var(--storefront-text,#374151)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg px-3 py-2"
            >
              <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              <div class="min-w-0">
                <div class="truncate font-medium">{{ company.name }}</div>
                <div v-if="company.inn" class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">ИНН: {{ company.inn }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Support contacts -->
        <div class="border-t border-[color:var(--storefront-border,#f3f4f6)] px-4 py-2">
          <h4 class="text-xs font-semibold text-[color:var(--storefront-title,#6b7280)] uppercase tracking-wider mb-2">Контакты поддержки</h4>
          <div class="space-y-2">
            <a :href="`tel:${contact_phone_href}`"
              class="flex items-center text-sm text-[color:var(--storefront-link,#4b5563)] hover:text-[color:var(--storefront-link-hover,#2563eb)] transition-colors">
              <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
              </svg>
              {{ contact_phone }}
            </a>
            <a :href="`mailto:${contact_email}`"
              class="flex items-center text-sm text-[color:var(--storefront-link,#4b5563)] hover:text-[color:var(--storefront-link-hover,#2563eb)] transition-colors">
              <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              {{ contact_email }}
            </a>
          </div>
        </div>

        <!-- Profile link -->
        <div v-if="!authStore.isCarCraftEmployee" class="border-t border-[color:var(--storefront-border,#f3f4f6)] px-4 py-2">
          <NuxtLink
            :to="authStore.isBusinessRole ? '/workspace/profile' : publicRoute('/cabinet?tab=profile')"
            class="storefront-action-ghost flex items-center text-sm text-[color:var(--storefront-primary-foreground,#374151)] hover:text-[color:var(--storefront-primary-hover-foreground,#2563eb)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] rounded-lg px-2 py-1.5 -mx-2 transition-colors"
            @click="isOpen = false"
          >
            <svg class="w-4 h-4 mr-2 text-[color:var(--storefront-primary-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            Профиль
          </NuxtLink>
        </div>

        <!-- Logout -->
        <div class="border-t border-[color:var(--storefront-border,#f3f4f6)] px-4 py-2">
          <button
            @click="handleLogout"
            class="storefront-action-ghost w-full flex items-center text-sm text-[color:var(--storefront-destructive-foreground,#dc2626)] hover:text-[color:var(--storefront-destructive-hover-foreground,#b91c1c)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] rounded-lg px-2 py-1.5 -mx-2 transition-colors"
          >
            <svg class="w-4 h-4 mr-2 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Выйти
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>
