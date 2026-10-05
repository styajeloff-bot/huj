<template>
  <section aria-labelledby="storefronts-heading">
    <div class="mb-6 flex flex-wrap items-start justify-between gap-6">
      <div class="min-w-0 flex-1">
        <h1 id="storefronts-heading" class="text-2xl font-semibold text-gray-950">Витрины и шрифты</h1>
        <p class="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
          Управляйте витринами, их публичными страницами и общим каталогом фирменных шрифтов.
        </p>
      </div>
      <button
        v-if="activeSection === 'storefronts'"
        type="button"
        class="btn-primary min-h-11 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
        :disabled="loading || saving || savingPublicUi || settingsImportPending"
        @click="startCreate"
      >
        <PlusIcon class="h-5 w-5" aria-hidden="true" />
        Создать витрину
      </button>
      <StorefrontSettingsTransfer
        v-if="activeSection === 'storefronts'"
        :disabled="loading || saving || savingPublicUi || Boolean(visibilityPanel?.saving)"
        :has-unsaved-changes="hasUnsavedChanges || Boolean(visibilityPanel?.hasUnsavedChanges)"
        @busy-change="settingsImportPending = $event"
        @imported="handleSettingsImported"
      />
    </div>

    <div :inert="settingsImportPending">
    <nav class="mb-6 border-b border-gray-200" aria-label="Разделы настройки витрин">
      <div role="tablist" class="flex gap-8">
        <button
          v-for="section in SECTIONS"
          :id="`storefronts-section-tab-${section.key}`"
          :key="section.key"
          type="button"
          role="tab"
          :aria-selected="activeSection === section.key"
          :aria-controls="`storefronts-section-panel-${section.key}`"
          :tabindex="activeSection === section.key ? 0 : -1"
          class="min-h-11 border-b-2 px-1 py-3 text-sm font-semibold transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 motion-reduce:transition-none"
          :class="activeSection === section.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900'"
          @click="selectSection(section.key)"
          @keydown.left.prevent="selectAdjacentSection(section.key, -1)"
          @keydown.right.prevent="selectAdjacentSection(section.key, 1)"
        >
          {{ section.label }}
        </button>
      </div>
    </nav>

    <div
      v-if="activeSection === 'fonts'"
      id="storefronts-section-panel-fonts"
      role="tabpanel"
      aria-labelledby="storefronts-section-tab-fonts"
    >
      <StorefrontFontsPanel ref="fontsPanel" @dirty-change="fontsDirty = $event" />
    </div>

    <div
      v-else
      id="storefronts-section-panel-storefronts"
      role="tabpanel"
      aria-labelledby="storefronts-section-tab-storefronts"
    >
    <div class="mb-4 min-h-12" aria-live="polite" aria-atomic="true">
      <p v-if="statusMessage" class="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        {{ statusMessage }}
      </p>
      <div v-else-if="errorMessage" class="flex items-center justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
        <span class="flex items-center gap-2">
          <ExclamationCircleIcon class="h-5 w-5 shrink-0" aria-hidden="true" />
          {{ errorMessage }}
        </span>
        <button v-if="loadFailed" type="button" class="btn-secondary min-h-11 shrink-0" @click="load">
          Повторить
        </button>
      </div>
    </div>

    <div v-if="loading" class="grid grid-cols-[minmax(220px,0.72fr)_minmax(0,1.7fr)] gap-6" aria-busy="true" aria-label="Загрузка витрин">
      <div class="h-72 animate-pulse rounded-xl bg-gray-100 motion-reduce:animate-none" />
      <div class="h-96 animate-pulse rounded-xl bg-gray-100 motion-reduce:animate-none" />
    </div>

    <div v-else class="grid grid-cols-[minmax(220px,0.72fr)_minmax(0,1.7fr)] items-start gap-6">
      <aside class="overflow-hidden rounded-xl border border-gray-200 bg-white" aria-label="Список витрин">
        <div
          v-for="item in storefronts"
          :key="item.id"
          role="button"
          tabindex="0"
          class="flex min-h-20 w-full items-center justify-between gap-4 border-b border-gray-100 px-5 py-4 text-left transition-colors duration-200 last:border-b-0 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600 motion-reduce:transition-none cursor-pointer"
          :class="selected?.id === item.id ? 'bg-blue-50 hover:bg-blue-50' : ''"
          :aria-current="selected?.id === item.id ? 'true' : undefined"
          @click="select(item)"
          @keydown.enter.self="select(item)"
          @keydown.space.self.prevent="select(item)"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate font-semibold text-gray-950">{{ storefrontName(item) }}</span>
            <span class="mt-1 block text-sm text-gray-500">{{ item.warehouse_ids.length }} складов</span>
          </span>
          <div class="flex items-center gap-2 shrink-0">
            <NuxtLink
              :to="`/workspace/storefronts/${item.id}/builder`"
              class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 shadow-2xs hover:bg-gray-100 hover:text-blue-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 transition-colors"
              :title="`Конструктор витрины ${storefrontName(item)}`"
              :aria-label="`Конструктор витрины ${storefrontName(item)}`"
              @click.stop
            >
              <WrenchScrewdriverIcon class="h-4 w-4" aria-hidden="true" />
            </NuxtLink>
            <span class="rounded-full px-2.5 py-1 text-sm font-medium" :class="item.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'">
              {{ item.is_active ? 'Активна' : 'Выключена' }}
            </span>
          </div>
        </div>
        <p v-if="storefronts.length === 0" class="p-8 text-center text-sm text-gray-500">Витрины пока не созданы</p>
      </aside>

      <div v-if="editing" class="min-w-0 overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div class="flex items-center justify-between gap-4 border-b border-gray-200 px-6 py-5">
          <div>
            <h2 class="text-lg font-semibold text-gray-950">{{ selected ? storefrontName(selected) : 'Новая витрина' }}</h2>
            <p v-if="selected" class="mt-1 text-sm text-gray-500">UUID: {{ selected.id }}</p>
          </div>
          <div class="flex items-center gap-3">
            <NuxtLink
              v-if="selected"
              :to="`/workspace/storefronts/${selected.id}/builder`"
              class="btn-primary inline-flex min-h-10 items-center gap-2 px-4 text-xs font-semibold shadow-xs"
            >
              <WrenchScrewdriverIcon class="h-4 w-4" aria-hidden="true" />
              Конструктор витрины
            </NuxtLink>
            <span v-if="selected?.is_default" class="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-800">Системная</span>
          </div>
        </div>

        <div v-if="selected" class="border-b border-gray-200 px-6 pt-2">
          <div role="tablist" aria-label="Настройки витрины" class="flex gap-8">
            <button
              v-for="tab in TABS"
              :id="`storefront-tab-${tab.key}`"
              :key="tab.key"
              type="button"
              role="tab"
              :aria-selected="activeTab === tab.key"
              :aria-controls="`storefront-panel-${tab.key}`"
              :tabindex="activeTab === tab.key ? 0 : -1"
              class="min-h-11 border-b-2 px-1 py-3 text-sm font-semibold transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 motion-reduce:transition-none"
              :class="activeTab === tab.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900'"
              @click="selectTab(tab.key)"
              @keydown.left.prevent="selectAdjacentTab(tab.key, -1)"
              @keydown.right.prevent="selectAdjacentTab(tab.key, 1)"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <form
          v-show="!selected || activeTab === 'general'"
          id="storefront-panel-general"
          role="tabpanel"
          aria-labelledby="storefront-tab-general"
          class="p-6"
          @submit.prevent="saveBasics"
        >
          <div class="grid grid-cols-2 gap-5">
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-gray-800">Slug</span>
              <span class="flex min-h-11 overflow-hidden rounded-lg border border-gray-300 bg-white focus-within:ring-2 focus-within:ring-blue-600">
                <span class="flex items-center border-r border-gray-200 bg-gray-50 px-3 text-gray-500">/</span>
                <input v-model.trim="form.slug" :disabled="Boolean(selected?.is_default)" required pattern="[a-z0-9-]+" class="min-w-0 flex-1 border-0 px-3 py-2 outline-none disabled:bg-gray-100" autocomplete="off">
              </span>
              <span class="mt-1 block text-sm leading-5 text-gray-500">Латинские буквы, цифры и дефис.</span>
            </label>

            <label class="flex min-h-11 items-center gap-3 self-start pt-7">
              <input v-model="form.is_active" type="checkbox" :disabled="Boolean(selected?.is_default)" class="h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-600">
              <span class="text-sm font-medium text-gray-800">Витрина активна</span>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-gray-800">Контактный email</span>
              <input v-model.trim="form.contact_email" type="email" class="input-field min-h-11" placeholder="Наследовать основной" :aria-describedby="selected ? 'storefront-effective-email' : undefined">
              <span v-if="selected" id="storefront-effective-email" class="mt-1.5 block text-sm text-gray-600">
                Сейчас: {{ selected.effective_contact_email || 'не указан' }}<template v-if="!selected.is_default && !selected.contact_email"> (наследуется от основной витрины)</template>
              </span>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-gray-800">Контактный телефон</span>
              <input v-model.trim="form.contact_phone" type="tel" class="input-field min-h-11" placeholder="Наследовать основной" :aria-describedby="selected ? 'storefront-effective-phone' : undefined">
              <span v-if="selected" id="storefront-effective-phone" class="mt-1.5 block text-sm text-gray-600">
                Сейчас: {{ selected.effective_contact_phone || 'не указан' }}<template v-if="!selected.is_default && !selected.contact_phone"> (наследуется от основной витрины)</template>
              </span>
            </label>
          </div>

          <fieldset class="mt-6" :disabled="Boolean(selected?.is_default)">
            <legend class="text-sm font-semibold text-gray-900">Склады витрины</legend>
            <p class="mt-1 text-sm text-gray-500">Выберите хотя бы один активный склад.</p>
            <div class="mt-3 grid max-h-60 grid-cols-2 gap-2 overflow-y-auto rounded-lg border border-gray-200 p-3">
              <label v-for="warehouse in warehouses" :key="warehouse.id" class="flex min-h-11 items-start gap-3 rounded-lg px-3 py-2 hover:bg-gray-50">
                <input v-model="form.warehouse_ids" type="checkbox" :value="warehouse.id" class="mt-0.5 h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-600">
                <span class="min-w-0 text-sm">
                  <span class="block font-medium text-gray-900">{{ warehouse.address }}</span>
                  <span class="block truncate text-sm text-gray-500">{{ [warehouse.brand, warehouse.city_name].filter(Boolean).join(' · ') }}</span>
                </span>
              </label>
              <p v-if="warehouses.length === 0" class="col-span-2 py-6 text-center text-sm text-gray-500">Активные склады не найдены</p>
            </div>
          </fieldset>

          <fieldset class="mt-6">
            <legend class="text-sm font-semibold text-gray-900">Логотип</legend>
            <div class="mt-3 flex items-center gap-4">
              <div v-if="displayedLogoUrl" class="shrink-0">
                <div class="flex w-40 items-center rounded border border-gray-200 bg-white p-2">
                  <div class="flex h-[50px] w-full items-center">
                    <img :src="displayedLogoUrl" :alt="selected?.logo_url ? 'Текущий логотип витрины' : 'Логотип, унаследованный от основной витрины'" class="max-h-[50px] max-w-full h-auto w-auto object-contain">
                  </div>
                </div>
                <span v-if="selected && !selected.logo_url" class="mt-1 block text-sm text-gray-500">Наследуется от основной</span>
              </div>
              <input ref="logoInput" type="file" accept="image/png,image/jpeg,image/webp" class="block min-h-11 flex-1 rounded-lg border border-gray-300 p-2 text-sm" @change="selectLogo">
              <button v-if="selected?.logo_url" type="button" class="btn-secondary min-h-11" :disabled="saving" @click="removeLogo">Убрать логотип</button>
            </div>
            <p class="mt-2 text-sm text-gray-500">Статичные PNG, JPEG или WebP, не более 5 МиБ. Исходный файл сохраняется без изменения качества и разрешения. При отображении высота — не более 50 px с сохранением пропорций; маленькие изображения не увеличиваются.</p>
          </fieldset>

          <div class="mt-8 flex justify-end gap-3 border-t border-gray-100 pt-5">
            <button v-if="!selected" type="button" class="btn-secondary min-h-11" @click="cancelCreate">Отмена</button>
            <button type="submit" class="btn-primary min-h-11 min-w-32" :disabled="saving || (!selected?.is_default && form.warehouse_ids.length === 0)">
              <ArrowPathIcon v-if="saving" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              {{ saving ? 'Сохранение…' : 'Сохранить' }}
            </button>
          </div>
        </form>

        <div
          v-if="selected"
          v-show="activeTab === 'visibility'"
          id="storefront-panel-visibility"
          role="tabpanel"
          aria-labelledby="storefront-tab-visibility"
          class="flex flex-col gap-8 p-6"
        >
          <form class="overflow-hidden rounded-xl border border-gray-200" @submit.prevent="savePublicUi">
            <div class="border-b border-gray-200 px-6 py-5">
              <div class="flex items-center gap-3">
                <span class="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                  <WindowIcon class="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="text-lg font-semibold text-gray-950">Публичные страницы</h3>
                  <p class="mt-1 text-sm leading-5 text-gray-600">Названия и главная страница действуют только для этой витрины.</p>
                </div>
              </div>
            </div>

            <div class="flex flex-col gap-6 p-6">
              <label class="block max-w-xl">
                <span class="mb-1.5 block text-sm font-medium text-gray-800">Главная страница</span>
                <select v-model="publicUiForm.home_page_key" class="select-field min-h-11 w-full" :disabled="savingPublicUi">
                  <option v-for="page in PUBLIC_PAGES" :key="page.key" :value="page.key">{{ publicUiForm.pageLabels[page.key] }}</option>
                </select>
                <span class="mt-1.5 block text-sm leading-5 text-gray-500">Выбранная страница будет автоматически доступна на публичном сайте.</span>
              </label>

              <fieldset>
                <div class="flex items-center justify-between gap-4 mb-3">
                  <legend class="text-sm font-semibold text-gray-900">Названия страниц</legend>
                  <NuxtLink
                    :to="`/workspace/storefronts/${selected.id}/builder`"
                    class="inline-flex items-center gap-1.5 rounded-lg border border-blue-600 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                  >
                    <PlusIcon class="h-3.5 w-3.5" aria-hidden="true" />
                    + Создать страницу в конструкторе
                  </NuxtLink>
                </div>

                <div class="grid grid-cols-2 gap-4">
                  <label v-for="page in PUBLIC_PAGES" :key="page.key" class="block">
                    <span class="mb-1.5 block text-sm font-medium text-gray-700">{{ page.defaultLabel }}</span>
                    <input v-model.trim="publicUiForm.pageLabels[page.key]" type="text" required maxlength="120" class="input-field min-h-11" :disabled="savingPublicUi" autocomplete="off">
                  </label>
                </div>

                <!-- Пользовательские страницы -->
                <div v-if="customPages.length > 0" class="mt-6 flex flex-col gap-3 border-t border-gray-100 pt-5">
                  <h4 class="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Пользовательские страницы
                  </h4>
                  <div class="flex flex-col gap-3">
                    <div
                      v-for="page in customPages"
                      :key="page.id"
                      class="flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50/50 p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div class="flex flex-1 flex-col gap-2 min-w-0 sm:flex-row sm:items-center sm:gap-4">
                        <div class="flex-1 min-w-[200px]">
                          <label :for="`custom-page-title-${page.id}`" class="sr-only">Название страницы {{ page.title }}</label>
                          <input
                            :id="`custom-page-title-${page.id}`"
                            v-model.trim="customPageTitles[page.id]"
                            type="text"
                            required
                            maxlength="120"
                            class="input-field min-h-10 text-sm"
                            :disabled="savingPublicUi"
                            autocomplete="off"
                            placeholder="Название страницы"
                          >
                        </div>
                        <div class="flex items-center gap-2 shrink-0">
                          <span
                            class="inline-flex items-center rounded-md bg-white px-2.5 py-1 text-xs font-mono text-gray-700 border border-gray-200"
                            :title="`URL slug: ${page.slug || page.page_key}`"
                          >
                            /{{ page.slug || page.page_key }}
                          </span>
                          <span
                            v-if="page.page_key && page.page_key !== page.slug"
                            class="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-500"
                            :title="`page_key: ${page.page_key}`"
                          >
                            key: {{ page.page_key }}
                          </span>
                        </div>
                      </div>
                      <div class="shrink-0">
                        <NuxtLink
                          :to="`/workspace/storefronts/${selected.id}/builder?page=${page.id}`"
                          class="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-100 hover:text-blue-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                        >
                          <WrenchScrewdriverIcon class="h-3.5 w-3.5 text-gray-500" aria-hidden="true" />
                          В конструктор
                        </NuxtLink>
                      </div>
                    </div>
                  </div>
                </div>
              </fieldset>

            </div>

            <footer class="flex items-center justify-between gap-4 border-t border-gray-200 bg-gray-50 px-6 py-4">
              <p class="text-sm text-gray-500">Сохранение не изменяет URL страниц.</p>
              <button type="submit" class="btn-primary min-h-11 min-w-44" :disabled="savingPublicUi">
                <ArrowPathIcon v-if="savingPublicUi" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                {{ savingPublicUi ? 'Сохраняем…' : 'Сохранить страницы' }}
              </button>
            </footer>
          </form>

          <AdminSectionVisibilityPanel
            :key="visibilityImportRevision"
            ref="visibilityPanel"
            :storefront-id="selected.id"
            :storefront-slug="selected.slug"
            :storefront-is-default="selected.is_default"
            :storefront-is-active="selected.is_active"
            :home-page-key="selected.public_ui.home_page_key"
            :public-pages="selected.public_ui.pages"
            :storefront-pages="storefrontPages"
          />
        </div>
      </div>

      <div v-else class="rounded-xl border border-dashed border-gray-300 p-10 text-center text-sm text-gray-500">
        Выберите витрину или создайте новую
      </div>
    </div>
    </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  ArrowPathIcon,
  ExclamationCircleIcon,
  PlusIcon,
  WindowIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/vue/24/outline'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import {
  createStorefrontsAdminApi,
  type AdminStorefront,
  type StorefrontPublicPageKey,
  type StorefrontWarehouseOption,
  type StorefrontWriteRequest,
  type StorefrontSettingsImportResult,
} from '~/features/admin/storefronts/api/storefrontsAdminApi'
import { createStorefrontBuilderApi } from '~/features/storefrontBuilder/api/storefrontBuilderApi'
import type { StorefrontPageListItem } from '~/features/storefrontBuilder/types'
import StorefrontFontsPanel from '~/features/admin/storefronts/components/StorefrontFontsPanel.vue'
import StorefrontSettingsTransfer from '~/features/admin/storefronts/components/StorefrontSettingsTransfer.vue'
import { storefrontAdminErrorMessage } from '~/features/admin/storefronts/errorMessage'
import AdminSectionVisibilityPanel from '~/features/sectionVisibility/AdminSectionVisibilityPanel.vue'
import type { UUID } from '~/types/ids'

