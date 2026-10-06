<template>
  <FastDealCardPage v-if="dealId" :key="dealId" :deal-id="dealId" />
  <div v-else class="max-w-3xl mx-auto rounded-lg bg-white p-8 text-center shadow-sm" role="alert">
    <h1 class="text-xl font-semibold text-gray-900">Сделка не найдена</h1>
    <p class="mt-2 text-sm text-gray-600">Некорректная ссылка на сделку.</p>
    <NuxtLink to="/workspace/fast-deals" class="btn-primary mt-4 inline-flex">К списку сделок</NuxtLink>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FastDealCardPage from '~/features/fast-deals/components/FastDealCardPage.vue'
import { isUuid } from '~/types/ids'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'], key: route => route.fullPath })

const route = useRoute()
// The id is an opaque UUID string; anything else is not a deal link.
const dealId = computed(() => (typeof route.params.id === 'string' && isUuid(route.params.id) ? route.params.id : null))
</script>
