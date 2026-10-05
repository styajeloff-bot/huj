<template>
  <header class="flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 select-none shadow-sm z-30">
    <!-- Left Section: Back, Storefront Name, Page Selector -->
    <div class="flex items-center gap-3 min-w-0">
      <NuxtLink
        to="/workspace/storefronts"
        class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        title="Назад к списку витрин"
      >
        <ArrowLeftIcon class="h-5 w-5" aria-hidden="true" />
      </NuxtLink>

      <div class="h-5 w-px bg-gray-200" aria-hidden="true" />

      <!-- Storefront Name & Status -->
      <div class="flex items-center gap-2 min-w-0">
        <span class="truncate font-semibold text-gray-900 text-sm max-w-[200px]" :title="storefrontTitle">
          {{ storefrontTitle }}
        </span>
        <span
          class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium"
          :class="builderStore.storefront?.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'"
        >
          {{ builderStore.storefront?.is_active ? 'Активна' : 'Тестовая' }}
        </span>
      </div>

      <div class="h-5 w-px bg-gray-200" aria-hidden="true" />

      <!-- Page Selector -->
      <div class="relative">
        <select
          :value="builderStore.activePageId || ''"
          class="h-9 rounded-lg border border-gray-300 bg-white pl-3 pr-8 text-xs font-medium text-gray-800 hover:border-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 cursor-pointer"
          @change="handlePageSelect(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="page in builderStore.availablePages"
            :key="page.id"
            :value="page.id"
          >
            {{ page.title }} ({{ page.page_key }})
          </option>
          <option value="__create_new__">+ Создать страницу…</option>
        </select>
      </div>

      <!-- Dirty / Status Badge -->
      <div class="flex items-center gap-2">
        <span
          v-if="builderStore.hasUnpublishedChanges"
          class="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 border border-amber-200"
          title="Есть несохраненные правки или неопубликованный черновик"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
          {{ builderStore.isDirty ? 'Несохраненные изменения' : 'Неопубликованный черновик' }}
        </span>
        <div v-else class="flex items-center gap-2">
          <span
            class="inline-flex items-center gap-1.5 rounded-md bg-green-50 px-2.5 py-1 text-xs font-medium text-green-800 border border-green-200"
            title="Все изменения страницы опубликованы на публичной витрине"
          >
            <CheckCircleIcon class="h-3.5 w-3.5 text-green-600" aria-hidden="true" />
            Все изменения опубликованы
          </span>

          <a
            v-if="isPagePublished && publishedPageUrl"
            :href="publishedPageUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 border border-blue-200 hover:bg-blue-100 transition-colors"
            title="Открыть опубликованную страницу в новой вкладке"
          >
            <span>Открыть страницу</span>
            <ArrowTopRightOnSquareIcon class="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>

    <!-- Center Section: Undo / Redo & Responsive Mode Toggles -->
    <div class="flex items-center gap-4">
      <!-- Undo / Redo -->
      <div class="flex items-center rounded-lg border border-gray-200 bg-gray-50 p-0.5">
        <button
          type="button"
          class="inline-flex h-8 w-8 items-center justify-center rounded text-gray-600 transition-colors hover:bg-white hover:text-gray-900 disabled:opacity-30 disabled:pointer-events-none"
          :disabled="!builderStore.canUndo"
          title="Отменить действие (Ctrl+Z / Cmd+Z)"
          @click="builderStore.undo()"
        >
          <ArrowUturnLeftIcon class="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="inline-flex h-8 w-8 items-center justify-center rounded text-gray-600 transition-colors hover:bg-white hover:text-gray-900 disabled:opacity-30 disabled:pointer-events-none"
          :disabled="!builderStore.canRedo"
          title="Повторить действие (Ctrl+Shift+Z / Cmd+Shift+Z)"
          @click="builderStore.redo()"
        >
          <ArrowUturnRightIcon class="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <!-- Viewport Device Switcher -->
      <div class="flex items-center rounded-lg border border-gray-200 bg-gray-50 p-0.5" role="group" aria-label="Разрешение холста">
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors"
          :class="builderStore.previewDevice === 'desktop' ? 'bg-white text-blue-700 shadow-sm font-semibold' : 'text-gray-600 hover:text-gray-900'"
          title="Десктоп (1440px)"
          @click="builderStore.setPreviewDevice('desktop')"
        >
          <ComputerDesktopIcon class="h-4 w-4" aria-hidden="true" />
          <span>1440px</span>
        </button>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors"
          :class="builderStore.previewDevice === 'laptop' ? 'bg-white text-blue-700 shadow-sm font-semibold' : 'text-gray-600 hover:text-gray-900'"
          title="Ноутбук (1024px)"
          @click="builderStore.setPreviewDevice('laptop')"
        >
          <RectangleGroupIcon class="h-4 w-4" aria-hidden="true" />
          <span>1024px</span>
        </button>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors"
          :class="builderStore.previewDevice === 'tablet' ? 'bg-white text-blue-700 shadow-sm font-semibold' : 'text-gray-600 hover:text-gray-900'"
          title="Планшет (768px)"
          @click="builderStore.setPreviewDevice('tablet')"
        >
          <DeviceTabletIcon class="h-4 w-4" aria-hidden="true" />
          <span>768px</span>
        </button>
      </div>
    </div>

    <!-- Right Section: Modals & Actions -->
    <div class="flex items-center gap-2">
      <!-- Templates Button -->
      <button
        type="button"
        class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 text-xs font-medium text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        @click="builderStore.showTemplatesModal = true"
      >
        <SquaresPlusIcon class="h-4 w-4 text-gray-500" aria-hidden="true" />
        <span>Шаблоны</span>
      </button>

      <!-- Preset Transfer Dropdown / Buttons -->
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 text-xs font-medium text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          title="Скачать JSON пресет страницы"
          @click="exportPresetFile"
        >
          <ArrowDownTrayIcon class="h-4 w-4 text-gray-500" aria-hidden="true" />
          <span>Экспорт</span>
        </button>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 text-xs font-medium text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          title="Загрузить JSON пресет страницы"
          @click="builderStore.showPresetModal = true"
        >
          <ArrowUpTrayIcon class="h-4 w-4 text-gray-500" aria-hidden="true" />
          <span>Импорт</span>
        </button>
      </div>

      <!-- Preview Toggle -->
      <button
        type="button"
        class="inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        :class="builderStore.previewMode ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'"
        title="Переключить режим чистого предпросмотра без рамок конструктора"
        @click="builderStore.previewMode = !builderStore.previewMode"
      >
        <EyeIcon class="h-4 w-4" aria-hidden="true" />
        <span>{{ builderStore.previewMode ? 'Редактирование' : 'Предпросмотр' }}</span>
      </button>

      <!-- Save Draft Button -->
      <button
        type="button"
        class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        :disabled="builderStore.isSaving"
        @click="builderStore.saveDraft()"
      >
        <ArrowPathIcon v-if="builderStore.isSaving" class="h-4 w-4 animate-spin text-gray-500" aria-hidden="true" />
        <CloudArrowUpIcon v-else class="h-4 w-4 text-gray-500" aria-hidden="true" />
        <span>{{ builderStore.isSaving ? 'Сохранение…' : 'Сохранить черновик' }}</span>
      </button>

      <!-- Publish Button -->
      <button
        type="button"
        class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-xs font-semibold text-white shadow-sm hover:bg-blue-500 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
        :disabled="builderStore.isPublishing"
        @click="builderStore.showPublishConfirmModal = true"
      >
        <ArrowPathIcon v-if="builderStore.isPublishing" class="h-4 w-4 animate-spin text-white" aria-hidden="true" />
        <GlobeAltIcon v-else class="h-4 w-4 text-white" aria-hidden="true" />
        <span>{{ builderStore.isPublishing ? 'Публикация…' : 'Опубликовать' }}</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowDownTrayIcon,
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowTopRightOnSquareIcon,
  ArrowUpTrayIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
  CheckCircleIcon,
  CloudArrowUpIcon,
  ComputerDesktopIcon,
  DeviceTabletIcon,
  EyeIcon,
  GlobeAltIcon,
  RectangleGroupIcon,
  SquaresPlusIcon,
} from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'