type StorefrontsSection = 'storefronts' | 'fonts'
type StorefrontSettingsTab = 'general' | 'visibility'

const SECTIONS: ReadonlyArray<{ key: StorefrontsSection; label: string }> = [
  { key: 'storefronts', label: 'Витрины' },
  { key: 'fonts', label: 'Шрифты' },
]
const TABS: ReadonlyArray<{ key: StorefrontSettingsTab; label: string }> = [
  { key: 'general', label: 'Основные настройки' },
  { key: 'visibility', label: 'Доступ к разделам' },
]
const PUBLIC_PAGES: ReadonlyArray<{ key: StorefrontPublicPageKey; defaultLabel: string }> = [
  { key: 'home', defaultLabel: 'Главная' },
  { key: 'about', defaultLabel: 'О нас' },
  { key: 'special_equipment_catalog', defaultLabel: 'Спецтехника' },
]
const MAX_LOGO_SIZE = 5 * 1024 * 1024
const ALLOWED_LOGO_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const api = createStorefrontsAdminApi(config)
const builderApi = createStorefrontBuilderApi(config)
const storefronts = ref<AdminStorefront[]>([])
const warehouses = ref<StorefrontWarehouseOption[]>([])
const selected = ref<AdminStorefront | null>(null)
const storefrontPages = ref<StorefrontPageListItem[]>([])
const loadingPages = ref(false)
const customPageTitles = reactive<Record<string, string>>({})
const customPageOriginalTitles = ref<Record<string, string>>({})
const customPages = computed(() => storefrontPages.value.filter(p => !p.is_system))
const pendingLogo = ref<File | null>(null)
const loading = ref(true)
const loadFailed = ref(false)
const saving = ref(false)
const savingPublicUi = ref(false)
const creating = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const logoInput = ref<HTMLInputElement | null>(null)
const visibilityPanel = ref<{ hasUnsavedChanges: boolean; saving: boolean } | null>(null)
const visibilityImportRevision = ref(0)
const settingsImportPending = ref(false)
const fontsPanel = ref<{ discardChanges: () => void } | null>(null)
const fontsDirty = ref(false)
const basicsBaseline = ref('')
const publicUiBaseline = ref('')
const activeSection = ref<StorefrontsSection>(route.query.section === 'fonts' ? 'fonts' : 'storefronts')
const activeTab = ref<StorefrontSettingsTab>(
  route.query.tab === 'visibility' ? 'visibility' : 'general',
)

