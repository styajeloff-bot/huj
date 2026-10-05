<template>
  <div class="fixed inset-0 z-40 flex flex-col bg-slate-100 overflow-hidden">
    <!-- Top Bar -->
    <StorefrontBuilderTopBar />

    <!-- Main Workspace Area -->
    <div class="flex flex-1 overflow-hidden min-h-0">
      <!-- Left Sidebar: Widgets & Structure & Global Styles -->
      <StorefrontBuilderSidebar v-show="!builderStore.previewMode" />

      <!-- Center Live Canvas -->
      <StorefrontBuilderCanvas />

      <!-- Right Inspector: Selected Element Properties -->
      <StorefrontBuilderInspector v-show="!builderStore.previewMode" />
    </div>

    <!-- Modals -->
    <StorefrontBuilderTemplatesModal />
    <StorefrontBuilderPresetTransferModal />
    <StorefrontBuilderRevisionsModal />

    <!-- Publish Confirmation Modal -->
    <div
      v-if="builderStore.showPublishConfirmModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
      @click.self="builderStore.showPublishConfirmModal = false"
    >
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-200">
        <h3 class="text-base font-semibold text-slate-900">Опубликовать витрину?</h3>
        <p class="mt-2 text-xs text-slate-600 leading-relaxed">
          Текущий черновик страницы станет активным на публичном сайте для всех посетителей.
        </p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            class="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            @click="builderStore.showPublishConfirmModal = false"
          >
            Отмена
          </button>
          <button
            type="button"
            class="rounded-lg bg-green-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-green-500 transition-colors"
            :disabled="builderStore.isPublishing"
            @click="confirmPublish"
          >
            {{ builderStore.isPublishing ? 'Публикуем…' : 'Да, опубликовать' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create Page Modal -->
    <div
      v-if="builderStore.showCreatePageModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
      @click.self="closeCreatePageModal"
    >
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-200">
        <h3 class="text-base font-semibold text-slate-900">Создать новую страницу</h3>

        <div
          v-if="createPageError"
          class="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"
          role="alert"
        >
          {{ createPageError }}
        </div>

        <form class="mt-4 space-y-3" @submit.prevent="submitCreatePage">
          <div>
            <label class="block text-xs font-medium text-slate-700 mb-1">Название страницы</label>
            <input
              v-model.trim="newPageTitle"
              type="text"
              required
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="Например, Спецпредложение и лизинг"
              @input="onTitleInput"
            >
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-700 mb-1">URL slug (путь страницы)</label>
            <input
              v-model.trim="newPageSlug"
              type="text"
              required
              pattern="[a-z0-9-]+$"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="specpredlozhenie-i-lizing"
              @input="isSlugManuallyEdited = true"
            >
            <div class="mt-1 flex items-center justify-between text-[11px] text-slate-500">
              <span>Латинские буквы, цифры и дефис</span>
              <span>URL: <span class="font-mono font-medium text-blue-600">{{ previewUrl }}</span></span>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-700 mb-1">Ключ страницы (page_key)</label>
            <input
              v-model.trim="newPageKey"
              type="text"
              required
              pattern="[a-z0-9_-]+"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="specpredlozhenie-i-lizing"
            >
            <span class="text-[10px] text-slate-500 mt-0.5 block">Латинские буквы, цифры, дефис, подчеркивание</span>
          </div>
          <div class="mt-6 flex justify-end gap-3 pt-3">
            <button
              type="button"
              class="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
              @click="closeCreatePageModal"
            >
              Отмена
            </button>
            <button
              type="submit"
              class="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-500 transition-colors disabled:opacity-50"
              :disabled="isSubmittingPage"
            >
              {{ isSubmittingPage ? 'Создание…' : 'Создать страницу' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStorefrontBuilderStore } from '~/features/storefrontBuilder/store/storefrontBuilder'
import { slugify } from '~/features/storefrontBuilder/utils/slugify'
import StorefrontBuilderTopBar from '~/features/storefrontBuilder/components/StorefrontBuilderTopBar.vue'
import StorefrontBuilderSidebar from '~/features/storefrontBuilder/components/StorefrontBuilderSidebar.vue'
import StorefrontBuilderCanvas from '~/features/storefrontBuilder/components/StorefrontBuilderCanvas.vue'
import StorefrontBuilderInspector from '~/features/storefrontBuilder/components/StorefrontBuilderInspector.vue'
import StorefrontBuilderTemplatesModal from '~/features/storefrontBuilder/components/StorefrontBuilderTemplatesModal.vue'
import StorefrontBuilderPresetTransferModal from '~/features/storefrontBuilder/components/StorefrontBuilderPresetTransferModal.vue'
import StorefrontBuilderRevisionsModal from '~/features/storefrontBuilder/components/StorefrontBuilderRevisionsModal.vue'

definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-workspace'],
})

const route = useRoute()
const builderStore = useStorefrontBuilderStore()

const newPageTitle = ref('')
const newPageSlug = ref('')
const newPageKey = ref('')
const isSlugManuallyEdited = ref(false)
const createPageError = ref('')
const isSubmittingPage = ref(false)

function onTitleInput() {
  if (!isSlugManuallyEdited.value) {
    const generated = slugify(newPageTitle.value)
    newPageSlug.value = generated
    newPageKey.value = generated
  }
}

const previewUrl = computed(() => {
  const slug = newPageSlug.value || 'slug'
  const isDefault = builderStore.storefront?.is_default
  const sfSlug = builderStore.storefront?.slug
  return isDefault || !sfSlug ? `/${slug}` : `/${sfSlug}/${slug}`
})

function closeCreatePageModal() {
  builderStore.showCreatePageModal = false
  newPageTitle.value = ''
  newPageSlug.value = ''
  newPageKey.value = ''
  isSlugManuallyEdited.value = false
  createPageError.value = ''
}

watch(
  () => builderStore.showCreatePageModal,
  (open) => {
    if (open) {
      newPageTitle.value = ''
      newPageSlug.value = ''
      newPageKey.value = ''
      isSlugManuallyEdited.value = false
      createPageError.value = ''
    }
  },
)

onMounted(async () => {
  const storefrontId = route.params.id as string
  if (storefrontId) {
    const targetPage = route.query.page ? (route.query.page as string) : undefined
    await builderStore.loadPage(storefrontId, targetPage)
  }
})

watch(
  () => route.query.page,
  async (newPage) => {
    const storefrontId = route.params.id as string
    if (storefrontId && newPage && newPage !== builderStore.activePageId) {
      await builderStore.loadPage(storefrontId, newPage as string)
    }
  },
)

async function confirmPublish() {
  await builderStore.publishPage()
  builderStore.showPublishConfirmModal = false
}

async function submitCreatePage() {
  if (!newPageTitle.value || !newPageKey.value) return
  createPageError.value = ''
  isSubmittingPage.value = true
  try {
    const created = await builderStore.createPage({
      title: newPageTitle.value,
      page_key: newPageKey.value,
      slug: newPageSlug.value || slugify(newPageTitle.value),
    })
    if (created) {
      closeCreatePageModal()
    }
  } catch (err: any) {
    createPageError.value =
      err?.data?.message ||
      err?.data?.detail ||
      err?.message ||
      builderStore.error ||
      'Ошибка при создании страницы'
  } finally {
    isSubmittingPage.value = false
  }
}
</script>