const builderStore = useStorefrontBuilderStore()

const storefrontTitle = computed(() => {
  if (!builderStore.storefront) return 'Загрузка витрины…'
  return builderStore.storefront.is_default
    ? 'Основной сайт'
    : `/${builderStore.storefront.slug || 'витрина'}`
})

const isPagePublished = computed(() => {
  return builderStore.currentPage?.status === 'published' || !!builderStore.currentPage?.published_at
})

const publishedPageUrl = computed(() => {
  if (!builderStore.currentPage) return null
  const isDefault = builderStore.storefront?.is_default
  const sfSlug = builderStore.storefront?.slug
  const pageKey = builderStore.currentPage.page_key
  const pageSlug = builderStore.currentPage.slug

  if (pageKey === 'home') {
    return isDefault || !sfSlug ? '/' : `/${sfSlug}`
  }
  if (pageKey === 'about') {
    return isDefault || !sfSlug ? '/about' : `/${sfSlug}/about`
  }
  if (pageKey === 'special_equipment_catalog') {
    return isDefault || !sfSlug ? '/special-equipment' : `/${sfSlug}/special-equipment`
  }
  const slug = pageSlug || pageKey
  return isDefault || !sfSlug ? `/${slug}` : `/${sfSlug}/${slug}`
})

function handlePageSelect(value: string) {
  if (value === '__create_new__') {
    builderStore.showCreatePageModal = true
  } else if (value && value !== builderStore.activePageId) {
    if (builderStore.activeStorefrontId) {
      builderStore.loadPage(builderStore.activeStorefrontId, value)
    }
  }
}

function exportPresetFile() {
  const jsonContent = builderStore.exportPreset()
  const blob = new Blob([jsonContent], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const dateStr = new Date().toISOString().slice(0, 10)
  const slug = builderStore.storefront?.slug || 'default'
  const pageKey = builderStore.currentPage?.page_key || 'page'
  link.href = url
  link.download = `storefront-preset-${slug}-${pageKey}-${dateStr}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>