const loadStorefrontPages = async (storefrontId: UUID) => {
  loadingPages.value = true
  try {
    const res = await builderApi.listPages(storefrontId)
    storefrontPages.value = res.items || []
    for (const p of storefrontPages.value) {
      if (!p.is_system) {
        customPageTitles[p.id] = p.title
        customPageOriginalTitles.value[p.id] = p.title
      }
    }
  } catch (err) {
    console.error('Failed to load storefront pages:', err)
    storefrontPages.value = []
  } finally {
    loadingPages.value = false
  }
}

watch(
  () => [selected.value?.id, activeTab.value] as const,
  ([storefrontId, tab]) => {
    if (storefrontId && tab === 'visibility') {
      void loadStorefrontPages(storefrontId)
    }
  },
  { immediate: true },
)

const emptyForm = () => ({
  slug: '',
  is_active: true,
  contact_email: '',
  contact_phone: '',
  warehouse_ids: [] as UUID[],
})
const form = reactive(emptyForm())
const publicUiForm = reactive({
  home_page_key: 'home' as StorefrontPublicPageKey,
  pageLabels: Object.fromEntries(PUBLIC_PAGES.map(page => [page.key, page.defaultLabel])) as Record<StorefrontPublicPageKey, string>,
})

const editing = computed(() => selected.value !== null || creating.value)
const displayedLogoUrl = computed(() => {
  const url = selected.value?.logo_url ?? selected.value?.effective_logo_url
  if (!url) return null
  return `${url}${url.includes('?') ? '&' : '?'}v=${selected.value?.version ?? 0}`
})
const basicsSnapshot = (): string => JSON.stringify(form)
const publicUiSnapshot = (): string => JSON.stringify(publicUiForm)
const basicsDirty = computed(() => basicsSnapshot() !== basicsBaseline.value || pendingLogo.value !== null)
const customPagesDirty = computed(() => {
  return customPages.value.some(
    page => (customPageTitles[page.id]?.trim() ?? '') !== (customPageOriginalTitles.value[page.id] ?? ''),
  )
})
const publicUiDirty = computed(() => publicUiSnapshot() !== publicUiBaseline.value || customPagesDirty.value)
const storefrontDirty = computed(() => basicsDirty.value || publicUiDirty.value)
const hasUnsavedChanges = computed(() => activeSection.value === 'fonts' ? fontsDirty.value : storefrontDirty.value)

