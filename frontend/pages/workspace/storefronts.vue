<template>
  <NuxtPage v-if="isChildRoute" />
  <AdminStorefrontsPanel v-else />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'

const AdminStorefrontsPanel = defineAsyncComponent(
  () => import('~/features/admin/storefronts/components/AdminStorefrontsPanel.vue'),
)
const route = useRoute()
const isChildRoute = computed(() => route.path !== '/workspace/storefronts')

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
