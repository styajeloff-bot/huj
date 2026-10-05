<template>
  <div
    v-if="builderStore.showTemplatesModal"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
    @click.self="builderStore.showTemplatesModal = false"
  >
    <div class="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl overflow-hidden border border-slate-200">
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/70">
        <div>
          <h3 class="text-base font-semibold text-slate-900">Библиотека готовых шаблонов</h3>
          <p class="mt-0.5 text-xs text-slate-500">
            Применение шаблона заменит текущие секции холста на преднастроенную структуру.
          </p>
        </div>
        <button
          type="button"
          class="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          @click="builderStore.showTemplatesModal = false"
        >
          <XMarkIcon class="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      <!-- Templates Grid -->
      <div class="flex-1 overflow-y-auto p-6">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            v-for="tpl in builderStore.templates"
            :key="tpl.code"
            class="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-xs transition-all hover:border-blue-500 hover:shadow-md"
          >
            <div>
              <div class="flex items-center justify-between mb-2">
                <span class="rounded bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 uppercase">
                  {{ tpl.category }}
                </span>
                <span class="text-[10px] text-slate-400 font-mono">{{ tpl.code }}</span>
              </div>
              <h4 class="text-sm font-semibold text-slate-900">{{ tpl.name }}</h4>
              <p class="mt-1 text-xs text-slate-500 leading-relaxed">{{ tpl.description }}</p>
            </div>

            <div class="mt-6 pt-4 border-t border-slate-100">
              <button
                type="button"
                class="w-full rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-500 transition-colors"
                @click="apply(tpl)"
              >
                Применить шаблон
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'
import type { StorefrontTemplate } from '../types'

const builderStore = useStorefrontBuilderStore()

function apply(template: StorefrontTemplate) {
  if (confirm(`Применить шаблон «${template.name}»? Текущие изменения черновика будут перезаписаны.`)) {
    builderStore.applyTemplate(template.layout)
    builderStore.showTemplatesModal = false
  }
}
</script>