const storefrontName = (item: AdminStorefront): string => item.is_default ? 'Основной сайт' : `/${item.slug}`

const showError = (error: unknown, fallback: string) => {
  errorMessage.value = storefrontAdminErrorMessage(error, fallback)
}

const clearFeedback = () => {
  errorMessage.value = ''
  statusMessage.value = ''
  loadFailed.value = false
}

const confirmDiscard = (): boolean => {
  if (!hasUnsavedChanges.value || !import.meta.client) return true
  return window.confirm('Уйти без сохранения? Введённые изменения будут потеряны.')
}

const syncForm = (item: AdminStorefront) => {
  Object.assign(form, {
    slug: item.slug ?? '',
    is_active: item.is_active,
    contact_email: item.contact_email ?? '',
    contact_phone: item.contact_phone ?? '',
    warehouse_ids: [...item.warehouse_ids],
  })
  publicUiForm.home_page_key = item.public_ui.home_page_key
  for (const page of PUBLIC_PAGES) {
    publicUiForm.pageLabels[page.key] = item.public_ui.pages[page.key].title
  }
  basicsBaseline.value = basicsSnapshot()
  publicUiBaseline.value = publicUiSnapshot()
}

const discardStorefrontChanges = () => {
  pendingLogo.value = null
  if (logoInput.value) logoInput.value.value = ''
  if (selected.value) {
    syncForm(selected.value)
    for (const p of customPages.value) {
      customPageTitles[p.id] = customPageOriginalTitles.value[p.id] ?? p.title
    }
  } else {
    Object.assign(form, emptyForm())
    basicsBaseline.value = basicsSnapshot()
    publicUiBaseline.value = publicUiSnapshot()
  }
}

