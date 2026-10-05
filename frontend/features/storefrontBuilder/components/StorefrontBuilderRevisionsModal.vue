<template>
  <div
    v-if="builderStore.showRevisionsModal"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
    @click.self="builderStore.showRevisionsModal = false"
  >
    <div class="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl overflow-hidden border border-slate-200">
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/70">
        <div>
          <h3 class="text-base font-semibold text-slate-900">История ревизий страницы</h3>
          <p class="mt-0.5 text-xs text-slate-500">
            Снимки состояний черновика, сохраненные ранее.
          </p>
        </div>
        <button
          type="button"
          class="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          @click="builderStore.showRevisionsModal = false"
        >
          <XMarkIcon class="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      <!-- Revisions List -->
      <div class="flex-1 overflow-y-auto p-6">
        <div v-if="builderStore.revisions.length === 0" class="py-12 text-center text-xs text-slate-500">
          История ревизий для этой страницы пока пуста. При каждом сохранении черновика здесь будет появляться новая версия.
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="rev in builderStore.revisions"
            :key="rev.id"
            class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-xs transition-all hover:border-blue-400"
          >
            <div>
              <div class="flex items-center gap-2 mb-1">
                <span class="rounded bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-700">
                  v{{ rev.version }}
                </span>
                <span class="text-xs font-semibold text-slate-900">
                  {{ rev.summary || 'Автоматический снимок' }}
                </span>
              </div>
              <p class="text-[11px] text-slate-500">
                {{ formatRevisionDate(rev.created_at) }}
              </p>
            </div>

            <button
              type="button"
              class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 hover:text-blue-600 transition-colors"
              @click="restore(rev)"
            >
              Восстановить версию
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'
import type { StorefrontPageRevision } from '../types'

const builderStore = useStorefrontBuilderStore()

function formatRevisionDate(isoStr: string) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

function restore(rev: StorefrontPageRevision) {
  if (confirm(`Восстановить версию v${rev.version}? Текущий несохраненный черновик будет перезаписан.`)) {
    builderStore.restoreRevision(rev.id)
    builderStore.showRevisionsModal = false
  }
}
</script>
