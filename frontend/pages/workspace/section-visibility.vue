<script setup lang="ts">
definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-workspace', 'require-admin'],
})

await navigateTo('/workspace/storefronts?tab=visibility', { redirectCode: 301 })
</script>