const discardCurrentChanges = () => {
  if (activeSection.value === 'fonts') {
    fontsPanel.value?.discardChanges()
    fontsDirty.value = false
    return
  }
  discardStorefrontChanges()
}

const handleStorefrontUpdated = (saved: AdminStorefront) => {
  selected.value = saved
  const index = storefronts.value.findIndex(item => item.id === saved.id)
  if (index >= 0) storefronts.value[index] = saved
  syncForm(saved)
}

const select = (item: AdminStorefront) => {
  if (selected.value?.id === item.id && !creating.value) return
  if (!confirmDiscard()) return
  discardStorefrontChanges()
  creating.value = false
  selected.value = item
  pendingLogo.value = null
  clearFeedback()
  syncForm(item)
}

const selectSection = async (section: StorefrontsSection) => {
  if (activeSection.value === section) return
  const query = { ...route.query }
  if (section === 'fonts') query.section = 'fonts'
  else delete query.section
  delete query.tab
  await router.replace({ query })
}

const selectAdjacentSection = (section: StorefrontsSection, offset: number) => {
  const index = SECTIONS.findIndex(candidate => candidate.key === section)
  const next = SECTIONS[(index + offset + SECTIONS.length) % SECTIONS.length]
  if (!next) return
  void selectSection(next.key).then(() => {
    if (activeSection.value !== next.key) return
    nextTick(() => document.getElementById(`storefronts-section-tab-${next.key}`)?.focus())
  })
}

const selectTab = async (tab: StorefrontSettingsTab) => {
  if (activeTab.value === tab) return
  const query = { ...route.query }
  if (tab === 'general') delete query.tab
  else query.tab = tab
  await router.replace({ query })
}

const selectAdjacentTab = (tab: StorefrontSettingsTab, offset: number) => {
  const index = TABS.findIndex(candidate => candidate.key === tab)
  const next = TABS[(index + offset + TABS.length) % TABS.length]
  if (!next) return
  void selectTab(next.key).then(() => {
    if (activeTab.value !== next.key) return
    nextTick(() => document.getElementById(`storefront-tab-${next.key}`)?.focus())
  })
}

const startCreate = () => {
  if (!confirmDiscard()) return
  discardStorefrontChanges()
  selected.value = null
  creating.value = true
  pendingLogo.value = null
  activeTab.value = 'general'
  const query = { ...route.query }
  delete query.tab
  void router.replace({ query })
  clearFeedback()
  Object.assign(form, emptyForm())
  basicsBaseline.value = basicsSnapshot()
}

const cancelCreate = () => {
  if (!confirmDiscard()) return
  discardStorefrontChanges()
  creating.value = false
  selected.value = storefronts.value[0] ?? null
  if (selected.value) syncForm(selected.value)
}

const load = async () => {
  loading.value = true
  clearFeedback()
  try {
    const [storefrontResponse, warehouseResponse] = await Promise.all([
      api.list(),
      api.listWarehouseOptions(),
    ])
    storefronts.value = storefrontResponse.items
    warehouses.value = warehouseResponse.warehouses
    const activeId = selected.value?.id
    const next = storefronts.value.find(item => item.id === activeId) ?? storefronts.value[0] ?? null
    selected.value = next
    if (next) syncForm(next)
  } catch (error) {
    loadFailed.value = true
    showError(error, 'Не удалось загрузить витрины')
  } finally {
    loading.value = false
  }
}

const selectLogo = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) return
  if (!ALLOWED_LOGO_TYPES.has(file.type) || file.size > MAX_LOGO_SIZE) {
    errorMessage.value = 'Выберите PNG, JPEG или WebP размером не более 5 МиБ'
    input.value = ''
    pendingLogo.value = null
    return
  }
  clearFeedback()
  pendingLogo.value = file
}

const handleSettingsImported = async (result: StorefrontSettingsImportResult) => {
  // Discard only after a successful import; the transfer panel obtained explicit consent.
  discardStorefrontChanges()
  creating.value = false
  // Import replaces visibility even when the selected storefront UUID stays the same.
  // A dedicated key avoids resetting drafts on ordinary manual saves.
  visibilityImportRevision.value += 1
  await load()
  const summary = `Импорт завершён. Создано витрин: ${result.created.length}. Обновлено: ${result.updated.length}.`
  if (loadFailed.value) errorMessage.value = `${summary} Не удалось обновить список. Нажмите «Повторить».`
  else statusMessage.value = summary
}

const saveBasics = async () => {
  saving.value = true
  clearFeedback()
  try {
    const body: StorefrontWriteRequest = selected.value?.is_default
      ? { contact_email: form.contact_email || null, contact_phone: form.contact_phone || null }
      : {
          slug: form.slug,
          is_active: form.is_active,
          contact_email: form.contact_email || null,
          contact_phone: form.contact_phone || null,
          warehouse_ids: form.warehouse_ids,
        }
    let saved = selected.value
      ? await api.update(selected.value.id, body)
      : await api.create(body)
    if (pendingLogo.value) saved = await api.uploadLogo(saved.id, pendingLogo.value)
    selected.value = saved
    creating.value = false
    pendingLogo.value = null
    if (logoInput.value) logoInput.value.value = ''
    await load()
    statusMessage.value = 'Витрина сохранена'
  } catch (error) {
    showError(error, 'Не удалось сохранить витрину')
  } finally {
    saving.value = false
  }
}

const savePublicUi = async () => {
  if (!selected.value || savingPublicUi.value) return
  savingPublicUi.value = true
  clearFeedback()
  try {
    const saved = await api.update(selected.value.id, {
      public_ui: {
        home_page_key: publicUiForm.home_page_key,
        pages: {
          home: { title: publicUiForm.pageLabels.home.trim() },
          about: { title: publicUiForm.pageLabels.about.trim() },
          special_equipment_catalog: { title: publicUiForm.pageLabels.special_equipment_catalog.trim() },
        },
      },
    })
    selected.value = saved
    const index = storefronts.value.findIndex(item => item.id === saved.id)
    if (index >= 0) storefronts.value[index] = saved
    syncForm(saved)

    const customUpdatePromises: Promise<unknown>[] = []
    for (const page of customPages.value) {
      const currentTitle = customPageTitles[page.id]?.trim()
      const originalTitle = customPageOriginalTitles.value[page.id]
      if (currentTitle && currentTitle !== originalTitle) {
        customUpdatePromises.push(
          builderApi.updatePageMetadata(selected.value.id, page.id, {
            title: currentTitle,
          }).then((updated) => {
            page.title = updated.title
            customPageTitles[page.id] = updated.title
            customPageOriginalTitles.value[page.id] = updated.title
          }),
        )
      }
    }
    if (customUpdatePromises.length > 0) {
      await Promise.all(customUpdatePromises)
    }

    statusMessage.value = 'Публичные страницы сохранены'
  } catch (error) {
    showError(error, 'Не удалось сохранить публичные страницы')
  } finally {
    savingPublicUi.value = false
  }
}

const removeLogo = async () => {
  if (!selected.value) return
  saving.value = true
  clearFeedback()
  try {
    selected.value = await api.deleteLogo(selected.value.id)
    await load()
    statusMessage.value = 'Логотип удалён'
  } catch (error) {
    showError(error, 'Не удалось удалить логотип')
  } finally {
    saving.value = false
  }
}

const resolveSection = (value: unknown): StorefrontsSection => value === 'fonts' ? 'fonts' : 'storefronts'
const resolveSettingsTab = (value: unknown): StorefrontSettingsTab =>
  value === 'visibility' ? 'visibility' : 'general'

onBeforeRouteUpdate((to) => {
  if (settingsImportPending.value) return false
  const targetSection = resolveSection(to.query.section)
  const sectionChanges = targetSection !== activeSection.value
  const tabChanges = targetSection === 'storefronts' && resolveSettingsTab(to.query.tab) !== activeTab.value
  if (!sectionChanges && !tabChanges) return true
  if (!confirmDiscard()) return false
  discardCurrentChanges()
  return true
})

onBeforeRouteLeave(() => !settingsImportPending.value && confirmDiscard())

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (!hasUnsavedChanges.value && !settingsImportPending.value) return
  event.preventDefault()
  event.returnValue = ''
}

watch(() => route.query.section, (value) => {
  activeSection.value = resolveSection(value)
  clearFeedback()
  if (activeSection.value === 'storefronts') void load()
})
watch(() => route.query.tab, (value) => {
  activeTab.value = resolveSettingsTab(value)
  clearFeedback()
})

basicsBaseline.value = basicsSnapshot()
publicUiBaseline.value = publicUiSnapshot()

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (activeSection.value === 'storefronts') void load()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>
